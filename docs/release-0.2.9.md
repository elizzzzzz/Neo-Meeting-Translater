# Local Meeting Interpreter 0.2.9

- Select Chinese/Japanese, Chinese/English, or English/Japanese once. Recording
  always configures automatic recognition and translates into the other language.
  Each chunk has a full source/translation badge; language columns stay fixed.
- Show the introduction and model progress during preparation. Hide them and
  the brand/footer strips after local models are ready. Audio/speaker settings
  and an explicit Auto/中文/日本語/English picker live in settings.
- Interface language is stored in Application Support, preserving the choice
  across service ports, restarts, and tip preference changes.
- Live capture, queue residence, ASR, and translation share a 4.8-second deadline.
  Expired audio is skipped; translation timeouts keep the source with a marker.
  Late output is ignored. Do not queue more jobs behind busy native inference.
- Native inference cannot be forcibly interrupted safely; while it is busy,
  incoming expired chunks are skipped and processing resumes when it returns.
  This bounds waiting/display age; it does not guarantee every utterance can be
  recognized within five seconds on the target hardware.
- Live ASR retains its context prompt. Separate serial LLM source correction is
  reserved for offline/inline processing so it cannot block the live deadline.
- Short audio transport stalls retain samples; queues beyond four seconds retain
  recent audio. Capture timestamps prevent a stale client queue receiving a new
  server deadline. Exports and session completion disclose skipped content.
- Build also refreshes the direct-open App shortcut, retaining previous releases.

Validation uses model-free recognizers, translators, timeout injection, and
Chinese/Japanese/English UI fixtures. It does not claim new real-model accuracy
or live M3 timing measurements.

Validation results: full Python suite 75 passed / 1 skipped; after adding the
unchanged-source timeout-marker regression, all 10 streaming tests passed.
All 34 frontend tests passed. UI smoke checks passed in Chinese, Japanese,
and English at 1440×900, 1280×720, and 1024×768 with no page errors or body
overflow; transcript heights were 677, 497, and 545 pixels respectively.
