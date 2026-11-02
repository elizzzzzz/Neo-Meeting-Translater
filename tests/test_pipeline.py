import base64
import json

import pytest

from meeting_interpreter.models import AudioEvent
from meeting_interpreter.pipeline import Pipeline, is_silent_pcm16
from meeting_interpreter.translation import NLLBTranslationBackend, OllamaTranslationBackend, nllb_language_code
from meeting_interpreter.speaker import PendingSpeakerBackend


def test_nllb_language_codes() -> None:
    assert nllb_language_code("zh") == "zho_Hans"
    assert nllb_language_code("ja") == "jpn_Jpan"
    assert nllb_language_code("en") == "eng_Latn"
    assert nllb_language_code("ko") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("source, target", [("zh", "ja"), ("ja", "zh"), ("zh", "en"), ("en", "zh")])
async def test_nllb_translation_pairs_are_supported(monkeypatch: pytest.MonkeyPatch, source: str, target: str) -> None:
    backend = NLLBTranslationBackend("test-model")

    def fake_translate(text: str, source_code: str, target_code: str) -> str:
        return f"{source_code}>{target_code}:{text}"

    monkeypatch.setattr(backend, "_translate_sync", fake_translate)
    result = await backend.translate("hello", source, target)
    assert result == f"{nllb_language_code(source)}>{nllb_language_code(target)}:hello"


@pytest.mark.asyncio
async def test_ollama_translation_uses_local_generate_api(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = OllamaTranslationBackend(model="translategemma:4b")
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return '{"response":"これはテストです。"}'.encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = await backend.translate("这是测试。", "zh", "ja")
    assert result == "これはテストです。"
    assert captured["url"] == "http://127.0.0.1:11434/api/generate"
    assert captured["body"]["model"] == "translategemma:4b"
    assert "Simplified Chinese" in captured["body"]["prompt"]
    assert "Japanese" in captured["body"]["prompt"]


@pytest.mark.asyncio
async def test_pending_speaker_backend_is_safe_default() -> None:
    assert await PendingSpeakerBackend().identify(b"pcm", 16_000, 0) == "SPEAKER_PENDING"


@pytest.mark.asyncio
async def test_mock_pipeline_emits_caption() -> None:
    event = AudioEvent(session_id="test", audio_base64=base64.b64encode(b"pcm").decode())
    captions = [caption async for caption in Pipeline().process_audio(event)]
    assert len(captions) == 1
    assert captions[0].speaker_id == "SPEAKER_00"
    assert captions[0].is_final is True


def test_pcm16_silence_gate() -> None:
    assert is_silent_pcm16(b"\x00" * 3200) is True
    assert is_silent_pcm16((b"\x00\x00" * 1599) + b"\xff\x7f") is False


@pytest.mark.asyncio
async def test_mock_pipeline_ignores_silent_audio() -> None:
    event = AudioEvent(session_id="silent", audio_base64=base64.b64encode(b"\x00" * 3200).decode())
    captions = [caption async for caption in Pipeline().process_audio(event)]
    assert captions == []


@pytest.mark.asyncio
async def test_mock_pipeline_does_not_repeat_for_continuous_audio() -> None:
    pipeline = Pipeline()
    event = AudioEvent(session_id="continuous", audio_base64=base64.b64encode(b"pcm").decode())
    first = [caption async for caption in pipeline.process_audio(event)]
    second = [caption async for caption in pipeline.process_audio(event)]
    assert len(first) == 1
    assert second == []


@pytest.mark.asyncio
async def test_pipeline_rejects_invalid_audio() -> None:
    event = AudioEvent(session_id="test", audio_base64="not-base64")
    with pytest.raises(ValueError, match="valid base64"):
        _ = [caption async for caption in Pipeline().process_audio(event)]
