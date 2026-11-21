import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ST = sys.argv[1]
path = os.path.join(ST, "typhoon.obj")
V, VT, VN = [], [], []
G = {}
cur = None
nlines = 0
for l in open(path):
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vt "):
        VT.append([float(x) for x in l.split()[1:3]])
    elif l.startswith("vn "):
        VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ("o ", "g "):
        cur = l.split()[1]
        assert cur != "cockpit_sillrail", "cockpit_detail.py has already run on this OBJ"
    elif l.startswith("f ") and cur in ("cockpit_seat", "cockpit_shellframe", "canopy_interior", "cockpit_conl", "cockpit_conr", "cockpit_keys", "cockpit_frame", "cockpit_panel", "cockpit_controls", "cockpit_shelltub", "cockpit_consoles", "cockpit_shelldeck", "cockpit_shellaft", "canopy", "fuselage_cockpit", "fuselage", "fuselage_nose"):
        G.setdefault(cur, []).append([tuple(int(a) if a else 0 for a in (c.split("/") + ["", ""])[:3]) for c in l.split()[1:]])
V, VT, VN = np.array(V), np.array(VT), np.array(VN)
FRAME_F = G.get("cockpit_shellframe", []) + G.get("cockpit_shelldeck", []) + G.get("cockpit_shellaft", [])
s_ = 0.0
for f in G["cockpit_seat"][:400]:
    a, b, c = (V[f[i][0] - 1] for i in range(3))
    if f[0][2]:
        s_ += np.cross(b - a, c - a) @ VN[f[0][2] - 1]
WIND = 1 if s_ >= 0 else -1
nv, nvt, nvn = len(V), len(VT), len(VN)
tail = []
UPV = np.array([0.0, 1.0, 0.0])

import bpy
from mathutils import Vector as _Vec
from mathutils.bvhtree import BVHTree as _BVH

_sf = []
for _g in ("cockpit_shellframe", "cockpit_shelldeck", "cockpit_shellaft", "cockpit_shelltub", "cockpit_consoles", "canopy_interior"):
    for f in G.get(_g, []):
        ids = [c[0] - 1 for c in f]
        for k in range(1, len(ids) - 1):
            _sf.append((ids[0], ids[k], ids[k + 1]))
SHELL = _BVH.FromPolygons([_Vec(v) for v in V], _sf)
del _sf
N_MISS = [0]


def shell_hit(o, d, far=0.30):
    h = SHELL.ray_cast(_Vec([float(a) for a in o]), _Vec([float(a) for a in unit(d)]), far)
    if h[0] is None:
        N_MISS[0] += 1
        return None
    return np.array(h[0])


def unit(v):
    v = np.asarray(v, float)
    return v / max(np.linalg.norm(v), 1e-12)


class Soup:

    def __init__(self, ch=0.0):
        self.t = []
        self.ch = ch

    def piece(self, tris, centre):
        for a, b, c in tris:
            n = np.cross(b - a, c - a)
            if n @ ((a + b + c) / 3 - centre) < 0:
                b, c = c, b
            self.t.append((a, b, c))

    def box(self, c, a1, a2, a3, h1, h2, h3):
        c, a1, a2, a3 = (np.asarray(v, float) for v in (c, a1, a2, a3))
        k = min(self.ch, 0.42 * min(h1, h2, h3))
        if k > 2e-4:
            A, H = (a1, a2, a3), (h1, h2, h3)

            def vtx(sg, full):
                return c + sum(A[m] * (sg[m] * (H[m] if m == full else H[m] - k)) for m in range(3))
            tris = []
            for ax in range(3):
                o1, o2 = (ax + 1) % 3, (ax + 2) % 3
                for sa in (-1, 1):
                    q = []
                    for s1, s2 in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                        sg = [0, 0, 0]; sg[ax], sg[o1], sg[o2] = sa, s1, s2
                        q.append(vtx(sg, ax))
                    tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
            for ax in range(3):
                o1, o2 = (ax + 1) % 3, (ax + 2) % 3
                for s1 in (-1, 1):
                    for s2 in (-1, 1):
                        q = []
                        for sa, face in ((-1, o1), (1, o1), (1, o2), (-1, o2)):
                            sg = [0, 0, 0]; sg[ax], sg[o1], sg[o2] = sa, s1, s2
                            q.append(vtx(sg, face))
                        tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
            for s0 in (-1, 1):
                for s1 in (-1, 1):
                    for s2 in (-1, 1):
                        sg = [s0, s1, s2]
                        tris.append((vtx(sg, 0), vtx(sg, 1), vtx(sg, 2)))
            self.piece(tris, c)
            return
        p = [c + a1 * h1 * i + a2 * h2 * j + a3 * h3 * k for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)]
        q = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
        self.piece([(p[a], p[b], p[c_]) for a, b, c_, d in q] + [(p[a], p[c_], p[d]) for a, b, c_, d in q], c)

    def cyl(self, a, b, r, seg=16, r2=None):
        a, b = np.asarray(a, float), np.asarray(b, float)
        ax = unit(b - a)
        e1 = unit(np.cross(ax, [0.31, 0.77, 0.55]))
        e2 = np.cross(ax, e1)
        r2 = r if r2 is None else r2
        rad = [math.cos(2 * math.pi * i / seg) * e1 + math.sin(2 * math.pi * i / seg) * e2 for i in range(seg)]
        ra = [a + r * q for q in rad]
        rb = [b + r2 * q for q in rad]
        caps = []
        for i in range(seg):
            j = (i + 1) % seg
            for tri, nn in (((ra[i], ra[j], rb[j]), (rad[i], rad[j], rad[j])), ((ra[i], rb[j], rb[i]), (rad[i], rad[j], rad[i]))):
                if np.cross(tri[1] - tri[0], tri[2] - tri[0]) @ (rad[i] + rad[j]) < 0:
                    tri, nn = (tri[0], tri[2], tri[1]), (nn[0], nn[2], nn[1])
                self.t.append(tri + (nn,))
            caps += [(a, ra[i], ra[j]), (b, rb[i], rb[j])]
        self.piece(caps, (a + b) / 2)

    def tri(self, a, b, c, na, nb, nc, uv=None):
        if np.cross(b - a, c - a) @ (na + nb + nc) < 0:
            b, c, nb, nc = c, b, nc, nb
            if uv is not None:
                uv = (uv[0], uv[2], uv[1])
        self.t.append((a, b, c, (na, nb, nc)) if uv is None else (a, b, c, (na, nb, nc), uv))

    def sweep(self, P, U, W, N, pts, dirs, sect, out=1):
        n_ = len(pts)
        for (o0, h0), (o1, h1) in zip(sect[:-1], sect[1:]):
            mo, mh = h1 - h0, -(o1 - o0)
            if abs(mh) < 1e-9:
                mo, mh = float(out), 0.0
            elif mh < 0:
                mo, mh = -mo, -mh
            ln = math.hypot(mo, mh)
            mo, mh = mo / ln, mh / ln
            ring = []
            for i in range(n_):
                d3 = U * dirs[i][0] + W * dirs[i][1]
                ring.append((P(pts[i][0] + dirs[i][0] * o0, pts[i][1] + dirs[i][1] * o0, h0),
                             P(pts[i][0] + dirs[i][0] * o1, pts[i][1] + dirs[i][1] * o1, h1), unit(d3 * mo + N * mh)))
            for i in range(n_):
                j = (i + 1) % n_
                a0, a1, na = ring[i]
                b0, b1, nb = ring[j]
                if np.linalg.norm(b0 - a0) > 1e-7 or np.linalg.norm(b1 - a1) > 1e-7:
                    if np.linalg.norm(np.cross(b0 - a0, b1 - a0)) > 1e-12:
                        self.tri(a0, b0, b1, na, nb, nb)
                    if np.linalg.norm(np.cross(b1 - a0, a1 - a0)) > 1e-12:
                        self.tri(a0, b1, a1, na, nb, na)

    def tube(self, pts, r, seg=10):
        for p0, p1 in zip(pts[:-1], pts[1:]):
            self.cyl(p0, p1, r, seg)

    def emit(self, name, mtl):
        global nv, nvt, nvn
        if not self.t:
            return 0
        fl = []
        for t in self.t:
            a, b, c = t[:3]
            nn = t[3] if len(t) > 3 else (unit(np.cross(b - a, c - a)),) * 3
            order = (0, 1, 2) if WIND > 0 else (0, 2, 1)
            pp = (a, b, c)
            gn = np.abs(np.cross(b - a, c - a))
            ax_ = (0, 2) if gn[1] >= gn[0] and gn[1] >= gn[2] else ((2, 1) if gn[0] >= gn[2] else (0, 1))
            uv_ = t[4] if len(t) > 4 else None
            for k in order:
                tail.append("v %.5f %.5f %.5f" % tuple(pp[k]))
                tail.append("vn %.4f %.4f %.4f" % tuple(nn[k]))
                tail.append("vt %.4f %.4f" % ((pp[k][ax_[0]] * 3.0, pp[k][ax_[1]] * 3.0) if uv_ is None else tuple(uv_[k])))
            fl.append("f " + " ".join("%d/%d/%d" % (nv + 1 + k, nvt + 1 + k, nvn + 1 + k) for k in range(3)))
            nv += 3
            nvn += 3
            nvt += 3
        tail.extend(["o " + name, "usemtl " + mtl] + fl)
        print("%s: %d triangles (%s)" % (name, len(self.t), mtl))
        return len(self.t)


HOSE_CELL, HOSE_INSET = (0.90, 0.33, 0.98, 0.41), 0.09


def _tri_wave(x):
    return 1.0 - abs((x % 2.0) - 1.0)


def hose(soup, pts, r, seg=10, step=0.004):
    Pp = [np.asarray(q, float) for q in pts]
    Pp = [Pp[0] * 2 - Pp[1]] + Pp + [Pp[-1] * 2 - Pp[-2]]
    path = []
    for i in range(1, len(Pp) - 2):
        p0, p1, p2, p3 = Pp[i - 1], Pp[i], Pp[i + 1], Pp[i + 2]
        n_ = max(int(math.ceil(np.linalg.norm(p2 - p1) / step)), 1)
        for k in range(n_):
            t = k / n_
            path.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    path.append(Pp[-2])
    u0, v0, u1, v1 = HOSE_CELL
    per = math.pi * r
    e1 = None
    rings, s_ = [], 0.0
    for i, q in enumerate(path):
        t = unit(path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)])
        e1 = unit(np.cross(t, [0.31, 0.77, 0.55])) if e1 is None else unit(e1 - t * (e1 @ t))
        e2 = np.cross(t, e1)
        if i:
            s_ += np.linalg.norm(q - path[i - 1])
        vv = v0 + (v1 - v0) * (HOSE_INSET + (1 - 2 * HOSE_INSET) * _tri_wave(s_ / per))
        ring = []
        for j in range(seg + 1):
            a = 2 * math.pi * j / seg
            d = math.cos(a) * e1 + math.sin(a) * e2
            uu = u0 + (u1 - u0) * (HOSE_INSET + (1 - 2 * HOSE_INSET) * _tri_wave(2.0 * j / seg))
            ring.append((q + d * r, d, (uu, vv)))
        rings.append(ring)
    for ra, rb in zip(rings[:-1], rings[1:]):
        for j in range(seg):
            a0, a1, b0, b1 = ra[j], ra[j + 1], rb[j], rb[j + 1]
            soup.tri(a0[0], a1[0], b1[0], a0[1], a1[1], b1[1], (a0[2], a1[2], b1[2]))
            soup.tri(a0[0], b1[0], b0[0], a0[1], b1[1], b0[1], (a0[2], b1[2], b0[2]))
    return path


def ferrule(soup, p, t, r, L=0.012):
    p, t = np.asarray(p, float), unit(t)
    soup.cyl(p, p + t * L * 0.62, r * 1.22, 14)
    soup.cyl(p + t * L * 0.62, p + t * L, r * 1.55, 6)


plac = Soup()
PLAC = {"rbf": (0, 0, 1024, 160), "name": (0, 176, 512, 496), "caution": (528, 176, 1008, 336)}


def plac_quad(c, e1, e2, nrm, w, h, cell):
    x0, y0, x1, y1 = PLAC[cell]
    c, e1, e2, nrm = (np.asarray(q, float) for q in (c, e1, e2, nrm))
    q = [(c - e1 * w / 2 - e2 * h / 2, (x0 / 1024, 1 - y1 / 512)), (c + e1 * w / 2 - e2 * h / 2, (x1 / 1024, 1 - y1 / 512)),
         (c + e1 * w / 2 + e2 * h / 2, (x1 / 1024, 1 - y0 / 512)), (c - e1 * w / 2 + e2 * h / 2, (x0 / 1024, 1 - y0 / 512))]
    for i, j, k in ((0, 1, 2), (0, 2, 3)):
        plac.tri(q[i][0], q[j][0], q[k][0], nrm, nrm, nrm, (q[i][1], q[j][1], q[k][1]))


rail, lug, scr, hole = Soup(0.0018), Soup(0.0014), Soup(), Soup()
BEAM_T = 0.36
for sx in (1, -1):
    A = np.array([sx * 0.4010, 0.8910, 6.535])
    B = np.array([sx * 0.3975, 0.8400, 6.975])
    d = unit(B - A)
    L = np.linalg.norm(B - A)
    xh = np.array([1.0, 0, 0])
    n = unit(np.cross(d, xh) * (1 if np.cross(d, xh)[1] > 0 else -1))
    A, B = A + n * 0.006, B + n * 0.006
    mid = (A + B) / 2
    _t0 = BEAM_T - 0.03
    mid = A + d * (L * (_t0 + 1) / 2)
    _hl = L * (1 - _t0) / 2 + 0.01
    rail.box(mid - n * 0.001, d, xh, n, _hl, 0.031, 0.009)
    rail.box(mid + n * 0.011 - xh * sx * 0.027, d, xh, n, _hl, 0.004, 0.004)
    rail.box(mid + n * 0.0095 + xh * sx * 0.0295, d, xh, n, _hl, 0.0015, 0.0025)
    for t in ():
        c = A + d * (L * t) + n * 0.008 - xh * sx * 0.012
        lug.box(c + n * 0.009, d, xh, n, 0.017, 0.008, 0.009)
        lug.box(c + n * 0.005 + d * 0.022, d, xh, n, 0.006, 0.008, 0.005)
        lug.cyl(c + n * 0.019 + d * 0.006 - xh * 0.011, c + n * 0.019 + d * 0.006 + xh * 0.011, 0.0065, 12)
        _ax = c + n * 0.019 + d * 0.006
        for _e in ((-1, 1) if t < 0.85 else ()):
            scr.cyl(_ax + xh * (_e * 0.011), _ax + xh * (_e * 0.0128), 0.0036, 6)
        scr.cyl(c + n * 0.0098 + d * 0.0225, c + n * 0.0112 + d * 0.0225, 0.0026, 8)
    e = B - d * 0.025 + n * 0.008
    rail.box(e + n * 0.005, d, xh, n, 0.026, 0.018, 0.005)
    rail.cyl(e + n * 0.028 - xh * 0.013, e + n * 0.028 + xh * 0.013, 0.019, 24)
    rail.box(e + n * 0.015, d, xh, n, 0.016, 0.012, 0.008)
    hole.cyl(e + n * 0.028 - xh * 0.0136, e + n * 0.028 + xh * 0.0136, 0.0095, 18)
