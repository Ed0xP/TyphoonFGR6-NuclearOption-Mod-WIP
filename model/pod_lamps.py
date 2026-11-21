import math
import os
import sys

import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ST = sys.argv[1]
path = os.path.join(ST, "typhoon.obj")
lines = open(path).read().split("\n")
MINE = ("navlamp_L", "navlamp_R", "navlamp_base", "formlight")
out, skip = [], False
for l in lines:
    if l[:2] in ("o ", "g "):
        skip = l.split()[1] in MINE
        if skip:
            continue
    if not (skip and l.startswith(("f ", "usemtl "))):
        out.append(l)
lines = out
V, VN, g, faces, nvt = [], [], None, {}, 0
for l in lines:
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vn "):
        VN.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vt "):
        nvt += 1
    elif l[:2] in ("o ", "g "):
        g = l.split()[1]
    elif l.startswith("f ") and g in ("pod_L", "pod_R", "fuselage", "fin"):
        c = [t.split("/") for t in l.split()[1:]]
        for j in range(1, len(c) - 1):
            faces.setdefault(g, []).append([(int(c[k][0]) - 1, int(c[k][2]) - 1) for k in (0, j, j + 1)])
V, VN = np.array(V), np.array(VN)

def _pieces(fl):
    par = {}

    def find(a):
        while par.setdefault(a, a) != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    key = {}
    for f in fl:
        ks = [key.setdefault(tuple(np.round(V[i], 4)), i) for i, _ in f]
        for k in ks[1:]:
            par[find(k)] = find(ks[0])
    comp = {}
    for n, f in enumerate(fl):
        comp.setdefault(find(key[tuple(np.round(V[f[0][0]], 4))]), []).append(n)
    return list(comp.values())


BLISTER = []
for nm in ("pod_L", "pod_R"):
    if nm not in faces:
        continue
    Pp = V[sorted({i for f in faces[nm] for i, _ in f})]
    z0, z1, xo = Pp[:, 2].min(), Pp[:, 2].max(), np.abs(Pp[:, 0]).max()
    for comp in _pieces(faces[nm]):
        Q = np.array([V[i] for n in comp for i, _ in faces[nm][n]])
        lo, hi = Q.min(0), Q.max(0)
        frac = ((lo[2] + hi[2]) / 2 - z0) / (z1 - z0)
        if len(comp) < 200 and 0.18 < hi[2] - lo[2] < 0.5 and hi[0] - lo[0] < 0.07 and hi[1] - lo[1] < 0.10 \
                and 0.33 < frac < 0.62 and np.abs(Q[:, 0]).max() > xo - 0.004:
            BLISTER.append((nm, lo - 0.006, hi + 0.006))
            print("pod_lamps: %s blister removed (%d triangles, z %.2f .. %.2f, %.0f mm proud)" % (nm, len(comp), lo[2], hi[2], (hi[0] - lo[0]) * 1000))
if BLISTER:
    out, g = [], None
    for l in lines:
        if l[:2] in ("o ", "g "):
            g = l.split()[1]
        elif l.startswith("f ") and g is not None:
            for nm, lo, hi in BLISTER:
                if g == nm or g == "seam_" + nm:
                    q = np.array([V[int(t.split("/")[0]) - 1] for t in l.split()[1:]])
                    if (q >= lo).all() and (q <= hi).all():
                        l = None
                        break
            if l is None:
                continue
        out.append(l)
    lines = out
    for nm in ("pod_L", "pod_R"):
        keep = []
        for f in faces.get(nm, []):
            q = np.array([V[i] for i, _ in f])
            if not any(b[0] == nm and (q >= b[1]).all() and (q <= b[2]).all() for b in BLISTER):
                keep.append(f)
        faces[nm] = keep

f0 = np.array(faces["fuselage"])
gn = np.cross(V[f0[:, 1, 0]] - V[f0[:, 0, 0]], V[f0[:, 2, 0]] - V[f0[:, 0, 0]])
WIND = 1 if (gn * VN[f0[:, 0, 1]]).sum() >= 0 else -1
groups = {k: [] for k in MINE}


def tri(name, a, b, c, n):
    groups[name].append((np.array(a, float), np.array(b, float), np.array(c, float), np.array(n, float)))


