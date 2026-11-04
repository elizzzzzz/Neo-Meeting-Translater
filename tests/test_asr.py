import struct

import pytest

from meeting_interpreter.asr import MLXWhisperBackend


@pytest.mark.asyncio
async def test_sensevoice_silence_never_reaches_decoder(tmp_path):
    from meeting_interpreter.asr import SenseVoiceBackend
    backend = SenseVoiceBackend(str(tmp_path), 'zh')
    assert await backend.transcribe(bytes(32000), 16000, 0) is None


@pytest.mark.asyncio
async def test_sensevoice_returns_chinese_and_japanese_with_token_times(tmp_path):
    from types import SimpleNamespace
    from meeting_interpreter.asr import SenseVoiceBackend
    class Stream:
        def accept_waveform(self, rate, waveform): assert rate == 16000
        result = SimpleNamespace(text='今日は会議です。', lang='<|ja|>', event='<|Speech|>',
                                 tokens=['今日', 'は', '会議', 'です', '。'], timestamps=[.1, .2, .3, .4, .5])
    class Recognizer:
        def create_stream(self): return Stream()
        def decode_stream(self, stream): pass
    backend = SenseVoiceBackend(str(tmp_path), 'ja')
    backend._recognizer = Recognizer()
    backend._has_speech = lambda waveform: True
    result = await backend.transcribe(struct.pack('<hh', 2000, -2000) * 4800, 16000, 7000)
    assert result.text == '今日は会議です。'
    assert result.language == 'ja'
    assert result.words[0].start_ms == 7100
    assert result.words[-1].end_ms == 7600
    assert backend.for_language('zh').language == 'zh'
    assert backend.language == 'ja'


@pytest.mark.asyncio
async def test_sensevoice_noise_rejected_by_speech_detector_never_becomes_a_caption(tmp_path):
    from meeting_interpreter.asr import SenseVoiceBackend
    backend = SenseVoiceBackend(str(tmp_path), 'zh')
    backend._has_speech = lambda waveform: False
    assert await backend.transcribe(struct.pack('<hh', 350, -350)*32000, 16000, 0) is None


def test_asr_selection_defaults_to_whisper_and_can_select_local_sensevoice(monkeypatch, tmp_path):
    from meeting_interpreter.asr import create_asr_backend, SenseVoiceBackend
    monkeypatch.delenv('MEETING_INTERPRETER_ASR_BACKEND', raising=False)
    assert isinstance(create_asr_backend('ja'), MLXWhisperBackend)
    monkeypatch.setenv('MEETING_INTERPRETER_ASR_BACKEND', 'sensevoice')
    monkeypatch.delenv('MEETING_INTERPRETER_SENSEVOICE_MODEL', raising=False)
    monkeypatch.setenv('MEETING_INTERPRETER_MODEL_DIR', str(tmp_path))
    backend = create_asr_backend('zh')
    assert isinstance(backend, SenseVoiceBackend)
    assert backend.model == str(tmp_path / 'asr/sensevoice')


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


@pytest.mark.asyncio
async def test_detected_speech_is_not_dropped_for_whisper_no_speech_score_alone(tmp_path):
    decoder = Decoder([{'text':'我补充一点，预算三万元。','no_speech_prob':.87,'avg_logprob':-.28,'compression_ratio':1.03}])
    backend = MLXWhisperBackend('cached-model','zh')
    backend._mlx_whisper = decoder
    backend._speech_detector = lambda waveform: True
    result = await backend.transcribe(struct.pack('<hh',2000,-2000)*8000,16000,0)
    assert result.text == '我补充一点，预算三万元。'


@pytest.mark.asyncio
async def test_decoder_returns_absolute_word_times_for_nonduplicating_chunk_overlap():
    decoder = Decoder([{'text':'今天开会。','no_speech_prob':.01,'avg_logprob':-.2,
                        'words':[{'word':'今天','start':.2,'end':.5},{'word':'开会。','start':.5,'end':1.0}]}])
    backend=MLXWhisperBackend('cached-model','zh')
    backend._mlx_whisper=decoder
    result=await backend.transcribe(struct.pack('<h',1000)*16000,16000,7000)
    assert decoder.options['word_timestamps'] is True
    assert result.words[0].start_ms == 7200
    assert result.words[-1].end_ms == 8000


@pytest.mark.asyncio
async def test_quiet_meeting_speech_is_kept_while_silence_and_noise_stay_rejected():
    """Optional real-model regression; no recording/model downloads in pytest."""
    import os
    import wave
    from pathlib import Path
    import numpy as np
    from meeting_interpreter.asr import SenseVoiceBackend
    recording = os.getenv('LMI_TEST_MEETING_WAV')
    model = os.getenv('LMI_TEST_SENSEVOICE_MODEL')
    if not recording or not model or not Path(recording).is_file():
        pytest.skip('Set LMI_TEST_MEETING_WAV and LMI_TEST_SENSEVOICE_MODEL for AISHELL-4 regression')
    with wave.open(recording) as f:
        f.setpos(round(89.06 * 16000))
        pcm = f.readframes(round(5.54 * 16000))
    backend = SenseVoiceBackend(model, 'zh')
    result = await backend.transcribe(pcm, 16000, 89060)
    assert result is not None, 'Audible, annotated speech was incorrectly rejected by VAD'
    assert '工作' in result.text and '汇报' in result.text
    assert await backend.transcribe(bytes(160000), 16000, 0) is None
    noise = (np.random.default_rng(7).normal(0,.01,80000)*32768).astype(np.int16).tobytes()
    assert await backend.transcribe(noise,16000,0) is None


def test_sensevoice_language_sessions_reuse_the_warmed_speech_detector(tmp_path):
    from meeting_interpreter.asr import SenseVoiceBackend
    backend = SenseVoiceBackend(str(tmp_path))
    chinese, japanese = backend.for_language('zh'), backend.for_language('ja')
    assert chinese._speech_detector is backend._speech_detector
    assert japanese._speech_detector is backend._speech_detector
    assert chinese.language == 'zh' and japanese.language == 'ja'
