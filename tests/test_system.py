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
    assert result["restart_required"] is True
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
    import pytest
    monkeypatch.setattr(system, 'user_config_path', lambda: tmp_path / '.env')
    with pytest.raises(ValueError, match='挂载'):
        system.save_model_directory('/Volumes/lmi-regression-unmounted/models')
    assert not (tmp_path / '.env').exists()


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
