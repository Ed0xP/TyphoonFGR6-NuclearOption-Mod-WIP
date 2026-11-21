import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ST = sys.argv[1]
path = os.path.join(ST, "typhoon.obj")

BAY_Z = (-2.80, 0.80)
W = 0.40
WB = 0.56
SLOT_R = 0.29
STORE_CLEAR = 0.28
CEIL = SLOT_R + STORE_CLEAR + SLOT_R + STORE_CLEAR + 0.03
CHAMF = 0.22
SKIN_IN = 0.012
DOOR_OPEN = 100.0
STORE_Z = 0.30
RIB_STEP, RIB_W, RIB_D = 0.45, 0.035, 0.035

lines = open(path).read().split("\n")
V, VT, VN, VLINE, groups, cur = [], [], [], [], [], None
for i, l in enumerate(lines):
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vt "):
        VT.append([float(x) for x in l.split()[1:3]])
    elif l.startswith("vn "):
        VN.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("o ") or l.startswith("g "):
        cur = dict(name=l.split()[1], o_line=i, lines=[], faces=[], flines=[], mtl=None)
        groups.append(cur)
    elif l.startswith("usemtl") and cur is not None:
        cur["mtl"] = l.split()[1]
        cur["lines"].append(i)
    elif l.startswith("f ") and cur is not None:
        cur["lines"].append(i)
        cur["flines"].append(i)
        cur["faces"].append([tuple(int(a) if a else 0 for a in (c.split("/") + ["", ""])[:3]) for c in l.split()[1:]])
V, VT, VN = np.array(V), np.array(VT), np.array(VN)
by = {g["name"]: g for g in groups}
assert "fuselage_bay" not in by, "bay_rework.py has already run on this OBJ"
for n in ("fuselage", "bay_door_L", "bay_door_R", "bay_doorinner_L", "bay_doorinner_R", "bay_box", "bay_drum"):
    assert n in by, n
drop = set()
tail = []
nv, nvt, nvn = len(V), len(VT), len(VN)


def remove_group(g):
    drop.add(g["o_line"])
    drop.update(g["lines"])


def wind_sign(g):
    s = 0.0
    for f in g["faces"][:300]:
        a, b, c = (V[f[i][0] - 1] for i in range(3))
        if f[0][2]:
            s += np.cross(b - a, c - a) @ VN[f[0][2] - 1]
    return 1 if s >= 0 else -1


WIND = wind_sign(by["fuselage"])


def emit(name, mtl, tris):
    global nv, nvt, nvn
    if not tris:
        return 0
    k = 0
    faces = []
    for t in tris:
        p = [np.asarray(c_[0], float) for c_ in t]
        n = [np.asarray(c_[2], float) for c_ in t]
        if (np.cross(p[1] - p[0], p[2] - p[0]) @ (n[0] + n[1] + n[2])) * WIND < 0:
            t = [t[0], t[2], t[1]]
        for c_ in t:
            nn = np.asarray(c_[2], float)
            tail.append("v %.6f %.6f %.6f" % tuple(c_[0]))
            tail.append("vt %.6f %.6f" % tuple(c_[1]))
            tail.append("vn %.5f %.5f %.5f" % tuple(nn / max(np.linalg.norm(nn), 1e-9)))
        faces.append("f " + " ".join("%d/%d/%d" % (nv + k + j + 1, nvt + k + j + 1, nvn + k + j + 1) for j in range(3)))
        k += 3
    tail.append("o " + name)
    tail.append("usemtl " + mtl)
    tail.extend(faces)
    nv += k
    nvt += k
    nvn += k
    return len(faces)


def tris_of(g):
    out = []
    for f in g["faces"]:
        cs = [(V[c[0] - 1], VT[c[1] - 1] if c[1] else np.zeros(2), VN[c[2] - 1] if c[2] else np.array([0, -1.0, 0]))
              for c in f]
        for j in range(1, len(cs) - 1):
            out.append([cs[0], cs[j], cs[j + 1]])
    return out


fus = by["fuselage"]
old_doors = tris_of(by["bay_door_L"]) + tris_of(by["bay_door_R"])
skin_tris = []
for f in fus["faces"]:
    skin_tris.append(f)
bvh_pts = [Vector(v) for v in V]
bvh_faces = [[c[0] - 1 for c in f] for f in fus["faces"] + by["bay_door_L"]["faces"] + by["bay_door_R"]["faces"]]
bvh = BVHTree.FromPolygons(bvh_pts, bvh_faces)


