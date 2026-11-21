import math
import os
import sys

import numpy as np
from scipy.ndimage import gaussian_filter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ckpaint as cp

ST = sys.argv[1]
W, H = 4096, 2048
FLAPS = 16
rng = np.random.default_rng(1604)

u = (np.arange(W) + 0.5) / W
v = 1.0 - (np.arange(H) + 0.5) / H
U, Vv = np.meshgrid(u, v)
outer = Vv >= 0.5
t_out = np.clip((Vv - 0.5) / 0.5, 0, 1)
t_in = np.clip(Vv / 0.485, 0, 1)
sec = U * FLAPS
k = np.floor(sec).astype(int) % FLAPS
f = sec - np.floor(sec)
flap = f < 0.62
fx = np.where(flap, f / 0.62, (f - 0.62) / 0.38)


def ss(e0, e1, x):
    x = np.clip((x - e0) / (e1 - e0), 0, 1)
    return x * x * (3 - 2 * x)


def noise(sig, seed, aspect=(1.0, 1.0)):
    r = np.random.default_rng(seed).standard_normal((H // 4, W // 4)).astype(np.float32)
    r = gaussian_filter(r, (sig * aspect[0] / 4, sig * aspect[1] / 4), mode="wrap")
    r = np.kron(r, np.ones((4, 4), np.float32))
    r = gaussian_filter(r, 2.0, mode="wrap")
    return r / max(float(r.std()), 1e-6)


streak = noise(40, 3, (6.0, 0.25))
blot = noise(60, 5)
fine = noise(4, 7)

flap_tone = 1 + rng.normal(0, 0.07, FLAPS)
flap_tint = rng.normal(0, 0.03, FLAPS)
inconel = np.array([0.150, 0.142, 0.134])
seal_c = np.array([0.095, 0.090, 0.086])
bronze = np.array([0.33, 0.26, 0.17])
violet = np.array([0.19, 0.18, 0.26])
soot = np.array([0.055, 0.052, 0.050])
inner_c = np.array([0.36, 0.33, 0.29])

col = np.where(flap[..., None], inconel * flap_tone[k][..., None], seal_c * (0.9 + 0.2 * flap_tone[k][..., None]))
col = col + flap_tint[k][..., None] * np.array([1.0, 0.6, 0.2])
heat = ss(0.45, 0.85, t_out) * (0.75 + 0.25 * np.sin(fx * math.pi))
col = col * (1 - 0.55 * heat[..., None] * ss(0.45, 0.70, t_out)[..., None]) + bronze * (0.55 * heat * ss(0.45, 0.70, t_out) * (1 - ss(0.72, 0.92, t_out)))[..., None]
col = col * (1 - 0.6 * ss(0.72, 0.92, t_out)[..., None]) + violet * (0.6 * ss(0.72, 0.92, t_out) * (1 - ss(0.94, 1.0, t_out)))[..., None]
col = col * (1 - 0.85 * ss(0.94, 1.0, t_out))[..., None] + soot * (0.85 * ss(0.94, 1.0, t_out))[..., None]
col = col * (1 + 0.07 * streak + 0.04 * blot)[..., None]
col = col * (1 - 0.25 * ss(0.10, 0.0, t_out))[..., None]
h = np.zeros((H, W), np.float32)
edge_d = np.minimum(fx, 1 - fx) * np.where(flap, 0.62, 0.38) * (2 * math.pi * 0.42 / FLAPS)
h += np.where(flap, -0.6 * np.exp(-edge_d / 0.004), -0.3 * np.exp(-edge_d / 0.003))
rib = np.exp(-((fx - 0.5) / 0.05) ** 2) * flap * ss(0.05, 0.12, t_out) * ss(0.95, 0.85, t_out)
h += 0.8 * rib
frames = sum(np.exp(-((t_out - tf) / 0.006) ** 2) for tf in (0.14, 0.50))
h -= 0.4 * frames * flap
px_m = W / (2 * math.pi * 0.42)
ycell = (t_out * 0.61) / 0.028
riv_rows = np.zeros((H, W), np.float32)
for e in (0.10, 0.90):
    du = (fx - e) * 0.62 * (2 * math.pi * 0.42 / FLAPS)
    dv = ((ycell % 1.0) - 0.5) * 0.028
    riv_rows += np.exp(-(du ** 2 + dv ** 2) / (2 * 0.0018 ** 2))
for tf in (0.14, 0.50):
    dv = (t_out - tf) * 0.61
    xcell = fx * 0.62 * (2 * math.pi * 0.42 / FLAPS) / 0.022
    du = ((xcell % 1.0) - 0.5) * 0.022
    riv_rows += np.exp(-(du ** 2 + (dv - 0.010) ** 2) / (2 * 0.0018 ** 2))
riv_rows *= flap * ss(0.03, 0.06, t_out) * ss(0.97, 0.93, t_out)
h += 0.5 * riv_rows
col = col * (1 + 0.10 * riv_rows[..., None]) * (1 - 0.18 * np.where(flap, np.exp(-edge_d / 0.004), 0)[..., None])
col = col * (1 + 0.10 * rib[..., None])
metal = np.where(flap, 0.70, 0.60)
smooth = np.where(flap, 0.36, 0.28) - 0.15 * ss(0.94, 1.0, t_out) + 0.04 * streak - 0.05 * np.abs(blot)

ci = inner_c * (1 + 0.05 * streak + 0.04 * blot)[..., None]
throat = np.exp(-((t_in - 0.58) / 0.16) ** 2)
ci = ci * (1 - 0.55 * throat)[..., None]
ci = ci * (1 - 0.35 * ss(0.15, 0.0, t_in))[..., None]
seam = np.exp(-((((U * FLAPS) % 1.0) - 0.5) / 0.012) ** 2)
ci = ci * (1 - 0.35 * seam)[..., None]
lip = (Vv > 0.485) & (Vv < 0.5)
ci = np.where(lip[..., None], soot * 1.4, ci)
hi = -0.5 * seam + 0.15 * fine
col = np.where(outer[..., None], col, ci)
h = np.where(outer, h + 0.015 * fine, hi)
metal = np.where(outer, metal, 0.55)
smooth = np.where(outer, smooth, 0.32 - 0.10 * throat)

cp.save(np.concatenate([np.clip(col, 0, 1), np.ones((H, W, 1))], -1)[..., :3], os.path.join(ST, "nozzle_base.png"), "RGB")
nx, ny, _ = cp.normal_from_height(h * 1.5, 0.9)
cp.save(cp.pack_normal(nx, ny), os.path.join(ST, "nozzle_normal.png"), "RGBA")
mk = np.zeros((H, W, 4), np.float32)
mk[..., 0] = np.clip(metal, 0, 1)
mk[..., 3] = np.clip(smooth, 0.05, 0.9)
cp.save(mk, os.path.join(ST, "nozzle_mask.png"), "RGBA")
print("nozzle textures: %d x %d (%.0f texels per metre round the nozzle)" % (W, H, px_m))
