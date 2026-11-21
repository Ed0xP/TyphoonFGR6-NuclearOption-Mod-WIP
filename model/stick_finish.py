import os
import sys

import cv2
import numpy as np
from PIL import Image

ST, NPZ = sys.argv[1], sys.argv[2]
d = np.load(NPZ)
V, T, UV = d["V"].astype(np.float64), d["T"], d["UV"]
fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
if (fn * (V[T].mean(1) - V.mean(0))).sum() < 0:
    fn = -fn
vn = np.zeros_like(V)
for k in range(3):
    np.add.at(vn, T[:, k], fn)
vn /= np.maximum(np.linalg.norm(vn, axis=1), 1e-12)[:, None]
acc, cnt = np.zeros_like(V), np.zeros(len(V))
PAIRS = ((0, 1), (1, 2), (2, 0))
for a, b in PAIRS:
    np.add.at(acc, T[:, a], V[T[:, b]]); np.add.at(cnt, T[:, a], 1)
    np.add.at(acc, T[:, b], V[T[:, a]]); np.add.at(cnt, T[:, b], 1)
cnt = np.maximum(cnt, 1)
el = float(np.linalg.norm(V[T[:, 1]] - V[T[:, 0]], axis=1).mean())
curv = -((acc / cnt[:, None] - V) * vn).sum(1) / el
for _ in range(2):
    a2 = np.zeros(len(V))
    for a, b in PAIRS:
        np.add.at(a2, T[:, a], curv[T[:, b]]); np.add.at(a2, T[:, b], curv[T[:, a]])
    curv = 0.5 * curv + 0.5 * a2 / cnt
base = np.asarray(Image.open(os.path.join(ST, "ckstick_base.png")).convert("RGB")).astype(np.float32) / 255
R = base.shape[0]
img = np.zeros((R, R), np.float32)
cov = np.zeros((R, R), np.float32)
tv = curv[T].mean(1)
for i in range(len(T)):
    p = np.round(np.stack([UV[i][:, 0] * R, (1 - UV[i][:, 1]) * R], 1)).astype(np.int32)
    cv2.fillConvexPoly(img, p, float(tv[i]))
    cv2.fillConvexPoly(cov, p, 1.0)
img = cv2.GaussianBlur(img * cov, (0, 0), 2.5) / np.maximum(cv2.GaussianBlur(cov, (0, 0), 2.5), 1e-3)
rng = np.random.default_rng(31)


def nz(sig, sx=None):
    r = rng.standard_normal((R, R)).astype(np.float32)
    r = cv2.GaussianBlur(r, (0, 0), sigmaX=sig if sx is None else sx[0], sigmaY=sig if sx is None else sx[1])
    return (r - r.mean()) / max(float(r.std()), 1e-6)


