import asyncio
import base64
import time
from array import array

import pytest

from meeting_interpreter.asr import ASRResult
from meeting_interpreter.models import AudioEvent, CaptionEvent
from meeting_interpreter.pipeline import Pipeline
from meeting_interpreter.streaming import LiveSession


async def wait_until(predicate, timeout=.8):
    async def poll():
        while not predicate():
            await asyncio.sleep(.002)
    await asyncio.wait_for(poll(), timeout)


@pytest.mark.asyncio
async def test_unchanged_recognition_keeps_timeout_marker_until_source_changes():
    sent = []
    async def send(payload): sent.append(payload)
    session = LiveSession(Pipeline(mode='mock'), send)
    caption = CaptionEvent(session_id='meeting', segment_id='1', speaker_id='A',
                           source_language='zh', target_language='ja',
                           original_text='请确认时间', translated_text='', start_ms=0, end_ms=800)
    try:
        await session._publish(caption, time.monotonic() + 1)
        await session._skip_caption(('meeting', '1'), 'translation')
        await session._publish(caption.model_copy(update={'end_ms': 1000}), time.monotonic() + 1)
        assert sent[-1]['skipped_stage'] == 'translation'
        assert sent[-1]['is_final']
        await session._publish(caption.model_copy(update={'original_text': '请确认会议时间', 'end_ms': 1200}), time.monotonic() + 1)
        assert sent[-1]['skipped_stage'] is None
        assert not sent[-1]['is_final']
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_recognition_timeout_drops_late_output_and_resumes_without_concurrent_jobs():
    release = asyncio.Event()
    calls = []
    class SlowFirst(Recognizer):
        async def transcribe(self, pcm, rate, start):
            calls.append(start)
            if len(calls) == 1:
                await release.wait()
                return ASRResult('过期的原文', 'zh', start, start + 800)
            return await super().transcribe(pcm, rate, start)
    sent = []
    async def send(payload): sent.append(payload)
    pipeline = Pipeline(mode='local', source_language='zh', target_language='zh', asr_backend=SlowFirst(), translate_inline=False)
    session = LiveSession(pipeline, send, latency_budget=.05)
    session.start()
    try:
        for _ in range(4): session.feed(audio())
        await wait_until(lambda: any(e['type'] == 'segment_skipped' for e in sent))
        for _ in range(4): session.feed(audio())
        await wait_until(lambda: session.processed_samples == session.received_samples)
        assert len(calls) == 1
        release.set()
        await wait_until(lambda: session._decode_task.done())
        for _ in range(4): session.feed(audio())
        await session.finish()
        captions = [e for e in sent if e['type'] == 'caption']
        assert captions and all('过期' not in e['original_text'] for e in captions)
        assert captions[0]['start_ms'] == 1600
        assert session.dropped_samples > 0
    finally:
        release.set()
        await session.close()


@pytest.mark.asyncio
async def test_translation_shares_capture_deadline_and_never_publishes_late_results():
    class SlowRecognizer(Recognizer):
        async def transcribe(self, *args):
            await asyncio.sleep(.035)
            return await super().transcribe(*args)
    release = asyncio.Event()
    class Translator:
        async def translate(self, *args):
            await release.wait()
            return '不应显示的迟到译文'
    sent = []
    async def send(payload): sent.append(payload)
    pipeline = Pipeline(mode='local', source_language='zh', target_language='ja', asr_backend=SlowRecognizer(), translator_backend=Translator(), translate_inline=False)
    session = LiveSession(pipeline, send, latency_budget=.065)
    session.start()
    try:
        started = time.monotonic()
        for _ in range(4): session.feed(audio())
        await wait_until(lambda: any(e.get('skipped_stage') == 'translation' for e in sent))
        assert time.monotonic() - started < .13
        release.set()
        await session.finish()
        captions = [e for e in sent if e['type'] == 'caption']
        assert any(e['original_text'] for e in captions)
        assert not any(e.get('translated_text') for e in captions)
        assert captions[-1]['is_final'] and captions[-1]['skipped_stage'] == 'translation'
    finally:
        release.set()
        await session.close()


