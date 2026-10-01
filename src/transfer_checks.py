"""Two readings of experiment 2 that the page did not make.

A. When does a reference tray help?

   Offset correction from k hand-pressed trays replaces a known bias with an
   estimated one.  The estimate carries the scatter of the k trays it was
   made from, so the corrected error on the remaining trays is

       MSE(k) = S^2 * (1 + 1/k),      S^2 = sigma_res^2 * N / (N - 1),

   where sigma_res is the offset-corrected RMSE of the cell (the floor) and
   N the number of trays of the held-out variety.  Uncorrected, the error is
   sigma_res^2 + bias^2.  References therefore only help once

       k > S^2 / (sigma_res^2 + bias^2 - S^2)   ~   (sigma_res / bias)^2.

   Part A reads this off results/exp2_transfer.json for every cell, checks
   the closed form against the simulated curve stored there, and lists the
   cells where five trays leave the calibration worse than leaving it alone.
   It needs no data.

B. What does the outlier test flag, and why?

   exp2 stores one number per cell, the fraction of held-out trays flagged
   by "T^2 or Q above the 95th percentile of the training data".  Part B
   refits the same models and splits that number: flagged by T^2, flagged by
   Q, how far beyond the limit, how many trays of the *training* varieties
   the same rule rejects when they are held out by 5-fold cross-validation,
   and what the Q residual is when the model has as many components as the
   feature set has columns.  It needs data/DATASET.csv.

Writes results/transfer_checks.json.  Run from the repository root:

    python src/transfer_checks.py            # both parts
    python src/transfer_checks.py --no-data  # part A only
"""

import json
import math
import sys

sys.path.insert(0, 'src')

import numpy as np

K_GRID = [1, 2, 3, 5, 8, 12, 20, 30]
EPS = float(np.finfo(float).eps)


def break_even(cell, n):
    """Closed-form reading of one cell's reference curve."""
    res = cell["rmse_offset_corrected_gl"]
    bias = cell["bias_gl"]
    raw = cell["rmse_raw_gl"]
    s2 = res ** 2 * n / (n - 1)
    gain = res ** 2 + bias ** 2 - s2
    k_star = s2 / gain if gain > 0 else math.inf
    curve = cell["reference_curve"]
    pred = {k: math.sqrt(s2 * (1 + 1 / k)) for k in K_GRID}
    sim = {k: curve[str(k)]["rmse_gl"] for k in K_GRID}
    first = next((k for k in K_GRID if sim[k] < raw), None)
    return {
        "n_trays": n,
        "rmse_raw_gl": raw,
        "rmse_floor_gl": res,
        "bias_gl": bias,
        "bias_over_floor": abs(bias) / res,
        "break_even_k": k_star if math.isfinite(k_star) else None,
        "first_grid_k_below_raw": first,
        "rmse_after_1_gl": sim[1],
        "rmse_after_5_gl": sim[5],
        "rmse_after_20_gl": sim[20],
        "five_refs_worse_than_raw": bool(sim[5] > raw),
        "closed_form_gl": {str(k): pred[k] for k in K_GRID},
        "closed_form_minus_simulated_gl": {str(k): pred[k] - sim[k]
                                           for k in K_GRID},
    }


def part_a(exp2, n_per_variety):
    cells = {}
    for key, cell in exp2["cells"].items():
        v = key.split("|")[1]
        cells[key] = break_even(cell, n_per_variety[v])
    worse = sorted(k for k, c in cells.items() if c["five_refs_worse_than_raw"])
    worse1 = sorted(k for k, c in cells.items()
                    if c["rmse_after_1_gl"] > c["rmse_raw_gl"])
    # the stored curve is a mean of RMSEs over 200 draws, the closed form a
    # root of the mean square; by Jensen the first sits below the second
    gap = {str(k): max(abs(c["closed_form_minus_simulated_gl"][str(k)])
                       / c["rmse_floor_gl"] for c in cells.values())
           for k in K_GRID}
    ratio5 = [c["rmse_after_5_gl"] / c["rmse_floor_gl"] for c in cells.values()]
    return {
        "cells": cells,
        "n_cells": len(cells),
        "cells_where_1_ref_worse_than_raw": worse1,
        "cells_where_5_refs_worse_than_raw": worse,
        "inflation_over_floor": {str(k): math.sqrt(1 + 1 / k) for k in K_GRID},
        "after_5_over_floor_min": min(ratio5),
        "after_5_over_floor_max": max(ratio5),
        "closed_form_max_abs_gap_fraction_of_floor_by_k": gap,
        "closed_form_max_abs_gap_fraction_of_floor": max(gap.values()),
    }


