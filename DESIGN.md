# Local Meeting Interpreter Design

Source reference: `apple` from the installed awesome-design-md library.

This project adapts the reference into a focused meeting workbench rather than a marketing page. The interface prioritizes readable live captions, device routing, target-language control and clear session state.

## Visual Rules

- Surfaces: `#ffffff`, `#f5f5f7`, `#1d1d1f`, with no decorative gradients.
- Action color: `#0066cc`; use it for primary controls, links and focus states.
- Text: `SF Pro Text, system-ui, -apple-system, sans-serif`; display headings use `SF Pro Display` when available.
- Structural radii: 8px for controls, 11px for utility panels, 18px only for large workspace surfaces.
- Elevation: hairline borders and surface changes; no card shadows.
- Touch targets: minimum 44px for primary controls and device selectors.

## Layout

- Black 44px global bar with product name and runtime state.
- Light sub-navigation row with the current workflow and session action.
- Two-column desktop workspace: transcript first, session controls second.
- One-column mobile layout below 760px.
- Transcript rows use stable columns for time, speaker, source and translation.

## Interaction

- The primary action is always starting or stopping an audio session.
- Temporary captions are visibly marked as drafts; stable captions have normal contrast.
- Source and target languages remain visible while a session is active.
- Device routing is explicit: microphone and meeting loopback are separate choices.
- Export and clear actions stay secondary and never compete with the session control.
