"""Sugar from the water it displaces, through a slab model of the berry.

The physical argument behind reading ripeness from reflectance is that
sugar displaces water: as the must sweetens, the water absorption band near
960 nm gets shallower.  The rest of this repository reads that band as a
depth (an index), or hands the whole spectrum to a regression.  Both fail
across varieties (§3): the depth also depends on how much berry the light
went through, and the regression learns the variety.

This file puts the argument into an equation.  A berry surface is a
scattering, absorbing layer; its reflectance follows the finite-thickness
Kubelka-Munk solution

    R = 1 / (a + b coth(b S d)),   a = 1 + K/S,   b = sqrt(a^2 - 1),
    K d = sum_i C_i k_i(lambda),   S d = s sigma(lambda),

with the absorbing contents C_i per unit area and the scattering thickness
S d per tray.  Three constituents are allowed, each confined to where it
can absorb: a pigment below 600 nm (anthocyanins, in the red varieties), a
pigment between 600 and 760 nm (chlorophyll), and water above 880 nm.  The
specific absorption spectra k_i(lambda) are small networks of wavelength
learned jointly with the per-tray contents from reflectance alone; no
sugar value enters the fit.

Water per unit *scattering thickness*, C_water / s, is water per volume of
tissue, and that is what sugar displaces.  It is the one feature this file
produces, and it is tested exactly as §3 tested the others: calibrated on
two varieties, applied to the third.
"""

import json
import sys

sys.path.insert(0, 'src')

import numpy as np
import torch
from scipy.stats import pearsonr

from camera import water_band_depth
from data import GL_PER_BRIX, load

torch.set_default_dtype(torch.float64)
torch.manual_seed(0)
WINDOWS = {0: (None, 600.0), 1: (600.0, 760.0), 2: (880.0, None)}
ROLE = {0: "pigment_blue_green", 1: "chlorophyll", 2: "water"}


def mlp(width=48, depth=3):
    layers, d = [], 1
    for _ in range(depth):
        layers += [torch.nn.Linear(d, width), torch.nn.Tanh()]
        d = width
    layers.append(torch.nn.Linear(d, 1))
    return torch.nn.Sequential(*layers)


class Slab(torch.nn.Module):
    def __init__(self, n, n_comp=3):
        super().__init__()
        self.k_nets = torch.nn.ModuleList([mlp() for _ in range(n_comp)])
        self.s_net = mlp(width=24, depth=2)
        self.c_raw = torch.nn.Parameter(torch.randn(n, n_comp) * 0.1)
        self.s_raw = torch.nn.Parameter(torch.zeros(n, 1))

    def endmembers(self, lam_s):
        wl = lam_s * 300.0 + 700.0
        cols = []
        for i, net in enumerate(self.k_nets):
            k = torch.nn.functional.softplus(net(lam_s))
            lo, hi = WINDOWS[i]
            if lo is not None:
                k = k * torch.sigmoid((wl - lo) / 15.0)
            if hi is not None:
                k = k * torch.sigmoid((hi - wl) / 15.0)
            cols.append(k)
        return torch.cat(cols, 1)

    def scattering(self, lam_s):
        return torch.nn.functional.softplus(self.s_net(lam_s) + 1.0)

    def forward(self, lam_s):
        K = self.endmembers(lam_s)
        sig = self.scattering(lam_s).T
        c = torch.nn.functional.softplus(self.c_raw)
        s = torch.exp(self.s_raw)
        Kd = c @ K.T + 1e-6
        Sd = s * sig
        a = 1.0 + Kd / Sd
        b = torch.sqrt(a ** 2 - 1.0 + 1e-12)
        return 1.0 / (a + b / torch.tanh(b * Sd))


def fit(R, lam_s, steps=3000, model=None, freeze=False, lr=1e-2):
    Y = torch.tensor(R)
    N = R.shape[0]
    if model is None:
        m = Slab(N)
    else:
        m = Slab(N)
        m.k_nets.load_state_dict(model.k_nets.state_dict())
        m.s_net.load_state_dict(model.s_net.state_dict())
    if freeze:
        for p in list(m.k_nets.parameters()) + list(m.s_net.parameters()):
            p.requires_grad_(False)
        params = [m.c_raw, m.s_raw]
    else:
        params = list(m.parameters())
    opt = torch.optim.Adam(params, lr=lr)
    L = torch.tensor(lam_s).reshape(-1, 1)
    for _ in range(steps):
        opt.zero_grad()
        pred = m(L)
        loss = torch.mean((pred - Y) ** 2 / (Y + 0.02))
        if not freeze:
            d2 = torch.diff(torch.log(m.endmembers(L) + 1e-6), n=2, dim=0)
            loss = loss + 1e-2 * torch.mean(d2 ** 2)
        loss.backward()
        opt.step()
    return m, float(loss)


