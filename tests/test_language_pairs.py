"""Bidirectional meeting routing, independent of locally installed models."""
import pytest

from meeting_interpreter.asr import ASRResult
from meeting_interpreter.models import SessionConfig
from meeting_interpreter.pipeline import Pipeline
from test_live_audio import audio


@pytest.mark.parametrize('pair', ['zh-ja', 'zh-en', 'en-ja'])
@pytest.mark.asyncio
async def test_alternating_pair_translates_both_sides_without_reconfiguring(pair):
    left, right = pair.split('-')
    text = {'zh': '请确认会议时间。', 'en': 'Please confirm the meeting time.', 'ja': '会議の時間を確認してください。'}
    calls = []

    class Recognizer:
        async def transcribe(self, pcm, rate, start):
            language = left if start < 2000 else right
            return ASRResult(text[language], language, start, start + len(pcm) // 32)

    class Translator:
        async def translate(self, utterance, source, target):
            calls.append((source, target))
            return text[target]

    pipeline = Pipeline(mode='local', source_language='auto', target_language=right,
                        language_pair=pair, asr_backend=Recognizer(), translator_backend=Translator())
    captions = []
    for samples in ([2000, -2000] * 6400, [0] * 25600, [2000, -2000] * 6400):
        captions.extend([c async for c in pipeline.process_audio(audio(samples))])
    final = {c.segment_id: c for c in captions if c.is_final}
    assert [(c.source_language, c.target_language) for c in final.values()] == [(left, right), (right, left)]
    assert all(c.original_text != c.translated_text and c.language_pair == pair for c in final.values())
    assert (left, right) in calls and (right, left) in calls


@pytest.mark.asyncio
async def test_pair_never_translates_unselected_third_language():
    class Recognizer:
        async def transcribe(self, pcm, rate, start):
            return ASRResult('这是第三种语言。', 'zh', start, start + 800)

    class Translator:
        async def translate(self, *args):
            pytest.fail('unselected language must not reach translation')

    pipeline = Pipeline(mode='local', language_pair='en-ja', asr_backend=Recognizer(), translator_backend=Translator())
    assert [c async for c in pipeline.process_audio(audio([2000, -2000] * 6400))] == []
    assert pipeline.audio_status['state'] == 'rejected'


def test_pair_config_preserves_legacy_single_direction_and_auto_decoder():
    from meeting_interpreter.asr import MLXWhisperBackend
    from pydantic import ValidationError
    assert SessionConfig(source_language='en', target_language='ja').language_pair is None
    with pytest.raises(ValidationError):
        SessionConfig(language_pair='zh-fr')
    warm = MLXWhisperBackend('already-local', language='zh')
    warm._mlx_whisper = object()
    pair = Pipeline(mode='local', language_pair='en-ja', asr_backend=warm)
    assert pair.asr.language is None
    assert warm.language == 'zh'
    locked = Pipeline(mode='local', source_language='en', language_pair='en-ja', asr_backend=warm)
    assert locked.language_pair is None
    assert locked.asr.language == 'en'
