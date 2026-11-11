# Changelog

Dated notes on what changed on this page and why. Newest first.

## 2026-11-11

- New section "Checking §2". The within-variety table of experiment 1 was
  re-run for all three varieties with the same seeds
  (`src/within_variety_check.py`, `results/within_variety_check.json`; all
  21 stored cells reproduce to 1e-4). The "factor of two" of §2 is a SYRAH
  statement: there near-infrared divides the camera's error by 1.94 (1.73
  to 2.03 over ten fold splits; resampling the 126 trays gives [1.58, 2.45],
  above 2 in 46% of resamples). On FER it buys 9% ([0.91, 1.31]) and on
  MAUZAC 6% ([0.96, 1.17]); on FER the visible bands (1.30) and the full
  spectrum (1.34) do more than the infrared. Within MAUZAC every feature set
  sits at 27.4 to 34.3 g/L against an SD of 33.7, and the visible bands and
  the water index are behind the camera. Finding 2 and the §2 paragraph
  amended. `tests/test_within_variety.py` (six tests, no dataset).
- `src/exp2_transfer.py` now skips the Q residual wherever the model has as
  many components as the feature set has columns (the four full-rank colour
  cells and the three water-index cells) and flags by T² alone, as the
  1 October caveat said it should; `results/exp2_transfer.json` and
  `results/transfer_checks.json` regenerated. Every other number reproduced
  to 1e-11. Two flag fractions moved: L\*a\*b\* on FER 4.8 to 1.6% (3 trays
  to 1 of 63), L\*a\*b\* on SYRAH 58.7 to 49.2% (74 to 62 of 126) — fourteen
  trays had been flagged by floating point. The 2-77% range and the outlier
  table are unchanged. The JSON now also carries the T² and Q fractions per
  cell. `tests/test_readme_numbers.py` updated accordingly.
- `tests/test_all.py`: the three checks that read `data/DATASET.csv` skip
  on a clone without it instead of failing (they had failed on every fresh
  clone, since the dataset is not redistributed).

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
