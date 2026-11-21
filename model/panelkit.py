import math
import os

import numpy as np

GREY = np.array([0.43, 0.445, 0.46], np.float32)
GREY_D = np.array([0.385, 0.398, 0.412], np.float32)
DARK = np.array([0.150, 0.155, 0.163], np.float32)
PANEL_DARK = np.array([0.228, 0.234, 0.240], np.float32)
BLACK = np.array([0.045, 0.046, 0.050], np.float32)
WHITE = np.array([0.86, 0.87, 0.84], np.float32)
YEL = np.array([0.86, 0.66, 0.06], np.float32)
PRIMER = np.array([0.60, 0.61, 0.60], np.float32)
STEEL = np.array([0.46, 0.47, 0.48], np.float32)


def b_(v):
    v = np.asarray(v, float)
    return np.array([v[0], v[2], v[1]])


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


class Frame:

    def __init__(self, O_u, X_u, Y_u, top=0.004):
        X_u = _unit(X_u)
        Y_u = np.asarray(Y_u, float)
        Y_u = _unit(Y_u - X_u * (Y_u @ X_u))
        self.O_u, self.X_u, self.Y_u = np.asarray(O_u, float), X_u, Y_u
        self.O, self.X, self.Y = b_(O_u), b_(X_u), b_(Y_u)
        self.N = np.cross(self.X, self.Y)
        self.N_u = b_(self.N)
        self.top = top

    def pt(self, x, y, z=0.0):
        return self.O + self.X * (x / 1000.0) + self.Y * (y / 1000.0) + self.N * (self.top + z / 1000.0)

    def local(self, p):
        d = np.asarray(p, float) - self.O
        return d @ self.X * 1000.0, d @ self.Y * 1000.0, d @ self.N * 1000.0

    def local_u(self, P):
        d = np.asarray(P, float) - self.O_u
        return d @ self.X_u * 1000.0, d @ self.Y_u * 1000.0, d @ self.N_u * 1000.0

    def label(self, text, x, y, cap, z=0.0, col=None, ang=0.0, spacing=1.35):
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        r = self.X * ca + self.Y * sa
        u = -self.X * sa + self.Y * ca
        return {"pos": [float(v) for v in self.pt(x, y, z)], "r": [float(v) for v in r], "u": [float(v) for v in u],
                "n": [float(v) for v in self.N], "text": text, "cap": cap / 1000.0, "font": "FONT", "spacing": spacing,
                "col": list(col) if col is not None else [0.89, 0.90, 0.86], "seen": True}


def rrect_pts(cx, cy, w, h, r, ang=0.0, n=6):
    r = min(r, w / 2 - 1e-3, h / 2 - 1e-3)
    pts = []
    for sx, sy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        for k in range(n + 1):
            a = math.radians(a0 + 90.0 * k / n)
            pts.append((sx * (w / 2 - r) + r * math.cos(a), sy * (h / 2 - r) + r * math.sin(a)))
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]


def circle_pts(cx, cy, r, n=40, a0=0.0):
    return [(cx + r * math.cos(a0 + 2 * math.pi * k / n), cy + r * math.sin(a0 + 2 * math.pi * k / n)) for k in range(n)]


def round_poly(pts, r, n=4):
    P = [np.asarray(p, float) for p in pts]
    out = []
    m = len(P)
    for i in range(m):
        a, b, c = P[i - 1], P[i], P[(i + 1) % m]
        u, v = _unit(a - b), _unit(c - b)
        ang = math.acos(max(-1.0, min(1.0, float(u @ v))))
        d = min(r / math.tan(ang / 2), 0.45 * np.linalg.norm(a - b), 0.45 * np.linalg.norm(c - b))
        p0, p1 = b + u * d, b + v * d
        for k in range(n + 1):
            t = k / n
            q = (1 - t) ** 2 * p0 + 2 * t * (1 - t) * b + t * t * p1
            out.append((float(q[0]), float(q[1])))
    return out


