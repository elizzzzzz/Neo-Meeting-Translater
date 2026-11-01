import base64

import pytest

from meeting_interpreter.models import AudioEvent
from meeting_interpreter.pipeline import Pipeline


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
