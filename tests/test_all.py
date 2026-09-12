"""Checks on the physics and the estimators, run before any result is quoted."""

import sys

sys.path.insert(0, 'src')

import numpy as np

from camera import (cie_xyz_bar, rgb_to_lab_like, spectra_to_rgb,
                    water_band_depth)
from data import GL_PER_BRIX, load, snv, to_brix


def test_cmf_peaks():
    """The colour matching functions must peak where the CIE ones do."""
    wl = np.arange(380, 781, 1.0)
    bar = cie_xyz_bar(wl)
    assert abs(wl[np.argmax(bar[1])] - 555) <= 5, wl[np.argmax(bar[1])]
    assert abs(wl[np.argmax(bar[2])] - 446) <= 8, wl[np.argmax(bar[2])]
    # x-bar is double-humped; its larger lobe is in the red
    assert wl[np.argmax(bar[0])] > 570


def test_camera_is_blind_beyond_700nm():
    """The physical reason a colour camera cannot use the water band.

    Whatever a model does with RGB, it cannot use information the sensor never
    collected.  Sensitivity past 750 nm must be negligible against the peak.
    """
    wl = np.arange(390, 1010, 2.0)
    bar = cie_xyz_bar(wl)
    peak = bar.max()
    beyond = bar[:, wl > 750].max()
    assert beyond / peak < 0.01, beyond / peak


def test_grey_is_neutral():
    """A flat reflectance under a flat illuminant must come out achromatic."""
    wl = np.arange(400, 701, 2.0)
    R = 0.18 * np.ones((1, len(wl)))
    rgb = spectra_to_rgb(wl, R)[0]
    assert rgb.max() / rgb.min() < 1.15, rgb
    lab = rgb_to_lab_like(rgb.reshape(1, 3))[0]
    assert abs(lab[1]) < 6 and abs(lab[2]) < 6, lab


def test_snv_normalises():
    X = np.random.default_rng(0).normal(3.0, 2.0, (20, 50))
    Z = snv(X)
    assert np.allclose(Z.mean(axis=1), 0, atol=1e-12)
    assert np.allclose(Z.std(axis=1), 1, atol=1e-12)


def test_brix_conversion():
    assert abs(to_brix(216.0) - 20.0) < 0.5
    assert abs(to_brix(np.array([GL_PER_BRIX]))[0] - 1.0) < 1e-9


def test_water_band_tracks_sugar_in_reds():
    """Sugar displaces water, so the 970 nm band should shallow as sugar rises.

    Verified within the two red varieties.  It does not hold in the white one,
    which is reported rather than hidden -- see the README.
    """
    wl, R, y, v = load()
    d = water_band_depth(wl, R, centre=960.0, left=880.0, right=1003.0)
    assert np.median(d) > 0, "the band must be an absorption feature"
    for var in ("SYRAH", "FER"):
        m = v == var
        r = np.corrcoef(d[m], y[m])[0, 1]
        assert r < -0.4, (var, r)


def test_random_cv_beats_the_mean_but_variety_transfer_does_not():
    """Pins the central finding, so a refactor cannot quietly erase it."""
    from exp1_rgb_vs_nir import feature_sets, fit_predict, run_random
    wl, R, y, v = load()
    F = feature_sets(wl, R)
    sd = y.std(ddof=1)

    p = run_random(F["full"], y, seed=0)
    rmse_random = np.sqrt(np.mean((p - y) ** 2))
    assert rmse_random < 0.75 * sd, (rmse_random, sd)

    te = v == "MAUZAC"
    pred, _ = fit_predict(F["full"][~te], y[~te], F["full"][te])
    rmse_lovo = np.sqrt(np.mean((pred - y[te]) ** 2))
    assert rmse_lovo > sd, (rmse_lovo, sd)


def test_offset_correction_helps_reds_not_the_white():
    """The failure mode differs by variety: a shift for reds, no relationship
    for the white one.  That difference is what decides whether a handful of
    reference measurements can rescue a calibration."""
    from exp1_rgb_vs_nir import feature_sets
    from exp2_transfer import fitted
    wl, R, y, v = load()
    X = feature_sets(wl, R)["nir"]

    te = v == "SYRAH"
    pipe, _ = fitted(X[~te], y[~te])
    pred = pipe.predict(X[te]).ravel()
    assert np.corrcoef(pred, y[te])[0, 1] > 0.8

    te = v == "MAUZAC"
    pipe, _ = fitted(X[~te], y[~te])
    pred = pipe.predict(X[te]).ravel()
    assert abs(np.corrcoef(pred, y[te])[0, 1]) < 0.4


def test_slab_model_limits():
    """No absorption -> R = Sd/(1+Sd); optically thick -> R = 1/(a+b)."""
    try:
        import torch
    except ImportError:
        print("  (skipped: no torch)"); return
    from exp5_km_pinn import Slab
    m = Slab(1)
    lam = torch.linspace(-1, 1, 50, dtype=torch.float64).reshape(-1, 1)
    with torch.no_grad():
        m.c_raw.fill_(-30.0)                      # softplus -> ~0 absorption
        Sd = torch.exp(m.s_raw) * m.scattering(lam).T
        R = m(lam)
        assert torch.allclose(R, Sd / (1 + Sd), atol=1e-4)
        m.c_raw.fill_(10.0); m.s_raw.fill_(5.0)  # strong absorption, thick layer
        K = m.endmembers(lam)
        Kd = torch.nn.functional.softplus(m.c_raw) @ K.T + 1e-6
        Sd = torch.exp(m.s_raw) * m.scattering(lam).T
        a = 1 + Kd / Sd; b = torch.sqrt(a ** 2 - 1 + 1e-12)
        R = m(lam)
        assert torch.allclose(R, 1 / (a + b), rtol=1e-3)


def test_constituents_stay_in_their_windows():
    try:
        import torch
    except ImportError:
        print("  (skipped: no torch)"); return
    from exp5_km_pinn import Slab, WINDOWS
    m = Slab(1)
    wl = np.linspace(397, 1003, 300)
    lam = torch.tensor((wl - 700.0) / 300.0).reshape(-1, 1)
    with torch.no_grad():
        K = m.endmembers(lam).numpy()
    for i, (lo, hi) in WINDOWS.items():
        peak = K[:, i].max()
        if lo is not None:
            assert K[wl < lo - 60, i].max() < 0.05 * peak
        if hi is not None:
            assert K[wl > hi + 60, i].max() < 0.05 * peak


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
