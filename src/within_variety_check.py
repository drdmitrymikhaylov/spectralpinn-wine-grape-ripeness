"""Section 2's "factor of two", read on all three varieties and with intervals.

The page says that inside a single variety the spectra pull further ahead
of the camera, and quotes SYRAH: near-infrared 10.6 g/L against 20.6 for
RGB.  Experiment 1 stored the same within-variety table for FER and MAUZAC
(results/exp1_rgb_vs_nir.json, "within") and the page never read it.  Each
stored cell is the mean over ten repeats of random 5-fold cross-validation
and carries no spread.

This script re-runs the within-variety protocol exactly as exp1 does it
(same feature sets, same seeds, same inner choice of the number of
components), keeps every repeat and every out-of-fold prediction, and
reports, per variety and feature set:

  - the mean RMSE over the ten repeats (must match the stored cell), its
    spread over repeats, and the range;
  - the ratio camera / spectral model, paired by repeat (the k-th repeat of
    every feature set uses the same fold split, because the split depends
    on the seed and the number of trays only);
  - a tray-level bootstrap of that ratio: trays resampled with replacement
    2 000 times, the RMSE of each feature set recomputed on the resampled
    trays from the stored out-of-fold predictions of every repeat, and the
    ratio of the two means taken -- the interval a different sample of trays
    of the same variety would give.

Writes results/within_variety_check.json.  Needs data/DATASET.csv.  Run
from the repository root:

    python src/within_variety_check.py
"""

import json
import sys

sys.path.insert(0, 'src')

import numpy as np

from data import load
from exp1_rgb_vs_nir import N_REPEATS, feature_sets, run_random

N_BOOT = 2000
SPECTRAL = ["vis", "red_edge", "nir", "full", "water"]


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def main():
    wl, R, y, variety = load()
    F = feature_sets(wl, R)
    stored = json.load(open("results/exp1_rgb_vs_nir.json"))["within"]
    varieties = sorted(set(variety))
    rng = np.random.default_rng(0)

    out = {"config": {"n_repeats": N_REPEATS, "n_boot": N_BOOT,
                      "source": "results/exp1_rgb_vs_nir.json"},
           "cells": {}, "ratios": {}}
    preds = {}
    for v in varieties:
        m = variety == v
        yv = y[m]
        n = int(m.sum())
        for name, X in F.items():
            P = np.stack([run_random(X[m], yv, seed=rep)
                          for rep in range(N_REPEATS)])      # repeats x trays
            preds[(name, v)] = P
            per_rep = [rmse(P[k], yv) for k in range(N_REPEATS)]
            mean = float(np.mean(per_rep))
            s = stored[name][v]["rmse_gl"]
            out["cells"][f"{name}|{v}"] = {
                "n_trays": n,
                "sd_gl": float(yv.std(ddof=1)),
                "rmse_mean_gl": mean,
                "rmse_stored_gl": s,
                "reproduces_stored": bool(abs(mean - s) < 1e-4),
                "rmse_sd_over_repeats_gl": float(np.std(per_rep, ddof=1)),
                "rmse_min_gl": float(min(per_rep)),
                "rmse_max_gl": float(max(per_rep)),
                "rmse_per_repeat_gl": per_rep,
            }

        # ratios camera / spectral, paired by repeat and bootstrapped by tray
        idx = np.arange(n)
        boots = [rng.choice(idx, size=n, replace=True) for _ in range(N_BOOT)]
        Prgb = preds[("rgb", v)]
        res_rgb = (Prgb - yv) ** 2
        for name in SPECTRAL:
            P = preds[(name, v)]
            paired = [rmse(Prgb[k], yv) / rmse(P[k], yv)
                      for k in range(N_REPEATS)]
            res = (P - yv) ** 2
            bratio = []
            for b in boots:
                a = np.sqrt(res_rgb[:, b].mean(axis=1)).mean()
                c = np.sqrt(res[:, b].mean(axis=1)).mean()
                bratio.append(a / c)
            bratio = np.asarray(bratio)
            # the same bootstrap for the spectral model's own RMSE
            own = np.asarray([np.sqrt(res[:, b].mean(axis=1)).mean()
                              for b in boots])
            out["ratios"][f"{name}|{v}"] = {
                "rgb_over_model_mean_of_means":
                    out["cells"][f"rgb|{v}"]["rmse_mean_gl"]
                    / out["cells"][f"{name}|{v}"]["rmse_mean_gl"],
                "paired_by_repeat_mean": float(np.mean(paired)),
                "paired_by_repeat_min": float(min(paired)),
                "paired_by_repeat_max": float(max(paired)),
                "repeats_with_model_ahead": int(sum(r > 1 for r in paired)),
                "tray_bootstrap_ci95": [float(np.quantile(bratio, 0.025)),
                                        float(np.quantile(bratio, 0.975))],
                "tray_bootstrap_fraction_above_1": float((bratio > 1).mean()),
                "tray_bootstrap_fraction_above_2": float((bratio > 2).mean()),
                "model_rmse_tray_bootstrap_ci95_gl":
                    [float(np.quantile(own, 0.025)),
                     float(np.quantile(own, 0.975))],
            }

    # which feature set is best within each variety, and by how much over RGB
    best = {}
    for v in varieties:
        cells = {name: out["cells"][f"{name}|{v}"]["rmse_mean_gl"]
                 for name in F}
        b = min(cells, key=cells.get)
        best[v] = {"feature_set": b, "rmse_gl": cells[b],
                   "rgb_over_best": cells["rgb"] / cells[b],
                   "nir_over_best": cells["nir"] / cells[b]}
    out["best_within_variety"] = best

    with open("results/within_variety_check.json", "w") as fh:
        json.dump(out, fh, indent=1)

    print(f"{'cell':16s} {'stored':>7s} {'mean':>7s} {'sd':>5s} {'min':>6s} "
          f"{'max':>6s}  ok")
    for key, c in out["cells"].items():
        print(f"{key:16s} {c['rmse_stored_gl']:7.1f} {c['rmse_mean_gl']:7.1f} "
              f"{c['rmse_sd_over_repeats_gl']:5.2f} {c['rmse_min_gl']:6.1f} "
              f"{c['rmse_max_gl']:6.1f}  {c['reproduces_stored']}")
    print(f"\n{'rgb / model':16s} {'ratio':>6s} {'paired':>6s} {'min':>5s} "
          f"{'max':>5s} {'ahead':>5s} {'boot 95% CI':>14s} {'P>1':>5s} {'P>2':>5s}")
    for key, c in out["ratios"].items():
        lo, hi = c["tray_bootstrap_ci95"]
        print(f"{key:16s} {c['rgb_over_model_mean_of_means']:6.2f} "
              f"{c['paired_by_repeat_mean']:6.2f} {c['paired_by_repeat_min']:5.2f} "
              f"{c['paired_by_repeat_max']:5.2f} {c['repeats_with_model_ahead']:5d} "
              f"[{lo:5.2f}, {hi:5.2f}] {c['tray_bootstrap_fraction_above_1']:5.2f} "
              f"{c['tray_bootstrap_fraction_above_2']:5.2f}")
    for v, b in best.items():
        print(f"best within {v}: {b['feature_set']} {b['rmse_gl']:.1f} g/L, "
              f"rgb/best {b['rgb_over_best']:.2f}, nir/best {b['nir_over_best']:.2f}")


if __name__ == "__main__":
    main()
