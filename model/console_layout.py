import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def _pts(tokens):
    return [tuple(float(v) for v in t.split(",")) for t in tokens]


class Layout:
    def __init__(self, path):
        self.items = []
        self.px0, self.py0, self.z0, self.x0, self.K = 0, 0, 0, 0, 0.001
        self.flip, self.zscale = 1.0, 1.0
        self.nzmin, self.ymax = 0.75, 0.62
        self.plate_col = None
        self.lift = 0.0
        for raw in open(path, encoding="utf-8"):
            t = raw.split("#")[0].split()
            if not t:
                continue
            k = t[0]
            if k not in ("plate", "recess", "line", "label", "key"):
                t = [t[0]] + [v for tok in t[1:] for v in tok.split(",")]
            elif k in ("label", "key") and "," in t[1]:
                t = [t[0]] + t[1].split(",") + t[2:]
            if k == "xform":
                self.px0, self.py0, self.z0, self.x0, self.K = (float(v) for v in t[1:6])
                if len(t) > 6:
                    self.flip = float(t[6])
                if len(t) > 7:
                    self.zscale = float(t[7])
            elif k == "lift":
                self.lift = float(t[1])
            elif k == "platecolour":
                self.plate_col = np.array([float(v) for v in t[1:4]], np.float32)
            elif k == "surface":
                self.nzmin, self.ymax = float(t[1]), float(t[2])
            elif k in ("plate", "recess", "line"):
                self.items.append(dict(kind=k, pts=_pts(t[1:])))
            elif k in ("hazard", "slot", "canopy", "rod", "lever", "guard"):
                it = dict(kind=k, x0=float(t[1]), y0=float(t[2]), x1=float(t[3]), y1=float(t[4]))
                if k == "hazard":
                    it["style"] = t[5] if len(t) > 5 else "yb"
                elif k in ("rod", "lever") and len(t) == 3:
                    pass
                self.items.append(it)
            elif k == "screw":
                self.items.append(dict(kind=k, x=float(t[1]), y=float(t[2])))
            elif k == "label":
                self.items.append(dict(kind=k, x=float(t[1]), y=float(t[2]), text=t[3].replace("_", " "),
                                       cap=float(t[4]) / 1000 if len(t) > 4 else 0.0022))
            elif k == "toggle":
                st_ = [q.split("=", 1)[1] for q in t[3:] if q.startswith("state=")]
                t = [q for q in t if not q.startswith("state=")]
                self.items.append(dict(kind=k, x=float(t[1]), y=float(t[2]), style=t[3] if len(t) > 3 else "bat",
                                       tilt=float(t[4]) if len(t) > 4 else 15.0, state=st_[0] if st_ else None))
            elif k == "knob":
                self.items.append(dict(kind=k, x=float(t[1]), y=float(t[2]), d=float(t[3]) / 1000,
                                       style=t[4] if len(t) > 4 else "plain", ang=float(t[5]) if len(t) > 5 else 0.0))
            elif k == "key":
                self.items.append(dict(kind=k, x=float(t[1]), y=float(t[2]), w=float(t[3]) / 1000, h=float(t[4]) / 1000,
                                       text="" if t[5] == "-" else t[5].replace("_", " "), colour=t[6] if len(t) > 6 else "green"))
            elif k in ("lpcock", "probe", "lamp", "rocker", "pin"):
                self.items.append(dict(kind=k, x=float(t[1]), y=float(t[2])))
            elif k == "drf":
                self.items.append(dict(kind=k, x=float(t[1]), y=float(t[2]), d=float(t[3]) / 1000))
            else:
                raise ValueError("console layout: unknown item " + k)
        xs = [p[0] for it in self.items if "pts" in it for p in it["pts"]]
        ys = [p[1] for it in self.items if "pts" in it for p in it["pts"]]
        self.bounds_px = (min(xs), min(ys), max(xs), max(ys))

    def to_xz(self, px, py):
        return self.x0 + self.flip * (self.py0 - py) * self.K, self.z0 - (px - self.px0) * self.K * self.zscale

    def to_px(self, x, z):
        return self.px0 + (self.z0 - z) / (self.K * self.zscale), self.py0 - (x - self.x0) / (self.K * self.flip)

    def region(self):
        a = self.to_xz(self.bounds_px[0], self.bounds_px[3])
        b = self.to_xz(self.bounds_px[2], self.bounds_px[1])
        return min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])


