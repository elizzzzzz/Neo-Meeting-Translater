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

### Choose one model first

For an M3 Mac with 16 GB unified memory:

| Goal | Model | Simple recommendation |
| --- | --- | --- |
| Best default for live subtitles | **translategemma:4b** | Start here for Chinese, Japanese and English |
| Better long-context wording | **translategemma:12b** | Use when quality matters more than speed and memory use |
| General context correction | **qwen3:4b** | Useful for context work; check the translation style |
| Lowest-memory fallback | **qwen2.5:3b** | Use for a quick trial or a memory-constrained Mac |

Install the default model first:

~~~bash
ollama pull translategemma:4b
ollama list
~~~

Then in NMT Settings choose **Ollama**, select **translategemma:4b**, and click **Save and return**. The first sentence can be slower while the model starts. Later sentences are faster while the model stays warm.

### Model folder

Ollama normally manages its own model folder. In NMT Settings, click **Use Ollama current folder** to fill in the detected folder. You can choose another folder for ASR files or other local resources.

Changing NMT's folder field does not move models managed by Ollama. To move Ollama's model storage, change Ollama's own storage setting, restart Ollama, then click **Check again** in NMT.

### If Ollama is unavailable

1. Open the Ollama app and wait a few seconds.
2. Run **ollama list** in Terminal.
3. Check that NMT uses the service **Ollama** and address **http://127.0.0.1:11434**.
4. Click **Check again**.
5. Make sure the selected model name exactly matches **ollama list**.
6. If the model is missing, run **ollama pull translategemma:4b**.
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
\n
