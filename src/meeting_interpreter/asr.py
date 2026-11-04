from __future__ import annotations

import asyncio
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ASRWord:
    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class ASRResult:
    text: str
    language: str
    start_ms: int
    end_ms: int
    words: tuple[ASRWord, ...] = ()


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


def sensevoice_model_directory() -> Path:
    explicit = os.getenv('MEETING_INTERPRETER_SENSEVOICE_MODEL')
    root = Path(os.getenv('MEETING_INTERPRETER_MODEL_DIR', str(Path.home() / 'Library/Application Support/LocalMeetingInterpreter/models'))).expanduser()
    return Path(explicit).expanduser() if explicit else root / 'asr/sensevoice'


def create_asr_backend(language: str | None = None) -> ASRBackend:
    engine = os.getenv('MEETING_INTERPRETER_ASR_BACKEND', 'whisper')
    if engine == 'sensevoice':
        return SenseVoiceBackend(str(sensevoice_model_directory()), language)
    if engine != 'whisper':
        raise ValueError(f'未知的语音识别引擎：{engine}')
    return MLXWhisperBackend(os.getenv('MEETING_INTERPRETER_ASR_MODEL', 'mlx-community/whisper-medium-mlx-8bit'), language)


class LocalSpeechDetector:
    """Small local speech gate, separate from the recognizer's text scores."""

    def __init__(self, model: Path) -> None:
        self.model = model
        self._vad = None

    def __call__(self, waveform) -> bool:
        import numpy as np
        if self._vad is None:
            import sherpa_onnx
            if not self.model.is_file():
                raise RuntimeError(f'未连接语音活动检测模型：{self.model}。SenseVoice 需要它过滤噪声字幕。')
            config = sherpa_onnx.VadModelConfig()
            config.silero_vad.model = str(self.model)
            config.silero_vad.min_speech_duration = .15
            config.silero_vad.min_silence_duration = .2
            config.sample_rate = 16000
            config.num_threads = 1
            self._vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=60)
        # Far-field meetings can be clearly intelligible at -40dBFS while
        # Silero rejects the unscaled signal. Normalize only its detector input;
        # keep the decoder's audio and the original silence/noise gates intact.
        level = float(np.std(waveform)) if len(waveform) else 0.0
        if .003 <= level < .04:
            peak = float(np.max(np.abs(waveform)))
            gain = min(4.0, .04 / level, .95 / max(peak, 1e-6))
            if gain > 1:
                waveform = waveform * gain
        self._vad.reset()
        self._vad.accept_waveform(np.concatenate((waveform, np.zeros(8000, dtype=np.float32))))
        self._vad.flush()
        return not self._vad.empty()