def lamp_unit(lens_name, base_name, surf, out_, fwd, up, L, H, T, seg=32, rings=9):
    def outline(ph, off, k=1.0):
        cx, sy = math.cos(ph), math.sin(ph)
        return cx * (L * (0.75 if cx > 0 else 1.25) * k + off), sy * (H * k + off)

    def lens_pt(i, j):
        th = 0.5 * math.pi * i / rings
        ph = 2 * math.pi * j / seg
        u, v = outline(ph, 0.0, math.cos(th))
        p = surf(u, v) + out_ * (0.0009 + math.sin(th) * T)
        cx, sy = math.cos(ph), math.sin(ph)
        n = fwd * (math.cos(th) * cx / (L * (0.75 if cx > 0 else 1.25))) + up * (math.cos(th) * sy / H) + out_ * (math.sin(th) / T)
        return p, n / np.linalg.norm(n)
    for i in range(rings):
        for j in range(seg):
            a, na = lens_pt(i, j); b, nb = lens_pt(i, j + 1); d, nd = lens_pt(i + 1, j); e, ne = lens_pt(i + 1, j + 1)
            tri(lens_name, a, b, e, [na, nb, ne])
            if i + 1 < rings:
                tri(lens_name, a, e, d, [na, ne, nd])
    prof = ((0.0075, -0.0005), (0.0055, 0.0019), (0.0008, 0.0019), (0.0, 0.0008))
    def bez_pt(k, j):
        ph = 2 * math.pi * j / seg
        u, v = outline(ph, prof[k][0])
        return surf(u, v) + out_ * prof[k][1]
    for k in range(len(prof) - 1):
        inward_step = prof[k + 1][1] < prof[k][1]
        def bez_n(j, k=k, inward_step=inward_step):
            n = np.cross(bez_pt(k, j + 1) - bez_pt(k, j - 1), bez_pt(k + 1, j) - bez_pt(k, j))
            ph = 2 * math.pi * j / seg
            rad = fwd * math.cos(ph) + up * math.sin(ph)
            want = -rad if inward_step else (out_ + rad * 0.3)
            n = n if n @ want > 0 else -n
            return n / max(np.linalg.norm(n), 1e-12)
        for j in range(seg):
            a, b, d, e = bez_pt(k, j), bez_pt(k, j + 1), bez_pt(k + 1, j), bez_pt(k + 1, j + 1)
            na, nb = bez_n(j), bez_n(j + 1)
            tri(base_name, a, b, e, [na, nb, nb]); tri(base_name, a, e, d, [na, nb, na])


def lens(name, c, out_, fwd, up, L, H, T, seg=14, rings=5):
    def pt(i, j):
        th = 0.5 * math.pi * i / rings
        ph = 2 * math.pi * j / seg
        x = math.cos(th) * math.cos(ph)
        x = x * (L * (0.75 if x > 0 else 1.25))
        p = c + fwd * x + up * (math.cos(th) * math.sin(ph) * H) + out_ * (math.sin(th) * T)
        n = fwd * (math.cos(th) * math.cos(ph) / L) + up * (math.cos(th) * math.sin(ph) / H) + out_ * (math.sin(th) / T)
        return p, n / np.linalg.norm(n)
    for i in range(rings):
        for j in range(seg):
            a, na = pt(i, j); b, nb = pt(i, j + 1); d, nd = pt(i + 1, j); e, ne = pt(i + 1, j + 1)
            tri(name, a, b, e, na + nb + ne)
            if i + 1 < rings:
                tri(name, a, e, d, na + ne + nd)


def plate(name, c, out_, fwd, up, hl, hh, t, bev=0.0015):
    q = lambda sx, sy, o, k: c + fwd * (sx * (hl - k)) + up * (sy * (hh - k)) + out_ * o
    top = [q(-1, -1, t, bev), q(1, -1, t, bev), q(1, 1, t, bev), q(-1, 1, t, bev)]
    bot = [q(-1, -1, 0, 0), q(1, -1, 0, 0), q(1, 1, 0, 0), q(-1, 1, 0, 0)]
    tri(name, top[0], top[1], top[2], out_); tri(name, top[0], top[2], top[3], out_)
    for k in range(4):
        m = (k + 1) % 4
        n = np.cross(bot[m] - bot[k], top[k] - bot[k])
        n = n if n @ ((top[k] + top[m]) / 2 - c) > 0 else -n
        tri(name, bot[k], bot[m], top[m], n); tri(name, bot[k], top[m], top[k], n)


