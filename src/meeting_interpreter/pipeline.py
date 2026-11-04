from __future__ import annotations

import asyncio
import base64
import itertools
import math
import time
from collections.abc import AsyncIterator
import os
import re

from .asr import ASRBackend, MLXWhisperBackend, MockASRBackend
from .models import AudioEvent, CaptionEvent
from .speaker import PendingSpeakerBackend, PyannoteSpeakerBackend, SpeakerBackend
from .translation import NLLBTranslationBackend, OllamaTranslationBackend, TranslationBackend


def is_silent_pcm16(audio: bytes, threshold: float = 0.015) -> bool:
    """Return whether a PCM16 mono chunk is below the voice activity floor."""
    if not audio:
        return True
    if len(audio) < 2 or len(audio) % 2:
        return False
    samples = memoryview(audio).cast("h")
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    rms = math.sqrt(mean_square) / 32768.0
    return rms < threshold


def pcm16_activity(audio: bytes, sample_rate: int) -> tuple[float, float, float]:
    """Return DC-corrected RMS, peak and active milliseconds in 20 ms frames.

    This is a conservative sound gate, not a speaker/semantic speech detector.
    Decoder confidence is checked separately so quiet speech remains usable.
    """
    if len(audio) % 2:
        raise ValueError("音频必须是完整的 PCM16 单声道采样")
    samples = memoryview(audio).cast("h")
    if not samples:
        return 0.0, 0.0, 0.0
    frame_size = max(1, sample_rate // 50)
    total_square = 0.0
    peak = 0.0
    active_samples = 0
    for offset in range(0, len(samples), frame_size):
        frame = samples[offset:offset + frame_size]
        mean = sum(frame) / len(frame)
        square = sum((sample - mean) ** 2 for sample in frame)
        frame_rms = math.sqrt(square / len(frame)) / 32768.0
        frame_peak = max(abs(sample - mean) for sample in frame) / 32768.0
        total_square += square
        peak = max(peak, frame_peak)
        if frame_rms >= 0.003 and frame_peak >= 0.006:
            active_samples += len(frame)
    return math.sqrt(total_square / len(samples)) / 32768.0, peak, active_samples / sample_rate * 1000


def text_matches_language(text: str, language: str) -> bool:
    if language == "zh":
        return bool(re.search(r"[\u3400-\u9fff]", text)) or not re.search(r"[A-Za-z\u3040-\u30ff]", text)
    if language == "ja":
        return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text)) or not re.search(r"[A-Za-z]", text)
    return True


