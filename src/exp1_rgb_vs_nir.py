"""How much of the sugar signal survives a colour camera?

The proposal behind a vineyard robot is that it drives the rows, looks at the
fruit and reports ripeness.  Whether that works turns on one question: how
much of what a spectrometer knows about sugar is still there after the
spectrum has been collapsed into three camera channels.

Seven feature sets, from what a camera gives to what a laboratory instrument
gives:

  rgb          three linear sRGB channels
  lab          L*, a*, b* -- colour as a person judges it, darkness and redness
  vis          the visible bands, 397-700 nm
  red_edge     680-780 nm, where chlorophyll gives way to scattering
  nir          780-1003 nm
  full         all 204 bands
  water        a single number: the depth of the water absorption band near
               960 nm, continuum-removed.  This is the physical mechanism --
               sugar displaces water, so the band gets shallower as the berry
               ripens -- and it is included to test whether a 204-band model
               is doing anything a one-line physical index cannot.

Three validation schemes, because the choice changes the answer more than the
model does:

  random       5-fold, repeated.  What most papers report.
  within       5-fold inside each variety separately.  The realistic case: a
               block is one variety and can be calibrated on itself.
  lovo         leave one variety out.  The honest generalisation test, and the
               one that says whether the model learned sugar or learned which
               grape it was looking at.

Everything is compared against the only baseline that matters: predicting the
mean of the training set.  A model that cannot beat that is not measuring
anything, whatever its R-squared.
"""

import json
import sys

sys.path.insert(0, 'src')

import numpy as np
from sklearn.cross_decomposition import PLSRegression
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from camera import rgb_to_lab_like, spectra_to_rgb, water_band_depth
from data import GL_PER_BRIX, band_mask, load, snv

MAX_COMPONENTS = 12
N_REPEATS = 10


def feature_sets(wl, R):
    A = snv(-np.log10(np.clip(R, 1e-6, None)))
    rgb = spectra_to_rgb(wl, R)
    lab = rgb_to_lab_like(rgb)
    water = water_band_depth(wl, R, centre=960.0, left=880.0, right=1003.0)
    return {
        "rgb": rgb,
        "lab": lab,
        "vis": A[:, band_mask(wl, 397, 700)],
        "red_edge": A[:, band_mask(wl, 680, 780)],
        "nir": A[:, band_mask(wl, 780, 1003.5)],
        "full": A,
        "water": water.reshape(-1, 1),
    }


def model(n_comp):
    return Pipeline([("sc", StandardScaler()),
                     ("pls", PLSRegression(n_components=n_comp, scale=False))])


def best_n_components(X, y, seed=0):
    """Chosen by inner cross-validation on the training data only."""
    n_max = min(MAX_COMPONENTS, X.shape[1], max(len(y) - 2, 1))
    best, best_rmse = 1, np.inf
    for n in range(1, n_max + 1):
        kf = KFold(5, shuffle=True, random_state=seed)
        try:
            p = cross_val_predict(model(n), X, y, cv=kf).ravel()
        except Exception:
            continue
        r = float(np.sqrt(np.mean((p - y) ** 2)))
        if r < best_rmse:
            best, best_rmse = n, r
    return best


def fit_predict(Xtr, ytr, Xte, seed=0):
    n = best_n_components(Xtr, ytr, seed)
    m = model(n).fit(Xtr, ytr)
    return m.predict(Xte).ravel(), n


def scores(y_true, y_pred):
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    rmse = float(np.sqrt(np.mean((y_pred - y_true) ** 2)))
    sd = float(y_true.std(ddof=1))
    ss = float(np.sum((y_true - y_true.mean()) ** 2))
    return {
        "rmse_gl": rmse,
        "rmse_brix": rmse / GL_PER_BRIX,
        "baseline_rmse_gl": sd,
        "r2": float(1 - np.sum((y_true - y_pred) ** 2) / ss) if ss > 0 else np.nan,
        "rpd": sd / rmse if rmse > 0 else np.nan,
        "n": int(len(y_true)),
    }


def run_random(X, y, seed):
    kf = KFold(5, shuffle=True, random_state=seed)
    pred = np.zeros_like(y, dtype=float)
    for tr, te in kf.split(X):
        pred[te], _ = fit_predict(X[tr], y[tr], X[te], seed)
    return pred


def main():
    wl, R, y, variety = load()
    F = feature_sets(wl, R)
    varieties = sorted(set(variety))
    out = {"config": {"n_samples": int(len(y)), "n_bands": int(len(wl)),
                      "wl_min": float(wl.min()), "wl_max": float(wl.max()),
                      "varieties": {v: int((variety == v).sum()) for v in varieties},
                      "sugar_mean_gl": float(y.mean()),
                      "sugar_sd_gl": float(y.std(ddof=1)),
                      "gl_per_brix": GL_PER_BRIX,
                      "max_components": MAX_COMPONENTS,
                      "n_repeats": N_REPEATS},
           "random": {}, "within": {}, "lovo": {}}

    for name, X in F.items():
        # --- random 5-fold, repeated
        rs = []
        for rep in range(N_REPEATS):
            rs.append(scores(y, run_random(X, y, seed=rep)))
        out["random"][name] = {
            k: float(np.mean([r[k] for r in rs])) for k in rs[0] if k != "n"}
        out["random"][name]["rmse_gl_sd"] = float(
            np.std([r["rmse_gl"] for r in rs]))

        # --- within variety
        per = {}
        for v in varieties:
            m = variety == v
            rr = [scores(y[m], run_random(X[m], y[m], seed=rep))
                  for rep in range(N_REPEATS)]
            per[v] = {k: float(np.mean([r[k] for r in rr]))
                      for k in rr[0] if k != "n"}
        out["within"][name] = per

        # --- leave one variety out
        per = {}
        for v in varieties:
            te = variety == v
            pred, ncomp = fit_predict(X[~te], y[~te], X[te])
            s = scores(y[te], pred)
            s["n_components"] = int(ncomp)
            s["bias_gl"] = float(np.mean(pred - y[te]))
            per[v] = s
        out["lovo"][name] = per

        print(f"{name:9s} random RMSE {out['random'][name]['rmse_gl']:6.1f} g/L "
              f"({out['random'][name]['rmse_brix']:4.2f} Brix, "
              f"R2 {out['random'][name]['r2']:5.2f}) | "
              f"within " + " ".join(
                  f"{v[:3]} {out['within'][name][v]['rmse_gl']:5.1f}"
                  for v in varieties) + " | lovo " + " ".join(
                  f"{v[:3]} {out['lovo'][name][v]['rmse_gl']:5.1f}"
                  for v in varieties))

    with open("results/exp1_rgb_vs_nir.json", "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"\nbaseline (predict the mean): {y.std(ddof=1):.1f} g/L = "
          f"{y.std(ddof=1)/GL_PER_BRIX:.2f} Brix")


if __name__ == "__main__":
    main()
