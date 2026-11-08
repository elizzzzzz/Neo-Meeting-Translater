from pathlib import Path

from meeting_interpreter import system


def test_interface_language_persists_independently_of_service_port_and_tip_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(system, 'preferences_path', lambda: tmp_path / 'preferences.json')
    system.save_preferences(interface_language='ja')
    system.save_preferences(False)
    assert system.read_preferences() == {'show_tips': False, 'interface_language': 'ja'}
    system.save_preferences(interface_language='auto')
    assert system.read_preferences() == {'show_tips': False, 'interface_language': 'auto'}


def test_inspect_ollama_reports_update_and_recommended_model(monkeypatch):
    monkeypatch.setattr(system, "_ollama_path", lambda: "/opt/homebrew/bin/ollama")
    monkeypatch.setattr(system, "_ollama_models", lambda timeout=1.2: (True, ["translategemma:4b"]))
    monkeypatch.setattr(system, "_latest_ollama_version", lambda timeout=1.8: "0.9.0")

    class Result:
        stdout = "ollama version is 0.8.0"
        stderr = ""
        returncode = 0

    monkeypatch.setattr(system.subprocess, "run", lambda *args, **kwargs: Result())
    info = system.inspect_ollama()
    assert info["installed"] is True
    assert info["reachable"] is True
    assert info["recommended_model_present"] is True
    assert info["update_available"] is True


def test_save_model_directory_writes_cache_locations(monkeypatch, tmp_path: Path):
    config = tmp_path / ".env"
    monkeypatch.setattr(system, "user_config_path", lambda: config)
    result = system.save_model_directory(str(tmp_path / "models"))
    text = config.read_text(encoding="utf-8")
    assert result["restart_required"] is False
    assert f"MEETING_INTERPRETER_MODEL_DIR={tmp_path / 'models'}" in text
    assert f"HF_HOME={tmp_path / 'models' / 'huggingface'}" in text


