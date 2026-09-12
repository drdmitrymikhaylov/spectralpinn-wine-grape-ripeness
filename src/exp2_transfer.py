"""What it takes to move a calibration to a variety it has never seen.

Experiment 1 ends with every feature set failing when a whole variety is held
out -- most of them worse than predicting the training mean.  That is the
normal fate of a spectroscopic calibration, and it is not the end of the
story, because there are two very different ways to be wrong:

  offset    the model is shifted.  Every prediction for the new variety is
            20 g/L too high, but they still rank the berries correctly.  One
            reference measurement fixes it.
  scatter   the model has lost the relationship.  No number of reference
            measurements fixes it; the calibration has to be rebuilt.

This script separates them, and then asks the question a grower actually
cares about: how many berries do I still have to press and measure by hand
before the robot's numbers can be trusted on this block?

It also tests the safeguard the failure calls for.  A calibration that is
asked about a spectrum unlike anything it was fitted on should say so rather
than answer.  The standard test in process spectroscopy is the pair of
distances in the model's own coordinates -- Hotelling's T-squared inside the
latent space and the Q residual orthogonal to it.  If those flag the held-out
variety, a deployed module can refuse the question instead of returning the
203 g/L that experiment 1 produced.
"""

import json
import sys

sys.path.insert(0, 'src')

import numpy as np
from sklearn.cross_decomposition import PLSRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from data import GL_PER_BRIX, load
from exp1_rgb_vs_nir import best_n_components, feature_sets, model

K_REFERENCE = [0, 1, 2, 3, 5, 8, 12, 20, 30]
N_DRAWS = 200
FEATURES = ["rgb", "lab", "vis", "nir", "full", "water"]


def fitted(Xtr, ytr, seed=0):
    n = best_n_components(Xtr, ytr, seed)
    return model(n).fit(Xtr, ytr), n


def diagnostics(pipe, Xtr, Xte):
    """Hotelling T^2 and Q residual of the test set in the model's space."""
    sc = pipe.named_steps["sc"]
    pls = pipe.named_steps["pls"]
    Ztr, Zte = sc.transform(Xtr), sc.transform(Xte)
    Ttr = pls.transform(Ztr)
    Tte = pls.transform(Zte)
    cov = np.cov(Ttr.T)
    cov = np.atleast_2d(cov)
    inv = np.linalg.pinv(cov)
    t2_tr = np.einsum("ij,jk,ik->i", Ttr, inv, Ttr)
    t2_te = np.einsum("ij,jk,ik->i", Tte, inv, Tte)
    rec_tr = Ttr @ pls.x_loadings_.T
    rec_te = Tte @ pls.x_loadings_.T
    q_tr = np.sum((Ztr - rec_tr) ** 2, axis=1)
    q_te = np.sum((Zte - rec_te) ** 2, axis=1)
    lim_t2 = float(np.quantile(t2_tr, 0.95))
    lim_q = float(np.quantile(q_tr, 0.95))
    flagged = (t2_te > lim_t2) | (q_te > lim_q)
    return {
        "t2_limit": lim_t2, "q_limit": lim_q,
        "t2_median_train": float(np.median(t2_tr)),
        "t2_median_test": float(np.median(t2_te)),
        "q_median_train": float(np.median(q_tr)),
        "q_median_test": float(np.median(q_te)),
        "flagged_fraction": float(flagged.mean()),
    }


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def main():
    wl, R, y, variety = load()
    F = feature_sets(wl, R)
    varieties = sorted(set(variety))
    rng = np.random.default_rng(0)

    out = {"config": {"k_reference": K_REFERENCE, "n_draws": N_DRAWS,
                      "gl_per_brix": GL_PER_BRIX},
           "cells": {}}

    for name in FEATURES:
        X = F[name]
        for v in varieties:
            te = variety == v
            pipe, ncomp = fitted(X[~te], y[~te])
            pred = pipe.predict(X[te]).ravel()
            truth = y[te]
            bias = float(np.mean(pred - truth))
            raw = rmse(pred, truth)
            corrected = rmse(pred - bias, truth)      # oracle offset
            sd = float(truth.std(ddof=1))
            r = float(np.corrcoef(pred, truth)[0, 1]) if len(truth) > 2 else np.nan

            # how many reference samples are needed to estimate that offset
            curve = {}
            for k in K_REFERENCE:
                if k == 0:
                    curve[k] = {"rmse_gl": raw, "rmse_brix": raw / GL_PER_BRIX}
                    continue
                errs = []
                idx = np.arange(len(truth))
                for _ in range(N_DRAWS):
                    pick = rng.choice(idx, size=min(k, len(idx)), replace=False)
                    off = float(np.mean(pred[pick] - truth[pick]))
                    hold = np.setdiff1d(idx, pick)
                    if len(hold) == 0:
                        continue
                    errs.append(rmse(pred[hold] - off, truth[hold]))
                curve[k] = {"rmse_gl": float(np.mean(errs)),
                            "rmse_brix": float(np.mean(errs)) / GL_PER_BRIX}

            out["cells"][f"{name}|{v}"] = {
                "n_components": int(ncomp),
                "rmse_raw_gl": raw,
                "rmse_offset_corrected_gl": corrected,
                "bias_gl": bias,
                "test_sd_gl": sd,
                "pearson_r": r,
                "reference_curve": {str(k): c for k, c in curve.items()},
                "diagnostics": diagnostics(pipe, X[~te], X[te]),
            }

    with open("results/exp2_transfer.json", "w") as fh:
        json.dump(out, fh, indent=1)

    print(f"{'features':9s} {'held out':8s} {'raw':>7s} {'offset':>7s} "
          f"{'bias':>7s} {'SD':>6s} {'r':>6s} {'k=5':>6s} {'k=20':>6s} {'OOD':>5s}")
    for name in FEATURES:
        for v in varieties:
            c = out["cells"][f"{name}|{v}"]
            print(f"{name:9s} {v:8s} {c['rmse_raw_gl']:7.1f} "
                  f"{c['rmse_offset_corrected_gl']:7.1f} {c['bias_gl']:7.1f} "
                  f"{c['test_sd_gl']:6.1f} {c['pearson_r']:6.2f} "
                  f"{c['reference_curve']['5']['rmse_gl']:6.1f} "
                  f"{c['reference_curve']['20']['rmse_gl']:6.1f} "
                  f"{c['diagnostics']['flagged_fraction']:5.2f}")


if __name__ == "__main__":
    main()
