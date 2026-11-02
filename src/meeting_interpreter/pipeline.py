from __future__ import annotations

import asyncio
import base64
import itertools
import math
import time
from collections.abc import AsyncIterator
import os

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


class Pipeline:
    """Streaming pipeline boundary.

    The mock implementation keeps the API testable without downloading model weights.
    Real adapters should replace `process_audio` while preserving CaptionEvent semantics.
    """

    def __init__(self, source_language: str = "auto", target_language: str = "zh", mode: str | None = None, speaker_mode: str | None = None) -> None:
        self.source_language = source_language
        self.target_language = target_language
        self.mode = mode or os.getenv("MEETING_INTERPRETER_MODE", "mock")
        self._sequence = itertools.count(1)
        self._clock_ms = 0
        self._buffers: dict[str, bytearray] = {}
        self._buffer_start_ms: dict[str, int] = {}
        self._last_text: dict[str, str] = {}
        self._mock_last_audio_at: dict[str, float] = {}
        self._mock_phrase_emitted: dict[str, bool] = {}
        if self.mode == "local":
            self.asr: ASRBackend = MLXWhisperBackend(
                model=os.getenv("MEETING_INTERPRETER_ASR_MODEL", "mlx-community/whisper-small-mlx-8bit"),
                language=self.source_language,
            )
            translation_backend = os.getenv("MEETING_INTERPRETER_TRANSLATION_BACKEND", "nllb").lower()
            if translation_backend == "ollama":
                self.translator = OllamaTranslationBackend(
                    model=os.getenv("MEETING_INTERPRETER_OLLAMA_MODEL", "translategemma:4b"),
                    base_url=os.getenv("MEETING_INTERPRETER_OLLAMA_URL", "http://127.0.0.1:11434"),
                    timeout=float(os.getenv("MEETING_INTERPRETER_OLLAMA_TIMEOUT", "180")),
                    keep_alive=os.getenv("MEETING_INTERPRETER_OLLAMA_KEEP_ALIVE", "10m"),
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

        if is_silent_pcm16(raw_audio):
            return

        if self.mode == "local":
            yield_event = await self._process_local(event, raw_audio)
            if yield_event is not None:
                yield yield_event
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

    async def _process_local(self, event: AudioEvent, raw_audio: bytes) -> CaptionEvent | None:
        buffer = self._buffers.setdefault(event.session_id, bytearray())
        buffer.extend(raw_audio)
        start_ms = self._buffer_start_ms.setdefault(event.session_id, 0)
        # Whisper needs a little context. Keep a rolling 3-second window and infer every
        # roughly 0.8 seconds after at least 1.2 seconds of audio has arrived.
        min_bytes = round(event.sample_rate * 2 * 1.2)
        window_bytes = round(event.sample_rate * 2 * 3.0)
        if len(buffer) < min_bytes:
            return None
        window = bytes(buffer[-window_bytes:])
        result = await self.asr.transcribe(window, event.sample_rate, start_ms)
        if result is None or result.text == self._last_text.get(event.session_id):
            return None
        self._last_text[event.session_id] = result.text
        if len(buffer) > window_bytes:
            del buffer[:-round(event.sample_rate * 2 * 1.0)]
            self._buffer_start_ms[event.session_id] = result.end_ms - 1000
        segment = next(self._sequence)
        speaker_id = await self.speaker.identify(window, event.sample_rate, result.start_ms)
        translated_text = (
            await self.translator.translate(result.text, result.language, self.target_language)
            if self.translator is not None
            else ""
        )
        return CaptionEvent(
            session_id=event.session_id,
            segment_id=f"seg-{segment:06d}",
            speaker_id=speaker_id,
            source_language=result.language,
            target_language=self.target_language,
            original_text=result.text,
            translated_text=translated_text,
            is_final=False,
            start_ms=result.start_ms,
            end_ms=result.end_ms,
        )
