import math

try:
    import bmesh
    from mathutils import Vector
    import ckmodel as ck
    Z = Vector((0, 0, 1))
except ImportError:
    bmesh = None

CELLS = {"lever": (0.82, 0.24, 0.90, 0.32), "knob": (0.90, 0.24, 0.98, 0.32), "handle": (0.82, 0.33, 0.90, 0.41),
         "hose": (0.90, 0.33, 0.98, 0.41), "steel": (0.82, 0.42, 0.90, 0.50)}
INSET = 0.09


def uv_axis(bm, cell, base, axis, length, v0=0.0, v1=1.0):
    u0, w0, u1, w1 = CELLS[cell]
    axis = Vector(axis).normalized()
    t = axis.orthogonal().normalized()
    b = axis.cross(t)
    base = Vector(base)
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            d = lp.vert.co - base
            h = min(max(d.dot(axis) / max(length, 1e-9), 0.0), 1.0)
            uu = abs(math.atan2(d.dot(b), d.dot(t))) / math.pi
            vv = v0 + (v1 - v0) * h
            lp[uvl].uv = (u0 + (u1 - u0) * (INSET + (1 - 2 * INSET) * uu), w0 + (w1 - w0) * (INSET + (1 - 2 * INSET) * vv))
    return bm


def _cyl(base, axis, r, h, seg=16, r_top=None):
    b = bmesh.new()
    ck.cylinder(b, Vector(base), Vector(axis), r, h, seg=seg, r_top=r_top)
    bmesh.ops.recalc_face_normals(b, faces=b.faces[:])
    return b


def _gear(base, axis, r, h, teeth, depth, r_top=None):
    from cockpit_hotas import gear
    return gear(Vector(base), Vector(axis), r, h, teeth=teeth, depth=depth, r_top=r_top)


def collar(parts, s=1.0):
    z = 0.0
    for r, h in ((0.0056, 0.0013), (0.0045, 0.0011), (0.0050, 0.0009), (0.0041, 0.0012)):
        parts.append(uv_axis(_cyl((0, 0, z), Z, r * s, h, seg=18, r_top=r * s * 0.96), "lever", (0, 0, 0), Z, 0.0045, 0.0, 0.16))
        z += h
    return z


def lever(parts, b0, ax, r0, r1, L, v0=0.18, seg=16):
    b0, ax = Vector(b0), Vector(ax).normalized()
    tot = L + 0.0011
    parts.append(uv_axis(_cyl(b0, ax, r0, L, seg=seg, r_top=r1), "lever", b0, ax, tot, v0, 1.0))
    parts.append(uv_axis(_cyl(b0 + ax * L, ax, r1, 0.0011, seg=seg, r_top=r1 * 0.80), "lever", b0, ax, tot, v0, 1.0))
    return b0 + ax * tot


def toggle(sw, style="bat", lean=14.0, lean_dir=90.0, s=1.0, split=False):
    parts = []
    z = collar(parts, s)
    if split:
        fixed, parts, lean = ck.merge(parts), [], 0.0
    a, d = math.radians(lean), math.radians(lean_dir)
    ax = Vector((math.cos(d) * math.sin(a), math.sin(d) * math.sin(a), math.cos(a)))
    side = Vector((-math.sin(d), math.cos(d), 0))
    b0 = Vector((0, 0, z - 0.0006))
    F = ck.frame(side, ax.cross(side).normalized(), ax)
    if style == "yellow":
        lever(parts, b0, ax, 0.0024 * s, 0.0026 * s, 0.0080)
        for k in range(4):
            parts.append(sw(ck.rbox(b0 + ax * (0.0105 + k * 0.0042), (0.0115, 0.0048, 0.0042), F, bevel=0.0007, seg=1), "yellow" if k % 2 == 0 else "black"))
    elif style == "pyramid":
        lever(parts, b0, ax, 0.0024 * s, 0.0026 * s, 0.0080)
        parts.append(uv_axis(_cyl(b0 + ax * 0.0088, ax, 0.0076, 0.0095, seg=4, r_top=0.0010), "lever", b0, ax, 0.019, 0.2, 1.0))
    elif style == "bat":
        lever(parts, b0, ax, 0.0024 * s, 0.0034 * s, 0.0165 * s)
    else:
        parts.append(uv_axis(_cyl(b0, ax, 0.0036 * s, 0.0052, seg=16, r_top=0.0034 * s), "lever", b0, ax, 0.026, 0.10, 1.0))
        parts.append(uv_axis(_cyl(b0 + ax * 0.0052, ax, 0.0040 * s, 0.0010, seg=16, r_top=0.0036 * s), "lever", b0, ax, 0.026, 0.10, 1.0))
        if style == "cube":
            parts.append(uv_axis(_cyl(b0 + ax * 0.0062, ax, 0.0028 * s, 0.0100, seg=14), "lever", b0, ax, 0.026, 0.10, 1.0))
            c = b0 + ax * 0.0205
            parts.append(uv_axis(ck.rbox(c, (0.0120, 0.0120, 0.0105), F, bevel=0.0015, seg=2), "lever", b0 + ax * 0.0150, ax, 0.0112, 0.34, 0.86))
            parts.append(sw(_cyl(c + ax * 0.00525, ax, 0.0040, 0.00025, seg=20), "darkgrey"))
        else:
            b1 = b0 + ax * 0.0062
            parts.append(uv_axis(_cyl(b1, ax, 0.0027 * s, 0.0185, seg=16, r_top=0.0039 * s), "lever", b0, ax, 0.0258, 0.10, 1.0))
            parts.append(uv_axis(_cyl(b1 + ax * 0.0185, ax, 0.0039 * s, 0.0011, seg=16, r_top=0.0032 * s), "lever", b0, ax, 0.0258, 0.10, 1.0))
    if split:
        return fixed, ck.merge(parts), b0
    return ck.merge(parts)


