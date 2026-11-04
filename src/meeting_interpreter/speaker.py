from __future__ import annotations

import asyncio
import math
import os
import threading
from pathlib import Path
from typing import Protocol


class SpeakerBackend(Protocol):
    async def identify(self, pcm: bytes, sample_rate: int, start_ms: int) -> str:
        """Return an anonymous speaker label for the latest audio window."""


class PendingSpeakerBackend:
    async def identify(self, pcm: bytes, sample_rate: int, start_ms: int) -> str:
        return "SPEAKER_PENDING"


def speaker_model_path() -> Path:
    configured = os.getenv("MEETING_INTERPRETER_SPEAKER_EMBEDDING_MODEL")
    return Path(configured).expanduser() if configured else Path.home() / "Library/Application Support/LocalMeetingInterpreter/models/speaker/campplus-zh-cn.onnx"


class SpeakerClusters:
    """Session-local anonymous voice identities, with confirmed changes only."""

    def __init__(self, threshold: float = .60, max_speakers: int = 8) -> None:
        self.threshold = threshold
        self.max_speakers = max_speakers
        self.centroids: list[list[float]] = []
        self.active = -1
        self.candidate: list[float] | None = None
        self.candidate_id = -1
        self.candidate_at_ms = 0
        self.changed_at_ms = 0

    def assign(self, embedding: list[float], at_ms: int) -> str:
        norm = math.sqrt(sum(x*x for x in embedding))
        if not norm or not math.isfinite(norm):
            return self.label
        vector = [x / norm for x in embedding]
        if not self.centroids:
            self.centroids.append(vector)
            self.active = 0
            return self.label
        scores = [sum(a*b for a,b in zip(vector, centroid)) for centroid in self.centroids]
        best = max(range(len(scores)), key=scores.__getitem__)
        proposed = best if scores[best] >= self.threshold else -1
        if proposed == self.active:
            self.candidate = None
            # Update only high-confidence observations, not mixed transitions.
            if scores[best] >= .75:
                averaged = [.9*a + .1*b for a,b in zip(self.centroids[best], vector)]
                length = math.sqrt(sum(x*x for x in averaged))
                self.centroids[best] = [x/length for x in averaged]
            return self.label
        same_candidate = self.candidate is not None and self.candidate_id == proposed and sum(a*b for a,b in zip(vector, self.candidate)) >= .70
        if not same_candidate:
            self.candidate, self.candidate_id, self.candidate_at_ms = vector, proposed, at_ms
            return self.label
        if at_ms - self.candidate_at_ms < 600:
            return self.label
        if proposed < 0:
            if len(self.centroids) >= self.max_speakers:
                return self.label
            self.centroids.append(vector)
            proposed = len(self.centroids) - 1
        self.active = proposed
        self.changed_at_ms = self.candidate_at_ms
        self.candidate = None
        return self.label

    @property
    def label(self) -> str:
        return f"SPEAKER_{self.active:02d}" if self.active >= 0 else "SPEAKER_PENDING"


class EmbeddingSpeakerBackend:
    """Small CPU-only local voice embedding model; never downloads at runtime."""

    _lock = threading.Lock()

    def __init__(self, model: str | None = None) -> None:
        self.model = Path(model) if model else speaker_model_path()
        self._extractor = None
        self.clusters = SpeakerClusters()

    @property
    def changed_at_ms(self) -> int:
        return self.clusters.changed_at_ms

    def for_session(self) -> EmbeddingSpeakerBackend:
        backend = EmbeddingSpeakerBackend(str(self.model))
        backend._extractor = self._extractor
        return backend

    def load(self) -> None:
        if self._extractor is not None:
            return
        if not self.model.is_file():
            raise RuntimeError("未连接本地声纹模型，请先使用手动换人，或配置声纹模型文件。")
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise RuntimeError("当前运行环境缺少本地声纹组件，请使用新版 App 或安装 speaker 依赖。") from exc
        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(self.model), num_threads=2, provider="cpu")
        if not config.validate():
            raise RuntimeError("本地声纹模型格式无效。")
        self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)

    async def identify(self, pcm: bytes, sample_rate: int, start_ms: int) -> str:
        if len(pcm) < sample_rate * 2 * .8:
            return self.clusters.label
        return await asyncio.to_thread(self._identify_sync, pcm, sample_rate, start_ms)

    def _identify_sync(self, pcm: bytes, sample_rate: int, start_ms: int) -> str:
        import numpy as np
        with self._lock:
            self.load()
            stream = self._extractor.create_stream()
            stream.accept_waveform(sample_rate=sample_rate, waveform=np.frombuffer(pcm, dtype=np.int16).astype(np.float32)/32768)
            stream.input_finished()
            if not self._extractor.is_ready(stream):
                return self.clusters.label
            embedding = self._extractor.compute(stream)
        return self.clusters.assign(list(embedding), start_ms)


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
