# NMT · Neo Meeting Translater

## Visual direction · 2026-11-08

The user requested an LM Studio inspired redesign and the product name **NMT
(Neo Meeting Translater)**. The spelling “Translater” is intentional. The new
workspace replaces the previous Apple pearl/blue appearance. Reference: official
LM Studio product site, https://lmstudio.ai/, inspected on 2026-11-08. Adapt its
quiet desktop workspace, compact tool rail and purple identity to live bilingual
transcription; do not copy its logo or add nonfunctional chat navigation.

The local `awesome-design-md` catalog has no LM Studio entry. Supplementary
reference: `linear.app`, upstream revision
`3b605329240ce735b510037cca322f1831fdd7f8`, for restrained surface hierarchy and
sparse lavender accents. This is a product workspace, not a marketing page.

### Tokens and composition

- Canvas `#18191d`, tool rail `#141519`, surface `#202126`, raised `#282930`.
- Text `#e8e8ed`, secondary `#a2a3b1`, quiet `#7e8090`, dividers `#36373f`.
- Accent `#b5a2fa` / hover `#ccbdff`; success `#86d8af`, warning `#e6c18b`.
- System SF Pro / Hiragino Sans / PingFang SC; 16px transcript with 1.9 line
  height, 12px controls, 10–11px metadata. No downloaded fonts or remote assets.
- 64px left tool rail, 56px identity/status bar, compact language toolbar;
  transcript takes the remaining height with equal language columns. A quiet
  184px status rail retains diagnostics. Corners 5–10px, spacing 4/8/12/16/24px.
- Use a custom NMT monogram, sparse lavender accents and monochrome line icons.
  Icon actions retain localized accessible labels and native hover tooltips.
- At 1024px, shrink status rail to 160px. Below 760px, use a 48px tool rail,
  wrap controls and hide the secondary diagnostic rail. Preserve two columns.
- Hover changes take 120ms; reduced-motion disables transitions. No animated
  background, gradients, or decorative motion competing with the transcript.

Status values use plain language and explicit stages: configured, loading, ready, receiving audio, and error. Model names remain visible in the session panel so a user can distinguish microphone, ASR, Ollama, and translation failures.

## Onboarding and offline preview

Use the NMT surface scale, localized labels and one lavender primary action. Tips and local settings appear as keyboard-accessible dialogs with Escape support. Preview explicitly uses sample text; never label it as warmed or ready for live recognition. Settings are persisted in Application Support independently of the local service port. Model directory editing must survive health polling. Show the speech model cache separately from Ollama-managed translation files until directory migration is supported.

## Audio diagnostics

Show the microphone's actual track name after permission, a compact native input meter with Chinese signal labels, and the server-confirmed recognition language. The meter indicates sound energy, not proof of recognized speech. Keep all twelve status rows within the existing single-screen panel. Keep audio device and model settings editable during recording; saving applies them through the controlled pause/resume flow. Keep the source-language correction buttons available; show the active decoder language after the service confirms the ordered change. Rejected recognition is explained in the diagnostic row and never inserted as a subtitle.

## Persistent bilingual speech

Use one paragraph per consecutive speaker turn, with a compact speaker/time line above equal-width source and translation columns. Keep the columns side by side in the main window and floating window. A bounded recognition chunk can be revised without replacing completed chunks. Keep the previous translation visible while a correction is pending. Retain every paragraph until the user clears the transcript; export uses the same grouping. The transcript alone scrolls, and following pauses when the user scrolls into history. A small lavender “回到最新” action resumes following. Automatic voice identification is explicitly marked as experimental and is only selectable when its local model has loaded; otherwise show manual boundaries in plain Chinese.

Keep the optional speech-engine choice inside local settings. Use the Chinese description “语音转文字引擎”; display the SenseVoice model's local availability and state that saving applies settings automatically. Keep Whisper available for Japanese comparisons. Model selection never downloads weights implicitly.

## Conversation-first ready state

