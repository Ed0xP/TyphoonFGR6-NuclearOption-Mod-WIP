import os
import sys

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

OBJ, IN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)


def load(name, mode=None):
    im = Image.open(os.path.join(IN, name))
    if mode:
        im = im.convert(mode)
    return np.asarray(im).astype(np.float32) / 255.0


def save(a, name, mode):
    im = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), mode)
    w4, h4 = (im.width + 3) // 4 * 4, (im.height + 3) // 4 * 4
    if (w4, h4) != im.size:
        im = im.resize((w4, h4), Image.LANCZOS)
    im.save(os.path.join(OUT, name), optimize=True)


base = load("cockpit_base.png", "RGB")
H, W = base.shape[:2]


def read_shell(path, group="canopy_interior"):
    V, VT, F, cur = [], [], [], None
    for line in open(path):
        if line.startswith("v "): V.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("vt "): VT.append([float(x) for x in line.split()[1:3]])
        elif line.startswith("o "): cur = line[2:].strip()
        elif line.startswith("f ") and cur == group:
            F.append([[int(p) if p else 0 for p in (t.split("/") + ["", ""])[:2]] for t in line.split()[1:]])
    return np.array(V), np.array(VT), F


def texel_positions(V, VT, F, w, h):
    pos = np.zeros((h, w, 3), np.float32)
    nrm = np.zeros((h, w, 3), np.float32)
    valid = np.zeros((h, w), bool)
    for f in F:
        for k in range(1, len(f) - 1):
            tri = [f[0], f[k], f[k + 1]]
            P = np.array([V[t[0] - 1] for t in tri]); T = np.array([VT[t[1] - 1] for t in tri])
            px, py = T[:, 0] * w, (1 - T[:, 1]) * h
            x0, x1 = max(int(np.floor(px.min())), 0), min(int(np.ceil(px.max())), w - 1)
            y0, y1 = max(int(np.floor(py.min())), 0), min(int(np.ceil(py.max())), h - 1)
            if x1 < x0 or y1 < y0:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            d = (py[1] - py[2]) * (px[0] - px[2]) + (px[2] - px[1]) * (py[0] - py[2])
            if abs(d) < 1e-9:
                continue
            l0 = ((py[1] - py[2]) * (xs - px[2]) + (px[2] - px[1]) * (ys - py[2])) / d
            l1 = ((py[2] - py[0]) * (xs - px[2]) + (px[0] - px[2]) * (ys - py[2])) / d
            l2 = 1 - l0 - l1
            m = (l0 >= -1e-3) & (l1 >= -1e-3) & (l2 >= -1e-3)
            if not m.any():
                continue
            n = np.cross(P[1] - P[0], P[2] - P[0]); ln = np.linalg.norm(n)
            if ln < 1e-12:
                continue
            p = l0[..., None] * P[0] + l1[..., None] * P[1] + l2[..., None] * P[2]
            sub = (slice(y0, y1 + 1), slice(x0, x1 + 1))
            pos[sub][m] = p[m]; nrm[sub][m] = n / ln; valid[sub][m] = True
    return pos, nrm, valid


V, VT, F = read_shell(OBJ)
h2, w2 = H // 2, W // 2
pos, nrm, valid = texel_positions(V, VT, F, w2, h2)
x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
panel = valid & (np.abs(x) < 0.40) & (y > 0.60) & (y < 1.30) & (z > 7.12) & (z < 7.60) & (nrm[..., 2] < -0.15)
panel = ndi.binary_closing(panel, iterations=4)
panel = ndi.binary_dilation(panel, iterations=3)
keep = np.asarray(Image.fromarray((panel * 255).astype(np.uint8)).resize((W, H), Image.NEAREST)).astype(np.float32) / 255
keep = ndi.gaussian_filter(keep, 3.0)
keep = np.clip(keep * 1.6, 0, 1)
print(f"protected (instrument panel): {keep.mean() * 100:.1f}% of the texture")

