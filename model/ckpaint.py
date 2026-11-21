import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy import ndimage as ndi

SURF = {
    "fabric":       ((0.455, 0.455, 0.300), 0.0, 0.18),
    "fabric_dark":  ((0.380, 0.385, 0.255), 0.0, 0.16),
    "mesh":         ((0.440, 0.445, 0.295), 0.0, 0.15),
    "black":        ((0.110, 0.113, 0.118), 0.0, 0.40),
    "pedgrey":      ((0.415, 0.428, 0.441), 0.0, 0.37),
    "pedmould":     ((0.496, 0.512, 0.527), 0.0, 0.39),
    "pedgrey_old":  ((0.47, 0.485, 0.50), 0.0, 0.34),
    "rubber":       ((0.150, 0.153, 0.160), 0.0, 0.34),
    "gripgrey":     ((0.205, 0.210, 0.218), 0.0, 0.36),
    "carbon":       ((0.120, 0.123, 0.130), 0.1, 0.58),
    "metal":        ((0.420, 0.430, 0.440), 0.85, 0.55),
    "darkgrey":     ((0.175, 0.180, 0.188), 0.0, 0.38),
    "webbing":      ((0.500, 0.480, 0.320), 0.0, 0.22),
    "webbing_grey": ((0.450, 0.480, 0.500), 0.0, 0.22),
}
SWATCH = {
    "black": ((0.06, 0.062, 0.066), 0.0, 0.45), "chrome": ((0.78, 0.79, 0.80), 1.0, 0.86),
    "white": ((0.92, 0.92, 0.90), 0.0, 0.4), "yellow": ((0.93, 0.74, 0.08), 0.0, 0.45),
    "red": ((0.72, 0.08, 0.06), 0.0, 0.55), "darkgrey": ((0.20, 0.21, 0.22), 0.3, 0.45),
    "olive": ((0.33, 0.34, 0.22), 0.0, 0.2), "metal": ((0.58, 0.59, 0.60), 0.9, 0.6),
    "green": ((0.2, 0.8, 0.3), 0.0, 0.5),
    "orange": ((0.80, 0.33, 0.12), 0.0, 0.45), "ltgrey": ((0.46, 0.47, 0.48), 0.5, 0.45),
    "keyblue": ((0.03, 0.05, 0.22), 0.0, 0.8), "pedgrey": ((0.50, 0.515, 0.53), 0.0, 0.35),
    "boxgrey": ((0.300, 0.310, 0.322), 0.0, 0.34),
}


