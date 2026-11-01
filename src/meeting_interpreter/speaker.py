from __future__ import annotations

import asyncio
from typing import Protocol


class SpeakerBackend(Protocol):
    async def identify(self, pcm: bytes, sample_rate: int, start_ms: int) -> str:
        """Return an anonymous speaker label for the latest audio window."""


class PendingSpeakerBackend:
    async def identify(self, pcm: bytes, sample_rate: int, start_ms: int) -> str:
        return "SPEAKER_PENDING"


class PyannoteSpeakerBackend:
    """Optional local pyannote Community-1 adapter.

    The pipeline is loaded lazily so ASR-only mode does not pay the memory cost.
    """

    def __init__(self, model_name: str, token: str | None, device: str = "cpu", max_speakers: int = 4) -> None:
        self.model_name = model_name
        self.token = token
        self.device_name = device
        self.max_speakers = max_speakers
        self._pipeline = None
        self._torch = None

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        try:
            import torch
            from pyannote.audio import Pipeline
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("speaker mode requires: pip install -e '.[diarization]'") from exc
        if not self.token and not self.model_name.startswith("/"):
            raise RuntimeError("set HF_TOKEN before downloading the pyannote speaker model")
        self._torch = torch
        self._pipeline = Pipeline.from_pretrained(self.model_name, token=self.token)
        if self.device_name != "cpu" and torch.backends.mps.is_available():
            self._pipeline.to(torch.device(self.device_name))

    async def identify(self, pcm: bytes, sample_rate: int, start_ms: int) -> str:
        if sample_rate != 16_000:
            raise ValueError("pyannote adapter currently expects 16 kHz PCM")
        return await asyncio.to_thread(self._identify_sync, pcm, sample_rate)

    def _identify_sync(self, pcm: bytes, sample_rate: int) -> str:
        import numpy as np

        self._load()
        assert self._pipeline is not None
        assert self._torch is not None
        waveform = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        audio = {"waveform": self._torch.from_numpy(waveform).unsqueeze(0), "sample_rate": sample_rate}
        output = self._pipeline(audio, max_speakers=self.max_speakers)
        annotation = getattr(output, "speaker_diarization", output)
        duration = len(waveform) / sample_rate
        candidates: list[tuple[float, str]] = []
        for segment, _, label in annotation.itertracks(yield_label=True):
            overlap = max(0.0, min(segment.end, duration) - max(segment.start, duration - 0.8))
            if overlap > 0:
                candidates.append((overlap, str(label)))
        if not candidates:
            return "SPEAKER_PENDING"
        return max(candidates, key=lambda item: item[0])[1]
