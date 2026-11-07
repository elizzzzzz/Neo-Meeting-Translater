"""Local SpeechAnalyzer bridge. No cloud recognition or implicit asset download."""
from __future__ import annotations

import atexit
import asyncio
import base64
import json
import os
import platform
import re
import select
import subprocess
import sys
import threading
import time
from pathlib import Path

APPLE_MODEL = 'Apple SpeechAnalyzer'
LANGUAGES = ('zh', 'ja', 'en')


def bridge_path() -> Path:
    override = os.getenv('MEETING_INTERPRETER_APPLE_SPEECH_HELPER')
    if override:
        return Path(override).expanduser()
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'native' / 'AppleSpeechBridge'
    return Path(__file__).resolve().parents[2] / 'build' / 'native' / 'AppleSpeechBridge'


def unavailable_reason() -> str | None:
    if platform.system() != 'Darwin':
        return 'Apple SpeechAnalyzer 仅适用于 Mac，需要 macOS 26 或更高版本'
    try:
        if int(platform.mac_ver()[0].split('.')[0]) < 26:
            return 'Apple SpeechAnalyzer 需要 macOS 26 或更高版本；可继续使用其他识别引擎'
    except ValueError:
        return '无法确认 macOS 版本，请使用其他识别引擎'
    if not bridge_path().is_file() or not os.access(bridge_path(), os.X_OK):
        return '安装包缺少 Apple 语音组件，请使用新版 App（开发环境请先运行 scripts/build_apple_speech.sh）'
    return None


class AppleSpeechError(RuntimeError):
    """A valid native error reply; the helper remains synchronized and warm."""