box_, lens_, dot_ = Soup(0.0030), Soup(), Soup()
for sx in (1, -1):
    c = np.array([sx * 0.352, 0.935, 6.985])
    aim = unit(np.array([0.0, 1.10, 6.55]) - c)
    u1 = unit(np.cross([0, 1.0, 0], aim))
    u2 = np.cross(aim, u1)
    box_.box(c, u1, u2, aim, 0.026, 0.026, 0.028)
    box_.box(c - u2 * 0.040, u1, u2, aim, 0.012, 0.016, 0.014)
    box_.box(np.array([sx * 0.372, 0.872, 6.975]), [1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0], 0.016, 0.022, 0.020)
    scr.cyl(c + aim * 0.028, c + aim * 0.0305, 0.0128, 20)
    lens_.cyl(c + aim * 0.0300, c + aim * 0.0314, 0.0088, 20)
    dot_.cyl(c + aim * 0.0312, c + aim * 0.0318, 0.0030, 14)
    foot = np.array([sx * 0.372, 0.872, 6.975])
    top = c - u2 * 0.030 + np.array([sx * 0.012, 0, 0])
    for kz, dz_ in ((-1, 0.040), (1, 0.030)):
        bot = foot + np.array([sx * 0.010, -0.014, kz * dz_])
        dd = unit(bot - top)
        sd_ = unit(np.cross(dd, [1.0, 0, 0]))
        box_.box((top + bot) / 2, dd, [1.0, 0, 0], sd_, np.linalg.norm(bot - top) / 2, 0.0050, 0.0030)
        box_.box(bot + np.array([0.0, -0.002, kz * 0.004]), [1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0], 0.0085, 0.0035, 0.0100)
        q = bot + np.array([0.0, 0.0015, kz * 0.009])
        scr.cyl(q, q + np.array([0, 0.0018, 0]), 0.0030, 10)
    lug.cyl(top - np.array([0.0085, 0, 0]), top + np.array([0.0085, 0, 0]), 0.0042, 12)
    for i_ in (-1, 1):
        for j_ in (-1, 1):
            q = c + aim * 0.028 + u1 * (i_ * 0.021) + u2 * (j_ * 0.021)
            scr.cyl(q, q + aim * 0.0012, 0.0022, 8)
cable = Soup()
for sx in (1, -1):
    def wallx(z):
        return 0.3833 - 0.0056 * (z - 6.545) / 0.41
    _cp = [np.array(q) * [sx, 1, 1] for q in ((0.352, 0.900, 6.972), (0.358, 0.872, 6.948), (wallx(6.915) - 0.0064, 0.822, 6.915),
                                             (wallx(6.840) - 0.0064, 0.790, 6.840), (wallx(6.700) - 0.0064, 0.776, 6.700), (wallx(6.575) - 0.0064, 0.778, 6.575))]
    hose(cable, _cp, 0.0055, 10)
    ferrule(lug, _cp[0], _cp[0] - _cp[1], 0.0055, 0.010)
    ferrule(lug, _cp[-1], _cp[-1] - _cp[-2], 0.0055, 0.012)

    def under(y, z, off, sx=sx):
        xw = 0.518 - (y - 0.56) * 0.36 - (z - 6.36) * 0.0245
        nw = np.array([sx * 0.94, 0.34, 0.0])
        o = np.array([sx * xw, y, z]) - nw * 0.08
        hit = shell_hit(o, nw, 0.16)
        if hit is not None and abs(np.linalg.norm(hit - o) - 0.08) < 0.012:
            return hit - nw * off
        return np.array([sx * (xw - 0.94 * off), y - 0.34 * off, z])
    runs = (((0.668, 0.0075, 6.80), (0.640, 0.0055, 6.72)) if sx < 0 else ((0.660, 0.0060, 6.64),))
    for y_, r_, z1_ in runs:
        zs = np.arange(6.275, z1_ - 0.02, 0.05)
        pts_ = [under(y_ - 0.005 * math.sin((z - 6.275) / 0.15 * math.pi) ** 2, z, r_ + 0.004) for z in zs]
        pts_ += [under(y_, z1_ - 0.012, r_ + 0.004), under(y_ - 0.002, z1_, r_ * 0.4), under(y_ - 0.004, z1_ + 0.006, -0.004)]
        hose(cable, pts_, r_, 10)
        ferrule(lug, pts_[-2], pts_[-1] - pts_[-2], r_, 0.010)
        ferrule(lug, pts_[0] + np.array([0, 0, 0.012]), [0, 0, -1.0], r_, 0.012)
        for z in np.arange(6.425, z1_ - 0.05, 0.15):
            cc = under(y_, z, r_ + 0.004)
            lug.cyl(cc - np.array([0, 0, 0.005]), cc + np.array([0, 0, 0.005]), r_ + 0.0018, 12)
            lug.box(under(y_ + r_ + 0.006, z, 0.002), [0, 0, 1.0], [-sx * 0.34, 0.94, 0], [sx * 0.94, 0.34, 0], 0.005, 0.006, 0.0015)
    yp = 0.698 if sx < 0 else 0.688
    lug.cyl(under(yp, 6.28, 0.007), under(yp, 6.84, 0.007), 0.0032, 10)
    for z in (6.36, 6.52, 6.68, 6.82):
        cc = under(yp, z, 0.007)
        lug.cyl(cc - np.array([0, 0, 0.007]), cc + np.array([0, 0, 0.007]), 0.0050, 6)
        lug.box(under(yp, z + 0.03, 0.003), [0, 0, 1.0], [-sx * 0.34, 0.94, 0], [sx * 0.94, 0.34, 0], 0.004, 0.007, 0.003)
    for q in ((0.3712, 0.796, 6.86), (0.3722, 0.777, 6.72), (0.3732, 0.777, 6.60)):
        c = np.array([wallx(q[2]) - 0.0064, q[1], q[2]]) * [sx, 1, 1]
        lug.box(c, [1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0], 0.0075, 0.0085, 0.006)
cable.emit("cockpit_cables", "ckdetail")

wall = Soup(0.0012)
for sx in (1, -1):
    _xa, _xb = (shell_hit([sx * 0.30, 0.757 + (0.709 - 0.757) * t_ + 0.6 * 0.129, 6.545 + 0.41 * t_], [sx, 0, 0]) for t_ in (0.05, 0.95))
    _xa, _xb = (abs(q[0]) if q is not None else 0.3765 for q in (_xa, _xb))
    assert 0.370 < _xb <= _xa < 0.390, "sill wall not where it was measured: %.4f %.4f" % (_xa, _xb)
    _x0, _x1 = _xa - (_xb - _xa) * 0.05 / 0.90, _xb + (_xb - _xa) * 0.05 / 0.90
    print("sill wall face: x = %.4f aft, %.4f forward" % (_x0, _x1))

    def wp(t, h):
        z = 6.545 + (6.955 - 6.545) * t
        yb, yt = 0.757 + (0.709 - 0.757) * t, 0.886 + (0.838 - 0.886) * t
        return np.array([sx * (_x0 + (_x1 - _x0) * t), yb + (yt - yb) * h, z])
    dz = unit(wp(1, 0.6) - wp(0, 0.6))
    inb = np.array([-sx * 1.0, 0, 0])
    inb = unit(inb - dz * (inb @ dz))
    upw = unit(np.cross(dz, inb) * (1 if np.cross(dz, inb)[1] > 0 else -1))
    L_ = np.linalg.norm(wp(1, 0.6) - wp(0, 0.6))
    wall.box((wp(0, 0.60) + wp(1, 0.60)) / 2 + inb * 0.0035, dz, upw, inb, L_ / 2, 0.007, 0.0045)
    wall.box((wp(0, 0.60) + wp(1, 0.60)) / 2 + inb * 0.009, dz, upw, inb, L_ / 2, 0.0025, 0.0015)
    for t in (0.10, 0.365, 0.63, 0.895):
        wall.box((wp(t, 0.145) + wp(t, 0.52)) / 2 + inb * 0.0025, dz, upw, inb, 0.005, np.linalg.norm(wp(t, 0.52) - wp(t, 0.145)) / 2, 0.0035)
        wall.box((wp(t, 0.68) + wp(t, 0.905)) / 2 + inb * 0.0025, dz, upw, inb, 0.005, np.linalg.norm(wp(t, 0.905) - wp(t, 0.68)) / 2, 0.0035)
    for h in (0.095, 0.955):
        for t in np.arange(0.03, 0.98, 0.075):
            if (h < 0.5 and abs(t - 0.50) < 0.075) or (h > 0.5 and t > 0.90):
                continue
            c = wp(t, h) - inb * 0.0002
            scr.cyl(c, c + inb * 0.0018, 0.0032, 10)
    wall.cyl(wp(0, 0.0) + inb * 0.004, wp(1, 0.0) + inb * 0.004, 0.009, 14)
    c = wp(0.50, 0.13)
    rail.box(c + inb * 0.0025, dz, upw, inb, 0.022, 0.011, 0.0035)
    for k in (-1, 1):
        rail.box(c + dz * (k * 0.011) + inb * 0.012, dz, upw, inb, 0.003, 0.009, 0.009)
        for kk in (-1, 1):
            q = c + dz * (k * 0.018) + upw * (kk * 0.007) + inb * 0.006
            scr.cyl(q, q + inb * 0.0016, 0.0026, 10)
    lug.cyl(c - dz * 0.016 + inb * 0.014, c + dz * 0.016 + inb * 0.014, 0.0035, 12)
    lug.box(c + inb * 0.014 - upw * 0.010, dz, upw, inb, 0.0065, 0.012, 0.0045)
    lug.cyl(c - upw * 0.022 + inb * 0.014 - dz * 0.008, c - upw * 0.022 + inb * 0.014 + dz * 0.008, 0.0062, 14)
    plac_quad(wp(0.235, 0.30) + inb * 0.0006, -dz * sx, upw, inb, 0.040, 0.025, "name")
    plac_quad(wp(0.765, 0.28) + inb * 0.0006, -dz * sx, upw, inb, 0.045, 0.015, "caution")

blank = Soup()
for sx in (1, -1):
    lo, hi = np.array([sx * 0.360, 0.535, 6.3045]), np.array([sx * 0.360, 0.770, 6.2660])
    upb = unit(hi - lo)
    fwd = unit(np.cross([1.0, 0, 0], upb))
    if fwd[2] < 0:
        fwd = -fwd
    cen = (lo + hi) / 2 + fwd * 0.003
    hh = np.linalg.norm(hi - lo) / 2
    wall.box(cen, [1.0, 0, 0], upb, fwd, 0.085, hh, 0.0022)
    wall.box(cen + fwd * 0.004, [1.0, 0, 0], upb, fwd, 0.085, 0.006, 0.003)
    for i in (-1, 1):
        for j in (-1, -0.33, 0.33, 1):
            c = cen + np.array([i * 0.075, 0, 0]) + upb * (j * hh * 0.86) + fwd * 0.002
            scr.cyl(c, c + fwd * 0.0015, 0.0032, 10)
hang = Soup(0.0015)
_X, _Y, _Z = [1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]
kb_d, kb_l, kb_w = Soup(0.0012), Soup(0.0006), Soup(0.0)
_kc = np.array([-0.3400, 0.6890, 7.2385])
_kn = unit(np.array([0.16, 0.30, -0.94]))
_ku = unit(np.cross(_kn, [1.0, 0, 0])); _ku = _ku if _ku[1] > 0 else -_ku
_kr = unit(np.cross(_ku, _kn))
kb_d.box([-0.3400, 0.6860, 7.2530], _X, _Y, _Z, 0.0200, 0.0190, 0.0150)
kb_d.box([-0.3400, 0.6690, 7.2500], _X, _Y, _Z, 0.0250, 0.0022, 0.0190)
kb_d.cyl(_kc - _kn * 0.0010, _kc + _kn * 0.0030, 0.0160, 28)
kb_l.cyl(_kc + _kn * 0.0030, _kc + _kn * 0.0125, 0.0128, 32, r2=0.0120)
for _i in range(12):
    _a = 2 * math.pi * _i / 12
    _rd = math.cos(_a) * _kr + math.sin(_a) * _ku
    _tg = np.cross(_kn, _rd)
    kb_l.box(_kc + _kn * 0.0078 + _rd * 0.0128, _rd, _tg, _kn, 0.0016, 0.0019, 0.0044)
kb_d.cyl(_kc + _kn * 0.0125, _kc + _kn * 0.0137, 0.0052, 18)
kb_w.box(_kc + _kn * 0.0127 + _ku * 0.0088, _kr, _ku, _kn, 0.0007, 0.0030, 0.0003)
kb_d.emit("cockpit_kneeknob_base", "ckbezel")
kb_l.emit("cockpit_kneeknob", "ckmetaldark")
kb_w.emit("cockpit_kneeknob_mark", "ckwhite")
KERB_BOX = (-0.296, -0.240, 0.524, 0.562, 7.010, 7.116)
_gl = []
for f in G.get("canopy", []):
    ids = [c[0] - 1 for c in f]
    for k in range(1, len(ids) - 1):
        _gl.append((ids[0], ids[k], ids[k + 1]))
GLASS0 = _BVH.FromPolygons([_Vec(v) for v in V], _gl)
_RA, _RB = np.array([0.4010, 0.8910, 6.535]), np.array([0.3975, 0.8400, 6.975])
_RD = unit(_RB - _RA); _RL = float(np.linalg.norm(_RB - _RA))
_RN = unit(np.cross(_RD, [1.0, 0, 0])); _RN = _RN if _RN[1] > 0 else -_RN


def rail_y(z, nn=0.0):
    q = _RA + _RD * ((z - _RA[2]) / _RD[2])
    return float(q[1] + _RN[1] * nn)


def _sill_station(z):
    yl = rail_y(z)
    xg = None
    for dy in (0.040, 0.055, 0.025):
        h = GLASS0.ray_cast(_Vec((0.30, yl + dy, z)), _Vec((1.0, 0, 0)), 0.3)
        if h[0] is not None:
            xg = h[0][0]
            break
    if xg is None:
        return None
    pr = []
    for x in np.arange(xg - 0.090, xg - 0.010, 0.003):
        h = SHELL.ray_cast(_Vec((x, yl + 0.10, z)), _Vec((0, -1.0, 0)), 0.30)
        if h[0] is not None:
            pr.append((x, h[0][1]))
    if len(pr) < 6:
        return None
    yt = max(q[1] for q in pr)
    xc = float(np.mean([q[0] for q in pr if q[1] > yt - 0.004]))
    return xg, yt, xc


BEAM_Z0 = float(os.environ.get("BEAM_Z0", "5.80"))
BEAM_Z1 = float(_RA[2] + _RD[2] * _RL * BEAM_T)
_st = [(z, _sill_station(z)) for z in np.arange(BEAM_Z0 - 0.04, BEAM_Z1 + 0.021, 0.02)]
_st = [(z, q) for z, q in _st if q is not None]
_zz = np.array([z for z, q in _st]); _q = np.array([q for z, q in _st])
_fg, _fy, _fc = (np.polyfit(_zz - 6.3, _q[:, k], 3) for k in range(3))
_PLATE_N = 0.023
def beam_top(z):
    return rail_y(z, _PLATE_N + 0.004)


def beam_xg(z):
    return float(np.polyval(_fg, min(max(z, _zz[0]), _zz[-1]) - 6.3))


def beam_xc(z):
    return float(np.polyval(_fc, min(max(z, _zz[0]), _zz[-1]) - 6.3))


print("sill beam: z %.2f .. %.3f, %d stations; fit off the glass %.1f mm, the ridge %.1f mm, its middle %.1f mm at worst; top %.0f .. %.0f mm over the ridge" % (
    BEAM_Z0, BEAM_Z1, len(_zz), np.abs(_q[:, 0] - np.polyval(_fg, _zz - 6.3)).max() * 1000, np.abs(_q[:, 1] - np.polyval(_fy, _zz - 6.3)).max() * 1000,
    np.abs(_q[:, 2] - np.polyval(_fc, _zz - 6.3)).max() * 1000,
    min(beam_top(z) - q[1] for z, q in _st if BEAM_Z0 <= z <= BEAM_Z1) * 1000, max(beam_top(z) - q[1] for z, q in _st if BEAM_Z0 <= z <= BEAM_Z1) * 1000))
