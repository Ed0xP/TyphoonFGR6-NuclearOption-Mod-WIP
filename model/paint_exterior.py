import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ckpanel
import ckskin

Image.MAX_IMAGE_PIXELS = None
OBJ, SRC, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
R = int(sys.argv[4]) if len(sys.argv) > 4 else 4096

BLACK = np.array([0.098, 0.102, 0.110], np.float32)
GREY = np.array([0.60, 0.63, 0.66], np.float32)
RADOME = np.array([0.61, 0.63, 0.65], np.float32)
PALE = np.array([0.62, 0.68, 0.74], np.float32)
FORM = np.array([0.78, 0.82, 0.45], np.float32)
PAINT_GROUPS = ("airbrake", "canard_", "fin", "flaperon_", "fuselage", "pod_", "rudder", "wing_", "geardoors", "bay_door_",
                "gear_main_door", "gear_nose_door")

V, VT, tris, tgrp, names = [], [], [], [], []
g, mtl = None, None
for line in open(OBJ):
    if line.startswith("v "):
        V.append([float(x) for x in line.split()[1:4]])
    elif line.startswith("vt "):
        VT.append([float(x) for x in line.split()[1:3]])
    elif line.startswith("g ") or line.startswith("o "):
        g = line.split()[1]
    elif line.startswith("usemtl"):
        mtl = line.split()[1]
    elif line.startswith("f ") and mtl == "airframe":
        idx = [(int(x.split("/")[0]) - 1, int(x.split("/")[1]) - 1) for x in line.split()[1:]]
        if g not in names:
            names.append(g)
        for i in range(1, len(idx) - 1):
            tris.append((idx[0], idx[i], idx[i + 1]))
            tgrp.append(names.index(g))
V, VT, T, tgrp = np.array(V), np.array(VT), np.array(tris), np.array(tgrp)
P, UV = V[T[:, :, 0]], VT[T[:, :, 1]]
n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
N3 = np.repeat(n[:, None, :], 3, axis=1)
print(f"airframe: {len(T)} triangles in {len(names)} parts; painting at {R} px")
tid, pos, nrm = ckskin.raster_attr(UV, P, N3, R, R)
cover = tid >= 0
grp = np.where(cover, tgrp[np.maximum(tid, 0)], -1)
X, Y, Z = pos[..., 0], pos[..., 1], pos[..., 2]
AX = np.abs(X)


def in_group(*prefixes):
    ids = [i for i, nm in enumerate(names) if any(nm.startswith(p) for p in prefixes)]
    return np.isin(grp, ids) & cover


src_path = os.path.join(SRC, "airframe_src_base.png")
if not os.path.exists(src_path):
    Image.open(os.path.join(SRC, "airframe_base.png")).save(src_path)
