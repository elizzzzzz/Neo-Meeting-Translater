import base64
import struct

import pytest

from meeting_interpreter.asr import ASRResult
from meeting_interpreter.models import AudioEvent
from meeting_interpreter.pipeline import Pipeline
from meeting_interpreter.asr import MLXWhisperBackend


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


def test_warmed_decoder_uses_session_language_without_mutating_other_sessions():
    warmed = MLXWhisperBackend("cached-model", language=None)
    warmed._mlx_whisper = object()
    chinese = Pipeline(mode="local", source_language="zh", asr_backend=warmed)
    japanese = Pipeline(mode="local", source_language="ja", asr_backend=warmed)
    assert chinese.asr.language == "zh"
    assert japanese.asr.language == "ja"
    assert warmed.language is None
    assert chinese.asr._mlx_whisper is warmed._mlx_whisper
    chinese.asr.set_context("中文会议")
    assert japanese.asr._context_prompt == ""


@pytest.mark.asyncio
async def test_dc_noise_does_not_invoke_asr():
    pipeline = Pipeline(mode="local", asr_backend=Recognizer())
    for _ in range(20):
        assert [c async for c in pipeline.process_audio(audio([150] * 1600))] == []
    assert not pipeline.asr.windows


@pytest.mark.asyncio
async def test_single_click_surrounded_by_silence_does_not_invoke_asr():
    pipeline = Pipeline(mode="local", asr_backend=Recognizer())
    assert [c async for c in pipeline.process_audio(audio([0] * 9600))] == []
    click = [0] * 1600
    click[800] = 25000
    assert [c async for c in pipeline.process_audio(audio(click))] == []
    assert not pipeline.asr.windows


@pytest.mark.asyncio
async def test_silence_buffer_is_bounded_and_new_turn_excludes_previous_speech():
    recognizer = Recognizer()
    pipeline = Pipeline(mode="local", asr_backend=recognizer)
    _ = [c async for c in pipeline.process_audio(audio([1000, -1000] * 4800))]
    for _ in range(30):
        _ = [c async for c in pipeline.process_audio(audio([0] * 1600))]
    assert len(pipeline._buffers["mic"]) <= 16000 * 2 * 4
    _ = [c async for c in pipeline.process_audio(audio([2000, -2000] * 4800))]
    assert 1000 not in memoryview(recognizer.windows[-1]).cast("h")


@pytest.mark.asyncio
async def test_chinese_lock_rejects_english_hallucination_before_translation():
    class HallucinatingRecognizer:
        async def transcribe(self, pcm, sample_rate, start_ms):
            # Whisper may still report the requested language for wrong-script text.
            return ASRResult("Thanks for watching!", "zh", start_ms, start_ms + 600)

    class MustNotTranslate:
        async def translate(self, *args):
            raise AssertionError("Rejected recognition must never reach translation")

    pipeline = Pipeline(mode="local", source_language="zh", target_language="ja",
                        asr_backend=HallucinatingRecognizer(), translator_backend=MustNotTranslate())
    results = [c async for c in pipeline.process_audio(audio([2000, -2000] * 4800))]
    assert results == []
    assert "中文" in pipeline.audio_status["message"]


def test_websocket_chinese_config_applies_to_warmed_decoder(monkeypatch):
    from fastapi.testclient import TestClient
    from meeting_interpreter.app import create_app

    languages = []

    def recognize(self, pcm, start_ms):
        languages.append(self.language)
        return ASRResult("今天开会。", self.language or "zh", start_ms, start_ms + 600)

    monkeypatch.setenv("MEETING_INTERPRETER_MODE", "local")
    monkeypatch.setenv("MEETING_INTERPRETER_TRANSLATION_BACKEND", "nllb")
    monkeypatch.setattr(MLXWhisperBackend, "_transcribe_sync", recognize)
    with TestClient(create_app()) as client:
        for _ in range(50):
            if client.get("/health").json()["models"]["ready"]:
                break
        else:
            pytest.fail("warmup did not finish")
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"type": "config", "source_language": "zh", "target_language": "zh"})
            configured = ws.receive_json()
            assert configured["asr_language"] == "zh"
            ws.receive_json()
            ws.send_json(audio([2000, -2000] * 4800).model_dump())
            while True:
                result = ws.receive_json()
                if result["type"] == "caption":
                    assert result["original_text"] == "今天开会。"
                    break
    assert languages[0] is None  # model warmup
    assert languages[-1] == "zh"  # actual recording reuses weights with the lock


@pytest.mark.asyncio
async def test_stopping_during_inference_does_not_report_an_asr_failure(monkeypatch):
    import json
    from meeting_interpreter.app import create_app
    from fastapi import WebSocketDisconnect

    monkeypatch.setenv("MEETING_INTERPRETER_MODE", "mock")
    application = create_app()
    endpoint = next(route.endpoint for route in application.routes if getattr(route, "path", "") == "/ws")

    class ClosedSocket:
        def __init__(self): self.closed = False
        async def accept(self): pass
        async def receive_text(self):
            if self.closed: raise WebSocketDisconnect()
            return json.dumps(AudioEvent(session_id="closing", audio_base64=base64.b64encode(b"pcm").decode()).model_dump())
        async def send_json(self, payload):
            if payload["type"] == "caption" or self.closed:
                self.closed = True
                raise RuntimeError('Cannot call "send" once a close message has been sent.')

    await endpoint(ClosedSocket())
