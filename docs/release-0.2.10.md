# Local Meeting Interpreter 0.2.10

Speech recognition and translation now have independent service and model
selectors in local settings. Each can use Ollama or llama.app; built-in Whisper,
SenseVoice, and NLLB remain available. Saving persists both selections and their
loopback addresses; reopen the App to warm the selected pair. Active runtime
status continues to describe the models actually running until restart.

- Discover installed models without loading or downloading weights. Separate
  speech/audio models from text-generation models; Qwen3-ASR is never offered as
  a text translator. Preserve missing saved model names with an explicit warning.
- Send PCM as a WAV audio request to Ollama's local chat API or llama.app's
  OpenAI-compatible chat API. Parse Qwen3-ASR's detected-language metadata so
  Chinese/Japanese/English routing remains automatic.
- Stream llama.app translations with SSE, retain the existing shared 4.8-second
  live deadline, and close cancelled HTTP streams. Disable supported reasoning
  modes for translation. Optional serial correction stays disabled in live mode.
- Allow independent ports, including Ollama 11434 and llama.app 9931. Restrict
  new service endpoints to HTTP loopback, bypass proxies and reject redirects.
- Report connected-but-empty services separately from models that are ready.
  Detect llama.app's one-resident-model limit: two different models on that
  server cannot be advertised as simultaneously hot. Use different services or
  configure llama.app for two resident models.
- Keep the two model cards prominent; collapse optional Ollama installation
  tools. Chinese/Japanese/English labels and persistent interface preferences
  remain available. External service model files remain managed by their apps.

## Validation

Automated tests exercise request formats, source-language parsing, model
filtering, independent persistent selections, invalid-address rejection, SSE
translation, late discovery, empty services, and single-model capacity. UI
fixtures exercise the selections and saving without changing user settings.

Real local Ollama checks used system-generated short speech, not microphone or
conference recordings. Installed models:

- Recognition: `frozenlab/qwen3-asr:1.7b`
- Translation: `kaanmotivasyon02/translategemma:4b`

The Chinese fixture “现在开始会议。” and Japanese fixture “会議を始めます。”
were transcribed correctly with the corresponding detected language. Warm
recognition requests took 0.870 s and 1.532 s. Warm translation requests took
0.321 s (Japanese→Chinese) and 0.314 s (Chinese→Japanese). Initial cold requests
took 14.701 s for recognition and 5.294 s for translation; these belong in startup
preparation, before microphone capture. Both models appeared in Ollama's resident
model list afterwards. These are short-fixture API timings, excluding capture
buffering, and do not establish long-meeting accuracy or guaranteed latency.

The installed llama.app service responded at port 9931 but had an empty model
catalogue and a one-model resident limit. Its protocol was tested with fixtures;
real llama.app inference remains unverified until compatible models are added.

After explicitly prewarming both Ollama models, the actual live pipeline was
fed the two WAV fixtures in paced 200 ms audio packets. The first correct full
Chinese text appeared at 1.499 s from capture start and its Japanese translation
at 1.988 s. Japanese text appeared at 1.476 s and its Chinese translation at
1.781 s. Both fixture sessions finished with zero dropped audio samples and zero
skipped translations. An earlier run without explicit prewarming correctly
skipped a cold translation at the live deadline. These observations support
preparing both models before opening capture; they are not long-meeting results.

Final automated checks: 94 Python tests passed, 1 skipped; 37 frontend tests
passed. Three-language layout and model-selection/save smoke checks passed at
1440×900, 1280×720, and 1024×768 without page errors. Portable arm64 ZIP and DMG
passed extraction/mounting, bundled-library, and code-signature verification.