class SenseVoiceBackend:
    """Local CPU recognizer with CTC token onsets; weights never download here."""

    _inference_lock = threading.Lock()
    supports_timestamps = True

    def __init__(self, model: str, language: str | None = None) -> None:
        self.model = model
        self.language = None if language in (None, '', 'auto') else language
        self._recognizer = None
        self._recognizers: dict[str, object] = {}
        self._speech_detector = LocalSpeechDetector(Path(model) / 'silero_vad.onnx')

    def for_language(self, language: str) -> SenseVoiceBackend:
        backend = SenseVoiceBackend(self.model, language)
        backend._recognizers = self._recognizers
        # All detector access is under _inference_lock and each call resets it.
        # Reuse the startup-warmed detector instead of loading ONNX per session.
        backend._speech_detector = self._speech_detector
        return backend

    def _load(self):
        if self._recognizer is not None:
            return self._recognizer
        key = self.language or 'auto'
        if key not in self._recognizers:
            folder = Path(self.model)
            if not (folder / 'model.int8.onnx').is_file() or not (folder / 'tokens.txt').is_file():
                raise RuntimeError(f'未连接 SenseVoice 语音识别模型：{folder}。需要 model.int8.onnx 和 tokens.txt，可在本地设置切回 Whisper。')
            import sherpa_onnx
            self._recognizers[key] = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(folder / 'model.int8.onnx'), tokens=str(folder / 'tokens.txt'),
                language=key, use_itn=True, num_threads=2, provider='cpu')
        self._recognizer = self._recognizers[key]
        return self._recognizer

    def _has_speech(self, waveform) -> bool:
        return self._speech_detector(waveform)

    def warmup(self) -> None:
        import numpy as np
        with self._inference_lock:
            self._load()
            self._has_speech(np.zeros(16000, dtype=np.float32))

    async def transcribe(self, pcm: bytes, sample_rate: int, start_ms: int) -> ASRResult | None:
        if sample_rate != 16000:
            raise ValueError('SenseVoice 需要 16 kHz 单声道音频')
        if not pcm:
            return None
        return await asyncio.to_thread(self._transcribe_sync, pcm, start_ms)

    def _transcribe_sync(self, pcm: bytes, start_ms: int) -> ASRResult | None:
        import numpy as np
        waveform = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
        # CTC can also produce a short word on zero input. Never ask it to
        # decode silence; the streaming pipeline applies an additional gate.
        if float(waveform.std()) < .003:
            return None
        with self._inference_lock:
            if not self._has_speech(waveform):
                return None
            recognizer = self._load()
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, waveform)
            recognizer.decode_stream(stream)
            result = stream.result
            text = result.text.strip()
            if not text or (result.event and result.event != '<|Speech|>'):
                return None
            duration = round(len(waveform) / 16000 * 1000)
            tokens = [token.replace('▁', ' ') for token in result.tokens]
            times = list(result.timestamps)
            words: tuple[ASRWord, ...] = ()
            # ITN may rewrite numbers without matching the token sequence.
            # Use times only when they actually describe the displayed text.
            if len(tokens) == len(times) and ''.join(tokens).strip() == text:
                words = tuple(ASRWord(token, start_ms + round(at * 1000),
                                      start_ms + min(duration, round(times[i+1] * 1000) if i+1 < len(times) else duration))
                              for i, (token, at) in enumerate(zip(tokens, times)))
            return ASRResult(text, re.sub(r'<\||\|>', '', result.lang) or self.language or 'auto',
                             start_ms, start_ms + duration, words)


class MLXWhisperBackend:
    """Lazy MLX Whisper adapter for Apple Silicon.

    The optional dependency and model weights are loaded only when local mode is used.
    This keeps the 16G unified-memory machine usable in mock mode and avoids importing
    MLX in environments without Apple Silicon.
    """

    # MLX Whisper caches a single model globally; serialize inference across
    # sessions while keeping each session's language and prompt independent.
    _inference_lock = threading.Lock()
    supports_timestamps = True

    def __init__(self, model: str, language: str | None = None) -> None:
        self.model = model
        self.language = None if language in (None, "", "auto") else language
        self._mlx_whisper = None
        self._context_prompt = ""
        vad_path = sensevoice_model_directory() / 'silero_vad.onnx'
        self._speech_detector = LocalSpeechDetector(vad_path) if vad_path.is_file() else None

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
            word_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=self._context_prompt or None,
            temperature=0.0,
            verbose=False,
        )
        # Whisper can confidently decode stock phrases on noise. Its default
        # skip rule can retain high-no-speech segments when logprob is high;
        # require both speech probability and decoding confidence here.
        segments = result.get("segments", [])
        speech_confirmed = self._speech_detector(waveform) if self._speech_detector is not None else False
        if self._speech_detector is not None and not speech_confirmed:
            return None
        reliable_segments = [segment for segment in segments
            if (speech_confirmed or segment.get("no_speech_prob", 0) < 0.6)
            and segment.get("avg_logprob", 0) >= -1.0
            and segment.get("compression_ratio", 0) <= 2.4
        ]
        text = "".join(segment.get("text", "") for segment in reliable_segments).strip()
        if not text:
            return None
        duration_ms = round(len(waveform) / 16_000 * 1000)
        return ASRResult(
            text=text,
            language=result.get("language") or self.language or "auto",
            start_ms=start_ms,
            end_ms=start_ms + duration_ms,
            words=tuple(ASRWord(word["word"], start_ms + round(word["start"] * 1000), start_ms + round(word["end"] * 1000))
                        for segment in reliable_segments for word in segment.get("words", [])),
        )
