# 0.2.12 — remove historical ASR paths after folder changes

This patch fixes cases still present in 0.2.11. Resolving an absolute direct model
path outside the chosen root could join an absolute path back onto the root and
silently return the old folder. SenseVoice also retained an independently saved
historical model path. Empty folder scans kept the historical model as an option,
and saving did not distinguish the pending configuration from warmed models.

Changes:

- Resolve built-in models inside the selected root. A missing Whisper model now
  produces an explicit configuration error rather than loading an old path or
  implicitly fetching a repository.
- Scan direct model folders, their immediate children, the `asr` subdirectory,
  and supported Hugging Face layouts. Select a unique available local model;
  otherwise leave the selection empty and require a choice.
- Saving SenseVoice writes the selected directory's effective model path.
  Saving any ASR engine removes inactive ASR path/service keys from the config;
  startup clears corresponding inherited keys. Duplicate saved keys are collapsed.
- Missing models disappear from built-in model choices. Empty model selections
  can be saved with an intended folder, with missing files reported explicitly.
- After saving, health reports a pending restart and the UI shows the saved ASR
  selection with “待重启加载”. Recording is blocked until the App is restarted,
  so the old resident model cannot be mistaken for the newly saved selection.

Validation:

- 114 Python tests passed; 1 optional real-audio accuracy test skipped.
- 43 frontend tests passed.
- Chinese/Japanese/English UI smoke at 1440×900, 1280×720 and 1024×768;
  saving shows pending restart and disables recording. No page errors.
- A temporary new directory linked existing local Whisper NPZ weights. Saved
  configuration removed the original absolute path. A fresh offline Python
  process read the configuration, loaded the model from the new path and ran a
  one-second silence transcription. No weights downloaded and no real user
  preferences changed. This is a loading/configuration check, not an accuracy test.

Use the new portable App, select the directory containing the chosen built-in
ASR model, save, completely quit and reopen the App. Ollama / llama.app models
remain selected by service and model name; those services own their storage.
