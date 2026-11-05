# Local Meeting Interpreter 0.2.7

## UI

- Added automatic, Chinese, Japanese, and English interface languages. The automatic option follows the macOS/WKWebView locale and a manual choice is saved locally.
- Expanded the bilingual transcript area and reduced the height of the header, controls, direction bar, and diagnostics column for single-screen meetings.
- Kept the transcript as the primary scrolling region; source and translation columns remain fixed for Chinese/Japanese, Chinese/English, and English/Japanese pairs.

## Compatibility

- Existing local ASR, Ollama health, warm-start, floating caption, speaker paragraph, and export behavior is unchanged.
- Caption text is never translated by the interface language switcher.

## Validation

- `node --check web/app.js`
- `node --test tests/frontend.test.cjs` (31 tests)
- `python3 -m compileall -q src tests`