def load(name="console_right.txt"):
    p = os.path.join(HERE, name)
    return Layout(p) if os.path.exists(p) and os.environ.get("NO_CONSOLE_LAYOUT") is None else None


def _sd_poly(X, Y, pts):
    P = np.asarray(pts, np.float64)
    d = np.full(X.shape, np.inf)
    inside = np.zeros(X.shape, bool)
    n = len(P)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        e = b - a
        wx, wy = X - a[0], Y - a[1]
        t = np.clip((wx * e[0] + wy * e[1]) / max(e @ e, 1e-9), 0, 1)
        dx, dy = wx - e[0] * t, wy - e[1] * t
        d = np.minimum(d, dx * dx + dy * dy)
        c1 = (a[1] > Y) != (b[1] > Y)
        xi = (b[0] - a[0]) * (Y - a[1]) / np.where(np.abs(b[1] - a[1]) < 1e-9, 1e-9, b[1] - a[1]) + a[0]
        inside ^= c1 & (X < xi)
    d = np.sqrt(d)
    return np.where(inside, -d, d)


def _d_polyline(X, Y, pts):
    P = np.asarray(pts, np.float64)
    d = np.full(X.shape, np.inf)
    for i in range(len(P) - 1):
        a, b = P[i], P[i + 1]
        e = b - a
        wx, wy = X - a[0], Y - a[1]
        t = np.clip((wx * e[0] + wy * e[1]) / max(e @ e, 1e-9), 0, 1)
        dx, dy = wx - e[0] * t, wy - e[1] * t
        d = np.minimum(d, dx * dx + dy * dy)
    return np.sqrt(d)


def _cov(sd, aa):
    return np.clip(0.5 - sd / aa, 0, 1)


C_PLATE = np.array([0.400, 0.413, 0.428], np.float32)
C_BACK = np.array([0.215, 0.222, 0.232], np.float32)
C_RECESS = np.array([0.295, 0.305, 0.317], np.float32)
C_SEAM = np.array([0.070, 0.072, 0.076], np.float32)
C_WHITE = np.array([0.86, 0.87, 0.84], np.float32)
C_YEL = np.array([0.86, 0.66, 0.06], np.float32)
C_BLK = np.array([0.045, 0.045, 0.05], np.float32)
C_ORA = np.array([0.80, 0.36, 0.14], np.float32)
C_WSTR = np.array([0.82, 0.82, 0.80], np.float32)
C_SLOT = np.array([0.035, 0.036, 0.040], np.float32)


