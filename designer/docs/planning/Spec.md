# Spec — index and traceable items

The specification proper is `docs/designer-spec-v16.md` and its five
appendices; it is not duplicated here. This file gives the requirements that
`Tests.md` traces to a stable ID, starting with the work done since these
planning files were introduced (9 November 2026). Older behaviour is traced by
the test suite itself (1208 tests at the last run) and by `make docs`.

| Area | Where it is specified |
|---|---|
| Model, application, packaging | `docs/designer-spec-v16.md` |
| Operators and functions | `docs/designer-signature-table.md` |
| The 44 built-in validators | `docs/designer-validator-library.md` |
| Diagnostics (96 codes) | `docs/designer-diagnostics.md` |
| Interfaces and pictures | `docs/designer-interfaces.md` |
| The worked example | `docs/designer-example-notes.md` |

## CON — colour and contrast (spec §13.12)

| ID | Requirement |
|---|---|
| CON-1 | The default is black text (`#000000`) on a white background (`#ffffff`), including the theme's own surfaces. |
| CON-2 | Every foreground/background pair the application draws reaches the chosen minimum WCAG 2 contrast ratio; the default minimum is AA, 4.5:1. |
| CON-3 | Presets AA (4.5:1), AAA (7:1) and Max (21:1, pure black and white only), and a custom minimum from 4.5 to 21. Nothing below AA is offered. |
| CON-4 | The level can be raised interactively — View ▸ Contrast (presets and Custom ratio…) and Edit ▸ Preferences… — and applies at once to what is open. |
| CON-5 | The level is stored in the settings file as `contrast`; a hand-edited preset name in any case, a number, or `"N:1"` is understood, and anything else reads as AA, never an error. |
| CON-6 | A colour that already meets the minimum is unchanged; a failing one is darkened (foreground) or lightened (tint) only as far as needed, keeping its hue. |
| CON-7 | Where colour can no longer distinguish a row state or relationship, another cue stands in: italic for a state, bold for a relationship; a selection that cannot be tinted is inverted. |
| CON-8 | No colour literal appears in any application module except `palette.py`, so every colour is covered by CON-2. |

## REV — reviews requested (not requirements)

| ID | Subject | Document |
|---|---|---|
| REV-1 | Impact of moving the code base to Go | `Review-Go-and-Database.md` §A |
| REV-2 | Impact of storing the model (or the exported schema) in a database | `Review-Go-and-Database.md` §B |
