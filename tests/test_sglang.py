"""SGLang uses loopback HTTP only; these tests never load real model weights."""
import io
import json
import os
import urllib.error

import pytest
from fastapi.testclient import TestClient

from meeting_interpreter import app as application, local_services, system
from meeting_interpreter.asr import ASRResult
from meeting_interpreter.translation import create_translation_backend


def configure(monkeypatch, model='meeting-translation'):
    monkeypatch.setenv('MEETING_INTERPRETER_TRANSLATION_BACKEND', 'sglang')
    monkeypatch.setenv('MEETING_INTERPRETER_SGLANG_MODEL', model)
    monkeypatch.setenv('MEETING_INTERPRETER_SGLANG_URL', 'http://127.0.0.1:30001/v1')
    # Switching away from llama.app must not reuse its address or model.
    monkeypatch.setenv('MEETING_INTERPRETER_LLAMA_MODEL', 'wrong-old-model')
    monkeypatch.setenv('MEETING_INTERPRETER_LLAMA_URL', 'http://127.0.0.1:9931')


def test_sglang_discovers_served_models_without_loading_or_probing_llama_props(monkeypatch):
    calls = []
    def request(url, **kwargs):
        calls.append(url)
        return {'data': [{'id': 'meeting-translation'}, {'id': 'bge-embed'}]}
    monkeypatch.setattr(local_services, 'json_request', request)
    result = local_services.inspect_service('sglang', 'http://localhost:30000/v1')
    assert result['provider'] == 'sglang' and result['name'] == 'SGLang'
    assert result['reachable']
    assert [m['id'] for m in result['models'] if m['translation']] == ['meeting-translation']
    assert calls == ['http://localhost:30000/v1/models']


def test_sglang_uses_its_own_saved_model_and_address_after_restart(monkeypatch, tmp_path):
    configure(monkeypatch)
    result = system.save_model_directory(str(tmp_path/'disconnected-models'), 'apple', {
        'translation_backend': 'sglang', 'translation_model': 'local-translation',
        'translation_url': 'http://localhost:30002/v1'})
    assert result['saved'] and not result['restart_required']
    monkeypatch.setenv('MEETING_INTERPRETER_SGLANG_MODEL', 'stale-environment-model')
    monkeypatch.setenv('MEETING_INTERPRETER_SGLANG_URL', 'http://localhost:1')
    monkeypatch.setattr(system, 'inspect_service', lambda *a, **kw: {'models': []})
    system.load_user_config()
    settings = system.model_settings()
    assert settings['translation_backend'] == 'sglang'
    assert settings['translation_model'] == 'local-translation'
    assert settings['translation_url'] == 'http://localhost:30002'
    backend = create_translation_backend()
    assert backend.model == 'local-translation' and backend.base_url == 'http://localhost:30002'


def test_sglang_rejects_remote_addresses_without_changing_saved_settings(monkeypatch, tmp_path):
    config = system.user_config_path()
    config.write_text('UNCHANGED=yes\n')
    with pytest.raises(ValueError, match='本机'):
        system.save_model_directory(str(tmp_path/'models'), 'apple', {
            'translation_backend': 'sglang', 'translation_url': 'http://192.168.1.10:30000',
            'translation_model': 'translator'})
    assert config.read_text() == 'UNCHANGED=yes\n'


@pytest.mark.asyncio
@pytest.mark.parametrize('source,target', [('zh','ja'), ('ja','zh'), ('zh','en'), ('en','zh'), ('en','ja'), ('ja','en')])
async def test_sglang_translates_each_direction_through_the_selected_model(monkeypatch, source, target):
    configure(monkeypatch)
    requests = []
    def request(req, **kwargs):
        requests.append((req.full_url, json.loads(req.data)))
        return io.BytesIO(json.dumps({'choices':[{'message':{'content':'本地翻译'}}]}).encode())
    monkeypatch.setattr('meeting_interpreter.translation.open_local', request)
    assert await create_translation_backend().translate('meeting utterance', source, target) == '本地翻译'
    url, payload = requests[0]
    assert url == 'http://127.0.0.1:30001/v1/chat/completions'
    assert payload['model'] == 'meeting-translation'
    assert payload['stream'] is False and payload['temperature'] == 0
    assert payload['chat_template_kwargs']['enable_thinking'] is False
    assert 'meeting utterance' in payload['messages'][0]['content']


@pytest.mark.asyncio
async def test_sglang_source_correction_stays_local_without_calling_ollama_generate(monkeypatch):
    configure(monkeypatch)
    backend = create_translation_backend()
    assert await backend.correct_source('会议。', '', 'zh') == '会议。'


