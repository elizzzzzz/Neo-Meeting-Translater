# NMT · Neo Meeting Translater

**NMT supports fully local speech recognition and translation. Once models are ready, your Mac can recognize Chinese, Japanese and English speech and produce bilingual subtitles offline, without uploading meeting audio or text to the cloud.**

[简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Download the latest version](https://github.com/elizzzzzz/Neo-Meeting-Translater/releases/latest) · [License](LICENSE)

## What NMT does

NMT listens to one audio source, turns speech into text, and shows the original words beside a translation. It is designed for in-person meetings, Tencent Meeting, Microsoft Teams and video playback.

When local speech and translation models are selected, audio, text and models stay on your Mac. The current release focuses on text subtitles; speech output is not included yet.

Current release: **v0.2.21** · Apple Silicon Mac (arm64) · native macOS app

## What you can use

- Chinese ↔ Japanese, Chinese ↔ English, and English ↔ Japanese.
- Automatic source-language detection inside the selected language pair.
- Quick source-language buttons when you want to correct the automatic choice.
- Continuous speaker paragraphs, recognition corrections, translation beside the original, and scrollable history.
- Optional anonymous speaker labels.
- A translucent subtitle window that can stay on top, move, resize, or show only the original or only the translation.
- Chinese, Japanese and English interface languages.
- Light mode, dark mode, or follow the Mac system appearance.
- Ollama, llama.app or SGLang for local text translation.
- Apple SpeechAnalyzer, MLX Whisper or SenseVoice for local speech recognition.
- Local model status, Ollama status, warm-up progress and microphone input level.
- Settings apply after saving; you do not need to restart the app.

## Before you download

You need:

- An Apple Silicon Mac. The current package is built for arm64; Intel Macs are not supported by this package.
- macOS microphone permission.
- A speech-recognition engine and model. Apple SpeechAnalyzer needs macOS 26 or later; Whisper and SenseVoice use local model files.
- A local translation service. Ollama is the easiest choice for most users.
- For Tencent Meeting, Microsoft Teams or browser audio, a virtual audio device such as BlackHole or Loopback.

The app package does not include model weights. This keeps the download smaller and lets you choose where models are stored.

## Download and open the app

1. Open the [latest release page](https://github.com/elizzzzzz/Neo-Meeting-Translater/releases/latest).
2. Download **NMT-portable.zip** for the no-install version. Open the ZIP, then double-click **NMT.app**.
3. Download **NMT.pkg** if you want a normal installer. Double-click it and follow the macOS installation steps.
4. Or download **NMT.dmg**, open it, and drag **NMT.app** to the **Applications** shortcut.
5. Start NMT from Applications and allow microphone access when macOS asks.
6. NMT opens as a native Mac window. It does not open a browser.

The release also contains **NMT-0.2.21.sha256**. To check a download, put the checksum file beside the ZIP, DMG and PKG and run:

~~~bash
shasum -a 256 -c NMT-0.2.21.sha256
~~~

The installer currently has no Apple Developer ID signature or Apple notarization. If macOS cannot verify the developer or safety of `NMT.pkg` or `NMT.app` on first opening:

1. Try opening the file, then dismiss the warning.
2. Open **System Settings → Privacy & Security** and scroll to **Security**.
3. Click **Open Anyway** beside the NMT warning, authenticate with your password or Touch ID, and confirm **Open**.
4. If you allowed the installer, finish installing and open NMT. If the app is also blocked, repeat these steps for the app.

Allow NMT individually; you do not need to disable system security. The app extracted from the portable ZIP follows the same first-opening steps.

## Speaker recognition and paragraphs

Choose **Automatic speaker split (test)** to distinguish voices with a local speaker model. This option is unavailable without the model; use **Manual speaker change** instead. Voice labels do not identify real names.

A confirmed voice change starts a new paragraph. A pause followed by the same speaker keeps the existing paragraph. Automatic detection needs enough speech and repeated confirmation; short interjections, similar voices and overlapping speech may be misclassified. It is not a substitute for manually verified meeting minutes.

## First setup in the app

1. Open **Settings**.
2. Under **Speech recognition**, choose Apple SpeechAnalyzer, Whisper or SenseVoice.
3. Under **Translation**, choose Ollama, llama.app or SGLang.
4. Choose a language pair: Chinese–Japanese, Chinese–English or English–Japanese.
5. Choose the microphone or audio-loopback input.
6. Click **Save and return**.
7. Wait until the status says the speech and translation models are ready, then click **Start**.

You can change the model, service, model folder, language pair and appearance later. The change is applied after saving. Existing model files are not moved automatically.

## Ollama setup

Ollama is the recommended translation service for most users. NMT connects to Ollama on this Mac at **http://127.0.0.1:11434**.

### Install and start Ollama

Download Ollama from [ollama.com](https://ollama.com/download/mac), open the Mac app, and leave it running. NMT also provides an **Install Ollama** action in Settings.

To check it in Terminal:

~~~bash
ollama --version
ollama list
~~~

If ollama list works, the local service is usually ready. In NMT Settings, click **Check again** and confirm that Ollama is installed and connected.

### Choose a translation model by memory and measured results

The tables separate **M3 / 16 GiB** and **M5 / 32 GiB** text translation tests so you can choose quality, waiting time and memory headroom. Other chips with the same memory need not have the same speed. Every listed configuration completed 144 cases covering all six Chinese, Japanese and English translation directions.

Overall = 85% quality + 10% speed + 5% collection completion. Compare overall scores within each test round, not across these two machines. Quality is a label-hidden AI-assisted review against fixed references and fact checklists, without independent human translator review; it is **not speech recognition accuracy or a sentence correctness percentage**. These are provisional snapshots; small score differences are not proven advantages.

#### 16G: Apple M3, November 9–12, 2026

| Model, precision and service | Overall /100 | Quality /100 | Mean TPS | Median sentence latency (s) | P95 latency (s) | Peak RSS (GiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3-4B-Instruct-2507 Q4_K_M · llama.cpp | 92.59 | 92.29 | 31.56 | 1.59 | 2.19 | 3.11 |
| Qwen3-4B-Instruct-2507 Q4_K_M · Ollama | 91.56 | 92.29 | 29.51 | 1.79 | 2.60 | 3.18 |
| Qwen3-4B-Instruct-2507 4bit · SGLang MLX | 90.42 | 92.40 | 30.70 | 1.61 | 6.22 | 4.59 |
| Hy-MT2 7B Q4_K_M · llama.cpp | 90.01 | 95.26 | 16.79 | 3.32 | 6.70 | 6.64 |
| Qwen3.5 4B Q4_K_M · llama.cpp | 89.66 | 93.44 | 21.35 | 2.30 | 4.89 | 4.40 |
| Qwen3 4B Q4_K_M · Ollama | 87.34 | 90.18 | 20.58 | 2.64 | 3.85 | 3.09 |
| TranslateGemma 4B Q8_0 · Ollama | 83.41 | 85.85 | 20.92 | 2.73 | 3.42 | 4.62 |
| TranslateGemma 4B Q4_K_M · Ollama | 81.38 | 87.24 | 9.50 | 5.95 | 11.26 | 3.02 |

- **For subtitle speed**: consider Qwen3-4B-Instruct-2507 Q4_K_M. Ollama is easier to set up; llama.cpp was faster in this round. This checkpoint differs from ordinary `qwen3:4b`.
- **For translation quality**: Hy-MT2 7B Q4_K_M / llama.cpp scored 95.26 for quality, with 3.32 s median sentence latency. Its Ollama median was 11.74 s; do not apply the llama.cpp result to Ollama.
- Qwen3.5 4B Q4_K_M / llama.cpp is another compromise to try. TranslateGemma 4B results are included for comparison; it is not the default choice. TranslateGemma 12B and Qwen2.5 3B were not measured in this round and are not recommended on the basis of these results.

This is a selection of reviewed configurations. See the [full 16G results and conditions](docs/model-benchmark-2026-11-09-m3-16gb.md) and [per-configuration latency and memory data](docs/benchmarks/2026-11-09-m3-16gb/configuration-metrics.csv) for more choices.

#### 32G: Apple M5, November 13–19, 2026

| Model, precision and service | Overall /100 | Quality /100 | Mean TPS | Median sentence latency (s) | P95 latency (s) | Peak RSS (GiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3 30B-A3B Q4_K_M · Ollama | 95.39 | 94.58 | 53.26 | 1.03 | 1.38 | 17.67 |
| Qwen3.5-4B 4bit · SGLang MLX | 92.94 | 93.74 | 38.80 | 1.25 | 1.73 | 5.35 |
| Qwen3.5 9B Q4_K_M · Ollama | 91.37 | 96.25 | 21.81 | 2.32 | 3.19 | 7.94 |
| Qwen3.5-4B 8bit · SGLang MLX | 89.38 | 93.58 | 21.56 | 2.16 | 3.11 | 7.48 |
| Qwen3-8B 4bit · SGLang MLX | 89.28 | 92.83 | 26.40 | 1.88 | 2.67 | 6.55 |
| Qwen3-VL-8B 8bit · SGLang MLX | 87.38 | 93.17 | 14.52 | 3.32 | 4.66 | 4.20 |
| Qwen3-8B 8bit · SGLang MLX | 87.00 | 92.81 | 14.39 | 3.33 | 4.77 | 5.49 |

- **For quality and room for speech recognition and meeting apps**: try Qwen3.5 9B Q4_K_M / Ollama first. It had the highest quality score in this round, with 2.32 s median sentence latency.
- **For speed with more memory available**: consider Qwen3 30B-A3B Q4_K_M / Ollama. Median latency was 1.03 s, but sampled peak RSS was 17.67 GiB and peak system swap was 1.47 GiB. A3B does not mean only 3B of weights must be loaded; this is not a recommendation for 16G.
- **If you already run SGLang MLX**: Qwen3.5 4B 4bit is a low-latency candidate. This run needed a compatibility patch and reached 10.46 GiB system swap (11.91 GiB for 8bit); retest under clean load. Low RSS alone does not establish enough memory headroom.

Only the 7 fully quality-reviewed configurations are listed here. The [full 32G report](docs/model-benchmark-2026-11-19-m5-32gb.md) and [per-configuration data](docs/benchmarks/2026-11-19-m5-32gb/configuration-metrics.csv) also cover incomplete reviews, failures and slower configurations. The 9B and 30B-A3B configurations still had critical errors in 7/144 and 8/144 cases respectively; high scores do not mean error-free translation.

**Reading the measurements**: median latency is typical waiting time for a complete translation; P95 is the time within which about 95% of cases finished. TPS measures generation speed, not waiting time. RSS samples resident memory of the service process tree, not the full unified-memory budget; swap is system-wide. Tests exclude speech recognition, audio segmentation, cold starts and subtitle rendering, and do not validate sustained parallel speech recognition and translation. llama.cpp was tested directly, not through llama.app; changing service, template or quantization needs another trial. These are translation models; choose a speech recognition engine separately.

### Install the model you choose

For **Qwen3-4B-Instruct-2507 Q4_K_M** on 16G, download a GGUF conversion of that checkpoint. You can load it in llama.app and enable its local server. For Ollama, create a text file named `Modelfile` containing the actual path:

~~~text
FROM /full/path/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
~~~

Run from the folder containing `Modelfile` (use the actual filename; quote paths containing spaces):

~~~bash
ollama create nmt-qwen3-4b-2507 -f Modelfile
ollama list
~~~

Check the [original model page](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), the conversion publisher and its license when selecting a Q4_K_M file. `nmt-qwen3-4b-2507` is a local name you create, not a public download tag. The benchmark used fixed files and templates; a newly downloaded conversion need not reproduce its scores.

For either of these 32G Ollama choices, **run only the download command for your chosen model**:

~~~bash
ollama pull qwen3.5:9b-q4_K_M
~~~

Or:

~~~bash
ollama pull qwen3:30b-a3b-q4_K_M
~~~

In NMT Settings select the matching translation service and exact model name shown by `ollama list`, then click **Save and return**. Wait for readiness on the first load. Run these commands yourself when ready; they do not automatically replace existing models.

### Model folder

Ollama normally manages its own model folder. In NMT Settings, click **Use Ollama current folder** to fill in the detected folder. You can choose another folder for ASR files or other local resources.

Changing NMT's folder field does not move models managed by Ollama. To move Ollama's model storage, change Ollama's own storage setting, restart Ollama, then click **Check again** in NMT.

### If Ollama is unavailable

1. Open the Ollama app and wait a few seconds.
2. Run **ollama list** in Terminal.
3. Check that NMT uses the service **Ollama** and address **http://127.0.0.1:11434**.
4. Click **Check again**.
5. Make sure the selected model name exactly matches **ollama list**.
6. If the model is missing, download or import the model you chose above, then select its exact local name.
7. If you changed the storage location, restart Ollama and check again.

NMT only connects to local loopback services. It does not send meeting audio or transcript text to a remote translation server.

## Meeting and browser audio

### Mac microphone

Choose the built-in microphone or headset microphone in NMT, allow permission, and click **Start**.

### Tencent Meeting, Microsoft Teams or browser video

1. Install BlackHole 2ch or Loopback.
2. Set the meeting or video app's speaker output to that virtual device.
3. In NMT, choose the same device as the input.
4. Click **Start**.

If you also want to hear the meeting, create a macOS Multi-Output Device that includes your headphones and the virtual audio device.

NMT reads one input device at a time. To combine your microphone and remote participants, use an external mixer or a virtual device that provides a combined input.

## Subtitle mode

Click **Subtitle mode** to open the compact floating window. Move it to an empty area of the meeting window. It can show both columns, the original only, or the translation only.

Older paragraphs remain available by scrolling. The newest paragraph stays at the bottom. Recognition corrections update the current paragraph instead of rapidly deleting the whole history.

## Privacy and limits

- Audio, recognized text, translations and model files stay local when local engines are selected.
- NMT does not use Tencent Meeting or Teams cloud transcription.
- Recognition can be wrong in noisy rooms, with quiet speech or overlapping speakers.
- Speaker labels are anonymous and cannot show meeting participant names.
- Latency depends on the model, sentence length and Mac workload. The one-second recognition plus one-second translation target is a goal, not a guarantee.
- The current release prioritizes text. Translation speech output is not available yet.

## Commercial use and attribution

NMT's original code and documentation are released under the [Apache License 2.0](LICENSE). Commercial use, modification and redistribution are allowed under that license.

When redistributing NMT, include LICENSE, NOTICE and applicable third-party notices. Please keep this attribution:

> Based on NMT (Neo Meeting Translater) by elizzzzzz and contributors. Source: https://github.com/elizzzzzz/Neo-Meeting-Translater

Models, Apple system resources, Ollama, audio drivers and other third-party components keep their own licenses. Check the model license before commercial deployment.

For help, open an issue with the app version, macOS version, selected models and the exact status message. Remove private meeting content before sharing logs.