beam, wedge = Soup(), Soup()
if not os.environ.get("NO_SILL_BEAM"):
    _BR = 0.011
    _zs = list(np.arange(BEAM_Z0, BEAM_Z1 - 0.012, 0.03)) + [BEAM_Z1]

    def _beam_sec(z, sx):
        T, xo, xc = beam_top(z), beam_xg(z) - 0.0045, beam_xc(z)
        xi = min(xc - 0.034, xo - 0.070)
        P = lambda x, y: np.array([sx * x, y, z])
        Nn = lambda x, y: unit(np.array([sx * x, y, 0.0]))
        run_o = [(P(xo, T - 0.022), Nn(1, 0)), (P(xo, T), Nn(1, 0))]
        run_t = [(P(xo, T), Nn(0.02, 1)), (P(xi, T - 0.0015), Nn(-0.02, 1))]
        run_s = [(P(xi, T - 0.0015), Nn(-0.02, 1))]
        for k in range(1, 6):
            a_ = math.radians(90 * k / 6)
            run_s.append((P(xi - _BR * math.sin(a_), T - 0.0015 - _BR + _BR * math.cos(a_)), Nn(-math.sin(a_), math.cos(a_))))
        run_s += [(P(xi - _BR, T - 0.0015 - _BR), Nn(-1, 0)), (P(xi - _BR, T - 0.058), Nn(-1, 0))]
        run_u = [(P(xi - _BR, T - 0.058), Nn(0, -1)), (P(xc - 0.008, T - 0.058), Nn(0, -1))]
        return [run_o, run_t, run_s, run_u]
    for sx in (1, -1):
        secs = [_beam_sec(z, sx) for z in _zs]
        for r in range(4):
            for i in range(len(secs) - 1):
                ra, rb = secs[i][r], secs[i + 1][r]
                for j in range(len(ra) - 1):
                    (a0, na0), (a1, na1), (b0, nb0), (b1, nb1) = ra[j], ra[j + 1], rb[j], rb[j + 1]
                    beam.tri(a0, b0, b1, na0, nb0, nb1)
                    beam.tri(a0, b1, a1, na0, nb1, na1)
        for i, zdir in ((0, -1.0), (len(secs) - 1, 1.0)):
            ring = [q for run in secs[i] for (q, _) in run]
            cen = sum(ring) / len(ring)
            en = np.array([0.0, 0.0, zdir])
            for j in range(len(ring)):
                a_, b_ = ring[j], ring[(j + 1) % len(ring)]
                if np.linalg.norm(np.cross(a_ - cen, b_ - cen)) > 1e-12:
                    beam.tri(cen, a_, b_, en, en, en)
        A = _RA * [sx, 1, 1]; B = _RB * [sx, 1, 1]
        d = unit(B - A); L = np.linalg.norm(B - A)
        xh = np.array([1.0, 0, 0])
        n = unit(np.cross(d, xh) * (1 if np.cross(d, xh)[1] > 0 else -1))
        A, B = A + n * 0.014, B + n * 0.014
        P0, P1 = A + d * (BEAM_T * L) + d * 0.0005, B - d * 0.060
        _g1 = _sill_station(float(P1[2]))
        o0 = xh * sx * (beam_xg(BEAM_Z1) - 0.0045 - abs(P0[0]))
        o1 = xh * sx * ((_g1[0] if _g1 else beam_xg(BEAM_Z1)) - 0.0045 - abs(P1[0]))
        i0, i1 = -xh * sx * 0.040, xh * sx * 0.004
        H = n * (_PLATE_N - 0.014)
        c8 = [P0 + o0, P0 + i0, P1 + i1, P1 + o1, P0 + o0 + H, P0 + i0 + H, P1 + i1 + H, P1 + o1 + H]
        quads = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        cen = sum(c8) / 8
        wedge.piece([(c8[q[0]], c8[q[1]], c8[q[2]]) for q in quads] + [(c8[q[0]], c8[q[2]], c8[q[3]]) for q in quads], cen)
        for t in (0.16, 0.50, 0.84):
            top = P0 + (P1 - P0) * t + H + ((o0 + (o1 - o0) * t) + (i0 + (i1 - i0) * t)) / 2
            scr.cyl(top - n * 0.0004, top + n * 0.0012, 0.0034, 10)
    beam.emit("cockpit_sillbeam", "ckrail")
    wedge.emit("cockpit_sillwedge", "ckrail")

fw_p, fw_d, fw_b = Soup(0.0012), Soup(), Soup()
for sx in (1, -1):
    xw = sx * 0.290
    inw = np.array([-float(sx), 0, 0])
    z0, z1, y0, y1 = 7.065, 7.335, 0.205, 0.405
    fw_p.box(np.array([xw, (y0 + y1) / 2, (z0 + z1) / 2]) + inw * 0.0012, _Z, _Y, _X, (z1 - z0) / 2, (y1 - y0) / 2, 0.0012)
    pw = (z1 - z0 - 0.020 * 4) / 3
    for k in range(3):
        zc = z0 + 0.020 + pw / 2 + k * (pw + 0.020); yc = (y0 + y1) / 2
        hw, hh, rr = pw / 2, (y1 - y0) / 2 - 0.022, 0.018
        ring = []
        for (cz, cy, a0) in ((zc + hw - rr, yc + hh - rr, 0), (zc - hw + rr, yc + hh - rr, 90), (zc - hw + rr, yc - hh + rr, 180), (zc + hw - rr, yc - hh + rr, 270)):
            for j in range(7):
                a = math.radians(a0 + 15 * j)
                ring.append(np.array([xw, cy + rr * math.sin(a), cz + rr * math.cos(a)]) + inw * 0.0036)
        cc = np.array([xw, yc, zc]) + inw * 0.0036
        for j in range(len(ring)):
            fw_d.tri(cc, ring[j], ring[(j + 1) % len(ring)], inw, inw, inw)
        fw_b.tube(ring + [ring[0], ring[1]], 0.0026, 6)
    for (zz, yy) in ((z0 + 0.009, y0 + 0.009), (z1 - 0.009, y0 + 0.009), (z0 + 0.009, y1 - 0.009), (z1 - 0.009, y1 - 0.009)):
        scr.cyl(np.array([xw, yy, zz]) + inw * 0.0024, np.array([xw, yy, zz]) + inw * 0.0036, 0.0032, 10)
fw_p.emit("cockpit_footpanel", "ckliner")
fw_d.emit("cockpit_footpocket", "ckbezel")
fw_b.emit("cockpit_footbead", "ckliner")

guard = Soup()
for (px_, py_) in ((345, 200), (418, 200), (535, 200), (603, 205)):
    gx, gz = -(0.290 + py_ / 1000.0), 7.100 - px_ / 1000.0
    gy = 0.440 + 0.0767 * (-0.37 - gx) + 0.09 * (gz - 6.35) + 0.0015
    for dz in (-0.0105, 0.0105):
        pts = [np.array([gx - 0.0085, gy - 0.002, gz + dz]), np.array([gx - 0.0085, gy + 0.011, gz + dz])]
        for j in range(1, 6):
            a = math.pi * j / 6
            pts.append(np.array([gx - 0.0085 * math.cos(a), gy + 0.011 + 0.0065 * math.sin(a), gz + dz]))
        pts += [np.array([gx + 0.0085, gy + 0.011, gz + dz]), np.array([gx + 0.0085, gy - 0.002, gz + dz])]
        guard.tube(pts, 0.0013, 6)
guard.emit("cockpit_swguards", "ckrail")

pad, strap, wred, wyel = Soup(0.013), Soup(0.0008), Soup(), Soup()
_hn = unit(np.array([0.0, 0.425, 1.0])); _ht = unit(np.array([0.0, 1.0, -0.425]))
_hc = np.array([0.0, 1.258, 6.333 - 0.425 * 0.058])
pad.box(_hc + _hn * 0.024, _X, _ht, _hn, 0.098, 0.052, 0.024)
for sx in (1, -1):
    _sp = [(1.203, 6.376), (1.150, 6.401), (1.050, 6.405), (0.950, 6.480), (0.862, 6.517)]
    for (ya, za), (yb, zb) in zip(_sp[:-1], _sp[1:]):
        a_, b_ = np.array([sx * 0.070, ya, za]), np.array([sx * 0.070, yb, zb])
        dd = unit(b_ - a_); nn_ = unit(np.cross(_X, dd)); nn_ = nn_ if nn_[2] > 0 else -nn_
        strap.box((a_ + b_) / 2 + nn_ * 0.0022, _X, dd, nn_, 0.0225, np.linalg.norm(b_ - a_) / 2 + 0.002, 0.0018)
    sc = np.array([sx * 0.1503, 1.243, 6.222])
    wyel.box(sc, _X, _Y, _Z, 0.0006, 0.0185, 0.0330)
    wred.box(sc + np.array(_X) * (sx * 0.0005), _X, _Y, _Z, 0.0006, 0.0150, 0.0295)
_bp = Soup(0.0010)
_bp.box(np.array([0.0, 1.262, 5.9988]), _X, _Y, _Z, 0.105, 0.042, 0.0012)
for _sx in (-0.095, 0.095):
    for _sy in (1.228, 1.296):
        scr.cyl(np.array([_sx, _sy, 5.9976]), np.array([_sx, _sy, 5.9966]), 0.0034, 10)
wyel.box(np.array([0.0, 1.262, 5.9972]), _X, _Y, _Z, 0.032, 0.011, 0.0005)
_bp.emit("cockpit_seatplate", "ckliner")
pad.emit("cockpit_headpad", "ckpad")
strap.emit("cockpit_seatstraps", "ckstrap")
wyel.emit("cockpit_seatwarn_y", "ckyellow")
wred.emit("cockpit_seatwarn_r", "ckredflag")
blk, trim = Soup(), Soup()
if not os.environ.get("NO_WALL_BLANKET"):
    _cl = []
    for f in G.get("cockpit_conl", []):
        ids = [c[0] - 1 for c in f]
        for k in range(1, len(ids) - 1):
            _cl.append((ids[0], ids[k], ids[k + 1]))
    CONL = _BVH.FromPolygons([_Vec(v) for v in V], _cl)

    def plate_y(x, z):
        h = CONL.ray_cast(_Vec((float(x), 0.57, float(z))), _Vec((0, -1.0, 0)), 0.3)
        return None if h[0] is None else float(h[0][1])
    _QW, _NPB = 0.070, 9
    _rows, _foot, _prof = [], [], []
    for z in np.arange(6.335, 6.8251, _QW / 4):
        yp = plate_y(-0.500, z)
        if yp is None:
            continue
        y, pts = yp - 0.004, []
        while y < 0.61:
            hh = SHELL.ray_cast(_Vec((-0.47, y, float(z))), _Vec((-1.0, 0, 0)), 0.09)
            if hh[0] is None or abs(hh[0][0]) > 0.538 or (pts and abs(hh[0][0]) < max(abs(q[0]) for q in pts) - 0.011):
                break
            pts.append(np.array([hh[0][0], y, float(z)]))
            y += 0.006
        if len(pts) < 6:
            continue
        _prof.append((float(z), np.array(pts)))
    _tz = np.array([q[0] for q in _prof]); _ty = np.array([q[1][-1][1] for q in _prof])
    _tk = np.polyfit(_tz, _ty, 1)
    _tk[1] -= max(0.003, float((np.polyval(_tk, _tz) - _ty).max()))
    for z, pts in _prof:
        ytop = float(np.polyval(_tk, z))
        keep = pts[pts[:, 1] <= ytop]
        if len(keep) < len(pts) and len(keep) >= 2:
            a_, b_ = pts[len(keep) - 1], pts[len(keep)]
            keep = np.vstack([keep, a_ + (b_ - a_) * ((ytop - a_[1]) / (b_[1] - a_[1]))])
        pts = keep
        ln_ = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
        row = []
        for fv in np.linspace(0, 1, _NPB):
            q = np.array([np.interp(fv * ln_[-1], ln_, pts[:, k]) for k in range(3)])
            q2 = np.array([np.interp(min(fv * ln_[-1] + 0.004, ln_[-1]), ln_, pts[:, k]) for k in range(3)])
            q1 = np.array([np.interp(max(fv * ln_[-1] - 0.004, 0.0), ln_, pts[:, k]) for k in range(3)])
            tg = unit(q2 - q1)
            nrm = unit(np.array([tg[1], -tg[0], 0.0]))
            nrm = nrm if nrm[0] > 0 else -nrm
            fz = ((z - 6.335) / _QW) % 1.0
            fp = float(np.clip((fv * ln_[-1] - 0.016) / max(ln_[-1] - 0.016, 1e-6), 0.0, 1.0))
            puff = 0.0022 + 0.0030 * abs(math.sin(math.pi * fz)) * math.sin(math.pi * fp) ** 0.6
            row.append(q + nrm * puff)
        _rows.append(row)
        _foot.append((float(z), abs(float(pts[1][0]))))
    _rows = np.array(_rows)
    _nr = len(_rows)
    _gn = np.zeros_like(_rows)
    for i in range(_nr):
        for j in range(_NPB):
            dz_ = _rows[min(i + 1, _nr - 1), j] - _rows[max(i - 1, 0), j]
            dv_ = _rows[i, min(j + 1, _NPB - 1)] - _rows[i, max(j - 1, 0)]
            nn_ = unit(np.cross(dz_, dv_))
            _gn[i, j] = nn_ if nn_[0] > 0 else -nn_
    for i in range(_nr - 1):
        for j in range(_NPB - 1):
            a0, a1, b0, b1 = _rows[i, j], _rows[i, j + 1], _rows[i + 1, j], _rows[i + 1, j + 1]
            blk.tri(a0, b0, b1, _gn[i, j], _gn[i + 1, j], _gn[i + 1, j + 1])
            blk.tri(a0, b1, a1, _gn[i, j], _gn[i + 1, j + 1], _gn[i, j + 1])
    for i_ in (0, _nr - 1):
        sgn = -1.0 if i_ == 0 else 1.0
        en = np.array([0.0, 0.0, sgn])
        for j in range(_NPB - 1):
            a0, a1 = _rows[i_, j], _rows[i_, j + 1]
            blk.tri(a0, a1, a1 - np.array([0.008, 0, 0]), en, en, en)
            blk.tri(a0, a1 - np.array([0.008, 0, 0]), a0 - np.array([0.008, 0, 0]), en, en, en)
    blk.tube([_rows[i, -1] for i in range(0, _nr, 2)] + [_rows[-1, -1]], 0.0030, 6)
    for i in range(0, _nr, 4):
        blk.tube([_rows[i, j] + _gn[i, j] * 0.0004 for j in range(1, _NPB)], 0.0011, 4)
    _zf = np.array([q[0] for q in _foot]); _xf = np.array([q[1] for q in _foot])
    _kx = np.polyfit(_zf, _xf, 2)
    _sec = []
    for z in _zf:
        xs = float(np.polyval(_kx, z))
        yl = plate_y(-(xs - 0.0042), z)
        if yl is None:
            _sec.append(None)
            continue
        _sec.append([np.array([-(xs - 0.0014), yl + 0.0080, z]), np.array([-(xs - 0.0042), yl + 0.0080, z]), np.array([-(xs - 0.0042), yl - 0.0006, z])])
    _nt = 0
    _fn = (np.array([0.0, 1.0, 0.0]), np.array([1.0, 0.0, 0.0]))
    for i in range(len(_sec) - 1):
        sa_, sb_ = _sec[i], _sec[i + 1]
        if sa_ is None or sb_ is None:
            continue
        for j in range(2):
            trim.tri(sa_[j], sb_[j], sb_[j + 1], _fn[j], _fn[j], _fn[j])
            trim.tri(sa_[j], sb_[j + 1], sa_[j + 1], _fn[j], _fn[j], _fn[j])
        _nt += 1
    for i_, sgn in ((0, -1.0), (len(_sec) - 1, 1.0)):
        if _sec[i_] is not None:
            en = np.array([0.0, 0.0, sgn]); q_ = _sec[i_]
            trim.tri(q_[0], q_[1], q_[2], en, en, en)
            trim.tri(q_[0], q_[2], q_[2] - np.array([0.0028, 0, 0]), en, en, en)
    for i in range(2, len(_sec) - 1, 8):
        if _sec[i] is not None:
            c_ = (_sec[i][1] + _sec[i][2]) / 2 + np.array([0, 0.0006, 0])
            scr.cyl(c_ - np.array([0.0002, 0, 0]), c_ + np.array([0.0009, 0, 0]), 0.0021, 8)
    print("left console wall: blanket of %d x %d points, z %.3f .. %.3f, %.0f .. %.0f mm tall, from 4 mm under the plate's top; strip of %d pieces along its foot (wall at the plate x %.4f .. %.4f)" % (
        _nr, _NPB, _rows[0, 0, 2], _rows[-1, 0, 2], (_rows[:, -1, 1] - _rows[:, 0, 1]).min() * 1000, (_rows[:, -1, 1] - _rows[:, 0, 1]).max() * 1000, _nt, _xf.min(), _xf.max()))