n1, n2 = nz(1.1), nz(7.0)
ridge = np.clip((img - 0.035) * 9.0, 0, 1)
hollow = np.clip((-img - 0.020) * 8.0, 0, 1)
wear = np.clip(ridge * 1.3 - 0.25 + 0.22 * n2, 0, 1) * np.clip(0.65 + 0.35 * n1, 0, 1)
sc = nz(1.0, (14, 0.7)) + nz(1.0, (0.7, 14))
sc = np.clip((sc - 2.9) * 1.1, 0, 1)
OWN = "own" in d.files
if OWN:
    dark = (base.mean(2) < 0.22).astype(np.float32)
    dark = cv2.GaussianBlur(dark, (0, 0), 1.0)
    img = cv2.GaussianBlur(img * cov, (0, 0), 9.0) / np.maximum(cv2.GaussianBlur(cov, (0, 0), 9.0), 1e-3)
    _c = img[cov > 0.5]
    r0, r1 = np.percentile(_c, 87), np.percentile(_c, 97.5)
    h0, h1 = np.percentile(_c, 9), np.percentile(_c, 2)
    ridge = np.clip((img - r0) / max(r1 - r0, 1e-6), 0, 1)
    hollow = np.clip((h0 - img) / max(h0 - h1, 1e-6), 0, 1)
    wear = np.clip(ridge * 1.5 - 0.10 + 0.14 * n2, 0, 1) * np.clip(0.60 + 0.40 * n1, 0, 1)
    peb = nz(1.7)
    peb = np.clip(peb, -2, 2) / 2
    scuff = np.clip((nz(60.0) - 0.6) * 1.2, 0, 1) * np.clip(0.5 + 0.5 * nz(3.0), 0, 1)
    fine = np.clip((nz(1.0, (9, 0.6)) + nz(1.0, (0.6, 9)) - 2.5) * 1.2, 0, 1)
    cast = np.clip(base * 1.55, 0, 1) * (1 - 0.34 * hollow)[..., None] * (1 + 0.05 * n2 + 0.09 * peb)[..., None]
    cast += (np.array([0.47, 0.48, 0.485], np.float32) - cast) * (0.66 * wear)[..., None]
    cast += (np.array([0.27, 0.275, 0.28], np.float32) - cast) * (0.16 * scuff)[..., None]
    cast += (np.array([0.36, 0.37, 0.375], np.float32) - cast) * (0.55 * fine)[..., None]
    cast += (np.array([0.20, 0.19, 0.17], np.float32) - cast) * (0.10 * hollow)[..., None]
    other = base * (1 - 0.18 * hollow)[..., None] * (1 + 0.03 * n2)[..., None]
    other += (np.array([0.62, 0.62, 0.61], np.float32) - other) * (0.30 * wear)[..., None]
    out = cast * dark[..., None] + other * (1 - dark)[..., None]
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(ST, "ckstick_base.png"), optimize=True)
    mk = np.asarray(Image.open(os.path.join(ST, "ckstick_mask.png")).convert("RGBA")).astype(np.float32) / 255
    mk[..., 3] = np.clip(mk[..., 3] + dark * (-0.04 + 0.26 * wear + 0.12 * scuff - 0.14 * hollow - 0.05 * peb + 0.10 * fine), 0, 1)
    mk[..., 0] = np.clip(mk[..., 0] + dark * 0.35 * wear * (wear > 0.7), 0, 1)
    mk[..., 1] = mk[..., 2] = mk[..., 0]
    Image.fromarray((mk * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(ST, "ckstick_mask.png"), optimize=True)
    h = (0.55 * peb * 2 + 0.35 * nz(2.6) - 1.8 * fine - 0.9 * wear) * (0.35 + 0.65 * dark)
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.16
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.16
    nm = np.ones((R, R, 4), np.float32)
    nm[..., 3] = np.clip(0.5 - gx * 0.5, 0, 1)
    nm[..., 1] = np.clip(0.5 + gy * 0.5, 0, 1)
    Image.fromarray((nm * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(ST, "ckstick_normal.png"), optimize=True)
else:
    LIFT, MATT = float(os.environ.get("STICK_LIFT", "1.55")), float(os.environ.get("STICK_MATT", "0.10"))
    out = np.clip(base * LIFT, 0, 1) * (1 - 0.24 * hollow)[..., None] * (1 + 0.035 * n2)[..., None]
    out += (np.array([0.40, 0.41, 0.42], np.float32) - out) * (0.50 * wear)[..., None]
    out += (np.array([0.33, 0.34, 0.35], np.float32) - out) * (0.45 * sc)[..., None]
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(ST, "ckstick_base.png"), optimize=True)
    mk = np.asarray(Image.open(os.path.join(ST, "ckstick_mask.png")).convert("RGBA")).astype(np.float32) / 255
    if mk.shape[0] != R:
        mk = cv2.resize(mk, (R, R), interpolation=cv2.INTER_LINEAR)
    mk[..., 3] = np.clip(mk[..., 3] - MATT + 0.22 * wear - 0.10 * hollow + 0.03 * n2 + 0.10 * sc, 0, 1)
    Image.fromarray((mk * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(ST, "ckstick_mask.png"), optimize=True)
    h = 0.55 * n1 + 0.45 * nz(2.2) - 1.6 * sc
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.085
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.085
    nm = np.ones((R, R, 4), np.float32)
    nm[..., 3] = np.clip(0.5 - gx * 0.5, 0, 1)
    nm[..., 1] = np.clip(0.5 + gy * 0.5, 0, 1)
    Image.fromarray((nm * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(ST, "ckstick_normal.png"), optimize=True)
print("stick grip: %d px, ridges %.1f %% of the skin, hollows %.1f %%" % (R, 100 * float((ridge * cov).sum() / cov.sum()), 100 * float((hollow * cov).sum() / cov.sum())))
