# 0.2.14 — background noise gate and core-speaker pickup

This release adds a local adaptive voice gate before ASR. It learns the recent
steady room-noise floor per capture session, suppresses inactive frames, and
keeps a voice that rises above that floor. It applies to microphone and local
meeting loopback audio, including Ollama/Qwen3-ASR and built-in ASR paths.

- Browser capture requests echo cancellation, noise suppression, automatic gain
  control and voice isolation when supported by macOS/WebKit.
- The local gate uses short energy frames, a conservative absolute floor, and a
  relative rise above the learned background. It does not upload audio or alter
  model files.
- Live status now reports “background quiet / waiting” versus “core speaker
  captured” while preserving the existing timeout and subtitle flow.

Validation:

- Steady background at approximately -49 dBFS is filtered and never reaches the
  recognizer; a far-field voice at approximately -38 dBFS remains eligible.
- 41 pipeline/live-audio tests and 45 frontend tests pass.
- This is an energy gate, not full beamforming or source separation. A second
  nearby speaker with similar loudness can still be recognized; microphone
  placement and macOS input gain remain important.