class AppleSpeechClient:
    """One resident helper shared by warmed language-specific session decoders."""
    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self._number = 0
        atexit.register(self.close)

    def close(self):
        process, self._process = self._process, None
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
            for pipe in (process.stdin, process.stdout):
                if pipe:
                    pipe.close()

    def request(self, action: str, timeout: float = 4.3, **payload) -> dict:
        reason = unavailable_reason()
        if reason:
            raise RuntimeError(reason)
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self.close()
                self._process = subprocess.Popen([str(bridge_path())], stdin=subprocess.PIPE,
                                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
                os.set_blocking(self._process.stdin.fileno(), False)
            process = self._process
            self._number += 1
            try:
                body = json.dumps(dict(payload, action=action, id=self._number), ensure_ascii=False).encode() + b'\n'
                # A PCM request can exceed a pipe buffer: write in bounded chunks.
                deadline = time.monotonic() + timeout
                view = memoryview(body)
                while view:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select([], [process.stdin], [], remaining)[1]:
                        raise TimeoutError('Apple 语音识别等待超时，请缩短发言间隔或选择单一源语言')
                    try:
                        written = os.write(process.stdin.fileno(), view[:8192])
                    except BlockingIOError:
                        continue
                    view = view[written:]
                output = bytearray()
                while b'\n' not in output:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                        raise TimeoutError('Apple 语音识别超时，本段已放弃；继续处理最新发言')
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        raise RuntimeError('Apple 语音组件已退出，请检查语言资源后重新开始录音')
                    output.extend(chunk)
                    if len(output) > 2 * 1024 * 1024:
                        raise RuntimeError('Apple 语音组件返回数据过大')
                result = json.loads(output.split(b'\n', 1)[0])
                if result.get('id') != self._number:
                    raise RuntimeError('Apple 语音组件响应顺序异常')
                if not result.get('ok'):
                    raise AppleSpeechError(result.get('message') or 'Apple 语音识别失败')
                return result
            except AppleSpeechError:
                raise
            except (OSError, ValueError, TimeoutError, RuntimeError):
                # A separate native process can be stopped safely. Never let a
                # late result from a timed-out job contaminate the next request.
                self.close()
                raise


def inspect_apple_speech(languages=None) -> dict:
    requested = tuple(languages or LANGUAGES)
    reason = unavailable_reason()
    info = {'available': False, 'languages': [], 'message': reason} if reason else {}
    if not reason:
        client = AppleSpeechClient()
        try:
            info = client.request('probe', timeout=8)
        except (OSError, RuntimeError, TimeoutError) as exc:
            info = {'available': False, 'languages': [], 'message': str(exc)}
        finally:
            client.close()
    installed = {row['language'] for row in info.get('languages', []) if row.get('installed')}
    return dict(info, engine='apple', model=APPLE_MODEL, models=[APPLE_MODEL], storage='macOS', path=None,
                installed=bool(info.get('available')) and all(language in installed for language in requested),
                missing=[language for language in requested if language not in installed])


def install_apple_speech(languages=None, timeout=1800) -> dict:
    requested = list(dict.fromkeys(languages or LANGUAGES))
    if not requested or any(language not in LANGUAGES for language in requested):
        raise ValueError('请选择中文、日语或英语语言资源')
    client = AppleSpeechClient()
    try:
        return client.request('install', timeout=timeout, languages=requested)
    except (OSError, RuntimeError, TimeoutError) as exc:
        return {'ok': False, 'message': f'Apple 语言资源准备失败：{exc}'}
    finally:
        client.close()


def choose_candidate(candidates: list[dict], languages) -> dict | None:
    """App-level comparison, not a claim of native multilingual auto-detection.

    Reject unclear competition instead of inventing a source language. The
    user can always lock a language with the toolbar buttons.
    """
    eligible = []
    for candidate in candidates:
        language, text = candidate.get('language'), candidate.get('text', '').strip()
        if language not in languages or not text:
            continue
        if language == 'en' and not re.search(r'[A-Za-z]', text):
            continue
        if language == 'zh' and (not re.search(r'[\u3400-\u9fff]', text) or re.search(r'[\u3040-\u30ff]', text)):
            continue
        if language == 'ja' and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', text):
            continue
        score = candidate.get('confidence', 0)
        if not isinstance(score, (int, float)) or not 0 <= score <= 1:
            continue
        eligible.append((score, candidate))
    eligible.sort(key=lambda item: item[0], reverse=True)
    if not eligible or eligible[0][0] < .30:
        return None
    if len(eligible) > 1 and eligible[0][0] - eligible[1][0] < .08:
        # Do not guess between Chinese and Japanese sharing Han characters.
        return None
    return eligible[0][1]


class AppleSpeechBackend:
    supports_timestamps = True

    def __init__(self, language=None, languages=None, client=None):
        self.language = None if language in (None, '', 'auto') else language
        self.languages = tuple(languages or LANGUAGES)
        self.client = client or AppleSpeechClient()
        self.last_message = ''

    def for_language(self, language):
        return AppleSpeechBackend(language, self.languages, self.client)

    def for_session(self, language, language_pair):
        return AppleSpeechBackend(language, language_pair.split('-') if language_pair else self.languages, self.client)

    async def warmup(self, initial=False):
        inventory = await asyncio.to_thread(self.client.request, 'probe', timeout=8)
        if not inventory.get('available'):
            raise RuntimeError(inventory.get('message') or '这台 Mac 无法使用 Apple SpeechAnalyzer')
        installed = [row['language'] for row in inventory.get('languages', []) if row.get('installed')]
        required = [self.language] if self.language else list(self.languages)
        if initial and not self.language:
            required = [next((language for language in self.languages if language in installed), self.languages[0])]
        missing = [language for language in required if language not in installed]
        if missing:
            names = '、'.join(dict(zh='中文', ja='日语', en='英语')[language] for language in missing)
            raise RuntimeError(f'Apple {names}语言资源未安装，请打开本地设置，点击“准备 Apple 语言资源”')
        await asyncio.to_thread(self.client.request, 'warmup', timeout=120, languages=required)

    async def ensure_language_ready(self, language):
        # Used only at an ordered live boundary. Never load behind active jobs.
        required = [language] if language != 'auto' else list(self.languages)
        await asyncio.to_thread(self.client.request, 'warmup', timeout=4.3, languages=required)

    async def transcribe(self, pcm, sample_rate, start_ms):
        from .asr import ASRResult, ASRWord
        if not pcm:
            return None
        result = await asyncio.to_thread(self.client.request, 'transcribe', timeout=4.3,
                                        audio=base64.b64encode(pcm).decode(), sample_rate=sample_rate,
                                        start_ms=start_ms, language=self.language, languages=list(self.languages))
        candidates = result.get('candidates', [])
        selected = next((row for row in candidates if row.get('language') == self.language and row.get('text', '').strip()), None) if self.language else choose_candidate(candidates, self.languages)
        if selected is None:
            self.last_message = 'Apple 未得到明确识别结果；可用顶部源语言按钮锁定中文、日语或英语后重试'
            return None
        self.last_message = ''
        text = selected['text'].strip()
        end = start_ms + round(len(pcm) * 1000 / 2 / sample_rate)
        words = tuple(ASRWord(row['text'], max(start_ms, row['start_ms']), min(end, row['end_ms']))
                      for row in selected.get('words', []) if row.get('text') and start_ms <= row['start_ms'] <= row['end_ms'] <= end)
        # Partial timestamps must not erase untimed punctuation/text at the
        # pipeline's overlap boundary. Use whole windows when coverage differs.
        if ''.join(word.text for word in words).strip() != text:
            words = ()
        return ASRResult(text, selected['language'], start_ms, end, words)
