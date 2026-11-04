import struct

import pytest

from meeting_interpreter.asr import MLXWhisperBackend


class Decoder:
    def __init__(self, segments):
        self.segments = segments
        self.options = None

    def transcribe(self, waveform, **options):
        self.options = options
        return {"text": "".join(s["text"] for s in self.segments), "language": "zh", "segments": self.segments}


@pytest.mark.asyncio
async def test_low_confidence_and_no_speech_segments_are_not_displayed():
    decoder = Decoder([
        {"text": "谢谢观看", "no_speech_prob": .95, "avg_logprob": -.1, "compression_ratio": 1},
        {"text": "编造内容", "no_speech_prob": .05, "avg_logprob": -1.5, "compression_ratio": 1},
        {"text": "重复重复", "no_speech_prob": .05, "avg_logprob": -.1, "compression_ratio": 3},
    ])
    backend = MLXWhisperBackend("cached-model", "zh")
    backend._mlx_whisper = decoder
    assert await backend.transcribe(struct.pack("<h", 1000) * 9600, 16000, 0) is None


@pytest.mark.asyncio
async def test_valid_chinese_keeps_mixed_english_names_and_excludes_bad_segments():
    decoder = Decoder([
        {"text": "今天用 Teams 开会。", "no_speech_prob": .03, "avg_logprob": -.2, "compression_ratio": 1.2},
        {"text": "Thanks for watching!", "no_speech_prob": .9, "avg_logprob": -.3, "compression_ratio": 1},
    ])
    backend = MLXWhisperBackend("cached-model", "zh")
    backend._mlx_whisper = decoder
    result = await backend.transcribe(struct.pack("<h", 1000) * 9600, 16000, 0)
    assert result.text == "今天用 Teams 开会。"
    assert decoder.options["language"] == "zh"
