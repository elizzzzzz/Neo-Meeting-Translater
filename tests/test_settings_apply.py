"""Live model switching on the same server; no user configuration or models."""
import os
import time
import threading
import pytest
from fastapi.testclient import TestClient
from meeting_interpreter import app as app_module, system
from meeting_interpreter.asr import ASRResult


def wait_state(client, predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        health = client.get('/health').json()
        if predicate(health):
            return health
        time.sleep(.01)
    pytest.fail(f'state never reached: {health}')


@pytest.fixture
def local_models(monkeypatch):
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'local')
    monkeypatch.setenv('MEETING_INTERPRETER_TRANSLATION_BACKEND', 'nllb')
    created = []
    class Speech:
        async def transcribe(self, pcm, sample_rate, start_ms):
            return ASRResult('今天开会。', 'zh', start_ms, start_ms + 600)
    class Translation:
        async def translate(self, text, source_language, target_language): return '会議です。'
    def create_speech():
        engine = os.getenv('MEETING_INTERPRETER_ASR_BACKEND')
        created.append((engine, os.getenv('MEETING_INTERPRETER_MODEL_DIR')))
        if engine == 'sensevoice': raise RuntimeError('测试：资源缺失')
        return Speech()
    monkeypatch.setattr(app_module, 'create_asr_backend', create_speech)
    monkeypatch.setattr(app_module, 'create_translation_backend', Translation)
    return created


def test_save_applies_engine_and_directory_without_restarting_server(tmp_path, local_models):
    with TestClient(app_module.create_app()) as client:
        wait_state(client, lambda h: h['models']['ready'])
        result = client.post('/settings', json={'model_dir': str(tmp_path/'models'), 'asr_engine': 'apple'}).json()
        assert result['saved'] and result['restart_required'] is False
        health = wait_state(client, lambda h: h['models']['ready'] and h['asr']['backend']=='apple')
        assert not health['settings']['applying']
        assert health['settings']['model_dir']==str(tmp_path/'models')
        assert 'Apple' in health['asr']['model']
        assert local_models[-1]==('apple',str(tmp_path/'models'))
        with client.websocket_connect('/ws') as ws:
            ws.receive_json()
            ws.send_json({'type':'config','source_language':'zh','target_language':'ja','language_pair':'zh-ja'})
            assert ws.receive_json()['type']=='configured'


def test_failed_apply_explains_error_and_next_save_recovers(tmp_path, local_models):
    with TestClient(app_module.create_app()) as client:
        wait_state(client, lambda h: h['models']['ready'])
        client.post('/settings', json={'model_dir':str(tmp_path/'bad'),'asr_engine':'sensevoice'})
        failed = wait_state(client,lambda h: h['models']['stage']=='error')
        assert not failed['models']['ready'] and not failed['settings']['restart_required']
        assert '资源缺失' in failed['last_error']
        client.post('/settings',json={'model_dir':str(tmp_path/'good'),'asr_engine':'apple'})
        healthy = wait_state(client,lambda h: h['models']['ready'])
        assert healthy['asr']['backend']=='apple' and healthy['last_error']==''


def test_save_during_warmup_serializes_native_work_and_uses_latest_selection(monkeypatch,tmp_path,local_models):
    entered, release = threading.Event(), threading.Event()
    original = app_module.create_asr_backend
    def create():
        backend = original()
        transcribe = backend.transcribe
        async def slow(*args):
            if not entered.is_set():
                entered.set()
                import asyncio
                await asyncio.to_thread(release.wait, 3)
            return await transcribe(*args)
        backend.transcribe = slow
        return backend
    monkeypatch.setattr(app_module,'create_asr_backend',create)
    with TestClient(app_module.create_app()) as client:
        assert entered.wait(1)
        try:
            first=client.post('/settings',json={'model_dir':str(tmp_path/'first'),'asr_engine':'sensevoice'})
            assert first.status_code==200
            second=client.post('/settings',json={'model_dir':str(tmp_path/'last'),'asr_engine':'apple'})
            assert second.status_code==200
            assert client.get('/health').json()['settings']['applying']
            assert len(local_models)==1
        finally: release.set()
        health=wait_state(client,lambda h: h['models']['ready'] and not h['settings'].get('applying'))
        assert health['asr']['backend']=='apple'
        assert local_models[-1]==('apple',str(tmp_path/'last'))
        assert not any(engine=='sensevoice' for engine,_ in local_models)