old = np.asarray(Image.open(src_path).convert("RGB").resize((R, R), Image.BICUBIC)).astype(np.float32) / 255
lum = old.mean(2)
sat = old.max(2) - old.min(2)
k = max(int(7 * R / 2048) | 1, 3)
ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
lines = np.clip(cv2.morphologyEx(lum, cv2.MORPH_BLACKHAT, ker) / 0.12, 0, 1)
lines = cv2.GaussianBlur(lines, (0, 0), 0.6)
old_marks = cv2.dilate(((lum < 0.27) | (sat > 0.22)).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
lines = lines * (1 - cv2.GaussianBlur(old_marks.astype(np.float32), (0, 0), 1.5))
paintable = in_group(*PAINT_GROUPS)
dark_feature = cv2.GaussianBlur((lum < 0.25).astype(np.float32), (0, 0), 1.2) > 0.5
marks = in_group("wing_", "canard_", "fin", "rudder", "flaperon_") | (in_group("fuselage") & (Z > 1.8) & (Z < 4.7) & (Y > 0.10) & (Y < 0.85)
                                                                     & (np.abs(nrm[..., 0]) > 0.35))
dark_feature &= ~marks
metal = in_group("fuselage") & (Z < -3.30)
repaint = paintable & ~dark_feature & ~metal
print(f"repainted: {repaint.sum() / max(cover.sum(), 1) * 100:.0f} % of the used texture")

rng = np.random.default_rng(4)


def noise(sig, seed):
    f = max(int(sig / 3), 1)
    r = np.random.default_rng(seed).standard_normal((R // f, R // f)).astype(np.float32)
    r = cv2.GaussianBlur(r, (0, 0), sig / f)
    r = cv2.resize(r, (R, R), interpolation=cv2.INTER_CUBIC)
    return r / max(float(r.std()), 1e-6)


n_l, n_m = noise(R / 40, 1), noise(R / 400, 2)
tone = 1 + 0.07 * n_l + 0.035 * n_m
col = np.empty((R, R, 3), np.float32)
col[:] = BLACK

def edge_profile(mask, coord, val, lo, hi, step=0.02, fn=np.maximum):
    nb = int((hi - lo) / step) + 1
    init = -1e9 if fn is np.maximum else 1e9
    out = np.full(nb, init, np.float64)
    b = np.clip(((coord[mask] - lo) / step).astype(int), 0, nb - 1)
    fn.at(out, b, val[mask])
    ok = np.abs(out) < 1e8
    xs = np.arange(nb)
    out = np.interp(xs, xs[ok], out[ok]) if ok.sum() > 2 else np.zeros(nb)
    out = cv2.blur(out.reshape(1, -1).astype(np.float32), (9, 1)).ravel()
    return lambda c: out[np.clip(((c - lo) / step).astype(int), 0, nb - 1)]


grey_m = np.zeros((R, R), np.float32)
pale_m = np.zeros((R, R), np.float32)
wing = in_group("wing_")
le_w = edge_profile(wing, AX, Z, 1.2, 5.2)
te_w = edge_profile(wing, AX, Z, 1.2, 5.2, fn=np.minimum)
grey_m[wing & (Z > le_w(AX) - (0.11 + 0.02 * (5.2 - AX)))] = 1
pale_m[wing & (Z < te_w(AX) + 0.045) & (AX > 1.35)] = 1
can = in_group("canard_")
le_c = edge_profile(can, AX, Z, 0.5, 1.9)
grey_m[can & (Z > le_c(AX) - 0.06)] = 1
fin = in_group("fin", "rudder")
le_f = edge_profile(in_group("fin"), Y, Z, 0.66, 3.52)
grey_m[in_group("fin") & (Z > le_f(Y) - 0.12) & (Y > 0.95)] = 1
grey_m[fin & (Y > 3.22 + 0.10 * np.clip((Z + 5.25) / 1.3, 0, 1))] = 1
pod = in_group("pod_")
grey_m[pod & ((Z > -0.47) | (Z < -2.52))] = 1
radome = in_group("fuselage_nose") & (Z > 8.62)
form_m = np.zeros((R, R), np.float32)
form_m[in_group("fuselage") & (np.abs(nrm[..., 0]) > 0.5) & (Z > 5.03) & (Z < 6.03) & (np.abs(Y - 0.81) < 0.028)] = 1
form_m[in_group("fin") & (np.abs(Z - (le_f(Y) - 0.26)) < 0.026) & (Y > 1.45) & (Y < 2.35)] = 1
form_m[pod & (np.abs(nrm[..., 0]) > 0.6) & (np.abs(Y + 0.30) < 0.02) & (Z > -1.9) & (Z < -1.2)] = 1
dots = np.zeros((R, R), np.float32)
upper = wing & (nrm[..., 1] > 0.5)
dash = lambda t: ((t / 0.05) % 1.0) < 0.42
d_le = le_w(AX) - Z
d_te = Z - te_w(AX)
inside = (AX > 1.50) & (AX < 4.72) & (d_le > 0.40) & (d_te > 0.26)
dots[upper & (np.abs(d_le - 0.40) < 0.007) & dash(AX) & (AX > 1.50) & (AX < 4.72) & (d_te > 0.26)] = 1
dots[upper & (np.abs(d_te - 0.26) < 0.007) & dash(AX) & (AX > 1.50) & (AX < 4.72) & (d_le > 0.40)] = 1
dots[upper & (np.abs(AX - 1.50) < 0.007) & dash(Z) & (d_le > 0.40) & (d_te > 0.26)] = 1
dots[upper & (np.abs(AX - 4.72) < 0.007) & dash(Z) & (d_le > 0.40) & (d_te > 0.26)] = 1


def soft(m, s=0.7):
    return cv2.GaussianBlur(m, (0, 0), s)[..., None]


col = col * (1 - soft(pale_m)) + PALE * soft(pale_m)
col = col * (1 - soft(grey_m)) + GREY * soft(grey_m)
rm = soft(radome.astype(np.float32))
col = col * (1 - rm) + RADOME * rm
light = np.clip(soft(grey_m) + rm + soft(pale_m), 0, 1)[..., 0]
col = col * tone[..., None]
col = col + (0.055 * lines * (1 - light))[..., None] - (col * 0.38 * (lines * light)[..., None])
col = col * (1 - soft(form_m, 0.5)) + FORM * soft(form_m, 0.5)
col = col * (1 - soft(dots, 0.5)) + np.array([0.80, 0.82, 0.82], np.float32) * soft(dots, 0.5)

S = 4000.0
FONT = ckpanel.FONT


def text_img(s, h_m, colour, spacing=0.0):
    fpx = int(h_m * S / 0.729)
    f = ImageFont.truetype(FONT, fpx)
    w = int(f.getlength(s) + spacing * S * (len(s) - 1)) + 8
    im = Image.new("RGBA", (w, int(h_m * S * 1.25) + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 4
    for ch in s:
        d.text((x, im.height / 2), ch, fill=tuple(int(c * 255) for c in colour) + (255,), font=f, anchor="lm")
        x += f.getlength(ch) + spacing * S
    return im


def roundel_img(d_m):
    px = int(d_m * S)
    SS = 4
    im = Image.new("RGBA", (px * SS, px * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, px * SS - 1, px * SS - 1], fill=(22, 32, 92, 255))
    r = 0.2 * px * SS
    c = px * SS / 2
    d.ellipse([c - r, c - r, c + r, c + r], fill=(196, 30, 42, 255))
    return im.resize((px, px), Image.LANCZOS)


def bars_img(w_m, h_m, d_m):
    W, H = int(w_m * S), int(h_m * S)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    green, yellow = (28, 142, 62, 255), (236, 208, 34, 255)
    d.rectangle([0, 0, W, H], fill=green)
    d.rectangle([0, H * 0.34, W, H * 0.66], fill=yellow)
    rd = roundel_img(d_m)
    gap = int(d_m * S * 0.5 + 0.012 * S)
    d.rectangle([W / 2 - gap, 0, W / 2 + gap, H], fill=(0, 0, 0, 0))
    im.alpha_composite(rd, (W // 2 - rd.width // 2, H // 2 - rd.height // 2))
    return im


def flash_img(w_m, h_m, lean, red_right):
    W, H = int(w_m * S), int(h_m * S)
    SS = 3
    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    sl = 0.32 * W * SS
    bw = (W * SS - sl) / 2
    blue, red = (22, 32, 92, 255), (196, 30, 42, 255)
    for i, c in enumerate((blue, red) if red_right else (red, blue)):
        xb = i * bw + (0 if lean > 0 else sl)
        xt = xb + (sl if lean > 0 else -sl)
        d.polygon([(xb, H * SS), (xb + bw, H * SS), (xt + bw, 0), (xt, 0)], fill=c)
    return im.resize((W, H), Image.LANCZOS)


def bat_img(w_m):
    W = int(w_m * S)
    H = int(W * 0.56)
    SS = 3
    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    half = [(0.50, 0.30), (0.535, 0.12), (0.555, 0.30), (0.62, 0.26), (0.74, 0.10), (0.86, 0.04), (0.985, 0.20), (0.90, 0.30),
            (0.93, 0.52), (0.84, 0.44), (0.80, 0.70), (0.71, 0.56), (0.64, 0.84), (0.57, 0.66), (0.50, 0.92)]
    pts = half + [(1 - x, y) for x, y in reversed(half[1:-1])]
    P_ = [(x * W * SS, y * H * SS) for x, y in pts]
    d.polygon(P_, fill=(34, 150, 66, 255), outline=(222, 214, 84, 255))
    d.line(P_ + [P_[0]], fill=(222, 214, 84, 255), width=max(int(0.006 * S * SS), 2), joint="curve")
    return im.resize((W, H), Image.LANCZOS)


def project(img, O, U, Vv, D, groups, depth=0.6, facing=0.25):
    global col
    O, U, Vv, D = (np.asarray(a, np.float32) for a in (O, U, Vv, D))
    a = np.asarray(img).astype(np.float32) / 255
    h, w = a.shape[:2]
    q = pos - O
    u, v, dd = q @ U, q @ Vv, q @ D
    m = in_group(*groups) & (np.abs(u) < w / S / 2) & (np.abs(v) < h / S / 2) & (np.abs(dd) < depth) & ((nrm @ D) > facing)
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        print("   marking fell off the model:", O)
        return 0
    fx = np.clip((u[m] * S + w / 2 - 0.5), 0, w - 1.001)
    fy = np.clip((h / 2 - v[m] * S - 0.5), 0, h - 1.001)
    x0, y0 = fx.astype(int), fy.astype(int)
    tx, ty = (fx - x0)[:, None], (fy - y0)[:, None]
    smp = (a[y0, x0] * (1 - tx) * (1 - ty) + a[y0, x0 + 1] * tx * (1 - ty) + a[y0 + 1, x0] * (1 - tx) * ty + a[y0 + 1, x0 + 1] * tx * ty)
    al = smp[:, 3:4]
    col[ys, xs] = col[ys, xs] * (1 - al) + smp[:, :3] * al
    return len(ys)


WHITE, RED = (0.88, 0.89, 0.88), (0.80, 0.11, 0.13)
FUS = ("fuselage",)
for sx in (1, -1):
    U = (0, 0, sx)
    D = (sx, 0, 0)
    Vup = (0, 1, 0)
    n1 = project(bars_img(1.36, 0.26, 0.30), (sx * 0.9, 0.40, 3.62), U, Vup, D, FUS, facing=0.45)
    n2 = project(text_img("ZJ914", 0.15, WHITE, 0.014), (sx * 0.9, 0.20, -2.15), U, Vup, D, FUS + ("nozzle_",), facing=0.55)
    n3 = project(text_img("914", 0.21, WHITE, 0.01), (0, 2.72, -3.92), U, Vup, D, ("fin", "rudder"))
    n4 = project(bat_img(0.66), (0, 1.97, -3.20), U, Vup, D, ("fin",))
    n5 = project(flash_img(0.44, 0.33, -sx, sx > 0), (0, 1.24, -3.08), U, Vup, D, ("fin",))
    n6 = project(text_img("WS-T", 0.26, RED, 0.02), (0, 1.24, -2.32), U, Vup, D, ("fin",))
    print(f"side {sx:+d}: texels  bars {n1}, serial {n2}, 914 {n3}, bat {n4}, flash {n5}, code {n6}")
rd = roundel_img(0.37)
print("wing roundels:", project(rd, (-3.96, 0.5, -0.32), (1, 0, 0), (0, 0, 1), (0, 1, 0), ("wing_",), depth=1.5, facing=0.5),
      project(rd, (3.96, -1.0, -0.32), (1, 0, 0), (0, 0, -1), (0, -1, 0), ("wing_",), depth=1.5, facing=0.5))

base = np.where(repaint[..., None], col, old)
both = np.zeros((R, R), bool)
Image.fromarray((np.clip(base, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(OUT, "airframe_base.png"), optimize=True)
print("airframe_base.png written")