def paint(L, pos, nrm, cover, base, height, smooth, keep, side=1):
    x_u, z_u, y_u = pos[..., 0], pos[..., 1], pos[..., 2]
    xa, xb, za, zb = L.region()
    m = cover & (nrm[..., 2] > L.nzmin) & (x_u * side > xa - 0.004) & (x_u * side < xb + 0.02) & (z_u > za - 0.003) & (z_u < zb + 0.003) & (y_u < L.ymax)
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        print("console layout: no texels")
        return []
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = (slice(y0, y1), slice(x0, x1))
    M = m[sub]
    PX, PY = L.to_px(x_u[sub] * side, z_u[sub])
    aa = 1.0 / max(np.median(np.abs(np.gradient(PX, axis=1)[M]) + np.abs(np.gradient(PX, axis=0)[M])), 1e-3)
    aa = max(min(aa, 3.0), 0.3)
    b = base[sub].copy(); h = height[sub].copy(); s = smooth[sub].copy()
    b[M] = C_BACK; h[M] = 0.42; s[M] = 0.30
    mm_px = 0.001 / L.K
    rng = np.random.default_rng(7)
    import panelkit as pk
    tppm = float(np.clip(mm_px / max(np.median(np.abs(np.gradient(PX, axis=1)[M]) + np.abs(np.gradient(PX, axis=0)[M])), 1e-3), 1.5, 8.0))
    KH = tppm / 3.0
    Xmm, Ymm = (PX / mm_px).astype(np.float32), (PY / mm_px).astype(np.float32)
    esd = np.full(PX.shape, 9.0, np.float32)
    platem = np.zeros(PX.shape, np.float32)

    def put(c, col=None, hv=None, sv=None):
        c = c * M
        if col is not None:
            b[...] = b + (np.asarray(col, np.float32) - b) * c[..., None]
        if hv is not None:
            h[...] = h + (hv - h) * c
        if sv is not None:
            s[...] = s + (sv - s) * c

    screws = []
    for it in L.items:
        k = it["kind"]
        if k in ("plate", "recess"):
            sd = _sd_poly(PX, PY, it["pts"])
            if k == "plate":
                put(_cov(sd + 0.5 * mm_px, aa), C_SEAM, 0.34, 0.2)
                shade = 1.0 + rng.uniform(-0.03, 0.03)
                cp_ = _cov(sd + 1.2 * mm_px, aa)
                put(cp_, (L.plate_col if L.plate_col is not None else C_PLATE) * shade, 0.55, 0.36)
                sd_mm = ((sd + 1.2 * mm_px) / mm_px).astype(np.float32)
                esd = np.where(cp_ > 0.5, sd_mm, esd)
                platem = np.maximum(platem * (1 - cp_), cp_)
                P = np.asarray(it["pts"], np.float64)
                cen = P.mean(0)
                for p in P:
                    v = cen - p
                    v /= max(np.linalg.norm(v), 1e-6)
                    screws.append(p + v * 6.5 * mm_px * 1.4)
            else:
                put(_cov(sd, aa), C_SEAM, 0.30, 0.2)
                cr_ = _cov(sd + 1.0 * mm_px, aa)
                put(cr_, C_RECESS, 0.38, 0.28)
                esd = np.where(cr_ > 0.5, -9.0, esd)
                platem = platem * (1 - cr_)
                b[...] = b * (1 - 0.30 * np.clip(1 + (sd + 1.0 * mm_px) / (4.0 * mm_px), 0, 1) * cr_ * M)[..., None]
        elif k == "hazard":
            sd = _sd_poly(PX, PY, [(it["x0"], it["y0"]), (it["x1"], it["y0"]), (it["x1"], it["y1"]), (it["x0"], it["y1"])])
            per = 7.0 * mm_px
            ph = (PX + PY) / per
            tri = np.abs(ph - np.floor(ph) - 0.5) * 2
            st = np.clip((tri - 0.5) * per / aa * 0.5 + 0.5, 0, 1)[..., None]
            a_, b_ = (C_YEL, C_BLK) if it["style"] == "yb" else (C_ORA, C_WSTR)
            col = st * a_ + (1 - st) * b_
            c = _cov(sd + 0.3 * mm_px, aa) * M
            b[...] = b + (col - b) * c[..., None]
            h[...] = h + (0.56 - h) * c
            s[...] = s + (0.40 - s) * c
            platem = platem * (1 - 0.6 * c)
            if it["style"] != "yb":
                for p in ((it["x0"], it["y0"]), (it["x1"], it["y0"]), (it["x1"], it["y1"]), (it["x0"], it["y1"])):
                    screws.append(np.array(p) + np.sign(np.array([(it["x0"] + it["x1"]) / 2, (it["y0"] + it["y1"]) / 2]) - np.array(p)) * 5 * mm_px)
        elif k == "guard":
            sd = _sd_poly(PX, PY, [(it["x0"], it["y0"]), (it["x1"], it["y0"]), (it["x1"], it["y1"]), (it["x0"], it["y1"])])
            put(_cov(sd, aa), C_SLOT, 0.2, 0.2)
        elif k == "slot":
            sd = _sd_poly(PX, PY, [(it["x0"], it["y0"]), (it["x1"], it["y0"]), (it["x1"], it["y1"]), (it["x0"], it["y1"])])
            put(_cov(sd, aa), C_SEAM, 0.30)
            put(_cov(sd + 1.0 * mm_px, aa), C_SLOT, 0.12, 0.2)
        elif k == "screw":
            screws.append(np.array([it["x"], it["y"]]))
    try:
        bump = np.zeros(PX.shape, np.float32)
        s0 = s.copy()
        seed = 100 + int(abs(L.x0) * 1000) % 50 + (0 if side > 0 else 7)
        sc = pk.scratches(PX.shape, tppm, 15.0, seed + 3)
        pk.paint_finish(b, bump, s, tppm, seed, platem * M, 1.0, sc, gain=1.25)
        pk.edge_wear(b, bump, s, tppm, esd, seed + 9, 1.7, platem * M, hl=0.30, bw=0.42, chamfer=(0.25, 0.9))
        b[...] = b * (1 - 0.07 * np.clip(1 + esd / 3.5, 0, 1) * (esd < 0) * platem * M)[..., None]
        ctl = np.full(PX.shape, 99.0, np.float32)
        for it in L.items:
            if it["kind"] in ("toggle", "knob", "key", "lpcock", "probe", "rocker", "lamp"):
                rr = {"toggle": 6.0, "key": 0.75 * max(it.get("w", 0.012), it.get("h", 0.012)) * 1000, "lpcock": 9.0, "probe": 9.0,
                      "rocker": 10.0, "lamp": 5.0}.get(it["kind"], 0.0) or it.get("d", 0.02) * 1000 * 0.58
                ctl = np.minimum(ctl, np.hypot(Xmm - it["x"] / mm_px, Ymm - it["y"] / mm_px) - rr)
        contact = np.clip(1 - ctl / 2.6, 0, 1) ** 1.6
        b[...] = b * (1 - 0.16 * contact * M)[..., None]
        rub = np.clip(1 - np.abs(ctl - 7.0) / 6.0, 0, 1) * np.clip(0.55 + 0.45 * pk.noise(PX.shape, 5.0 * tppm, seed + 20), 0, 1)
        b[...] = b * (1 + 0.045 * rub * platem * M)[..., None]
        s[...] = s + 0.10 * rub * platem * M
        s[...] = np.where(M, np.clip(s, 0.12, 0.62), s0)
        h[...] = h + bump * KH * M
    except Exception as e:
        print("console layout: finish skipped:", e)
    for it in L.items:
        if it["kind"] == "line":
            d = _d_polyline(PX, PY, it["pts"])
            put(_cov(d - 0.35 * mm_px, aa), C_WHITE, 0.50, 0.35)
    def _put2(c, col, bmp, sv):
        c = c * M
        if col is not None:
            b[...] = b + (np.asarray(col, np.float32) - b) * c[..., None]
        if bmp is not None:
            h[...] = h + bmp * KH * c
        if sv is not None:
            s[...] = s + (sv - s) * c
    for p in screws:
        pk.paint_screw(_put2, Xmm, Ymm, p[0] / mm_px, p[1] / mm_px, 2.4, lambda sd_: np.clip(0.5 - sd_ * tppm, 0, 1), "cross",
                       rng.uniform(0, math.pi), pk.STEEL * 0.95)
    base[sub][M] = b[M]
    height[sub][M] = h[M]
    smooth[sub][M] = s[M]
    keep[sub][M] = 1.0
    labels = []
    lab_items = [it for it in L.items if it["kind"] == "label"]
    for it in L.items:
        if it["kind"] == "key" and it["text"]:
            col = {"green": [0.45, 1.0, 0.5], "blue": [0.75, 0.85, 1.0]}.get(it["colour"], [0.9, 0.9, 0.86])
            lab_items.append(dict(kind="label", x=it["x"], y=it["y"], text=it["text"], cap=min(it["w"], it["h"]) * 0.30, col=col))
    for it in lab_items:
        x, z = L.to_xz(it["x"], it["y"])
        q = np.array([x * side, z])
        d = (pos[..., 0] - q[0]) ** 2 + (pos[..., 1] - q[1]) ** 2
        d[~m] = 9
        iy, ix = np.unravel_index(np.argmin(d), d.shape)
        if d[iy, ix] > 0.003 ** 2:
            continue
        n = nrm[iy, ix].astype(np.float64) / 127.0 if nrm.dtype != np.float32 else nrm[iy, ix].astype(np.float64)
        n /= max(np.linalg.norm(n), 1e-9)
        r_ = np.array([1.0, 0, 0]) - n * n[0]
        r_ /= np.linalg.norm(r_)
        u_ = np.cross(n, r_)
        p3 = pos[iy, ix].astype(np.float64)
        p3[0], p3[1] = q[0], q[1]
        labels.append({"pos": [float(v) for v in p3], "r": [float(v) for v in r_], "u": [float(v) for v in u_],
                       "n": [float(v) for v in n], "text": it["text"], "cap": float(it["cap"]), "font": "FONT",
                       "spacing": 1.35, "col": it.get("col", [0.89, 0.90, 0.86]), "seen": True})
    print(f"console layout painted: {int(M.sum())} texels, {len(screws)} screws, {len(labels)} labels")
    return labels


