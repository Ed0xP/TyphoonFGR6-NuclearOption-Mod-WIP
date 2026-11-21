import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ckskin

ST = sys.argv[1]
V, VT, F, T = [], [], [], []
cur = None
for l in open(os.path.join(ST, "typhoon.obj")):
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vt "):
        VT.append([float(x) for x in l.split()[1:3]])
    elif l[:2] in ("o ", "g "):
        cur = l.split()[1]
    elif l.startswith("f ") and cur == "canopy_interior":
        c = [p.split("/") for p in l.split()[1:]]
        F.append([int(p[0]) - 1 for p in c])
        T.append([int(p[1]) - 1 for p in c])
V, VT = np.array(V), np.array(VT)

key, par = {}, {}


def kid(i):
    return key.setdefault(tuple(np.round(V[i], 4)), len(key))


def find(a):
    while par.setdefault(a, a) != a:
        par[a] = par[par[a]]
        a = par[a]
    return a


for f in F:
    ks = [kid(i) for i in f]
    for a in ks[1:]:
        par[find(a)] = find(ks[0])
comp = {}
for fi, f in enumerate(F):
    comp.setdefault(find(kid(f[0])), []).append(fi)
kind = np.zeros(len(F), np.float32)
for c, fs in comp.items():
    P_ = V[[i for fi in fs for i in F[fi]]]
    lo, hi = P_.min(0), P_.max(0)
    if len(fs) > 2000 and lo[1] > 0.6:
        kind[fs] = 1
    elif len(fs) < 100 and hi[2] > 8.4 and lo[1] > 0.6 and hi[1] < 1.05:
        kind[fs] = 2
print("shell: %d faces in %d pieces; frame %d faces, deck %d" % (len(F), len(comp), int((kind == 1).sum()), int((kind == 2).sum())))

base = np.asarray(Image.open(os.path.join(ST, "cockpit_base.png")).convert("RGB")).astype(np.float32) / 255
H, W = base.shape[:2]
P, UV, A = [], [], []
for fi, (f, t) in enumerate(zip(F, T)):
    if kind[fi] == 0:
        continue
    for j in range(1, len(f) - 1):
        tri = (0, j, j + 1)
        p = np.array([V[f[a]] for a in tri])
        n = np.cross(p[1] - p[0], p[2] - p[0])
        n /= max(np.linalg.norm(n), 1e-12)
        P.append(p)
        UV.append([VT[t[a]] for a in tri])
        A.append([[n[0], n[1], n[2], kind[fi]]] * 3)
tid, pos, att = ckskin.raster_attr(np.array(UV), np.array(P), np.array(A), W, H)
cover = tid >= 0
X, Y, Z = pos[..., 0], pos[..., 1], pos[..., 2]
NY = np.abs(att[..., 1])
knd = np.round(att[..., 3])
lum = base.mean(2)
sat = base.max(2) - base.min(2)
panel_box = (np.abs(X) < 0.41) & (Y > 0.55) & (Y < 1.12) & (Z > 6.95) & (Z < 7.46)
panel_box |= (np.abs(X) < 0.18) & (Y < 1.32) & (Z > 6.95) & (Z < 7.46)
if os.environ.get("SHELL_STATS"):
    for k_ in (1, 2):
        q = cover & (knd == k_) & ~panel_box
        print("  kind %d: %.1f %% of texture; lum %s; sat %s" % (k_, 100 * q.mean(), np.round(np.percentile(lum[q], [5, 25, 50, 75, 95]), 3), np.round(np.percentile(sat[q], [5, 50, 95]), 3)))
    sys.exit()
m = cover & (knd > 0) & (lum < 0.20) & (sat < 0.06) & ~panel_box
m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
print("shell: %.1f %% of the texture re-finished" % (100.0 * m.mean()))


