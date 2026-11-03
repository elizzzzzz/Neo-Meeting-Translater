from pathlib import Path

from meeting_interpreter import system


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


def test_default_model_directory_is_application_support(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("MEETING_INTERPRETER_MODEL_DIR", raising=False)
    monkeypatch.setattr(system.Path, "home", lambda: tmp_path)
    assert system.current_model_directory() == str(tmp_path / "Library/Application Support/LocalMeetingInterpreter/models")