def test_live_switch_drains_native_decode_before_releasing_models(monkeypatch,tmp_path,local_models):
    import asyncio
    from test_live_audio import audio
    from starlette.websockets import WebSocketDisconnect
    entered, release = threading.Event(), threading.Event()
    original=app_module.create_asr_backend
    old_calls=0
    def create():
        if entered.is_set(): assert release.is_set(), 'new model overlapped native decode'
        backend=original()
        transcribe=backend.transcribe
        async def slow(*args):
            nonlocal old_calls
            old_calls+=1
            if old_calls==2:
                entered.set()
                await asyncio.to_thread(release.wait,3)
            return await transcribe(*args)
        backend.transcribe=slow
        return backend
    monkeypatch.setattr(app_module,'create_asr_backend',create)
    with TestClient(app_module.create_app()) as client:
        wait_state(client,lambda h:h['models']['ready'])
        with client.websocket_connect('/ws') as ws:
            ws.receive_json()
            ws.send_json({'type':'config','source_language':'zh','target_language':'ja','language_pair':'zh-ja'})
            assert ws.receive_json()['type']=='configured'
            ws.receive_json()
            ws.send_json(audio([2000,-2000]*4800).model_dump(mode='json'))
            assert entered.wait(1)
            try:
                result=client.post('/settings',json={'model_dir':str(tmp_path/'new'),'asr_engine':'apple'})
                assert result.status_code==200
                assert client.get('/health').json()['settings']['applying']
                assert len(local_models)==1
                while True:
                    event=ws.receive_json()
                    if event['type']=='settings_applying':break
                with pytest.raises(WebSocketDisconnect): ws.receive_json()
            finally:release.set()
            health=wait_state(client,lambda h:h['models']['ready'])
            assert health['asr']['backend']=='apple'


def test_loaded_translation_library_uses_new_cache_directory(monkeypatch,tmp_path):
    import sys
    from types import SimpleNamespace
    from meeting_interpreter.translation import NLLBTranslationBackend
    seen=[]
    class Loader:
        @staticmethod
        def from_pretrained(name, **options):
            seen.append(options.get('cache_dir'))
            return SimpleNamespace(to=lambda device:None)
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(float32='float32',float16='float16'))
    monkeypatch.setitem(sys.modules,'transformers',SimpleNamespace(AutoTokenizer=Loader,AutoModelForSeq2SeqLM=Loader))
    monkeypatch.setenv('HUGGINGFACE_HUB_CACHE',str(tmp_path/'new-cache'))
    NLLBTranslationBackend('test-local',device='cpu')._load()
    assert seen==[str(tmp_path/'new-cache')]*2


def test_saved_services_and_translation_model_apply_without_process_restart(monkeypatch,tmp_path,local_models):
    warmed=[]
    class Translation:
        def __init__(self):
            self.selection=(os.getenv('MEETING_INTERPRETER_TRANSLATION_BACKEND'),os.getenv('MEETING_INTERPRETER_LLAMA_MODEL'),os.getenv('MEETING_INTERPRETER_LLAMA_URL'))
        async def translate(self,*args):
            warmed.append(self.selection)
            return '会議です。'
    monkeypatch.setattr(app_module,'create_translation_backend',Translation)
    monkeypatch.setattr(app_module,'inspect_service',lambda provider,url,*args:{'provider':provider,'reachable':True,'models':[{'id':'new-asr'},{'id':'new-translation'}]})
    with TestClient(app_module.create_app()) as client:
        wait_state(client,lambda h:h['models']['ready'])
        response=client.post('/settings',json={'model_dir':str(tmp_path/'models'),'asr_engine':'ollama','asr_model':'new-asr','asr_url':'http://127.0.0.1:11435','translation_backend':'llama','translation_model':'new-translation','translation_url':'http://127.0.0.1:9932'})
        assert response.status_code==200
        health=wait_state(client,lambda h:h['models']['ready'] and h['asr']['backend']=='ollama')
        assert health['asr']['model']=='new-asr'
        assert health['translation']['backend']=='llama' and health['translation']['model']=='new-translation'
        assert warmed[-1]==('llama','new-translation','http://127.0.0.1:9932')
