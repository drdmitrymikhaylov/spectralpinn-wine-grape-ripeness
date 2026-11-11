"""Pins the README section "Checking §2" to results/within_variety_check.json
(written by src/within_variety_check.py) and results/exp1_rgb_vs_nir.json.
No dataset is needed.
"""

import json
import os
from decimal import ROUND_HALF_UP, Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
FLAT = " ".join(README.split())
EXP1 = json.load(open(os.path.join(ROOT, "results", "exp1_rgb_vs_nir.json")))
WVC = json.load(open(os.path.join(ROOT, "results",
                                  "within_variety_check.json")))

VARIETIES = ["FER", "MAUZAC", "SYRAH"]
FEATURES = ["rgb", "lab", "vis", "red_edge", "nir", "full", "water"]
LABEL = {"rgb": "colour camera (RGB)", "lab": "L\\*a\\*b\\*", "vis": "visible",
         "red_edge": "red edge", "nir": "near-infrared", "full": "all bands",
         "water": "water index"}
RATIO_ROWS = [f"{m}|{v}" for v in VARIETIES
              for m in ("vis", "nir", "full", "water")]


def r(x, nd=1):
    """Round half up, as a reader would."""
    q = Decimal(1).scaleb(-nd)
    return str(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def within_row(name):
    cells = [WVC["cells"][f"{name}|{v}"] for v in VARIETIES]
    return (f"| {LABEL[name]} | " + " | ".join(
        f"{r(c['rmse_mean_gl'])} ± {r(c['rmse_sd_over_repeats_gl'])}"
        for c in cells) + " |")


def ratio_row(key):
    c = WVC["ratios"][key]
    name, v = key.split("|")
    lo, hi = c["tray_bootstrap_ci95"]
    return (f"| {v} | {LABEL[name]} | {r(c['rgb_over_model_mean_of_means'], 2)} | "
            f"{r(c['paired_by_repeat_min'], 2)}-{r(c['paired_by_repeat_max'], 2)} | "
            f"{c['repeats_with_model_ahead']} of 10 | "
            f"[{r(lo, 2)}, {r(hi, 2)}] | "
            f"{r(100 * c['tray_bootstrap_fraction_above_1'], 0)}% |")


def test_every_cell_reproduces_the_stored_within_variety_table():
    assert len(WVC["cells"]) == 21
    for key, c in WVC["cells"].items():
        name, v = key.split("|")
        assert abs(c["rmse_mean_gl"] - EXP1["within"][name][v]["rmse_gl"]) < 1e-4
        assert c["reproduces_stored"]
        assert len(c["rmse_per_repeat_gl"]) == WVC["config"]["n_repeats"] == 10
        assert c["n_trays"] == EXP1["config"]["varieties"][v]


def test_within_table_rows():
    for name in FEATURES:
        assert within_row(name) in README, within_row(name)


def test_ratio_table_rows():
    for key in RATIO_ROWS:
        assert ratio_row(key) in README, ratio_row(key)


def test_the_factor_of_two_is_a_syrah_statement():
    s = WVC["ratios"]["nir|SYRAH"]
    assert r(s["rgb_over_model_mean_of_means"], 2) == "1.94"
    assert r(s["paired_by_repeat_min"], 2) == "1.73"
    assert r(s["paired_by_repeat_max"], 2) == "2.03"
    assert s["repeats_with_model_ahead"] == 10
    lo, hi = s["tray_bootstrap_ci95"]
    assert r(lo, 2) == "1.58" and r(hi, 2) == "2.45"
    assert r(100 * s["tray_bootstrap_fraction_above_2"], 0) == "46"
    assert "1.73 to 2.03" in FLAT and "[1.58, 2.45]" in FLAT
    assert "above 2 in 46%" in FLAT
    f = WVC["ratios"]["nir|FER"]
    assert r(f["rgb_over_model_mean_of_means"], 2) == "1.09"
    assert f["repeats_with_model_ahead"] == 9
    assert r(f["tray_bootstrap_ci95"][0], 2) == "0.91"
    m = WVC["ratios"]["nir|MAUZAC"]
    assert r(m["rgb_over_model_mean_of_means"], 2) == "1.06"
    assert r(m["tray_bootstrap_ci95"][0], 2) == "0.96"
    assert "9% on FER" in FLAT and "6% on MAUZAC" in FLAT
    # on FER the gain is in the visible, not the infrared
    best = WVC["best_within_variety"]
    assert best["FER"]["feature_set"] == "full"
    assert r(best["FER"]["rgb_over_best"], 2) == "1.34"
    assert r(WVC["ratios"]["vis|FER"]["rgb_over_model_mean_of_means"], 2) == "1.30"
    assert best["SYRAH"]["feature_set"] == "nir"
    assert best["MAUZAC"]["feature_set"] == "nir"


def test_nothing_reads_sugar_within_the_white_grape():
    cells = {n: WVC["cells"][f"{n}|MAUZAC"] for n in FEATURES}
    sd = cells["rgb"]["sd_gl"]
    assert r(sd) == "33.7"
    lo = min(c["rmse_mean_gl"] for c in cells.values())
    hi = max(c["rmse_mean_gl"] for c in cells.values())
    assert r(lo) == "27.4" and r(hi) == "34.3"
    assert "between 27.4 and 34.3 g/L" in FLAT
    # ratio of SD to RMSE, the spectroscopist's RPD, for the best and worst
    assert r(sd / lo, 2) == "1.23" and r(sd / hi, 2) == "0.98"
    assert "1.23" in FLAT and "0.98" in FLAT
    # the visible bands and the water index are behind the camera there
    assert WVC["ratios"]["vis|MAUZAC"]["rgb_over_model_mean_of_means"] < 1
    assert WVC["ratios"]["water|MAUZAC"]["rgb_over_model_mean_of_means"] < 1
    assert r(WVC["ratios"]["water|MAUZAC"]["rgb_over_model_mean_of_means"], 2) == "0.85"
    assert WVC["ratios"]["water|MAUZAC"]["repeats_with_model_ahead"] == 0


def test_repeat_spread_is_small_against_the_tray_spread():
    # over repeats the SYRAH cells move by a few tenths of a g/L; over
    # resampled trays the near-infrared cell moves by g/L
    for name in FEATURES:
        c = WVC["cells"][f"{name}|SYRAH"]
        assert c["rmse_sd_over_repeats_gl"] < 0.7
    lo, hi = WVC["ratios"]["nir|SYRAH"]["model_rmse_tray_bootstrap_ci95_gl"]
    assert r(lo) == "8.4" and r(hi) == "13.1"
    assert "[8.4, 13.1]" in FLAT
    # half-width of that interval against the spread over repeats
    assert r((hi - lo) / 2) == "2.4"
    assert r(WVC["cells"]["nir|SYRAH"]["rmse_sd_over_repeats_gl"]) == "0.5"


if __name__ == "__main__":
    for name in FEATURES:
        print(within_row(name))
    print()
    for key in RATIO_ROWS:
        print(ratio_row(key))
    s = WVC["ratios"]["nir|SYRAH"]
    print(s["model_rmse_tray_bootstrap_ci95_gl"], s["tray_bootstrap_fraction_above_2"])
    m = {n: WVC["cells"][f"{n}|MAUZAC"]["rmse_mean_gl"] for n in FEATURES}
    print(min(m.values()), max(m.values()), WVC["cells"]["rgb|MAUZAC"]["sd_gl"])