@pytest.mark.asyncio
async def test_sglang_streams_incremental_translation_and_closes_the_connection(monkeypatch):
    configure(monkeypatch)
    replies = []
    class Response(io.BytesIO):
        def close(self):
            replies.append('closed')
            super().close()
    def request(req, **kwargs):
        assert json.loads(req.data)['stream'] is True
        return Response(('data: '+json.dumps({'choices':[{'delta':{'content':'会議'}}]})+'\n\n'
                         'data: '+json.dumps({'choices':[{'delta':{'content':'です。'},'finish_reason':'stop'}]})+'\n\n'
                         'data: [DONE]\n\n').encode())
    monkeypatch.setattr('meeting_interpreter.translation.open_local', request)
    result = [part async for part in create_translation_backend().stream_translate('会议。','zh','ja')]
    assert result == ['会議','会議です。'] and replies == ['closed']


@pytest.mark.asyncio
async def test_sglang_reports_its_own_name_on_incomplete_translation(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr('meeting_interpreter.translation.open_local', lambda *a, **kw: io.BytesIO(b'data: [DONE]\n\n'))
    with pytest.raises(RuntimeError, match='SGLang'):
        _ = [part async for part in create_translation_backend().stream_translate('会议。','zh','ja')]


@pytest.mark.asyncio
async def test_sglang_does_not_claim_token_limit_truncation_as_complete_translation(monkeypatch):
    configure(monkeypatch)
    body = {'choices':[{'delta':{'content':'未完成'},'finish_reason':'length'}]}
    monkeypatch.setattr('meeting_interpreter.translation.open_local', lambda *a, **kw:
                        io.BytesIO(('data: '+json.dumps(body)+'\n\n').encode()))
    with pytest.raises(RuntimeError, match='SGLang.*(截断|完整)'):
        _ = [part async for part in create_translation_backend().stream_translate('会议。','zh','ja')]


@pytest.mark.asyncio
async def test_sglang_connection_timeout_identifies_the_selected_service(monkeypatch):
    configure(monkeypatch)
    def offline(*args, **kwargs): raise TimeoutError('simulated timeout')
    monkeypatch.setattr('meeting_interpreter.translation.open_local', offline)
    with pytest.raises(RuntimeError, match='SGLang.*超时'):
        _ = [part async for part in create_translation_backend().stream_translate('会议。','zh','ja')]


def test_sglang_live_apply_warms_selected_model_and_health_detects_disconnect(monkeypatch, tmp_path):
    from test_settings_apply import wait_state
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'local')
    monkeypatch.setenv('MEETING_INTERPRETER_TRANSLATION_BACKEND', 'nllb')
    state, warmed = {'reachable': True}, []
    class Speech:
        async def transcribe(self, *args): return ASRResult('测试。', 'zh', 0, 600)
    class Translation:
        async def translate(self, *args):
            warmed.append((os.getenv('MEETING_INTERPRETER_TRANSLATION_BACKEND'),
                           os.getenv('MEETING_INTERPRETER_SGLANG_MODEL'),
                           os.getenv('MEETING_INTERPRETER_SGLANG_URL')))
            return 'テスト。'
    def inspect(provider, url, *args):
        assert provider == 'sglang' and url == 'http://127.0.0.1:30003'
        return {'provider':provider,'name':'SGLang','reachable':state['reachable'],
                'models':[{'id':'served-translation'}] if state['reachable'] else []}
    monkeypatch.setattr(application, 'create_asr_backend', Speech)
    monkeypatch.setattr(application, 'create_translation_backend', Translation)
    monkeypatch.setattr(application, 'inspect_service', inspect)
    monkeypatch.setattr(system, 'inspect_service', inspect)
    with TestClient(application.create_app()) as client:
        wait_state(client, lambda h: h['models']['ready'])
        response = client.post('/settings', json={'model_dir':str(tmp_path/'models'),
            'asr_engine':'apple','translation_backend':'sglang','translation_model':'served-translation',
            'translation_url':'http://127.0.0.1:30003/v1'})
        assert response.status_code == 200 and response.json()['restart_required'] is False
        health = wait_state(client, lambda h: h['models']['ready'] and h['translation']['backend']=='sglang')
        assert health['translation']['model'] == 'served-translation'
        assert health['translation']['service']['name'] == 'SGLang'
        assert warmed[-1] == ('sglang','served-translation','http://127.0.0.1:30003')
        state['reachable'] = False
        health = client.get('/health').json()
        assert not health['models']['ready'] and health['translation']['status'] == 'offline'


def test_sglang_model_is_required_before_warmup(monkeypatch):
    configure(monkeypatch, '')
    with pytest.raises(ValueError, match='SGLang'):
        create_translation_backend()