def skin_y(x, z):
    h = bvh.ray_cast(Vector((x, -5.0, z)), Vector((0, 1, 0)))
    return h[0].y if h[0] is not None else None


z0, z1 = BAY_Z
pts = []
for z in np.linspace(z0, z1, 19):
    for x in (-W, 0.0, W):
        y = skin_y(x, z)
        if y is not None:
            pts.append((z, y))
pts = np.array(pts)
k, c = np.polyfit(pts[:, 0], pts[:, 1], 1)
pitch = math.degrees(math.atan(-k))
F = np.array([0.0, k, 1.0]); F /= np.linalg.norm(F)
U = np.array([0.0, 1.0, -k]); U /= np.linalg.norm(U)
R = np.array([1.0, 0.0, 0.0])
zc = 0.5 * (z0 + z1)
O = np.array([0.0, k * zc + c, zc])
L_half = 0.5 * (z1 - z0) * math.sqrt(1 + k * k)
O = O + U * (pts[:, 1] - (k * pts[:, 0] + c)).max()
print("bay: belly y = %.4f z + %.4f (pitch %.2f deg), half length %.3f, origin %s" % (k, c, pitch, L_half, np.round(O, 4)))


def frame(r, u, s):
    return O + R * r + U * u + F * s


def to_frame(p):
    d = np.asarray(p) - O
    return d @ R, d @ U, d @ F


def skin_u(r, s):
    p = frame(r, 0.0, s)
    y = skin_y(p[0], p[2])
    if y is None:
        return 0.0
    return (np.array([p[0], y, p[2]]) - O) @ U


def clip(poly, keep):
    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        da, db = keep(a[0]), keep(b[0])
        if da >= 0:
            out.append(a)
        if (da >= 0) != (db >= 0):
            t = da / (da - db)
            out.append(tuple(a[j] + (b[j] - a[j]) * t for j in range(3)))
    return out


planes = [lambda p: p[0] + W, lambda p: W - p[0], lambda p: p[2] - z0, lambda p: z1 - p[2]]
cand_lines, outside, inside = set(), [], []
n_junk = 0
junk_out = []
junk_c = []
for fi, f in enumerate(fus["faces"]):
    P = np.array([V[c_[0] - 1] for c_ in f])
    cen = P.mean(0)
    if abs(cen[0]) > W + 0.6 or cen[2] < z0 - 0.6 or cen[2] > z1 + 0.6:
        continue
    nrm = np.cross(P[1] - P[0], P[2] - P[0])
    if np.linalg.norm(nrm) < 1e-12:
        continue
    if P[:, 0].max() <= -W or P[:, 0].min() >= W or P[:, 2].max() <= z0 or P[:, 2].min() >= z1:
        continue
    vn = VN[f[0][2] - 1] if f[0][2] else nrm
    u_c = (cen - O) @ U
    belly = vn[1] < -0.3 * np.linalg.norm(vn) and cen[1] < O[1] + 0.3
    feature = u_c < 0.03
    junk = 0.03 <= u_c < 0.45
    if not (belly or feature or junk):
        continue
    cand_lines.add(fus["flines"][fi])
    if junk and not belly:
        cs_ = [(V[c_[0] - 1], VT[c_[1] - 1] if c_[1] else np.zeros(2), VN[c_[2] - 1] if c_[2] else np.array([0, -1.0, 0])) for c_ in f]
        for j in range(1, len(cs_) - 1):
            rest = [cs_[0], cs_[j], cs_[j + 1]]
            for pl in planes:
                if not rest:
                    break
                o = clip(rest, lambda p, pl=pl: -pl(p))
                if len(o) >= 3:
                    junk_out.append(o)
                rest = clip(rest, pl)
        n_junk += 1
        junk_c.append(cen)
        continue
    cs = [(V[c_[0] - 1], VT[c_[1] - 1] if c_[1] else np.zeros(2), VN[c_[2] - 1] if c_[2] else np.array([0, -1.0, 0])) for c_ in f]
    for j in range(1, len(cs) - 1):
        tri = [cs[0], cs[j], cs[j + 1]]
        rest = tri
        for pl in planes:
            if not rest:
                break
            o = clip(rest, lambda p, pl=pl: -pl(p))
            if len(o) >= 3:
                outside.append(o)
            rest = clip(rest, pl)
        if len(rest) >= 3:
            inside.append(rest)
