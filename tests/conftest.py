import pytest


@pytest.fixture(autouse=True)
def isolate_optional_voice_model(monkeypatch, tmp_path):
    """Unit tests must not load a model from the user's Application Support."""
    from meeting_interpreter import system
    monkeypatch.setattr(system, 'user_config_path', lambda: tmp_path / '.env')
    monkeypatch.delenv('MEETING_INTERPRETER_MODEL_DIR', raising=False)
    monkeypatch.setenv("MEETING_INTERPRETER_ASR_BACKEND", "whisper")
    monkeypatch.setenv("MEETING_INTERPRETER_SPEAKER_EMBEDDING_MODEL", str(tmp_path / "not-installed.onnx"))
    monkeypatch.setenv("MEETING_INTERPRETER_SENSEVOICE_MODEL", str(tmp_path / "not-installed-sensevoice"))