def knob(sw, d, style="plain", ang=0.0, cell="knob"):
    r = d / 2
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    R = ck.frame(Vector((ca, sa, 0)), Vector((-sa, ca, 0)), Z)
    z0 = 0.0016
    parts = [sw(_cyl((0, 0, 0), Z, r * 1.15, z0, seg=28), "black")]

    def tex(b, h):
        return uv_axis(b, cell, (0, 0, z0), Z, h)
    if style == "bar":
        H = 0.0060 + 0.0110
        parts.append(tex(_cyl((0, 0, z0), Z, r * 0.66, 0.0060, seg=24), H))
        parts.append(tex(ck.rbox(Vector((0, 0, z0 + 0.0060 + 0.0055)), (r * 0.66, r * 1.9, 0.011), R, bevel=0.0020, seg=3), H))
        parts.append(sw(ck.rbox(R @ Vector((0, r * 0.60, z0 + H + 0.0001)), (0.0013, r * 0.66, 0.0004), R, bevel=0), "white"))
    elif style == "square":
        H = 0.004 + 0.012
        parts.append(tex(_cyl((0, 0, z0), Z, r * 0.60, 0.004, seg=20), H))
        parts.append(tex(ck.rbox(Vector((0, 0, z0 + 0.004 + 0.006)), (d * 0.85, d * 0.85, 0.012), R, bevel=0.0018, seg=3), H))
        parts.append(sw(ck.rbox(R @ Vector((0, d * 0.26, z0 + H + 0.0001)), (0.0013, d * 0.28, 0.0004), R, bevel=0), "white"))
    elif style == "tee":
        H = 0.008 + 0.018
        parts.append(tex(_cyl((0, 0, z0), Z, r * 0.58, 0.012, seg=24), H))
        prof = [(-r * 0.95, -0.0045), (-r * 0.30, -0.0060), (r * 0.30, -0.0060), (r * 0.95, -0.0045), (r * 0.95, 0.0045),
                (r * 0.30, 0.0060), (-r * 0.30, 0.0060), (-r * 0.95, 0.0045)]
        b = bmesh.new()
        ck.prism_profile(b, prof, Vector((0, 0, z0 + 0.008 + 0.009)), R @ ck.frame(Vector((1, 0, 0)), Z, Vector((0, -1, 0))), 0.012)
        bmesh.ops.recalc_face_normals(b, faces=b.faces[:])
        b2 = ck.modded(b, bevel=0.0020, seg=3, angle=30)
        b.free()
        parts.append(tex(b2, H))
    else:
        h = r * 1.28
        teeth = max(12, int(round(2 * math.pi * r / 0.0030)))
        parts.append(tex(_cyl((0, 0, z0), Z, r * 1.05, h * 0.10, seg=28, r_top=r * 1.02), h))
        parts.append(tex(_gear((0, 0, z0 + h * 0.10), Z, r * 0.99, h * 0.56, teeth, r * 0.085, r_top=r * 0.93), h))
        b = _cyl((0, 0, z0 + h * 0.66), Z, r * 0.86, h * 0.34, seg=28, r_top=r * 0.68)
        b2 = ck.modded(b, bevel=r * 0.07, seg=2, angle=40)
        b.free()
        parts.append(tex(b2, h))
        top = z0 + h + 0.0002
        parts.append(sw(ck.rbox(R @ Vector((0, r * 0.36, top)), (0.0013, r * 0.60, 0.0004), R, bevel=0), "white"))
        sl = Vector((0, r * 0.18, -h * 0.34)).normalized()
        nrm = Vector((0, h * 0.34, r * 0.18)).normalized()
        Fs = R @ ck.frame(Vector((1, 0, 0)), -sl, nrm)
        parts.append(sw(ck.rbox(R @ (Vector((0, r * 0.77, z0 + h * 0.83)) + nrm * 0.0003), (0.0013, h * 0.30, 0.0004), Fs, bevel=0), "white"))
        if style == "pointer":
            parts.append(tex(ck.rbox(Vector((0, 0, top + 0.0033)), (r * 0.46, r * 2.2, 0.0070), R, bevel=0.0016, seg=3), h + 0.0072))
            parts.append(sw(ck.rbox(R @ Vector((0, r * 0.75, top + 0.0070)), (0.0013, r * 0.62, 0.0004), R, bevel=0), "white"))
    return ck.merge(parts)