Y, Z = np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
for nm, sx in (("pod_L", -1), ("pod_R", 1)):
    if nm not in faces:
        continue
    P = V[sorted({i for f in faces[nm] for i, _ in f})]
    z0, z1 = P[:, 2].min(), P[:, 2].max()
    out_ = np.array([float(sx), 0, 0])

    ids = sorted({i for f in faces[nm] for i, _ in f})
    remap = {i: k for k, i in enumerate(ids)}
    bvh = BVHTree.FromPolygons([Vector(V[i]) for i in ids], [tuple(remap[i] for i, _ in f) for f in faces[nm]])
    yc = (P[:, 1].min() + P[:, 1].max()) / 2

    def skin(z, y_off=0.0):
        h = bvh.ray_cast(Vector((sx * 9.0, yc + y_off, z)), Vector((-float(sx), 0, 0)), 8.0)
        if h[0] is None:
            return np.array([P[:, 0].max() if sx > 0 else P[:, 0].min(), yc + y_off, z]), 0.0
        top = bvh.ray_cast(Vector((h[0].x - sx * 0.05, 5.0, z)), Vector((0, -1.0, 0)), 9.0)
        return np.array(h[0]), (top[0].y - yc) if top[0] is not None else 0.0
    L = z1 - z0
    c, r = skin(z0 + 0.70 * L)

    def surf(u, v, c=c, sx=sx, bvh=bvh):
        h = bvh.ray_cast(Vector((sx * 9.0, c[1] + v, c[2] + u)), Vector((-float(sx), 0, 0)), 8.0)
        if h[0] is None or abs(h[0].x - c[0]) > 0.02:
            return c + Y * v + Z * u
        return np.array(h[0])
    dev = max(abs(surf(u, v)[0] - c[0]) for u in (-0.06, 0, 0.045) for v in (-0.023, 0, 0.023))
    lamp_unit("navlamp_L" if sx < 0 else "navlamp_R", "navlamp_base", surf, out_, Z, Y, 0.041, 0.0145, 0.0095)
    print("pod_lamps: %s lamp laid on the skin (it falls away %.1f mm under the bezel)" % (nm, dev * 1000))
    print("pod_lamps: %s z %.2f .. %.2f, radius %.3f at the lamp, outer face x %.3f" % (nm, z0, z1, r, c[0]))
if "fin" in faces and os.environ.get("FIN_STRIPS"):
    F = np.array([[V[i] for i, _ in f] for f in faces["fin"]])
    Pf = F.reshape(-1, 3)
    y0, y1 = Pf[:, 1].min(), Pf[:, 1].max()
    yy = y0 + 0.55 * (y1 - y0)
    band = Pf[np.abs(Pf[:, 1] - yy) < 0.12]
    if len(band) >= 6:
        zc = (band[:, 2].min() + band[:, 2].max()) / 2
        for sx in (-1, 1):
            side = band[(band[:, 0] * sx > 0) & (np.abs(band[:, 2] - zc) < 0.5)]
            xs = (np.abs(side[:, 0]).max() if len(side) else 0.03) * sx
            sweep = math.radians(38)
            fwd = np.array([0, -math.sin(sweep), math.cos(sweep)])
            up = np.cross(np.array([float(sx), 0, 0]), fwd)
            plate("formlight", np.array([xs, yy, zc]), np.array([float(sx), 0, 0]), fwd, up / np.linalg.norm(up), 0.23, 0.016, 0.0022)
        print("pod_lamps: fin strips at y %.2f, z %.2f, half thickness %.3f" % (yy, zc, abs(xs)))
tail, tail_f = [], []
nv, nvn = len(V), len(VN)
MTL = {"navlamp_L": "navred", "navlamp_R": "navgreen", "navlamp_base": "navbezel", "formlight": "formlight"}
for gname, tl in groups.items():
    if not tl:
        continue
    fl = ["o " + gname, "usemtl " + MTL[gname]]
    for (a, b, c, n) in tl:
        ns = n if n.ndim == 2 else np.array([n, n, n])
        ns = ns / np.maximum(np.linalg.norm(ns, axis=1, keepdims=True), 1e-12)
        if np.linalg.norm(np.cross(b - a, c - a)) < 1e-12:
            continue
        if np.cross(b - a, c - a) @ ns.mean(0) * WIND < 0:
            b, c = c, b
            ns = ns[[0, 2, 1]]
        for p, n1 in zip((a, b, c), ns):
            tail.append("v %.5f %.5f %.5f" % tuple(p))
            tail.append("vn %.4f %.4f %.4f" % tuple(n1))
            tail.append("vt 0.5 0.5")
        fl.append("f " + " ".join("%d/%d/%d" % (nv + 1 + k, nvt + 1 + k, nvn + 1 + k) for k in range(3)))
        nv += 3; nvt += 3; nvn += 3
    tail_f += fl
open(path, "w").write("\n".join(lines + tail + tail_f) + "\n")
mp = os.path.join(ST, "typhoon_materials.txt")
txt = open(mp).read().rstrip("\n")
for ln in ("navred color=#3A0B09 smooth=0.90 metal=0 emitcolor=#FF2414", "navgreen color=#08301A smooth=0.90 metal=0 emitcolor=#1FFF62",
           "formlight color=#8A9468 smooth=0.55 metal=0 emitcolor=#C8F070", "navbezel color=#2A2D31 smooth=0.42 metal=0.55"):
    rows = txt.split("\n")
    hit = [i for i, x in enumerate(rows) if x.startswith(ln.split()[0] + " ")]
    if hit:
        rows[hit[0]] = ln
        txt = "\n".join(rows)
    else:
        txt += "\n" + ln
open(mp, "w").write(txt + "\n")
print("pod_lamps: " + ", ".join("%s %d" % (k, len(v)) for k, v in groups.items() if v))
