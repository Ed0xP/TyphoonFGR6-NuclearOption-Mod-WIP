import math
import os
import sys

import numpy as np

ST = sys.argv[1]
Z_BACKS = -2.20
SKINS = ("nozzle_L", "nozzle_R", "fuselage", "fuselage_root_L", "fuselage_root_R", "fuselage_baylip", "fin")
WHOLE = ("bay_box",)
path = os.path.join(ST, "typhoon.obj")
lines = open(path).read().split("\n")
out, skip = [], False
for l in lines:
    if l[:2] in ("o ", "g "):
        skip = l.split()[1] in ("tail_backs", "airbrake_inner", "airbrake_holes")
        if skip:
            continue
    if not (skip and l.startswith(("f ", "usemtl "))):
        out.append(l)
lines = out
V, VN, g, faces = [], [], None, {}
nvt = 0
for l in lines:
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vn "):
        VN.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vt "):
        nvt += 1
    elif l[:2] in ("o ", "g "):
        g = l.split()[1]
    elif l.startswith("f ") and g in SKINS + WHOLE + ("airbrake",):
        c = [t.split("/") for t in l.split()[1:]]
        for j in range(1, len(c) - 1):
            faces.setdefault(g, []).append([(int(c[k][0]) - 1, int(c[k][2]) - 1) for k in (0, j, j + 1)])
V, VN = np.array(V), np.array(VN)
f0 = np.array(faces["fuselage"])
gn = np.cross(V[f0[:, 1, 0]] - V[f0[:, 0, 0]], V[f0[:, 2, 0]] - V[f0[:, 0, 0]])
WIND = 1 if (gn * VN[f0[:, 0, 1]]).sum() >= 0 else -1
tris = []


def add(a, b, c, n):
    tris.append((np.array(a), np.array(b), np.array(c), np.array(n)))


nb = 0
for g_ in SKINS + WHOLE:
    for f in faces.get(g_, []):
        P = [V[i] for i, _ in f]
        if g_ in SKINS and (P[0][2] + P[1][2] + P[2][2]) / 3 > Z_BACKS:
            continue
        n = np.cross(P[1] - P[0], P[2] - P[0]) * WIND
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        n = -n / ln
        o = n * 0.0005
        add(P[0] + o, P[1] + o, P[2] + o, n)
        nb += 1
nd = len(tris)
for sx in (1, -1):
    ax = np.array([sx * 0.4855, -0.0392])
    SEG = 48
    ring = lambda r, z: [np.array([ax[0] + r * math.cos(2 * math.pi * i / SEG), ax[1] + r * math.sin(2 * math.pi * i / SEG), z]) for i in range(SEG)]
    r0, r1 = ring(0.100, -2.83), ring(0.375, -2.83)
    for i in range(SEG):
        j = (i + 1) % SEG
        add(r0[i], r1[i], r1[j], (0, 0, -1.0))
        add(r0[i], r1[j], r0[j], (0, 0, -1.0))
    Z1, R1 = -3.45, 0.340
    for k in range(6):
        za, zb = -2.83 + (Z1 + 2.83) * k / 6, -2.83 + (Z1 + 2.83) * (k + 1) / 6
        ra, rb = 0.377 + (R1 - 0.377) * k / 6, 0.377 + (R1 - 0.377) * (k + 1) / 6
        qa, qb = ring(ra, za), ring(rb, zb)
        for i in range(SEG):
            j = (i + 1) % SEG
            n_ = -np.array([math.cos(2 * math.pi * (i + 0.5) / SEG), math.sin(2 * math.pi * (i + 0.5) / SEG), 0.0])
            add(qa[i], qa[j], qb[j], n_)
            add(qa[i], qb[j], qb[i], n_)
