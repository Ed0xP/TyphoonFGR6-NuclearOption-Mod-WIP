import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None
ST = sys.argv[1]
T, F, g = [], [], None
for l in open(os.path.join(ST, "typhoon.obj"), errors="ignore"):
    if l.startswith("vt "):
        T.append([float(x) for x in l.split()[1:3]])
    elif l[:2] in ("o ", "g "):
        g = l.split()[1]
    elif l.startswith("f ") and g in ("pod_R", "pod_L"):
        c = [int(t.split("/")[1]) for t in l.split()[1:]]
        for j in range(1, len(c) - 1):
            F.append((c[0], c[j], c[j + 1]))
U = np.array(T)[np.array(F) - 1]
path = os.path.join(ST, "exwing_normal.png")
im = Image.open(path).convert("RGBA")
S = im.size[0]
mk = Image.new("L", (S, S), 0)
d = ImageDraw.Draw(mk)
for t in U:
    d.polygon([(u * S, (1 - v) * S) for u, v in t], fill=255)
m = np.asarray(mk) > 0
a = np.asarray(im).astype(np.float32) / 255.0
nx, ny = a[..., 3] * 2 - 1, a[..., 1] * 2 - 1
lab, n = ndi.label(m)
kept = flat = 0
for k, sl in enumerate(ndi.find_objects(lab)):
    mm = lab[sl] == k + 1
    h, w = mm.shape
    if mm.sum() < 400:
        continue
    X, Y = nx[sl].copy(), ny[sl].copy()
    strong = (np.abs(X) + np.abs(Y) > 0.10) & mm
    keep = np.zeros_like(mm)
    if h >= w:
        frac = strong.sum(1) / np.maximum(mm.sum(1), 1)
        rows = ndi.binary_dilation(frac > 0.62, iterations=1)
        keep[rows, :] = True
    else:
        frac = strong.sum(0) / np.maximum(mm.sum(0), 1)
        cols = ndi.binary_dilation(frac > 0.62, iterations=1)
        keep[:, cols] = True
    edge = mm & ~ndi.binary_erosion(mm, iterations=3)
    keep &= mm
    X2 = np.where(keep, X * 0.6, 0.0)
    Y2 = np.where(keep, Y * 0.6, 0.0)
    X2, Y2 = np.where(edge, X, X2), np.where(edge, Y, Y2)
    nx[sl] = np.where(mm, X2, nx[sl])
    ny[sl] = np.where(mm, Y2, ny[sl])
    kept += int((keep & strong).sum())
    flat += int((strong & ~keep & ~edge).sum())
a[..., 3] = nx * 0.5 + 0.5
a[..., 1] = ny * 0.5 + 0.5
a[..., 2] = a[..., 1]
Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(path)
print("pod_clean: %d islands, %d line texels kept (joints), %d flattened" % (n, kept, flat))
