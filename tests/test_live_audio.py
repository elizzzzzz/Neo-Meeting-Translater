import base64
import struct

import pytest

from meeting_interpreter.asr import ASRResult
from meeting_interpreter.models import AudioEvent
from meeting_interpreter.pipeline import Pipeline


def audio(samples: list[int]) -> AudioEvent:
    return AudioEvent(session_id="mic", audio_base64=base64.b64encode(struct.pack(f"<{len(samples)}h", *samples)).decode())


class Recognizer:
    def __init__(self):
        self.windows = []

    async def transcribe(self, pcm, sample_rate, start_ms):
        self.windows.append(pcm)
        return ASRResult("这是测试。", "zh", start_ms, start_ms + round(len(pcm) / 32))


class Translator:
    async def translate(self, text, source, target):
        return "これはテストです。"


class RevisingRecognizer:
    def __init__(self):
        self.calls = 0

    async def transcribe(self, pcm, sample_rate, start_ms):
        self.calls += 1
        text = "これは" if self.calls == 1 else "これはテストです。"
        return ASRResult(text, "ja", start_ms, start_ms + round(len(pcm) / 32))


@pytest.mark.asyncio
async def test_quiet_short_utterance_is_flushed_after_silence():
    pipeline = Pipeline(mode="local", target_language="ja")
    pipeline.asr = Recognizer()
    pipeline.translator = Translator()
    results = []
    # -42 dBFS speech, below the old fixed 0.015 gate. 0.6 s voice then 0.6 s pause.
    for event in [audio([250, -250] * 4800), audio([0] * 9600)]:
        results.extend([c async for c in pipeline.process_audio(event)])
    assert pipeline.asr.windows, "quiet speech must reach ASR"
    assert results[0].translated_text == ""
    assert results[0].segment_id == results[-1].segment_id
    assert results[-1].translated_text == "これはテストです。"
    assert results[-1].is_final is True


@pytest.mark.asyncio
async def test_silence_does_not_invoke_asr():
    pipeline = Pipeline(mode="local")
    pipeline.asr = Recognizer()
    for _ in range(30):
        assert [c async for c in pipeline.process_audio(audio([0] * 1600))] == []
    assert pipeline.asr.windows == []


@pytest.mark.asyncio
async def test_continuous_audio_does_not_infer_on_every_packet():
    pipeline = Pipeline(mode="local", target_language="ja")
    pipeline.asr = Recognizer()
    pipeline.translator = Translator()
    for _ in range(50):
        _ = [c async for c in pipeline.process_audio(audio([2000, -2000] * 800))]
    assert 1 <= len(pipeline.asr.windows) <= 7


@pytest.mark.asyncio
async def test_live_caption_is_revised_with_same_segment_id():
    pipeline = Pipeline(mode="local", target_language="zh")
    pipeline.asr = RevisingRecognizer()
    pipeline.translator = Translator()
    results = []
    for _ in range(2):
        results.extend([c async for c in pipeline.process_audio(audio([2000, -2000] * 8000))])
    source_updates = [event for event in results if event.original_text]
    assert len(source_updates) >= 2
    assert source_updates[0].segment_id == source_updates[-1].segment_id
    assert source_updates[-1].original_text == "これはテストです。"
