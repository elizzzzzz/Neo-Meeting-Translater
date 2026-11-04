# 0.2.5

0.2.5 focuses on bilingual meeting readability and local setup.

- Chinese/Japanese sessions keep Chinese on the left and 日本語 on the right. Each part carries a compact `源` or `译` label based on the detected source language.
- Consecutive chunks remain in the same speaker paragraph even when the decoder changes between Chinese and Japanese.
- Ollama streaming translation commits at a readable interval and keeps the previous translation while a corrected source is being translated, reducing visible flicker.
- Stable recognition chunks can use a conservative Ollama context pass to fix likely homophones, punctuation and segmentation errors. The result is length, number and language checked before it reaches the transcript; a failed correction leaves the ASR text unchanged.
- “演示字幕” is now “字幕模式”. It opens the real, translucent floating transcript and never creates sample captions. The settings dialog controls 双栏、仅源文 and 仅译文 display.
- Local settings can inspect and explicitly install Ollama, upgrade through Homebrew, install the recommended translation model, inspect Whisper/SenseVoice availability, and prepare the local Whisper cache. No download or upgrade starts without a click.
- Online meetings and web video use a macOS loopback input such as BlackHole or Loopback. The app now explains this in Chinese settings; direct Tencent Meeting/Teams capture still depends on the selected system audio device and permissions.

Validation: Python unit tests, frontend tests, Python syntax compilation, and arm64 package checks are run before publishing the release artifacts.