def noise(sig, seed):
    r = np.random.default_rng(seed).standard_normal((H // 2, W // 2)).astype(np.float32)
    r = cv2.GaussianBlur(r, (0, 0), sig / 2)
    r = cv2.resize(r, (W, H), interpolation=cv2.INTER_LINEAR)
    return (r - r.mean()) / max(float(r.std()), 1e-6)


blur = cv2.GaussianBlur(lum, (0, 0), 14)
detail = np.clip((lum + 0.015) / (blur + 0.015), 0.55, 1.5) ** 0.85
arch = np.clip((Z - 7.12) / 0.10, 0, 1) * (knd == 1)
tone = np.empty_like(base)
SILL, ARCH, DECK = (0.172, 0.180, 0.176), (0.215, 0.225, 0.218), (0.150, 0.155, 0.155)
for c in range(3):
    t_ = SILL[c] + (ARCH[c] - SILL[c]) * arch
    t_ = np.where(knd == 2, DECK[c], t_)
    tone[..., c] = t_
tone *= (detail * (1 + 0.035 * noise(40, 1) + 0.02 * noise(6, 2)))[..., None]

nx_ = att[..., :3].copy()
nx_[~cover] = 0
g = np.zeros((H, W), np.float32)
for c in range(3):
    g += np.abs(cv2.Sobel(nx_[..., c], cv2.CV_32F, 1, 0, ksize=3)) + np.abs(cv2.Sobel(nx_[..., c], cv2.CV_32F, 0, 1, ksize=3))
edge = (g > 0.9).astype(np.uint8)
edge |= (cv2.distanceTransform(cover.astype(np.uint8), cv2.DIST_L2, 3) < 2.5).astype(np.uint8) & cover.astype(np.uint8)
edge = cv2.GaussianBlur(cv2.dilate(edge, np.ones((3, 3), np.uint8)).astype(np.float32), (0, 0), 1.6)
chip_n = 0.6 * noise(2.2, 3) + 0.4 * noise(9, 4)
chips = np.clip(edge * 1.6, 0, 1) * np.clip((chip_n - 0.15) * 2.2, 0, 1)
up = np.clip((NY - 0.55) / 0.3, 0, 1)
rub = np.clip((noise(55, 5) - 0.35) * 1.4, 0, 1) * np.clip(0.55 + 0.45 * noise(3.0, 6), 0, 1) * up * (knd == 1)
streak = np.random.default_rng(7).standard_normal((H, W)).astype(np.float32)
streak = cv2.GaussianBlur(streak, (0, 0), sigmaX=9, sigmaY=0.7)
streak = np.clip((streak / max(float(streak.std()), 1e-6) - 1.9) * 1.5, 0, 1) * up
dust = 0.05 * up * np.clip(0.6 + 0.4 * noise(25, 8), 0, 1)

out = tone.copy()
BARE, RUB = np.array([0.43, 0.44, 0.42], np.float32), np.array([0.30, 0.31, 0.295], np.float32)
out += (RUB - out) * (0.55 * rub)[..., None]
out += (BARE - out) * (0.45 * streak)[..., None]
out += dust[..., None]
out += (BARE - out) * (0.80 * chips)[..., None]
a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.8)[..., None]
res = base * (1 - a) + out * a
Image.fromarray((np.clip(res, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(ST, "cockpit_base.png"))

mp = os.path.join(ST, "cockpit_mask.png")
if os.path.exists(mp):
    mk = np.asarray(Image.open(mp).convert("RGBA")).astype(np.float32) / 255
    if mk.shape[:2] == (H, W):
        sm = 0.30 + 0.10 * chips + 0.06 * rub - 0.06 * dust / 0.05
        mk[..., 3] = mk[..., 3] * (1 - a[..., 0]) + sm * a[..., 0]
        mk[..., 0] = mk[..., 0] * (1 - a[..., 0]) + 0.35 * chips * a[..., 0]
        Image.fromarray((np.clip(mk, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(mp)
print("shell: cockpit_base.png and cockpit_mask.png rewritten")