nbk = 0
try:
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    import re as _re
    _rx = _re.compile(r"^(fuselage|nozzle_[LR]$|fin$|bay_door_[LR]$|bay_box$|wing_[LR]$)")
    _F, _g = [], None
    for l in lines:
        if l[:2] in ("o ", "g "):
            _g = l.split()[1]
        elif l.startswith("f ") and _g and _rx.match(_g):
            _ids = [int(t.split("/")[0]) - 1 for t in l.split()[1:]]
            for _j in range(1, len(_ids) - 1):
                _F.append((_ids[0], _ids[_j], _ids[_j + 1]))
    _bvh = BVHTree.FromPolygons([Vector(v) for v in V], _F)
    ZB, STEP, MARG = -2.815, 0.0125, 0.012
    _dirs = [Vector(d) for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0))]

    def _inside(x, y):
        o = Vector((x, y, ZB))
        for d in _dirs:
            h = _bvh.ray_cast(o, d, 3.0)
            if h[0] is None or h[3] < MARG:
                return False
        return True
    for _iy in range(int(1.7 / STEP)):
        y = -0.75 + (_iy + 0.5) * STEP
        run = None
        for _ix in range(int(2.6 / STEP) + 1):
            x = -1.3 + (_ix + 0.5) * STEP
            ok = _ix < int(2.6 / STEP) and _inside(x, y)
            if ok and run is None:
                run = x - STEP / 2
            elif not ok and run is not None:
                x1 = x - STEP / 2
                a_, b_, c_, d_ = (run, y - STEP / 2, ZB), (x1, y - STEP / 2, ZB), (x1, y + STEP / 2, ZB), (run, y + STEP / 2, ZB)
                add(a_, b_, c_, (0, 0, -1.0)); add(a_, c_, d_, (0, 0, -1.0))
                nbk += 2
                run = None
    print("tail_close: bulkhead at z %.3f, %d triangles" % (ZB, nbk))
except ImportError:
    print("tail_close: no Blender python here, the rear bulkhead is left out")

ab = faces.get("airbrake", [])
ab_tris = []
if ab:
    from scipy.interpolate import LinearNDInterpolator
    top = []
    for f in ab:
        P = [V[i] for i, _ in f]
        n = np.cross(P[1] - P[0], P[2] - P[0]) * WIND
        if np.linalg.norm(n) > 1e-12 and n[1] / np.linalg.norm(n) > 0.45:
            top += P
    top = np.unique(np.round(np.array(top), 4), axis=0)
    for _ in range(3):
        Af = np.stack([np.ones(len(top)), top[:, 2], top[:, 0] ** 2, top[:, 0] ** 2 * top[:, 2], top[:, 2] ** 2, top[:, 0] ** 4], 1)
        co = np.linalg.lstsq(Af, top[:, 1], rcond=None)[0]
        top = top[top[:, 1] > Af @ co - 0.020]
    fy = LinearNDInterpolator(top[:, [0, 2]], top[:, 1])
    DEPTH, STEP, INSET = 0.028, 0.022, 0.004
    x0, x1, z0, z1 = top[:, 0].min(), top[:, 0].max(), top[:, 2].min(), top[:, 2].max()
    nxg, nzg = int(round((x1 - x0 - 2 * INSET) / STEP)), int(round((z1 - z0 - 2 * INSET) / STEP))
    gx = np.linspace(x0 + INSET, x1 - INSET, nxg + 1)
    gz = np.linspace(z0 + INSET, z1 - INSET, nzg + 1)

    def at(x, z):
        y = fy(x, z)
        if np.isnan(y):
            return None, None
        e = 0.006
        ya, yb, yc, yd = fy(x - e, z), fy(x + e, z), fy(x, z - e), fy(x, z + e)
        dx = 0.0 if np.isnan(ya) or np.isnan(yb) else (yb - ya) / (2 * e)
        dz = 0.0 if np.isnan(yc) or np.isnan(yd) else (yd - yc) / (2 * e)
        n = np.array([-dx, 1.0, -dz])
        return np.array([x, float(y), z]), n / np.linalg.norm(n)

    node = {}
    for i, x in enumerate(gx):
        for j, z in enumerate(gz):
            p, n = at(x, z)
            if p is not None:
                node[(i, j)] = (p, n, p - n * DEPTH)
    quad = {(i, j) for i in range(nxg) for j in range(nzg) if all(k in node for k in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)))}
    for i, j in quad:
        a_, b_, c_, d_ = (node[k] for k in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)))
        nn = -(a_[1] + b_[1] + c_[1] + d_[1]) / 4
        ab_tris.append((a_[2], b_[2], c_[2], nn, 0))
        ab_tris.append((a_[2], c_[2], d_[2], nn, 0))
        for (di, dj), (k0, k1) in (((-1, 0), ((i, j), (i, j + 1))), ((1, 0), ((i + 1, j), (i + 1, j + 1))),
                                   ((0, -1), ((i, j), (i + 1, j))), ((0, 1), ((i, j + 1), (i + 1, j + 1)))):
            if (i + di, j + dj) in quad:
                continue
            A, B = node[k0], node[k1]
            nn = np.array([float(di), 0.0, float(dj)])
            ab_tris.append((A[0], B[0], B[2], nn, 0))
            ab_tris.append((A[0], B[2], A[2], nn, 0))

    def rib(pts, half, tall):
        ring = []
        for i, (x, z) in enumerate(pts):
            p, n = at(x, z)
            if p is None:
                ring.append(None)
                continue
            p = p - n * DEPTH
            a = np.array(pts[min(i + 1, len(pts) - 1)]) - np.array(pts[max(i - 1, 0)])
            t = np.array([a[0], 0.0, a[1]])
            t /= np.linalg.norm(t)
            s_ = np.cross(n, t)
            s_ /= np.linalg.norm(s_)
            ring.append((p + s_ * half, p - s_ * half, p - s_ * half * 0.7 - n * tall, p + s_ * half * 0.7 - n * tall, s_, n))
        for A, B in zip(ring[:-1], ring[1:]):
            if A is None or B is None:
                continue
            for i, j, nn in ((0, 3, A[4]), (1, 2, -A[4]), (3, 2, -A[5])):
                ab_tris.append((A[i], B[i], B[j], nn, 0))
                ab_tris.append((A[i], B[j], A[j], nn, 0))
    NS = 14
    ZR = np.linspace(z0 + 0.12, z1 - 0.12, 7)
    for z in ZR:
        rib([(x0 + 0.012 + (x1 - x0 - 0.024) * i / NS, z) for i in range(NS + 1)], 0.007, 0.014)
    for x in (-0.105, 0.0, 0.105):
        rib([(x, z0 + 0.03 + (z1 - z0 - 0.06) * i / 30) for i in range(31)], 0.006, 0.018)
    for z in (ZR[:-1] + ZR[1:]) / 2:
        for x in (-0.052, 0.052):
            p, n = at(x, z)
            if p is None:
                continue
            t = np.array([1.0, 0, 0]) - n * n[0]
            t /= np.linalg.norm(t)
            b = np.cross(n, t)
            c = p - n * (DEPTH + 0.0015)
            pr = [c + (t * math.cos(2 * math.pi * i / 16) + b * math.sin(2 * math.pi * i / 16)) * 0.026 for i in range(16)]
            for i in range(16):
                ab_tris.append((c, pr[i], pr[(i + 1) % 16], -n, 1))