blk.emit("cockpit_wallblanket", "ckblanket")
trim.emit("cockpit_walltrim", "ckmetaldark")

aftp, aftd, afth, aftst = Soup(), Soup(0.0025), Soup(), Soup(0.0008)


def aft_hit(x, z, y0=1.30):
    h = SHELL.ray_cast(_Vec((float(x), y0, float(z))), _Vec((0, -1.0, 0)), 0.9)
    return None if h[0] is None else np.array(h[0])


def aft_frame(x, z, e=0.012):
    p = aft_hit(x, z)
    q = [aft_hit(x - e, z), aft_hit(x + e, z), aft_hit(x, z - e), aft_hit(x, z + e)]
    if p is None or any(v is None for v in q):
        return None
    u, w = unit(q[1] - q[0]), unit(q[3] - q[2])
    n = unit(np.cross(w, u))
    return p, u, w, (n if n[1] > 0 else -n)


def drape(soup, x0, x1, z0, z1, h, nx=6, nz=8, screws=0.05):
    xs_, zs_ = np.linspace(x0, x1, nx + 1), np.linspace(z0, z1, nz + 1)
    grid = [[aft_frame(x, z) for z in zs_] for x in xs_]
    if any(g is None for row in grid for g in row):
        return False
    top = [[g[0] + g[3] * h for g in row] for row in grid]
    for i in range(nx):
        for j in range(nz):
            a, b, c, d = top[i][j], top[i + 1][j], top[i + 1][j + 1], top[i][j + 1]
            na, nb, nc, nd = grid[i][j][3], grid[i + 1][j][3], grid[i + 1][j + 1][3], grid[i][j + 1][3]
            soup.tri(a, b, c, na, nb, nc); soup.tri(a, c, d, na, nc, nd)
    edge_ = [(i, 0) for i in range(nx + 1)] + [(nx, j) for j in range(1, nz + 1)] + [(i, nz) for i in range(nx - 1, -1, -1)] + [(0, j) for j in range(nz - 1, 0, -1)]
    cen = np.array([(x0 + x1) / 2, 0, (z0 + z1) / 2])
    for k in range(len(edge_)):
        (i0, j0), (i1, j1) = edge_[k], edge_[(k + 1) % len(edge_)]
        a, b = top[i0][j0], top[i1][j1]
        a_, b_ = grid[i0][j0][0] - grid[i0][j0][3] * 0.001, grid[i1][j1][0] - grid[i1][j1][3] * 0.001
        m_ = (a + b) / 2 - cen
        on_ = np.array([np.sign(m_[0]), 0.0, 0.0]) if abs(m_[0]) / (x1 - x0) > abs(m_[2]) / (z1 - z0) else np.array([0.0, 0.0, np.sign(m_[2])])
        soup.tri(a, b, b_, on_, on_, on_); soup.tri(a, b_, a_, on_, on_, on_)
    if screws:
        per = [(x, z0 + 0.009) for x in np.linspace(x0 + 0.009, x1 - 0.009, max(int(round((x1 - x0) / screws)), 1) + 1)]
        per += [(x, z1 - 0.009) for x in np.linspace(x0 + 0.009, x1 - 0.009, max(int(round((x1 - x0) / screws)), 1) + 1)]
        per += [(xx, z) for xx in (x0 + 0.009, x1 - 0.009) for z in np.linspace(z0 + 0.009, z1 - 0.009, max(int(round((z1 - z0) / screws)), 1) + 1)[1:-1]]
        for (x, z) in per:
            fr = aft_frame(x, z)
            if fr is not None:
                scr.cyl(fr[0] + fr[3] * (h - 0.0002), fr[0] + fr[3] * (h + 0.0009), 0.0030, 10)
    return True


def connector(soup, p, ax, r=0.009, L=0.016):
    ax = unit(ax)
    soup.cyl(p, p + ax * L, r, 14)
    lug.cyl(p + ax * (L * 0.55), p + ax * (L * 0.85), r * 1.22, 8)
    return p + ax * L


def clip(p, along, up, r):
    side = unit(np.cross(along, up))
    lug.box(p, along, side, up, 0.006, r + 0.0018, r + 0.0018)
    lug.box(p + side * (r + 0.008) - up * (r - 0.001), along, side, up, 0.006, 0.007, 0.0012)
    q = p + side * (r + 0.009) - up * (r - 0.0022)
    scr.cyl(q, q + up * 0.0012, 0.0026, 8)


cab2 = Soup()
n_aft = [0, 0]
if not os.environ.get("NO_AFT_DETAIL"):
    _PH = 0.0016
    for sx in (1, -1):
        for (z0, z1) in ((6.062, 6.268), (5.800, 6.032)):
            n_aft[0] += drape(aftp, min(sx * 0.212, sx * 0.338), max(sx * 0.212, sx * 0.338), z0, z1, _PH, nx=5, nz=8)
    for (z0, z1) in ((6.062, 6.268), (5.800, 6.032)):
        n_aft[0] += drape(aftp, -0.188, 0.188, z0, z1, _PH, nx=12, nz=8)
    def riser(x, y):
        h = SHELL.ray_cast(_Vec((float(x), float(y), 5.95)), _Vec((0, 0, -1.0)), 0.5)
        return None if h[0] is None else (np.array(h[0]), np.array(h[1]))
    for sx in (1, -1):
        fr = aft_frame(sx * 0.275, 6.165)
        if fr is None:
            continue
        p0, u, w, n = fr
        base = p0 + n * _PH
        if sx > 0:
            hx, hz, hh = 0.046, 0.078, 0.056
            aftd.box(base + n * (hh / 2 - 0.002), u, w, n, hx, hz, hh / 2)
            aftd.box(base + n * (hh + 0.0015), u, w, n, hx + 0.003, hz + 0.003, 0.0025)
            for k in range(7):
                aftd.box(base + n * (hh + 0.0085) + w * (-0.054 + 0.018 * k), u, w, n, hx - 0.006, 0.0022, 0.0055)
            for (du, dw) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                q = base + u * (du * (hx - 0.008)) + w * (dw * (hz - 0.008)) + n * (hh + 0.004)
                scr.cyl(q, q + n * 0.0014, 0.0030, 8)
            plac_quad(base - u * (hx + 0.0006) + n * (hh * 0.55), -w, n, -u, 0.060, 0.038, "name")
            ends = []
            for k, du in enumerate((-0.020, 0.020)):
                c0 = base + u * du - w * hz + n * (hh * 0.50)
                ends.append(connector(aftd, c0, -w))
        else:
            rb, hl = 0.036, 0.085
            c_ = base + n * (rb + 0.012)
            afth.cyl(c_ - w * hl, c_ + w * hl, rb, 20)
            afth.cyl(c_ + w * hl, c_ + w * (hl + 0.016), rb, 20, rb * 0.55)
            afth.cyl(c_ - w * hl, c_ - w * (hl + 0.016), rb, 20, rb * 0.55)
            for dz_ in (-0.045, 0.045):
                aftd.box(c_ + w * dz_ - n * (rb * 0.62 + 0.004), u, w, n, rb + 0.006, 0.011, rb * 0.42)
                aftst.box(c_ + w * dz_ + n * 0.0005, u, w, n, rb + 0.0015, 0.009, rb + 0.0015)
            v0 = c_ - w * (hl + 0.016)
            lug.cyl(v0, v0 - w * 0.026, 0.011, 10)
            lug.cyl(v0 - w * 0.016 - n * 0.004, v0 - w * 0.016 + n * 0.024, 0.0075, 10)
            scr.cyl(v0 - w * 0.016 + n * 0.024, v0 - w * 0.016 + n * 0.030, 0.012, 14)
            ends = [v0 - w * 0.026]
        for k, e0 in enumerate(ends):
            xr = sx * (0.262 + 0.030 * k)
            f1, f2 = aft_frame(xr, 5.98), aft_frame(xr, 5.84)
            rz = riser(xr, 0.90)
            if f1 is None or f2 is None or rz is None:
                continue
            rr = 0.0058 if sx > 0 else 0.0046
            gro = rz[0] + np.array([0.0, -0.012, 0.0])
            hp_ = [e0, e0 - w * 0.030 - n * 0.006, f1[0] + f1[3] * (_PH + rr + 0.001), f2[0] + f2[3] * (_PH + rr + 0.001),
                   gro + np.array([0.0, -0.004, 0.045]), gro + np.array([0.0, 0.0, 0.004])]
            hose(cab2, hp_, rr)
            ferrule(lug, e0, -w, rr)
            lug.cyl(gro + np.array([0, 0, 0.001]), gro + np.array([0, 0, 0.007]), rr * 2.1, 14)
            for fz_ in (f1, f2):
                clip(fz_[0] + fz_[3] * (_PH + rr + 0.001), fz_[2], fz_[3], rr)
            n_aft[1] += 1
        for xr in np.arange(0.045, 0.335, 0.032):
            for yy in (0.865, 0.945):
                rz = riser(sx * xr, yy)
                if rz is not None and abs(rz[1][2]) > 0.6:
                    scr.cyl(rz[0], rz[0] + np.array([0, 0, 0.0012]), 0.0026, 8)
        seg_ = [riser(sx * xr, 0.905) for xr in np.arange(0.03, 0.340, 0.031)]
        seg_ = [q[0] for q in seg_ if q is not None and abs(q[1][2]) > 0.6]
        for a, b in zip(seg_[:-1], seg_[1:]):
            dd = unit(b - a)
            aftp.box((a + b) / 2 + np.array([0, 0, 0.003]), dd, _Y, np.cross(dd, _Y), np.linalg.norm(b - a) / 2 + 0.0005, 0.007, 0.003)
        rz = riser(sx * 0.155, 0.872)
        if rz is not None:
            plac_quad(rz[0] + np.array([0, 0, 0.0008]), np.array([-1.0, 0, 0]), _Y, _Z, 0.084, 0.028, "caution")
    for sx in (1, -1):
        fr = aft_frame(sx * 0.095, 5.50)
        if fr is None:
            continue
        p0, u, w, n = fr
        aftd.box(p0 + n * 0.022, u, w, n, 0.038, 0.062, 0.024)
        aftd.box(p0 + n * 0.0475, u, w, n, 0.040, 0.064, 0.002)
        for (du, dw) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            q = p0 + u * (du * 0.031) + w * (dw * 0.055) + n * 0.0495
            scr.cyl(q, q + n * 0.0012, 0.0028, 8)
        e0 = connector(aftd, p0 + w * 0.062 + n * 0.024 - u * (sx * 0.012), w, 0.008, 0.014)
        f1 = aft_frame(sx * 0.050, 5.615)
        if f1 is not None:
            hose(cab2, [e0, e0 + w * 0.02, f1[0] + f1[3] * 0.008, np.array([sx * 0.012, f1[0][1] + 0.004, 5.66])], 0.0050)
            ferrule(lug, e0, w, 0.0050)
    print("behind the seat: %d access panels, %d hoses to the riser" % (n_aft[0], n_aft[1]))
aftp.emit("cockpit_aftpanels", "ckplate")
aftd.emit("cockpit_aftboxes", "ckbezel")
afth.emit("cockpit_aftbottle", "ckpad")
aftst.emit("cockpit_aftstraps", "ckstrap")
cab2.emit("cockpit_aftcables", "ckdetail")
hang.emit("cockpit_pedalhangers", "ckliner")
wall.emit("cockpit_sillwall", "ckwall")
blank.emit("cockpit_blankplates", "ckplate")
box_.emit("cockpit_sensorbox", "ckmetaldark")
lens_.emit("cockpit_sensorlens", "cklens")
dot_.emit("cockpit_sensordot", "ckwhite")
rail.emit("cockpit_sillrail", "ckrail")
lug.emit("cockpit_silllugs", "ckmetaldark")

DT = []
for f in FRAME_F:
    p = V[[c[0] - 1 for c in f]]
    if p[:, 2].min() > 7.40 and p[:, 1].max() < 1.06 and np.abs(p[:, 0]).max() < 0.40:
        for k in range(1, len(p) - 1):
            DT.append((p[0], p[k], p[k + 1]))


def deck_y(x, z):
    best = None
    for a, b, c in DT:
        d0 = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
        if abs(d0) < 1e-12:
            continue
        l0 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d0
        l1 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d0
        l2 = 1 - l0 - l1
        if min(l0, l1, l2) >= -1e-6:
            y = l0 * a[1] + l1 * b[1] + l2 * c[1]
            best = y if best is None else max(best, y)
    return best


def deck_frame(x, z, e=0.02):
    y = deck_y(x, z)
    yx0, yx1, yz0, yz1 = deck_y(x - e, z), deck_y(x + e, z), deck_y(x, z - e), deck_y(x, z + e)
    if None in (y, yx0, yx1, yz0, yz1):
        return None
    u = unit([2 * e, yx1 - yx0, 0])
    w = unit([0, yz1 - yz0, 2 * e])
    n = unit(np.cross(w, u))
    if n[1] < 0:
        n = -n
    return np.array([x, y, z]), u, w, n


deck, slot = Soup(), Soup()
n_deck = 0
if DT:
    for sx in (1, -1):
        fr = deck_frame(sx * 0.150, 7.70)
        if fr is None:
            continue
        p, u, w, n = fr
        deck.box(p - n * 0.0015, u, w, n, 0.052, 0.074, 0.0105)
        for k in (-1, 0, 1):
            c = p + w * (k * 0.044) + n * 0.0092
            slot.box(c, u, w, n, 0.042, 0.016, 0.0006)
            wl = unit(w * math.cos(math.radians(32)) + n * math.sin(math.radians(32)))
            deck.box(c + w * 0.006 + n * 0.005, u, wl, np.cross(u, wl), 0.042, 0.011, 0.0012)
        for i in (-1, 1):
            for j in (-1, 1):
                c = p + u * (i * 0.046) + w * (j * 0.068) + n * 0.009
                scr.cyl(c, c + n * 0.0014, 0.0032, 10)
        n_deck += 1
    zs = np.arange(7.50, 8.26, 0.06)
    for z0, z1 in zip(zs[:-1], zs[1:]):
        a, b = deck_y(0.0, z0), deck_y(0.0, z1)
        if a is None or b is None:
            continue
        pa, pb = np.array([0, a, z0]), np.array([0, b, z1])
        w = unit(pb - pa)
        n = unit(np.cross(w, [1.0, 0, 0]))
        if n[1] < 0:
            n = -n
        deck.box((pa + pb) / 2 + n * 0.002, [1.0, 0, 0], w, n, 0.045, np.linalg.norm(pb - pa) / 2 + 0.002, 0.004)
        for sx in (1, -1):
            c = (pa + pb) / 2 + n * 0.006 + np.array([sx * 0.036, 0, 0])
            scr.cyl(c, c + n * 0.0014, 0.003, 10)
    for sx in (1, -1):
        for z in np.arange(7.50, 8.10, 0.045):
            fr = deck_frame(sx * (0.27 - (z - 7.5) * 0.12), z, 0.012)
            if fr is not None:
                scr.cyl(fr[0], fr[0] + fr[3] * 0.0016, 0.0032, 10)
