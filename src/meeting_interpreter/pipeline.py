from __future__ import annotations

import asyncio
import base64
import itertools
from collections.abc import AsyncIterator

from .models import AudioEvent, CaptionEvent


class Pipeline:
    """Streaming pipeline boundary.

    The mock implementation keeps the API testable without downloading model weights.
    Real adapters should replace `process_audio` while preserving CaptionEvent semantics.
    """

    def __init__(self, source_language: str = "auto", target_language: str = "zh") -> None:
        self.source_language = source_language
        self.target_language = target_language
        self._sequence = itertools.count(1)
        self._clock_ms = 0

    async def process_audio(self, event: AudioEvent) -> AsyncIterator[CaptionEvent]:
        # Decode now so malformed input is rejected before real model inference is added.
        try:
            base64.b64decode(event.audio_base64, validate=True)
        except ValueError as exc:
            raise ValueError("audio_base64 is not valid base64") from exc

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
