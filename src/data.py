"""Loading and preprocessing of the berry reflectance data.

Source: Gomes, V. et al., "Dataset containing spectral data from hyperspectral
imaging and sugar content measurements of grape berries in various maturity
stages", Data in Brief (2022); Mendeley Data doi:10.17632/gjwx64sgkp.1.
274 trays of 100 berries, three varieties, reflectance at 204 bands from
397 to 1003 nm, with the sugar content of the must pressed from each tray.

Two things about the design matter for every result that follows.

  The label is a batch label.  Sugar was measured on the juice of a whole
  tray, not berry by berry, so the target is already a 100-berry average.
  That is the quantity a vineyard manager wants, and it means the data cannot
  say anything about single-berry accuracy.

  Variety is confounded with everything.  Two of the three varieties are red
  and one is white, so any colour feature separates them trivially.  A model
  validated by random splitting will be rewarded for recognising the variety,
  which is why every headline number here is also computed with a whole
  variety held out.
"""

import numpy as np
import pandas as pd

# Sugar in must is reported in g/L.  Degrees Brix is grams of sucrose per 100 g
# of solution, so the conversion needs the density of the must, which itself
# depends on the sugar.  Over the range present here (100-283 g/L) the usual
# oenological approximation is Brix ~ (g/L) / 10 / SG with SG ~ 1.07-1.12; a
# single factor of 10.8 is within about +/-0.4 Brix across the whole range and
# is used only for reporting, never inside a model.
GL_PER_BRIX = 10.8


def to_brix(g_per_l):
    return np.asarray(g_per_l, dtype=float) / GL_PER_BRIX


def load(path="data/DATASET.csv"):
    """Return (wavelengths, reflectance, sugar_g_per_l, variety)."""
    d = pd.read_csv(path, sep=";")
    band_cols = [c for c in d.columns if c.startswith("x.")]
    wl = np.array([float(c[2:]) for c in band_cols])
    order = np.argsort(wl)
    wl = wl[order]
    R = d[band_cols].to_numpy(dtype=float)[:, order]
    y = d["Sugar content (g/l)"].to_numpy(dtype=float)
    variety = d["Variety"].to_numpy()
    return wl, R, y, variety


def snv(X):
    """Standard normal variate: centre and scale each spectrum by its own
    mean and standard deviation.

    This removes the multiplicative scaling that comes from how far the berry
    sat from the lamp and how much of the pixel it filled -- geometry, not
    chemistry.  Without it, a model can score well by reading brightness,
    which a robot in a vineyard will not reproduce.
    """
    X = np.asarray(X, dtype=float)
    m = X.mean(axis=1, keepdims=True)
    s = X.std(axis=1, keepdims=True)
    return (X - m) / np.where(s > 0, s, 1.0)


def savgol_derivative(X, wl, window=11, order=2, deriv=1):
    """Savitzky-Golay derivative along the wavelength axis."""
    from scipy.signal import savgol_filter
    dx = float(np.median(np.diff(wl)))
    return savgol_filter(X, window_length=window, polyorder=order,
                         deriv=deriv, delta=dx, axis=1)


def band_mask(wl, lo, hi):
    return (wl >= lo) & (wl <= hi)
