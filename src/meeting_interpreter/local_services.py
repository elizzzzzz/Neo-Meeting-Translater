"""Loopback-only model services and capability discovery; never loads weights."""
from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request


SERVICE_URLS = {'ollama': 'http://127.0.0.1:11434', 'llama': 'http://127.0.0.1:9931',
                'sglang': 'http://127.0.0.1:30000'}
SERVICE_NAMES = {'ollama': 'Ollama', 'llama': 'llama.app', 'sglang': 'SGLang'}


def local_url(value: str) -> str:
    """Keep recordings/text on the machine, including after HTTP redirects."""
    if not isinstance(value, str) or any(c in value for c in '\r\n\x00'):
        raise ValueError('请填写有效的本机服务地址。')
    parsed = urllib.parse.urlsplit(value)
    try:
        loopback = parsed.hostname == 'localhost' or ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError:
        loopback = False
    if parsed.scheme != 'http' or not loopback or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('模型服务地址必须为本机 HTTP 地址，例如 http://127.0.0.1:9931。')
    if parsed.path.rstrip('/') not in ('', '/v1'):
        raise ValueError('请输入模型服务根地址或 /v1 地址。')
    # Strip /v1 so native probes and OpenAI routes use one canonical root.
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, '', '', '')).rstrip('/')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('本地模型服务不允许重定向。')


def open_local(request, timeout=2):
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    local_url(urllib.parse.urlunsplit((*urllib.parse.urlsplit(url)[:2], '', '', '')))
    # Ignore proxy environment variables even for localhost.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout)


def json_request(url, payload=None, timeout=2):
    request = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                                     headers={'Content-Type': 'application/json'})
    with open_local(request, timeout=timeout) as response:
        return json.loads(response.read(4 * 1024 * 1024).decode())


def model_roles(name: str, capabilities=()) -> tuple[bool, bool]:
    lower = name.lower()
    speech = any(token in lower for token in ('asr', 'whisper', 'sensevoice', 'parakeet'))
    embedding = any(token in lower for token in ('embed', 'rerank'))
    # Unknown models cannot be assumed to accept audio. Native Ollama reports
    # audio explicitly; llama.cpp's model catalogue often has only names.
    asr = speech or 'audio' in capabilities
    translation = not speech and not embedding and (not capabilities or 'completion' in capabilities)
    return asr, translation


def inspect_service(provider: str, base_url: str | None = None, timeout: float = 1.2) -> dict:
    if provider not in SERVICE_URLS:
        raise ValueError('请选择 Ollama、llama.app 或 SGLang。')
    root = local_url(base_url or SERVICE_URLS[provider])
    result = {'provider': provider, 'name': SERVICE_NAMES[provider], 'url': root,
              'reachable': False, 'models': [], 'message': ''}
    try:
        payload = json_request(root + ('/api/tags' if provider == 'ollama' else '/v1/models'), timeout=timeout)
        models = payload.get('models', []) if provider == 'ollama' else payload.get('data', [])
        result['reachable'] = True
        if provider == 'llama':
            try:
                props = json_request(root + '/props', timeout=timeout)
                maximum = props.get('max_instances')
                if isinstance(maximum, int) and maximum > 0:
                    result['max_loaded_models'] = maximum
            except (OSError, ValueError, urllib.error.URLError):
                pass
        for item in models:
            name = str(item.get('name') or item.get('id') or '')
            if not name:
                continue
            capabilities = item.get('capabilities') or []
            asr, translation = model_roles(name, capabilities)
            status = item.get('status')
            if isinstance(status, dict):
                status = status.get('value')
            result['models'].append({'id': name, 'asr': asr, 'translation': translation,
                                      'capabilities': capabilities, 'status': status or 'available'})
        result['message'] = '已连接' if result['models'] else '服务已连接，尚未配置模型；请在服务应用中添加模型后刷新。'
    except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
        result['message'] = f'{SERVICE_NAMES[provider]} 未连接：{exc}'
    return result


def match_service_model(selected: str, models: list[dict]) -> str:
    ids = [item['id'] for item in models]
    if selected in ids or '/' in selected or not selected:
        return selected
    matches = [name for name in ids if name.rsplit('/', 1)[-1] == selected]
    return matches[0] if len(matches) == 1 else selected
