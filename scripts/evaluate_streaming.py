#!/usr/bin/env python3
"""Replay a referenced natural recording at wall-clock speed through local workers.

Manifest: {audio: absolute PCM16 WAV, language: zh|ja, target: ja|zh,
source: provenance, reference_kind: human_subtitles|..., utterances:
[{start: seconds, end: seconds, text: ...}]}. Never uploads or copies audio.
Subtitle timing is line-level: latency uses exact suffix matches and reports its
coverage. It is an estimate, not word-aligned ground truth or a microphone test.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import json
import os
import resource
import statistics
import time
import unicodedata
import wave
from pathlib import Path

from meeting_interpreter.asr import SenseVoiceBackend, MLXWhisperBackend
from meeting_interpreter.models import AudioEvent
from meeting_interpreter.pipeline import Pipeline
from meeting_interpreter.streaming import LiveSession
from meeting_interpreter.translation import OllamaTranslationBackend


class WebSocketReplay:
    """Exercise the packaged application's actual audio protocol."""
    @classmethod
    async def connect(cls, url, language, target, send):
        import websockets
        from urllib.parse import urlsplit
        if urlsplit(url).hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise ValueError('评测音频只能发送给本机的 App')
        self = cls()
        self.ws = await websockets.connect(url, max_size=5_000_000)
        self.send = send
        self.stats = {}
        await self.ws.send(json.dumps(dict(type='config', source_language=language, target_language=target, speaker_mode='none')))
        while True:
            event = json.loads(await self.ws.recv())
            if event['type'] == 'error': raise RuntimeError(event['message'])
            if event['type'] == 'configured': break
        return self

    def start(self):
        self.task = asyncio.create_task(self.receive())

    async def receive(self):
        async for message in self.ws:
            event = json.loads(message)
            for key in ('received_samples', 'processed_samples', 'queued_audio_ms', 'dropped_samples', 'pending_translations', 'rejected_samples'):
                if key in event: self.stats[key] = event[key]
            await self.send(event)
            if event['type'] == 'session_finished': return
        raise RuntimeError('录音收尾前连接已断开')

    async def feed(self, event):
        await self.ws.send(event.model_dump_json())

    async def finish(self):
        await self.ws.send(json.dumps({'type':'finish'}))
        await self.task

    def metrics(self): return self.stats

    async def close(self):
        if hasattr(self, 'task'):
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        await self.ws.close()


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).lower()
                   if unicodedata.category(c)[0] not in 'PZSC')


def character_errors(reference, hypothesis):
    # Exact Levenshtein counts, including insertions: CER can exceed 100%.
    row = [(j, 0, j, 0) for j in range(len(hypothesis) + 1)]
    for i, x in enumerate(reference, 1):
        new = [(i, i, 0, 0)]
        for j, y in enumerate(hypothesis, 1):
            if x == y:
                new.append(row[j - 1])
            else:
                choices = [(row[j][0]+1, row[j][1]+1, row[j][2], row[j][3]),
                           (new[-1][0]+1, new[-1][1], new[-1][2]+1, new[-1][3]),
                           (row[j-1][0]+1, row[j-1][1], row[j-1][2], row[j-1][3]+1)]
                new.append(min(choices, key=lambda v: v[0]))
        row = new
    errors, deletions, insertions, substitutions = row[-1]
    return dict(cer=errors / max(1, len(reference)), reference_characters=len(reference),
                deletions=deletions, insertions=insertions, substitutions=substitutions)


def summary(values):
    ordered = sorted(values)
    return None if not ordered else dict(n=len(ordered), p50_ms=round(statistics.median(ordered)),
        p95_ms=round(ordered[min(len(ordered)-1, int(len(ordered)*.95))]), max_ms=round(max(ordered)))


def score_timeline(timeline, utterances, canonical=lambda text: text):
    source_revisions, latest, latencies, translation_extra, errors = {}, {}, {}, [], []
    translation_first, stable_lines = {}, {}
    suffixes = [normalize(canonical(u['text']))[-12:] for u in utterances]
    for event in timeline:
        elapsed = event['wall_ms']
        if event['type'] in ('error', 'capture_paused'): errors.append(event)
        if event['type'] != 'caption': continue
        key = event['segment_id']
        source_changed = latest.get(key, {}).get('original_text') != event['original_text']
        latest[key] = event
        source_revisions.setdefault((key,event['original_text']), elapsed)
        if event.get('translation_source_text'):
            source_at = source_revisions.get((key,event['translation_source_text']))
            if source_at is not None:
                translation_first.setdefault((key,event['translation_source_text']), elapsed-source_at)
                if event.get('translation_complete', True):
                    translation_extra.append(elapsed-source_at)
        if not source_changed: continue
        text = normalize(canonical(''.join(c['original_text'] for c in latest.values())))
        for i, (u, suffix) in enumerate(zip(utterances, suffixes)):
            if len(suffix) >= 8:
                if suffix in text:
                    latencies.setdefault(i, elapsed-u['end']*1000)
                    stable_lines.setdefault(i, elapsed-u['end']*1000)
                else:
                    stable_lines.pop(i, None)
    return dict(latest=latest, latencies=latencies, stable_lines=stable_lines,
                translation_extra=translation_extra, translation_first=translation_first,
                errors=errors)


