from __future__ import annotations

import asyncio
import base64
import itertools
import math
import time
from collections.abc import AsyncIterator
import os
import re
from dataclasses import replace

from .asr import ASRBackend, MLXWhisperBackend, SenseVoiceBackend, MockASRBackend, create_asr_backend
from .models import AudioEvent, CaptionEvent
from .speaker import EmbeddingSpeakerBackend, PendingSpeakerBackend, PyannoteSpeakerBackend, SpeakerBackend
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


def normalize_language(language: str | None) -> str:
    """Normalize decoder language labels used by SenseVoice/Whisper."""
    value = (language or "auto").strip().lower().replace("_", "-")
    if value.startswith("zh") or value in {"cmn", "zho", "chinese"}:
        return "zh"
    if value.startswith("ja") or value in {"jpn", "japanese"}:
        return "ja"
    if value.startswith("en") or value in {"eng", "english"}:
        return "en"
    return value or "auto"


class Pipeline:
    """Streaming pipeline boundary.

    The mock implementation keeps the API testable without downloading model weights.
    Real adapters should replace `process_audio` while preserving CaptionEvent semantics.
    """

    def __init__(self, source_language: str = "auto", target_language: str = "zh", mode: str | None = None, speaker_mode: str | None = None, asr_backend: ASRBackend | None = None, translator_backend: TranslationBackend | None = None, speaker_backend: EmbeddingSpeakerBackend | None = None, translate_inline: bool = True, language_pair: str | None = None) -> None:
        self.translate_inline = translate_inline
        self.source_language = source_language
        self.target_language = target_language
        if language_pair not in (None, "zh-ja", "zh-en", "en-ja"):
            raise ValueError("请选择中日、中英或英日会议语言。")
        self.language_pair = language_pair if source_language == "auto" else None
        self.mode = mode or os.getenv("MEETING_INTERPRETER_MODE", "mock")
        self._sequence = itertools.count(1)
        self._clock_ms = 0
        self._buffers: dict[str, bytearray] = {}
        self._audio_ms: dict[str, int] = {}
        self._audio_samples: dict[str, int] = {}
        self._buffer_start_ms: dict[str, int] = {}
        self._committed_until_ms: dict[str, int] = {}
        self._decoded_boundary_ms: dict[str, int] = {}
        self._decoded_has_timestamps: dict[str, bool] = {}
        self._speaker_ids: dict[str, str] = {}
        self._last_speaker_probe_ms: dict[str, int] = {}
        self._last_events: dict[str, AudioEvent] = {}
        self._latest_caption: dict[str, CaptionEvent] = {}
        self._manual_speaker_number = 1
        self._manual_label = "SPEAKER_PENDING"
        self._last_infer_ms: dict[str, int] = {}
        self._last_text: dict[str, str] = {}
        self._context_text: dict[str, str] = {}
        self._paragraph_text: dict[str, str] = {}
        self._last_voice_ms: dict[str, int] = {}
        self._voice_duration_ms: dict[str, float] = {}
        self.audio_status: dict[str, object] = {"state": "silent", "rms": 0.0, "peak": 0.0, "message": "等待声音输入"}
        self._active_segment_id: dict[str, str] = {}
        self._active_start_ms: dict[str, int] = {}
        self._mock_last_audio_at: dict[str, float] = {}
        self._mock_phrase_emitted: dict[str, bool] = {}
        self.context_correction_enabled = os.getenv("MEETING_INTERPRETER_CONTEXT_CORRECTION", "1").lower() not in {"0", "false", "no"}
        if self.mode == "local":
            self.asr: ASRBackend = (asr_backend.for_language(source_language) if isinstance(asr_backend, (MLXWhisperBackend, SenseVoiceBackend)) else asr_backend) or create_asr_backend(source_language)
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
            selected_speaker_mode = speaker_mode or os.getenv("MEETING_INTERPRETER_SPEAKER_MODE", "none")
            if selected_speaker_mode == "embedding":
                self.speaker: SpeakerBackend = speaker_backend.for_session() if speaker_backend else EmbeddingSpeakerBackend()
            elif selected_speaker_mode == "pyannote":
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

    async def process_audio(self, event: AudioEvent, defer_partial: bool = False) -> AsyncIterator[CaptionEvent]:
        # Decode now so malformed input is rejected before real model inference is added.
        try:
            raw_audio = base64.b64decode(event.audio_base64, validate=True)
        except ValueError as exc:
            raise ValueError("audio_base64 is not valid base64") from exc

        if self.mode == "local":
            async for yield_event in self._process_local(event, raw_audio, defer_partial):
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

    async def _process_local(self, event: AudioEvent, raw_audio: bytes, defer_partial: bool = False) -> AsyncIterator[CaptionEvent]:
        if event.channels != 1:
            raise ValueError("语音识别需要单声道音频")
        rms, peak, active_ms = pcm16_activity(raw_audio, event.sample_rate)
        self.audio_status = {"state": "sound" if active_ms else "silent", "rms": round(rms, 5), "peak": round(peak, 5),
                             "message": "收到声音，正在识别" if active_ms else "静音或音量较低，等待讲话"}
        session = event.session_id
        self._last_events[session] = event
        buffer = self._buffers.setdefault(session, bytearray())
        previous_audio_ms = self._audio_ms.get(session, 0)
        self._audio_samples[session] = self._audio_samples.get(session, 0) + len(raw_audio) // 2
        audio_ms = round(self._audio_samples[session] / event.sample_rate * 1000)
        self._audio_ms[session] = audio_ms
        previous_voice_ms = self._last_voice_ms.get(session)
        new_turn = active_ms and (previous_voice_ms is None or previous_audio_ms - previous_voice_ms >= 1200)
        if new_turn:
            if self._last_text.get(session):
                self._context_text[session] = self._last_text[session][-240:]
            buffer.clear()
            self._buffer_start_ms[session] = previous_audio_ms
            self._committed_until_ms[session] = previous_audio_ms
            self._active_segment_id[session] = f"seg-{next(self._sequence):06d}"
            self._active_start_ms[session] = previous_audio_ms
            self._last_text[session] = ""
            self._voice_duration_ms[session] = 0
            self._last_infer_ms.pop(session, None)
            self._speaker_ids.setdefault(session, self._manual_label)
        buffer.extend(raw_audio)
        if active_ms:
            self._last_voice_ms[session] = audio_ms
            self._voice_duration_ms[session] = self._voice_duration_ms.get(session, 0) + active_ms
        else:
            gap_ms = audio_ms - previous_voice_ms if previous_voice_ms is not None else 1200
            if previous_voice_ms is None:
                buffer.clear()
                return
            if gap_ms < 350:
                return
            if self._last_infer_ms.get(session, -1) >= previous_voice_ms:
                if gap_ms >= 1200:
                    buffer.clear()
                return

        if active_ms and not isinstance(self.speaker, PendingSpeakerBackend) and audio_ms - self._last_speaker_probe_ms.get(session, -1000) >= 900:
            probe_bytes = min(len(buffer), event.sample_rate * 2 * 2)
            probe_start = self._buffer_start_ms.get(session, 0) + round((len(buffer) - probe_bytes) / 2 / event.sample_rate * 1000)
            identity = await self.speaker.identify(bytes(buffer[-probe_bytes:]), event.sample_rate, probe_start)
            self._last_speaker_probe_ms[session] = audio_ms
            previous_identity = self._speaker_ids.get(session, "SPEAKER_PENDING")
            if identity != "SPEAKER_PENDING" and identity != previous_identity:
                if previous_identity != "SPEAKER_PENDING":
                    split_ms = max(self._buffer_start_ms[session], min(audio_ms, getattr(self.speaker, "changed_at_ms", probe_start)))
                    split_bytes = round((split_ms - self._buffer_start_ms[session]) * event.sample_rate * 2 / 1000)
                    new_caption_needed = split_ms > self._active_start_ms.get(session, 0)
                    if split_bytes and new_caption_needed:
                        async for caption in self._decode_window(event, bytes(buffer[:split_bytes]), self._buffer_start_ms[session]):
                            yield caption
                    del buffer[:split_bytes]
                    self._buffer_start_ms[session] = split_ms
                    self._committed_until_ms[session] = split_ms
                    if new_caption_needed:
                        self._active_segment_id[session] = f"seg-{next(self._sequence):06d}"
                    self._active_start_ms[session] = split_ms
                self._speaker_ids[session] = identity
                self._last_text[session] = ""
                self._last_infer_ms.pop(session, None)

        # A chunk has its own identity. Once committed, its words remain in the
        # transcript while only the next chunk can be revised. Never discard
        # old audio from a rolling window and overwrite the same caption id.
        window_bytes = event.sample_rate * 2 * 8
        while len(buffer) >= window_bytes and self._voice_duration_ms.get(session, 0) >= 160:
            start_ms = self._buffer_start_ms[session]
            self._decoded_boundary_ms[session] = start_ms + 8000
            async for caption in self._decode_window(event, bytes(buffer[:window_bytes]), start_ms, commit_before_ms=start_ms + 7500):
                yield caption
            if self._last_text.get(session):
                self._context_text[session] = self._last_text[session][-240:]
            end_ms = self._decoded_boundary_ms[session]
            overlap_bytes = event.sample_rate * 2 if self._decoded_has_timestamps.get(session, False) else 0
            consumed_bytes = round((end_ms - start_ms) * event.sample_rate * 2 / 1000)
            del buffer[:consumed_bytes - overlap_bytes]
            self._buffer_start_ms[session] = end_ms - round(overlap_bytes / 2 / event.sample_rate * 1000)
            self._committed_until_ms[session] = end_ms
            self._active_segment_id[session] = f"seg-{next(self._sequence):06d}"
            self._active_start_ms[session] = end_ms
            self._last_text[session] = ""
            self._last_infer_ms[session] = end_ms
        if self._voice_duration_ms.get(session, 0) < 160 or len(buffer) < round(event.sample_rate * 2 * .6):
            return
        if defer_partial and active_ms:
            return
        last_infer_ms = self._last_infer_ms.get(session)
        if active_ms and last_infer_ms is not None and audio_ms - last_infer_ms < 600:
            return
        self._last_infer_ms[session] = audio_ms
        async for caption in self._decode_window(event, bytes(buffer), self._buffer_start_ms.get(session, previous_audio_ms)):
            yield caption
        if not active_ms and audio_ms - (previous_voice_ms or 0) >= 1200:
            buffer.clear()

    async def _decode_window(self, event: AudioEvent, window: bytes, start_ms: int, commit_before_ms: int | None = None) -> AsyncIterator[CaptionEvent]:
        context = self._context_text.get(event.session_id, "")
        if hasattr(self.asr, "set_context"):
            self.asr.set_context(context)
        result = await self.asr.transcribe(window, event.sample_rate, start_ms)
        self._decoded_has_timestamps[event.session_id] = bool(result and result.words)
        if result is None:
            self.audio_status.update(state="rejected", message="未识别到可靠语音，请检查输入设备或靠近麦克风")
            return
        result_language = normalize_language(result.language)
        target_language = self.target_language
        if self.language_pair:
            pair = self.language_pair.split("-")
            if result_language not in pair:
                self.audio_status.update(state="rejected", message="识别语言不属于所选会议语言，请检查音频输入或会议语言设置")
                return
            target_language = pair[1] if result_language == pair[0] else pair[0]
        if self.source_language != "auto" and (result_language != self.source_language or not text_matches_language(result.text, self.source_language)):
            language = {"zh": "中文", "ja": "日语", "en": "英语"}.get(self.source_language, self.source_language)
            self.audio_status.update(state="rejected", message=f"已忽略与锁定{language}不符的识别内容，请检查音频输入；多语混说可选自动识别")
            return
        cutoff = self._committed_until_ms.get(event.session_id, 0)
        if result.words and (start_ms < cutoff or commit_before_ms is not None):
            words = [word for word in result.words if (word.start_ms + word.end_ms) / 2 >= cutoff
                     and (commit_before_ms is None or word.end_ms <= commit_before_ms)]
            text = "".join(word.text for word in words).strip()
            if not text:
                return
            result = replace(result, text=text)
            if commit_before_ms is not None and words[-1].end_ms - start_ms >= 1200:
                # Commit at a completed word, leaving the final half-second
                # revisable so words cut by the audio boundary aren't doubled.
                boundary = words[-1].end_ms
                self._decoded_boundary_ms[event.session_id] = boundary
                result = replace(result, end_ms=boundary)
        if result.language in {"zh", "ja"}:
            # CTC subword boundaries are not spaces in Chinese/Japanese prose.
            # Clean display/translation after applying word timestamps.
            result = replace(result, text=re.sub(r"(?<=[0-9\u3040-\u30ff\u3400-\u9fff])\s+(?=[0-9\u3040-\u30ff\u3400-\u9fff])", "", result.text))
        result = replace(result, language=result_language)
        stable = commit_before_ms is not None
        correct_source = getattr(self.translator, "correct_source", None)
        if stable and self.context_correction_enabled and correct_source is not None and result.text:
            try:
                corrected = await correct_source(
                    result.text,
                    self._paragraph_text.get(event.session_id, self._context_text.get(event.session_id, "")),
                    result.language,
                )
                if corrected:
                    result = replace(result, text=corrected)
            except Exception:
                # Recognition and translation remain usable when the optional
                # semantic correction request is unavailable or times out.
                pass
        speaker_id = self._speaker_ids.get(event.session_id, "SPEAKER_PENDING")
        if result.text == self._last_text.get(event.session_id):
            previous = self._latest_caption.get(event.session_id)
            if (previous and previous.segment_id == self._active_segment_id[event.session_id]
                    and previous.speaker_id == speaker_id and previous.source_language == result.language
                    and previous.target_language == target_language):
                updated = previous.model_copy(update={"end_ms": result.end_ms})
                self._latest_caption[event.session_id] = updated
                yield updated
                return
        self._last_text[event.session_id] = result.text
        self._paragraph_text[event.session_id] = (self._paragraph_text.get(event.session_id, "") + " " + result.text).strip()[-600:]
        translated_text = result.text if self.translator is None or result.language == target_language else ""
        caption = CaptionEvent(
            session_id=event.session_id,
            segment_id=self._active_segment_id[event.session_id],
            speaker_id=speaker_id,
            source_language=result.language,
            target_language=target_language,
            language_pair=self.language_pair,
            original_text=result.text,
            translated_text=translated_text,
            is_final=bool(translated_text),
            start_ms=self._active_start_ms.get(event.session_id, result.start_ms),
            end_ms=result.end_ms,
        )
        # Emit the recognized source text immediately. This keeps the live
        # transcript responsive while a cold Ollama model is loading.
        self._latest_caption[event.session_id] = caption
        yield caption
        if self.translate_inline and not translated_text and self.translator is not None:
            translated_text = await self.translator.translate(result.text, result.language, target_language)
            caption = caption.model_copy(update={"translated_text": translated_text, "is_final": True})
            self._latest_caption[event.session_id] = caption
            yield caption

    async def flush_audio(self) -> AsyncIterator[CaptionEvent]:
        """Finish short trailing audio on stop, without waiting for another packet."""
        for session, event in self._last_events.items():
            buffer = self._buffers.get(session, bytearray())
            if buffer and self._voice_duration_ms.get(session, 0) >= 160:
                async for caption in self._decode_window(event, bytes(buffer), self._buffer_start_ms.get(session, 0)):
                    yield caption

    async def change_speaker(self) -> AsyncIterator[CaptionEvent]:
        """Manual boundary: finish the current audio, then start a fresh paragraph."""
        async for caption in self.flush_audio():
            yield caption
        self._manual_speaker_number += 1
        for session in self._last_events:
            buffer = self._buffers.get(session, bytearray())
            buffer.clear()
            self._last_voice_ms.pop(session, None)
            self._speaker_ids[session] = f"MANUAL_{self._manual_speaker_number}"
        self._manual_label = f"MANUAL_{self._manual_speaker_number}"
        self.speaker = PendingSpeakerBackend()
