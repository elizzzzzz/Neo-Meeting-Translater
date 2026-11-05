# 0.2.11 — model directory and discovery fixes

Changing the model folder now rescans the edited path before saving. Reopening
settings reads the saved folder again; background health polling preserves an
in-progress edit. The native folder picker and “Use Ollama folder” action both
refresh the model lists. Save and reopen the App to replace warmed models.

The default folder follows `OLLAMA_MODELS` from the environment or macOS launch
configuration, otherwise `~/.ollama/models`; symbolic links are resolved. An
explicitly saved folder takes precedence. Selecting a folder does not move
weights or change the model storage owned by a running Ollama / llama.app
service. Service model lists are read from each service's configured local URL.

Saved model choices now take precedence over inherited stale model/cache paths
at desktop startup. Built-in file inspection and loading resolve the same model
location. Detection accepts the App cache layout, Hugging Face hub roots, direct
model folders, and both MLX Whisper `weights.npz` and `weights.safetensors`.
Pinned snapshots are resolved inside the new folder even when the old copy still
exists. Missing snapshots retain their repository identity for subsequent scans.
SenseVoice inspection respects its configured path. Missing external volumes
receive a specific diagnostic and are not created as fake mount directories.

A short service model name such as `translategemma:4b` resolves to an installed
namespaced name only when there is exactly one match. Exact names and ambiguous
choices are retained; unrelated models are never selected automatically. The
optional Ollama recommendation panel uses the same name matching.

Validation:

- Python: 107 passed, 1 skipped. Existing framework/dependency deprecation warnings remain.
- Frontend: 41 passed.
- UI smoke: Chinese/Japanese/English at 1440×900, 1280×720 and 1024×768;
  model-folder controls checked at 1440×900 and 1024×768; no page errors.
- Existing local NPZ weights resolved through a temporary relocated cache link;
  startup selected the new path and matched the installed Ollama translation
  model name. No weight download or persistent user setting change was needed.

This patch validates discovery/configuration. It does not claim a new meeting
recognition accuracy or latency measurement.