def fbm(shape, scales=(64, 16, 4), weights=(0.6, 0.3, 0.1), seed=0):
    rng = np.random.default_rng(seed)
    out = np.zeros(shape, np.float32)
    for s, w in zip(scales, weights):
        small = rng.standard_normal((max(shape[0] // s, 2) + 2, max(shape[1] // s, 2) + 2)).astype(np.float32)
        big = np.asarray(Image.fromarray(small).resize((shape[1] + 2 * s, shape[0] + 2 * s), Image.BICUBIC))[s:s + shape[0], s:s + shape[1]]
        out += w * big
    return out / max(np.abs(out).max(), 1e-6)


def raster(UV, P, ids, W, H):
    idmap = np.full((H, W), -1, np.int32)
    pos = np.zeros((H, W, 3), np.float32)
    for t in range(len(UV)):
        px = UV[t, :, 0] * W
        py = (1 - UV[t, :, 1]) * H
        x0, x1 = max(int(np.floor(px.min())), 0), min(int(np.ceil(px.max())), W - 1)
        y0, y1 = max(int(np.floor(py.min())), 0), min(int(np.ceil(py.max())), H - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (py[1] - py[2]) * (px[0] - px[2]) + (px[2] - px[1]) * (py[0] - py[2])
        if abs(d) < 1e-12:
            continue
        l0 = ((py[1] - py[2]) * (xs - px[2]) + (px[2] - px[1]) * (ys - py[2])) / d
        l1 = ((py[2] - py[0]) * (xs - px[2]) + (px[0] - px[2]) * (ys - py[2])) / d
        l2 = 1 - l0 - l1
        m = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        if not m.any():
            continue
        p = l0[..., None] * P[t, 0] + l1[..., None] * P[t, 1] + l2[..., None] * P[t, 2]
        sub = (slice(y0, y1 + 1), slice(x0, x1 + 1))
        idmap[sub][m] = ids[t]
        pos[sub][m] = p[m]
    return idmap, pos


def weave(X, Y, period=7.0):
    a = np.sin(2 * np.pi * X / period)
    b = np.sin(2 * np.pi * Y / period)
    cell = (np.floor(X / period) + np.floor(Y / period)) % 2
    return 0.5 + 0.25 * np.where(cell > 0, np.abs(a), np.abs(b)) + 0.25 * a * b


def spacer_mesh(X, Y, period=26.0):
    yy = Y / (period * 0.866)
    xx = X / period + 0.5 * (np.floor(yy) % 2)
    fx = xx - np.floor(xx) - 0.5
    fy = yy - np.floor(yy) - 0.5
    r = np.sqrt(fx * fx + (fy * 1.15) ** 2)
    return np.clip((r - 0.22) / 0.12, 0, 1)


def twill(X, Y, period=10.0):
    k = np.floor(X / period) + np.floor(Y / period)
    blk = (np.floor(X / (2 * period)) + np.floor(Y / (2 * period))) % 2
    d = np.where(blk > 0, (X + Y), (X - Y)) / period
    return 0.5 + 0.5 * np.sin(np.pi * d) * (0.6 + 0.4 * (k % 2))


def ribs(across, n=14):
    return 0.5 + 0.5 * np.cos(2 * np.pi * across * n)


def paint_surfaces(idmap, pos, part_surface, H, W):
    base = np.zeros((H, W, 3), np.float32)
    height = np.full((H, W), 0.5, np.float32)
    metal = np.zeros((H, W), np.float32)
    smooth = np.full((H, W), 0.3, np.float32)
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    lowf = fbm((H, W), (256, 64), (0.7, 0.3), seed=1)
    grain = fbm((H, W), (8, 2), (0.6, 0.4), seed=2)
    for pid, surf in part_surface.items():
        m = idmap == pid
        if not m.any() or surf not in SURF:
            continue
        col, mt, sm = SURF[surf]
        col = np.array(col, np.float32)
        x, y = X[m], Y[m]
        if surf in ("fabric", "fabric_dark"):
            h = weave(x, y, 7.0)
            c = col[None, :] * (0.88 + 0.16 * h[:, None]) * (1 + 0.07 * lowf[m][:, None])
            s = sm + 0.05 * h
        elif surf == "mesh":
            h = spacer_mesh(x, y, 15.0) * (0.8 + 0.2 * weave(x, y, 5.0))
            c = col[None, :] * (0.70 + 0.35 * h[:, None]) * (1 + 0.06 * lowf[m][:, None])
            s = sm + 0.0 * h
        elif surf == "carbon":
            h = 0.5 + 0.15 * (twill(x, y, 3.0) - 0.5)
            c = col[None, :] * (0.95 + 0.08 * h[:, None])
            s = sm - 0.1 * (1 - h)
        elif surf == "metal":
            h = 0.5 + 0.1 * grain[m]
            c = col[None, :] * (0.92 + 0.1 * grain[m][:, None])
            s = sm + 0.1 * grain[m]
        else:
            h = 0.5 + 0.06 * grain[m]
            c = col[None, :] * (1 + 0.06 * lowf[m][:, None] + 0.03 * grain[m][:, None])
            s = sm + 0.05 * grain[m]
        base[m] = c
        height[m] = h
        metal[m] = mt
        smooth[m] = s
    return base, height, metal, smooth


def paint_rect(base, height, metal, smooth, rect, kind, H, W, extra=None):
    u0, v0, u1, v1 = rect
    x0, x1 = int(u0 * W), int(math.ceil(u1 * W))
    y0, y1 = int((1 - v1) * H), int(math.ceil((1 - v0) * H))
    h, w = y1 - y0, x1 - x0
    Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
    sl = (slice(y0, y1), slice(x0, x1))
    if kind in ("webbing", "webbing_grey"):
        col, mt, sm = SURF[kind]
        across = Y / max(h - 1, 1)
        hh = ribs(across, 16) * 0.6 + 0.4 * weave(X, Y, 4.0)
        edge = np.minimum(across, 1 - across)
        hh = np.where(edge < 0.06, 0.8, hh)
        c = np.array(col)[None, None, :] * (0.8 + 0.3 * hh[..., None])
        for ex in (0.02, 0.97):
            cx = ex * w
            box = (np.abs(X - cx) < 0.018 * w) & (edge > 0.12)
            diag = box & ((np.abs((X - cx) / (0.018 * w) - (across - 0.5) / 0.38) < 0.08) |
                          (np.abs((X - cx) / (0.018 * w) + (across - 0.5) / 0.38) < 0.08) |
                          (np.abs(np.abs(X - cx) - 0.017 * w) < 1.2))
            c[diag] *= 0.55
        base[sl], height[sl], metal[sl], smooth[sl] = c, hh, mt, sm
    elif kind == "handle":
        stripe = (np.floor((X + Y * 1.6) / 40.0) % 2) > 0
        c = np.where(stripe[..., None], np.array([0.93, 0.76, 0.06]), np.array([0.05, 0.05, 0.05]))
        hh = 0.5 + 0.15 * weave(X, Y, 3.0)
        c = c * (0.85 + 0.25 * hh[..., None])
        base[sl], height[sl], metal[sl], smooth[sl] = c, hh, 0.0, 0.35
    elif kind == "qrbface":
        size = max(h, w)
        S = 4
        im = Image.new("RGB", (size * S, size * S), (14, 14, 15))
        d = ImageDraw.Draw(im)
        R = size * S / 2
        d.ellipse([R - R * 0.98, R - R * 0.98, R + R * 0.98, R + R * 0.98], fill=(22, 22, 24), outline=(55, 55, 58), width=S * 2)
        d.ellipse([R - R * 0.30, R - R * 0.30, R + R * 0.30, R + R * 0.30], fill=(40, 40, 42), outline=(90, 90, 92), width=S * 2)
        d.ellipse([R - R * 0.12, R - R * 0.12, R + R * 0.12, R + R * 0.12], fill=(70, 70, 72))
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(R * 0.17))
        except OSError:
            font = ImageFont.load_default()

        def arc_text(text, radius, start_deg, step_deg, flip):
            for i, ch in enumerate(text):
                a = math.radians(start_deg + i * step_deg)
                cx, cy = R + radius * math.cos(a), R + radius * math.sin(a)
                g = Image.new("L", (int(R * 0.3), int(R * 0.3)), 0)
                ImageDraw.Draw(g).text((g.width / 2, g.height / 2), ch, fill=235, font=font, anchor="mm")
                rot = -math.degrees(a) - 90 if not flip else -math.degrees(a) + 90
                g = g.rotate(rot, resample=Image.BICUBIC)
                im.paste((235, 235, 230), (int(cx - g.width / 2), int(cy - g.height / 2)), g)
        t1 = "PUSH BUTTON"
        arc_text(t1, R * 0.64, -90 - (len(t1) - 1) * 6.5, 13.0, False)
        t2 = "TURN TO RELEASE"
        arc_text(t2, R * 0.64, 90 + (len(t2) - 1) * 5.6, -11.2, True)
        im = im.rotate(180)
        im = im.resize((w, h), Image.LANCZOS)
        c = np.asarray(im).astype(np.float32) / 255
        lum = c.mean(2)
        base[sl], height[sl], metal[sl], smooth[sl] = c, 0.5 + 0.3 * (lum > 0.5), 0.0, 0.45
    elif kind == "swtex":
        import ctl_parts
        c, hh, mt, sm = ctl_parts.paint_cell(extra, h, w)
        base[sl], height[sl], metal[sl], smooth[sl] = c, hh, mt, sm
    elif kind == "swatch":
        col, mt, sm = SWATCH.get(extra, ((0.5, 0.5, 0.5), 0, 0.5)) if extra != "hazard" else ((0, 0, 0), 0, 0.45)
        if extra == "hazard":
            stripe = (np.floor((X + Y) / (w / 4.0)) % 2) > 0
            c = np.where(stripe[..., None], np.array([0.92, 0.72, 0.05]), np.array([0.04, 0.04, 0.04]))
        else:
            c = np.broadcast_to(np.array(col, np.float32), (h, w, 3))
        base[sl], height[sl], metal[sl], smooth[sl] = c, 0.5, mt, sm


def dilate(img, filled, iters=None):
    idx = ndi.distance_transform_edt(~filled, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


def normal_from_height(height, strength):
    gy, gx = np.gradient(height.astype(np.float32))
    nx, ny = -gx * strength, gy * strength
    nz = np.ones_like(nx)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return nx / ln, ny / ln, nz / ln


def pack_normal(nx, ny):
    out = np.ones(nx.shape + (4,), np.float32)
    out[..., 1] = ny * 0.5 + 0.5
    out[..., 2] = ny * 0.5 + 0.5
    out[..., 3] = nx * 0.5 + 0.5
    return out


def save(a, path, mode):
    Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), mode).save(path, optimize=True)
