# Local Meeting Interpreter UI

Visual reference: the local Apple design reference (`awesome-design-md/design-md/apple`).

The app keeps the existing Apple inspired language: SF Pro system fallbacks, white surfaces on a pearl canvas, Action Blue `#0066cc`, 11px panel corners, fine `#e0e0e0` dividers, and restrained status chips. Runtime diagnostics are intentionally compact and use the same caption scale so they support troubleshooting without competing with the live transcript.

Status values use plain language and explicit stages: configured, loading, ready, receiving audio, and error. Model names remain visible in the session panel so a user can distinguish microphone, ASR, Ollama, and translation failures.

## Onboarding and offline preview

Preserve the Apple reference at revision `3b605329240ce735b510037cca322f1831fdd7f8`. Use compact Chinese labels, a single blue primary action, and the existing pearl surfaces. Tips and local settings appear as keyboard-accessible dialogs with Escape support. Preview explicitly uses sample text; never label it as warmed or ready for live recognition. Settings are persisted in Application Support independently of the local service port. Model directory editing must survive health polling. Show the speech model cache separately from Ollama-managed translation files until directory migration is supported.

## Audio diagnostics

Show the microphone's actual track name after permission, a compact native input meter with Chinese signal labels, and the server-confirmed recognition language. The meter indicates sound energy, not proof of recognized speech. Keep all twelve status rows within the existing single-screen panel. Lock input and language controls during recording so the visible settings match the active decoder; stop recording to change them. Rejected recognition is explained in the diagnostic row and never inserted as a subtitle.