for tri in old_doors:
    rest = tri
    for pl in planes:
        rest = clip(rest, pl) if rest else []
    if len(rest) >= 3:
        inside.append(rest)
drop.update(cand_lines)
if junk_c:
    print("bay: dropped skin between", np.round(np.min(junk_c, 0), 2), np.round(np.max(junk_c, 0), 2))
print("bay: %d fuselage faces re-cut (%d inside the box dropped), %d pieces stay skin, %d go to the doors" % (len(cand_lines), n_junk, len(outside), len(inside)))


def fan(polys):
    T = []
    for poly in polys:
        for j in range(1, len(poly) - 1):
            T.append([poly[0], poly[j], poly[j + 1]])
    return T


OUT_T = fan(outside)
for nm in ("bay_door_L", "bay_door_R", "bay_doorinner_L", "bay_doorinner_R", "bay_box", "bay_drum"):
    remove_group(by[nm])

GEAR = []
DOOR_T = {}
for s, sgn in (("L", -1), ("R", 1)):
    polys = []
    for poly in inside:
        half = clip(poly, lambda p, sgn=sgn: sgn * p[0])
        if len(half) >= 3:
            polys.append(half)
    T = fan(polys)
    DOOR_T[s] = T
    emit("bay_door_" + s, "airframe", T)
    grey = np.array([0.5, 0.5])
    inner = []
    for t in T:
        inner.append([(np.asarray(cc[0]) + U * SKIN_IN, grey, -np.asarray(cc[2])) for cc in t[::-1]])
    ecount = {}
    key = lambda p: tuple(np.round(p, 4))
    for t in T:
        for j in range(3):
            a, b = t[j][0], t[(j + 1) % 3][0]
            kk = tuple(sorted((key(a), key(b))))
            ecount.setdefault(kk, []).append((np.asarray(a), np.asarray(b)))
    dc = np.mean([np.asarray(cc[0]) for t in T for cc in t], 0)
    n_edge = 0
    for kk, lst in ecount.items():
        if len(lst) != 1:
            continue
        a, b = lst[0]
        if np.linalg.norm(b - a) < 1e-5:
            continue
        on_rim = lambda p: min(abs(abs(p[0]) - W), abs(p[0]), abs(p[2] - z0), abs(p[2] - z1)) < 0.004
        if not (on_rim(a) and on_rim(b)):
            continue
        side = np.cross(b - a, U)
        side /= max(np.linalg.norm(side), 1e-9)
        if side @ ((a + b) / 2 - dc) < 0:
            side = -side
        a2, b2 = a + U * SKIN_IN, b + U * SKIN_IN
        inner.append([(a, grey, side), (b, grey, side), (b2, grey, side)])
        inner.append([(a, grey, side), (b2, grey, side), (a2, grey, side)])
        n_edge += 1
    emit("bay_doorinner_" + s, "bayinner", inner)
    edge_pts = [np.asarray(cc[0]) for t in T for cc in t if abs(abs(cc[0][0]) - W) < 0.002]
    u_edge = float(np.median([(p - O) @ U for p in edge_pts])) if edge_pts else 0.0
    hinge = frame(sgn * W, u_edge + 0.006, 0.0)
    ax = F * (1 if s == "L" else -1)
    a_ = math.radians(60)
    Kx = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    Rm = np.eye(3) + math.sin(a_) * Kx + (1 - math.cos(a_)) * Kx @ Kx
    test = Rm @ (np.array([0.0, hinge[1], hinge[2]]) - hinge) + hinge
    if test[1] > hinge[1]:
        ax = -ax
    fmt = lambda v: " ".join("%.4f" % x for x in v)
    GEAR.append(f"baydoor bay_door_{s} bay_doorinner_{s} hinge {fmt(hinge)} axis {fmt(ax)} open {DOOR_OPEN:.1f}")
    print("bay door %s: %d triangles, %d edge strips, hinge %s" % (s, len(T), n_edge, np.round(hinge, 4)))

def tri_bvh(T):
    pts, fcs = [], []
    for t in T:
        fcs.append([len(pts), len(pts) + 1, len(pts) + 2])
        pts += [Vector(tuple(c_[0])) for c_ in t]
    return BVHTree.FromPolygons(pts, fcs)


