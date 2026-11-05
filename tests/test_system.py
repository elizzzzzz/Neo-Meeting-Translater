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


def test_default_model_directory_is_application_support(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("MEETING_INTERPRETER_MODEL_DIR", raising=False)
    monkeypatch.setattr(system.Path, "home", lambda: tmp_path)
    assert system.current_model_directory() == str(tmp_path / "Library/Application Support/LocalMeetingInterpreter/models")


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
