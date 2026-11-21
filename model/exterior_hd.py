import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ckpaint as cp
import ckpanel
import ckskin
import exlines

Image.MAX_IMAGE_PIXELS = None
ST, SRC = sys.argv[1], sys.argv[2]
SCALE = float(os.environ.get("EXT_SCALE", "1"))
ATLASES = [("exfus", ("fuselage", "airbrake", "geardoors", "bay_door_", "gear_main_door", "gear_nose_door"), 8192, 4096),
           ("exwing", ("wing_", "flaperon_", "canard_", "pod_"), 8192, 4096),
           ("exfin", ("fin", "rudder"), 4096, 2048),
           ("exmisc", ("nozzle_", "petals_", "pylon_"), 4096, 2048)]
ONLY = os.environ.get("EXT_ONLY")

BLACK = np.array([0.098, 0.102, 0.110], np.float32)
GREY = np.array([0.47, 0.49, 0.51], np.float32)
RADOME = np.array([0.49, 0.505, 0.52], np.float32)
PALE = np.array([0.50, 0.545, 0.59], np.float32)
WHITE, RED, YELLOW = (0.88, 0.89, 0.88), (0.80, 0.11, 0.13), (0.93, 0.80, 0.12)

lines_in = open(os.path.join(ST, "typhoon.obj")).read().split("\n")
V, VT = [], []
objs = []
cur, mtl = None, "body"
for li, line in enumerate(lines_in):
    if line.startswith("v "):
        V.append([float(x) for x in line.split()[1:4]])
    elif line.startswith("vt "):
        VT.append([float(x) for x in line.split()[1:3]])
    elif line.startswith("o ") or line.startswith("g "):
        cur = dict(name=line.split()[1], mtl=mtl, faces=[])
        objs.append(cur)
    elif line.startswith("usemtl"):
        mtl = line.split()[1]
        if cur is not None:
            cur["mtl"] = mtl
    elif line.startswith("f ") and cur is not None:
        cur["faces"].append((li, [tuple(int(a) - 1 if a else -1 for a in (c.split("/") + ["", ""])[:3]) for c in line.split()[1:]]))
V, VT = np.array(V), np.array(VT)
assert not any(o["mtl"].startswith("ex") for o in objs), "this typhoon.obj already has the new exterior UVs"


def members(prefixes):
    return [o for o in objs if o["mtl"] == "airframe" and any(o["name"].startswith(p) for p in prefixes) and o["faces"]]


def unwrap(faces):
    import bpy
    used = sorted({v for f in faces for v in f})
    rm = {v: i for i, v in enumerate(used)}
    ok = [len(set(f)) == len(f) and len(f) >= 3 for f in faces]
    me = bpy.data.meshes.new("u")
    me.from_pydata([tuple(V[v]) for v in used], [], [[rm[v] for v in f] for f, k in zip(faces, ok) if k])
    me.update()
    ob = bpy.data.objects.new("u", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    me.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(float(os.environ.get("EXT_ANGLE", "66"))), island_margin=0.0)
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    kw = eval(os.environ.get("EXT_PACK", "dict(margin=0.003, rotate=True)"))
    bpy.ops.uv.pack_islands(**kw)
    bpy.ops.object.mode_set(mode='OBJECT')
    uv = np.array([l.uv[:] for l in me.uv_layers.active.data], np.float64)
    ar, k0 = 0.0, 0
    for p_ in me.polygons:
        q = uv[p_.loop_start:p_.loop_start + p_.loop_total]
        ar += 0.5 * abs(sum(q[i][0] * q[(i + 1) % len(q)][1] - q[(i + 1) % len(q)][0] * q[i][1] for i in range(len(q))))
    print("   unwrap: %d faces, UV area used %.0f %%" % (len(me.polygons), ar * 100))
    out, k = [], 0
    for f, good in zip(faces, ok):
        if good:
            out.append(uv[k:k + len(f)])
            k += len(f)
        else:
            out.append(np.zeros((len(f), 2)))
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return out


S = 4000.0
FONT = ckpanel.FONT
_LIB = "/usr/share/fonts/truetype/liberation/"
REG = _LIB + "LiberationSans-Regular.ttf" if os.path.exists(_LIB + "LiberationSans-Regular.ttf") else FONT
BOLD = _LIB + "LiberationSans-Bold.ttf" if os.path.exists(_LIB + "LiberationSans-Bold.ttf") else FONT
INK = (12, 12, 12, 255)


def _rgba(c, a=255):
    return tuple(int(v * 255) for v in c) + (a,)