def t2_q(pipe, Xtr, Xte):
    """Per-tray T^2 and Q, computed exactly as exp2_transfer.diagnostics."""
    sc = pipe.named_steps["sc"]
    pls = pipe.named_steps["pls"]
    Ztr, Zte = sc.transform(Xtr), sc.transform(Xte)
    Ttr, Tte = pls.transform(Ztr), pls.transform(Zte)
    inv = np.linalg.pinv(np.atleast_2d(np.cov(Ttr.T)))
    t2_tr = np.einsum("ij,jk,ik->i", Ttr, inv, Ttr)
    t2_te = np.einsum("ij,jk,ik->i", Tte, inv, Tte)
    q_tr = np.sum((Ztr - Ttr @ pls.x_loadings_.T) ** 2, axis=1)
    q_te = np.sum((Zte - Tte @ pls.x_loadings_.T) ** 2, axis=1)
    return t2_tr, t2_te, q_tr, q_te, float(np.sum(Ztr ** 2, axis=1).mean())


def part_b(exp2):
    from sklearn.model_selection import KFold

    from data import load
    from exp1_rgb_vs_nir import feature_sets, model
    from exp2_transfer import FEATURES, fitted

    wl, R, y, variety = load()
    F = feature_sets(wl, R)
    cells = {}
    for name in FEATURES:
        X = F[name]
        for v in sorted(set(variety)):
            te = variety == v
            pipe, ncomp = fitted(X[~te], y[~te])
            t2_tr, t2_te, q_tr, q_te, ss = t2_q(pipe, X[~te], X[te])
            lim_t2 = float(np.quantile(t2_tr, 0.95))
            lim_q = float(np.quantile(q_tr, 0.95))
            by_t2, by_q = t2_te > lim_t2, q_te > lim_q
            stored = exp2["cells"][f"{name}|{v}"]
            assert ncomp == stored["n_components"], (name, v)
            either = float((by_t2 | by_q).mean())
            stored_flag = stored["diagnostics"]["flagged_fraction"]
            # Q is a rounding residue when it sits at machine precision
            # relative to the mean squared norm of a scaled training row;
            # only then may a refit disagree with the stored fraction
            q_numerical = bool(lim_q < 1e3 * EPS * max(ss, 1.0))
            assert q_numerical or abs(either - stored_flag) < 1e-9, (name, v)

            # the same rule applied to trays of the varieties it was fitted
            # on, held out by 5-fold cross-validation
            Xin, yin = X[~te], y[~te]
            hit = np.zeros(len(yin), bool)
            for tr, ho in KFold(5, shuffle=True, random_state=0).split(Xin):
                m = model(ncomp).fit(Xin[tr], yin[tr])
                a_tr, a_ho, b_tr, b_ho, _ = t2_q(m, Xin[tr], Xin[ho])
                hit[ho] = ((a_ho > np.quantile(a_tr, 0.95))
                           | (b_ho > np.quantile(b_tr, 0.95)))

            # how far beyond the limit: the larger of T^2/limit and Q/limit
            # per tray (T^2 alone where Q is a rounding residue)
            sev = t2_te / lim_t2
            if not q_numerical:
                sev = np.maximum(sev, q_te / lim_q)

            cells[f"{name}|{v}"] = {
                "severity_min": float(sev.min()),
                "severity_median": float(np.median(sev)),
                "severity_max": float(sev.max()),
                "fraction_beyond_10x_limit": float((sev > 10).mean()),
                "flagged_stored_in_exp2": stored_flag,
                "n_components": int(ncomp),
                "n_features": int(X.shape[1]),
                "full_rank": bool(ncomp == X.shape[1]),
                "n_test": int(te.sum()),
                "flagged_either": either,
                "flagged_by_t2": float(by_t2.mean()),
                "flagged_by_q": float(by_q.mean()),
                "flagged_by_q_only": float((by_q & ~by_t2).mean()),
                "flagged_by_both": float((by_q & by_t2).mean()),
                "t2_limit": lim_t2,
                "q_limit": lim_q,
                "q_is_numerical_zero": q_numerical,
                "flagged_meaningful": float(by_t2.mean()) if q_numerical
                else either,
                "t2_median_over_limit": float(np.median(t2_te) / lim_t2),
                "q_median_over_limit": None if q_numerical
                else float(np.median(q_te) / lim_q),
                "train_in_sample_flagged":
                    float(((t2_tr > lim_t2) | (q_tr > lim_q)).mean()),
                "same_variety_cv_flagged": float(hit.mean()),
                "n_same_variety": int(len(yin)),
                "pearson_r": stored["pearson_r"],
                "rmse_floor_over_sd": stored["rmse_offset_corrected_gl"]
                / stored["test_sd_gl"],
            }
    multi = [k for k in cells if not k.startswith("water|")]
    white = [k for k in multi if k.endswith("|MAUZAC")]
    red = [k for k in multi if not k.endswith("|MAUZAC")]
    return {
        "cells": cells,
        "held_out_red_flagged_min": min(cells[k]["flagged_stored_in_exp2"]
                                        for k in red),
        "held_out_red_flagged_max": max(cells[k]["flagged_stored_in_exp2"]
                                        for k in red),
        "white_severity_min_over_cells": min(cells[k]["severity_min"]
                                             for k in white),
        "red_severity_max_over_cells": max(cells[k]["severity_max"]
                                           for k in red),
        "same_variety_cv_flagged_min": min(c["same_variety_cv_flagged"]
                                           for c in cells.values()),
        "same_variety_cv_flagged_max": max(c["same_variety_cv_flagged"]
                                           for c in cells.values()),
    }


