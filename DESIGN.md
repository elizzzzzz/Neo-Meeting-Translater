# Local Meeting Interpreter UI

Visual reference: the local Apple design reference (`awesome-design-md/design-md/apple`).

The app keeps the existing Apple inspired language: SF Pro system fallbacks, white surfaces on a pearl canvas, Action Blue `#0066cc`, 11px panel corners, fine `#e0e0e0` dividers, and restrained status chips. Runtime diagnostics are intentionally compact and use the same caption scale so they support troubleshooting without competing with the live transcript.

Status values use plain language and explicit stages: configured, loading, ready, receiving audio, and error. Model names remain visible in the session panel so a user can distinguish microphone, ASR, Ollama, and translation failures.
