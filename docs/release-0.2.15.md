# 0.2.15 — continuous speech and quick source-language correction

- Source/translation badges appear once per column at the paragraph start,
  rather than on every recognition chunk. A turn containing both source
  languages uses a combined badge, with each chunk's role available on hover.
- Paragraph identity survives eight-second recognition windows, pauses, source
  language corrections and the first confirmed speaker label. Confirmed speaker
  changes, manual boundaries and new sessions create new paragraphs. Automatic
  voice clustering requires three consistent observations over at least 1.6 s;
  two brief inconsistent probes no longer create a new identity.
- Compact source-language buttons offer Auto and the two current meeting
  languages. The override works before and during recording, keeps the selected
  pair/column positions, and routes translation to the opposite member.
- Live language changes run in order after accepted audio. A timed-out native
  decode must finish before decoder settings change; late results stay hidden.
  The server confirms the applied language in the status panel.

Validation:

- 126 Python tests passed; 1 skipped. Includes ordered switches during active
  inference for all three pairs, automatic-mode restoration, recovery after a
  timed-out native job, long speech/pauses and initial voice confirmation.
- 49 frontend tests passed, including badge counts, preserved history, pending
  speaker labels, explicit paragraph boundaries and pair-preserving overrides.
- Model-free Chromium smoke checks exercised actual buttons, startup config,
  live overrides and scroll history. Chinese/Japanese/English layouts passed at
  1440×900, 1280×720 and 1024×768 with no page overflow or script errors.
- This validates control flow and rendering; it does not measure real-world
  speaker identification accuracy. No model download or microphone recording
  was needed for these checks.