AO = os.environ.get("SHELL_AO", "")
if AO and os.path.exists(AO):
    d = np.load(AO)

    def up(a):
        im = Image.fromarray((np.clip(a.astype(np.float32), 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
        return np.asarray(im.resize((W, H), Image.BILINEAR)).astype(np.float32) / 255.0
    ao_old, ao_new = up(d["old"]), up(d["new"])
    f = (0.45 + 0.55 * ao_new) / np.maximum(0.30 + 0.70 * ao_old, 0.12)
    base_ao = np.clip(base * f[..., None], 0, 1)
    print("ambient occlusion re-baked for the new seat and controls")
else:
    base_ao = base
    print("no shell_ao.npz: baked shading kept")

base_in = base
base = base_ao
lum = base.mean(2, keepdims=True)
sat = base.max(2, keepdims=True) - base.min(2, keepdims=True)
blueish = np.clip((base[..., 2:3] - base[..., 0:1] - 0.015) * 12, 0, 1) * np.clip(1 - (sat - 0.08) * 8, 0, 1)
neutral = lum * np.array([1.0, 1.0, 1.01], np.float32)
b2 = base * (1 - 0.85 * blueish) + neutral * 0.85 * blueish
b2 = np.clip(b2, 0, 1) ** 0.88
b2 = b2 * 1.04
import cv2
_g = (np.clip(b2, 0, 1) * 255).astype(np.uint8)
b2 = cv2.ximgproc.guidedFilter(_g, _g, radius=3, eps=(0.05 * 255) ** 2).astype(np.float32) / 255
blur = np.stack([ndi.gaussian_filter(b2[..., c], 1.4) for c in range(3)], -1)
b2 = b2 + 0.5 * (b2 - blur)
b2 = np.clip(b2, 0, 1)
out_base = base_in * keep[..., None] + b2 * (1 - keep[..., None])
save(out_base, "cockpit_base.png", "RGB")

nrm_old = np.asarray(Image.open(os.path.join(IN, "cockpit_normal.png")).convert("RGBA").resize((W, H), Image.BICUBIC)).astype(np.float32) / 255
ox = nrm_old[..., 3] * 2 - 1
oy = nrm_old[..., 1] * 2 - 1
L = base_in.mean(2)
hp = L - ndi.gaussian_filter(L, 2.5)
height = ndi.gaussian_filter(hp, 0.7)
gy, gx = np.gradient(height)
s = 0.0 * (1 - keep)
rx, ry = -gx * s, gy * s
k_n = keep + 0.5 * (1 - keep)
nx, ny = ox * k_n + rx, oy * k_n + ry
nz = np.sqrt(np.clip(1 - np.clip(ox * ox + oy * oy, 0, 0.99), 0.01, 1)) * np.ones_like(nx)
ln = np.sqrt(nx * nx + ny * ny + nz * nz)
nx, ny = nx / ln, ny / ln
nx = np.where(keep > 0.999, ox, nx)
ny = np.where(keep > 0.999, oy, ny)
packed = np.ones((H, W, 4), np.float32)
packed[..., 1] = packed[..., 2] = ny * 0.5 + 0.5
packed[..., 3] = nx * 0.5 + 0.5
save(packed, "cockpit_normal.png", "RGBA")

mask_old = np.asarray(Image.open(os.path.join(IN, "cockpit_mask.png")).convert("RGBA").resize((W, H), Image.BICUBIC)).astype(np.float32) / 255
metal = mask_old[..., 0] * 0.3
smooth = np.clip(0.28 + 0.25 * mask_old[..., 3] + 0.12 * (L - 0.3), 0.15, 0.6)
m2 = np.stack([metal, metal, metal, smooth], -1)
mask = mask_old * keep[..., None] + m2 * (1 - keep[..., None])
save(mask, "cockpit_mask.png", "RGBA")
save(load("cockpit_emit.png", "RGB"), "cockpit_emit.png", "RGB")
print("written:", ", ".join(sorted(f for f in os.listdir(OUT) if f.startswith("cockpit_"))))
