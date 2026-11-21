import os
import sys

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
D = sys.argv[1]


def load(n):
    return np.asarray(Image.open(os.path.join(D, n)).convert('RGB')).astype(np.float32)


def save(n, a):
    Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8)).save(os.path.join(D, n), optimize=True)


def darken(a, w=None):
    mx = a.max(2); mn = a.min(2); sat = (mx - mn) / np.maximum(mx, 1)
    k = np.clip((0.30 - sat) / 0.12, 0, 1)
    L = a.mean(2, keepdims=True)
    d = (15 + 0.19 * L) * np.array([0.96, 1.0, 1.05], np.float32)
    d = np.minimum(d, np.maximum(a, d * 0.6))
    k = k[..., None] * (1 if w is None else w[..., None])
    return a * (1 - k) + d * k


def glow(e, halo, gain):
    t = cv2.dilate(e, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    t = np.maximum(t, cv2.GaussianBlur(t, (0, 0), halo) * gain)
    return np.maximum(t, cv2.GaussianBlur(t, (0, 0), halo * 3) * gain * 0.6)


def save_rgba(n, a):
    Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), 'RGBA').save(os.path.join(D, n), optimize=True)


def make_glow(e):
    t = cv2.dilate(e, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    t = np.maximum(t, cv2.GaussianBlur(t, (0, 0), 2.0) * 0.45)
    alpha = np.clip(t.max(2) * 1.15, 0, 255)
    hue = cv2.GaussianBlur(e, (0, 0), 8.0) + cv2.GaussianBlur(e, (0, 0), 40.0) * 0.2
    mx = hue.max(2, keepdims=True)
    rgb = np.where(mx > 0.02, hue / np.maximum(mx, 1e-6) * 255, np.array([107, 255, 128], np.float32))
    return np.dstack([rgb, alpha])


def wear(a, seed, amount=1.0):
    h, w = a.shape[:2]
    rng = np.random.default_rng(seed)
    n1 = cv2.resize(rng.random((h // 96, w // 96)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    n2 = cv2.resize(rng.random((h // 12, w // 12)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    sc = np.zeros((h, w), np.float32)
    for _ in range(int(1400 * amount)):
        x, y = rng.integers(0, w), rng.integers(0, h)
        ang = rng.random() * np.pi
        ln = rng.integers(12, 140)
        cv2.line(sc, (int(x), int(y)), (int(x + np.cos(ang) * ln), int(y + np.sin(ang) * ln)), float(0.25 + 0.75 * rng.random()), 1, cv2.LINE_AA)
    sc = cv2.GaussianBlur(sc, (0, 0), 0.6)
    dust = (rng.random((h, w)) > 0.9988).astype(np.float32)
    mx = a.max(2); mn = a.min(2)
    paint = (np.clip((0.30 - (mx - mn) / np.maximum(mx, 1)) / 0.12, 0, 1) * np.clip((120 - mx) / 40, 0, 1))[..., None]
    out = a * (1 + (0.16 * (n1 - 0.5) + 0.07 * (n2 - 0.5))[..., None] * paint * amount)
    return out + (sc * 16 + dust * 22)[..., None] * paint * amount


if os.environ.get("RETONE_PANEL_ONLY"):
    save('ckpanel_base.png', wear(load('ckpanel_base.png'), 12, 0.7))
    e = load('ckpanel_emit.png')
    save_rgba('ckpanel_glow.png', make_glow(e))
    save('ckpanel_emit.png', glow(e, 3.0, 0.55))
    print("retoned: front panel only")
    sys.exit(0)
b = load('ckconsole_base.png'); e = load('ckconsole_emit.png')
_kp = os.path.join(D, 'ckconsole_keep.png')
kp = (np.asarray(Image.open(_kp).convert('L')).astype(np.float32) / 255)[..., None] if os.path.exists(_kp) else 0.0
b = darken(b) * (1 - kp) + b * kp
la = np.clip(cv2.GaussianBlur(e.max(2), (0, 0), 0.7) / 110, 0, 1)[..., None]
if os.environ.get("NO_DECALS") is None:
    la = la * 0
save('ckconsole_base.png', wear(b, 11) * (1 - la) + np.array([226, 228, 220], np.float32) * la)
save_rgba('ckconsole_glow.png', make_glow(e))
save('ckconsole_emit.png', glow(e, 3.0, 0.55))
del b, e, la
save('ckpanel_base.png', wear(load('ckpanel_base.png'), 12, 0.7))
e = load('ckpanel_emit.png')
save_rgba('ckpanel_glow.png', make_glow(e))
save('ckpanel_emit.png', glow(e, 3.0, 0.55))
save_rgba('cockpit_glow.png', make_glow(load('cockpit_emit.png')))
del e
vs = []; vt = []; g = m = None; F = []
for l in open(os.path.join(D, 'typhoon.obj')):
    if l.startswith('v '):
        vs.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('vt '):
        vt.append([float(x) for x in l.split()[1:3]])
    elif l.startswith('g ') or l.startswith('o '):
        g = l.split()[1]
    elif l.startswith('usemtl'):
        m = l.split()[1]
    elif l.startswith('f ') and g == 'canopy_interior' and m == 'cockpit':
        t = [x.split('/') for x in l.split()[1:]]
        for i in range(1, len(t) - 1):
            F.append([int(t[0][0]) - 1, int(t[i][0]) - 1, int(t[i + 1][0]) - 1, int(t[0][1]) - 1, int(t[i][1]) - 1, int(t[i + 1][1]) - 1])
vs = np.array(vs); vt = np.array(vt); F = np.array(F)
P = vs[F[:, :3]]
c = P.mean(1)
sel = (P[:, :, 1].max(1) < 0.90) & (c[:, 2] > 5.85) & (c[:, 2] < 7.75) & (np.abs(c[:, 0]) < 0.56)
img = load('cockpit_base.png'); H, W = img.shape[:2]
mask = np.zeros((H, W), np.uint8)
for t in F[sel][:, 3:]:
    uv = vt[t]
    cv2.fillPoly(mask, [np.round(np.stack([uv[:, 0] * W, (1 - uv[:, 1]) * H], 1)).astype(np.int32)], 255)
w = cv2.GaussianBlur(cv2.dilate(mask.astype(np.float32) / 255, np.ones((5, 5), np.uint8)), (0, 0), 1.5)
save('cockpit_base.png', darken(img, w))
mk = np.asarray(Image.open(os.path.join(D, 'cockpit_mask.png')).convert('RGBA')).astype(np.float32)
mk[..., 3] *= (1 - 0.7 * w)
Image.fromarray(np.clip(mk + 0.5, 0, 255).astype(np.uint8), 'RGBA').save(os.path.join(D, 'cockpit_mask.png'), optimize=True)
print(f"retoned: consoles, {int(sel.sum())} tub wall triangles, legend glow")
