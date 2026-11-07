"""Ordered local audio spool with independent recognition and translation workers."""
from __future__ import annotations

import asyncio
import base64
import tempfile
import time
from collections import deque
from collections.abc import Awaitable, Callable

from .models import AudioEvent, CaptionEvent
from .pipeline import Pipeline


class LiveSession:
    def __init__(self, pipeline: Pipeline, send: Callable[[dict], Awaitable[None]], max_bytes: int = 512 * 1024 * 1024, latency_budget: float = 4.8):
        self.pipeline, self.send = pipeline, send
        self.max_bytes = max_bytes
        # Audio stays on this computer; no growing in-memory PCM backlog.
        self._audio = tempfile.TemporaryFile(prefix='meeting-audio-', suffix='.pcm')
        self._written = 0
        self._records = deque()
        self._available = asyncio.Event()
        self._translate_available = asyncio.Event()
        self._pending = {}  # Latest revision per segment, insertion order retained.
        self._captions = {}
        self._workers = []
        self._ended = False
        self._recognition_done = False
        self._failure = None
        self._format = None
        self.received_samples = 0
        self.processed_samples = 0
        self.sample_rate = 16000
        self.latency_budget = min(4.8, max(.01, latency_budget))
        self.dropped_samples = 0
        self.skipped_translations = 0
        self._deadlines = {}
        self._decode_task = None
        self._translation_task = None
        self._recovery_event = None
        self._recovery_samples = 0
        self._pending_source_language = None

    def start(self):
        self._workers = [asyncio.create_task(self._recognize()), asyncio.create_task(self._translate())]

    def feed(self, event: AudioEvent):
        if self._ended or self._failure:
            raise ValueError('收音已停止，请等待当前发言处理完成')
        raw = base64.b64decode(event.audio_base64, validate=True)
        if self.pipeline.mode == 'local' and (len(raw) % 2 or event.channels != 1):
            raise ValueError('语音识别需要完整的 PCM16 单声道音频')
        if len(raw) > event.sample_rate * 2 * 5:
            raise ValueError('单个音频包不能超过 5 秒')
        signature = (event.session_id, event.sample_rate, event.channels)
        if self._format is not None and signature != self._format:
            raise ValueError('录音期间不能更改会话或采样格式')
        self._format = signature
        self.sample_rate = event.sample_rate
        if not self._records:
            # Any in-flight record has already been read into its small decode buffer.
            self._audio.seek(0)
            self._audio.truncate()
            self._written = 0
        if self._written + len(raw) > self.max_bytes:
            raise BufferError('本地音频缓冲空间已满，已停止收音；请等待已接收的语音处理完成')
        offset = self._written
        self._audio.seek(offset)
        self._audio.write(raw)
        self._written += len(raw)
        metadata = event.model_copy(update={'audio_base64': ''})
        age = max(0, time.time() - event.captured_at_ms / 1000) if event.captured_at_ms is not None else 0
        received_deadline = time.monotonic() + max(0, self.latency_budget - age)
        if self._records and self._records[-1][0] == 'audio':
            kind, previous, start, size, deadline = self._records[-1]
            if deadline > time.monotonic() and start + size == offset and size + len(raw) <= event.sample_rate * 2 * .8:
                self._records[-1] = (kind, previous, start, size + len(raw), deadline)
            else:
                self._records.append(('audio', metadata, offset, len(raw), received_deadline))
        else:
            self._records.append(('audio', metadata, offset, len(raw), received_deadline))
        self.received_samples += len(raw) // 2
        self._available.set()

    def change_speaker(self):
        self._records.append(('speaker', None, 0, 0, time.monotonic() + self.latency_budget))
        self._available.set()

    def change_source_language(self, language):
        if language not in {'auto', 'zh', 'ja', 'en'}:
            raise ValueError('源语言只能选择自动、中文、日语或英语')
        if language != 'auto' and self.pipeline.language_pair and language not in self.pipeline.language_pair.split('-'):
            raise ValueError('请选择当前会议语言组合内的源语言')
        self._records.append(('language', language, 0, 0, time.monotonic() + self.latency_budget))
        self._available.set()

    async def _apply_source_language(self):
        language = self._pending_source_language
        if language is None or self._decode_task is not None:
            return
        if hasattr(self.pipeline.asr, 'ensure_language_ready'):
            try:
                await self.pipeline.asr.ensure_language_ready(language)
            except Exception as exc:
                self._pending_source_language = None
                await self.send({'type': 'source_language_changed', 'source_language': self.pipeline.source_language,
                                 'target_language': self.pipeline.target_language,
                                 'message': f'源语言未切换：{exc}'})
                return
        self.pipeline.set_source_language(language)
        self._pending_source_language = None
        await self.send({'type': 'source_language_changed', 'source_language': language,
                         'asr_language': language, 'target_language': self.pipeline.target_language,
                         'language_pair': self.pipeline.language_pair,
                         'message': '已恢复自动识别' if language == 'auto' else f'源语言已锁定为{dict(zh="中文", ja="日语", en="英语")[language]}'})

    def metrics(self):
        return {'received_samples': self.received_samples, 'processed_samples': self.processed_samples,
                'queued_audio_ms': round((self.received_samples - self.processed_samples) * 1000 / self.sample_rate),
                'dropped_samples': self.dropped_samples, 'skipped_translations': self.skipped_translations,
                'pending_translations': len(self._pending)}

    async def _publish(self, caption: CaptionEvent, deadline: float):
        if time.monotonic() >= deadline:
            return
        key = (caption.session_id, caption.segment_id)
        previous = self._captions.get(key)
        if (previous and previous.source_language == caption.source_language
                and previous.target_language == caption.target_language):
            if previous.original_text == caption.original_text:
                caption = caption.model_copy(update={'translated_text': previous.translated_text,
                                                      'is_final': previous.is_final,
                                                      'skipped_stage': previous.skipped_stage})
            elif not caption.translated_text:
                caption = caption.model_copy(update={'translated_text': previous.translated_text})
        self._captions[key] = caption
        self._deadlines[key] = deadline
        await self.send({**caption.model_dump(mode='json'), 'queued_audio_ms': self.metrics()['queued_audio_ms']})
        if self.pipeline.translator is not None and caption.source_language != caption.target_language and not caption.is_final:
            self._pending[key] = caption
            self._translate_available.set()

    async def _skip_caption(self, key, stage):
        self._pending.pop(key, None)
        previous = self._captions.get(key)
        if previous is None or previous.is_final:
            return
        updated = previous.model_copy(update={'is_final': True, 'skipped_stage': stage})
        self._captions[key] = updated
        await self.send(updated.model_dump(mode='json'))

    async def _drop_audio(self, event, samples, reason):
        self.processed_samples += samples
        self.dropped_samples += samples
        if self._decode_task is not None:
            self._recovery_event = event
            self._recovery_samples += samples
        else:
            self.pipeline.discard_audio(event, samples)
        await self.send({'type': 'segment_skipped', 'stage': 'recognition', 'reason': reason,
                         'message': '识别等待超时，本段已跳过；继续接收最新发言', **self.metrics()})

    def _recover_decoder(self):
        if self._decode_task is not None and self._decode_task.done():
            # Native GPU/thread inference cannot be killed safely. Drain its late
            # result, never publish it or queue another inference behind its lock.
            if not self._decode_task.cancelled():
                self._decode_task.exception()
            self._decode_task = None
            if self._recovery_event is not None:
                self.pipeline.discard_audio(self._recovery_event, self._recovery_samples)
            self._recovery_event = None
            self._recovery_samples = 0

    async def _decode(self, iterator, deadline):
        async def collect():
            return [caption async for caption in iterator]
        self._decode_task = asyncio.create_task(collect())
        remaining = max(0, deadline - time.monotonic())
        result = await asyncio.wait_for(asyncio.shield(self._decode_task), remaining)
        self._decode_task = None
        for caption in result:
            await self._publish(caption, deadline)

    async def _recognize(self):
        try:
            while True:
                self._recover_decoder()
                await self._apply_source_language()
                if not self._records:
                    if self._ended:
                        break
                    self._available.clear()
                    await self._available.wait()
                    continue
                kind, event, offset, size, deadline = self._records.popleft()
                self._recover_decoder()
                if kind == 'language':
                    self._pending_source_language = event
                    if self._decode_task is not None:
                        self._decode_task.add_done_callback(lambda _: self._available.set())
                    await self._apply_source_language()
                    continue
                if kind == 'speaker':
                    # Keep manual boundaries even when a native decode is late.
                    if self._decode_task is not None:
                        self.pipeline.mark_speaker_change()
                    else:
                        try:
                            await self._decode(self.pipeline.change_speaker(), deadline)
                        except TimeoutError:
                            self._recovery_event = next(iter(self.pipeline._last_events.values()), None)
                    continue
                if self._decode_task is not None or time.monotonic() >= deadline:
                    await self._drop_audio(event, size // 2, 'decoder_busy' if self._decode_task else 'queue_timeout')
                    continue
                self._audio.seek(offset)
                raw = self._audio.read(size)
                event = event.model_copy(update={'audio_base64': base64.b64encode(raw).decode()})
                started = time.perf_counter()
                defer_partial = bool(self._records and self._records[0][0] == "audio")
                try:
                    await self._decode(self.pipeline.process_audio(event, defer_partial=defer_partial), deadline)
                except TimeoutError:
                    self._recovery_event = event
                    self.dropped_samples += size // 2
                    for key in list(self._captions):
                        if key[0] == event.session_id:
                            await self._skip_caption(key, 'recognition')
                    await self.send({'type': 'segment_skipped', 'stage': 'recognition',
                                     'message': '识别超时，本段已跳过；等待引擎恢复后继续最新发言'})
                self.processed_samples += size // 2
                await self.send({'type': 'audio_status', **self.pipeline.audio_status, **self.metrics(),
                                 'recognition_work_ms': round((time.perf_counter() - started) * 1000)})
            self._recover_decoder()
            if self._decode_task is None:
                # Flushing never grants stale speech a new latency budget.
                deadline = max(self._deadlines.values(), default=time.monotonic())
                if deadline > time.monotonic():
                    try:
                        await self._decode(self.pipeline.flush_audio(), deadline)
                    except TimeoutError:
                        pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._failure = exc
            await self.send({'type': 'capture_paused', 'message': f'语音识别失败，已停止收音：{exc}', **self.metrics()})
        finally:
            self._recognition_done = True
            self._translate_available.set()

    async def _translation_job(self, key, caption, deadline):
        started = time.perf_counter()

        async def publish(text, complete):
            latest = self._captions[key]
            current = (latest.original_text == caption.original_text
                       and latest.source_language == caption.source_language
                       and latest.target_language == caption.target_language
                       and self._deadlines[key] == deadline)
            if not current or latest.skipped_stage or time.monotonic() >= deadline:
                return
            if not complete and caption.translated_text:
                return  # Keep the previous full translation until revision completes.
            updated = latest.model_copy(update={'translated_text': text, 'is_final': complete})
            self._captions[key] = updated
            if complete:
                self._pending.pop(key, None)
            await self.send({**updated.model_dump(mode='json'),
                'translation_work_ms': round((time.perf_counter() - started) * 1000),
                'translation_complete': complete, 'translated_through_ms': caption.end_ms,
                'translation_source_text': caption.original_text})

        stream = getattr(self.pipeline.translator, 'stream_translate', None)
        if stream is not None:
            text, published_at, last_text = '', 0.0, ''
            async for text in stream(caption.original_text, caption.source_language, caption.target_language):
                now = time.monotonic()
                if now >= deadline:
                    raise TimeoutError('translation deadline expired')
                if text and text != last_text and now - published_at >= .22:
                    await publish(text, False)
                    published_at, last_text = now, text
            if not text:
                raise RuntimeError('翻译模型返回了空翻译')
        else:
            text = await self.pipeline.translator.translate(caption.original_text, caption.source_language, caption.target_language)
        if time.monotonic() >= deadline:
            raise TimeoutError('translation deadline expired')
        await publish(text, True)

    async def _translate(self):
        while True:
            if not self._pending:
                if self._recognition_done:
                    return
                self._translate_available.clear()
                await self._translate_available.wait()
                continue
            key = next(iter(self._pending))
            caption = self._pending.pop(key)
            deadline = self._deadlines[key]
            if self._translation_task is not None and self._translation_task.done():
                if not self._translation_task.cancelled():
                    self._translation_task.exception()
                self._translation_task = None
            if time.monotonic() >= deadline or self._translation_task is not None:
                await self._expire_translation(key, caption, deadline)
                continue
            started = time.perf_counter()
            await self.send({'type': 'translation_status', 'state': 'processing', 'pending_translations': len(self._pending)})
            self._translation_task = asyncio.create_task(self._translation_job(key, caption, deadline))
            try:
                await asyncio.wait_for(asyncio.shield(self._translation_task), max(0, deadline - time.monotonic()))
                self._translation_task = None
            except TimeoutError:
                # Keep a single outstanding job until native/HTTP work returns.
                # Its deadline guard rejects all late output.
                await self._expire_translation(key, caption, deadline)
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._translation_task = None
                if self._deadlines[key] == deadline:
                    await self._skip_caption(key, 'translation')
                await self.send({'type': 'translation_status', 'state': 'error', 'message': str(exc)})
                await self.send({'type': 'error', 'message': f'翻译失败，原文已保留：{exc}'})
                continue
            await self.send({'type': 'translation_status', 'state': 'running',
                             'last_response_ms': round((time.perf_counter() - started) * 1000),
                             'pending_translations': len(self._pending)})

    async def _expire_translation(self, key, caption, deadline):
        self.skipped_translations += 1
        if self._deadlines[key] == deadline:
            await self._skip_caption(key, 'translation')
        await self.send({'type': 'segment_skipped', 'stage': 'translation',
                         'session_id': caption.session_id, 'segment_id': caption.segment_id,
                         'message': '翻译超时或引擎仍忙，已跳过本段译文；原文保留', **self.metrics()})

    async def finish(self):
        self._ended = True
        self._available.set()
        if self._workers:
            await asyncio.gather(*self._workers)
        if self._failure:
            raise self._failure

    async def close(self):
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        if self._decode_task is not None:
            self._decode_task.cancel()
            await asyncio.gather(self._decode_task, return_exceptions=True)
        if self._translation_task is not None:
            self._translation_task.cancel()
            await asyncio.gather(self._translation_task, return_exceptions=True)
        self._audio.close()
