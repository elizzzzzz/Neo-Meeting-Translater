from __future__ import annotations

import asyncio
import base64
import itertools
from collections.abc import AsyncIterator
import os

from .asr import ASRBackend, MLXWhisperBackend, MockASRBackend
from .models import AudioEvent, CaptionEvent


class Pipeline:
    """Streaming pipeline boundary.

    The mock implementation keeps the API testable without downloading model weights.
    Real adapters should replace `process_audio` while preserving CaptionEvent semantics.
    """

    def __init__(self, source_language: str = "auto", target_language: str = "zh", mode: str | None = None) -> None:
        self.source_language = source_language
        self.target_language = target_language
        self.mode = mode or os.getenv("MEETING_INTERPRETER_MODE", "mock")
        self._sequence = itertools.count(1)
        self._clock_ms = 0
        self._buffers: dict[str, bytearray] = {}
        self._buffer_start_ms: dict[str, int] = {}
        self._last_text: dict[str, str] = {}
        if self.mode == "local":
            self.asr: ASRBackend = MLXWhisperBackend(
                model=os.getenv("MEETING_INTERPRETER_ASR_MODEL", "mlx-community/whisper-small-mlx-8bit"),
                language=self.source_language,
            )
        else:
            self.asr = MockASRBackend()

    async def process_audio(self, event: AudioEvent) -> AsyncIterator[CaptionEvent]:
        # Decode now so malformed input is rejected before real model inference is added.
        try:
            raw_audio = base64.b64decode(event.audio_base64, validate=True)
        except ValueError as exc:
            raise ValueError("audio_base64 is not valid base64") from exc

        if self.mode == "local":
            yield_event = await self._process_local(event, raw_audio)
            if yield_event is not None:
                yield yield_event
            return

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
        return CaptionEvent(
            session_id=event.session_id,
            segment_id=f"seg-{segment:06d}",
            speaker_id="SPEAKER_PENDING",
            source_language=result.language,
            target_language=self.target_language,
            original_text=result.text,
            translated_text="",
            is_final=False,
            start_ms=result.start_ms,
            end_ms=result.end_ms,
        )