def inset_poly(pts, d):
    P = np.asarray(pts, float)
    area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
    sgn = 1.0 if area > 0 else -1.0
    n = len(P)
    out = []
    for i in range(n):
        a, b, c = P[i - 1], P[i], P[(i + 1) % n]
        e1, e2 = _unit(b - a), _unit(c - b)
        n1, n2 = sgn * np.array([-e1[1], e1[0]]), sgn * np.array([-e2[1], e2[0]])
        q = b + (n1 + n2) * d / max(1.0 + float(n1 @ n2), 0.2)
        out.append((float(q[0]), float(q[1])))
    return out


def sd_poly(X, Y, pts):
    P = np.asarray(pts, np.float64)
    d = np.full(X.shape, np.inf, np.float64)
    inside = np.zeros(X.shape, bool)
    n = len(P)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        e = b - a
        wx, wy = X - a[0], Y - a[1]
        t = np.clip((wx * e[0] + wy * e[1]) / max(e @ e, 1e-12), 0, 1)
        dx, dy = wx - e[0] * t, wy - e[1] * t
        d = np.minimum(d, dx * dx + dy * dy)
        c1 = (a[1] > Y) != (b[1] > Y)
        xi = (b[0] - a[0]) * (Y - a[1]) / np.where(np.abs(b[1] - a[1]) < 1e-12, 1e-12, b[1] - a[1]) + a[0]
        inside ^= c1 & (X < xi)
    d = np.sqrt(d)
    return np.where(inside, -d, d).astype(np.float32)


def sd_rrect(X, Y, cx, cy, w, h, r=0.0, ang=0.0):
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    x, y = X - cx, Y - cy
    u, v = np.abs(x * ca + y * sa) - (w / 2 - r), np.abs(-x * sa + y * ca) - (h / 2 - r)
    return (np.hypot(np.maximum(u, 0), np.maximum(v, 0)) + np.minimum(np.maximum(u, v), 0) - r).astype(np.float32)


def sd_circle(X, Y, cx, cy, r):
    return (np.hypot(X - cx, Y - cy) - r).astype(np.float32)


def sd_seg(X, Y, x0, y0, x1, y1):
    e = np.array([x1 - x0, y1 - y0], float)
    wx, wy = X - x0, Y - y0
    t = np.clip((wx * e[0] + wy * e[1]) / max(e @ e, 1e-12), 0, 1)
    return np.hypot(wx - e[0] * t, wy - e[1] * t).astype(np.float32)


