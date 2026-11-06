# 0.2.13 — persist ASR settings independently of model availability

The previous save endpoint rejected the entire form before writing any settings
when the selected model directory was on an unmounted disk. An empty translation
catalogue also prevented saving ASR changes. Both failures left the old config
untouched, so restarting brought back the historical selection.

- Save the intended absolute model directory without requiring the directory to
  exist or creating it. An unavailable directory is reported separately from a
  successful save. Service models keep using their service's storage.
- Allow empty model selections to persist as unconfigured values. This clears
  historical names instead of blocking unrelated model/service changes.
- Verify the persisted keys after the atomic write, then return a save receipt
  containing the saved settings. URL and config-injection validation remain in
  place. Restart remains necessary to replace the resident models.
- Preserve the successful save message if the subsequent health refresh fails.

Validation:

- Reproduced both original failures against the settings API before fixing them:
  HTTP 400 with the original config unchanged.
- 116 Python tests passed; one optional real-audio accuracy test skipped.
- 45 frontend tests passed.
- `scripts/smoke_settings_persistence.py` used real settings and health endpoints
  with a temporary configuration and simulated model catalogues. The UI saved an
  Ollama ASR selection with an unavailable external directory and empty llama.app
  translation selection. Closing/reopening settings and restarting the server
  preserved all choices; runtime health selected the saved ASR model.
- Built arm64 App, portable ZIP and DMG. Verified signatures, extracted ZIP and
  mounted DMG. These checks do not measure recognition accuracy or latency.
- No user configuration changed; no models downloaded, loaded or upgraded.

Open the 0.2.13 App, select the desired ASR settings, save, then fully quit and
reopen the App. Previous unsuccessful saves cannot be recovered automatically.