class Pipeline:
    """Streaming pipeline boundary.

    The mock implementation keeps the API testable without downloading model weights.
    Real adapters should replace `process_audio` while preserving CaptionEvent semantics.
    """

    def __init__(self, source_language: str = "auto", target_language: str = "zh", mode: str | None = None, speaker_mode: str | None = None, asr_backend: ASRBackend | None = None, translator_backend: TranslationBackend | None = None) -> None:
        self.source_language = source_language
        self.target_language = target_language
        self.mode = mode or os.getenv("MEETING_INTERPRETER_MODE", "mock")
        self._sequence = itertools.count(1)
        self._clock_ms = 0
        self._buffers: dict[str, bytearray] = {}
        self._audio_ms: dict[str, int] = {}
        self._last_infer_ms: dict[str, int] = {}
        self._last_text: dict[str, str] = {}
        self._last_voice_ms: dict[str, int] = {}
        self._voice_duration_ms: dict[str, float] = {}
        self.audio_status: dict[str, object] = {"state": "silent", "rms": 0.0, "peak": 0.0, "message": "等待声音输入"}
        self._active_segment_id: dict[str, str] = {}
        self._active_start_ms: dict[str, int] = {}
        self._mock_last_audio_at: dict[str, float] = {}
        self._mock_phrase_emitted: dict[str, bool] = {}
        if self.mode == "local":
            self.asr: ASRBackend = (asr_backend.for_language(source_language) if isinstance(asr_backend, MLXWhisperBackend) else asr_backend) or MLXWhisperBackend(
                model=os.getenv("MEETING_INTERPRETER_ASR_MODEL", "mlx-community/whisper-medium-mlx-8bit"),
                language=self.source_language,
            )
            translation_backend = os.getenv("MEETING_INTERPRETER_TRANSLATION_BACKEND", "nllb").lower()
            if translator_backend is not None:
                self.translator = translator_backend
            elif translation_backend == "ollama":
                self.translator = OllamaTranslationBackend(
                    model=os.getenv("MEETING_INTERPRETER_OLLAMA_MODEL", "translategemma:4b"),
                    base_url=os.getenv("MEETING_INTERPRETER_OLLAMA_URL", "http://127.0.0.1:11434"),
                    timeout=float(os.getenv("MEETING_INTERPRETER_OLLAMA_TIMEOUT", "180")),
                    keep_alive=os.getenv("MEETING_INTERPRETER_OLLAMA_KEEP_ALIVE", "24h"),
                )
            else:
                self.translator = NLLBTranslationBackend(
                    model_name=os.getenv("MEETING_INTERPRETER_TRANSLATION_MODEL", "facebook/nllb-200-distilled-600M"),
                    device=os.getenv("MEETING_INTERPRETER_TRANSLATION_DEVICE", "auto"),
                )
            if (speaker_mode or os.getenv("MEETING_INTERPRETER_SPEAKER_MODE", "none")) == "pyannote":
                self.speaker: SpeakerBackend = PyannoteSpeakerBackend(
                    model_name=os.getenv("MEETING_INTERPRETER_SPEAKER_MODEL", "pyannote/speaker-diarization-community-1"),
                    token=os.getenv("HF_TOKEN"),
                    device=os.getenv("MEETING_INTERPRETER_SPEAKER_DEVICE", "cpu"),
                    max_speakers=int(os.getenv("MEETING_INTERPRETER_MAX_SPEAKERS", "4")),
                )
            else:
                self.speaker = PendingSpeakerBackend()
        else:
            self.asr = MockASRBackend()
            self.translator = None
            self.speaker = PendingSpeakerBackend()

    async def process_audio(self, event: AudioEvent) -> AsyncIterator[CaptionEvent]:
        # Decode now so malformed input is rejected before real model inference is added.
        try:
            raw_audio = base64.b64decode(event.audio_base64, validate=True)
        except ValueError as exc:
            raise ValueError("audio_base64 is not valid base64") from exc

        if self.mode == "local":
            async for yield_event in self._process_local(event, raw_audio):
                yield yield_event
            return

        if is_silent_pcm16(raw_audio, threshold=0.015):
            return

        # Mock mode is only a transport/demo fallback. Treat a continuous stream
        # of chunks as one utterance so microphone noise cannot create an endless
        # list of identical demo captions. A new caption is allowed after an
        # actual pause in the incoming audio.
        now = time.monotonic()
        last_audio_at = self._mock_last_audio_at.get(event.session_id)
        if last_audio_at is not None and now - last_audio_at >= 1.2:
            self._mock_phrase_emitted[event.session_id] = False
        self._mock_last_audio_at[event.session_id] = now
        if self._mock_phrase_emitted.get(event.session_id, False):
            return
        self._mock_phrase_emitted[event.session_id] = True

        # This delay simulates a small streaming chunk and keeps the demo responsive.
        await asyncio.sleep(0.03)
        segment = next(self._sequence)
        start_ms = self._clock_ms
        self._clock_ms += 900
        yield CaptionEvent(
            session_id=event.session_id,
            segment_id=f"seg-{segment:06d}",
            speaker_id=f"SPEAKER_{(segment - 1) % 2:02d}",
            source_language="ja" if segment % 2 else "en",
            target_language=self.target_language,
            original_text="これはローカル会議翻訳の演示です。" if segment % 2 else "This is a local meeting translation demo.",
            translated_text="这是本地会议翻译演示。" if segment % 2 else "这是一个本地会议翻译演示。",
            is_final=True,
            start_ms=start_ms,
            end_ms=self._clock_ms,
        )

    async def _process_local(self, event: AudioEvent, raw_audio: bytes) -> AsyncIterator[CaptionEvent]:
        if event.channels != 1:
            raise ValueError("语音识别需要单声道音频")
        rms, peak, active_ms = pcm16_activity(raw_audio, event.sample_rate)
        self.audio_status = {"state": "sound" if active_ms else "silent", "rms": round(rms, 5), "peak": round(peak, 5),
                             "message": "收到声音，正在识别" if active_ms else "静音或音量较低，等待讲话"}
        buffer = self._buffers.setdefault(event.session_id, bytearray())
        buffer.extend(raw_audio)
        chunk_ms = round(len(raw_audio) / 2 / event.sample_rate * 1000)
        audio_ms = self._audio_ms.get(event.session_id, 0) + chunk_ms
        self._audio_ms[event.session_id] = audio_ms
        window_bytes = round(event.sample_rate * 2 * 4.0)
        if len(buffer) > window_bytes:
            del buffer[:-window_bytes]
        previous_voice_ms = self._last_voice_ms.get(event.session_id)
        if not active_ms:
            gap_ms = audio_ms - previous_voice_ms if previous_voice_ms is not None else 1200
            if gap_ms >= 1200:
                buffer.clear()
                self._last_text[event.session_id] = ""
                return
            # Flush a short utterance once, after a pause, without decoding
            # every subsequent silent packet or replaying its last words.
            if gap_ms < 350 or self._last_infer_ms.get(event.session_id, -1) >= previous_voice_ms:
                return
        else:
            new_turn = previous_voice_ms is None or audio_ms - chunk_ms - previous_voice_ms >= 1200
            self._last_voice_ms[event.session_id] = audio_ms
            if new_turn:
                buffer[:] = raw_audio[-window_bytes:]
                self._active_segment_id[event.session_id] = f"seg-{next(self._sequence):06d}"
                self._active_start_ms[event.session_id] = max(0, audio_ms - chunk_ms)
                self._last_text[event.session_id] = ""
                self._voice_duration_ms[event.session_id] = 0
                self._last_infer_ms.pop(event.session_id, None)
            self._voice_duration_ms[event.session_id] = self._voice_duration_ms.get(event.session_id, 0) + active_ms
        if self._voice_duration_ms.get(event.session_id, 0) < 160:
            return

        # A larger context window improves names, particles, and sentence
        # boundaries while still emitting revisions roughly once per second.
        min_bytes = round(event.sample_rate * 2 * 0.6)
        if len(buffer) < min_bytes:
            return
        last_infer_ms = self._last_infer_ms.get(event.session_id)
        if active_ms and last_infer_ms is not None and audio_ms - last_infer_ms < 900:
            return
        self._last_infer_ms[event.session_id] = audio_ms
        window = bytes(buffer)
        start_ms = max(0, audio_ms - round(len(window) / 2 / event.sample_rate * 1000))
        context = self._last_text.get(event.session_id, "")
        if hasattr(self.asr, "set_context"):
            self.asr.set_context(context)
        result = await self.asr.transcribe(window, event.sample_rate, start_ms)
        if result is None:
            self.audio_status.update(state="rejected", message="未识别到可靠语音，请检查输入设备或靠近麦克风")
            return
        if self.source_language != "auto" and (result.language != self.source_language or not text_matches_language(result.text, self.source_language)):
            language = {"zh": "中文", "ja": "日语", "en": "英语"}.get(self.source_language, self.source_language)
            self.audio_status.update(state="rejected", message=f"已忽略与锁定{language}不符的识别内容，请检查音频输入；多语混说可选自动识别")
            return
        if result.text == self._last_text.get(event.session_id):
            return
        self._last_text[event.session_id] = result.text
        speaker_id = await self.speaker.identify(window, event.sample_rate, result.start_ms)
        translated_text = result.text if self.translator is None or result.language == self.target_language else ""
        caption = CaptionEvent(
            session_id=event.session_id,
            segment_id=self._active_segment_id[event.session_id],
            speaker_id=speaker_id,
            source_language=result.language,
            target_language=self.target_language,
            original_text=result.text,
            translated_text=translated_text,
            is_final=bool(translated_text),
            start_ms=self._active_start_ms.get(event.session_id, result.start_ms),
            end_ms=result.end_ms,
        )
        # Emit the recognized source text immediately. This keeps the live
        # transcript responsive while a cold Ollama model is loading.
        yield caption
        if not translated_text and self.translator is not None:
            translated_text = await self.translator.translate(result.text, result.language, self.target_language)
            yield caption.model_copy(update={"translated_text": translated_text, "is_final": True})
