"""Apple adapter control flow, without downloading system language assets."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from meeting_interpreter import apple_speech, system
from meeting_interpreter.apple_speech import AppleSpeechBackend, AppleSpeechClient, choose_candidate
from meeting_interpreter.asr import create_asr_backend
from meeting_interpreter.pipeline import Pipeline
from meeting_interpreter.streaming import LiveSession
from test_live_audio import audio


class NativeFixture:
    def __init__(self, installed=('zh', 'ja', 'en')):
        self.installed = installed
        self.calls = []
    def close(self): pass
    def request(self, action, **payload):
        self.calls.append((action, payload))
        if action == 'probe':
            return {'ok': True, 'available': True, 'languages': [
                {'language': language, 'installed': language in self.installed, 'status': 'installed' if language in self.installed else 'missing'} for language in ('zh','ja','en')]}
        if action in ('warmup', 'install'): return {'ok': True, 'ready': True}
        if action == 'transcribe':
            selected = payload['language'] or payload['languages'][0]
            return {'ok': True, 'candidates': [
                {'text': {'zh':'今天开会。','ja':'今日は会議です。','en':'This is a meeting.'}[language],
                 'language': language, 'confidence': .9 if language == selected else .4}
                for language in ([payload['language']] if payload['language'] else payload['languages'])]}
        raise AssertionError(action)


def test_factory_selects_apple_without_reading_model_directory(monkeypatch):
    monkeypatch.setenv('MEETING_INTERPRETER_ASR_BACKEND','apple')
    monkeypatch.setenv('MEETING_INTERPRETER_MODEL_DIR','/Volumes/offline/missing')
    backend = create_asr_backend('zh')
    assert isinstance(backend, AppleSpeechBackend) and backend.language == 'zh'
    backend.client.close()


def test_old_macos_fails_clearly_without_starting_process(monkeypatch):
    monkeypatch.setattr(apple_speech.platform,'system',lambda:'Darwin')
    monkeypatch.setattr(apple_speech.platform,'mac_ver',lambda:('15.7',(),''))
    monkeypatch.setattr(apple_speech.subprocess,'Popen',lambda *a,**k:pytest.fail('must not launch unsupported helper'))
    info=apple_speech.inspect_apple_speech()
    assert not info['available'] and not info['installed']
    assert 'macOS 26' in info['message']


@pytest.mark.asyncio
async def test_missing_assets_never_trigger_implicit_install():
    native=NativeFixture(installed=('en',))
    backend=AppleSpeechBackend(client=native)
    await backend.warmup(initial=True)
    assert native.calls[-1][1]['languages']==['en']
    japanese=backend.for_session('auto','zh-ja')
    with pytest.raises(RuntimeError,match='中文、日语'):
        await japanese.warmup()
    assert 'install' not in [action for action,_ in native.calls]


@pytest.mark.asyncio
@pytest.mark.parametrize('pair', ['zh-ja','zh-en','en-ja'])
async def test_apple_session_scopes_auto_candidates_to_pair_and_reuses_resident_helper(pair):
    native=NativeFixture()
    root=AppleSpeechBackend(client=native)
    left,right=pair.split('-')
    pipeline=Pipeline(mode='local',language_pair=pair,asr_backend=root,translate_inline=False)
    assert pipeline.asr.client is root.client
    assert pipeline.asr.languages == (left,right)
    await pipeline.asr.warmup()
    assert native.calls[-1][1]['languages']==[left,right]
    captions=[c async for c in pipeline.process_audio(audio([2000,-2000]*4800))]
    assert captions[-1].source_language==left
    assert captions[-1].target_language==right
    paragraph=captions[-1].paragraph_id
    pipeline.set_source_language(right)
    captions=[c async for c in pipeline.process_audio(audio([2000,-2000]*4800))]
    assert captions[-1].source_language==right and captions[-1].target_language==left
    assert captions[-1].paragraph_id==paragraph
    assert root.language is None


def test_automatic_candidate_comparison_rejects_unclear_or_out_of_pair_results():
    zh={'language':'zh','text':'我们开会。','confidence':.9}
    ja={'language':'ja','text':'会議を始めます。','confidence':.5}
    assert choose_candidate([zh,ja],('zh','ja'))==zh
    assert choose_candidate([zh,{**ja,'confidence':.86}],('zh','ja')) is None
    assert choose_candidate([zh],('en','ja')) is None
    assert choose_candidate([{**zh,'confidence':0}],('zh','ja')) is None
    assert choose_candidate([{**zh,'text':'これは会議です。'}],('zh','ja')) is None


@pytest.mark.asyncio
async def test_ambiguous_apple_result_explains_source_language_buttons():
    class Ambiguous(NativeFixture):
        def request(self, action, **payload):
            return {'candidates':[{'language':'zh','text':'会議','confidence':.8},{'language':'ja','text':'会議','confidence':.8}]}
    backend=AppleSpeechBackend(client=Ambiguous())
    assert await backend.transcribe(bytes(32000),16000,0) is None
    assert '源语言按钮' in backend.last_message


@pytest.mark.asyncio
async def test_native_timestamps_preserve_entire_text_or_use_whole_window():
    class Timed(NativeFixture):
        def request(self, action, **payload):
            return {'candidates':[{'language':'zh','text':'今天开会。','confidence':.9,'words':[
                {'text':'今天','start_ms':2000,'end_ms':2300},{'text':'开会。','start_ms':2300,'end_ms':2600}]}]}
    backend=AppleSpeechBackend('zh',client=Timed())
    result=await backend.transcribe(bytes(19200),16000,2000)
    assert [word.start_ms for word in result.words]==[2000,2300]
    result=await backend.transcribe(bytes(16000),16000,2000)
    assert result.text=='今天开会。' and not result.words


@pytest.mark.asyncio
async def test_failed_live_language_preparation_keeps_previous_decoder_and_does_not_pause():
    class Unready(AppleSpeechBackend):
        async def ensure_language_ready(self, language): raise RuntimeError('日语资源未安装')
    native=NativeFixture()
    pipeline=Pipeline(mode='local',source_language='zh',target_language='ja',asr_backend=AppleSpeechBackend(client=native),translate_inline=False)
    pipeline.asr=Unready('zh',client=native)
    sent=[]
    async def send(payload):sent.append(payload)
    session=LiveSession(pipeline,send)
    try:
        session.change_source_language('ja')
        session.start()
        await session.finish()
        assert pipeline.source_language=='zh'
        assert sent[0]['type']=='source_language_changed' and sent[0]['source_language']=='zh'
        assert '未切换' in sent[0]['message']
        assert not any(row['type']=='capture_paused' for row in sent)
    finally: await session.close()


def test_apple_settings_persist_without_stale_custom_asr_models(monkeypatch,tmp_path):
    config=tmp_path/'.env'
    config.write_text('MEETING_INTERPRETER_ASR_BACKEND=whisper\nMEETING_INTERPRETER_ASR_MODEL=/old/model\nMEETING_INTERPRETER_SENSEVOICE_MODEL=/old/voice\nMEETING_INTERPRETER_SERVICE_ASR_MODEL=old-service\nMEETING_INTERPRETER_ASR_URL=http://127.0.0.1:9999\n')
    monkeypatch.setattr(system,'user_config_path',lambda:config)
    system.save_model_directory('/Volumes/disconnected/models','apple',{'asr_model':'Apple SpeechAnalyzer','translation_backend':'nllb'})
    saved=system.saved_config()
    assert saved['MEETING_INTERPRETER_ASR_BACKEND']=='apple'
    assert not any(key in saved for key in ['MEETING_INTERPRETER_ASR_MODEL','MEETING_INTERPRETER_SENSEVOICE_MODEL','MEETING_INTERPRETER_SERVICE_ASR_MODEL','MEETING_INTERPRETER_ASR_URL'])
    system.load_user_config()
    assert system.model_settings()['asr_model']=='Apple SpeechAnalyzer'
    assert system.model_settings()['asr_engine']=='apple'


def test_apple_inventory_ignores_custom_folder_and_download_is_explicit(monkeypatch):
    native=NativeFixture()
    monkeypatch.setattr(apple_speech,'unavailable_reason',lambda:None)
    monkeypatch.setattr(apple_speech,'AppleSpeechClient',lambda:native)
    info=system.inspect_asr_models('apple',model_dir='ignored-relative-folder',languages=['zh','ja'])
    assert info['installed'] and info['storage']=='macOS'
    assert [action for action,_ in native.calls]==['probe']
    assert system.download_asr_model('apple',languages=['zh','ja'])['ok']
    assert native.calls[-1][0]=='install'
    assert native.calls[-1][1]['languages']==['zh','ja']


def test_apple_api_validates_requested_pair_and_resource_languages(monkeypatch):
    from fastapi.testclient import TestClient
    from meeting_interpreter.app import create_app
    native=NativeFixture()
    monkeypatch.setattr(apple_speech,'unavailable_reason',lambda:None)
    monkeypatch.setattr(apple_speech,'AppleSpeechClient',lambda:native)
    with TestClient(create_app()) as client:
        response=client.get('/system/models',params={'engine':'apple','language_pair':'en-ja','model_dir':'/missing'})
        assert response.status_code==200 and response.json()['model']=='Apple SpeechAnalyzer'
        assert client.get('/system/models?engine=apple&language_pair=zh-fr').status_code==400
        assert client.post('/system/download-asr',json={'engine':'apple','languages':['zh','xx']}).status_code==400
        assert not any(action=='install' for action,_ in native.calls)
        response=client.post('/system/download-asr',json={'engine':'apple','languages':['en','ja']})
        assert response.status_code==200 and response.json()['ok']
        assert native.calls[-1][0]=='install'


def test_native_rpc_timeout_stops_helper_and_next_job_has_no_stale_reply(monkeypatch,tmp_path):
    helper=tmp_path/'speech-helper'
    helper.write_text(f'#!{sys.executable}\n'+'''import json,sys,time
for line in sys.stdin:
 request=json.loads(line)
 if request['action']=='stall': time.sleep(2)
 print(json.dumps({'ok':True,'id':request['id'],'action':request['action']}),flush=True)
''')
    helper.chmod(0o755)
    monkeypatch.setattr(apple_speech,'bridge_path',lambda:helper)
    monkeypatch.setattr(apple_speech,'unavailable_reason',lambda:None)
    client=AppleSpeechClient()
    try:
        with pytest.raises(TimeoutError): client.request('stall',timeout=.05)
        assert client._process is None
        assert client.request('probe',timeout=1)['action']=='probe'
    finally: client.close()


def test_native_reported_error_keeps_helper_warm_and_synchronized(monkeypatch,tmp_path):
    helper=tmp_path/'speech-helper'
    helper.write_text(f'#!{sys.executable}\n'+'''import json,sys
for line in sys.stdin:
 request=json.loads(line)
 print(json.dumps({'ok':request['action']!='missing','id':request['id'],'message':'资源未安装'}),flush=True)
''')
    helper.chmod(0o755)
    monkeypatch.setattr(apple_speech,'bridge_path',lambda:helper)
    monkeypatch.setattr(apple_speech,'unavailable_reason',lambda:None)
    client=AppleSpeechClient()
    try:
        with pytest.raises(apple_speech.AppleSpeechError,match='资源未安装'):
            client.request('missing',timeout=1)
        process=client._process
        assert process.poll() is None
        assert client.request('probe',timeout=1)['ok']
        assert client._process is process
    finally: client.close()


def test_missing_apple_assets_show_in_health_and_block_microphone_configuration(monkeypatch):
    from fastapi.testclient import TestClient
    from meeting_interpreter import app as app_module
    native=NativeFixture(installed=())
    monkeypatch.setenv('MEETING_INTERPRETER_MODE','local')
    monkeypatch.setenv('MEETING_INTERPRETER_ASR_BACKEND','apple')
    monkeypatch.setenv('MEETING_INTERPRETER_TRANSLATION_BACKEND','nllb')
    monkeypatch.setattr(app_module,'create_asr_backend',lambda:AppleSpeechBackend(client=native))
    with TestClient(app_module.create_app()) as client:
        for _ in range(50):
            health=client.get('/health').json()
            if health['asr']['status']=='error': break
        else: pytest.fail('missing assets were not surfaced')
        assert not health['models']['ready']
        assert '语言资源未安装' in health['last_error']
        assert health['asr']['backend']=='apple'
        assert 'Apple SpeechAnalyzer' in health['asr']['model']
        with client.websocket_connect('/ws') as ws:
            ws.receive_json()
            ws.send_json({'type':'config','source_language':'auto','language_pair':'zh-ja','target_language':'ja'})
            ws.receive_json()  # preparation status, never a configured acknowledgement
            error=ws.receive_json()
            assert error['type']=='error' and '未开启收音' in error['message']
    assert all(action not in ('install','transcribe') for action,_ in native.calls)