tail = []
nv0, nvn0 = len(V), len(VN)
groups = [("tail_backs", "dark", tris)]
if ab_tris:
    groups += [("airbrake_inner", "abinner", [t[:4] for t in ab_tris if t[4] == 0]), ("airbrake_holes", "dark", [t[:4] for t in ab_tris if t[4] == 1])]
nf = 0
for gname, mtl, tl in groups:
    fl = ["o " + gname, "usemtl " + mtl]
    for a, b, c, n in tl:
        pp = (a, b, c)
        if np.cross(b - a, c - a) @ n * WIND < 0:
            pp = (a, c, b)
        for p in pp:
            tail.append("v %.5f %.5f %.5f" % tuple(p))
            tail.append("vn %.4f %.4f %.4f" % tuple(n))
            tail.append("vt 0.5 0.5")
        fl.append("f " + " ".join("%d/%d/%d" % (nv0 + nf + k + 1, nvt + nf + k + 1, nvn0 + nf + k + 1) for k in range(3)))
        nf += 3
    tail_f = fl if gname == "tail_backs" else tail_f + fl
while lines and lines[-1] == "":
    lines.pop()
open(path, "w").write("\n".join(lines + tail + tail_f) + "\n")
print("tail_close: %d backs of tail skins and the bay box, %d triangles of turbine discs (winding %+d)" % (nb, len(tris) - nd, WIND))

sp = os.path.join(ST, "typhoon_surfaces.txt")
if ab_tris and os.path.exists(sp):
    rows = open(sp).read().rstrip("\n").split("\n")
    src = [r for r in rows if r.startswith("airbrake ")]
    rows = [r for r in rows if not r.startswith(("airbrake_inner ", "airbrake_holes "))]
    if src:
        rows += [src[0].replace("airbrake ", n_ + " ", 1) for n_ in ("airbrake_inner", "airbrake_holes")]
    open(sp, "w").write("\n".join(rows) + "\n")
mp = os.path.join(ST, "typhoon_materials.txt")
rows = [r for r in open(mp).read().rstrip("\n").split("\n") if not r.startswith("abinner ")]
open(mp, "w").write("\n".join(rows + ["abinner color=#41464B smooth=0.32 metal=0.1"]) + "\n")
print("tail_close: airbrake underside %d triangles" % len(ab_tris))