def paint_cell(name, h, w, seed=0):
    import numpy as np
    from scipy import ndimage as ndi
    rng = np.random.default_rng(1234 + seed + sum(ord(c) for c in name))
    V = np.broadcast_to(np.linspace(1.0, 0.0, h, dtype=np.float32)[:, None], (h, w)).copy()

    def nz(su, sv):
        a = ndi.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), (sv, su), mode="wrap")
        return a / max(a.std(), 1e-6)
    fine, mid, big = nz(1.2, 0.7), nz(7.0, 3.5), nz(26.0, 14.0)
    if name == "lever":
        paint = np.array([0.215, 0.220, 0.226], np.float32)
        bare = np.array([0.560, 0.560, 0.550], np.float32)
        primer = np.array([0.560, 0.520, 0.300], np.float32)
        base = paint[None, None, :] * (1 + 0.035 * big + 0.02 * mid + 0.012 * fine)[..., None]
        foot = np.clip(1 - V / 0.22, 0, 1)
        base *= (1 - 0.42 * foot ** 0.8)[..., None]
        tip = np.clip((V - 0.72) / 0.28, 0, 1)
        thr = 3.05 - 1.75 * tip ** 1.5
        chip = np.clip((nz(13.0, 6.5) + 0.40 * fine - thr) * 2.6, 0, 1)
        pr = np.clip((nz(15.0, 8.0) + 0.3 * fine - 3.0 + 1.6 * tip) * 3.0, 0, 1) * (1 - chip)
        base += (primer - base) * (0.45 * pr)[..., None]
        base += (bare - base) * chip[..., None]
        rub = np.clip(1 - np.abs(V - 0.80) / 0.16, 0, 1) * np.clip(0.6 + 0.4 * big, 0, 1)
        base *= (1 + 0.07 * rub * (1 - chip))[..., None]
        sc = np.clip((ndi.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), (9.0, 0.6), mode="wrap") * 9 - 1.9), 0, 1)
        base *= (1 + 0.10 * sc)[..., None]
        metal = 0.15 + 0.55 * chip
        smooth = 0.40 + 0.26 * chip + 0.10 * rub - 0.14 * foot + 0.02 * fine
        height = 0.5 - 0.10 * chip - 0.04 * pr + 0.02 * fine
    elif name == "knob":
        paint = np.array([0.300, 0.308, 0.316], np.float32)
        base = paint[None, None, :] * (1 + 0.04 * big + 0.025 * mid + 0.012 * fine)[..., None]
        foot = np.clip(1 - V / 0.14, 0, 1)
        base *= (1 - 0.35 * foot)[..., None]
        rim = np.clip(1 - np.abs(V - 0.66) / 0.05, 0, 1) + 0.8 * np.clip(1 - np.abs(V - 0.97) / 0.05, 0, 1)
        wear = np.clip(rim * (0.75 + 0.5 * mid), 0, 1)
        base += (np.array([0.50, 0.505, 0.51], np.float32) - base) * (0.55 * wear)[..., None]
        chip = np.clip((mid + 0.5 * fine - 2.05) * 2.6, 0, 1) * (V > 0.1)
        base += (np.array([0.60, 0.60, 0.59], np.float32) - base) * chip[..., None]
        flute = np.clip(1 - np.abs(V - 0.38) / 0.28, 0, 1)
        base *= (1 - 0.06 * flute * np.clip(0.5 + 0.5 * big, 0, 1))[..., None]
        metal = 0.10 + 0.75 * chip + 0.25 * wear
        smooth = 0.36 + 0.20 * wear + 0.22 * chip - 0.10 * foot + 0.02 * fine
        height = 0.5 - 0.08 * chip + 0.02 * fine
    elif name == "handle":
        paint = np.array([0.150, 0.165, 0.150], np.float32)
        primer = np.array([0.600, 0.545, 0.280], np.float32)
        base = paint[None, None, :] * (1 + 0.06 * big + 0.03 * mid + 0.015 * fine)[..., None]
        ends = np.clip(1 - np.minimum(V, 1 - V) / 0.22, 0, 1)
        thr = 2.05 - 0.75 * ends
        chip = np.clip((nz(11.0, 6.0) + 0.35 * fine - thr) * 2.4, 0, 1)
        bare = np.clip((mid + 0.6 * fine - thr - 0.75) * 3.0, 0, 1)
        base += (primer - base) * (0.9 * chip)[..., None]
        base += (np.array([0.58, 0.58, 0.57], np.float32) - base) * bare[..., None]
        metal = 0.05 + 0.8 * bare
        smooth = 0.34 + 0.10 * chip + 0.25 * bare + 0.02 * fine
        height = 0.5 - 0.06 * chip - 0.08 * bare + 0.02 * fine
    elif name == "steel":
        X = np.broadcast_to(np.arange(w, dtype=np.float32)[None, :], (h, w))
        Y = np.broadcast_to(np.arange(h, dtype=np.float32)[:, None], (h, w))
        p = w / 26.0
        kn = np.abs(np.sin((X + Y) * math.pi / p)) * np.abs(np.sin((X - Y) * math.pi / p))
        dark = np.array([0.115, 0.120, 0.128], np.float32)
        pale = np.array([0.470, 0.475, 0.480], np.float32)
        base = dark[None, None, :] * (0.80 + 0.45 * kn + 0.05 * mid)[..., None]
        crown = np.clip((V - 0.70) / 0.30, 0, 1)
        tipw = np.clip((kn - 0.62 + 0.18 * mid + 0.25 * crown) * 3.0, 0, 1) * np.clip(0.55 + 0.45 * big, 0.15, 1)
        edge = np.clip(1 - np.abs(V - 0.97) / 0.04, 0, 1) * np.clip(0.6 + 0.4 * mid, 0, 1)
        wear = np.clip(tipw + edge, 0, 1)
        base += (pale - base) * (0.75 * wear)[..., None]
        foot = np.clip(1 - V / 0.12, 0, 1)
        base *= (1 - 0.35 * foot)[..., None]
        metal = 0.55 + 0.40 * wear
        smooth = 0.34 + 0.26 * wear - 0.10 * foot + 0.02 * fine
        height = 0.40 + 0.22 * kn
    else:
        X = np.broadcast_to(np.arange(w, dtype=np.float32)[None, :], (h, w))
        Y = np.broadcast_to(np.arange(h, dtype=np.float32)[:, None], (h, w))
        p = w / 12.0
        a = np.sin((X + Y) * 2 * math.pi / p)
        b_ = np.sin((X - Y) * 2 * math.pi / p)
        wv = np.where(((np.floor((X + Y) / p) + np.floor((X - Y) / p)) % 2) > 0, np.abs(a), np.abs(b_))
        col = np.array([0.34, 0.345, 0.35], np.float32)
        base = col[None, None, :] * (0.55 + 0.60 * wv + 0.04 * mid)[..., None]
        metal = np.full((h, w), 0.85, np.float32)
        smooth = 0.42 + 0.20 * wv
        height = 0.35 + 0.30 * wv
    return np.clip(base, 0, 1), height.astype(np.float32), np.clip(metal, 0, 1).astype(np.float32), np.clip(smooth, 0.05, 0.9).astype(np.float32)