@pytest.mark.asyncio
async def test_expired_capture_queue_is_dropped_before_model_inference():
    calls = []
    class TrackedRecognizer(Recognizer):
        async def transcribe(self, *args):
            calls.append(args[2])
            return await super().transcribe(*args)
    sent = []
    async def send(payload): sent.append(payload)
    pipeline = Pipeline(mode='local', source_language='zh', target_language='zh', asr_backend=TrackedRecognizer(), translate_inline=False)
    session = LiveSession(pipeline, send)
    for _ in range(4): session.feed(audio().model_copy(update={'captured_at_ms': (time.time() - 10) * 1000}))
    for _ in range(4): session.feed(audio())
    session.start()
    try:
        await session.finish()
        assert session.dropped_samples == 12800
        assert calls and min(calls) == 800
        assert session.processed_samples == session.received_samples
    finally:
        await session.close()


def audio(value=1000):
    pcm = array('h', [value, -value] * 1600).tobytes()
    return AudioEvent(session_id='meeting', audio_base64=base64.b64encode(pcm).decode())


class Recognizer:
    async def transcribe(self, pcm, sample_rate, start_ms):
        await asyncio.sleep(0)
        end = start_ms + len(pcm) // 32
        return ASRResult(f'发言{start_ms}到{end}。', 'zh', start_ms, end)


@pytest.mark.asyncio
async def test_slow_translation_does_not_block_recognition_or_discard_audio():
    entered, release = asyncio.Event(), asyncio.Event()
    class Translator:
        async def translate(self, text, source, target):
            entered.set()
            await release.wait()
            return '訳：' + text
    sent = []
    async def send(payload): sent.append(payload)
    pipeline = Pipeline(mode='local', source_language='zh', target_language='ja',
                        asr_backend=Recognizer(), translator_backend=Translator(), translate_inline=False)
    session = LiveSession(pipeline, send)
    session.start()
    try:
        for _ in range(5): session.feed(audio())
        await asyncio.wait_for(entered.wait(), 1)
        for _ in range(55): session.feed(audio())
        async def caught_up():
            while session.processed_samples < 192000: await asyncio.sleep(.001)
        await asyncio.wait_for(caught_up(), 1)
        assert session.received_samples == session.processed_samples == 192000
        assert any(e.get('end_ms') == 12000 for e in sent)
        assert not any(e.get('translated_text') for e in sent)
        release.set()
        await asyncio.wait_for(session.finish(), 1)
        captions = [e for e in sent if e['type'] == 'caption']
        # Completing an old translation must never roll the source backwards.
        ends = [e['end_ms'] for e in captions if e['segment_id'] == 'seg-000001']
        assert ends == sorted(ends)
        final = {e['segment_id']: e for e in captions}
        assert all(e['translated_text'] == '訳：' + e['original_text'] for e in final.values())
    finally:
        release.set()
        await session.close()


@pytest.mark.asyncio
async def test_manual_boundary_and_stop_drain_audio_in_order():
    sent = []
    async def send(payload): sent.append(payload)
    pipeline = Pipeline(mode='local', source_language='zh', target_language='zh', asr_backend=Recognizer(), translate_inline=False)
    session = LiveSession(pipeline, send)
    session.start()
    try:
        for _ in range(7): session.feed(audio())
        session.change_speaker()
        for _ in range(8): session.feed(audio(2000))
        await session.finish()
        final = {e['segment_id']: e for e in sent if e['type'] == 'caption'}
        assert [(e['start_ms'], e['end_ms']) for e in final.values()] == [(0, 1400), (1400, 3000)]
        assert len({e['speaker_id'] for e in final.values()}) == 2
        assert session.received_samples == session.processed_samples == 48000
    finally: await session.close()