def hit_uv(bvh_, T, x, z):
    h = bvh_.ray_cast(Vector((x, -5.0, z)), Vector((0, 1, 0)))
    if h[0] is None:
        return None, None
    t = T[h[2]]
    a, b, c3 = [np.asarray(c_[0]) for c_ in t]
    q = np.array(h[0])
    v0, v1, v2 = b - a, c3 - a, q - a
    d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-14:
        return h[0].y, np.asarray(t[0][1])
    w1 = (d11 * d20 - d01 * d21) / den
    w2 = (d00 * d21 - d01 * d20) / den
    uv = (1 - w1 - w2) * np.asarray(t[0][1]) + w1 * np.asarray(t[1][1]) + w2 * np.asarray(t[2][1])
    return h[0].y, uv


DT = DOOR_T["L"] + DOOR_T["R"]
bd = tri_bvh(DT)
rim = {}
for t in OUT_T + fan(junk_out):
    for c_ in t:
        p_ = np.asarray(c_[0])
        if abs(p_[2] - z0) < 0.002 and abs(p_[0]) <= W + 0.002:
            rim[tuple(np.round(p_[:2], 4))] = np.asarray(c_[1])
lip = []
n_lip, top_gap = 0, 0.0
xs = np.linspace(-W + 0.002, W - 0.002, 81)
low = []
for x in xs:
    yd, uvd = hit_uv(bd, DT, x, z0 + 0.004)
    low.append((yd, uvd))
up_pts = sorted([(k_[0], k_[1], v_) for k_, v_ in rim.items()])
high = []
for i, x in enumerate(xs):
    yd = low[i][0]
    if yd is None:
        high.append(None); continue
    cand = [(px, py, uv) for px, py, uv in up_pts if py > yd + 0.01]
    if len(cand) < 2:
        high.append(None); continue
    L_ = [q for q in cand if q[0] <= x]
    R_ = [q for q in cand if q[0] >= x]
    if not L_ or not R_:
        high.append(None); continue
    l_, r_ = L_[-1], R_[0]
    for q in L_[::-1]:
        if q[1] > l_[1] and x - q[0] < 0.06: l_ = q
    for q in R_:
        if q[1] > r_[1] and q[0] - x < 0.06: r_ = q
    tt = 0.0 if r_[0] == l_[0] else (x - l_[0]) / (r_[0] - l_[0])
    high.append((l_[1] + (r_[1] - l_[1]) * tt, l_[2] * (1 - tt) + r_[2] * tt))
for i in range(len(xs) - 1):
    a_, b_ = (xs[i], low[i], high[i]), (xs[i + 1], low[i + 1], high[i + 1])
    if a_[2] is None or b_[2] is None or a_[1][0] is None or b_[1][0] is None:
        continue
    top_gap = max(top_gap, a_[2][0] - a_[1][0], b_[2][0] - b_[1][0])
    nn = -F
    P = [np.array([a_[0], a_[1][0] - 0.002, z0 - 0.001]), np.array([b_[0], b_[1][0] - 0.002, z0 - 0.001]),
         np.array([b_[0], b_[2][0], z0 - 0.001]), np.array([a_[0], a_[2][0], z0 - 0.001])]
    lip.append([(P[0], a_[1][1], nn), (P[1], b_[1][1], nn), (P[2], b_[2][1], nn)])
    lip.append([(P[0], a_[1][1], nn), (P[2], b_[2][1], nn), (P[3], a_[2][1], nn)])
    n_lip += 1
print("bay: rear lip %d strips, step up to %.3f m" % (n_lip, top_gap))
emit("fuselage_bay", "airframe", OUT_T)
emit("fuselage_baylip", "baylip", lip + fan(junk_out))

NS = 25
ss = np.linspace(-L_half, L_half, NS)


def top_u(r, s):
    p = frame(r, 0.0, s)
    h = bvh.ray_cast(Vector((p[0], 5.0, p[2])), Vector((0, -1, 0)))
    if h[0] is None:
        return None
    return (np.array([p[0], h[0].y, p[2]]) - O) @ U


def ceil_at(s):
    tops = [top_u(r, s) for r in (-WB - 0.03, -WB + CHAMF, -0.30, 0.30, WB - CHAMF, WB + 0.03)]
    tops = [t for t in tops if t is not None]
    return min([CEIL] + [t - 0.06 for t in tops])


def section(s):
    ul, ur = skin_u(-W, s) + SKIN_IN, skin_u(W, s) + SKIN_IN
    ulb, urb = skin_u(-WB + 0.01, s) + SKIN_IN, skin_u(WB - 0.01, s) + SKIN_IN
    c_ = ceil_at(s)
    return [(-W, ul), (-WB, ulb), (-WB, c_ - CHAMF), (-WB + CHAMF, c_), (WB - CHAMF, c_), (WB, c_ - CHAMF),
            (WB, urb), (W, ur)]


