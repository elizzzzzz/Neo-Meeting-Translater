# 0.2.6

0.2.6 applies the bilingual routing and subtitle rules to all supported pairs:

- Chinese ↔ Japanese, Chinese ↔ English, and English ↔ Japanese now use the same automatic two-way meeting mode.
- When source language is automatic, each recognized segment selects the other language in the chosen pair as its target. A third language is rejected before translation.
- The main and floating transcript keep the selected language order fixed. For example, English ↔ Japanese keeps English on the left and Japanese on the right, even when the Japanese participant speaks.
- Each side marks the actual segment as `源` or `译`. Source-only and translation-only display modes use the same routing.
- Historical paragraphs retain their own language pair when the user changes the pair for a later session.
- Stale translation revisions are ignored when the source text or direction has already changed.

Validation includes 29 frontend tests, 5 language-pair tests, focused Python regression suites, JavaScript syntax checking, Python bytecode compilation, and the existing macOS UI/package verification workflow.