deck.emit("cockpit_deck", "ckdeck")

import bpy
from mathutils import Vector as _Vec
from mathutils.geometry import tessellate_polygon as _tess

bez = Soup()
eye = np.array([0.0, 1.16, 6.5])


def components(faces):
    key, par = {}, {}

    def kid(i):
        return key.setdefault(tuple(np.round(V[i - 1], 4)), len(key))

    def find(a):
        while par.setdefault(a, a) != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for f in faces:
        ks = [kid(c[0]) for c in f]
        for a in ks[1:]:
            par[find(a)] = find(ks[0])
    out = {}
    for f in faces:
        out.setdefault(find(kid(f[0][0])), set()).update(c[0] - 1 for c in f)
    return [V[sorted(v)] for v in out.values()]


def rrect_loop(cx, cy, hw, hh, r, seg=5):
    r = max(min(r, hw - 2e-4, hh - 2e-4), 1e-4)
    pts, dirs = [], []
    for sx, sy, a0 in ((1, 1, 0.0), (-1, 1, 90.0), (-1, -1, 180.0), (1, -1, 270.0)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90.0 * i / seg)
            pts.append((cx + sx * (hw - r) + r * math.cos(a), cy + sy * (hh - r) + r * math.sin(a)))
            dirs.append((math.cos(a), math.sin(a)))
    return np.array(pts), np.array(dirs)


def circle_loop(cx, cy, r, seg=20):
    a = np.arange(seg) * (2 * math.pi / seg)
    d = np.stack([np.cos(a), np.sin(a)], 1)
    return np.array([cx, cy]) + d * r, d


def poly_loop(corners, r, seg=4):
    c_ = [np.array(q, float) for q in corners]
    pts, dirs = [], []
    for i in range(len(c_)):
        p0, p1, p2 = c_[i - 1], c_[i], c_[(i + 1) % len(c_)]
        d1, d2 = unit(p0 - p1), unit(p2 - p1)
        half = math.acos(float(np.clip(d1 @ d2, -1, 1))) / 2
        t_ = min(r / math.tan(half), 0.45 * min(np.linalg.norm(p0 - p1), np.linalg.norm(p2 - p1)))
        rr = t_ * math.tan(half)
        cen = p1 + unit(d1 + d2) * (rr / math.sin(half))
        v0, v1 = p1 + d1 * t_ - cen, p1 + d2 * t_ - cen
        th0 = math.atan2(v0[1], v0[0])
        dth = math.atan2(v0[0] * v1[1] - v0[1] * v1[0], float(v0 @ v1))
        for k in range(seg + 1):
            a = th0 + dth * k / seg
            dirs.append((math.cos(a), math.sin(a)))
            pts.append(cen + rr * np.array(dirs[-1]))
    return np.array(pts), np.array(dirs)


def plate_top(soup, P, N, outer, holes, h):
    loops = [outer] + [hl[::-1] for hl in holes]
    flat = [q for lp in loops for q in lp]
    for a, b, c in _tess([[_Vec((float(q[0]), float(q[1]), 0.0)) for q in lp] for lp in loops]):
        pa, pb, pc = (P(flat[k][0], flat[k][1], h) for k in (a, b, c))
        if np.linalg.norm(np.cross(pb - pa, pc - pa)) > 1e-12:
            soup.tri(pa, pb, pc, N, N, N)


def screw_head(P, U, W, N, a, b, h, r=0.0023):
    c = P(a, b, h)
    scr.cyl(c, c + N * 0.0006, r, 12)
    k = (hash((round(a * 1e4), round(b * 1e4))) % 90) * math.pi / 180
    for ang in (k, k + math.pi / 2):
        d_ = U * math.cos(ang) + W * math.sin(ang)
        slot.box(c + N * 0.00062, d_, np.cross(N, d_), N, r * 0.72, r * 0.16, 0.00008)


SCR = {}
for l in open(os.path.join(ST, "typhoon_cockpit.txt")):
    t = l.split()
    if len(t) >= 14 and t[0] == "screen":
        SCR[t[1]] = np.array([float(x) for x in t[2:14]]).reshape(4, 3)
unitd = Soup()
umark = Soup()
utext = Soup()
UWORDS = ["BRT", "BAL", "OFF", "ON"]