Show the introduction and a bounded progress indicator only while local models
are preparing. Once ready, hide the introduction and footer; retain only the compact NMT identity/status bar. Keep
one compact language-pair toolbar, recording controls, transcript, settings, and
the icon-based status rail. Move audio device, speaker detection, and explicit
interface language choices into settings; automatic interface language follows
the system and manual Chinese/Japanese/English choices persist across ports.

Meeting language pairs default to automatic source detection and route the
translation to the other member. Offer compact buttons for Auto and the two
selected meeting languages; the source override preserves the pair and column
positions. Use one Source/Translation badge per column at the paragraph start,
not per decoder chunk. A mixed-language turn uses one combined badge; individual
chunks retain their role in a hover description. A timed-out translation retains
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


Model-folder controls use the compact NMT settings surface. Default to
Ollama's detected storage folder and offer one secondary “Use Ollama folder”
action next to the folder picker. Rescan an edited path before saving, retain
manual edits during health polling, and show missing disks separately from
missing weights. Saving a changed configuration applies it automatically;
service-managed files remain owned by Ollama / llama.app.


## Stable speech paragraphs and quick corrections

Keep a paragraph identity independent of ASR chunks, pauses and initial pending
speaker labels. Only a confirmed speaker change, a manual boundary or a new
session starts a new speech paragraph. Speaker clustering requires sustained
agreement; two brief inconsistent probes do not create a new voice identity.
Keep existing scroll position and history during source-language corrections.
Use compact 30px source buttons with visible selection and keyboard focus. Show
only Auto and the two languages in the current meeting pair, preserving space
for captions. Live selection is confirmed after already accepted audio has
finished processing; an expired native job must finish before decoder mutation.


## Apple speech recognition

Add Apple SpeechAnalyzer to the existing speech-engine selector; preserve the
compact model/service settings layout. Explain the macOS 26 requirement, local
recognition, system-owned language storage and independent translation model.
Show each language's resource state and one explicit preparation button. Show
preparation and failures inside the speech card even when optional Ollama tools
are collapsed. A directory change must not suggest that Apple assets moved.
Label app-level bilingual candidate comparison as experimental and keep source
language correction buttons available. Missing assets block capture with an
actionable message rather than silently selecting a different recognizer.


## Apply settings without restarting

Keep model editing available during recording. Saving finishes the old audio
session, keeps the transcript, and shows bounded preparation progress while
replacing the engines. Resume the microphone only after the saved revision is
ready; the Stop action cancels that pending resume. Show save success separately
from model loading failure, with the exact actionable error in the settings
receipt. Do not ask the user to restart. Updating model lists remains read-only.

## Rename compatibility

Display NMT in the workspace, native window, Finder bundle and new archive names.
Keep the existing bundle identifier, internal executable and Application Support
directory to retain microphone permissions, saved paths and single-instance
behavior across upgrades. Existing released archives keep their historical names.


## Light, dark and system appearance · 0.2.19

Keep the same transcript geometry, lavender identity, icons and spacing in both
styles. Supplementary local reference: `apple`, same upstream revision, for quiet
white/pearl surfaces; preserve NMT's own accent instead of adopting Apple blue.
Light canvas `#f4f4f7`, rail `#ecebf1`, surface `#ffffff`, ink `#24232b`, muted
`#64616f`, dividers `#dcdbe3`, accent `#7053c1`. Semantic status, speaker and
translation colors have separate contrast-appropriate light/dark tokens.

The sidebar sun/moon action switches to the opposite effective appearance and
pins that manual choice. Settings offers Light, Dark and Follow system (default).
Changes apply immediately and persist independently of model settings, tips and
interface language. Native window chrome follows the same choice; system mode
inherits live macOS appearance changes. The floating window uses a matching
translucent surface and readable foreground in both modes. Appearance updates
must not re-render transcript nodes, move the user's history position, restart
recording or reload models. Resolve the saved mode before the first stylesheet
paint where local storage is available. Keep all labels localized in zh/ja/en.
