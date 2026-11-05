import base64
import io
import json
import wave

import pytest

from meeting_interpreter import local_services, system
from meeting_interpreter.asr import ServiceASRBackend, parse_service_transcript, create_asr_backend
from meeting_interpreter.translation import LlamaTranslationBackend, create_translation_backend


@pytest.mark.parametrize('url', ['https://cloud.example/v1', 'http://192.168.1.2:8000', 'http://localhost.evil/v1', 'http://user@localhost:8000', 'http://127.0.0.1:1234/?x=1'])
def test_only_loopback_services_are_allowed(url):
    with pytest.raises(ValueError): local_services.local_url(url)


def test_service_discovery_filters_asr_from_translation_without_inference(monkeypatch):
    calls = []
    def request(url, **kwargs):
        calls.append(url)
        return {'models': [{'name': 'frozenlab/qwen3-asr:1.7b', 'capabilities': ['completion', 'audio']},
                           {'name': 'translategemma:4b', 'capabilities': ['completion']},
                           {'name': 'nomic-embed', 'capabilities': ['embedding']}]}
    monkeypatch.setattr(local_services, 'json_request', request)
    result = local_services.inspect_service('ollama')
    assert result['reachable']
    assert [m['id'] for m in result['models'] if m['asr']] == ['frozenlab/qwen3-asr:1.7b']
    assert [m['id'] for m in result['models'] if m['translation']] == ['translategemma:4b']
    assert calls == ['http://127.0.0.1:11434/api/tags']


def test_llama_empty_catalogue_is_connected_but_not_ready(monkeypatch):
    monkeypatch.setattr(local_services, 'json_request', lambda *a, **k: {'data': []})
    result = local_services.inspect_service('llama', 'http://localhost:9931/v1')
    assert result['reachable'] and result['models'] == []
    assert '尚未配置模型' in result['message']
    assert result['url'] == 'http://localhost:9931'


def test_llama_model_capacity_is_reported_without_loading_models(monkeypatch):
    monkeypatch.setattr(local_services, 'json_request', lambda url, **kwargs:
                        {'max_instances': 1} if url.endswith('/props') else {'data': [{'id': 'qwen3-asr'}, {'id': 'translate-local'}]})
    result = local_services.inspect_service('llama')
    assert result['max_loaded_models'] == 1
    assert result['models'][0]['asr'] and result['models'][1]['translation']


def test_single_slot_llama_service_does_not_claim_two_hot_models(monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from meeting_interpreter import app as application
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'local')
    monkeypatch.setenv('MEETING_INTERPRETER_ASR_BACKEND', 'llama')
    monkeypatch.setenv('MEETING_INTERPRETER_SERVICE_ASR_MODEL', 'qwen3-asr')
    monkeypatch.setenv('MEETING_INTERPRETER_ASR_URL', 'http://127.0.0.1:9931')
    monkeypatch.setenv('MEETING_INTERPRETER_TRANSLATION_BACKEND', 'llama')
    monkeypatch.setenv('MEETING_INTERPRETER_LLAMA_MODEL', 'translate-local')
    monkeypatch.setenv('MEETING_INTERPRETER_LLAMA_URL', 'http://127.0.0.1:9931')
    monkeypatch.setattr(application, 'inspect_service', lambda *a, **k: {'reachable':True, 'max_loaded_models':1,
        'models':[{'id':'qwen3-asr'},{'id':'translate-local'}]})
    def should_not_load(): raise AssertionError('incompatible model pair must not load')
    monkeypatch.setattr(application, 'create_asr_backend', should_not_load)
    with TestClient(application.create_app()) as client:
        for _ in range(20):
            health = client.get('/health').json()
            if health['models']['stage'] == 'error': break
            time.sleep(.01)
        assert health['models']['stage'] == 'error'
        assert not health['models']['ready']
        assert '仅能驻留 1 个模型' in health['models']['message']


@pytest.mark.parametrize('provider', ['ollama', 'llama'])
@pytest.mark.asyncio
async def test_qwen_audio_request_and_detected_language(provider, monkeypatch):
    captured = []
    def request(url, payload, **kwargs):
        captured.append((url, payload))
        text = 'language Japanese<asr_text>会議を始めます。'
        return {'message': {'content': text}} if provider == 'ollama' else {'choices': [{'message': {'content': text}}]}
    monkeypatch.setattr('meeting_interpreter.asr.json_request', request)
    backend = ServiceASRBackend(provider, 'qwen3-asr:1.7b', local_services.SERVICE_URLS[provider])
    result = await backend.transcribe(b'\x01\x02' * 16000, 16000, 1000)
    assert result.text == '会議を始めます。' and result.language == 'ja'
    assert (result.start_ms, result.end_ms) == (1000, 2000)
    url, payload = captured[0]
    assert payload['stream'] is False
    message = payload['messages'][0]
    audio = message['images'][0] if provider == 'ollama' else message['content'][1]['input_audio']['data']
    with wave.open(io.BytesIO(base64.b64decode(audio))) as wav:
        assert wav.getframerate() == 16000 and wav.getnchannels() == 1
        assert wav.readframes(16000) == b'\x01\x02' * 16000
    assert backend.for_language('zh').language == 'zh' and backend.language is None