secs = [section(s) for s in ss]
print("bay box: ceiling %.3f (front) .. %.3f (rear) above the floor line" % (ceil_at(L_half), ceil_at(-L_half)))
box = []
mid = np.array([0.0, CEIL * 0.5])
for i in range(NS - 1):
    for j in range(len(secs[i]) - 1):
        a, b = secs[i][j], secs[i][j + 1]
        a2, b2 = secs[i + 1][j], secs[i + 1][j + 1]
        e = np.array(b) - np.array(a)
        nr = np.array([-e[1], e[0]])
        if nr @ (mid - (np.array(a) + np.array(b)) / 2) < 0:
            nr = -nr
        n3 = R * nr[0] + U * nr[1]
        P = [frame(a[0], a[1], ss[i]), frame(b[0], b[1], ss[i]), frame(b2[0], b2[1], ss[i + 1]), frame(a2[0], a2[1], ss[i + 1])]
        uv = np.array([0.5, 0.5])
        box.append([(P[0], uv, n3), (P[1], uv, n3), (P[2], uv, n3)])
        box.append([(P[0], uv, n3), (P[2], uv, n3), (P[3], uv, n3)])
for i, nn in ((0, F), (NS - 1, -F)):
    sec = secs[i] + [(r, skin_u(r, ss[i]) + SKIN_IN) for r in np.linspace(W, -W, 17)[1:-1]]
    ring = [frame(r, u, ss[i]) for r, u in sec]
    cen = np.mean(ring, 0)
    for j in range(len(ring)):
        a, b = ring[j], ring[(j + 1) % len(ring)]
        box.append([(cen, np.array([0.5, 0.5]), nn), (a, np.array([0.5, 0.5]), nn), (b, np.array([0.5, 0.5]), nn)])
emit("bay_box", "baywall", box)

ribs = []
for s0 in np.arange(-L_half + 0.30, L_half - 0.2, RIB_STEP):
    for s_ in (s0,):
        sec = section(s_)[1:-1]
        sec2 = section(s_ + RIB_W)[1:-1]
        def inset(sec):
            out = []
            for j, (r, u) in enumerate(sec):
                nrm = np.zeros(2)
                for jj in (j - 1, j):
                    if 0 <= jj < len(sec) - 1:
                        e = np.array(sec[jj + 1]) - np.array(sec[jj])
                        nr = np.array([-e[1], e[0]]) / max(np.linalg.norm(e), 1e-9)
                        if nr @ (mid - (np.array(sec[jj]) + np.array(sec[jj + 1])) / 2) < 0:
                            nr = -nr
                        nrm += nr
                nrm /= max(np.linalg.norm(nrm), 1e-9)
                out.append((r + nrm[0] * RIB_D, u + nrm[1] * RIB_D))
            return out
        in1, in2 = inset(sec), inset(sec2)
        uv = np.array([0.5, 0.5])
        for j in range(len(sec) - 1):
            e = np.array(in1[j + 1]) - np.array(in1[j])
            nr = np.array([-e[1], e[0]])
            if nr @ (mid - (np.array(in1[j]) + np.array(in1[j + 1])) / 2) < 0:
                nr = -nr
            n3 = R * nr[0] + U * nr[1]
            q = [frame(*in1[j], s_), frame(*in1[j + 1], s_), frame(*in2[j + 1], s_ + RIB_W), frame(*in2[j], s_ + RIB_W)]
            ribs += [[(q[0], uv, n3), (q[1], uv, n3), (q[2], uv, n3)], [(q[0], uv, n3), (q[2], uv, n3), (q[3], uv, n3)]]
            for (ss_, A, B, nn) in ((s_, sec, in1, -F), (s_ + RIB_W, sec2, in2, F)):
                q = [frame(*A[j], ss_), frame(*A[j + 1], ss_), frame(*B[j + 1], ss_), frame(*B[j], ss_)]
                ribs += [[(q[0], uv, nn), (q[1], uv, nn), (q[2], uv, nn)], [(q[0], uv, nn), (q[2], uv, nn), (q[3], uv, nn)]]
emit("bay_boxribs", "bayrib", ribs)

axis_u = SLOT_R + STORE_CLEAR


