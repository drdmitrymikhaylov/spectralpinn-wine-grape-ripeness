"""Pins the numbers in the README section "Checking §3" to the results files.

No dataset is needed: everything is read from results/exp2_transfer.json
(written by src/exp2_transfer.py) and results/transfer_checks.json (written
by src/transfer_checks.py).  If a result file is regenerated and a number
moves, the README row no longer matches and the test says which one.
"""

import json
import os
import sys
from decimal import ROUND_HALF_UP, Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

README = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
EXP1 = json.load(open(os.path.join(ROOT, "results", "exp1_rgb_vs_nir.json")))
EXP2 = json.load(open(os.path.join(ROOT, "results", "exp2_transfer.json")))
CHK = json.load(open(os.path.join(ROOT, "results", "transfer_checks.json")))

LABEL = {"nir": "near-infrared", "full": "all bands", "vis": "visible",
         "water": "water index", "rgb": "colour camera (RGB)"}

REFERENCE_ROWS = ["nir|SYRAH", "full|SYRAH", "nir|FER", "nir|MAUZAC",
                  "vis|FER", "rgb|SYRAH", "vis|SYRAH", "water|SYRAH"]
OUTLIER_ROWS = ["vis|FER", "vis|SYRAH", "nir|FER", "nir|SYRAH", "full|FER",
                "full|SYRAH", "vis|MAUZAC", "nir|MAUZAC", "full|MAUZAC"]


