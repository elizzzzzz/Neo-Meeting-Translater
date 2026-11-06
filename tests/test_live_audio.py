import base64
import struct

import pytest

from meeting_interpreter.asr import ASRResult, ASRWord
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
    assert 1 <= len(pipeline.asr.windows) <= 9


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
async def test_steady_background_bed_does_not_invoke_asr_but_core_voice_does():
    pipeline = Pipeline(mode="local", asr_backend=Recognizer())
    background = audio([110, -110] * 800)
    speaker = audio([420, -420] * 800)
    for _ in range(12):
        assert [c async for c in pipeline.process_audio(background)] == []
    assert pipeline.asr.windows == []
    for _ in range(8):
        _ = [c async for c in pipeline.process_audio(speaker)]
    assert pipeline.asr.windows


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


def test_websocket_chinese_config_applies_to_warmed_decoder(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from meeting_interpreter.app import create_app

    monkeypatch.setattr("meeting_interpreter.app.speaker_model_path", lambda: tmp_path / "absent.onnx")
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


@pytest.mark.asyncio
async def test_long_speech_keeps_completed_chunks_instead_of_overwriting_history():
    class TimedRecognizer:
        async def transcribe(self, pcm, sample_rate, start_ms):
            duration = round(len(pcm) / 32)
            return ASRResult(f"发言从{start_ms}到{start_ms + duration}。", "zh", start_ms, start_ms + duration)

    pipeline = Pipeline(mode="local", source_language="zh", target_language="zh", asr_backend=TimedRecognizer())
    latest = {}
    for _ in range(20):
        for caption in [c async for c in pipeline.process_audio(audio([2000, -2000] * 8000))]:
            latest[caption.segment_id] = caption
    assert len(latest) >= 3
    assert next(iter(latest.values())).start_ms == 0
    assert next(iter(latest.values())).end_ms <= 8000
    assert max(c.end_ms for c in latest.values()) == 20000
    assert sum(c.end_ms - c.start_ms for c in latest.values()) >= 20000


@pytest.mark.asyncio
async def test_speaker_change_closes_old_audio_before_starting_the_next_paragraph():
    class Speakers:
        changed_at_ms = 4000
        async def identify(self, pcm, sample_rate, start_ms):
            return 'SPEAKER_00' if start_ms < 4000 else 'SPEAKER_01'

    pipeline=Pipeline(mode='local',source_language='zh',target_language='zh',asr_backend=Recognizer())
    pipeline.speaker=Speakers()
    latest={}
    for _ in range(8):
        for c in [c async for c in pipeline.process_audio(audio([2000,-2000]*8000))]:
            latest[c.segment_id]=c
    ordered=list(latest.values())
    assert [c.speaker_id for c in ordered]==['SPEAKER_00','SPEAKER_01']
    assert ordered[0].end_ms==4000
    assert ordered[1].start_ms==4000


@pytest.mark.asyncio
async def test_manual_change_flushes_the_old_speaker_and_keeps_audio_out_of_next_speech():
    pipeline=Pipeline(mode='local',source_language='zh',target_language='zh',asr_backend=Recognizer())
    first=[c async for c in pipeline.process_audio(audio([1000,-1000]*8000))]
    _=[c async for c in pipeline.change_speaker()]
    second=[c async for c in pipeline.process_audio(audio([2000,-2000]*8000))]
    assert first[0].segment_id != second[0].segment_id
    assert first[0].speaker_id != second[0].speaker_id
    assert 1000 not in memoryview(pipeline.asr.windows[-1]).cast('h')


@pytest.mark.asyncio
async def test_stop_flushes_the_last_audio_that_has_not_reached_the_inference_interval():
    pipeline=Pipeline(mode='local',source_language='zh',target_language='zh',asr_backend=Recognizer())
    for samples in ([1000,-1000]*8000,[2000,-2000]*2400):
        _=[c async for c in pipeline.process_audio(audio(samples))]
    assert len(pipeline.asr.windows[-1])==32000
    final=[c async for c in pipeline.flush_audio()]
    assert len(pipeline.asr.windows[-1])==41600
    assert final[-1].end_ms==1300


@pytest.mark.asyncio
async def test_unstable_current_text_is_not_fed_back_as_its_own_recognition_prompt():
    class ContextRecognizer(Recognizer):
        def __init__(self):
            super().__init__()
            self.prompts=[]
        def set_context(self,text):
            self.prompts.append(text)

    recognizer=ContextRecognizer()
    pipeline=Pipeline(mode='local',source_language='zh',target_language='zh',asr_backend=recognizer)
    for _ in range(3):
        _=[c async for c in pipeline.process_audio(audio([1000,-1000]*8000))]
    assert recognizer.prompts==['','','']


@pytest.mark.asyncio
async def test_chunk_boundary_does_not_commit_a_word_cut_in_half():
    class WordRecognizer:
        supports_timestamps=True
        async def transcribe(self,pcm,sample_rate,start_ms):
            end_ms=start_ms+round(len(pcm)/32)
            words=[ASRWord('之前的发言。',0,min(6800,end_ms))]
            if end_ms>=8000:
                words.append(ASRWord('时间安排。' if end_ms>=10000 else '时',7600,min(10000,end_ms)))
            return ASRResult(''.join(w.text for w in words),'zh',start_ms,end_ms,tuple(words))
    pipeline=Pipeline(mode='local',source_language='zh',target_language='zh',asr_backend=WordRecognizer())
    latest={}
    for _ in range(10):
        for c in [c async for c in pipeline.process_audio(audio([1000,-1000]*8000))]:latest[c.segment_id]=c
    assert ''.join(c.original_text for c in latest.values())=='之前的发言。时间安排。'


@pytest.mark.asyncio
async def test_decoder_without_usable_word_times_does_not_replay_overlap():
    class UntimedRecognizer(Recognizer):
        supports_timestamps = True
    recognizer = UntimedRecognizer()
    pipeline = Pipeline(mode='local', source_language='zh', target_language='zh', asr_backend=recognizer)
    for _ in range(9):
        _ = [c async for c in pipeline.process_audio(audio([1000,-1000]*8000))]
    assert pipeline._buffer_start_ms['mic'] == 8000
    assert len(pipeline._buffers['mic']) == 32000


@pytest.mark.asyncio
async def test_audio_clock_counts_samples_without_rounding_each_capture_frame():
    pipeline = Pipeline(mode='local', source_language='zh', target_language='zh', asr_backend=Recognizer())
    event = audio([0] * 1365)  # common 48kHz capture -> 16kHz frame length
    for _ in range(1000):
        _ = [c async for c in pipeline.process_audio(event)]
    assert pipeline._audio_ms['mic'] == round(1365 * 1000 / 16000 * 1000)


@pytest.mark.asyncio
async def test_partial_recognition_refreshes_every_six_hundred_ms():
    recognizer = Recognizer()
    pipeline = Pipeline(mode='local', source_language='zh', target_language='zh', asr_backend=recognizer)
    for _ in range(7):
        _ = [c async for c in pipeline.process_audio(audio([1000, -1000] * 1600))]
    assert [len(pcm) // 32 for pcm in recognizer.windows] == [600, 1200]


@pytest.mark.asyncio
async def test_japanese_token_spacing_does_not_pollute_source_or_translation():
    class JapaneseRecognizer:
        async def transcribe(self, pcm, rate, start):
            return ASRResult('会議 の 開始 は 3 月 6 日 です。GPU memory は確認。', 'ja', start, start + 1000)
    pipeline = Pipeline(mode='local', source_language='ja', target_language='ja', asr_backend=JapaneseRecognizer())
    captions = [c async for c in pipeline.process_audio(audio([1000,-1000] * 8000))]
    assert captions[-1].original_text == '会議の開始は3月6日です。GPU memory は確認。'


@pytest.mark.asyncio
async def test_coalescing_does_not_erase_a_short_utterance_before_the_next_turn():
    recognizer = Recognizer()
    pipeline = Pipeline(mode='local', source_language='zh', target_language='zh', asr_backend=recognizer)
    _ = [c async for c in pipeline.process_audio(audio([1000,-1000]*4800), defer_partial=True)]
    closed = [c async for c in pipeline.process_audio(audio([0]*22400), defer_partial=True)]
    assert closed, 'The short speech must be decoded on its following silence before a new turn clears the buffer'
    assert 1000 in memoryview(recognizer.windows[-1]).cast('h')


def test_selected_sensevoice_language_is_warm_before_configuration_ack(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from meeting_interpreter.app import create_app
    from meeting_interpreter.asr import SenseVoiceBackend
    warmed=[]
    monkeypatch.setenv('MEETING_INTERPRETER_MODE','local')
    monkeypatch.setenv('MEETING_INTERPRETER_ASR_BACKEND','sensevoice')
    monkeypatch.setenv('MEETING_INTERPRETER_TRANSLATION_BACKEND','nllb')
    monkeypatch.setattr('meeting_interpreter.app.speaker_model_path',lambda:tmp_path/'absent')
    monkeypatch.setattr(SenseVoiceBackend,'warmup',lambda self:warmed.append(self.language))
    with TestClient(create_app()) as client:
        for _ in range(100):
            if client.get('/health').json()['models']['ready']: break
        else: pytest.fail('startup did not finish')
        with client.websocket_connect('/ws') as ws:
            ws.receive_json()
            ws.send_json(dict(type='config',source_language='ja',target_language='zh'))
            while True:
                event=ws.receive_json()
                if event['type']=='configured': break
                assert event['type'] != 'error'
            assert warmed == [None,'ja']
            assert event['asr_language']=='ja'