async def run(args):
    manifest = json.loads(Path(args.manifest).read_text())
    with wave.open(manifest['audio']) as f:
        assert f.getframerate() == 16000 and f.getnchannels() == 1 and f.getsampwidth() == 2
        pcm = f.readframes(f.getnframes())
    if args.seconds:
        cutoff = max(u['end'] for u in manifest['utterances'] if u['end'] <= args.seconds)
        pcm = pcm[:round(cutoff * 32000)]
    duration = len(pcm)/32000
    utterances = [u for u in manifest['utterances'] if u['start'] < duration and u['start'] >= 0]
    language = manifest['language']
    canonical = lambda text: text
    if args.simplify_chinese and language == 'zh':
        from opencc import OpenCC
        canonical = OpenCC('t2s').convert
    if not args.ws_url:
        if args.engine == 'sensevoice':
            asr = SenseVoiceBackend(args.model, language)
            await asyncio.to_thread(asr.warmup)
        else:
            asr = MLXWhisperBackend(args.model, language)
            await asr.transcribe(bytes(32000), 16000, 0)
        translator = OllamaTranslationBackend(timeout=180) if args.translate else None
        if translator:
            await translator.translate('会议测试' if language == 'zh' else '会議のテスト', language, manifest['target'])
        pipeline = Pipeline(mode='local', source_language=language,
            target_language=manifest['target'] if translator else language,
            asr_backend=asr, translator_backend=translator, translate_inline=False)
    # The live consumer only records events. Text normalization and reference
    # matching happen after playback, so the scorer cannot delay socket reads.
    timeline, feed_lateness = [], []
    started = time.perf_counter()
    async def send(event):
        timeline.append({**event, 'wall_ms': round((time.perf_counter()-started)*1000, 2)})
    print(f'Preparing local session for {duration:.2f}s wall-clock replay', flush=True)
    configured_at = time.perf_counter()
    if args.ws_url:
        session = await WebSocketReplay.connect(args.ws_url, language, manifest['target'] if args.translate else language, send)
    else:
        session = LiveSession(pipeline, send)
    configuration_seconds = time.perf_counter()-configured_at
    print(f'Session prepared in {configuration_seconds:.2f}s; starting replay', flush=True)
    started = time.perf_counter()
    session.start()
    try:
        frame_bytes = 6400  # 200ms, paced by a monotonic deadline.
        next_progress = 30
        for offset in range(0, len(pcm), frame_bytes):
            chunk = pcm[offset:offset+frame_bytes]
            due = started+(offset+len(chunk))/32000
            await asyncio.sleep(max(0, due-time.perf_counter()))
            event = AudioEvent(session_id='evaluation', source='file', audio_base64=base64.b64encode(chunk).decode())
            if args.ws_url: await session.feed(event)
            else: session.feed(event)
            feed_lateness.append(max(0, (time.perf_counter()-due)*1000))
            if offset / 32000 >= next_progress:
                print(f'{next_progress}s: {session.metrics()}', flush=True)
                next_progress += 30
        await session.finish()
        elapsed = time.perf_counter()-started
        scored = score_timeline(timeline, utterances, canonical)
        latest = scored['latest']
        latencies, stable_lines = scored['latencies'], scored['stable_lines']
        translation_extra, translation_first = scored['translation_extra'], scored['translation_first']
        errors = scored['errors']
        max_queued = max((e.get('queued_audio_ms', 0) for e in timeline), default=0)
        reference = ''.join(u['text'] for u in utterances)
        hypothesis = ''.join(c['original_text'] for c in latest.values())
        report = dict(engine=args.engine, model=args.model, provenance=manifest.get('source'),
            reference_kind=manifest.get('reference_kind'), audio_seconds=duration,
            session_configuration_seconds=round(configuration_seconds,3),
            elapsed_seconds=round(elapsed,3), drain_seconds=round(elapsed-duration,3),
            wall_clock_paced=True, scoring_after_playback=True, feed_lateness=summary(feed_lateness), translation_enabled=args.translate, native_websocket_replay=bool(args.ws_url),
            normalization='NFKC, lowercase, punctuation/space removal; optional Chinese t2s; no numeral conversion',
            **character_errors(normalize(canonical(reference)),normalize(canonical(hypothesis))),
            raw_script_cer=character_errors(normalize(reference),normalize(hypothesis))['cer'],
            chinese_script_normalized=args.simplify_chinese and language == 'zh',
            reference_timing_overrun_ms=round(max(0, max(u['end'] for u in utterances)-duration)*1000),
            matched_subtitle_lines=len(latencies), eligible_subtitle_lines=sum(len(normalize(canonical(u['text'])))>=8 for u in utterances),
            source_line_end_latency_estimate=summary(list(latencies.values())),
            source_line_stable_latency_estimate=summary(list(stable_lines.values())),
            translation_after_source_latency=summary(translation_extra),
            translation_first_visible_after_source=summary(list(translation_first.values())), max_queued_audio_ms=max_queued,
            **session.metrics(), peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            peak_rss_scope='replay_client_only' if args.ws_url else 'ASR_and_replay_excludes_Ollama',
            load_average=os.getloadavg(), errors=errors, reference=reference, hypothesis=hypothesis,
            captions=list(latest.values()))
        Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
        Path(args.output).with_suffix('.timeline.json').write_text(json.dumps(timeline,ensure_ascii=False))
        print(json.dumps({k:v for k,v in report.items() if k not in ('captions','reference','hypothesis')},ensure_ascii=False,indent=2),flush=True)
    finally:
        await session.close()


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest');p.add_argument('--model',required=True)
    p.add_argument('--ws-url',help='Replay through an already warm native app, e.g. ws://127.0.0.1:8000/ws; needs websockets')
    p.add_argument('--engine',choices=['sensevoice','whisper'],default='sensevoice')
    p.add_argument('--translate',action='store_true');p.add_argument('--seconds',type=float)
    p.add_argument('--simplify-chinese',action='store_true',help='Requires optional opencc-python-reimplemented; reports raw CER too')
    p.add_argument('--output',required=True)
    asyncio.run(run(p.parse_args()))