def noise(shape, sigma, seed):
    from scipy import ndimage as ndi
    if sigma > 8.0:
        import cv2
        f = max(int(sigma / 3.0), 2)
        small = (max(shape[0] // f, 2), max(shape[1] // f, 2))
        r = ndi.gaussian_filter(np.random.default_rng(seed).standard_normal(small).astype(np.float32), sigma / f)
        r = cv2.resize(r, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)
        return r / max(float(r.std()), 1e-6)
    r = np.random.default_rng(seed).standard_normal(shape).astype(np.float32)
    if sigma > 0.3:
        r = ndi.gaussian_filter(r, sigma)
    return r / max(float(r.std()), 1e-6)


def scratches(shape, ppm, per_dm2=14.0, seed=5, long_frac=0.25):
    import cv2
    H, W = shape
    rng = np.random.default_rng(seed)
    area_dm2 = (H / ppm) * (W / ppm) / 1e4
    n = int(per_dm2 * area_dm2)
    S = 2
    im = np.zeros((H * S, W * S), np.uint8)
    for i in range(n):
        x, y = rng.uniform(0, W * S), rng.uniform(0, H * S)
        a = rng.uniform(0, math.pi)
        L = (rng.uniform(14, 55) if rng.random() < long_frac else rng.uniform(2.5, 12)) * ppm * S
        curve = rng.normal(0, 0.08)
        k = max(int(L / (6 * S)), 2)
        pts = []
        for j in range(k + 1):
            t = j / k - 0.5
            aa = a + curve * t * 2
            pts.append((x + math.cos(aa) * L * t, y + math.sin(aa) * L * t))
        v = int(rng.uniform(70, 255))
        cv2.polylines(im, [np.array(pts, np.int32).reshape(-1, 1, 2)], False, v, 1 if rng.random() < 0.8 else 2, cv2.LINE_AA)
    im = cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA)
    return im.astype(np.float32) / 255.0


def hf_ao(h_mm, ppm, strength=1.0):
    from scipy import ndimage as ndi
    occ = np.zeros(h_mm.shape, np.float32)
    for sig, w in ((0.45, 0.30), (1.1, 0.34), (2.6, 0.36), (6.0, 0.34), (13.0, 0.26)):
        sp = sig * ppm
        if sp > 10.0:
            import cv2
            f = max(int(sp / 4.0), 2)
            sm = cv2.resize(h_mm, (max(h_mm.shape[1] // f, 2), max(h_mm.shape[0] // f, 2)), interpolation=cv2.INTER_AREA)
            g = cv2.resize(ndi.gaussian_filter(sm, sp / f, mode="nearest"), (h_mm.shape[1], h_mm.shape[0]), interpolation=cv2.INTER_LINEAR)
        else:
            g = ndi.gaussian_filter(h_mm, sp, mode="nearest")
        occ += w * np.clip((g - h_mm) / (sig * 1.15), 0, 1.6)
    return (1.0 / (1.0 + 1.25 * strength * occ)).astype(np.float32)


def paint_finish(base, bump, smooth, ppm, seed=1, m=None, wear=1.0, scratch_layer=None, gain=1.0):
    sh = base.shape[:2]
    mm = np.ones(sh, np.float32) if m is None else m.astype(np.float32)
    g_f = noise(sh, max(0.11 * ppm, 0.75), seed)
    g_m = noise(sh, 1.6 * ppm, seed + 1)
    g_l = noise(sh, 16.0 * ppm, seed + 2)
    base *= (1 + mm * gain * (0.012 * g_f + 0.010 * g_m + 0.014 * g_l))[..., None]
    base[..., 2] *= 1 + mm * 0.006 * g_l
    bump += mm * 0.005 * g_f
    smooth += mm * (0.012 * g_m - 0.008 * g_l + 0.004 * g_f)
    sc = scratches(sh, ppm, 13.0 * wear, seed + 3) if scratch_layer is None else scratch_layer
    sc = sc * mm * np.clip(0.55 + 0.45 * noise(sh, 9.0 * ppm, seed + 4), 0, 1)
    base *= (1 + 0.11 * gain * sc)[..., None]
    smooth += 0.06 * sc
    bump -= 0.004 * sc
    return sc


def edge_wear(base, bump, smooth, ppm, sd_in, seed=3, wear=1.0, m=None, hl=0.26, bw=0.24, chamfer=(0.10, 0.6)):
    sh = sd_in.shape
    mm = 1.0 if m is None else m
    band = np.clip(1 - np.abs(sd_in + bw) / bw, 0, 1) * mm
    wide = np.clip(1 - np.abs(sd_in + 1.3) / 1.5, 0, 1) * (sd_in < 0) * mm
    base *= (1 + hl * band)[..., None]
    smooth += 0.16 * band
    bump -= chamfer[0] * np.clip(1 + sd_in / chamfer[1], 0, 1) * (sd_in < 0) * mm
    n = noise(sh, 0.28 * ppm, seed) + 0.7 * noise(sh, 1.3 * ppm, seed + 1)
    chips = np.clip((n - 2.75 + 0.35 * wear) * 2.2, 0, 1) * wide
    base += (PRIMER - base) * (0.85 * chips)[..., None]
    smooth += 0.14 * chips
    bump -= 0.03 * chips
    dirt = np.clip(1 - np.abs(sd_in - 0.9) / 1.4, 0, 1) * (sd_in > 0)
    base *= (1 - 0.10 * dirt * mm)[..., None] if m is not None else (1 - 0.10 * dirt)[..., None]


def paint_screw(put, X, Y, x, y, r, ppm_cov, slot="cross", ang=0.0, col=STEEL):
    dx, dy = X - x, Y - y
    d = np.hypot(dx, dy)
    if not (d < r * 2.5).any():
        return
    put(ppm_cov(d - r - 0.35), BLACK * 1.5, -0.10, 0.25)
    dome = np.clip(1 - (d / max(r, 1e-6)) ** 2, 0, 1)
    c = ppm_cov(d - r)
    put(c, col * 1.06, None, 0.52)
    put(c * dome, col * 1.2, 0.10, None)
    put(c * np.clip((dx * 0.6 + dy * 0.8) / r, 0, 1) * 0.5, col * 1.25, None, None)
    ca, sa = math.cos(ang), math.sin(ang)
    u, v = dx * ca + dy * sa, -dx * sa + dy * ca
    w = max(0.17 * r, 0.22)
    if slot == "cross":
        sdl = np.minimum(np.maximum(np.abs(u) - r * 0.62, np.abs(v) - w), np.maximum(np.abs(v) - r * 0.62, np.abs(u) - w))
    else:
        sdl = np.maximum(np.abs(u) - r * 0.92, np.abs(v) - w)
    put(ppm_cov(sdl) * (d < r), BLACK, -0.18, 0.2)
    return dome * c


class Canvas:

    def __init__(self, win, res=2048, colour=GREY, seed=1):
        self.win = win
        x0, x1, y0, y1 = win
        W, H = (res, res) if isinstance(res, int) else res
        self.res = (W, H)
        jj, ii = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        self.X = x0 + (jj + 0.5) / W * (x1 - x0)
        self.Y = y1 - (ii + 0.5) / H * (y1 - y0)
        del jj, ii
        self.ppm = W / (x1 - x0)
        assert abs(H / (y1 - y0) - self.ppm) < 0.01 * self.ppm, "canvas: pixels per mm differ in x and y"
        self.base = np.empty((H, W, 3), np.float32)
        self.base[:] = colour
        self.hm = np.zeros((H, W), np.float32)
        self.occ = np.zeros((H, W), np.float32)
        self.bump = np.zeros((H, W), np.float32)
        self.smooth = np.full((H, W), 0.34, np.float32)
        self.paintm = np.ones((H, W), np.float32)
        self.esd = np.full((H, W), 9.0, np.float32)
        self.ewear = np.ones((H, W), np.float32)
        self.late = []
        self.seed = seed

    def sub(self, x0, x1, y0, y1, pad=8.0):
        wx0, wx1, wy0, wy1 = self.win
        W, H = self.res
        j0 = max(int((min(x0, x1) - pad - wx0) * self.ppm), 0)
        j1 = min(int(math.ceil((max(x0, x1) + pad - wx0) * self.ppm)) + 1, W)
        i0 = max(int((wy1 - max(y0, y1) - pad) * self.ppm), 0)
        i1 = min(int(math.ceil((wy1 - min(y0, y1) + pad) * self.ppm)) + 1, H)
        c = object.__new__(Canvas)
        c.win, c.res, c.ppm, c.seed, c.late = self.win, self.res, self.ppm, self.seed, self.late
        if j1 <= j0 or i1 <= i0:
            j0, j1, i0, i1 = 0, 1, 0, 1
        sl = (slice(i0, i1), slice(j0, j1))
        for k in ("X", "Y", "base", "hm", "occ", "bump", "smooth", "paintm", "esd", "ewear"):
            setattr(c, k, getattr(self, k)[sl])
        return c

    def uv(self, x, y):
        x0, x1, y0, y1 = self.win
        return (x - x0) / (x1 - x0), (y - y0) / (y1 - y0)

    def cov(self, sd):
        return np.clip(0.5 - sd * self.ppm, 0, 1)

    def put(self, c, col=None, bump=None, smooth=None, paint=None):
        if col is not None:
            self.base += (np.asarray(col, np.float32) - self.base) * c[..., None]
        if bump is not None:
            self.bump += bump * c
        if smooth is not None:
            self.smooth += (smooth - self.smooth) * c
        if paint is not None:
            self.paintm += (paint - self.paintm) * c

    def plate(self, sd, z, col=None, smooth=None, paint=1.0, wear=1.0, edge=True):
        c = self.cov(sd)
        self.put(c, col, None, smooth, paint)
        self.hm += (z - self.hm) * c
        self.bump *= (1 - c)
        top = c > 0.5
        self.esd[...] = np.where(top, sd if (edge and paint > 0.5) else -9.0, self.esd)
        self.ewear[...] = np.where(top, wear, self.ewear)
        return c

    def stand(self, sd, z):
        np.maximum(self.occ, z * self.cov(sd), out=self.occ)

    def line(self, pts, w=0.6, col=WHITE):
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            s = self.sub(x0, x1, y0, y1, pad=w + 2.0)
            self.late.append((s, sd_seg(s.X, s.Y, x0, y0, x1, y1) - w / 2, col, -0.03, 0.35))

    def mark(self, sd, col, bump=None, smooth=None):
        self.late.append((self, sd, col, bump, smooth))

    def hazard(self, sd, period=6.5, a=YEL, b=BLACK, ang=45.0):
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        ph = ((self.X * ca + self.Y * sa) / period) % 1.0
        tri = np.abs(ph - 0.5) * 2
        st = np.clip((tri - 0.5) * period * self.ppm * 0.5 + 0.5, 0, 1)[..., None]
        col = st * np.asarray(a, np.float32) + (1 - st) * np.asarray(b, np.float32)
        c = self.cov(sd)
        self.base += (col - self.base) * c[..., None]
        self.smooth += (0.42 - self.smooth) * c
        self.paintm *= (1 - 0.5 * c)

    def screw(self, x, y, r=1.7, slot="cross", ang=None, col=STEEL):
        if ang is None:
            ang = (x * 12.9898 + y * 78.233) % math.pi
        self.late.append((self.sub(x - r, x + r, y - r, y + r, pad=r * 1.5 + 1.0), "screw", x, y, r, slot, ang, col))

    def screw_fault(self, x, y, r, others=(), keep=(), want_z=None):
        x0, x1, y0, y1 = self.win
        if not (x0 + r < x < x1 - r and y0 + r < y < y1 - r):
            return "off"
        s = self.sub(x - r, x + r, y - r, y + r, pad=r + 3.0)
        d = np.hypot(s.X - x, s.Y - y)
        disc = d <= r + 0.5
        if not disc.any():
            return "off"
        h = s.hm[disc]
        if h.max() - h.min() > 0.25:
            return "step"
        if want_z is not None and abs(float(h.mean()) - want_z) > 0.3:
            return "well"
        e = s.esd[disc]
        if ((e > -0.6) & (e < 8.9)).any():
            return "edge"
        near = d <= r + 1.2
        if (s.occ[near] > s.hm[near] + 0.5).any():
            return "control"
        for ox, oy, orr in others:
            if math.hypot(ox - x, oy - y) < r + orr + 0.8:
                return "screw"
        for kx0, kx1, ky0, ky1 in keep:
            if math.hypot(x - min(max(x, kx0), kx1), y - min(max(y, ky0), ky1)) < r + 0.6:
                return "label"
        for it in self.late:
            if isinstance(it[1], str):
                continue
            cv, sd = it[0], it[1]
            if cv.X[0, 0] - 1 > x + r or cv.X[0, -1] + 1 < x - r or cv.Y[-1, 0] - 1 > y + r or cv.Y[0, 0] + 1 < y - r:
                continue
            if ((sd < 0.2) & (np.hypot(cv.X - x, cv.Y - y) < r + 0.4)).any():
                return "mark"
        return None

    def clear_spot(self, x, y, r, others=(), keep=(), want_z=None, reach=8.0):
        n = int(reach)
        for dx, dy in sorted(((i, j) for i in range(-n, n + 1) for j in range(-n, n + 1) if i * i + j * j <= reach * reach),
                             key=lambda q: q[0] * q[0] + q[1] * q[1]):
            if self.screw_fault(x + dx, y + dy, r, others, keep, want_z) is None:
                return x + dx, y + dy
        return None

    def check_screws(self, keep=()):
        scr = [(it[2], it[3], it[4]) for it in self.late if isinstance(it[1], str)]
        bad = []
        for i, (x, y, r) in enumerate(scr):
            f = self.screw_fault(x, y, r, scr[:i] + scr[i + 1:], keep)
            if f:
                bad.append((x, y, r, f))
        self.screw_faults = bad
        print("SCREW QC: %d painted screws, %d faults" % (len(scr), len(bad)))
        for x, y, r, f in bad:
            print("SCREW QC   %-7s at (%.1f, %.1f) r %.1f" % (f, x, y, r))
        return bad

    def finish(self, wear=1.0, gain=1.0):
        if not hasattr(self, "screw_faults"):
            self.check_screws(getattr(self, "keep", ()))
        paint_finish(self.base, self.bump, self.smooth, self.ppm, self.seed, self.paintm, wear, gain=gain)
        edge_wear(self.base, self.bump, self.smooth, self.ppm, self.esd, self.seed + 10, wear, self.paintm * self.ewear, **getattr(self, "edge", {}))
        for it in self.late:
            cv = it[0]
            if isinstance(it[1], str):
                _, _, x, y, r, slot, ang, col = it
                paint_screw(lambda c, col_, b_, s_, cv=cv: cv.put(c, col_, b_, s_), cv.X, cv.Y, x, y, r, cv.cov, slot, ang, col)
            else:
                _, sd, col, bump, smooth = it
                cv.put(cv.cov(sd), col, bump, smooth)

    def save(self, out_dir, name, ao_strength=1.0, ao_floor=0.40):
        from PIL import Image
        import ckpaint as cp
        ao = hf_ao(np.maximum(self.hm, self.occ), self.ppm, ao_strength)
        ao = np.where(self.occ > self.hm + 0.5, np.minimum(ao, 0.45), ao)
        self.base *= (ao_floor + (1 - ao_floor) * ao)[..., None]
        self.smooth *= (0.72 + 0.28 * ao)
        nx, ny, _ = cp.normal_from_height(self.bump, self.ppm * 1.0)
        cp.save(self.base, os.path.join(out_dir, name + "_base.png"), "RGB")
        cp.save(cp.pack_normal(nx, ny), os.path.join(out_dir, name + "_normal.png"), "RGBA")
        del nx, ny
        mk = np.zeros(self.smooth.shape + (4,), np.float32)
        mk[..., 3] = self.smooth
        cp.save(mk, os.path.join(out_dir, name + "_mask.png"), "RGBA")
        W, H = self.res
        Image.fromarray((np.clip(ao, 0, 1) * 255).astype(np.uint8)).resize((max(W // 4, 1), max(H // 4, 1))).save(os.path.join(out_dir, name + "_ao_preview.png"))


class Builder:

    def __init__(self, ck, sw, fr, win):
        from mathutils import Vector
        self.ck, self.sw, self.fr, self.win = ck, sw, fr, win
        self.V = Vector
        self.Xv, self.Yv, self.Nv = Vector(fr.X), Vector(fr.Y), Vector(fr.N)
        self.F = ck.frame(self.Xv, self.Yv, self.Nv)
        self.slab, self.bits = [], []

    def P(self, x, y, z=0.0):
        return self.V(self.fr.pt(x, y, z))

    def rot(self, ang):
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        return self.ck.frame(self.Xv * ca + self.Yv * sa, -self.Xv * sa + self.Yv * ca, self.Nv)

    def _uv(self, b):
        x0, x1, y0, y1 = self.win
        uvl = b.loops.layers.uv.active or b.loops.layers.uv.new("UVMap")
        for f in b.faces:
            for lp in f.loops:
                x, y, _ = self.fr.local(lp.vert.co)
                lp[uvl].uv = (min(max((x - x0) / (x1 - x0), 0.002), 0.998), min(max((y - y0) / (y1 - y0), 0.002), 0.998))
        return b

    def prism(self, pts, z0, z1, bevel=0.6, col=None, holes=(), seg=2):
        import bmesh
        b = bmesh.new()
        loops = [pts] + list(holes)
        if holes:
            ed = []
            for lp_ in loops:
                vs = [b.verts.new(self.P(x, y, z1)) for x, y in lp_]
                ed += [b.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
            bmesh.ops.triangle_fill(b, use_beauty=True, use_dissolve=False, edges=ed)
            kill = []
            for f in b.faces:
                cx, cy, _ = self.fr.local(f.calc_center_median())
                if any(_inside(cx, cy, h_) for h_ in holes) or not _inside(cx, cy, pts):
                    kill.append(f)
            if kill:
                bmesh.ops.delete(b, geom=kill, context='FACES')
            ext = bmesh.ops.extrude_face_region(b, geom=b.faces[:])
            bmesh.ops.translate(b, vec=-self.Nv * ((z1 - z0) / 1000.0), verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)])
        else:
            top = [b.verts.new(self.P(x, y, z1)) for x, y in pts]
            bot = [b.verts.new(self.P(x, y, z0)) for x, y in pts]
            b.faces.new(top)
            b.faces.new(bot[::-1])
            n = len(top)
            for i in range(n):
                j = (i + 1) % n
                b.faces.new((top[i], top[j], bot[j], bot[i]))
        bmesh.ops.recalc_face_normals(b, faces=b.faces[:])
        if bevel:
            b2 = self.ck.modded(b, bevel=bevel / 1000.0, seg=seg, angle=30)
            b.free()
            b = b2
        if col is None:
            self.slab.append(self._uv(b))
        else:
            self.bits.append(self.sw(b, col))
        return b

    def box(self, x, y, zc, size, col, bevel=0.8, seg=2, ang=0.0, F=None):
        s = tuple(v / 1000.0 for v in size)
        self.bits.append(self.sw(self.ck.rbox(self.P(x, y, zc), s, F or (self.rot(ang) if ang else self.F), bevel=bevel / 1000.0, seg=seg), col))

    def cyl(self, x, y, z0, r, h, col, seg=20, r_top=None, axis=None):
        from cockpit_hotas import cyl
        self.bits.append(self.sw(cyl(self.P(x, y, z0), axis or self.Nv, r / 1000.0, h / 1000.0, seg=seg,
                                     r_top=None if r_top is None else r_top / 1000.0), col))

    def _place(self, bm, x, y, z, ang=0.0):
        from mathutils import Matrix
        F = self.rot(ang) if ang else self.F
        bm.transform(Matrix.Translation(self.P(x, y, z)) @ F.to_4x4())
        self.bits.append(bm)

    def toggle(self, x, y, z=0.0, lean=14.0, lean_dir=90.0, long=False):
        import ctl_parts
        self._place(ctl_parts.toggle(self.sw, "long" if long else "bat", lean=lean, lean_dir=lean_dir), x, y, z)

    def knob(self, x, y, z, d, ang=0.0):
        import ctl_parts
        self._place(ctl_parts.knob(self.sw, d / 1000.0, "plain", -ang), x, y, z)

    def key(self, x, y, z, w, h, face="black", cap=5.2, ang=0.0, housing=True):
        if housing:
            self.box(x, y, z + 1.3, (w + 4.4, h + 4.4, 2.6), "black", bevel=0.7, seg=1, ang=ang)
        self.box(x, y, z + cap / 2 + 0.6, (w, h, cap), "darkgrey", bevel=1.0, seg=2, ang=ang)
        self.box(x, y, z + cap + 0.62, (w * 0.82, h * 0.82, 0.4), face, bevel=0, ang=ang)
        return z + cap + 0.85

    def hexbolt(self, x, y, z, r=4.6, h=2.8, washer=True):
        if washer:
            self.cyl(x, y, z, r * 1.42, 0.8, "black", seg=20)
        self.cyl(x, y, z + (0.8 if washer else 0.0), r, h, "darkgrey", seg=6)

    def screw(self, x, y, z, r=3.0, ang=0.7):
        self.cyl(x, y, z, r, 1.1, "darkgrey", seg=12, r_top=r * 0.8)
        self.box(x, y, z + 1.18, (r * 1.45, 0.7, 0.3), "black", bevel=0, ang=math.degrees(ang))

    def merged(self):
        return self.ck.merge(self.slab), self.ck.merge(self.bits)


def _inside(x, y, pts):
    ins = False
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            ins = not ins
    return ins