@pytest.mark.parametrize('text,expected', [('language Chinese<asr_text>会议开始。', ('会议开始。', 'zh')), ('language English<asr_text>Hello.', ('Hello.', 'en')), ('{"text":"会議です。","language":"Japanese"}', ('会議です。', 'ja'))])
def test_parse_detected_source_language(text, expected):
    assert parse_service_transcript(text) == expected


def test_independent_model_selections_survive_restart_and_preserve_other_settings(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    config.write_text('MEETING_INTERPRETER_OLLAMA_MODEL=old-model\nMEETING_INTERPRETER_SPEAKER_MODE=none\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    result = system.save_model_directory(str(tmp_path / 'models'), 'ollama', {
        'asr_model': 'frozenlab/qwen3-asr:1.7b', 'asr_url': 'http://127.0.0.1:11434',
        'translation_backend': 'llama', 'translation_model': 'translate-local', 'translation_url': 'http://127.0.0.1:9931/v1'})
    assert result['restart_required']
    assert 'MEETING_INTERPRETER_OLLAMA_MODEL=old-model' in config.read_text()
    assert 'MEETING_INTERPRETER_SPEAKER_MODE=none' in config.read_text()
    settings = system.model_settings()
    assert settings['asr_engine'] == 'ollama' and settings['asr_model'] == 'frozenlab/qwen3-asr:1.7b'
    assert settings['translation_backend'] == 'llama' and settings['translation_model'] == 'translate-local'
    assert settings['translation_url'] == 'http://127.0.0.1:9931'


def test_invalid_service_settings_never_partially_overwrite_config(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    config.write_text('UNCHANGED=yes\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    with pytest.raises(ValueError):
        system.save_model_directory(str(tmp_path / 'models'), 'llama', {'asr_model': 'qwen3-asr', 'asr_url': 'http://cloud.example', 'translation_backend': 'ollama'})
    assert config.read_text() == 'UNCHANGED=yes\n'


def test_selected_factories_use_separate_services(monkeypatch):
    monkeypatch.setenv('MEETING_INTERPRETER_ASR_BACKEND', 'ollama')
    monkeypatch.setenv('MEETING_INTERPRETER_SERVICE_ASR_MODEL', 'qwen3-asr:1.7b')
    monkeypatch.setenv('MEETING_INTERPRETER_TRANSLATION_BACKEND', 'llama')
    monkeypatch.setenv('MEETING_INTERPRETER_LLAMA_MODEL', 'translate-local')
    assert isinstance(create_asr_backend(), ServiceASRBackend)
    assert isinstance(create_translation_backend(), LlamaTranslationBackend)


@pytest.mark.asyncio
async def test_llama_streaming_translation_accumulates_sse_and_closes_response(monkeypatch):
    closed, requests = [], []
    class Response(io.BytesIO):
        def close(self):
            closed.append(True)
            super().close()
    def open_request(request, **kwargs):
        requests.append((request.full_url, json.loads(request.data)))
        return Response(('data: '+json.dumps({'choices': [{'delta': {'content': '会議'}}]})+'\n\n'
                         'data: '+json.dumps({'choices': [{'delta': {'content': 'です。'}, 'finish_reason': 'stop'}]})+'\n\n').encode())
    monkeypatch.setattr('meeting_interpreter.translation.open_local', open_request)
    result = [text async for text in LlamaTranslationBackend('translate-local').stream_translate('这是会议。', 'zh', 'ja')]
    assert result == ['会議', '会議です。'] and closed
    assert requests[0][0] == 'http://127.0.0.1:9931/v1/chat/completions'
    assert requests[0][1]['model'] == 'translate-local' and requests[0][1]['stream']


def test_service_short_name_only_resolves_when_unambiguous():
    models = [{'id': 'vendor/translategemma:4b'}, {'id': 'vendor/qwen3-asr:1.7b'}]
    assert local_services.match_service_model('translategemma:4b', models) == 'vendor/translategemma:4b'
    assert local_services.match_service_model('other/translategemma:4b', models) == 'other/translategemma:4b'
    assert local_services.match_service_model('translategemma:4b', models + [{'id':'other/translategemma:4b'}]) == 'translategemma:4b'
