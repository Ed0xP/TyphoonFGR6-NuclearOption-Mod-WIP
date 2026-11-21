import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi


def raster_attr(UV, P, A, W, H):
    tid = np.full((H, W), -1, np.int32)
    pos = np.zeros((H, W, 3), np.float32)
    att = np.zeros((H, W, A.shape[2]), np.float32)
    for t in range(len(UV)):
        px = UV[t, :, 0] * W
        py = (1 - UV[t, :, 1]) * H
        x0, x1 = max(int(np.floor(px.min())) - 1, 0), min(int(np.ceil(px.max())) + 1, W - 1)
        y0, y1 = max(int(np.floor(py.min())) - 1, 0), min(int(np.ceil(py.max())) + 1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (py[1] - py[2]) * (px[0] - px[2]) + (px[2] - px[1]) * (py[0] - py[2])
        if abs(d) < 1e-12:
            continue
        l0 = ((py[1] - py[2]) * (xs - px[2]) + (px[2] - px[1]) * (ys - py[2])) / d
        l1 = ((py[2] - py[0]) * (xs - px[2]) + (px[0] - px[2]) * (ys - py[2])) / d
        l2 = 1 - l0 - l1
        m = (l0 >= -0.03) & (l1 >= -0.03) & (l2 >= -0.03)
        if not m.any():
            continue
        sub = (slice(y0, y1 + 1), slice(x0, x1 + 1))
        inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        m2 = m & (inside | (tid[sub] < 0))
        pos[sub][m2] = (l0[..., None] * P[t, 0] + l1[..., None] * P[t, 1] + l2[..., None] * P[t, 2])[m2]
        att[sub][m2] = (l0[..., None] * A[t, 0] + l1[..., None] * A[t, 1] + l2[..., None] * A[t, 2])[m2]
        tid[sub][m2] = t
    return tid, pos, att


def sample(img, uv):
    H, W = img.shape[:2]
    x = uv[..., 0] * W - 0.5
    y = (1 - uv[..., 1]) * H - 0.5
    out = np.zeros(uv.shape[:-1] + (img.shape[2],), np.float32)
    for c in range(img.shape[2]):
        out[..., c] = ndi.map_coordinates(img[..., c], [y, x], order=1, mode="nearest")
    return out


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def tri_affine(Pt, UVt):
    e1, e2 = Pt[1] - Pt[0], Pt[2] - Pt[0]
    n = np.cross(e1, e2)
    M = np.array([e1, e2, n]).T
    Minv = np.linalg.inv(M)

    def f(p):
        b = Minv @ (np.asarray(p) - Pt[0])
        return UVt[0] + b[0] * (UVt[1] - UVt[0]) + b[1] * (UVt[2] - UVt[0])
    return f


LABELS = {
    "toggle": ["ON/OFF", "NORM/REV", "OPEN/NORM", "DAY/NIGHT", "AUTO/OFF", "MAIN/REV", "RAD1/RAD2", "NORM/AMP",
               "BRT/DIM", "LAND/TAXI", "EXPD/MAN", "NORM/OFF", "WHITE/RED", "ARM/SAFE"],
    "lever": ["UP/DOWN", "NORM/REV", "OPEN/NORM", "ON/OFF", "NORM/EMER", "OUT/IN"],
    "knob": ["CABIN", "FLOW", "SUIT", "FORM", "FLOODS", "MSSL", "TB", "I/C", "TEMP", "CONSOLE", "INST", "MIDS A",
             "MIDS B", "TAC"],
    "pointer": ["MODE", "CIU", "X FEED", "FUEL PROBE", "REV LTS"],
}


PANEL_TITLES = ["SEL JETT", "CABIN", "EXT LIGHTS", "INT LIGHTS", "MIDS", "AIR DRIVE", "FUEL PROBE", "FLOODS", "ECS",
                "SECURE DATA", "YAW TRIM", "COMMS", "FUEL", "ENG START", "DEMIST", "IFF", "OXY", "ELEC", "HYD", "FCS"]


DECALS = False
LABELS_OUT = []
SKIP_SIDES = set()


def paint(tid, pos, nrm, old_rgb, ao, cover, controls, density, size, uv_lookup, seed=3):
    rng = np.random.default_rng(seed)
    H, W = tid.shape
    rgb = old_rgb
    lum = rgb.mean(2)
    r12 = max(int(density * 0.006), 3)
    mean12 = cv2.blur(lum, (2 * r12 + 1, 2 * r12 + 1))
    satv = rgb.max(2) - rgb.min(2)
    sat12 = cv2.blur(satv, (2 * r12 + 1, 2 * r12 + 1))
    light = smoothstep(0.34, 0.42, mean12) * (1 - smoothstep(0.10, 0.18, sat12))
    clear = np.zeros((H, W), bool)
    for kind, p, r_, f_, u_, rad, uv_of in controls:
        d = np.linalg.norm(pos - np.asarray(p, np.float32), axis=2)
        clear |= (d < rad * 1.3) & cover
    clear = ndi.binary_dilation(clear, iterations=3)
    light = np.maximum(light, ndi.gaussian_filter(clear.astype(np.float32), 2.0))
    light = ndi.gaussian_filter(light, density * 0.0005)
    o8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    keep_c = cv2.ximgproc.guidedFilter(o8, o8, radius=4, eps=(0.07 * 255) ** 2).astype(np.float32) / 255
    kb = np.stack([ndi.gaussian_filter(keep_c[..., c], 1.5) for c in range(3)], -1)
    flat = np.clip(keep_c + 0.35 * (keep_c - kb), 0, 1)
    _kerb = (np.abs(pos[..., 0]) > 0.215) & (np.abs(pos[..., 0]) < 0.315) & (pos[..., 1] > 6.94) & (pos[..., 1] < 7.14) & (pos[..., 2] > 0.40) & (pos[..., 2] < 0.60)
    flat[_kerb] = np.array([0.205, 0.210, 0.216], np.float32) * (1 + 0.03 * ndi.gaussian_filter(rng.standard_normal((H, W)).astype(np.float32), 3.0))[_kerb][:, None]
    grey = np.array([0.555, 0.570, 0.580], np.float32)
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    top = cover & (nrm[..., 2] > 0.3) & (np.abs(x) > 0.2)
    shade = np.ones((H, W), np.float32)
    gaps = np.zeros((H, W), bool)
    fast_pts = []
    titles = []
    ctrl_p = np.array([c[1] for c in controls]) if controls else np.zeros((0, 3))
    for side in (-1, 1):
        if side in SKIP_SIDES:
            continue
        m = top & (np.sign(x) == side)
        if not m.any():
            continue
        ys = y[m]
        y0, y1 = np.percentile(ys, 0.5), np.percentile(ys, 99.5)
        cy = ctrl_p[np.sign(ctrl_p[:, 0]) == side][:, 1] if len(ctrl_p) else np.zeros(0)
        cuts = [y0]
        while cuts[-1] + 0.07 < y1 - 0.05:
            cand = np.linspace(cuts[-1] + 0.07, min(cuts[-1] + 0.15, y1 - 0.05), 40)
            clr = np.array([np.min(np.abs(cy - c)) if len(cy) else 1.0 for c in cand])
            cuts.append(float(cand[np.argmax(clr - 0.05 * np.abs(cand - cuts[-1] - 0.11))]))
        cuts.append(y1)
        for i in range(len(cuts) - 1):
            a_, b_ = cuts[i], cuts[i + 1]
            pm = m & (y >= a_) & (y < b_)
            shade[pm] = 1.0 + rng.uniform(-0.025, 0.025)
            if i > 0:
                gaps |= m & (np.abs(y - a_) < 0.00045)
            band = m & (np.abs(y - a_) < 0.004)
            if band.any():
                ax_ = np.abs(x[band])
                for yy in (a_ + 0.007, b_ - 0.007):
                    for xx in (ax_.min() + 0.008, ax_.max() - 0.008):
                        fast_pts.append(np.array([side * xx, yy, np.median(z[band])]))
                tx = ax_.min() + 0.022
                titles.append((np.array([side * tx, a_ + 0.008, np.median(z[band])]), PANEL_TITLES[rng.integers(len(PANEL_TITLES))]))
    titles = []
    paint_c = grey[None, None, :] * shade[..., None]
    base = flat * (1 - light[..., None]) + paint_c * light[..., None]
    gaps &= light > 0.5
    height = np.full((H, W), 0.5, np.float32)
    gaps_s = ndi.gaussian_filter(gaps.astype(np.float32), 0.6)
    base = base * (1 - 0.6 * gaps_s[..., None])
    height -= 0.4 * gaps_s
    im = Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8))
    hm = Image.fromarray((np.clip(height, 0, 1) * 255).astype(np.uint8))
    em = Image.new("L", (W, H), 0)
    dr, dh, de = ImageDraw.Draw(im), ImageDraw.Draw(hm), ImageDraw.Draw(em)
    font_path = "DejaVuSansCondensed-Bold.ttf"
    try:
        ImageFont.truetype(font_path, 10)
    except OSError:
        font_path = "DejaVuSans-Bold.ttf"

    def frame_px(fmap, p, r_, f_):
        c_uv = fmap(p)
        c_px = np.array([c_uv[0] * W, (1 - c_uv[1]) * H])
        def to_px(q):
            u = fmap(q)
            return np.array([u[0] * W, (1 - u[1]) * H])
        ax_r = (to_px(p + r_ * 0.01) - c_px) / 0.01
        ax_f = (to_px(p + f_ * 0.01) - c_px) / 0.01
        return c_px, ax_r, ax_f

    def text_at(fmap, p, r_, f_, text, cap_m, dy=0.0, n_=(0.0, 0.0, 1.0)):
        n3 = np.asarray(n_, float); r3 = np.asarray(r_, float)
        u3 = np.cross(n3, r3)
        if u3[1] < 0:
            r3, u3 = -r3, -u3
        LABELS_OUT.append({"pos": [float(v) for v in np.asarray(p, float) + np.asarray(f_, float) * dy], "r": [float(v) for v in r3],
                           "u": [float(v) for v in u3], "n": [float(v) for v in n3], "text": str(text), "cap": float(cap_m),
                           "font": "FONT", "spacing": 1.45, "col": [0.89, 0.90, 0.86], "seen": True})
        c_px, ax_r, ax_f = frame_px(fmap, p, r_, f_)
        ppm = np.linalg.norm(ax_r)
        if ppm < 50:
            return
        ang = math.degrees(math.atan2(ax_r[1], ax_r[0]))
        mirrored = (ax_r[0] * ax_f[1] - ax_r[1] * ax_f[0]) > 0
        S = 4
        cap = cap_m * ppm
        font = ImageFont.truetype(font_path, max(int(cap * S * 1.4), 8))
        g = Image.new("L", (int(cap * S * 1.3 * (len(text) + 2)), int(cap * S * 2.4)), 0)
        ImageDraw.Draw(g).text((g.width / 2, g.height / 2), text, fill=255, font=font, anchor="mm")
        if mirrored:
            g = g.transpose(Image.FLIP_LEFT_RIGHT)
        g = g.resize((max(g.width // S, 1), max(g.height // S, 1)), Image.LANCZOS)
        g = g.rotate(-ang, resample=Image.BICUBIC, expand=True)
        q = c_px + ax_f * dy
        box = (int(q[0] - g.width / 2), int(q[1] - g.height / 2))
        if not DECALS:
            im.paste((24, 24, 26), box, g)
            hm.paste(95, box, g)
        em.paste(255, box, g)

    n_lab = 0
    for kind, p, r_, f_, u_, rad, fmap in controls:
        if kind not in LABELS:
            continue
        p, r_, f_ = np.asarray(p), np.asarray(r_), np.asarray(f_)
        pick = str(rng.choice(LABELS[kind]))
        words = pick.split("/") if "/" in pick else [pick, ""]
        if kind in ("toggle", "lever"):
            text_at(fmap, p, r_, f_, words[0], 0.0023, rad + 0.0035, u_)
            text_at(fmap, p, r_, f_, words[1], 0.0023, -(rad + 0.0035), u_)
        else:
            text_at(fmap, p, r_, f_, words[0], 0.0023, rad * 1.45 + 0.004, u_)
            c_px, ax_r, ax_f = frame_px(fmap, p, r_, f_)
            wpx = max(int(0.0005 * np.linalg.norm(ax_r)), 1)
            for k_ in range(7):
                a = math.radians(-135 + k_ * 45)
                v = np.array([math.sin(a), math.cos(a)])
                q0 = c_px + ax_r * v[0] * rad * 1.05 + ax_f * v[1] * rad * 1.05
                q1 = c_px + ax_r * v[0] * rad * 1.35 + ax_f * v[1] * rad * 1.35
                dr.line([tuple(q0), tuple(q1)], fill=(24, 24, 26), width=wpx)
                dh.line([tuple(q0), tuple(q1)], fill=95, width=wpx)
                de.line([tuple(q0), tuple(q1)], fill=255, width=wpx)
        n_lab += 1
    for p, t in titles:
        fmap = uv_lookup(p)
        if fmap is None:
            continue
        r_, f_ = np.array([1.0, 0, 0]) * np.sign(p[0]) if False else np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
        text_at(fmap, p, r_, f_, t, 0.0028)
    n_f = 0
    for p in fast_pts:
        if len(ctrl_p) and np.min(np.linalg.norm(ctrl_p - p, axis=1)) < 0.009:
            continue
        fmap = uv_lookup(p)
        if fmap is None:
            continue
        c_px, ax_r, ax_f = frame_px(fmap, p, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]))
        rr = 0.0024 * np.linalg.norm(ax_r)
        cx, cy = c_px
        if not (0 <= cx < W and 0 <= cy < H) or light[int(cy), int(cx)] < 0.5:
            continue
        pc = tuple(int(v) for v in np.clip(np.asarray(im.getpixel((int(cx), int(cy)))) * 0.85, 0, 255))
        dr.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=pc, outline=(45, 47, 49), width=max(int(rr * 0.2), 1))
        dh.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=165)
        a = rng.uniform(0, np.pi)
        dx, dy = np.cos(a) * rr * 0.8, np.sin(a) * rr * 0.8
        dr.line([cx - dx, cy - dy, cx + dx, cy + dy], fill=(28, 28, 30), width=max(int(rr * 0.25), 1))
        dh.line([cx - dx, cy - dy, cx + dx, cy + dy], fill=100, width=max(int(rr * 0.25), 1))
        n_f += 1
    base = np.asarray(im).astype(np.float32) / 255
    height = np.asarray(hm).astype(np.float32) / 255
    grain = ndi.gaussian_filter(rng.standard_normal((H, W)).astype(np.float32), 1.0)
    height = height + 0.010 * grain
    base = base * (1 + 0.010 * grain[..., None])
    base = base * (0.55 + 0.45 * ao)[..., None]
    smooth = (0.38 - 0.12 * (height < 0.45)) * (0.7 + 0.3 * ao)
    print(f"console skin: {n_lab} labelled controls, {len(titles)} panels, {n_f} fasteners")
    emit = (np.asarray(em).astype(np.float32) / 255)[..., None] * np.array([0.55, 1.0, 0.65], np.float32)
    return base, height, smooth.astype(np.float32), emit
