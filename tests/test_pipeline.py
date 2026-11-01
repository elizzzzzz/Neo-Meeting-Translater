import base64

import pytest

from meeting_interpreter.models import AudioEvent
from meeting_interpreter.pipeline import Pipeline
from meeting_interpreter.translation import NLLBTranslationBackend, nllb_language_code
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
async def test_pending_speaker_backend_is_safe_default() -> None:
    assert await PendingSpeakerBackend().identify(b"pcm", 16_000, 0) == "SPEAKER_PENDING"


@pytest.mark.asyncio
async def test_mock_pipeline_emits_caption() -> None:
    event = AudioEvent(session_id="test", audio_base64=base64.b64encode(b"pcm").decode())
    captions = [caption async for caption in Pipeline().process_audio(event)]
    assert len(captions) == 1
    assert captions[0].speaker_id == "SPEAKER_00"
    assert captions[0].is_final is True


@pytest.mark.asyncio
async def test_pipeline_rejects_invalid_audio() -> None:
    event = AudioEvent(session_id="test", audio_base64="not-base64")
    with pytest.raises(ValueError, match="valid base64"):
        _ = [caption async for caption in Pipeline().process_audio(event)]
