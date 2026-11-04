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
    def __init__(self, pipeline: Pipeline, send: Callable[[dict], Awaitable[None]], max_bytes: int = 512 * 1024 * 1024):
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
        if self._records and self._records[-1][0] == 'audio':
            kind, previous, start, size = self._records[-1]
            if start + size == offset and size + len(raw) <= event.sample_rate * 2 * .8:
                self._records[-1] = (kind, previous, start, size + len(raw))
            else:
                self._records.append(('audio', metadata, offset, len(raw)))
        else:
            self._records.append(('audio', metadata, offset, len(raw)))
        self.received_samples += len(raw) // 2
        self._available.set()

    def change_speaker(self):
        self._records.append(('speaker', None, 0, 0))
        self._available.set()

    def metrics(self):
        return {'received_samples': self.received_samples, 'processed_samples': self.processed_samples,
                'queued_audio_ms': round((self.received_samples - self.processed_samples) * 1000 / self.sample_rate),
                'dropped_samples': 0, 'pending_translations': len(self._pending)}

    async def _publish(self, caption: CaptionEvent):
        key = (caption.session_id, caption.segment_id)
        previous = self._captions.get(key)
        if previous:
            if previous.original_text == caption.original_text:
                caption = caption.model_copy(update={'translated_text': previous.translated_text,
                                                      'is_final': previous.is_final})
            elif not caption.translated_text:
                caption = caption.model_copy(update={'translated_text': previous.translated_text})
        self._captions[key] = caption
        await self.send({**caption.model_dump(mode='json'), 'queued_audio_ms': self.metrics()['queued_audio_ms']})
        if self.pipeline.translator is not None and caption.source_language != caption.target_language and not caption.is_final:
            self._pending[key] = caption
            self._translate_available.set()

    async def _recognize(self):
        try:
            while True:
                if not self._records:
                    if self._ended:
                        break
                    self._available.clear()
                    await self._available.wait()
                    continue
                kind, event, offset, size = self._records.popleft()
                if kind == 'speaker':
                    async for caption in self.pipeline.change_speaker():
                        await self._publish(caption)
                    continue
                self._audio.seek(offset)
                raw = self._audio.read(size)
                event = event.model_copy(update={'audio_base64': base64.b64encode(raw).decode()})
                started = time.perf_counter()
                defer_partial = bool(self._records and self._records[0][0] == "audio")
                async for caption in self.pipeline.process_audio(event, defer_partial=defer_partial):
                    await self._publish(caption)
                self.processed_samples += size // 2
                await self.send({'type': 'audio_status', **self.pipeline.audio_status, **self.metrics(),
                                 'recognition_work_ms': round((time.perf_counter() - started) * 1000)})
            async for caption in self.pipeline.flush_audio():
                await self._publish(caption)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._failure = exc
            await self.send({'type': 'capture_paused', 'message': f'语音识别失败，已停止收音：{exc}', **self.metrics()})
        finally:
            self._recognition_done = True
            self._translate_available.set()

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
            started = time.perf_counter()
            await self.send({'type': 'translation_status', 'state': 'processing', 'pending_translations': len(self._pending)})
            async def publish_translation(text, complete):
                latest = self._captions[key]
                current = latest.original_text == caption.original_text
                updated = latest.model_copy(update={'translated_text': text, 'is_final': complete and current})
                self._captions[key] = updated
                if complete and current:
                    self._pending.pop(key, None)
                await self.send({**updated.model_dump(mode='json'),
                    'translation_work_ms': round((time.perf_counter() - started) * 1000),
                    'translation_complete': complete, 'translated_through_ms': caption.end_ms,
                    'translation_source_text': caption.original_text})

            try:
                stream = getattr(self.pipeline.translator, 'stream_translate', None)
                if stream is not None:
                    text = ''
                    published_at = 0.0
                    async for text in stream(caption.original_text, caption.source_language, caption.target_language):
                        now = time.perf_counter()
                        if text and now - published_at >= .1:
                            await publish_translation(text, False)
                            published_at = now
                    if not text:
                        raise RuntimeError('翻译模型返回了空翻译')
                else:
                    text = await self.pipeline.translator.translate(caption.original_text, caption.source_language, caption.target_language)
                await publish_translation(text, True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self.send({'type': 'translation_status', 'state': 'error', 'message': str(exc)})
                await self.send({'type': 'error', 'message': f'翻译失败，原文已保留：{exc}'})
                continue
            await self.send({'type': 'translation_status', 'state': 'running',
                             'last_response_ms': round((time.perf_counter() - started) * 1000),
                             'pending_translations': len(self._pending)})

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
        self._audio.close()
