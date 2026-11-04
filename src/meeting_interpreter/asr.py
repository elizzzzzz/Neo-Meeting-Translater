from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ASRResult:
    text: str
    language: str
    start_ms: int
    end_ms: int


class ASRBackend(Protocol):
    async def transcribe(self, pcm: bytes, sample_rate: int, start_ms: int) -> ASRResult | None:
        """Transcribe a mono PCM16 window without blocking the event loop."""


class MockASRBackend:
    async def transcribe(self, pcm: bytes, sample_rate: int, start_ms: int) -> ASRResult:
        await asyncio.sleep(0.01)
        duration_ms = max(1, round(len(pcm) / 2 / sample_rate * 1000))
        return ASRResult(
            text="这是本地模型的实时语音识别演示。",
            language="zh",
            start_ms=start_ms,
            end_ms=start_ms + duration_ms,
        )


class MLXWhisperBackend:
    """Lazy MLX Whisper adapter for Apple Silicon.

    The optional dependency and model weights are loaded only when local mode is used.
    This keeps the 16G unified-memory machine usable in mock mode and avoids importing
    MLX in environments without Apple Silicon.
    """

    # MLX Whisper caches a single model globally; serialize inference across
    # sessions while keeping each session's language and prompt independent.
    _inference_lock = threading.Lock()

    def __init__(self, model: str, language: str | None = None) -> None:
        self.model = model
        self.language = None if language in (None, "", "auto") else language
        self._mlx_whisper = None
        self._context_prompt = ""

    def for_language(self, language: str) -> MLXWhisperBackend:
        """Reuse warm weights, with fresh decoding settings for this session."""
        backend = MLXWhisperBackend(self.model, language)
        backend._mlx_whisper = self._mlx_whisper
        return backend

    def set_context(self, text: str) -> None:
        """Provide the latest committed text as a decoding hint."""
        self._context_prompt = text[-240:].strip()

    def _load(self):
        if self._mlx_whisper is None:
            try:
                import mlx_whisper
            except ImportError as exc:  # pragma: no cover - depends on optional Apple package
                raise RuntimeError("local mode requires: pip install -e '.[apple]'") from exc
            self._mlx_whisper = mlx_whisper
        return self._mlx_whisper

    async def transcribe(self, pcm: bytes, sample_rate: int, start_ms: int) -> ASRResult | None:
        if sample_rate != 16_000:
            raise ValueError("MLX Whisper adapter currently expects 16 kHz PCM")
        if not pcm:
            return None
        return await asyncio.to_thread(self._transcribe_locked, pcm, start_ms)

    def _transcribe_locked(self, pcm: bytes, start_ms: int) -> ASRResult | None:
        with self._inference_lock:
            return self._transcribe_sync(pcm, start_ms)

    def _transcribe_sync(self, pcm: bytes, start_ms: int) -> ASRResult | None:
        import numpy as np

        whisper = self._load()
        waveform = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        result = whisper.transcribe(
            waveform,
            path_or_hf_repo=self.model,
            language=self.language,
            task="transcribe",
            word_timestamps=False,
            condition_on_previous_text=False,
            initial_prompt=self._context_prompt or None,
            temperature=0.0,
            verbose=False,
        )
        # Whisper can confidently decode stock phrases on noise. Its default
        # skip rule can retain high-no-speech segments when logprob is high;
        # require both speech probability and decoding confidence here.
        segments = result.get("segments", [])
        text = "".join(
            segment.get("text", "") for segment in segments
            if segment.get("no_speech_prob", 0) < 0.6
            and segment.get("avg_logprob", 0) >= -1.0
            and segment.get("compression_ratio", 0) <= 2.4
        ).strip()
        if not text:
            return None
        duration_ms = round(len(waveform) / 16_000 * 1000)
        return ASRResult(
            text=text,
            language=result.get("language") or self.language or "auto",
            start_ms=start_ms,
            end_ms=start_ms + duration_ms,
        )
