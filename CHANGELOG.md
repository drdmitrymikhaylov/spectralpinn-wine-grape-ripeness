# Changelog

Dated notes on what changed on this page and why. Newest first.

## 2026-10-19

- LICENSE now holds the standard MIT text and LICENSE-CONTENT the standard CC BY 4.0 text, so GitHub recognises the licence (it showed "Other" before). The terms are unchanged; the note on what each licence covers moved to `NOTICE.md`.

## 2026-10-01

- New section "Checking §3". Experiment 2 re-read from its stored results
  (`src/transfer_checks.py`, `results/transfer_checks.json`). A reference
  tray helps only when the offset is larger than the scatter around it: one
  hand-pressed tray makes the answer worse in 11 of the 18 model-variety
  cells and five trays in 6, including two rows of the §3 table (visible on
  SYRAH 27.3 to 29.4 g/L, water index 27.5 to 29.6). Break-even is about
  (floor / bias)² trays: 0.2 for near-infrared on SYRAH, 114 for the water
  index.
- The outlier test, split by statistic. Every MAUZAC tray is at least 34
  times beyond its limit; the worst red tray is at 27. But the test passes
  97% of held-out FER trays under the near-infrared model, which is biased
  by +35.4 g/L there (RMSE 44.1 against an SD of 31.9), and it flags 5 to 18%
  of trays of its own training varieties under cross-validation.
- Correction: held-out red varieties are flagged at 2-77%, not 2-60% (the
  visible model on SYRAH is at 77%).
- Caveat recorded: with three components on three channels the Q residual is
  rounding error (limit of order 1e-29), so the stored flag fractions of the
  full-rank RGB and L\*a\*b\* cells are not reproducible (1.6 to 3.2%, 4.8 to
  1.6%, 58.7 to 50.8% on refit). The stored results were not regenerated.
- `tests/test_readme_numbers.py`: eight tests pin the new section to
  `results/`. Verdict row 9 added; the "one reference measurement fixes it"
  sentence in §3 qualified.
- Three macOS `._*` files removed from the repository; `._*` ignored.