KNOB_SCALE = 0.85
def build(L, surf, local_frame, sw, place, ck, side=1):
    import bmesh
    from mathutils import Matrix, Vector
    out, ctrl = [], []
    K = L.K

    def at(px, py):
        x, z = L.to_xz(px, py)
        h = surf(x * side, z)
        lf = getattr(L, "lift_fn", None)
        lift = L.lift + (lf(px, py) if lf is not None else 0.0)
        if h is not None and lift:
            h = (Vector(h[0]) + Vector(h[1]).normalized() * lift, h[1])
        return h

    def cyl(base, axis, r, h, col, seg=16, r_top=None):
        b = bmesh.new()
        ck.cylinder(b, Vector(base), Vector(axis), r, h, seg=seg, r_top=r_top)
        return sw(b, col)

    def sphere(c, r, col, sx=1.0, sy=1.0, sz=1.0):
        b = bmesh.new()
        bmesh.ops.create_uvsphere(b, u_segments=12, v_segments=8, radius=r,
                                  matrix=Matrix.Translation(Vector(c)) @ Matrix.Diagonal((sx, sy, sz, 1.0)))
        return sw(b, col)

    import ctl_parts

    def toggle(style, tilt):
        return ctl_parts.toggle(sw, style if style in ("yellow", "bat", "pyramid", "cube") else "long", lean=tilt, lean_dir=90.0)

    def knob(d, style, ang):
        return ctl_parts.knob(sw, d, style, ang)

    def key(w, h, colour):
        parts = [sw(ck.rbox(Vector((0, 0, 0.0012)), (w + 0.004, h + 0.004, 0.0024), bevel=0.0007, seg=1), "black"),
                 sw(ck.rbox(Vector((0, 0, 0.0038)), (w, h, 0.0040), bevel=0.0009, seg=2), "darkgrey"),
                 sw(ck.rbox(Vector((0, 0, 0.0059)), (w * 0.80, h * 0.80, 0.0004), bevel=0), {"blue": "keyblue", "red": "red"}.get(colour, "black"))]
        return ck.merge(parts)

    n = 0
    for it in L.items:
        k = it["kind"]
        if k in ("toggle", "knob", "key", "lpcock", "probe", "lamp", "rocker", "drf", "pin"):
            hit = at(it["x"], it["y"])
            if hit is None:
                print("  console layout: off the console:", k, it["x"], it["y"])
                continue
            pos, nrm = hit
            F = local_frame(nrm)
            if k == "toggle" and it.get("state"):
                st_ = it["style"] if it["style"] in ("yellow", "bat", "pyramid", "cube") else "long"
                fx_, lv_, pv_ = ctl_parts.toggle(sw, st_, split=True)
                out.append(place(fx_, pos, F))
                place(lv_, pos, F)
                piv = Vector(pos) + F.col[2] * 0.0004 + F @ pv_
                L.moving = getattr(L, "moving", []) + [(it["state"], lv_, piv, Vector(F.col[0]), abs(it["tilt"]) or 15.0)]
                rad = 0.008
            elif k == "toggle":
                out.append(place(toggle(it["style"], it["tilt"]), pos, F)); rad = 0.008
            elif k == "knob":
                dk = it["d"] * KNOB_SCALE
                out.append(place(knob(dk, it["style"], it["ang"]), pos, F)); rad = dk * 0.65 + 0.002
            elif k == "key":
                out.append(place(key(it["w"], it["h"], it["colour"]), pos, F)); rad = max(it["w"], it["h"]) * 0.75
            elif k == "lpcock":
                b = bmesh.new()
                prof = [(-0.009, -0.006), (0.009, -0.006), (0.011, 0.010), (-0.011, 0.010)]
                ck.prism_profile(b, prof, Vector((0, -0.004, 0.017)), ck.frame(Vector((1, 0, 0)), Vector((0, 0.34, 0.94)).normalized(), Vector((0, -0.94, 0.34))), 0.014)
                bmesh.ops.recalc_face_normals(b, faces=b.faces[:])
                parts = [sw(ck.modded(b, bevel=0.0022, seg=2, angle=30), "orange"),
                         cyl((0, 0, 0), (0, -0.2, 1), 0.0030, 0.012, "metal"),
                         cyl((0, 0, 0), (0, 0, 1), 0.0060, 0.0025, "metal", seg=6)]
                out.append(place(ck.merge(parts), pos, F)); rad = 0.014
            elif k == "drf":
                d = it["d"]
                parts = [cyl((0, 0, 0), (0, 0, 1), d * 0.92, 0.0016, "black", seg=40)]
                nseg, r0, r1 = 16, d * 0.50, d * 0.86
                for k2 in range(nseg):
                    a0, a1 = 2 * math.pi * k2 / nseg, 2 * math.pi * (k2 + 1) / nseg
                    b = bmesh.new()
                    ck.prism_profile(b, [(r0 * math.cos(a0), r0 * math.sin(a0)), (r1 * math.cos(a0), r1 * math.sin(a0)),
                                         (r1 * math.cos((a0 + a1) / 2), r1 * math.sin((a0 + a1) / 2)), (r1 * math.cos(a1), r1 * math.sin(a1)),
                                         (r0 * math.cos(a1), r0 * math.sin(a1))], Vector((0, 0, 0.0020)), Matrix.Identity(3), 0.0040)
                    bmesh.ops.recalc_face_normals(b, faces=b.faces[:])
                    parts.append(sw(b, "yellow" if k2 % 2 == 0 else "black"))
                parts.append(sw(ck.rbox(Vector((0, 0, 0.0035)), (d * 0.66, d * 0.66, 0.0070), bevel=0.0012, seg=2), "black"))
                parts.append(sw(ck.rbox(Vector((0, 0, 0.0060)), (d * 0.46, d * 0.46, 0.0060), bevel=0.0012, seg=2), "darkgrey"))
                out.append(place(ck.merge(parts), pos, F)); rad = d
            elif k == "pin":
                parts = [cyl((0, 0, 0), (0, 0, 1), 0.0060, 0.012, "metal", seg=14),
                         cyl((0, 0, 0.012), (0, 0, 1), 0.0035, 0.030, "metal", seg=12),
                         cyl((0, 0, 0.042), (0, 0, 1), 0.0048, 0.008, "darkgrey", seg=12),
                         sw(ck.rbox(Vector((0.0, 0.016, 0.060)), (0.004, 0.030, 0.016), bevel=0.001, seg=1), "red"),
                         cyl((0, 0.000, 0.050), (0, 1, 0.6), 0.0008, 0.012, "chrome", seg=6)]
                out.append(place(ck.merge(parts), pos, F)); rad = 0.008
            elif k == "lamp":
                parts = [cyl((0, 0, 0), (0, 0, 1), 0.0052, 0.0030, "black", seg=16),
                         sphere((0, 0, 0.0030), 0.0038, "green", sz=0.55)]
                out.append(place(ck.merge(parts), pos, F)); rad = 0.006
            elif k == "rocker":
                parts = [sw(ck.rbox(Vector((0, 0, 0.0025)), (0.016, 0.026, 0.005), bevel=0.0012, seg=1), "black"),
                         sw(ck.rbox(Vector((0, 0.003, 0.0065)), (0.010, 0.012, 0.004), bevel=0.0015, seg=2), "darkgrey"),
                         sw(ck.rbox(Vector((0, -0.006, 0.0058)), (0.010, 0.008, 0.003), bevel=0.0012, seg=2), "darkgrey")]
                out.append(place(ck.merge(parts), pos, F)); rad = 0.014
            elif k == "probe":
                parts = [toggle("long", -15),
                         sw(ck.rbox(Vector((-0.012, 0.000, 0.012)), (0.006, 0.026, 0.024), bevel=0.0015, seg=2), "darkgrey"),
                         sw(ck.rbox(Vector((-0.003, 0.000, 0.0255)), (0.024, 0.026, 0.005), bevel=0.0015, seg=2), "darkgrey")]
                out.append(place(ck.merge(parts), pos, F)); rad = 0.016
            ctrl.append(("rc_" + k, np.array(pos), np.array(F.col[0]), np.array(F.col[1]), np.array(F.col[2]), rad))
            n += 1
        elif k == "guard":
            c = at((it["x0"] + it["x1"]) / 2, (it["y0"] + it["y1"]) / 2)
            if c is None:
                continue
            pos, nrm = c
            F = local_frame(nrm)
            Lf = abs(it["x1"] - it["x0"]) * K
            W = abs(it["y1"] - it["y0"]) * K
            t_, hgt = 0.0035, 0.013
            parts = []
            k2 = 0
            for (cx_, cy_, sx_, sy_) in ((0, Lf / 2 - t_ / 2, W, t_), (0, -Lf / 2 + t_ / 2, W, t_), (W / 2 - t_ / 2, 0, t_, Lf), (-W / 2 + t_ / 2, 0, t_, Lf)):
                n_seg = 4
                for j in range(n_seg):
                    f0, f1 = -0.5 + j / n_seg, -0.5 + (j + 1) / n_seg
                    if sx_ > sy_:
                        cc, ss = Vector((cx_ + (f0 + f1) / 2 * sx_, cy_, hgt / 2)), (sx_ / n_seg, sy_, hgt)
                    else:
                        cc, ss = Vector((cx_, cy_ + (f0 + f1) / 2 * sy_, hgt / 2)), (sx_, sy_ / n_seg, hgt)
                    parts.append(sw(ck.rbox(cc, ss, bevel=0), "yellow" if k2 % 2 == 0 else "black"))
                    k2 += 1
            parts.append(sw(ck.rbox(Vector((0, 0, 0.004)), (W * 0.5, Lf * 0.5, 0.008), bevel=0.0012, seg=2), "darkgrey"))
            parts.append(sw(ck.rbox(Vector((0, 0, 0.0082)), (W * 0.38, Lf * 0.38, 0.0004), bevel=0), "red"))
            out.append(place(ck.merge(parts), pos, F))
            ctrl.append(("rc_guard", np.array(pos), np.array(F.col[0]), np.array(F.col[1]), np.array(F.col[2]), max(W, Lf) / 2))
        elif k == "canopy":
            c = at((it["x0"] + it["x1"]) / 2, (it["y0"] + it["y1"]) / 2)
            if c is None:
                continue
            pos, nrm = c
            F = local_frame(nrm)
            Lf = abs(it["x1"] - it["x0"]) * K
            W = abs(it["y1"] - it["y0"]) * K
            parts = [sw(ck.rbox(Vector((0, 0, 0.0015)), (W, Lf, 0.003), bevel=0.0008, seg=1), "boxgrey"),
                     sw(ck.rbox(Vector((-W * 0.18, 0, 0.013)), (W * 0.42, Lf * 0.86, 0.020), bevel=0.003, seg=2), "boxgrey"),
                     sw(ck.rbox(Vector((-W * 0.18, -Lf * 0.05, 0.0232)), (W * 0.16, Lf * 0.50, 0.0006), bevel=0), "black"),
                     sw(ck.rbox(Vector((-W * 0.18, Lf * 0.36, 0.0245)), (W * 0.30, Lf * 0.10, 0.004), bevel=0.0012, seg=1), "metal")]
            for yy in (-Lf * 0.30, Lf * 0.20):
                parts.append(cyl((-W * 0.18, yy, 0.023), (0, 0, 1), 0.0028, 0.010, "metal", seg=10))
            parts.append(sw(ck.rbox(Vector((-W * 0.18, -Lf * 0.05, 0.035)), (0.011, Lf * 0.62, 0.007), bevel=0.0025, seg=2), "darkgrey"))
            for sx_ in (-1, 1):
                for sy_ in (-1, 1):
                    parts.append(cyl((sx_ * (W / 2 - 0.006), sy_ * (Lf / 2 - 0.006), 0.003), (0, 0, 1), 0.0026, 0.0008, "darkgrey", seg=10))
            for k2 in range(9):
                parts.append(cyl((W * 0.12, -Lf * 0.12 + k2 * 0.0026, 0.008), (0, 1, 0), 0.0028, 0.0012, "metal", seg=8))
            parts.append(cyl((W * 0.12, -Lf * 0.30, 0.008), (0, 1, 0), 0.0014, Lf * 0.42, "metal", seg=8))
            out.append(place(ck.merge(parts), pos, F))
            ctrl.append(("rc_canopy", np.array(pos), np.array(F.col[0]), np.array(F.col[1]), np.array(F.col[2]), max(W, Lf) / 2))
        elif k in ("rod", "lever"):
            a = at(it["x0"], it["y0"]); b_ = at(it["x1"], it["y1"])
            if a is None or b_ is None:
                continue
            pa, na = a; pb, nb = b_
            up = (Vector(na) + Vector(nb)).normalized()
            hgt = 0.020 if k == "rod" else 0.017
            A, B = Vector(pa) + up * hgt, Vector(pb) + up * hgt
            d = (B - A)
            parts = []
            if k == "rod":
                parts.append(ctl_parts.uv_axis(ctl_parts._cyl(A - d.normalized() * 0.004, d, 0.0035, d.length + 0.008, seg=14), "lever",
                                               A - d.normalized() * 0.004, d, d.length + 0.008, 0.30, 0.78))
                for P_, n_ in ((pa, na), (pb, nb)):
                    Fq = local_frame(n_)
                    parts.append(place(sw(ck.rbox(Vector((0, 0, hgt / 2)), (0.010, 0.012, hgt + 0.004), bevel=0.0015, seg=1), "darkgrey"), Vector(P_), Fq, lift=0.0))
                    parts.append(place(cyl((0, 0, hgt), (1, 0, 0), 0.0055, 0.004, "metal", seg=12), Vector(P_) + Vector((-0.002, 0, 0)), Fq, lift=0.0))
            else:
                ex = d.normalized()
                ez = up
                ey = ez.cross(ex).normalized()
                Fb = ck.frame(ex, ey, ez)
                parts.append(ctl_parts.uv_axis(ck.rbox((A + B) / 2, (d.length, 0.006, 0.004), Fb, bevel=0.001, seg=1), "lever", A, ex, d.length, 0.30, 0.78))
                parts.append(ctl_parts.uv_axis(ck.rbox(B - ex * 0.020 + ez * 0.003, (0.044, 0.0145, 0.0125), Fb, bevel=0.0048, seg=3), "handle",
                                               B - ex * 0.042 + ez * 0.003, ex, 0.044))
                parts.append(sw(ck.rbox(Vector(pa) + ez * 0.009, (0.012, 0.012, 0.018), Fb, bevel=0.0015, seg=1), "darkgrey"))
                parts.append(cyl(Vector(pa) + ez * 0.012 - ey * 0.009, ey, 0.004, 0.018, "metal", seg=12))
            out.append(ck.merge(parts))
            mid = (Vector(pa) + Vector(pb)) / 2
            ctrl.append(("rc_" + k, np.array(mid), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array(up), d.length / 2))
    print(f"console layout: {n} controls built")
    return out, ctrl