def word_quad(P, U, W, N, a, b, h, word, wd=0.00725, ht=0.003625):
    k = UWORDS.index(word)
    u0, v1 = (k % 2) * 0.5, 1.0 - (k // 2) * 0.5
    q = [(a - wd / 2, b - ht / 2, u0, v1 - 0.5), (a + wd / 2, b - ht / 2, u0 + 0.5, v1 - 0.5), (a + wd / 2, b + ht / 2, u0 + 0.5, v1), (a - wd / 2, b + ht / 2, u0, v1)]
    for i, j, k_ in ((0, 1, 2), (0, 2, 3)):
        utext.tri(P(q[i][0], q[i][1], h), P(q[j][0], q[j][1], h), P(q[k_][0], q[k_][1], h), N, N, N, (q[i][2:], q[j][2:], q[k_][2:]))

unitp, unite = Soup(), Soup()
HT, BV = 0.0046, 0.0007
CH, LIP, GLS = 0.0065, 0.0019, 0.0006
CL, MARG = 0.0009, 0.0045
keycomps = components(G.get("cockpit_keys", []))
ctlcomps = components(G.get("cockpit_controls", []))
frames = {}
for nm in ("mfd_L", "mfd_C", "mfd_R"):
    if nm not in SCR:
        continue
    q = SCR[nm]
    u, v = unit(q[1] - q[0]), unit(q[0] - q[3])
    n = unit(np.cross(u, v))
    if n @ (eye - q.mean(0)) < 0:
        n = -n
    v = np.cross(n, u) if np.cross(n, u) @ v > 0 else -np.cross(n, u)
    frames[nm] = (q.mean(0), u, v, n, np.linalg.norm(q[1] - q[0]) / 2, np.linalg.norm(q[0] - q[3]) / 2)
ukeys = {nm: [] for nm in frames}
for kc in keycomps:
    c = kc.mean(0)
    best = None
    for nm, (o, u, v, n, gw, gh) in frames.items():
        cu, cv, cw = (c - o) @ u, (c - o) @ v, (c - o) @ n
        d = math.hypot(max(abs(cu) - gw, 0), max(abs(cv) - gh, 0))
        if abs(cw) < 0.03 and d < 0.045 and (best is None or d < best[0]):
            best = (d, nm)
    if best:
        o, u, v, n, gw, gh = frames[best[1]]
        pu, pv, pw = (kc - o) @ u, (kc - o) @ v, (kc - o) @ n
        ukeys[best[1]].append((float(pu.min()), float(pu.max()), float(pv.min()), float(pv.max()), float(pw.min())))
for nm, (o, u, v, n, gw, gh) in frames.items():
    keys = ukeys[nm]
    if len(keys) < 6:
        print("%s: only %d keys found round it - no housing built" % (nm, len(keys)))
        continue
    w0 = float(np.median([k[4] for k in keys]))
    P = lambda a, b, h=0.0, o=o, u=u, v=v, n=n, w0=w0: o + u * a + v * b + n * (w0 + h)
    x0 = min(min(k[0] for k in keys), -gw) - CL - MARG
    x1 = max(max(k[1] for k in keys), gw) + CL + MARG
    y0 = min(min(k[2] for k in keys), -gh) - CL - MARG
    y1 = max(max(k[3] for k in keys), gh + CH) + CL + MARG
    knobs = []
    for cc in ctlcomps:
        pu, pv, pw = (cc - o) @ u, (cc - o) @ v, (cc - o) @ n - w0
        if x0 < pu.mean() < x1 and y0 < pv.mean() < y1 and pw.min() > -0.004 and pw.max() < 0.03 and pw.min() < 0.006:
            ca, cb = (pu.min() + pu.max()) / 2, (pv.min() + pv.max()) / 2
            rr = float(np.hypot(pu - ca, pv - cb).max())
            for kb in knobs:
                if math.hypot(kb[0] - ca, kb[1] - cb) < 0.008:
                    kb[2] = max(kb[2], rr + math.hypot(kb[0] - ca, kb[1] - cb))
                    break
            else:
                knobs.append([ca, cb, rr])
    outer, odir = rrect_loop((x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2, 0.007, 6)
    glass, gdir = rrect_loop(0.0, 0.0, gw - 0.0003, gh - 0.0003, 0.0085, 8)
    holes, walls = [glass + gdir * CH], []
    for k in keys:
        lp, ld = rrect_loop((k[0] + k[1]) / 2, (k[2] + k[3]) / 2, (k[1] - k[0]) / 2 + CL, (k[3] - k[2]) / 2 + CL, 0.0016, 2)
        holes.append(lp)
        walls.append((lp, ld))
    for ca, cb, rr in knobs:
        lp, ld = circle_loop(ca, cb, rr + 0.0011, 20)
        holes.append(lp)
        walls.append((lp, ld))
    plate_top(unitp, P, n, outer - odir * BV, holes, HT)
    unite.sweep(P, u, v, n, outer, odir, [(-BV, HT), (0.0, HT - BV)], 1)
    unitp.sweep(P, u, v, n, outer, odir, [(0.0, HT - BV), (0.0, 0.0)], 1)
    _k = 0.0008 / CH
    unite.sweep(P, u, v, n, glass, gdir, [(CH, HT), (CH * (1 - _k), HT - (HT - LIP) * _k)], -1)
    unitp.sweep(P, u, v, n, glass, gdir, [(CH * (1 - _k), HT - (HT - LIP) * _k), (0.0, LIP)], -1)
    unitd.sweep(P, u, v, n, glass, gdir, [(0.0, LIP), (0.0, GLS)], -1)
    for lp, ld in walls:
        unitd.sweep(P, u, v, n, lp, ld, [(0.0, HT), (0.0, 0.0)], -1)
    n_s = 0
    for side in (-1, 1):
        col = sorted([k for k in keys if side * (k[0] + k[1]) / 2 > gw and y0 + 0.02 < (k[2] + k[3]) / 2], key=lambda k: k[2])
        for i in range(0, len(col) - 1, 2):
            if col[i + 1][2] - col[i][3] > 0.0075:
                screw_head(P, u, v, n, (col[i][0] + col[i][1] + col[i + 1][0] + col[i + 1][1]) / 4, (col[i][3] + col[i + 1][2]) / 2, HT)
                n_s += 1
        screw_head(P, u, v, n, side * gw * 0.62, (gh + CH + y1) / 2, HT)
    row = sorted([k for k in keys if (k[2] + k[3]) / 2 < -gh and abs((k[0] + k[1]) / 2) < gw], key=lambda k: k[0])
    for i in (0, len(row) - 2):
        if 0 <= i < len(row) - 1 and row[i + 1][0] - row[i][1] > 0.0075:
            screw_head(P, u, v, n, (row[i][1] + row[i + 1][0]) / 2, (row[i][2] + row[i][3] + row[i + 1][2] + row[i + 1][3]) / 4, HT)
            n_s += 1
    for ca, cb, rr in knobs:
        if not row:
            break
        sgn = 1 if ca > 0 else -1
        he = ca - sgn * (rr + 0.0011)
        ke = (row[-1][1] + CL) if sgn > 0 else (row[0][0] - CL)
        if abs(he - ke) > 0.0085:
            ra = (he + ke) / 2
            slot.box(P(ra, cb, HT + 0.0001), u, v, n, 0.0031, 0.0072, 0.0001)
            scr.box(P(ra, cb, HT + 0.0009), u, v, n, 0.0026, 0.0066, 0.0009)
            for sy in (1, -1):
                umark.box(P(ra, cb + sy * 0.0036, HT + 0.00185), u, v, n, 0.0011, 0.00022, 0.00005)
            umark.box(P(ra, cb + 0.0036, HT + 0.00185), v, u, n, 0.0011, 0.00022, 0.00005)
            word_quad(P, u, v, n, ra, cb - 0.0094, HT + 0.00015, "BRT" if sgn < 0 else "BAL")
    yb_ = (gh + CH + y1) / 2
    slot.box(P(0.0, yb_, HT + 0.0001), u, v, n, 0.0075, 0.0022, 0.0001)
    scr.box(P(-0.0030, yb_, HT + 0.0010), u, v, n, 0.0022, 0.0019, 0.0010)
    word_quad(P, u, v, n, -0.0118, yb_, HT + 0.00015, "OFF")
    word_quad(P, u, v, n, 0.0118, yb_, HT + 0.00015, "ON")
    DROP, TH = 0.0125, HT * 0.72
    n_lug = 0
    sq = None
    for cc in keycomps + ctlcomps:
        pu, pv, pw = (cc - o) @ u, (cc - o) @ v, (cc - o) @ n - w0
        if abs(pu.mean()) < 0.008 and y0 - 0.032 < pv.mean() < y0 - 0.004 and -0.002 < pw.min() and pw.max() < 0.012 and pu.max() - pu.min() < 0.03:
            q_ = (float(pu.min()), float(pu.max()), float(pv.min()), float(pv.max()), float(pw.max()))
            sq = q_ if sq is None else (min(sq[0], q_[0]), max(sq[1], q_[1]), min(sq[2], q_[2]), max(sq[3], q_[3]), max(sq[4], q_[4]))
    for tw in (0.31 * (x1 - x0), 0.24 * (x1 - x0), 0.17 * (x1 - x0)):
        bx0, bx1, by0, by1 = -tw - 0.002, tw + 0.002, y0 - DROP - 0.002, y0 - 0.0005
        clash = False
        for cc in ctlcomps + keycomps:
            pu, pv, pw = (cc - o) @ u, (cc - o) @ v, (cc - o) @ n - w0
            if sq is not None and sq[0] - 1e-4 < pu.min() and pu.max() < sq[1] + 1e-4 and sq[2] - 1e-4 < pv.min() and pv.max() < sq[3] + 1e-4:
                continue
            if pw.min() < 0.03 and pw.max() > -0.01 and pu.max() > bx0 and pu.min() < bx1 and pv.max() > by0 and pv.min() < by1:
                clash = True
                if os.environ.get("LUG_DEBUG"):
                    print("   lug %s tw %.0f: clash u %.1f..%.1f v %.1f..%.1f w %.1f..%.1f n=%d" % (nm, tw * 1000, pu.min() * 1000, pu.max() * 1000, (pv.min() - y0) * 1000, (pv.max() - y0) * 1000, pw.min() * 1000, pw.max() * 1000, len(cc)))
                break
        if clash:
            continue
        yc = y0 - DROP / 2 + 0.0012
        tab, tdir = rrect_loop(0.0, y0 - DROP / 2 + 0.002, tw, DROP / 2 + 0.002, 0.0045, 5)
        hl = []
        for sgn in (-1, 1):
            for f_ in (0.50, 0.68, 0.86):
                lp, ld = circle_loop(sgn * f_ * tw, yc, 0.0027, 14)
                hl.append((lp, ld))
        plate_top(unitp, P, n, tab - tdir * BV, [h_[0] for h_ in hl], TH)
        unite.sweep(P, u, v, n, tab, tdir, [(-BV, TH), (0.0, TH - BV)], 1)
        unitp.sweep(P, u, v, n, tab, tdir, [(0.0, TH - BV), (0.0, 0.0)], 1)
        for lp, ld in hl:
            unitd.sweep(P, u, v, n, lp, ld, [(0.0, TH), (0.0, 0.0008)], -1)
            plate_top(unitd, P, n, lp, [], 0.0008)
        for sgn in (-1, 1):
            screw_head(P, u, v, n, sgn * 0.34 * tw, yc, TH, r=0.0019)
        sc_, sw_ = (0.0, yc), TH
        if sq is not None:
            TH2 = TH + 0.0007
            lx, ly = (sq[0] + sq[1]) / 2, (y0 + 0.002 + sq[2] - 0.0045) / 2
            lobe, ldir = rrect_loop(lx, ly, (sq[1] - sq[0]) / 2 + 0.0048, (y0 + 0.002 - (sq[2] - 0.0045)) / 2, 0.0040, 5)
            pk_, pkd = rrect_loop(lx, (sq[2] + sq[3]) / 2, (sq[1] - sq[0]) / 2 + CL, (sq[3] - sq[2]) / 2 + CL, 0.0016, 2)
            plate_top(unitp, P, n, lobe - ldir * BV, [pk_], TH2)
            unite.sweep(P, u, v, n, lobe, ldir, [(-BV, TH2), (0.0, TH2 - BV)], 1)
            unitp.sweep(P, u, v, n, lobe, ldir, [(0.0, TH2 - BV), (0.0, 0.0)], 1)
            unitd.sweep(P, u, v, n, pk_, pkd, [(0.0, TH2), (0.0, 0.0)], -1)
            sc_, sw_ = (lx, (sq[2] + sq[3]) / 2), sq[4]
        unite.cyl(P(sc_[0], sc_[1], sw_), P(sc_[0], sc_[1], sw_ + 0.0012), 0.0060, 20, r2=0.0056)
        unitd.cyl(P(sc_[0], sc_[1], sw_ + 0.0012), P(sc_[0], sc_[1], sw_ + 0.0034), 0.0046, 16, r2=0.0026)
        unitd.cyl(P(sc_[0], sc_[1], sw_ + 0.0034), P(sc_[0], sc_[1], sw_ + 0.0060), 0.0020, 10)
        unitp.cyl(P(sc_[0], sc_[1], sw_ + 0.0060), P(sc_[0], sc_[1], sw_ + 0.0084), 0.0040, 14, r2=0.0034)
        n_lug = 1
        break
    print("%s: lug %s" % (nm, ("built, half width %.0f mm%s" % (tw * 1000, ", with the cursor key" if sq is not None else "")) if n_lug else "left out (no clear space under the housing)"))
    print("%s: display unit %.0f x %.0f mm, glass %.0f x %.0f mm, %d key pockets, %d knob holes, %d screws" %
          (nm, (x1 - x0) * 1000, (y1 - y0) * 1000, gw * 2000, gh * 2000, len(keys), len(knobs), n_s + 2))
unitp.emit("cockpit_dispunit", "ckunit")
unitd.emit("cockpit_dispwell", "ckunitdark")
unite.emit("cockpit_dispedge", "ckunitedge")
umark.emit("cockpit_dispmarks", "ckwhite")
utext.emit("cockpit_disptext", "ckunittxt")
if "sadi" in SCR:
    q = SCR["sadi"]
    cen = q.mean(0)
    u, v = unit(q[1] - q[0]), unit(q[0] - q[3])
    n = unit(np.cross(u, v))
    if n @ (eye - cen) < 0:
        n = -n
    r_ = 0.5 * min(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[0] - q[3]))
    SEG = 40
    for i in range(SEG):
        a0, a1 = 2 * math.pi * i / SEG, 2 * math.pi * (i + 1) / SEG
        d0, d1 = math.cos(a0) * u + math.sin(a0) * v, math.cos(a1) * u + math.sin(a1) * v
        ri, ro, hh = r_ * 0.985, r_ + 0.006, 0.005
        p = [cen + d0 * ri + n * hh, cen + d1 * ri + n * hh, cen + d1 * (ro - 0.0015) + n * hh, cen + d0 * (ro - 0.0015) + n * hh,
             cen + d0 * ro, cen + d1 * ro, cen + d0 * ri, cen + d1 * ri]
        mid = cen + (d0 + d1) / 2 * ((ri + ro) / 2) + n * (hh / 2)
        bez.piece([(p[0], p[1], p[2]), (p[0], p[2], p[3]), (p[3], p[2], p[5]), (p[3], p[5], p[4]), (p[6], p[7], p[1]), (p[6], p[1], p[0])], mid)
    for i in (-1, 1):
        for j in (-1, 1):
            c = cen + u * (i * (r_ + 0.003)) + v * (j * (r_ + 0.003))
            scr.cyl(c, c + n * 0.0016, 0.003, 10)
if "ufcp" in SCR:
    q = SCR["ufcp"]
    cen = q.mean(0)
    n = unit(np.cross(q[1] - q[0], q[3] - q[0]))
    if n @ (eye - cen) < 0:
        n = -n
    for i in range(4):
        a, b = q[i], q[(i + 1) % 4]
        e = unit(b - a)
        out = unit(np.cross(e, n))
        if out @ ((a + b) / 2 - cen) < 0:
            out = -out
        bez.box((a + b) / 2 + out * 0.0017 + n * 0.0014, e, out, n, np.linalg.norm(b - a) / 2 + 0.003, 0.0013, 0.0022)
face_, sbyh = Soup(), Soup()
sglass = Soup()
SBY_RI, SBY_RO, SBY_RT = 0.0185, 0.0210, 0.0200
SBY = []
PT = []
for f in G.get("cockpit_panel", []):
    p = V[[c[0] - 1 for c in f]]
    for k in range(1, len(p) - 1):
        PT.append((p[0], p[k], p[k + 1]))
tgt = np.array([0.362, 0.790, 7.300])
dray = unit(tgt - eye)
hit = None
for a, b, c in PT:
    e1, e2 = b - a, c - a
    h = np.cross(dray, e2)
    det = e1 @ h
    if abs(det) < 1e-12:
        continue
    s0 = eye - a
    uu = (s0 @ h) / det
    q0 = np.cross(s0, e1)
    vv = (dray @ q0) / det
    tt = (e2 @ q0) / det
    if uu >= 0 and vv >= 0 and uu + vv <= 1 and tt > 0.1 and (hit is None or tt < hit[0]):
        hit = (tt, eye + dray * tt, unit(np.cross(e1, e2)))
if hit is not None and np.linalg.norm(hit[1] - tgt) < 0.08:
    C0, gn_ = hit[1], hit[2]
    if gn_ @ (eye - C0) < 0:
        gn_ = -gn_
    upp = unit(UPV - gn_ * (UPV @ gn_))
    rgt = np.cross(gn_, upp)
    if rgt[0] < 0:
        rgt = -rgt
    PG = lambda a, b, h=0.0: C0 + rgt * a + upp * b + gn_ * h
    HP, HD, HR, HN = 0.0030, 0.0035, 0.0070, 0.0050
    hl, hd = poly_loop([(-0.0245, -0.0610), (0.0265, -0.0610), (0.0265, 0.0620), (0.0120, 0.0760), (-0.0245, 0.0760)], 0.006, 4)
    FT = [(np.array([(q - C0) @ rgt, (q - C0) @ upp]) for q in t3) for t3 in PT
          if abs(unit(np.cross(t3[1] - t3[0], t3[2] - t3[0])) @ gn_) > 0.995 and abs((t3[0] - C0) @ gn_) < 0.0015]
    FT = [tuple(t3) for t3 in FT]

    def on_face(q):
        for a, b, c in FT:
            d0 = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d0) < 1e-14:
                continue
            l0 = ((b[1] - c[1]) * (q[0] - c[0]) + (c[0] - b[0]) * (q[1] - c[1])) / d0
            l1 = ((c[1] - a[1]) * (q[0] - c[0]) + (a[0] - c[0]) * (q[1] - c[1])) / d0
            if min(l0, l1, 1 - l0 - l1) >= -0.02:
                return True
        return False
    n_off = sum(0 if on_face(q) else 1 for q in hl)
    plate_top(sbyh, PG, gn_, hl - hd * 0.0006, [], HP)
    sbyh.sweep(PG, rgt, upp, gn_, hl, hd, [(-0.0006, HP), (0.0, HP - 0.0006), (0.0, 0.0)], 1)
    for sa, sb in ((-0.0205, 0.02925), (0.0225, 0.02925), (-0.0205, -0.01625), (0.0225, -0.01625), (-0.0200, 0.0715), (0.0225, -0.0570)):
        screw_head(PG, rgt, upp, gn_, sa, sb, HP)
    for gi, cy in enumerate((0.0520, 0.0065, -0.0390)):
        cx = 0.0010
        gc_ = PG(cx, cy)
        lp, ld = circle_loop(cx, cy, SBY_RI, 40)
        bez.sweep(PG, rgt, upp, gn_, lp, ld, [(0.0, HD), (0.0009, HR), (SBY_RO - SBY_RI - 0.0010, HR), (SBY_RO - SBY_RI, HR - 0.0010), (SBY_RO - SBY_RI, HP)], 1)
        u0, v0 = (gi % 2) * 0.5 + 0.25, 0.75 - (gi // 2) * 0.5
        rd = SBY_RI + 0.0005
        ring = [(math.cos(2 * math.pi * i / 40) * rd, math.sin(2 * math.pi * i / 40) * rd) for i in range(40)]
        for i in range(40):
            (ax, ay), (bx, by) = ring[i], ring[(i + 1) % 40]
            face_.tri(PG(cx, cy, HD), PG(cx + ax, cy + ay, HD), PG(cx + bx, cy + by, HD), gn_, gn_, gn_,
                      ((u0, v0), (u0 + ax / SBY_RT * 0.25, v0 + ay / SBY_RT * 0.25), (u0 + bx / SBY_RT * 0.25, v0 + by / SBY_RT * 0.25)))
        for i in range(40):
            (ax, ay), (bx, by) = ring[i], ring[(i + 1) % 40]
            sglass.tri(PG(cx, cy, HR - 0.0012), PG(cx + ax, cy + ay, HR - 0.0012), PG(cx + bx, cy + by, HR - 0.0012), gn_, gn_, gn_)
        scr.cyl(PG(cx, cy, HD), PG(cx, cy, HN + 0.0007), 0.0024, 14)
        nd = Soup()
        pa, pb, pc = PG(cx, cy + 0.0008, HN + 0.0005), PG(cx - 0.0008, cy, HN + 0.0005), PG(cx + 0.0008, cy, HN + 0.0005)
        nd.t.append((pa, pb, pc, (gn_, gn_, gn_)) if np.cross(pb - pa, pc - pa) @ gn_ > 0 else (pa, pc, pb, (gn_, gn_, gn_)))
        LN, WN = 0.0145, 0.0009
        nd.box(PG(cx, cy + LN / 2, HN), upp, rgt, gn_, LN / 2, WN, 0.0003)
        nd.box(PG(cx, cy - 0.0025, HN), upp, rgt, gn_, 0.0025, 0.0014, 0.0003)
        for sx in (-1, 1):
            q = PG(cx + sx * WN, cy - LN, HN)
            nd.t.append((q, q + rgt * 2e-5, q + upp * 2e-5, (gn_, gn_, gn_)) if np.cross(rgt, upp) @ gn_ > 0 else (q, q + upp * 2e-5, q + rgt * 2e-5, (gn_, gn_, gn_)))
        nd.emit("cockpit_sbyneedle_%d" % gi, "ckwhite")
        SBY.append(gi)
    print("standby gauges at", np.round(C0, 3), "facing", np.round(gn_, 2), "- housing points off the panel face: %d of %d" % (n_off, len(hl)))
else:
    print("standby gauges skipped: no panel face found at the strip", None if hit is None else np.round(hit[1], 3))
sbyh.emit("cockpit_sbyhousing", "ckunit")
face_.emit("cockpit_sbyfaces", "cksby")
sglass.emit("cockpit_sbyglass", "ckglass")
bez.emit("cockpit_bezels", "ckbezel")

AT = []
for f in FRAME_F:
    p = V[[c[0] - 1 for c in f]]
    if p[:, 2].min() > 6.85 and p[:, 2].max() < 7.40 and p[:, 1].max() > 0.70:
        for k in range(1, len(p) - 1):
            AT.append((p[0], p[k], p[k + 1]))
n_slot = 0
if AT:
    T0, T1, T2 = (np.array([t[i] for t in AT]) for i in range(3))
    E1, E2 = T1 - T0, T2 - T0
    TN = np.cross(E1, E2)
    TN /= np.maximum(np.linalg.norm(TN, axis=1), 1e-12)[:, None]
    O = np.array([0.0, 1.00, 6.60])

    def cast(d):
        h = np.cross(d, E2)
        a_ = (E1 * h).sum(1)
        ok = np.abs(a_) > 1e-10
        f_ = 1.0 / np.where(ok, a_, 1)
        s_ = O - T0
        u_ = f_ * (s_ * h).sum(1)
        q_ = np.cross(s_, E1)
        v_ = f_ * (q_ @ d)
        t_ = f_ * (E2 * q_).sum(1)
        ok &= (u_ >= 0) & (v_ >= 0) & (u_ + v_ <= 1) & (t_ > 0.05)
        if not ok.any():
            return None
        i = int(np.argmin(np.where(ok, t_, 1e9)))
        return O + d * t_[i], TN[i] if TN[i] @ d < 0 else -TN[i]
    rs = np.arange(0.28, 0.66, 0.006)
    prev = None
    for th in np.radians(np.arange(22, 159, 3.0)):
        hits = []
        for r in rs:
            hp = cast(unit(np.array([r * math.cos(th), 0.78 + r * math.sin(th), 7.06]) - O))
            hits.append(hp if hp is not None and 6.93 < hp[0][2] < 7.25 else None)
        runs, cur_ = [], []
        for k, hp in enumerate(hits):
            if hp is not None:
                cur_.append(k)
            elif cur_:
                runs.append(cur_)
                cur_ = []
        if cur_:
            runs.append(cur_)
        if not runs:
            prev = None
            continue
        run = max(runs, key=len)
        if len(run) < 5:
            prev = None
            continue
        k = run[0] + max(int(round(0.20 * (len(run) - 1))), 1)
        P_, N_ = hits[k]
        if prev is not None and 0.008 < np.linalg.norm(P_ - prev) < 0.06:
            t_ = unit(P_ - prev)
            t_ = unit(t_ - N_ * (t_ @ N_))
            if os.environ.get("ARCH_SLOTS"):
                slot.box(P_ + N_ * 0.0010, t_, np.cross(N_, t_), N_, 0.0075, 0.0028, 0.0008)
                n_slot += 1
        prev = P_
bolts = []
print("arch: %d bolts found, %d slots between them" % (len(bolts), n_slot))

pin, flag = Soup(), Soup()
for z in (6.575, 6.528):
    a = np.array([0.497, 0.532, z])
    b = np.array([0.478, 0.598, z + 0.004])
    ax = unit(b - a)
    pin.cyl(a, a + ax * 0.012, 0.0085, 12)
    pin.cyl(a + ax * 0.010, b, 0.0042, 10)
    pin.cyl(b, b + ax * 0.010, 0.0065, 12)
    side = unit(np.cross(ax, [0, 0, 1.0]))
    flag.box(b + ax * 0.030, ax, [0, 0, 1.0], side, 0.022, 0.0075, 0.0018)
    plac_quad(b + ax * 0.030 - side * 0.00195, ax, [0, 0, 1.0], -side, 0.040, 0.0125, "rbf")
plac.emit("cockpit_placards", "ckplacard")
pin.emit("cockpit_pins", "ckmetaldark")
flag.emit("cockpit_pinflags", "ckredflag")

lamp = Soup()
try:
    import gear_panel
    pts = []
    for x, y in gear_panel.LAMPS:
        p0, p1 = np.array(gear_panel.FR.pt(x, y, 0.0), float), np.array(gear_panel.FR.pt(x, y, 1.0), float)
        if 7.0 < p0[1] < 7.4:
            p0, p1 = p0[[0, 2, 1]], p1[[0, 2, 1]]
        n = unit(p1 - p0)
        if n @ (eye - p0) < 0:
            n = -n
        lamp.cyl(p0 + n * 0.0002, p0 + n * 0.0016, 0.0044, 14, r2=0.0036)
        scr.cyl(p0 - n * 0.0005, p0 + n * 0.0009, 0.0058, 14)
        pts.append(np.round(p0, 3).tolist())
    print("gear lamps at", pts)
except Exception as ex:
    print("gear lamps skipped:", ex)
lamp.emit("cockpit_gearlamps", "gearlamp")
scr.emit("cockpit_detscrews", "ckscrew")
slot.t += hole.t
slot.emit("cockpit_detholes", "ckhole")

bp = os.path.join(ST, "cockpit_base.png")
base = np.asarray(Image.open(bp).convert("RGB")).copy()
H, W = base.shape[:2]
import cv2
msk = np.zeros((H, W), np.uint8)
n_red = 0
for f in G.get("canopy_interior", []):
    if any(c[1] == 0 for c in f):
        continue
    cen = V[[c[0] - 1 for c in f]].mean(0)
    if not (abs(cen[0]) < 0.2 and 0.9 < cen[1] < 1.35 and 7.0 < cen[2] < 7.6):
        continue
    uv = VT[[c[1] - 1 for c in f]]
    px = np.stack([uv[:, 0] * W, (1 - uv[:, 1]) * H], 1)
    c0 = px.mean(0)
    r, g, b = base[min(max(int(c0[1]), 0), H - 1), min(max(int(c0[0]), 0), W - 1)].astype(int)
    if r > 90 and r - g > 45 and r - b > 30:
        cv2.fillConvexPoly(msk, np.round(px).astype(np.int32), 255)
        n_red += 1
if n_red:
    msk = cv2.dilate(msk, np.ones((3, 3), np.uint8))
    red = (base[..., 0].astype(int) - base[..., 1] > 35) & (msk > 0)
    yy, xx = np.nonzero(red)
    shade = 0.75 + 0.5 * (yy - yy.min()) / max(np.ptp(yy), 1)
    base[yy, xx] = np.clip(np.stack([14 * shade, 30 * shade, 26 * shade], 1), 0, 255).astype(np.uint8)
    Image.fromarray(base, "RGB").save(bp)
    for nm, fill in (("cockpit_emit.png", (0, 0, 0)), ("cockpit_glow.png", (0, 0, 0, 0))):
        ep = os.path.join(ST, nm)
        if os.path.exists(ep):
            im = Image.open(ep)
            arr = np.asarray(im).copy()
            if arr.shape[:2] == (H, W):
                arr[yy, xx] = fill[:arr.shape[2]] if arr.ndim == 3 else 0
                Image.fromarray(arr, im.mode).save(ep)
    mp = os.path.join(ST, "cockpit_mask.png")
    if os.path.exists(mp):
        arr = np.asarray(Image.open(mp).convert("RGBA")).copy()
        if arr.shape[:2] == (H, W):
            arr[yy, xx] = (0, 0, 0, 235)
            Image.fromarray(arr, "RGBA").save(mp)
print("HUD lens: %d red faces repainted (%d texels)" % (n_red, int(red.sum()) if n_red else 0))

cfr, cseal, cscr = Soup(), Soup(), Soup()
n_cf = [0, 0]
if G.get("canopy"):
    gk, gpos = {}, []

    def _gk(i):
        k_ = tuple(np.round(V[i - 1], 4))
        if k_ not in gk:
            gk[k_] = len(gpos)
            gpos.append(V[i - 1])
        return gk[k_]
    gtri = []
    for f in G["canopy"]:
        ks = [_gk(c[0]) for c in f]
        for k in range(1, len(ks) - 1):
            if len({ks[0], ks[k], ks[k + 1]}) == 3:
                gtri.append((ks[0], ks[k], ks[k + 1]))
    gpos = np.array(gpos)
    GLASS = _BVH.FromPolygons([_Vec(v) for v in gpos], gtri)
    gn = np.cross(gpos[[t[1] for t in gtri]] - gpos[[t[0] for t in gtri]], gpos[[t[2] for t in gtri]] - gpos[[t[0] for t in gtri]])
    gn /= np.maximum(np.linalg.norm(gn, axis=1), 1e-12)[:, None]
    ecount = {}
    for t in gtri:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            ecount[tuple(sorted((a, b)))] = ecount.get(tuple(sorted((a, b))), 0) + 1
    badj = {}
    for (a, b), c in ecount.items():
        if c == 1:
            badj.setdefault(a, []).append(b)
            badj.setdefault(b, []).append(a)
    loops, seen = [], set()
    for s0 in badj:
        if s0 in seen or len(badj[s0]) != 2:
            continue
        lp, cur_ = [s0], s0
        seen.add(s0)
        while True:
            nx = [q for q in badj[cur_] if q not in seen]
            if not nx:
                break
            cur_ = nx[0]
            seen.add(cur_)
            lp.append(cur_)
        if len(lp) >= 8:
            loops.append(gpos[lp])

    def on_glass(q):
        h = GLASS.find_nearest(_Vec([float(a) for a in q]))
        pt = np.array(h[0])
        n = gn[h[2]]
        if n @ (np.array([0.0, 0.80, pt[2]]) - pt) < 0:
            n = -n
        return pt, n
    CF_W, CF_H, CF_N = 0.042, 0.0072, 6
    CF_BOW = float(os.environ.get("CANOPY_BOW", "0.016"))
    EYE = np.array([0.0, 1.16, 6.50])

    def sect(w):
        flat = [(0.0028 + (w - 0.0138) * k / CF_N, CF_H) for k in range(CF_N + 1)]
        return [(0.0, 0.0004), (0.0, 0.0048)] + flat + [(w - 0.0035, 0.0056), (w, 0.0022), (w, 0.0004)]
    for L0 in loops:
        wind = L0[:, 2].min() > 7.0
        pts = []
        m = len(L0)
        for i in range(m):
            a, b = L0[i], L0[(i + 1) % m]
            nseg = max(int(math.ceil(np.linalg.norm(b - a) / 0.014)), 1)
            for k in range(nseg):
                pts.append(a + (b - a) * (k / nseg))
        pts = np.array(pts)
        m = len(pts)
        for _ in range(3):
            pts = (np.roll(pts, 1, 0) + 2 * pts + np.roll(pts, -1, 0)) / 4
        base = []
        for i in range(m):
            p = pts[i]
            t_ = unit(pts[(i + 1) % m] - pts[i - 1])
            p0, n0 = on_glass(p)
            b_ = unit(np.cross(n0, t_))
            q1, _ = on_glass(p0 + b_ * 0.02)
            q2, _ = on_glass(p0 - b_ * 0.02)
            if np.linalg.norm(q2 - (p0 - b_ * 0.02)) < np.linalg.norm(q1 - (p0 + b_ * 0.02)):
                b_ = -b_
            base.append((p0, n0, b_))
        Wd = np.full(m, CF_W)
        bow = np.zeros(m, bool)
        if not wind:
            Z0, Z1 = BEAM_Z0 - 0.10, 7.06
            _hn = unit(np.array([0.0, -0.152, 0.988])); _hu = unit(np.cross(_hn, [1.0, 0, 0])); _hu = _hu if _hu[1] > 0 else -_hu
            nw = 0
            for i in range(m):
                p0, n0, b_ = base[i]
                dq = p0 - np.array([0.0, 0.93, 7.085])
                if math.degrees(math.atan2(abs(dq[0]), dq @ _hu)) < 99.0 and dq @ _hn > -0.085:
                    bow[i] = True
                    continue
                if p0[2] < Z0 or p0[2] > Z1:
                    continue
                ramp = float(np.clip((p0[2] - Z0) / 0.10, 0, 1))
                tgt = beam_top(float(p0[2])) + 0.015
                for s_ in np.arange(0.0, 0.2401, 0.002):
                    if on_glass(p0 + b_ * s_)[0][1] >= tgt:
                        Wd[i] = CF_W + (max(s_, 0.016) - CF_W) * ramp * ramp * (3 - 2 * ramp)
                        nw += 1
                        break
            print("canopy frame: along the sills its top edge is 15 mm over the beam (%d sections, %.0f .. %.0f mm wide); %d sections round the bow left to the hoop's lip" % (
                nw, Wd[~bow].min() * 1000, Wd[~bow].max() * 1000, int(bow.sum())))
            for _ in range(3):
                Wd = (np.roll(Wd, 1) + 2 * Wd + np.roll(Wd, -1)) / 4
        rings = []
        for i in range(m):
            p0, n0, b_ = base[i]
            keep = ((not wind) and not bow[i]) or (wind and p0[2] > 7.24)
            fade = 1.0 if not wind else float(np.clip((p0[2] - 7.24) / 0.05, 0.0, 1.0))
            ring = []
            for s_, h_ in sect(Wd[i]):
                q, nq = on_glass(p0 + b_ * (s_ * (0.35 + 0.65 * fade)))
                ring.append((q + nq * (h_ * max(fade, 0.08)), nq))
            rings.append((keep, ring, b_, p0, n0, fade))
        S0 = sect(CF_W)
        for i in range(m):
            j = (i + 1) % m
            if not (rings[i][0] and rings[j][0]):
                continue
            ra, rb = rings[i], rings[j]
            for k in range(len(S0) - 1):
                (s0_, h0_), (s1_, h1_) = S0[k], S0[k + 1]
                ms, mh = h1_ - h0_, -(s1_ - s0_)
                ln_ = math.hypot(ms, mh)
                ms, mh = -ms / ln_, -mh / ln_
                na = unit(ra[2] * ms + ra[1][k][1] * mh)
                nb = unit(rb[2] * ms + rb[1][k][1] * mh)
                a0, a1, b0, b1 = ra[1][k][0], ra[1][k + 1][0], rb[1][k][0], rb[1][k + 1][0]
                if np.linalg.norm(np.cross(b0 - a0, b1 - a0)) > 1e-12:
                    cfr.tri(a0, b0, b1, na, nb, nb)
                if np.linalg.norm(np.cross(b1 - a0, a1 - a0)) > 1e-12:
                    cfr.tri(a0, b1, a1, na, nb, na)
            for k in range(1, len(S0) - 2):
                a0, a1, b0, b1 = (ra[1][k][0] - ra[1][k][1] * (S0[k][1] - 0.0004), ra[1][k + 1][0] - ra[1][k + 1][1] * (S0[k + 1][1] - 0.0004),
                                  rb[1][k][0] - rb[1][k][1] * (S0[k][1] - 0.0004), rb[1][k + 1][0] - rb[1][k + 1][1] * (S0[k + 1][1] - 0.0004))
                na, nb = -ra[1][k][1], -rb[1][k][1]
                if np.linalg.norm(np.cross(b0 - a0, b1 - a0)) > 1e-12:
                    cfr.tri(a0, b0, b1, na, nb, nb)
                if np.linalg.norm(np.cross(b1 - a0, a1 - a0)) > 1e-12:
                    cfr.tri(a0, b1, a1, na, nb, na)
            n_cf[0] += 1
        run, acc = [], 0.0
        for i in range(m + 1):
            keep, ring, b_, p0, n0, fade = rings[i % m]
            if keep and fade > 0.5:
                q, nq = on_glass(p0 + b_ * (Wd[i % m] + 0.0015))
                run.append(q + nq * 0.0030)
            if (not keep or fade <= 0.5 or i == m) and len(run) > 1:
                cseal.tube(run[::3] + ([run[-1]] if (len(run) - 1) % 3 else []), 0.0034, 6)
                run = []
            elif not keep or fade <= 0.5:
                run = []
            if i < m and keep and fade > 0.99:
                acc += np.linalg.norm(pts[(i + 1) % m] - pts[i])
                if acc >= 0.085 and Wd[i] >= 0.020:
                    acc = 0.0
                    q, nq = on_glass(p0 + b_ * (Wd[i] - 0.0080))
                    cscr.cyl(q + nq * (CF_H - 0.0003), q + nq * (CF_H + 0.0012), 0.0030, 10)
                    n_cf[1] += 1
cfr.emit("canopy_frame", "ckcanfr")
cseal.emit("canopy_seal", "ckcable")
cscr.emit("canopy_framescrews", "ckscrew")
print("canopy frames: %d sections, %d screws" % tuple(n_cf))

liner = Soup()
for _g in ("fuselage_cockpit", "fuselage", "fuselage_nose"):
    for f in G.get(_g, []):
        p_ = V[[c[0] - 1 for c in f]]
        cen = p_.mean(0)
        if not (abs(cen[0]) < 0.66 and 0.30 < cen[1] < 1.30 and 5.80 < cen[2] < 8.10):
            continue
        nn = np.zeros(3)
        for c in f:
            if c[2]:
                nn += VN[c[2] - 1]
        if np.linalg.norm(nn) < 1e-9:
            continue
        nn = unit(nn)
        for k in range(1, len(p_) - 1):
            a, b, c = (p_[0] - nn * 0.0015, p_[k] - nn * 0.0015, p_[k + 1] - nn * 0.0015)
            if np.linalg.norm(np.cross(b - a, c - a)) > 1e-10:
                liner.tri(a, b, c, -nn, -nn, -nn)
liner.emit("cockpit_skinliner", "ckliner")

import cv2 as _cv
_N = 1024


def _tn(sig, seed):
    r = np.random.default_rng(seed).standard_normal((_N, _N)).astype(np.float32)
    r = _cv.GaussianBlur(np.tile(r, (3, 3)), (0, 0), sig)[_N:2 * _N, _N:2 * _N]
    return (r - r.mean()) / max(float(r.std()), 1e-6)


_drift = 0.045 * _tn(70, 1) + 0.02 * _tn(9, 2)
_stain = np.clip((_tn(40, 3) - 0.9) * 0.9, 0, 1)
_chip = np.clip((0.6 * _tn(1.6, 4) + 0.4 * _tn(5, 5) - 1.9) * 2.5, 0, 1)
_sc = np.random.default_rng(6).standard_normal((_N, _N)).astype(np.float32)
_sc = _cv.GaussianBlur(np.tile(_sc, (3, 3)), (0, 0), sigmaX=6, sigmaY=0.7)[_N:2 * _N, _N:2 * _N]
_sc = np.clip((_sc / _sc.std() - 2.6) * 1.5, 0, 1)
_b = 0.80 * (1 + 0.6 * _drift) * (1 - 0.07 * _stain)
_b = _b + (1.0 - _b) * np.clip(0.42 * _chip + 0.20 * _sc, 0, 1)
Image.fromarray((np.clip(np.repeat(_b[..., None], 3, 2), 0, 1) * 255).astype(np.uint8), "RGB").save(os.path.join(ST, "ckworn_base.png"))
_h = 0.025 * _tn(1.2, 7) - 0.35 * _chip - 0.18 * _sc
_gx = (np.roll(_h, -1, 1) - np.roll(_h, 1, 1)) * 1.0
_gy = (np.roll(_h, -1, 0) - np.roll(_h, 1, 0)) * 1.0
_nrm = np.zeros((_N, _N, 4), np.float32)
_nrm[..., 3] = np.clip(0.5 - _gx * 0.5, 0, 1)
_nrm[..., 1] = np.clip(0.5 + _gy * 0.5, 0, 1)
_nrm[..., 0] = 1.0
_nrm[..., 2] = 1.0
Image.fromarray((_nrm * 255).astype(np.uint8), "RGBA").save(os.path.join(ST, "ckworn_normal.png"))
_mk = np.zeros((_N, _N, 4), np.float32)
_mk[..., 0] = np.clip(0.15 + 0.6 * _chip + 0.3 * _sc, 0, 1)
_mk[..., 3] = np.clip(0.36 + 0.16 * _chip - 0.08 * _stain, 0, 1)
Image.fromarray((_mk * 255).astype(np.uint8), "RGBA").save(os.path.join(ST, "ckworn_mask.png"))
_W = " base=ckworn_base.png normal=ckworn_normal.png mask=ckworn_mask.png smooth=1 metal=1"

_N = 1024
_ub = 0.86 * (1 + 0.035 * _tn(120, 21) + 0.018 * _tn(12, 22) + 0.010 * _tn(1.6, 23) + 0.007 * _tn(0.7, 28))
_scf = np.random.default_rng(24).standard_normal((_N, _N)).astype(np.float32)
_scf = _cv.GaussianBlur(np.tile(_scf, (3, 3)), (0, 0), sigmaX=18, sigmaY=1.1)[_N:2 * _N, _N:2 * _N]
_scf = np.clip((_scf / _scf.std() - 3.0) * 1.2, 0, 1)
_dust = np.clip((_tn(60, 25) - 1.1) * 0.6, 0, 1)
_ub = _ub + (1.0 - _ub) * np.clip(0.30 * _scf + 0.10 * _dust, 0, 1)
Image.fromarray((np.clip(np.repeat(_ub[..., None], 3, 2), 0, 1) * 255).astype(np.uint8), "RGB").save(os.path.join(ST, "ckunit_base.png"))
_um = np.zeros((_N, _N, 4), np.float32)
_um[..., 0] = 0.10
_um[..., 3] = np.clip(0.40 + 0.05 * _tn(50, 26) - 0.12 * _dust - 0.10 * _scf, 0, 1)
Image.fromarray((_um * 255).astype(np.uint8), "RGBA").save(os.path.join(ST, "ckunit_mask.png"))
_uh = 2 * (0.012 * _tn(2.0, 27) + 0.004 * _tn(0.8, 29))
_un = np.ones((_N, _N, 4), np.float32)
_un[..., 3] = np.clip(0.5 - (np.roll(_uh, -1, 1) - np.roll(_uh, 1, 1)) * 0.5, 0, 1)
_un[..., 1] = np.clip(0.5 + (np.roll(_uh, -1, 0) - np.roll(_uh, 1, 0)) * 0.5, 0, 1)
Image.fromarray((_un * 255).astype(np.uint8), "RGBA").save(os.path.join(ST, "ckunit_normal.png"))

from PIL import ImageDraw as _PDr, ImageFont as _PFt
import ckpanel as _ckr
_pl = Image.new("RGBA", (2048, 1024), (255, 255, 255, 0))
_pd = _PDr.Draw(_pl)
_pd.text((1024, 160), "REMOVE BEFORE FLIGHT", fill=(244, 244, 238, 255), font=_PFt.truetype(_ckr.FONT, 150), anchor="mm")
_pd.rectangle([0, 352, 1023, 991], fill=(150, 153, 150, 255))
_pd.rectangle([22, 374, 1001, 969], outline=(28, 29, 30, 255), width=7)
for _i, _t in enumerate(("PART No", "SERIAL No", "MOD STATE", "INSP")):
    _y = 452 + _i * 132
    _pd.text((60, _y), _t, fill=(24, 25, 26, 255), font=_PFt.truetype(_ckr.FONT, 62), anchor="lm")
    _pd.rectangle([470, _y - 44, 950, _y + 44], outline=(40, 41, 42, 255), width=5)
    for _k in range(3 + (_i * 2) % 3):
        _pd.line([520 + _k * 88, _y, 575 + _k * 88, _y], fill=(60, 61, 62, 255), width=12)
for _cx, _cy in ((60, 400), (964, 400), (60, 944), (964, 944)):
    _pd.ellipse([_cx - 13, _cy - 13, _cx + 13, _cy + 13], fill=(70, 72, 73, 255))
_pd.rectangle([1056, 352, 2015, 671], fill=(232, 184, 22, 255))
_pd.rectangle([1074, 370, 1997, 653], outline=(18, 18, 18, 255), width=14)
_pd.text((1536, 512), "CAUTION", fill=(18, 18, 18, 255), font=_PFt.truetype(_ckr.FONT, 170), anchor="mm")
_pa = np.asarray(_pl.resize((1024, 512), Image.LANCZOS)).copy()
_pa[:80, :, :3] = (244, 244, 238)
Image.fromarray(_pa, "RGBA").save(os.path.join(ST, "ckplacard.png"), optimize=True)

from PIL import ImageDraw as _IDr, ImageFont as _IFt
import ckpanel as _ckq
_tw = Image.new("L", (2048, 1024), 0)
_td = _IDr.Draw(_tw)
_tf = _IFt.truetype(_ckq.FONT, 330)
for _i, _wd in enumerate(UWORDS):
    _td.text(((_i % 2) * 1024 + 512, (_i // 2) * 512 + 256), _wd, fill=255, font=_tf, anchor="mm")
_ta = np.zeros((256, 512, 4), np.uint8)
_ta[..., :3] = (226, 228, 220)
_ta[..., 3] = np.asarray(_tw.resize((512, 256), Image.LANCZOS))
Image.fromarray(_ta, "RGBA").save(os.path.join(ST, "ckunittxt.png"), optimize=True)

if SBY:
    from PIL import ImageDraw, ImageFont
    import ckpanel as _ckp
    _S = 4
    _C = 512 * _S
    sheet = Image.new("RGB", (2 * _C, 2 * _C), (10, 10, 11))
    dr = ImageDraw.Draw(sheet)
    _R = _C / 2 * SBY_RI / SBY_RT
    _WH = (226, 227, 220)

    def _pt(k, ang, r):
        ox, oy = (k % 2) * _C + _C / 2, (k // 2) * _C + _C / 2
        return ox + math.sin(math.radians(ang)) * r * _R, oy - math.cos(math.radians(ang)) * r * _R

    def _tick(k, ang, r0, r1, w):
        dr.line([_pt(k, ang, r0), _pt(k, ang, r1)], fill=_WH, width=int(w * _S))

    def _txt(k, ang, r, text, size, fill=_WH):
        f = ImageFont.truetype(_ckp.FONT, int(size * _R))
        dr.text(_pt(k, ang, r), text, fill=fill, font=f, anchor="mm")
    for k in range(3):
        ox, oy = (k % 2) * _C + _C / 2, (k // 2) * _C + _C / 2
        dr.ellipse([ox - _R * 1.04, oy - _R * 1.04, ox + _R * 1.04, oy + _R * 1.04], fill=(13, 13, 14))
    for i in range(0, 801, 25):
        a = -165.0 + 330.0 * i / 800
        _tick(0, a, 0.80 if i % 100 == 0 else (0.86 if i % 50 == 0 else 0.90), 0.97, 5 if i % 100 == 0 else 3)
        if i % 100 == 0:
            _txt(0, a, 0.64, str(i // 100), 0.21)
    _txt(0, 0, 0.0, "", 0.1)
    dr.text((0 * _C + _C / 2, _C / 2 - 0.30 * _R), "x100", fill=_WH, font=ImageFont.truetype(_ckp.FONT, int(0.13 * _R)), anchor="mm")
    dr.text((0 * _C + _C / 2, _C / 2 + 0.34 * _R), "KTS", fill=_WH, font=ImageFont.truetype(_ckp.FONT, int(0.19 * _R)), anchor="mm")
    for i in range(-12, 13):
        a = -90.0 + 150.0 * (i * 500) / 6000
        _tick(1, a, 0.80 if i % 2 == 0 else 0.88, 0.97, 5 if i % 2 == 0 else 3)
        if i % 4 == 0:
            _txt(1, a, 0.64, str(abs(i) // 2), 0.21)
    dr.text((1 * _C + _C / 2 + 0.42 * _R, _C / 2 - 0.14 * _R), "x1000", fill=_WH, font=ImageFont.truetype(_ckp.FONT, int(0.13 * _R)), anchor="mm")
    dr.text((1 * _C + _C / 2 + 0.42 * _R, _C / 2 + 0.08 * _R), "FT MIN", fill=_WH, font=ImageFont.truetype(_ckp.FONT, int(0.15 * _R)), anchor="mm")
    for nm_, yy_ in (("UP", -0.34), ("DN", 0.34)):
        dr.text((1 * _C + _C / 2 - 0.36 * _R, _C / 2 + yy_ * _R), nm_, fill=_WH, font=ImageFont.truetype(_ckp.FONT, int(0.12 * _R)), anchor="mm")
    for i in range(50):
        a = 360.0 * i / 50
        _tick(2, a, 0.80 if i % 5 == 0 else 0.90, 0.97, 5 if i % 5 == 0 else 3)
        if i % 5 == 0:
            _txt(2, a, 0.64, str(i // 5), 0.21)
    dr.text((0 * _C + _C / 2, _C + _C / 2 - 0.30 * _R), "x100", fill=_WH, font=ImageFont.truetype(_ckp.FONT, int(0.13 * _R)), anchor="mm")
    dr.text((0 * _C + _C / 2, _C + _C / 2 + 0.34 * _R), "FEET", fill=_WH, font=ImageFont.truetype(_ckp.FONT, int(0.19 * _R)), anchor="mm")
    sheet.resize((1024, 1024), Image.LANCZOS).save(os.path.join(ST, "cksby.png"), optimize=True)

def _mirror_picture():
    from scipy import ndimage as _nd
    Wm, Hm = 512, 192
    out = np.zeros((3 * Hm, Wm, 3), np.float32)
    U, Vv = np.meshgrid((np.arange(Wm) + 0.5) / Wm, 1 - (np.arange(Hm) + 0.5) / Hm)
    rng = np.random.default_rng(7)
    for band, head_u in ((0, 0.14), (1, 0.86), (2, 0.50)):
        sky = np.array([0.66, 0.74, 0.82])[None, None] * (1 - Vv)[..., None] + np.array([0.36, 0.50, 0.68])[None, None] * Vv[..., None]
        cloud = _nd.gaussian_filter(rng.standard_normal((Hm, Wm)), (9, 30))
        sky = sky + 0.10 * np.clip(cloud / cloud.std() - 0.4, 0, 1)[..., None]
        img = sky.copy()

        def lay(mask, col):
            m = np.clip(mask, 0, 1)[..., None]
            img[:] = img * (1 - m) + np.array(col)[None, None] * m
        aa = lambda d, w=0.012: np.clip(0.5 - d / w, 0, 1)
        lay(aa(Vv - (0.30 + 0.07 * np.cos((U - 0.5) * 3.0))), (0.085, 0.090, 0.097))
        lay(aa(np.abs(U - 0.5 - (0.5 - head_u) * 0.15) - 0.018 * (1.2 - Vv)) * (Vv < 0.78), (0.070, 0.074, 0.080))
        rr = np.hypot((U - 0.5) / 0.62, (Vv - 0.05) / 0.86)
        lay(aa(np.abs(rr - 1.0) - 0.016, 0.010), (0.12, 0.125, 0.13))
        lay(aa(np.maximum(np.abs(U - head_u) - 0.105, Vv - 0.70)), (0.040, 0.042, 0.045))
        lay(aa(np.hypot((U - head_u) / 0.070, (Vv - 0.34) / 0.36) - 1.0, 0.10) * 0.85, (0.17, 0.18, 0.175))
        img = _nd.gaussian_filter(img, (2.6, 2.6, 0))
        vg = 1 - 0.25 * ((U - 0.5) ** 2 * 2.2 + (Vv - 0.5) ** 2 * 1.2)
        out[(2 - band) * Hm:(3 - band) * Hm] = img * vg[..., None]
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(ST, "ckmirror.png"), optimize=True)


_mirror_picture()
with open(path, "a") as fo:
    fo.write("\n".join(tail) + "\n")
_V = []
_out, _g, _cut = [], None, 0
for _ln in open(path):
    if _ln.startswith("v "):
        _p = _ln.split()
        _V.append((float(_p[1]), float(_p[2]), float(_p[3])))
    elif _ln.startswith("o ") or _ln.startswith("g "):
        _g = _ln[2:].strip()
    elif _ln.startswith("f ") and _g in ("cockpit_consoles", "cockpit_shelltub"):
        _ps = [_V[int(_t.split("/")[0]) - 1] for _t in _ln.split()[1:]]
        if all(KERB_BOX[0] <= q[0] <= KERB_BOX[1] and KERB_BOX[2] <= q[1] <= KERB_BOX[3] and KERB_BOX[4] <= q[2] <= KERB_BOX[5] for q in _ps):
            _cut += 1
            continue
    _out.append(_ln)
if _cut:
    open(path, "w").writelines(_out)
print("left console: %d faces of the loose striped block removed" % _cut)
del _V, _out
mt = os.path.join(ST, "typhoon_materials.txt")
txt = open(mt).read().rstrip("\n")
for ln in ("ckrail color=#80858A" + _W, "ckmetaldark color=#5F6468" + _W, "cklens color=#14171A smooth=0.86 metal=0", "ckmirror base=ckmirror.png emit=ckmirror.png emitstrength=0.22 smooth=0.62 metal=0", "ckscrew color=#3A3D40 smooth=0.5 metal=0.6",
           "ckhole color=#050606 smooth=0.1 metal=0", "ckdeck color=#565A5D" + _W, "ckbezel color=#1B1D1F smooth=0.38 metal=0.1",
           "ckredflag color=#B3221C smooth=0.35 metal=0", "ckpad color=#444A3C" + _W, "ckblanket color=#6E746A" + _W, "ckstrap color=#6E7360" + _W, "ckyellow color=#C39A16 smooth=0.38 metal=0", "ckcable color=#1B1C1E smooth=0.30 metal=0", "ckwhite color=#E4E5E0 smooth=0.3 metal=0", "ckwall color=#70757A" + _W,
           "ckplate color=#7F858A" + _W, "gearlamp color=#0D2412 smooth=0.85 metal=0 emitcolor=#2BFF4E",
           "ckunit color=#34373A base=ckunit_base.png normal=ckunit_normal.png mask=ckunit_mask.png smooth=1 metal=1", "ckunitedge color=#5E6266 smooth=0.42 metal=0.4",
           "cksby base=cksby.png smooth=0.42 metal=0", "ckunittxt base=ckunittxt.png alpha=0.998 smooth=0.25 metal=0",
           "ckunitdark color=#151617 smooth=0.30 metal=0.1", "ckglass color=#C4D6DE alpha=0.07 smooth=0.98 metal=0",
           "ckplacard base=ckplacard.png alpha=0.998 smooth=0.30 metal=0", "ckcanfr color=#5F6367" + _W, "ckliner color=#474B4F" + _W):
    _rows = txt.split("\n")
    _hit = [i for i, x in enumerate(_rows) if x.startswith(ln.split()[0] + " ")]
    if _hit:
        _rows[_hit[0]] = ln
        txt = "\n".join(_rows)
    else:
        txt += "\n" + ln
open(mt, "w").write(txt + "\n")
print("cockpit_detail: %d vertices added" % (nv - len(V)))