def test_speech_engine_setting_persists_without_changing_translation(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    config.write_text('MEETING_INTERPRETER_OLLAMA_MODEL=translategemma:4b\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    system.save_model_directory(str(tmp_path / 'models'), 'sensevoice')
    text = config.read_text()
    assert 'MEETING_INTERPRETER_ASR_BACKEND=sensevoice' in text
    assert 'MEETING_INTERPRETER_OLLAMA_MODEL=translategemma:4b' in text


def test_default_model_directory_follows_ollama(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("MEETING_INTERPRETER_MODEL_DIR", raising=False)
    monkeypatch.setattr(system.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    monkeypatch.setattr(system.subprocess, "run", lambda *a, **k: type("Result", (), {"stdout": "", "returncode": 0})())
    assert system.current_model_directory() == str(tmp_path / ".ollama/models")


def test_tips_preference_survives_a_new_process(monkeypatch, tmp_path):
    import json
    from fastapi.testclient import TestClient
    from meeting_interpreter.app import create_app

    preferences = tmp_path / 'preferences.json'
    monkeypatch.setattr(system, 'preferences_path', lambda: preferences, raising=False)
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'mock')
    with TestClient(create_app()) as client:
        assert client.get('/preferences').status_code == 200
        assert client.post('/preferences', json={'show_tips': False}).status_code == 200
    assert json.loads(preferences.read_text())['show_tips'] is False
    with TestClient(create_app()) as client:
        assert client.get('/preferences').json()['show_tips'] is False


def test_model_directory_rejects_newline_before_writing_config(monkeypatch, tmp_path):
    import pytest
    config = tmp_path / '.env'
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    with pytest.raises(ValueError, match='换行'):
        system.save_model_directory(str(tmp_path / 'models') + '\nEXTRA_SETTING=1')
    assert not config.exists()


def _whisper_snapshot(root, repo='mlx-community/whisper-medium-mlx-8bit'):
    folder = root / ('models--' + repo.replace('/', '--')) / 'snapshots' / 'new-revision'
    folder.mkdir(parents=True)
    (folder / 'config.json').write_text('{}')
    (folder / 'weights.safetensors').write_bytes(b'weights')
    return folder


def test_model_inspection_uses_saved_selection_instead_of_old_environment(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    root = tmp_path / 'models'
    repo = 'mlx-community/whisper-small-mlx-8bit'
    folder = _whisper_snapshot(root / 'huggingface/hub', repo)
    config.write_text(f'MEETING_INTERPRETER_MODEL_DIR={root}\nMEETING_INTERPRETER_ASR_MODEL={repo}\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    monkeypatch.setenv('MEETING_INTERPRETER_ASR_MODEL', 'old/whisper')
    info = system.inspect_asr_models()
    assert info['model'] == repo
    assert info['installed']
    assert info['resolved_model'] == str(folder)


def test_changed_directory_rebases_pinned_hf_snapshot_even_if_old_files_exist(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    old = _whisper_snapshot(tmp_path / 'old/huggingface/hub')
    new = _whisper_snapshot(tmp_path / 'new/hub')
    config.write_text(f'MEETING_INTERPRETER_MODEL_DIR={tmp_path / "old"}\nMEETING_INTERPRETER_ASR_MODEL={old}\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    system.save_model_directory(str(tmp_path / 'new'))
    assert system.model_settings()['asr_model'] == str(new)


def test_direct_model_folder_is_detected_in_preview_without_saving(monkeypatch, tmp_path):
    root = tmp_path / 'new-model'
    root.mkdir()
    (root / 'config.json').write_text('{}')
    (root / 'weights.safetensors').write_bytes(b'weights')
    monkeypatch.setattr(system, 'user_config_path', lambda: tmp_path / '.env')
    info = system.inspect_asr_models('whisper', 'old/whisper', model_dir=str(root))
    assert info['installed'] and info['model'] == str(root)
    assert not (tmp_path / '.env').exists()


def test_startup_saved_model_settings_override_inherited_paths(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    root = tmp_path / 'new'
    new = _whisper_snapshot(root / 'hub')
    config.write_text(f'MEETING_INTERPRETER_MODEL_DIR={root}\nMEETING_INTERPRETER_ASR_MODEL=mlx-community/whisper-medium-mlx-8bit\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    monkeypatch.setattr(system.os, 'environ', dict(system.os.environ))
    for key in ('MEETING_INTERPRETER_MODEL_DIR', 'HF_HOME', 'HUGGINGFACE_HUB_CACHE', 'TRANSFORMERS_CACHE', 'MEETING_INTERPRETER_ASR_MODEL'):
        monkeypatch.setenv(key, '/old/path')
    system.load_user_config()
    import os
    assert os.environ['MEETING_INTERPRETER_ASR_MODEL'] == str(new)
    assert os.environ['HUGGINGFACE_HUB_CACHE'] == str(root / 'huggingface/hub')
    assert os.environ['MEETING_INTERPRETER_MODEL_DIR'] == str(root)


def test_sensevoice_inspection_honors_explicit_saved_location(monkeypatch, tmp_path):
    folder = tmp_path / 'sensevoice'
    folder.mkdir()
    for name in ('model.int8.onnx', 'tokens.txt', 'silero_vad.onnx'):
        (folder / name).write_bytes(b'data')
    config = tmp_path / '.env'
    config.write_text(f'MEETING_INTERPRETER_SENSEVOICE_MODEL={folder}\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    assert system.inspect_asr_models('sensevoice')['path'] == str(folder)
    assert system.inspect_asr_models('sensevoice')['installed']


def test_saving_missing_external_volume_does_not_create_fake_mount(monkeypatch, tmp_path):
    monkeypatch.setattr(system, 'user_config_path', lambda: tmp_path / '.env')
    root = '/Volumes/lmi-regression-unmounted/models'
    result = system.save_model_directory(root)
    assert system.saved_config()['MEETING_INTERPRETER_MODEL_DIR'] == root
    assert not Path('/Volumes/lmi-regression-unmounted').exists()
    assert result['saved'] is True
    assert result['settings']['model_dir_exists'] is False


def test_asr_service_save_survives_unmounted_root_and_process_restart(monkeypatch, tmp_path):
    import json
    import subprocess
    import sys
    from fastapi.testclient import TestClient
    from meeting_interpreter.app import create_app

    config = tmp_path / '.env'
    root = '/Volumes/lmi-regression-unmounted/models'
    config.write_text(f'MEETING_INTERPRETER_MODEL_DIR={root}\nMEETING_INTERPRETER_ASR_BACKEND=sensevoice\nMEETING_INTERPRETER_ASR_MODEL=/old/whisper\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'mock')
    desired = dict(model_dir=root, asr_engine='ollama', asr_model='frozenlab/qwen3-asr:1.7b',
                   asr_url='http://127.0.0.1:11434', translation_backend='llama',
                   translation_model='', translation_url='http://127.0.0.1:9931')
    with TestClient(create_app()) as client:
        response = client.post('/settings', json=desired)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['saved'] is True
        for key, value in desired.items():
            assert result['settings'][key] == value
            assert client.get('/settings').json()[key] == value
        assert not client.get('/health').json()['settings']['restart_required']
    # A fresh process must override the historical inherited ASR settings too.
    restarted = subprocess.run([sys.executable, '-c', '''
import json, sys
from pathlib import Path
from meeting_interpreter import system
system.user_config_path = lambda: Path(sys.argv[1])
system.load_user_config()
from meeting_interpreter.asr import create_asr_backend
asr = create_asr_backend()
print(json.dumps({'settings':system.model_settings(), 'runtime_model':asr.model}))
''', str(config)], capture_output=True, text=True, check=True)
    actual = json.loads(restarted.stdout)
    assert actual['runtime_model'] == desired['asr_model']
    for key, value in desired.items():
        assert actual['settings'][key] == value
    assert 'MEETING_INTERPRETER_ASR_MODEL=' not in config.read_text()


def test_empty_service_selection_clears_previous_model_without_blocking_other_settings(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    config.write_text('MEETING_INTERPRETER_SERVICE_ASR_MODEL=old-asr\nMEETING_INTERPRETER_OLLAMA_MODEL=old-translation\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    result = system.save_model_directory(str(tmp_path / 'not-created'), 'ollama', {
        'asr_model':'', 'translation_backend':'ollama', 'translation_model':''})
    assert result['settings']['asr_model'] == ''
    assert result['settings']['translation_model'] == ''
    assert system.saved_config()['MEETING_INTERPRETER_SERVICE_ASR_MODEL'] == ''
    assert not (tmp_path / 'not-created').exists()


def test_default_directory_follows_custom_ollama_location(monkeypatch, tmp_path):
    monkeypatch.setattr(system, 'user_config_path', lambda: tmp_path / '.env')
    monkeypatch.delenv('MEETING_INTERPRETER_MODEL_DIR', raising=False)
    monkeypatch.setenv('OLLAMA_MODELS', str(tmp_path / 'ollama-files'))
    assert system.current_model_directory() == str(tmp_path / 'ollama-files')


def test_startup_refreshes_unique_installed_service_name_without_inference(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    config.write_text('MEETING_INTERPRETER_TRANSLATION_BACKEND=ollama\nMEETING_INTERPRETER_OLLAMA_MODEL=translategemma:4b\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    monkeypatch.setattr(system, 'inspect_service', lambda *a, **k: {'models': [{'id':'vendor/translategemma:4b'}]})
    monkeypatch.setattr(system.os, 'environ', dict(system.os.environ))
    monkeypatch.setenv('MEETING_INTERPRETER_OLLAMA_MODEL', 'old-model')
    system.load_user_config()
    import os
    assert os.environ['MEETING_INTERPRETER_OLLAMA_MODEL'] == 'vendor/translategemma:4b'


def test_ollama_recommendation_recognizes_installed_namespaced_model(monkeypatch):
    monkeypatch.setattr(system, '_ollama_path', lambda: None)
    monkeypatch.setattr(system, '_ollama_models', lambda **kw: (True, ['vendor/translategemma:4b']))
    info = system.inspect_ollama()
    assert info['recommended_model_present']
    assert info['recommended_model'] == 'vendor/translategemma:4b'


def test_preview_api_uses_unsaved_folder_without_changing_preferences(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from meeting_interpreter.app import create_app
    config = tmp_path / '.env'
    config.write_text(f'MEETING_INTERPRETER_MODEL_DIR={tmp_path / "old"}\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'mock')
    folder = _whisper_snapshot(tmp_path / 'new/hub')
    with TestClient(create_app()) as client:
        result = client.get('/system/models', params={'engine':'whisper', 'model':'mlx-community/whisper-medium-mlx-8bit', 'model_dir':str(tmp_path / 'new')}).json()
    assert result['resolved_model'] == str(folder)
    assert str(tmp_path / 'old') in config.read_text()


def test_unmounted_snapshot_keeps_repository_identity_for_later_rescan(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    repo = 'mlx-community/whisper-medium-mlx-8bit'
    config.write_text(f'MEETING_INTERPRETER_MODEL_DIR={tmp_path / "missing"}\nMEETING_INTERPRETER_ASR_MODEL=/old/models--{repo.replace("/", "--")}/snapshots/old\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    monkeypatch.setattr(system.os, 'environ', dict(system.os.environ))
    system.load_user_config()
    pinned = system.os.environ['MEETING_INTERPRETER_ASR_MODEL']
    new = _whisper_snapshot(tmp_path / 'new/hub')
    info = system.inspect_asr_models('whisper', pinned, model_dir=str(tmp_path / 'new'))
    assert info['resolved_model'] == str(new)


def test_legacy_mlx_npz_weights_are_detected(monkeypatch, tmp_path):
    root = tmp_path / 'whisper'
    root.mkdir()
    (root / 'config.json').write_text('{}')
    (root / 'weights.npz').write_bytes(b'weights')
    monkeypatch.setattr(system, 'user_config_path', lambda: tmp_path / '.env')
    info = system.inspect_asr_models('whisper', model_dir=str(root))
    assert info['installed']
    assert info['resolved_model'] == str(root)


def test_new_empty_root_never_resolves_old_direct_model(tmp_path):
    old = tmp_path / 'old-whisper'
    old.mkdir()
    (old / 'config.json').write_text('{}')
    (old / 'weights.npz').write_bytes(b'weights')
    new = tmp_path / 'new'
    new.mkdir()
    assert system.resolve_model_location(str(old), new) is None


def test_preview_changed_root_drops_stale_absolute_selection(monkeypatch, tmp_path):
    old = _whisper_snapshot(tmp_path / 'old/hub')
    new = tmp_path / 'new'
    new.mkdir()
    monkeypatch.setattr(system, 'user_config_path', lambda: tmp_path / '.env')
    info = system.inspect_asr_models('whisper', str(old), str(new))
    assert not info['installed']
    assert str(old) not in info['models']
    assert not info['model']


def test_changing_sensevoice_root_replaces_independent_historical_path(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    config.write_text(f'MEETING_INTERPRETER_MODEL_DIR={tmp_path / "old"}\nMEETING_INTERPRETER_ASR_BACKEND=sensevoice\nMEETING_INTERPRETER_SENSEVOICE_MODEL={tmp_path / "independent-old"}\nMEETING_INTERPRETER_ASR_MODEL={tmp_path / "old-whisper"}\n')
    root = tmp_path / 'new-sensevoice'
    root.mkdir()
    for name in ('model.int8.onnx', 'tokens.txt', 'silero_vad.onnx'):
        (root / name).write_bytes(b'weights')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    system.save_model_directory(str(root), 'sensevoice', {'asr_model':'SenseVoice-Small'})
    saved = system.saved_config()
    assert saved['MEETING_INTERPRETER_SENSEVOICE_MODEL'] == str(root)
    assert 'MEETING_INTERPRETER_ASR_MODEL' not in saved
    monkeypatch.setattr(system.os, 'environ', dict(system.os.environ))
    system.load_user_config()
    from meeting_interpreter.asr import create_asr_backend
    assert create_asr_backend().model == str(root)
    assert system.inspect_asr_models('sensevoice')['path'] == str(root)


def test_saving_whisper_in_empty_new_folder_clears_pinned_old_model(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    old = _whisper_snapshot(tmp_path / 'old/hub')
    config.write_text(f'MEETING_INTERPRETER_MODEL_DIR={tmp_path / "old"}\nMEETING_INTERPRETER_ASR_MODEL={old}\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    system.save_model_directory(str(tmp_path / 'empty'), 'whisper', {'asr_model':str(old)})
    assert str(old) not in config.read_text()
    assert system.model_settings()['asr_model'] == ''
    monkeypatch.setattr(system.os, 'environ', dict(system.os.environ))
    system.load_user_config()
    from meeting_interpreter.asr import create_asr_backend
    import pytest
    with pytest.raises(RuntimeError, match='模型'):
        create_asr_backend()


def test_model_root_discovers_a_direct_child_whisper_folder(monkeypatch, tmp_path):
    root = tmp_path / 'new'
    model = root / 'whisper-medium'
    model.mkdir(parents=True)
    (model / 'config.json').write_text('{}')
    (model / 'weights.npz').write_bytes(b'weights')
    monkeypatch.setattr(system, 'user_config_path', lambda: tmp_path / '.env')
    info = system.inspect_asr_models('whisper', '/old/whisper-medium', str(root))
    assert info['installed']
    assert info['model'] == str(model)


def test_settings_reports_sensevoice_selection_without_inherited_whisper_path(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    config.write_text(f'MEETING_INTERPRETER_MODEL_DIR={tmp_path / "new"}\nMEETING_INTERPRETER_ASR_BACKEND=sensevoice\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    monkeypatch.setenv('MEETING_INTERPRETER_ASR_MODEL', '/old-whisper')
    assert system.model_settings()['asr_model'] == 'SenseVoice-Small'


def test_settings_save_applies_current_model_without_restart(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from meeting_interpreter.app import create_app
    config = tmp_path / '.env'
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'mock')
    monkeypatch.setenv('MEETING_INTERPRETER_TRANSLATION_BACKEND', 'nllb')
    with TestClient(create_app()) as client:
        response = client.post('/settings', json={'model_dir':str(tmp_path / 'new'), 'asr_engine':'sensevoice', 'asr_model':'SenseVoice-Small'})
        assert response.status_code == 200
        health = client.get('/health').json()
        assert not health['settings']['restart_required']
        assert health['settings']['requested_revision'] == 1
        assert '重启' not in health['models']['message']


def test_appearance_persists_across_other_preferences_and_app_clients(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from meeting_interpreter.app import create_app
    monkeypatch.setattr(system, 'preferences_path', lambda: tmp_path / 'preferences.json')
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'mock')
    with TestClient(create_app()) as client:
        for mode in ['light', 'dark', 'system']:
            assert client.post('/preferences', json={'appearance': mode}).json()['appearance'] == mode
        client.post('/preferences', json={'show_tips': False, 'interface_language': 'ja'})
    with TestClient(create_app()) as client:
        assert client.get('/preferences').json() == {'appearance': 'system', 'show_tips': False, 'interface_language': 'ja', 'setup_completed': False}
        for invalid in ['sepia', '', 4, [], {}]:
            assert client.post('/preferences', json={'appearance': invalid}).status_code == 400
        assert client.get('/preferences').json()['appearance'] == 'system'


def test_old_or_invalid_appearance_preferences_allow_system_default(monkeypatch, tmp_path):
    path = tmp_path / 'preferences.json'
    monkeypatch.setattr(system, 'preferences_path', lambda: path)
    assert system.read_preferences().get('appearance', 'system') == 'system'
    path.write_text('{"appearance":"invalid","show_tips":false}')
    assert system.read_preferences() == {'show_tips': False}


def test_existing_configuration_skips_setup_without_checking_model_availability(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    config.write_text('MEETING_INTERPRETER_MODEL_DIR=/Volumes/disconnected/models\n')
    system.save_preferences(show_tips=True, appearance='dark', interface_language='ja')
    assert system.startup_preferences() == {
        'show_tips': False, 'setup_completed': True, 'appearance': 'dark', 'interface_language': 'ja'}
    # Reading startup state never rewrites the user's preference or model file.
    assert system.read_preferences()['show_tips'] is True
    assert config.read_text() == 'MEETING_INTERPRETER_MODEL_DIR=/Volumes/disconnected/models\n'


def test_first_launch_and_environment_defaults_do_not_complete_setup(monkeypatch, tmp_path):
    config = tmp_path / '.env'
    config.write_text('MEETING_INTERPRETER_MODE=local\n')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    monkeypatch.setenv('MEETING_INTERPRETER_MODEL_DIR', '/environment-default')
    assert system.startup_preferences() == {'show_tips': True, 'setup_completed': False}
    system.save_preferences(show_tips=False)
    assert system.startup_preferences() == {'show_tips': False, 'setup_completed': False}
    config.write_text('MEETING_INTERPRETER_ASR_BACKEND=apple\n')
    assert system.startup_preferences()['setup_completed'] is True


def test_successful_settings_save_is_remembered_across_new_app_instances(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from meeting_interpreter.app import create_app
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'mock')
    config = tmp_path / '.env'
    config.write_text('')
    monkeypatch.setattr(system, 'user_config_path', lambda: config)
    system.save_preferences(show_tips=True, appearance='light')
    with TestClient(create_app()) as client:
        assert client.get('/preferences').json()['setup_completed'] is False
        assert client.post('/settings', json={'model_dir':'relative/path','asr_engine':'apple'}).status_code == 400
        assert client.get('/preferences').json()['setup_completed'] is False
        saved = client.post('/settings', json={'model_dir':str(tmp_path/'offline-models'),'asr_engine':'apple'})
        assert saved.status_code == 200
    with TestClient(create_app()) as client:
        preferences = client.get('/preferences').json()
        assert preferences['setup_completed'] is True and preferences['show_tips'] is False
        assert preferences['appearance'] == 'light'