def contents(m):
    with torch.no_grad():
        c = torch.nn.functional.softplus(m.c_raw).numpy()
        s = torch.exp(m.s_raw).squeeze().numpy()
    return c, s


def scores(y, yhat):
    rmse = float(np.sqrt(np.mean((y - yhat) ** 2)))
    return {"rmse_gl": rmse, "rmse_brix": rmse / GL_PER_BRIX,
            "r2": float(1 - np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2)),
            "r": float(pearsonr(y, yhat)[0]), "bias_gl": float(np.mean(yhat - y))}


def main():
    wl, R, y, variety = load()
    R = np.clip(R, 1e-3, 0.999)
    lam_s = (wl - 700.0) / 300.0
    vars_ = sorted(set(variety))
    out = {"n": int(len(y)), "wl": wl.tolist(), "roles": ROLE, "lovo": {}, "within": {}}

    m_all, loss_all = fit(R, lam_s)
    with torch.no_grad():
        L = torch.tensor(lam_s).reshape(-1, 1)
        out["endmembers"] = m_all.endmembers(L).numpy().tolist()
        out["scattering"] = m_all.scattering(L).squeeze().numpy().tolist()
        out["fit_rel_rmse"] = float(torch.sqrt(torch.mean((m_all(L) - torch.tensor(R)) ** 2)) /
                                    torch.mean(torch.tensor(R)))
    c_all, s_all = contents(m_all)
    w_all = c_all[:, 2] / s_all
    out["water_per_thickness"] = w_all.tolist()
    out["scatter_thickness"] = s_all.tolist()
    depth = water_band_depth(wl, R, centre=960.0, left=880.0, right=1003.0)
    print(f"global fit: relative RMSE {out['fit_rel_rmse']:.3f}")
    for v in vars_:
        k = variety == v
        out["within"][v] = {"r_water_per_thickness": float(pearsonr(w_all[k], y[k])[0]),
                            "r_water_per_area": float(pearsonr(c_all[k, 2], y[k])[0]),
                            "r_band_depth": float(pearsonr(depth[k], y[k])[0]),
                            "r_thickness": float(pearsonr(s_all[k], y[k])[0]), "n": int(k.sum())}
        w = out["within"][v]
        print(f"  within {v:8s}: r(sugar, C_water) {w['r_water_per_area']:+.2f}  r(sugar, C_water/s) "
              f"{w['r_water_per_thickness']:+.2f}   r(sugar, band depth) {w['r_band_depth']:+.2f}"
              f"   r(sugar, S d) {w['r_thickness']:+.2f}")

    # leave one variety out: endmembers from two varieties, contents on the third,
    # a one-line calibration sugar = a + b * feature fitted on the two.
    for v in vars_:
        te = variety == v; tr = ~te
        m_tr, _ = fit(R[tr], lam_s, steps=2500)
        m_te, _ = fit(R[te], lam_s, steps=800, model=m_tr, freeze=True, lr=3e-2)
        c_tr, s_tr = contents(m_tr); c_te, s_te = contents(m_te)
        feats = {"water_per_thickness": (c_tr[:, 2] / s_tr, c_te[:, 2] / s_te),
                 "water_per_area": (c_tr[:, 2], c_te[:, 2]),
                 "band_depth": (depth[tr], depth[te])}
        row = {"baseline_rmse_gl": float(np.std(y[te])), "n": int(te.sum())}
        for name, (ftr, fte) in feats.items():
            A = np.polyfit(ftr, y[tr], 1)
            row[name] = scores(y[te], np.polyval(A, fte))
        out["lovo"][v] = row
        print(f"  held out {v:8s} n={te.sum():3d}: " + "   ".join(
            f"{name} RMSE {row[name]['rmse_gl']:.1f} (r {row[name]['r']:+.2f})" for name in feats)
              + f"   predict-the-mean {np.std(y[te]):.1f}")
    with open("results/exp5_km_pinn.json", "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