@pytest.mark.asyncio
async def test_capacity_failure_is_explicit_and_retains_accepted_audio():
    async def send(payload): pass
    pipeline = Pipeline(mode='mock')
    session = LiveSession(pipeline, send, max_bytes=6400)
    try:
        session.feed(audio())
        with pytest.raises(BufferError, match='停止收音'):
            session.feed(audio())
        assert session.received_samples == 3200
    finally: await session.close()


@pytest.mark.asyncio
async def test_websocket_acknowledges_new_audio_while_translation_is_busy(monkeypatch):
    import json
    from fastapi import WebSocketDisconnect
    from meeting_interpreter import app as app_module
    real_pipeline = Pipeline
    entered, release = asyncio.Event(), asyncio.Event()
    class Translator:
        async def translate(self, text, source, target):
            entered.set()
            await release.wait()
            return '訳文'
    def pipeline(**kwargs):
        kwargs.update(mode='local', asr_backend=Recognizer(), translator_backend=Translator(), source_language='zh', target_language='ja')
        return real_pipeline(**kwargs)
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'mock')
    monkeypatch.setattr(app_module, 'Pipeline', pipeline)
    application = app_module.create_app()
    endpoint = next(r.endpoint for r in application.routes if getattr(r, 'path', '') == '/ws')
    incoming, outgoing = asyncio.Queue(), asyncio.Queue()
    class Socket:
        async def accept(self): pass
        async def receive_text(self):
            item = await incoming.get()
            if item is None: raise WebSocketDisconnect()
            return json.dumps(item)
        async def send_json(self, item): await outgoing.put(item)
        async def close(self): pass
    async def receive(kind):
        while True:
            item = await asyncio.wait_for(outgoing.get(), 1)
            if item['type'] == kind: return item
    task = asyncio.create_task(endpoint(Socket()))
    try:
        await receive('status')
        for _ in range(5):
            await incoming.put(audio().model_dump())
            assert (await receive('audio_ack'))['accepted']
        await asyncio.wait_for(entered.wait(), 1)
        await incoming.put(audio().model_dump())
        ack = await asyncio.wait_for(receive('audio_ack'), .1)
        assert ack['received_samples'] == 19200
        release.set()
        await incoming.put({'type':'finish'})
        result = await receive('session_finished')
        assert result['received_samples'] == result['processed_samples'] == 19200
        await task
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_backlog_coalesces_obsolete_recognition_revisions_without_skipping_speech():
    entered, release = asyncio.Event(), asyncio.Event()
    windows = []
    class SlowFirstRecognizer(Recognizer):
        async def transcribe(self, pcm, rate, start):
            windows.append((start, len(pcm) // 32))
            if len(windows) == 1:
                entered.set()
                await release.wait()
            return await super().transcribe(pcm, rate, start)
    async def send(payload): pass
    pipeline = Pipeline(mode='local', source_language='zh', target_language='zh', asr_backend=SlowFirstRecognizer(), translate_inline=False)
    session = LiveSession(pipeline, send)
    session.start()
    try:
        for _ in range(5): session.feed(audio())
        await asyncio.wait_for(entered.wait(), 1)
        for _ in range(55): session.feed(audio())
        release.set()
        await session.finish()
        assert session.received_samples == session.processed_samples == 192000
        assert (0, 8000) in windows  # Completed history still decoded in full.
        assert windows[-1] == (8000, 4000)
        assert len(windows) <= 4
    finally:
        release.set()
        await session.close()


@pytest.mark.asyncio
async def test_streamed_translation_is_visible_before_generation_finishes():
    release = asyncio.Event()
    partial = asyncio.Event()
    class Translator:
        async def stream_translate(self, text, source, target):
            yield '正在'
            await release.wait()
            yield '正在翻译。'
        async def translate(self, *args): raise AssertionError('streaming should be preferred')
    sent=[]
    async def send(payload):
        sent.append(payload)
        if payload.get('translated_text') == '正在': partial.set()
    pipeline=Pipeline(mode='local',source_language='zh',target_language='ja',asr_backend=Recognizer(),translator_backend=Translator(),translate_inline=False)
    session=LiveSession(pipeline,send);session.start()
    try:
        for _ in range(5):session.feed(audio())
        await asyncio.wait_for(partial.wait(),1)
        assert not next(e for e in sent if e.get('translated_text')=='正在')['is_final']
        release.set();await session.finish()
        assert [e for e in sent if e['type']=='caption'][-1]['translated_text']=='正在翻译。'
    finally:
        release.set();await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('pair,first,second', [('zh-ja','zh','ja'), ('zh-en','zh','en'), ('en-ja','en','ja')])
async def test_live_language_switch_is_ordered_and_routes_to_other_pair_member(pair, first, second):
    entered, release = asyncio.Event(), asyncio.Event()
    calls, sent = [], []
    class LanguageRecognizer:
        def __init__(self, language): self.language = language
        def for_language(self, language): return LanguageRecognizer(language)
        async def transcribe(self, pcm, rate, start):
            language = self.language
            calls.append(language)
            if len(calls) == 1:
                entered.set()
                await release.wait()
            detected = language if language != 'auto' else first
            text = {'zh':'今天讨论会议。', 'ja':'これは会議です。', 'en':'This is a meeting.'}[detected]
            return ASRResult(text, detected, start, start + len(pcm)//32)
    async def send(payload): sent.append(payload)
    class LocalTranslator:
        async def translate(self, *args): return '本地测试译文'
    pipeline = Pipeline(mode='local', source_language=first, target_language=second, language_pair=pair,
                        asr_backend=LanguageRecognizer(first), translator_backend=LocalTranslator(), translate_inline=False)
    session = LiveSession(pipeline, send)
    session.start()
    try:
        for _ in range(4): session.feed(audio())
        await asyncio.wait_for(entered.wait(), 1)
        session.change_source_language(second)
        for _ in range(4): session.feed(audio())
        assert pipeline.source_language == first
        release.set()
        await wait_until(lambda: any(e['type']=='source_language_changed' for e in sent))
        await wait_until(lambda: len(calls) >= 2)
        first_caption = next(e for e in sent if e['type']=='caption')
        assert first_caption['source_language'] == first
        switched = [e for e in sent if e['type']=='caption' and e['source_language']==second]
        assert switched and switched[-1]['target_language']==first
        assert switched[-1]['paragraph_id']==first_caption['paragraph_id']
        session.change_source_language('auto')
        for _ in range(4): session.feed(audio())
        await session.finish()
        assert pipeline.source_language=='auto' and pipeline.language_pair==pair
        assert 'auto' in calls
        assert session.dropped_samples==0
    finally:
        release.set()
        await session.close()


@pytest.mark.asyncio
async def test_language_change_waits_for_expired_native_decode_without_reusing_late_result():
    entered, release = asyncio.Event(), asyncio.Event()
    class Slow(Recognizer):
        async def transcribe(self, *args):
            entered.set()
            await release.wait()
            return await super().transcribe(*args)
    sent=[]
    async def send(payload): sent.append(payload)
    pipeline = Pipeline(mode='local', source_language='zh', target_language='zh', asr_backend=Slow(), translate_inline=False)
    session=LiveSession(pipeline,send,latency_budget=.03)
    session.start()
    try:
        for _ in range(4): session.feed(audio())
        await asyncio.wait_for(entered.wait(),1)
        await wait_until(lambda:any(e['type']=='segment_skipped' for e in sent))
        session.change_source_language('auto')
        await asyncio.sleep(.01)
        assert pipeline.source_language=='zh'
        release.set()
        await wait_until(lambda:any(e['type']=='source_language_changed' for e in sent))
        assert pipeline.source_language=='auto'
        assert not [e for e in sent if e['type']=='caption']
    finally:
        release.set()
        await session.close()