def main():
    exp2 = json.load(open("results/exp2_transfer.json"))
    exp1 = json.load(open("results/exp1_rgb_vs_nir.json"))
    out = {"source": "results/exp2_transfer.json",
           "break_even": part_a(exp2, exp1["config"]["varieties"])}
    if "--no-data" not in sys.argv:
        out["outlier_test"] = part_b(exp2)
    else:
        try:
            old = json.load(open("results/transfer_checks.json"))
            out["outlier_test"] = old["outlier_test"]
        except (OSError, KeyError):
            pass
    with open("results/transfer_checks.json", "w") as fh:
        json.dump(out, fh, indent=1)

    a = out["break_even"]["cells"]
    print(f"{'cell':14s} {'raw':>6s} {'floor':>6s} {'bias':>7s} {'k*':>6s} "
          f"{'k=1':>6s} {'k=5':>6s} {'k=20':>6s}")
    for key, c in a.items():
        ks = "never" if c["break_even_k"] is None else f"{c['break_even_k']:.1f}"
        print(f"{key:14s} {c['rmse_raw_gl']:6.1f} {c['rmse_floor_gl']:6.1f} "
              f"{c['bias_gl']:7.1f} {ks:>6s} {c['rmse_after_1_gl']:6.1f} "
              f"{c['rmse_after_5_gl']:6.1f} {c['rmse_after_20_gl']:6.1f}")
    print("5 refs worse than raw:",
          out["break_even"]["cells_where_5_refs_worse_than_raw"])
    print("closed form vs simulation, max gap / floor:",
          round(out["break_even"]["closed_form_max_abs_gap_fraction_of_floor"], 4))
    if "outlier_test" in out:
        print(f"\n{'cell':14s} {'nc/nf':>6s} {'either':>6s} {'T2':>5s} {'Q':>5s} "
              f"{'Qonly':>5s} {'T2/lim':>8s} {'Q/lim':>8s} {'cvFA':>5s} "
              f"{'r':>6s} {'Qnum':>4s}")
        for key, c in out["outlier_test"]["cells"].items():
            qr = "-" if c["q_median_over_limit"] is None \
                else f"{c['q_median_over_limit']:.2f}"
            print(f"{key:14s} {c['n_components']:>2d}/{c['n_features']:<3d} "
                  f"{c['flagged_either']:6.2f} {c['flagged_by_t2']:5.2f} "
                  f"{c['flagged_by_q']:5.2f} {c['flagged_by_q_only']:5.2f} "
                  f"{c['t2_median_over_limit']:8.2f} {qr:>8s} "
                  f"{c['same_variety_cv_flagged']:5.2f} {c['pearson_r']:6.2f} "
                  f"{'yes' if c['q_is_numerical_zero'] else '':>4s}")


if __name__ == "__main__":
    main()
