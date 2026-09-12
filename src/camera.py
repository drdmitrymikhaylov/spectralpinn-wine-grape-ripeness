"""What a colour camera actually measures.

A hyperspectral instrument reports reflectance at every wavelength.  A camera
does not: each of its three channels reports one number, the integral of the
incoming spectrum against that channel's sensitivity.  Everything the spectrum
knew that survives that integration is available to a robot with an ordinary
camera; everything else is not, no matter how good the model behind it.

The channel sensitivities used here are the CIE 1931 2-degree colour matching
functions, in the analytic multi-lobe Gaussian form of Wyman, Sloan & Shirley
(JCGT 2:2, 2013), converted to linear sRGB.  Using the CIE functions rather
than one manufacturer's curves keeps the result about colour cameras in
general instead of about one sensor.
"""

import numpy as np

# linear sRGB from CIE XYZ (IEC 61966-2-1, D65)
XYZ_TO_SRGB = np.array([
    [3.2406, -1.5372, -0.4986],
    [-0.9689, 1.8758, 0.0415],
    [0.0557, -0.2040, 1.0570],
])


# CIE XYZ of the D65 white point, the reference sRGB is defined against
D65_WHITE = np.array([0.95047, 1.0, 1.08883])


def _g(x, mu, s1, s2):
    """Piecewise Gaussian with different widths either side of the peak."""
    s = np.where(x < mu, s1, s2)
    return np.exp(-0.5 * ((x - mu) / s) ** 2)


def cie_xyz_bar(wl_nm):
    """CIE 1931 2-degree colour matching functions, analytic approximation."""
    w = np.asarray(wl_nm, dtype=float)
    x = (1.056 * _g(w, 599.8, 37.9, 31.0)
         + 0.362 * _g(w, 442.0, 16.0, 26.7)
         - 0.065 * _g(w, 501.1, 20.4, 26.2))
    y = (0.821 * _g(w, 568.8, 46.9, 40.5)
         + 0.286 * _g(w, 530.9, 16.3, 31.1))
    z = (1.217 * _g(w, 437.0, 11.8, 36.0)
         + 0.681 * _g(w, 459.0, 26.0, 13.8))
    return np.stack([x, y, z], axis=0)


def spectra_to_rgb(wl_nm, reflectance, illuminant=None, relative=True):
    """Linear sRGB per sample from reflectance spectra.

    reflectance: (n_samples, n_bands).  `illuminant` defaults to flat; a
    daylight or blackbody spectrum can be supplied instead.

    `relative` decides which of two different cameras is being modelled.
    With relative=True the response is divided by that of a perfect white
    diffuser under the same light, so a grey surface comes out neutral
    whatever the illuminant -- a camera that knows the light, through a white
    reference in frame or a correct white balance.  With relative=False the
    raw sensor response is returned, colour cast included, which is what an
    uncalibrated camera delivers when the light changes under it.
    """
    wl = np.asarray(wl_nm, dtype=float)
    R = np.asarray(reflectance, dtype=float)
    bar = cie_xyz_bar(wl)                       # (3, n_bands)
    E = np.ones_like(wl) if illuminant is None else np.asarray(illuminant)
    dw = np.gradient(wl)
    w = bar * E * dw                            # integration weights
    XYZ = R @ w.T                               # (n_samples, 3)
    white = w.sum(axis=1)                       # perfect diffuser, same light
    if relative:
        # von Kries adaptation to the D65 white point sRGB is defined against,
        # so that a grey surface is grey under any illuminant
        XYZ = XYZ / np.where(white > 0, white, 1.0) * D65_WHITE
    else:
        XYZ = XYZ / white[1]
    rgb = XYZ @ XYZ_TO_SRGB.T
    return np.clip(rgb, 0.0, None)


def rgb_to_lab_like(rgb):
    """CIELAB-style coordinates from linear sRGB, via XYZ under D65.

    Ripeness in a red variety is usually judged by eye as "how dark and how
    red", which is L* and a*.  Providing them makes the colour baseline as
    strong as the practice it stands in for.
    """
    M = np.linalg.inv(XYZ_TO_SRGB)
    XYZ = np.asarray(rgb) @ M.T
    white = np.array([0.95047, 1.0, 1.08883])
    t = np.clip(XYZ / white, 1e-9, None)
    f = np.where(t > (6 / 29) ** 3, np.cbrt(t), t / (3 * (6 / 29) ** 2) + 4 / 29)
    L = 116 * f[:, 1] - 16
    a = 500 * (f[:, 0] - f[:, 1])
    b = 200 * (f[:, 1] - f[:, 2])
    return np.stack([L, a, b], axis=1)


def water_band_depth(wl_nm, reflectance, centre=970.0, left=900.0, right=1003.0):
    """Depth of the water absorption band near 970 nm.

    This is the physical reason near-infrared can read sugar at all.  Soluble
    solids displace water, so the more sugar a berry holds the less water it
    holds per unit volume, and the shallower the O-H overtone absorption near
    970 nm becomes.  Colour carries no equivalent mechanism: anthocyanin
    absorption in the visible tracks pigment, and pigment tracks ripeness only
    through the variety's own development.

    Computed in absorbance, as the depth below the straight line joining the
    two shoulder points -- the standard continuum-removal definition.
    """
    wl = np.asarray(wl_nm, dtype=float)
    R = np.clip(np.asarray(reflectance, dtype=float), 1e-6, None)
    A = -np.log10(R)

    def at(w0):
        i = int(np.argmin(np.abs(wl - w0)))
        return A[:, i], wl[i]

    a_l, w_l = at(left)
    a_r, w_r = at(right)
    a_c, w_c = at(centre)
    frac = (w_c - w_l) / (w_r - w_l)
    baseline = a_l + frac * (a_r - a_l)
    return a_c - baseline