def text_img(s, h_m, colour, spacing=0.0, box=None, pad=0.0, font=None, fill=None, lead=1.42):
    f = ImageFont.truetype(font or BOLD, max(int(h_m * S / 0.716), 6))
    rows = s.split("|")
    wt = max(int(f.getlength(r) + spacing * S * (len(r) - 1)) for r in rows)
    lh = h_m * S * lead
    p = int(pad * S) + 4
    im = Image.new("RGBA", (wt + 2 * p, int(lh * len(rows)) + 2 * p), _rgba(fill) if fill is not None else (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if box is not None:
        d.rectangle([1, 1, im.width - 2, im.height - 2], outline=_rgba(box), width=max(int(0.0035 * S), 2))
    for i, r in enumerate(rows):
        w = f.getlength(r) + spacing * S * (len(r) - 1)
        x = im.width / 2 - w / 2
        for ch in r:
            d.text((x, p + lh * (i + 0.5)), ch, fill=_rgba(colour), font=f, anchor="lm")
            x += f.getlength(ch) + spacing * S
    return im


def _ss(w, h, k=3):
    return Image.new("RGBA", (int(w * S) * k, int(h * S) * k), (0, 0, 0, 0)), k


def _down(im, k):
    return im.resize((im.width // k, im.height // k), Image.LANCZOS)


ROUNDEL_BLUE, ROUNDEL_RED = (34, 50, 122, 255), (198, 32, 44, 255)


def roundel_img(d_m):
    im, k = _ss(d_m, d_m, 4)
    d = ImageDraw.Draw(im)
    n = im.width
    d.ellipse([0, 0, n - 1, n - 1], fill=ROUNDEL_BLUE)
    r, c = 0.205 * n, n / 2
    d.ellipse([c - r, c - r, c + r, c + r], fill=ROUNDEL_RED)
    return _down(im, k)


def bars_img(w_m, h_m, d_m):
    hh = max(h_m, d_m)
    W, H = int(w_m * S), int(hh * S)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y0, y1 = H / 2 - h_m * S / 2, H / 2 + h_m * S / 2
    gap = d_m * S * 0.5 + 0.018 * S
    for x0, x1 in ((0, W / 2 - gap), (W / 2 + gap, W)):
        d.rectangle([x0, y0, x1, y1], fill=(30, 138, 62, 255))
        d.rectangle([x0, y0 + (y1 - y0) * 0.36, x1, y0 + (y1 - y0) * 0.64], fill=(232, 204, 36, 255))
    rd = roundel_img(d_m)
    im.alpha_composite(rd, (W // 2 - rd.width // 2, H // 2 - rd.height // 2))
    return im


def flash_img(w_m, h_m, lean, red_right):
    im, k = _ss(w_m, h_m)
    W, H = im.size
    d = ImageDraw.Draw(im)
    sl = 0.32 * W
    bw = (W - sl) / 2
    for i, c in enumerate((ROUNDEL_BLUE, ROUNDEL_RED) if red_right else (ROUNDEL_RED, ROUNDEL_BLUE)):
        xb = i * bw + (0 if lean > 0 else sl)
        xt = xb + (sl if lean > 0 else -sl)
        d.polygon([(xb, H), (xb + bw, H), (xt + bw, 0), (xt, 0)], fill=c)
    return _down(im, k)


def bat_img(w_m):
    im, k = _ss(w_m, w_m * 0.56)
    W, H = im.size
    d = ImageDraw.Draw(im)
    half = [(0.50, 0.30), (0.535, 0.12), (0.555, 0.30), (0.62, 0.26), (0.74, 0.10), (0.86, 0.04), (0.985, 0.20), (0.90, 0.30),
            (0.93, 0.52), (0.84, 0.44), (0.80, 0.70), (0.71, 0.56), (0.64, 0.84), (0.57, 0.66), (0.50, 0.92)]
    pts = half + [(1 - x, y) for x, y in reversed(half[1:-1])]
    P_ = [(x * W, y * H) for x, y in pts]
    d.polygon(P_, fill=(34, 150, 66, 255))
    d.line(P_ + [P_[0]], fill=(222, 214, 84, 255), width=max(int(0.007 * S * k), 2), joint="curve")
    return _down(im, k)


def formstrip_img(L_m, h_m, n):
    im, k = _ss(L_m, h_m)
    W, H = im.size
    d = ImageDraw.Draw(im)
    fr = int(0.009 * S * k)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=int(0.008 * S * k), fill=(74, 77, 78, 255))
    d.rounded_rectangle([fr * 0.45, fr * 0.45, W - 1 - fr * 0.45, H - 1 - fr * 0.45], radius=int(0.006 * S * k), outline=(104, 108, 108, 255), width=max(int(0.0015 * S * k), 1))
    gw = int(0.006 * S * k)
    seg = (W - 2 * fr - (n - 1) * gw) / n
    for i in range(n):
        x0 = fr + i * (seg + gw)
        d.rectangle([x0, fr, x0 + seg, H - 1 - fr], fill=(150, 156, 88, 255))
        d.rectangle([x0 + 0.004 * S * k, fr + 0.004 * S * k, x0 + seg - 0.004 * S * k, H - 1 - fr - 0.004 * S * k], fill=(164, 170, 98, 255))
    for i in range(n + 1):
        x = fr * 0.5 + i * (W - fr) / n
        for y in (fr * 0.5, H - 1 - fr * 0.5):
            r = 0.0022 * S * k
            d.ellipse([x - r, y - r, x + r, y + r], fill=(40, 42, 42, 255))
    return _down(im, k)


def rescue_arrow_img():
    w, h = 0.25, 0.082
    im, k = _ss(w, h)
    W, H = im.size
    d = ImageDraw.Draw(im)
    hd = 0.20 * W
    pts = [(2, H / 2), (hd, 2), (hd, H * 0.14), (W - 3, H * 0.14), (W - 3, H * 0.86), (hd, H * 0.86), (hd, H - 3)]
    d.polygon(pts, fill=(238, 200, 30, 255))
    d.line(pts + [pts[0]], fill=INK, width=int(0.0035 * S * k), joint="curve")
    f = ImageFont.truetype(BOLD, int(0.036 * S * k / 0.716))
    d.text((hd + (W - hd) * 0.5, H * 0.5), "RESCUE", fill=INK, font=f, anchor="mm")
    return _down(im, k)


def rescue_box_img():
    w, h = 0.20, 0.085
    im, k = _ss(w, h)
    W, H = im.size
    d = ImageDraw.Draw(im)
    d.rectangle([2, 2, W - 3, H - 3], outline=(238, 200, 30, 255), width=int(0.004 * S * k))
    f = ImageFont.truetype(BOLD, int(0.030 * S * k / 0.716))
    d.text((W * 0.5, H * 0.36), "RESCUE", fill=(238, 200, 30, 255), font=f, anchor="mm")
    f2 = ImageFont.truetype(BOLD, int(0.0105 * S * k / 0.716))
    d.text((W * 0.5, H * 0.74), "HANDLE ON OTHER SIDE", fill=(238, 200, 30, 255), font=f2, anchor="mm")
    return _down(im, k)


def handle_marker_img(d_m):
    im, k = _ss(d_m, d_m, 4)
    n = im.width
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, n - 1, n - 1], fill=(238, 200, 30, 255))
    for i in range(0, 8, 2):
        d.pieslice([n * 0.07, n * 0.07, n * 0.93, n * 0.93], i * 45 + 22.5, (i + 1) * 45 + 22.5, fill=INK)
    r = n * 0.20
    d.ellipse([n / 2 - r, n / 2 - r, n / 2 + r, n / 2 + r], fill=(120, 122, 120, 255), outline=INK, width=int(n * 0.03))
    return _down(im, k)


def triangle_img(w_m):
    im, k = _ss(w_m, w_m * 0.87)
    W, H = im.size
    d = ImageDraw.Draw(im)
    d.polygon([(0, 0), (W, 0), (W / 2, H)], fill=(226, 226, 220, 255))
    m = W * 0.10
    d.polygon([(m * 1.7, m), (W - m * 1.7, m), (W / 2, H - m * 2)], fill=(196, 30, 42, 255))
    f = ImageFont.truetype(BOLD, int(W * 0.10))
    d.text((W / 2, H * 0.26), "DANGER", fill=(236, 236, 230, 255), font=f, anchor="mm")
    return _down(im, k)


def patch_img(w_m, h_m, colour):
    return Image.new("RGBA", (int(w_m * S), int(h_m * S)), _rgba(colour))


def ring_img(d_m, colour, wd=0.006):
    im, k = _ss(d_m, d_m, 4)
    n = im.width
    ImageDraw.Draw(im).ellipse([wd * S * k / 2, wd * S * k / 2, n - 1 - wd * S * k / 2, n - 1 - wd * S * k / 2], outline=_rgba(colour), width=int(wd * S * k))
    return _down(im, k)


def earth_img(h_m, colour):
    im, k = _ss(h_m, h_m)
    n = im.width
    d = ImageDraw.Draw(im)
    w = max(int(n * 0.07), 2)
    d.line([(n / 2, n * 0.08), (n / 2, n * 0.5)], fill=_rgba(colour), width=w)
    for i, half in enumerate((0.40, 0.26, 0.12)):
        y = n * (0.5 + i * 0.17)
        d.line([(n / 2 - n * half, y), (n / 2 + n * half, y)], fill=_rgba(colour), width=w)
    return _down(im, k)


src = np.asarray(Image.open(os.path.join(SRC, "airframe_src_base.png")).convert("RGB"))
sf = src.astype(np.float32) / 255
s_lum = sf.mean(2)
D_old = cv2.GaussianBlur((s_lum < 0.25).astype(np.float32), (0, 0), 0.8)
del sf
EXL = exlines.build(os.path.join(SRC, "airframe_src_base.png"), cache=os.environ.get("EXT_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "typhoon_exlines")))
SRC_DENS = 118.0


def paint(name, P, UVn, UVo, tg, names, R, RN):
    import gc
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    A = np.concatenate([np.repeat(n[:, None, :], 3, axis=1), UVo], axis=2)
    tid, pos, att = ckskin.raster_attr(UVn, P, A, R, R)
    cover = tid >= 0
    grp = np.where(cover, tg[np.maximum(tid, 0)], -1).astype(np.int16)
    del tid
    nrm = att[..., :3].astype(np.float16)
    mx = (att[..., 3] * src.shape[1] - 0.5).astype(np.float32)
    my = ((1 - att[..., 4]) * src.shape[0] - 0.5).astype(np.float32)
    del att
    oldc = cv2.remap(src, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    Dk = cv2.remap(D_old, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE) > 0.5
    dens = math.sqrt(cover.sum() / max(np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1).sum() / 2, 1e-9))
    print(f"{name}: {len(P)} triangles, {cover.mean() * 100:.0f} % of {R} px used, {dens:.0f} texels per metre")

    Kx = EXL["K"]
    mxk, myk = (mx + 0.5) * Kx - 0.5, (my + 0.5) * Kx - 0.5
    sig = float(os.environ.get("EX_LINE_SOFT", "0.30")) * SRC_DENS * Kx / dens
    ln = np.load(EXL["lines"])
    if sig > 0.5:
        ln = cv2.GaussianBlur(ln, (0, 0), sig)
    ln = cv2.remap(ln, mxk, myk, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    rv = np.load(EXL["rivets"])
    if sig > 0.5:
        rv = cv2.GaussianBlur(rv, (0, 0), sig)
    rv = cv2.remap(rv, mxk, myk, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    del mxk, myk
    Kp = EXL["KP"]
    lab = cv2.remap(np.load(EXL["panels"]), (mx + 0.5) * Kp - 0.5, (my + 0.5) * Kp - 0.5, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT)
    del mx, my
    gc.collect()
    gain = 1.0 + 0.9 * min(max(sig, 0.0), 1.2)
    ln = np.clip(ln.astype(np.float32) * (gain / 255.0), 0, 1)
    LINE_SHARP = float(os.environ.get("EX_LINE_SHARP", "1.6"))
    if LINE_SHARP != 1.0:
        ln = np.clip(ln * 1.15, 0, 1) ** LINE_SHARP
    rv8 = np.clip(rv.astype(np.float32) * gain, 0, 255).astype(np.uint8)
    del rv

    X, Y, Z = pos[..., 0], pos[..., 1], pos[..., 2]
    NX, NY = nrm[..., 0], nrm[..., 1]

    def G(*pre):
        ids = [i for i, nm in enumerate(names) if any(nm.startswith(p) for p in pre)]
        return np.isin(grp, ids) & cover

    if not os.environ.get("NO_DOOR_LINES"):
        _dm = G("geardoors", "gear_main_door", "gear_nose_door")
        if _dm.any():
            _dt = cv2.distanceTransform(_dm.astype(np.uint8), cv2.DIST_L2, 5)
            ln = np.maximum(ln, (np.exp(-((_dt - 0.014 * dens) / 0.8) ** 2) * _dm * 0.85).astype(np.float32))
            _sp = max(int(round(0.034 * dens)), 6)
            _ys, _xs = np.nonzero(_dm & (np.abs(_dt - 0.030 * dens) < 1.0))
            _sel = ((_xs % _sp) < 2) | ((_ys % _sp) < 2)
            rv8[_ys[_sel], _xs[_sel]] = 255
            print("   gear doors: edge seam and %d fastener texels" % int(_sel.sum()))
            del _dt, _ys, _xs, _sel
        del _dm

    def soft(m, s=0.8):
        return cv2.GaussianBlur(m.astype(np.float32), (0, 0), s)

    def noise2(shape, sig_, seed):
        r = np.random.default_rng(seed).standard_normal(shape).astype(np.float32)
        r = cv2.GaussianBlur(r, (0, 0), sig_)
        return r / max(float(r.std()), 1e-6)
    nz = noise2((1024, 1024), 6.0, 5)

    def nz_at(a, b):
        a = (np.asarray(a, np.float32) % 1.0 * 1023).astype(np.float32)
        b = (np.asarray(b, np.float32) % 1.0 * 1023).astype(np.float32)
        if a.ndim == 2:
            return cv2.remap(nz, a, b, cv2.INTER_LINEAR)
        n_ = len(a)
        w_ = 4096
        pad = (-n_) % w_
        a2 = np.concatenate([a, np.zeros(pad, np.float32)]).reshape(-1, w_)
        b2 = np.concatenate([b, np.zeros(pad, np.float32)]).reshape(-1, w_)
        return cv2.remap(nz, a2, b2, cv2.INTER_LINEAR).ravel()[:n_]

    def streak_at(x, y, z):
        return nz_at(x * 0.31 + y * 0.17, z * 0.021 + x * 0.05)

    def drift_at(x, y, z):
        return nz_at(x * 0.045 + 0.3, z * 0.041 + y * 0.06)

    marks = G("wing_", "canard_", "fin", "rudder", "flaperon_", "pod_", "pylon_") | (G("fuselage") & (Z > 2.6) & (Z < 4.9) & (Y > 0.08) & (Y < 0.62) & (np.abs(NX) > 0.35))
    marks |= G("fuselage") & (np.abs(X) < 0.20) & (Z > -1.95) & (Z < -1.45) & (Y > 0.58)
    keep = cover & Dk & ~marks
    del Dk, marks
    if name == "exmisc":
        keep &= ~G("petals_")
    ln *= ~keep
    rv8[keep] = 0

    nl = int(lab.max()) + 1
    lc = lab[cover]
    cnt_l = np.maximum(np.bincount(lc, minlength=nl), 1)
    cx, cy, cz = (np.bincount(lc, weights=a[cover], minlength=nl) / cnt_l for a in (X, Y, Z))
    del lc
    field = (0.50 * np.sin(1.9 * cx + 0.4) + 0.45 * np.sin(2.6 * cz + 1.2) + 0.40 * np.sin(3.3 * cy + 2.1) + 0.35 * np.sin(1.4 * cx + 3.1 * cz) + 0.30 * np.sin(4.7 * cz - 2.2 * cy)) / 1.2
    lut = (0.020 * field + np.clip(np.random.default_rng(11).normal(0, 0.007, nl), -0.016, 0.016)).astype(np.float32)
    lut[0] = 0
    tone = 1 + lut[lab]
    rz_idx = np.nonzero(G("wing_", "fuselage_root_") & (np.abs(NY) > 0.55) & (np.abs(X) < 1.80))
    if len(rz_idx[0]):
        w_ = np.clip((1.80 - np.abs(X[rz_idx]).astype(np.float32)) / 0.20, 0, 1)
        ln[rz_idx] *= 1 - w_
        rv8[rz_idx] = (rv8[rz_idx].astype(np.float32) * (1 - w_)).astype(np.uint8)
        tone[rz_idx] = 1 + (tone[rz_idx] - 1) * (1 - w_)
        print("   wing roots: source lines and panel tones cleared on %d texels" % len(rz_idx[0]))
        del w_
    del rz_idx
    del lab, cx, cy, cz
    gc.collect()

    col = np.empty((R, R, 3), np.float32)
    col[:] = BLACK
    smooth = np.full((R, R), 0.44, np.float32)
    metal8 = np.zeros((R, R), np.uint8)

    def edge_profile(mask, coord, val, lo, hi, step=0.02, fn=np.maximum):
        nb = int((hi - lo) / step) + 1
        out = np.full(nb, -1e9 if fn is np.maximum else 1e9, np.float64)
        b = np.clip(((coord[mask] - lo) / step).astype(int), 0, nb - 1)
        fn.at(out, b, val[mask])
        okb = np.abs(out) < 1e8
        xs = np.arange(nb)
        out = np.interp(xs, xs[okb], out[okb]) if okb.sum() > 2 else np.zeros(nb)
        out = cv2.blur(out.reshape(1, -1).astype(np.float32), (9, 1)).ravel()
        cen = lo + (np.arange(nb) + 0.5) * step
        return lambda c: np.interp(c, cen, out).astype(np.float32)

    grey_m = np.zeros((R, R), bool)
    pale_m = np.zeros((R, R), bool)
    dots = np.zeros((R, R), bool)
    radome = np.zeros((R, R), bool)
    strip_m = np.zeros((R, R), bool)
    tip_m = np.zeros((R, R), bool)
    ti_idx, ti_rgb = None, None
    AXIS_X, AXIS_Y = 0.4855, -0.0392

    def pipe_frame(x_, y_, nx_, ny_):
        rxx = x_ - np.where(x_ > 0, AXIS_X, -AXIS_X).astype(np.float32)
        ryy = y_ - AXIS_Y
        rr = np.maximum(np.hypot(rxx, ryy), 1e-4)
        return rr, (nx_.astype(np.float32) * rxx + ny_.astype(np.float32) * ryy) / rr

    if name == "exwing":
        AX = np.abs(X)
        wing = G("wing_")
        le_w, te_w = edge_profile(wing, AX, Z, 1.2, 5.2), edge_profile(wing, AX, Z, 1.2, 5.2, fn=np.minimum)
        xs1 = np.linspace(1.2, 5.2, 401)
        slope = np.gradient(le_w(xs1), xs1)
        d_le = le_w(AX)
        d_le -= Z
        m_ = wing & (d_le < 0.11 + 0.02 * (5.2 - AX))
        del d_le
        m_ &= np.interp(AX, xs1, slope) < -0.30
        pale_m |= m_
        del m_
        d_te = Z - te_w(AX)
        pale_m |= wing & (d_te < 0.045) & (AX > 1.35) & (Z < -1.0)
        can = G("canard_")
        le_c = edge_profile(can, AX, Z, 0.5, 1.9)
        pale_m |= can & (Z > le_c(AX) - 0.045)
        pod = G("pod_")
        grey_m |= pod & ((Z > -0.47) | (Z < -2.52))
        del can, pod
        upper = wing & (NY > 0.5)
        del wing
        dash = lambda t: ((t / 0.08) % 1.0) < 0.55
        wd = 0.009
        xs_ = np.linspace(2.3, 4.6, 24)
        b_le, a_le = np.polyfit(xs_, le_w(xs_), 1)
        d_lt = (a_le + b_le * AX).astype(np.float32)
        d_lt -= Z
        xt_ = np.linspace(2.0, 4.6, 24)
        b_te, a_te = np.polyfit(xt_, te_w(xt_), 1)
        d_te = (Z - (a_te + b_te * AX)).astype(np.float32)
        X_IN = 1.78
        inx = upper & (AX > X_IN) & (AX < 4.72)
        dots |= inx & (np.abs(d_lt - 0.40) < wd) & dash(AX) & (d_te > 0.26)
        dots |= inx & (np.abs(d_te - 0.26) < wd) & dash(AX) & (d_lt > 0.40)
        del inx
        box_ = upper & (d_lt > 0.40) & (d_te > 0.26)
        del d_lt, d_te, upper
        dots |= box_ & (np.abs(AX - X_IN) < wd) & dash(Z)
        dots |= box_ & (np.abs(AX - 4.72) < wd) & dash(Z)
        del box_, AX
        gc.collect()

    elif name == "exfin":
        fin = G("fin")
        le_f = edge_profile(fin, Y, Z, 0.66, 3.52)
        pale_m |= fin & (Z > le_f(Y) - 0.10) & (Y > 0.95)
        grey_m |= cover & (Y > 3.22 + 0.10 * np.clip((Z + 5.25) / 1.3, 0, 1))
        rud = G("rudder")
        le_r = edge_profile(rud, Y, Z, 0.85, 3.0)
        pale_m |= rud & (Z > le_r(Y) - 0.014) & (Y > 0.95) & (Y < 2.95)
    elif name == "exfus":
        nose = G("fuselage_nose")
        radome |= nose & (Z > 8.675)
        keep &= ~radome
        ln *= ~radome
        rv8[radome] = 0
        ri = np.nonzero(radome)
        xr, yr, zr = X[ri], Y[ri], Z[ri]
        zb = np.linspace(8.675, 10.73, 42)
        bi = np.clip(np.digitize(zr, zb) - 1, 0, len(zb) - 2)
        ymx = np.full(len(zb) - 1, -9.0)
        ymn = np.full(len(zb) - 1, 9.0)
        np.maximum.at(ymx, bi, yr)
        np.minimum.at(ymn, bi, yr)
        okb = ymx > ymn
        ryv = yr - np.interp(zr, ((zb[:-1] + zb[1:]) / 2)[okb], ((ymx + ymn) / 2)[okb]).astype(np.float32)
        az = np.degrees(np.arctan2(xr, ryv))
        radv = np.hypot(xr, ryv)
        sm_ = np.zeros(len(zr), bool)
        for a0, z0, z1 in ((90, 9.20, 10.20), (-90, 9.20, 10.20), (0, 8.92, 9.70), (180, 8.92, 9.70), (45, 8.92, 9.45), (-45, 8.92, 9.45)):
            da = np.abs((az - a0 + 180) % 360 - 180)
            sm_ |= (np.radians(da) * radv < 0.0022) & (zr > z0) & (zr < z1)
        strip_m[ri] = sm_
        tip_m[ri] = zr > 10.675
        del ri, xr, yr, zr, ryv, az, radv, sm_, bi
        ln = np.maximum(ln, soft(nose & (np.abs(Z - 8.675) < 0.003), 0.7))
        del nose
        ti = np.nonzero(G("fuselage") & (Z < -3.335))
        x_, y_, z_ = X[ti], Y[ti], Z[ti]
        rr, outward = pipe_frame(x_, y_, NX[ti], NY[ti])
        sel = (outward > 0.55) & (rr > 0.38) & (rr < 0.70)
        ti_idx = (ti[0][sel], ti[1][sel])
        x_, y_, z_ = x_[sel], y_[sel], z_[sel]
        h_ = np.clip((-3.335 - z_) / 0.27, 0, 1)
        base_t = 0.44 * (1 + 0.09 * streak_at(x_, y_, z_) + 0.05 * drift_at(x_, y_, z_))
        ti_rgb = np.stack([base_t * (1.00 + 0.06 * h_), base_t * (0.985 + 0.01 * h_), base_t * (0.95 - 0.10 * h_ + 0.16 * h_ * h_)], 1).astype(np.float32)
        del ti, x_, y_, z_, rr, outward, sel, h_, base_t
    elif name == "exmisc":
        o_l = oldc.astype(np.float32).mean(2) / 255
        painted = ((oldc[..., 2].astype(np.float32) - oldc[..., 0]) > 0.028 * 255) & (o_l > 0.33)
        painted = cv2.GaussianBlur(painted.astype(np.float32), (0, 0), 1.2) > 0.5
        pet_m = G("petals_")
        ti = np.nonzero(G("nozzle_", "petals_") & ~painted & ~keep)
        x_, y_, z_ = X[ti], Y[ti], Z[ti]
        rr, outward = pipe_frame(x_, y_, NX[ti], NY[ti])
        pet = pet_m[ti].astype(np.float32)
        sl = np.clip((o_l[ti] - 0.25) / 0.50, 0, 1)
        hot = np.clip((-3.55 - z_) / 0.62, 0, 1)
        ring_c = np.array([0.43, 0.42, 0.40], np.float32)
        out_c = np.array([0.215, 0.225, 0.245], np.float32)
        in_c = np.array([0.175, 0.160, 0.145], np.float32)
        w_in = np.clip(0.5 - outward * 2.5, 0, 1) * pet
        w_out = pet - w_in
        w_ring = 1 - w_in - w_out
        ti_rgb = (w_ring[:, None] * ring_c * (0.62 + 0.62 * sl)[:, None] + w_out[:, None] * out_c * (0.70 + 0.55 * sl)[:, None]
                  + w_in[:, None] * in_c * (0.80 + 0.40 * sl)[:, None]).astype(np.float32)
        ring_heat = w_ring * np.clip((-3.42 - z_) / 0.40, 0, 1)
        ti_rgb[:, 0] *= 1 + 0.10 * ring_heat * (1 - hot)
        ti_rgb[:, 2] *= 1 - 0.16 * ring_heat * (1 - hot) + 0.22 * ring_heat * hot
        ti_rgb *= (1 + 0.10 * streak_at(x_, y_, z_))[:, None]
        ti_idx = ti
        del o_l, painted, pet_m, ti, x_, y_, z_, rr, outward, pet, sl, hot, w_in, w_out, w_ring, ring_heat
    gc.collect()

    def lay(m, c, sm=None, s=0.8):
        a = soft(m, s)
        ia = 1 - a
        for c_ in range(3):
            ch = col[..., c_]
            ch *= ia
            ch += float(c[c_]) * a
        if sm is not None:
            smooth[...] = smooth * ia + sm * a
        return a
    light = lay(pale_m, PALE, 0.36)
    light += lay(grey_m, GREY, 0.34)
    rad_a = lay(radome, RADOME, 0.24)
    light += rad_a
    np.clip(light, 0, 1, out=light)
    del pale_m, grey_m, radome
    tone -= 1
    tone *= 1 - rad_a
    tone += 1
    st = streak_at(X, Y, Z)
    st *= 0.040 * (1 - 0.6 * rad_a)
    st += 1
    tone *= st
    st = drift_at(X, Y, Z)
    st *= 0.045 * (1 - 0.7 * rad_a)
    st += 1
    tone *= st
    del st, rad_a
    col *= tone[..., None]
    del tone
    gc.collect()
    col += (0.034 * ln * (1 - light))[..., None]
    col *= (1 - 0.40 * ln * light)[..., None]
    smooth -= 0.14 * ln
    rvf = rv8.astype(np.float32) / 255
    col += (0.020 * rvf * (1 - light))[..., None]
    col *= (1 - 0.16 * rvf * light)[..., None]
    smooth -= 0.05 * rvf
    del rvf, light
    lay(dots, (0.80, 0.82, 0.82), 0.40, 0.6)
    lay(strip_m, (0.36, 0.37, 0.38), 0.45, 0.6)
    lay(tip_m, (0.66, 0.60, 0.44), 0.40, 0.8)
    del dots, strip_m, tip_m
    if ti_idx is not None and len(ti_idx[0]):
        l_ = ln[ti_idx]
        col[ti_idx] = ti_rgb * ((1 - 0.45 * l_) * (1 - 0.18 * rv8[ti_idx].astype(np.float32) / 255))[:, None]
        smooth[ti_idx] = 0.56 - 0.10 * l_
        metal8[ti_idx] = 255
        if name == "exfus":
            tm = np.zeros((R, R), np.uint8)
            tm[ti_idx] = 1
            edge = soft(G("fuselage") & (np.abs(Z + 3.335) < 0.004) & (cv2.dilate(tm, np.ones((9, 9), np.uint8)) > 0), 0.6)
            col *= (1 - 0.5 * edge)[..., None]
            del tm, edge
        del l_, ti_rgb
    gc.collect()

    def project(img, O, U, Vv, D, groups, depth=0.6, facing=0.25, sm=0.40, flat=False):
        O, U, Vv, D = (np.asarray(a, np.float32) for a in (O, U, Vv, D))
        a = np.asarray(img).astype(np.float32) / 255
        h, w = a.shape[:2]
        rad = 0.5 * math.hypot(w, h) / S + 0.02
        m = G(*groups)
        if not m.any():
            return 0
        m &= (np.abs(X - O[0]) < rad + depth * abs(D[0])) & (np.abs(Y - O[1]) < rad + depth * abs(D[1])) & (np.abs(Z - O[2]) < rad + depth * abs(D[2]))
        ys, xs = np.nonzero(m)
        if len(ys) == 0:
            return 0
        q = pos[ys, xs] - O
        u, v, dd = q @ U, q @ Vv, q @ D
        ok = (np.abs(u) < w / S / 2) & (np.abs(v) < h / S / 2) & (np.abs(dd) < depth) & ((nrm[ys, xs].astype(np.float32) @ D) > facing)
        ys, xs, u, v = ys[ok], xs[ok], u[ok], v[ok]
        if len(ys) == 0:
            return 0
        fx = np.clip(u * S + w / 2 - 0.5, 0, w - 1.001)
        fy = np.clip(h / 2 - v * S - 0.5, 0, h - 1.001)
        k = max(int(round(S / dens)), 1)
        if k > 1:
            ab = cv2.blur(a, (k, k))
        else:
            ab = a
        x0, y0 = fx.astype(int), fy.astype(int)
        tx, ty = (fx - x0)[:, None], (fy - y0)[:, None]
        smp = ab[y0, x0] * (1 - tx) * (1 - ty) + ab[y0, x0 + 1] * tx * (1 - ty) + ab[y0 + 1, x0] * (1 - tx) * ty + ab[y0 + 1, x0 + 1] * tx * ty
        al = smp[:, 3:4]
        rgb = smp[:, :3] / np.maximum(al, 1e-3)
        col[ys, xs] = col[ys, xs] * (1 - al) + rgb * al * (0.95 + 0.05 * (1 - ln[ys, xs][:, None]))
        smooth[ys, xs] = smooth[ys, xs] * (1 - al[:, 0]) + sm * al[:, 0]
        metal8[ys, xs] = (metal8[ys, xs] * (1 - al[:, 0])).astype(np.uint8)
        if flat:
            ys2, xs2 = np.nonzero(m)
            q2 = pos[ys2, xs2] - O
            in2 = (np.abs(q2 @ U) < w / S / 2 + 0.025) & (np.abs(q2 @ Vv) < h / S / 2 + 0.025) & (np.abs(q2 @ D) < depth) & ((nrm[ys2, xs2].astype(np.float32) @ D) > facing)
            ln[ys2[in2], xs2[in2]] = 0
            rv8[ys2[in2], xs2[in2]] = 0
        return len(ys)

    def on_surface(O, D, groups, r=0.07):
        O_, D_ = np.asarray(O, np.float32), np.asarray(D, np.float32)
        m = G(*groups) & (np.abs(Y - O_[1]) < r) & (np.abs(Z - O_[2]) < r) & (np.abs(X - O_[0]) < 0.9)
        ys, xs = np.nonzero(m)
        if len(ys):
            ok = (nrm[ys, xs].astype(np.float32) @ D_) > 0.2
            ys, xs = ys[ok], xs[ok]
        if len(ys) < 20:
            return None
        n_ = nrm[ys, xs].astype(np.float32).mean(0)
        n_ /= max(float(np.linalg.norm(n_)), 1e-6)
        u_ = np.array([0.0, 0.0, 1.0 if D_[0] > 0 else -1.0], np.float32)
        u_ -= n_ * float(u_ @ n_)
        u_ /= max(float(np.linalg.norm(u_)), 1e-6)
        v_ = np.cross(n_, u_) * (1.0 if D_[0] > 0 else -1.0)
        if v_[1] < 0:
            v_ = -v_
        return pos[ys, xs].mean(0), u_, v_, n_

    cnt = {}
    Vup = (0, 1, 0)
    GREYW = (0.80, 0.81, 0.80)
    FL_U, FL_V = (0, 0.563, -0.826), (0, 0.826, 0.563)
    for sx in (1, -1):
        U, D = (0, 0, sx), (sx, 0, 0)
        if name == "exfus":
            F = ("fuselage",)
            cnt["bars"] = project(bars_img(1.50, 0.25, 0.36), (sx * 0.9, 0.36, 4.22), U, Vup, D, F, facing=0.45)
            cnt["strip"] = project(formstrip_img(0.93, 0.066, 3), (sx * 0.9, 0.497, 5.725), U, Vup, D, F, facing=0.40, sm=0.62, flat=True)
            cnt["serial"] = project(text_img("ZJ914", 0.115, GREYW, 0.012, font=REG), (sx * 0.9, 0.22, -2.15), U, Vup, D, F, facing=0.55)
            sf = on_surface((sx * 0.9, 0.725, 6.52), D, F)
            if sf is not None:
                p0, u0, v0, n0 = sf
                cnt["tri"] = project(triangle_img(0.15), p0, u0, v0, n0, F, depth=0.12, facing=0.5, flat=True)
                cnt["seat"] = project(text_img("EJECTION SEAT", 0.0125, RED, 0.001), p0 - v0 * 0.10, u0, v0, n0, F, depth=0.12, facing=0.5)
            else:
                cnt["tri"] = project(triangle_img(0.15), (sx * 0.9, 0.725, 6.52), U, Vup, D, F, facing=0.35, flat=True)
                cnt["seat"] = project(text_img("EJECTION SEAT", 0.0125, RED, 0.001), (sx * 0.9, 0.625, 6.52), U, Vup, D, F, facing=0.35)
            cnt["hot"] = project(text_img("DANGER|HOT GASES", 0.017, RED, 0.001, box=RED, pad=0.006), (sx * 0.9, 0.13, 5.92), U, Vup, D, F, facing=0.45)
            cnt["radome note"] = project(text_img("CAUTION|RADOME|DO NOT PAINT", 0.011, GREYW, 0.0008, font=REG), (sx * 0.9, 0.30, 8.47), U, Vup, D, F, facing=0.45)
            if sx < 0:
                cnt["rescue"] = project(rescue_arrow_img(), (sx * 0.9, -0.40, 5.02), U, Vup, D, F, facing=0.4)
                cnt["handle"] = project(handle_marker_img(0.085), (sx * 0.9, -0.40, 5.235), U, Vup, D, F, facing=0.4)
                cnt["handle note"] = project(text_img("EMERGENCY CANOPY|JETTISON HANDLE", 0.0105, (0.93, 0.80, 0.12), 0.0008), (sx * 0.9, -0.305, 5.235), U, Vup, D, F, facing=0.4)
            else:
                cnt["rescue"] = project(rescue_box_img(), (sx * 0.9, -0.40, 5.05), U, Vup, D, F, facing=0.4)
            cnt["intake"] = project(text_img("DANGER|AIR INTAKE|KEEP CLEAR", 0.019, RED, 0.001), (sx * 0.9, -0.40, 5.43), U, Vup, D, F, facing=0.4)
            cnt["label"] = project(text_img("EXTERNAL|POWER", 0.0105, INK[:3], 0.0008, fill=(0.93, 0.80, 0.12), pad=0.006), (sx * 0.9, -0.57, 5.15), U, Vup, D, F, facing=0.4)
            for z_ in (3.95, 2.30, 0.70):
                cnt["nostep"] = project(text_img("NO STEP", 0.028, GREYW, 0.002), (sx * 0.62, 1.5, z_), (0, 0, sx), (-sx, 0, 0), (0, 1, 0), F + ("airbrake",), depth=1.2, facing=0.55)
            cnt["earth"] = project(earth_img(0.05, GREYW), (sx * 0.50, 1.5, 3.42), (0, 0, sx), (-sx, 0, 0), (0, 1, 0), F, depth=1.2, facing=0.55)
            cnt["warn"] = project(text_img("WARNING|CANOPY JETTISON ROCKETS|KEEP CLEAR WHEN|CANOPY IS OPEN", 0.0105, RED, 0.0008), (sx * 0.47, 1.5, 3.12), (0, 0, sx), (-sx, 0, 0), (0, 1, 0), F, depth=1.2, facing=0.55)
        elif name == "exfin":
            cnt["914"] = project(text_img("914", 0.19, GREYW, 0.012, font=REG), (0, 2.72, -3.92), U, Vup, D, ("fin", "rudder"))
            cnt["bat"] = project(bat_img(0.66), (0, 1.97, -3.22), U, Vup, D, ("fin",))
            cnt["flash"] = project(flash_img(0.44, 0.33, -sx, sx > 0), (0, 1.24, -3.08), U, Vup, D, ("fin",))
            cnt["code"] = project(text_img("WS-T", 0.25, RED, 0.02, font=BOLD), (0, 1.24, -2.32), U, Vup, D, ("fin",))
            cnt["strip"] = project(formstrip_img(1.30, 0.046, 4), (0, 1.93, -2.50), FL_U, FL_V, D, ("fin",), sm=0.62, flat=True)
        elif name == "exwing":
            for (x_, z_) in ((2.2, -1.95), (4.2, -2.0)):
                cnt["nostep"] = project(text_img("NO STEP", 0.032, GREYW, 0.002), (sx * x_, 0.5, z_), (1, 0, 0), (0, 0, 1), (0, 1, 0), ("flaperon_",), depth=1.5, facing=0.5)
            cnt["nostep2"] = project(text_img("NO STEP", 0.028, GREYW, 0.002), (sx * 1.15, 0.5, 7.05), (1, 0, 0), (0, 0, 1), (0, 1, 0), ("canard_",), depth=1.5, facing=0.5)
            cnt["pod strip"] = project(formstrip_img(0.52, 0.034, 3), (sx * 5.3, -0.30, -1.45), U, Vup, D, ("pod_",), depth=0.5, facing=0.6, sm=0.62, flat=True)
    if name == "exwing":
        rd = roundel_img(0.42)
        cnt["roundel up"] = project(rd, (-3.96, 0.5, -0.32), (1, 0, 0), (0, 0, 1), (0, 1, 0), ("wing_",), depth=1.5, facing=0.5)
        cnt["roundel low"] = project(rd, (3.96, -1.0, -0.32), (1, 0, 0), (0, 0, -1), (0, -1, 0), ("wing_",), depth=1.5, facing=0.5)
    if name == "exfus":
        top = ("fuselage", "airbrake")
        cnt["spine panel"] = project(patch_img(0.20, 0.24, (0.80, 0.81, 0.80)), (0, 1.5, 2.55), (1, 0, 0), (0, 0, 1), (0, 1, 0), ("airbrake",), depth=1.5, facing=0.5, flat=True)
        for z_ in (3.02, 3.20):
            cnt["spine rings"] = project(ring_img(0.075, GREYW), (-0.20, 1.5, z_), (1, 0, 0), (0, 0, 1), (0, 1, 0), top, depth=1.5, facing=0.5)
    print("   markings (texels):", cnt)

    del pos, nrm, X, Y, Z, NX, NY, grp
    gc.collect()
    kf = soft(keep, 0.7)
    base8 = np.empty((R, R, 3), np.uint8)
    for c_ in range(3):
        ch = col[..., c_]
        ch *= (1 - kf)
        ch += oldc[..., c_].astype(np.float32) * (kf / 255.0)
        base8[..., c_] = (np.clip(ch, 0, 1) * 255 + 0.5).astype(np.uint8)
    del col, oldc, kf, ch
    gc.collect()
    filled = cover.astype(np.uint8)
    k3 = np.ones((3, 3), np.uint8)
    for _ in range(max(int(14 * R / 8192), 4)):
        d = cv2.dilate(base8, k3)
        grow = cv2.dilate(filled, k3)
        new = (grow > 0) & (filled == 0)
        base8[new] = d[new]
        filled = grow
    del d, grow, new, filled
    Image.fromarray(base8, "RGB").save(os.path.join(ST, name + "_base.png"))
    del base8
    h = cv2.resize(-(ln + (0.30 / 255) * rv8), (RN, RN), interpolation=cv2.INTER_AREA)
    sm = cv2.resize(np.where(keep, 0.30, smooth).astype(np.float32), (RN, RN), interpolation=cv2.INTER_AREA)
    mt_ = cv2.resize(metal8, (RN, RN), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    nx, ny, _ = cp.normal_from_height(h, float(os.environ.get("EX_NRM", "0.48")))
    cp.save(cp.pack_normal(nx, ny), os.path.join(ST, name + "_normal.png"), "RGBA")
    mk = np.zeros((RN, RN, 4), np.float32)
    mk[..., 0] = np.clip(mt_, 0, 1)
    mk[..., 3] = np.clip(sm, 0.05, 0.9)
    cp.save(mk, os.path.join(ST, name + "_mask.png"), "RGBA")


import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
new_uv = {}
for name, prefixes, R, RN in ATLASES:
    mem = members(prefixes)
    faces, where = [], []
    for o in mem:
        for k, (li, c) in enumerate(o["faces"]):
            faces.append([v for v, t, n_ in c])
            where.append((objs.index(o), k))
    uvs = unwrap(faces)
    for w, uv in zip(where, uvs):
        new_uv[w] = (name, uv)
    if ONLY and name not in ONLY.split(","):
        continue
    P, UVn, UVo, tg, names = [], [], [], [], [o["name"] for o in mem]
    for o in mem:
        gi = names.index(o["name"])
        oi = objs.index(o)
        for k, (li, c) in enumerate(o["faces"]):
            uv = new_uv[(oi, k)][1]
            for j in range(1, len(c) - 1):
                tri = (0, j, j + 1)
                P.append([V[c[a][0]] for a in tri])
                UVn.append([uv[a] for a in tri])
                UVo.append([VT[c[a][1]] if c[a][1] >= 0 else (0, 0) for a in tri])
                tg.append(gi)
    paint(name, np.array(P), np.array(UVn), np.array(UVo), np.array(tg), names, int(R * SCALE), int(RN * SCALE))

face_at = {}
for oi, o in enumerate(objs):
    for k, (li, c) in enumerate(o["faces"]):
        if (oi, k) in new_uv:
            face_at[li] = (oi, k, c)
out = []
n_old, n_new = 0, 0
old2new = {}
done_mtl = set()
for li, line in enumerate(lines_in):
    if line.startswith("vt "):
        old2new[n_old] = n_new
        n_old += 1
        n_new += 1
        out.append(line)
    elif line.startswith("f "):
        if li in face_at:
            oi, k, c = face_at[li]
            atlas, uv = new_uv[(oi, k)]
            if oi not in done_mtl:
                out.append("usemtl " + atlas)
                done_mtl.add(oi)
            for u_, v_ in uv:
                out.append("vt %.6f %.6f" % (u_, v_))
            out.append("f " + " ".join("%d/%d/%s" % (v + 1, n_new + j + 1, (str(nn + 1) if nn >= 0 else "")) for j, (v, t, nn) in enumerate(c)))
            n_new += len(c)
        else:
            parts = []
            for c in line.split()[1:]:
                a = (c.split("/") + ["", ""])[:3]
                if a[1]:
                    a[1] = str(old2new[int(a[1]) - 1] + 1)
                parts.append("/".join(a).rstrip("/") if not a[2] else "/".join(a))
            out.append("f " + " ".join(parts))
    else:
        out.append(line)
fixed, last = [], None
i = 0
open(os.path.join(ST, "typhoon.obj"), "w").write("\n".join(out))
mt = os.path.join(ST, "typhoon_materials.txt")
txt = open(mt).read()
for name, _, _, _ in ATLASES:
    if not any(l.startswith(name + " ") for l in txt.split("\n")):
        txt = txt.rstrip("\n") + "\n%s base=%s_base.png normal=%s_normal.png mask=%s_mask.png smooth=1 metal=1\n" % (name, name, name, name)
open(mt, "w").write(txt)
Image.open(os.path.join(SRC, "airframe_src_base.png")).save(os.path.join(ST, "airframe_base.png"))
print("exterior: OBJ rewritten (%d faces re-mapped), materials added, airframe_base.png back to the source" % len(face_at))
import resource
print("peak memory %.1f GB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6))