def r(x, nd=1):
    """Round half up, as a reader would."""
    q = Decimal(1).scaleb(-nd)
    return str(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def pct(x):
    return r(100 * x, 0) + "%"


def reference_row(key):
    c = CHK["break_even"]["cells"][key]
    name, v = key.split("|")
    k = c["break_even_k"]
    return (f"| {LABEL[name]} | {v} | {r(c['bias_over_floor'], 2)} | "
            f"{r(k, 1) if k < 10 else r(k, 0)} | {r(c['rmse_raw_gl'])} | "
            f"{r(c['rmse_after_1_gl'])} | {r(c['rmse_after_5_gl'])} | "
            f"{r(c['rmse_after_20_gl'])} | {r(c['rmse_floor_gl'])} |")


def outlier_row(key):
    c = CHK["outlier_test"]["cells"][key]
    e = EXP2["cells"][key]
    name, v = key.split("|")
    sev = c["severity_median"]
    return (f"| {LABEL[name]} | {v} | {pct(c['flagged_stored_in_exp2'])} | "
            f"{pct(c['flagged_by_t2'])} | {pct(c['flagged_by_q'])} | "
            f"{r(sev, 2) if sev < 10 else r(sev, 0)} | "
            f"{pct(c['same_variety_cv_flagged'])} | {r(e['pearson_r'], 2)} | "
            f"{r(e['rmse_raw_gl'] / e['test_sd_gl'], 2)} |")


def test_break_even_is_recomputed_from_exp2():
    """Part A of the check is a pure function of exp2_transfer.json."""
    from transfer_checks import part_a
    fresh = part_a(EXP2, EXP1["config"]["varieties"])
    for key, c in fresh["cells"].items():
        s = CHK["break_even"]["cells"][key]
        for f in ("rmse_raw_gl", "rmse_floor_gl", "bias_over_floor",
                  "rmse_after_1_gl", "rmse_after_5_gl", "rmse_after_20_gl"):
            assert abs(c[f] - s[f]) < 1e-9, (key, f)
        assert (c["break_even_k"] is None) == (s["break_even_k"] is None)
    assert fresh["cells_where_5_refs_worse_than_raw"] == \
        CHK["break_even"]["cells_where_5_refs_worse_than_raw"]


def test_reference_table_rows():
    for key in REFERENCE_ROWS:
        assert reference_row(key) in README, reference_row(key)


def test_reference_counts():
    a = CHK["break_even"]
    assert a["n_cells"] == 18
    assert len(a["cells_where_1_ref_worse_than_raw"]) == 11
    assert len(a["cells_where_5_refs_worse_than_raw"]) == 6
    assert "worse in 11 of the 18" in README
    assert "worse in 6" in README
    # the two rows of the §3 table where five trays hurt
    for key in ("vis|SYRAH", "water|SYRAH"):
        assert key in a["cells_where_5_refs_worse_than_raw"]
    # "after 5 refs" sits 8 to 11 % above the floor in every cell
    assert r(100 * (a["after_5_over_floor_min"] - 1), 0) == "8"
    assert r(100 * (a["after_5_over_floor_max"] - 1), 0) == "11"
    assert "8 to 11% above" in README
    # the closed form against the stored simulation
    gap = a["closed_form_max_abs_gap_fraction_of_floor_by_k"]
    assert max(gap[k] for k in ("5", "8", "12", "20", "30")) < 0.022
    assert r(100 * gap["1"], 0) == "12"
    # break-even for the water index on SYRAH: 114 of the 126 trays
    w = a["cells"]["water|SYRAH"]
    assert r(w["break_even_k"], 0) == "114" and w["n_trays"] == 126
    assert "114 trays" in README
    assert w["first_grid_k_below_raw"] is None


def test_flag_range_is_2_to_77():
    b = CHK["outlier_test"]
    assert pct(b["held_out_red_flagged_min"]) == "2%"
    assert pct(b["held_out_red_flagged_max"]) == "77%"
    assert "flagged at 2-77%" in README
    assert "flagged at 2-60%" not in README
    red = [c["diagnostics"]["flagged_fraction"] for k, c in
           EXP2["cells"].items()
           if not k.startswith("water|") and not k.endswith("|MAUZAC")]
    assert abs(max(red) - b["held_out_red_flagged_max"]) < 1e-12
    white = [c["diagnostics"]["flagged_fraction"] for k, c in
             EXP2["cells"].items()
             if not k.startswith("water|") and k.endswith("|MAUZAC")]
    assert white == [1.0] * 5


def test_outlier_table_rows():
    for key in OUTLIER_ROWS:
        assert outlier_row(key) in README, outlier_row(key)


def test_white_and_red_are_separated_by_a_wide_gap():
    b = CHK["outlier_test"]
    assert r(b["white_severity_min_over_cells"], 0) == "34"
    assert r(b["red_severity_max_over_cells"], 0) == "27"
    assert "at least 34 times" in README and "is at 27" in README
    n = EXP1["config"]["varieties"]
    assert 5 * n["MAUZAC"] == 425 and 5 * (n["FER"] + n["SYRAH"]) == 945
    assert "425" in README and "945" in README
    cells = b["cells"]
    assert pct(cells["vis|SYRAH"]["fraction_beyond_10x_limit"]) == "2%"
    meds = [c["severity_median"] for k, c in cells.items()
            if not k.startswith("water|") and not k.endswith("|MAUZAC")]
    assert r(min(meds), 1) == "0.2" and r(max(meds), 1) == "1.5"
    wmeds = [c["severity_median"] for k, c in cells.items()
             if not k.startswith("water|") and k.endswith("|MAUZAC")]
    assert r(min(wmeds), 0) == "67" and r(max(wmeds), 0) == "817"


def test_the_test_passes_a_shifted_calibration():
    e = EXP2["cells"]["nir|FER"]
    assert pct(e["diagnostics"]["flagged_fraction"]) == "3%"
    assert r(e["bias_gl"]) == "35.4" and r(e["rmse_raw_gl"]) == "44.1"
    assert r(e["test_sd_gl"]) == "31.9"
    assert e["rmse_raw_gl"] > e["test_sd_gl"]
    s = EXP2["cells"]["nir|SYRAH"]
    assert pct(s["diagnostics"]["flagged_fraction"]) == "47%"
    assert r(s["pearson_r"], 2) == "0.91"
    b = CHK["outlier_test"]
    assert pct(b["same_variety_cv_flagged_min"]) == "5%"
    assert pct(b["same_variety_cv_flagged_max"]) == "18%"
    multi = [c["same_variety_cv_flagged"] for k, c in b["cells"].items()
             if k.split("|")[0] in ("vis", "nir", "full")]
    assert pct(min(multi)) == "9%" and pct(max(multi)) == "18%"


def test_q_residual_is_rounding_error_at_full_rank():
    b = CHK["outlier_test"]["cells"]
    full_rank_colour = [k for k, c in b.items()
                        if c["full_rank"] and not k.startswith("water|")]
    assert sorted(full_rank_colour) == ["lab|FER", "lab|SYRAH", "rgb|FER",
                                        "rgb|MAUZAC"]
    for k in full_rank_colour:
        assert EXP2["cells"][k]["diagnostics"]["q_limit"] < 1e-20
        assert b[k]["q_is_numerical_zero"]
    moved = {"rgb|FER": ("1.6", "3.2"), "lab|FER": ("4.8", "1.6"),
             "lab|SYRAH": ("58.7", "50.8")}
    for k, (old, new) in moved.items():
        assert r(100 * b[k]["flagged_stored_in_exp2"]) == old, k
        assert r(100 * b[k]["flagged_either"]) == new, k
        assert old in README and new in README
    exact = [k for k, c in b.items() if not c["q_is_numerical_zero"]]
    assert len(exact) == 11
    for k in exact:
        assert abs(b[k]["flagged_stored_in_exp2"] - b[k]["flagged_either"]) < 1e-9


if __name__ == "__main__":
    for key in REFERENCE_ROWS:
        print(reference_row(key))
    print()
    for key in OUTLIER_ROWS:
        print(outlier_row(key))
