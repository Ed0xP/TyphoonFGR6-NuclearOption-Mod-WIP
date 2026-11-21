import math
import os
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

INS, QH = 0.11, 1.30
VE = INS / (1 + INS)
CELL = 0.115

WHITE = np.array((1.00, 0.90, 0.66))
YELLOW = np.array((1.00, 0.72, 0.30))
ORANGE = np.array((1.00, 0.42, 0.08))
RED = np.array((0.92, 0.26, 0.08))
PINK = np.array((0.85, 0.32, 0.42))
VIOLET = np.array((0.55, 0.40, 1.00))


def ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return a + (b - a) * np.clip(t, 0, 1)[..., None]


def half_width(s):
    return 1.0 + 0.08 * np.sin(np.clip(s / 0.12, 0, 1) * np.pi) - 0.62 * s ** 0.8


def save(name, rgb, a):
    rgb = np.clip(rgb, 0, 1)
    a = np.clip(a, 0, 1)
    px = np.concatenate([rgb, a[..., None]], -1)[::-1]
    Image.fromarray((px * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(OUT, name))
    print(name, px.shape[1], "x", px.shape[0], "peak", round(float(rgb.max()), 3), "alpha max", round(float(a.max()), 3))


rng = np.random.default_rng(7)

W, H = 256, 1024
v = ((np.arange(H) + 0.5) / H)[:, None]
q = np.abs((np.arange(W) + 0.5) / W * 2 - 1)[None, :]
s = np.clip((v - VE) / (1 - VE), 0, 1)
outside = ss(VE - 0.010, VE + 0.012, v)
rho = q * QH / half_width(s)
edge = 1 / (1 + np.exp(np.clip((rho - 0.92) / 0.05, -50, 50)))
body = np.maximum(1 - 0.45 * np.minimum(rho * rho, 2), 0) * edge
bulb = np.exp(-s / 0.17)
tail = (1 - s) ** 1.7
along = 0.80 * bulb + 0.55 * tail
ph = (s / CELL + 0.35) % 1.0
amp = np.exp(-s / 0.30) * ss(0.02, 0.08, s)
lens_w = 0.18 + 0.30 * np.sin(np.pi * ph)
node = np.exp(-((ph - 0.5) / 0.20) ** 2)
diamond = amp * node * np.exp(-(rho / lens_w) ** 2.4)
core = np.exp(-(rho / 0.45) ** 2)
turb = gaussian_filter(rng.random((H, W)), (40, 6))
turb = (turb - turb.min()) / np.ptp(turb)
turb = 0.80 + 0.40 * turb
i_out = body * (along * (0.45 + 0.70 * core) * (0.85 + 0.15 * turb) + 0.28 * diamond)
i_in = body * (0.22 + 0.30 * core) * ss(0, 1, v / (VE * 0.4))
inten = i_in + (i_out - i_in) * outside
inner = np.exp(-(rho / 0.28) ** 2)
col = mix(ORANGE, YELLOW, inner * (0.35 + 0.65 * bulb) + 0.25 * bulb * core)
col = mix(col, WHITE, np.clip(inner * bulb * 0.8 + diamond * 1.1, 0, 1) * 0.75)
col = mix(col, RED, ss(0.12, 0.70, s) * (1 - diamond))
col = mix(col, PINK, ss(0.50, 1.0, s) * 0.55)
col = mix(col, VIOLET, np.clip((rho - 0.62) / 0.38, 0, 1) * np.clip(1 - s * 5, 0, 1) * 0.30)
col = mix(col, YELLOW, (1 - outside) * 0.45)
peak = np.percentile(inten, 99.8)
inten = inten / peak
alpha = np.clip(inten, 0, 1) * (0.85 * bulb + 0.22 * tail + 0.30 * diamond) * edge
alpha = alpha + (1 - outside) * 0.12 * body
save("reheat_plume.png", col * np.clip(inten, 0, 1)[..., None], alpha)

G = 256
d = (np.arange(G) + 0.5) / G * 2 - 1
dx, dy = np.meshgrid(d, d)
r = np.hypot(dx, dy)
ang = np.arctan2(dy, dx)
disc = 1 / (1 + np.exp((r - 0.86) / 0.04))
hot = np.clip(1 - r * r, 0, 1) ** 0.7
gutters = np.exp(-((((ang / (2 * math.pi) * 12) % 1.0) - 0.5) / 0.10) ** 2) * ss(0.22, 0.32, r) * ss(0.90, 0.78, r)
ring = np.exp(-((r - 0.55) / 0.035) ** 2) + 0.7 * np.exp(-((r - 0.30) / 0.03) ** 2)
cone = np.exp(-(r / 0.13) ** 2)
detail = 1 - 0.13 * np.clip(gutters + ring, 0, 1) - 0.10 * cone
c_core = mix(mix(ORANGE, YELLOW, hot ** 0.9), WHITE, hot ** 4 * 0.45)
i_core = disc * detail * (0.70 + 0.30 * hot)
save("reheat_core.png", c_core * i_core[..., None], disc * 0.92)

g = np.clip(1 - r * r, 0, 1) ** 1.4
save("reheat_glow.png", mix(ORANGE, np.array((1.0, 0.86, 0.62)), g ** 1.4) * g[..., None], g * 0.35)

LW, LH = 256, 128
u = ((np.arange(LW) + 0.5) / LW)[None, :]
vv = ((np.arange(LH) + 0.5) / LH)[:, None]
seams = np.exp(-((((u * 20) % 1.0) - 0.5) / 0.07) ** 2)
streak = gaussian_filter(rng.random((LH, LW)), (10, 1.5))
streak = (streak - streak.min()) / np.ptp(streak)
i_l = (1.0 - 0.45 * vv) * (1 - 0.55 * seams) * (0.85 + 0.25 * streak) * ss(0.0, 0.08, vv) * ss(1.0, 0.94, vv)
c_l = mix(mix(YELLOW, ORANGE, (vv * np.ones_like(u)) * 1.2), RED, seams * 0.5)
save("reheat_liner.png", c_l * np.clip(i_l, 0, 1)[..., None], np.clip(i_l, 0, 1) * 0.45)