def cylinder(r, s0, s1, seg=24):
    T = []
    uv = np.array([0.5, 0.5])
    p = lambda a, s_: frame(r * math.sin(a), axis_u - r * math.cos(a), s_)
    nr = lambda a: R * math.sin(a) - U * math.cos(a)
    for i in range(seg):
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        T.append([(p(a0, s0), uv, nr(a0)), (p(a1, s0), uv, nr(a1)), (p(a1, s1), uv, nr(a1))])
        T.append([(p(a0, s0), uv, nr(a0)), (p(a1, s1), uv, nr(a1)), (p(a0, s1), uv, nr(a0))])
        for s_, nn in ((s0, -F), (s1, F)):
            T.append([(frame(0, axis_u, s_), uv, nn), (p(a0, s_), uv, nn), (p(a1, s_), uv, nn)])
    return T


drum = cylinder(0.055, -L_half + 0.04, L_half - 0.04)
for s_end in (-L_half + 0.07, L_half - 0.10):
    drum += cylinder(0.11, s_end, s_end + 0.03)
    for i in range(8):
        a = 2 * math.pi * i / 8
        d = R * math.sin(a) - U * math.cos(a)
        side = np.cross(F, d)
        c0 = frame(0, axis_u, s_end)
        corners = [c0 + side * w + F * f_ + d * rr for rr in (0.1, SLOT_R + 0.03) for w in (-0.018, 0.018) for f_ in (0, 0.03)]
        cen = np.mean(corners, 0)
        for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
            pa, pb, pc, pd = [corners[j] for j in q]
            nq = np.cross(pb - pa, pc - pa); nq /= np.linalg.norm(nq)
            if nq @ ((pa + pc) / 2 - cen) < 0:
                nq = -nq
            uv = np.array([0.5, 0.5])
            drum += [[(pa, uv, nq), (pb, uv, nq), (pc, uv, nq)], [(pa, uv, nq), (pc, uv, nq), (pd, uv, nq)]]
emit("bay_drum", "drum", drum)
drum_point = frame(0, axis_u, 0)
fmt = lambda v: " ".join("%.4f" % x for x in v)
GEAR.append(f"bay frame {fmt(O)} forward {fmt(F)} up {fmt(U)} halflength {L_half:.4f}")
GEAR.append(f"drum bay_drum axis {fmt(F)} through {fmt(drum_point)} slot {SLOT_R:.3f}")
station = drum_point - F * STORE_Z
GEAR.append(f"# bay stations (typhoon_hardpoints.txt): {fmt(station)} | {pitch:.2f}, 0.0, 0.0 | rotary")

out = [l for i, l in enumerate(lines) if i not in drop]
while out and out[-1] == "":
    out.pop()
open(path, "w").write("\n".join(out + tail) + "\n")

gp = os.path.join(ST, "typhoon_gear.txt")
gl = [l for l in open(gp).read().rstrip("\n").split("\n")
      if not (l.startswith("baydoor ") or l.startswith("bay frame") or l.startswith("drum ") or l.startswith("# bay stations"))]
open(gp, "w").write("\n".join(gl + GEAR) + "\n")

hp = os.path.join(ST, "typhoon_hardpoints.txt")
st_txt = "%.3f, %.3f, %.3f | %.2f, 0.0, 0.0 | rotary" % (station[0], station[1], station[2], pitch)
hl = []
for l in open(hp).read().rstrip("\n").split("\n"):
    t = l.split("=")[0].strip()
    if t in ("weaponbayMount_L", "weaponbayMount_R"):
        l = "%s = %s" % (t, st_txt)
    elif l.startswith("# --- Internal Weapon Bays"):
        l = "# --- Internal Weapon Bays -> the centre weapon bay (0.80 x 3.60 m): both stations sit on the drum's axis and their"
    hl.append(l)
open(hp, "w").write("\n".join(hl) + "\n")

mp = os.path.join(ST, "typhoon_materials.txt")
ml = [l for l in open(mp).read().rstrip("\n").split("\n") if not l.split(" ")[0] in ("bayinner", "baywall", "bayrib", "baylip")]
ml += ["bayinner color=#AEB3B6 smooth=0.35 metal=0.1",
       "baywall color=#A3A9AD smooth=0.3 metal=0.1",
       "bayrib color=#7E858A smooth=0.35 metal=0.2",
       "baylip color=#3A3E43 smooth=0.3 metal=0.1"]
open(mp, "w").write("\n".join(ml) + "\n")
print("bay_rework: station", st_txt)
print("\n".join(GEAR))
