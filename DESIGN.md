# Local Meeting Interpreter UI

Visual reference: the local Apple design reference (`awesome-design-md/design-md/apple`).

The app keeps the existing Apple inspired language: SF Pro system fallbacks, white surfaces on a pearl canvas, Action Blue `#0066cc`, 11px panel corners, fine `#e0e0e0` dividers, and restrained status chips. Runtime diagnostics are intentionally compact and use the same caption scale so they support troubleshooting without competing with the live transcript.

Status values use plain language and explicit stages: configured, loading, ready, receiving audio, and error. Model names remain visible in the session panel so a user can distinguish microphone, ASR, Ollama, and translation failures.

## Onboarding and offline preview

Preserve the Apple reference at revision `3b605329240ce735b510037cca322f1831fdd7f8`. Use compact Chinese labels, a single blue primary action, and the existing pearl surfaces. Tips and local settings appear as keyboard-accessible dialogs with Escape support. Preview explicitly uses sample text; never label it as warmed or ready for live recognition. Settings are persisted in Application Support independently of the local service port. Model directory editing must survive health polling. Show the speech model cache separately from Ollama-managed translation files until directory migration is supported.

## Audio diagnostics

Show the microphone's actual track name after permission, a compact native input meter with Chinese signal labels, and the server-confirmed recognition language. The meter indicates sound energy, not proof of recognized speech. Keep all twelve status rows within the existing single-screen panel. Lock input and language controls during recording so the visible settings match the active decoder; stop recording to change them. Rejected recognition is explained in the diagnostic row and never inserted as a subtitle.

## Persistent bilingual speech

Use one paragraph per consecutive speaker turn, with a compact speaker/time line above equal-width source and translation columns. Keep the columns side by side in the main window and floating window. A bounded recognition chunk can be revised without replacing completed chunks. Keep the previous translation visible while a correction is pending. Retain every paragraph until the user clears the transcript; export uses the same grouping. The transcript alone scrolls, and following pauses when the user scrolls into history. A small blue “回到最新” action resumes following. Automatic voice identification is explicitly marked as experimental and is only selectable when its local model has loaded; otherwise show manual boundaries in plain Chinese.

Keep the optional speech-engine choice inside local settings. Use the Chinese description “语音转文字引擎”; display the SenseVoice model's local availability and state that applying settings requires reopening the App. Keep Whisper available for Japanese comparisons. Model selection never downloads weights implicitly.

## Conversation-first ready state

Show the introduction and a bounded progress indicator only while local models
are preparing. Once ready, hide the introduction, brand strip, and footer. Keep
one compact language-pair toolbar, recording controls, transcript, settings, and
the icon-based status rail. Move audio device, speaker detection, and explicit
interface language choices into settings; automatic interface language follows
the system and manual Chinese/Japanese/English choices persist across ports.

Meeting language pairs always use automatic source detection and route the
translation to the other member. Keep language columns fixed and use full
Source/Translation role badges for each chunk. A timed-out translation retains
its source and an explicit skipped marker; never imply complete meeting coverage
after audio or translation was dropped. Real-time inference and translation
share a capture deadline below five seconds rather than extending each stage.

## Independent model services

Keep speech recognition and translation in two equal settings cards. Each card
has its own service, loopback address, model list, and status; they can use
different services. Use “语音识别 · 声音转文字” and “文字翻译 · 中日英互译”
instead of technical abbreviations. Filter model choices by audio/text roles.
Distinguish files found, service connected, model preparing, and ready; discovery
never means warmed. Collapse optional Ollama installation tools below the cards.
Save/restart feedback stays visible independently of the collapsed tools. Retain
the conversation layout and local-only routing. Model-directory controls cover
built-in caches; Ollama and llama.app retain ownership of their model files.


Model-folder controls keep the existing compact Apple settings style. Default to
Ollama's detected storage folder and offer one secondary “Use Ollama folder”
action next to the folder picker. Rescan an edited path before saving, retain
manual edits during health polling, and show missing disks separately from
missing weights. Loading a changed configuration requires saving and restarting;
service-managed files remain owned by Ollama / llama.app.
