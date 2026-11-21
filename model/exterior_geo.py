import math
import os
import sys

import numpy as np
from scipy.interpolate import PchipInterpolator

ST = sys.argv[1]
path = os.path.join(ST, "typhoon.obj")
lines = open(path).read().split("\n")
V, VT, VN = [], [], []
VLINE = []
groups = []
cur = None
for i, l in enumerate(lines):
    if l.startswith("v "):
        VLINE.append(i)
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
assert not any(g["name"].startswith("engine_core") for g in groups), "exterior_geo.py has already run on this OBJ"
by = {g["name"]: g for g in groups}
drop = set()
tail = []
nv, nvt, nvn = len(V), len(VT), len(VN)


def remove(g):
    drop.add(g["o_line"])
    drop.update(g["lines"])


def add_group(name, mtl, P, UV, N, tris, keep_faces=()):
    global nv, nvt, nvn
    for p in P:
        tail.append("v %.6f %.6f %.6f" % tuple(p))
    for t in UV:
        tail.append("vt %.6f %.6f" % tuple(t))
    for n in N:
        tail.append("vn %.5f %.5f %.5f" % tuple(n))
    tail.append("o " + name)
    tail.append("usemtl " + mtl)
    for f in keep_faces:
        tail.append("f " + " ".join("%d/%s/%s" % (a, b if b else "", c if c else "") for a, b, c in f))
    for t in tris:
        tail.append("f " + " ".join("%d/%d/%d" % (nv + i + 1, nvt + i + 1, nvn + i + 1) for i in t))
    nv += len(P)
    nvt += len(UV)
    nvn += len(N)


def fix_winding(P, N, tris):
    out = []
    for a, b, c in tris:
        n = np.cross(P[b] - P[a], P[c] - P[a])
        out.append((a, b, c) if n @ (N[a] + N[b] + N[c]) >= 0 else (a, c, b))
    return out


def winding_sign(g):
    s = 0.0
    for f in g["faces"][:200]:
        a, b, c = (V[f[i][0] - 1] for i in range(3))
        if f[0][2]:
            s += np.cross(b - a, c - a) @ VN[f[0][2] - 1]
    return 1 if s >= 0 else -1


WIND = winding_sign(by["fuselage"])


def emit(name, mtl, P, UV, N, tris, keep_faces=()):
    P, UV, N = np.asarray(P, float), np.asarray(UV, float), np.asarray(N, float)
    N = N / np.maximum(np.linalg.norm(N, axis=1), 1e-9)[:, None]
    tris = fix_winding(P, N, tris)
    if WIND < 0:
        tris = [(a, c, b) for a, b, c in tris]
    add_group(name, mtl, P, UV, N, tris, keep_faces)
    return len(tris)


g = by["fuselage_nose"]
Z0, ZTIP = 8.675, 10.73
rad_faces = [f for f in g["faces"] if min(V[c[0] - 1][2] for c in f) >= Z0]
rest = [f for f in g["faces"] if min(V[c[0] - 1][2] for c in f) < Z0]
ids = sorted({c[0] - 1 for f in rad_faces for c in f})
RP = V[ids]
uv_of = {}
for f in rad_faces:
    for c in f:
        uv_of[c[0] - 1] = VT[c[1] - 1] if c[1] else (0.5, 0.5)
order = np.argsort(RP[:, 2])
clusters, cl = [], [order[0]]
for i in order[1:]:
    if RP[i, 2] - RP[cl[-1], 2] > 0.05:
        clusters.append(cl)
        cl = []
    cl.append(i)
clusters.append(cl)
KF = 4
zs, yc_s, co_s = [], [], []
for cl in clusters:
    if len(cl) < 12:
        continue
    pts = RP[cl]
    yc = (pts[:, 1].max() + pts[:, 1].min()) / 2
    th = np.arctan2(pts[:, 0], pts[:, 1] - yc)
    r = np.hypot(pts[:, 0], pts[:, 1] - yc)
    ths = np.sort(th)
    gap = np.diff(np.concatenate([ths, [ths[0] + 2 * math.pi]])).max()
    if math.degrees(gap) > 50:
        continue
    A = np.stack([np.cos(k * th) for k in range(KF + 1)], 1)
    co = np.linalg.lstsq(A, r, rcond=None)[0]
    if co[0] <= 0 or np.abs(A @ co - r).max() > 0.02:
        continue
    zs.append(float(pts[:, 2].mean()))
    yc_s.append(yc)
    co_s.append(co)
tip = RP[RP[:, 2].argmax()]
zs.append(float(tip[2]))
yc_s.append(float(tip[1]))
co_s.append(np.zeros(KF + 1))
zs, yc_s, co_s = np.array(zs), np.array(yc_s), np.array(co_s)
print("radome stations:", np.round(zs, 3), "mean radius", np.round(co_s[:, 0], 3))
f_yc = PchipInterpolator(zs, yc_s)
f_co = [PchipInterpolator(zs, co_s[:, k]) for k in range(KF + 1)]
NS, NR = 72, 46


def rad_pt(z, th):
    r = sum(f_co[k](z) * math.cos(k * th) for k in range(KF + 1))
    return np.array([r * math.sin(th), f_yc(z) + r * math.cos(th), z])


zz = zs[0] + (zs[-1] - 0.012 - zs[0]) * (np.linspace(0, 1, NR) ** 1.15)
zz = np.concatenate([[zs[0] - 0.012], zz])
P, N, UVr, tris = [], [], [], []
ids_arr = np.array(ids)
for j, z in enumerate(zz):
    for i in range(NS):
        th = 2 * math.pi * i / NS
        zc = max(z, zs[0])
        p = rad_pt(zc, th)
        if j == 0:
            p = np.array([p[0] * 0.992, f_yc(zc) + (p[1] - f_yc(zc)) * 0.992, z])
        dz, dt = 0.004, 0.002
        a = rad_pt(min(zc + dz, zs[-1] - 1e-4), th) - rad_pt(max(zc - dz, zs[0]), th)
        b = rad_pt(zc, th + dt) - rad_pt(zc, th - dt)
        n = np.cross(b, a)
        if n @ np.array([p[0], p[1] - f_yc(zc), 0.0]) < 0:
            n = -n
        P.append(p)
        N.append(n)
        UVr.append(uv_of[int(ids_arr[np.argmin(((RP - p) ** 2).sum(1))])])
P.append(np.array([0.0, float(f_yc(zs[-1])), zs[-1]]))
N.append(np.array([0.0, 0.0, 1.0]))
UVr.append(uv_of[int(ids_arr[RP[:, 2].argmax()])])
for j in range(len(zz) - 1):
    for i in range(NS):
        a, b = j * NS + i, j * NS + (i + 1) % NS
        c, d = a + NS, b + NS
        tris += [(a, b, d), (a, d, c)]
top = (len(zz) - 1) * NS
for i in range(NS):
    tris.append((top + i, top + (i + 1) % NS, len(P) - 1))
remove(g)
n_r = emit("fuselage_nose", g["mtl"] or "airframe", P, UVr, N, tris, keep_faces=rest)
print("radome: %d old faces -> %d triangles (%d sides, %d rings); %d other nose faces kept" % (len(rad_faces), n_r, NS, len(zz), len(rest)))


def naca(xc, t):
    return 5 * t * (0.2969 * np.sqrt(xc) - 0.1260 * xc - 0.3516 * xc ** 2 + 0.2843 * xc ** 3 - 0.1036 * xc ** 4)


def old_uv_lookup(g):
    T = []
    for f in g["faces"]:
        for k in range(1, len(f) - 1):
            tri = (f[0], f[k], f[k + 1])
            p = np.array([V[c[0] - 1] for c in tri])
            uv = np.array([VT[c[1] - 1] if c[1] else (0.5, 0.5) for c in tri])
            n = np.cross(p[1] - p[0], p[2] - p[0])
            if np.linalg.norm(n) < 1e-10:
                continue
            ny = n[1] / np.linalg.norm(n) * WIND
            T.append((p, uv, ny))
    allp = np.array([p for t in T for p in t[0]])
    alluv = np.array([u for t in T for u in t[1]])

    def look(x, z, upper):
        best = None
        for p, uv, ny in T:
            if (ny > 0.3) != upper and abs(ny) > 0.3:
                continue
            if abs(ny) <= 0.3:
                continue
            a, b, c = p[:, [0, 2]]
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-12:
                continue
            l0 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (z - c[1])) / d
            l1 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (z - c[1])) / d
            l2 = 1 - l0 - l1
            m = min(l0, l1, l2)
            if best is None or m > best[0]:
                best = (m, np.clip([l0, l1, l2], 0, 1), uv)
            if m >= 0:
                break
        if best is None:
            return alluv[np.argmin((allp[:, 0] - x) ** 2 + (allp[:, 2] - z) ** 2)]
        w = best[1] / best[1].sum()
        return w @ best[2]
    return look


def build_canard(sx, g):
    look = old_uv_lookup(g)
    LE0, LE1 = np.array([0.512, 8.415]), np.array([1.876, 6.995])
    TE0, TE1 = np.array([0.643, 6.968]), np.array([1.868, 6.622])
    Y0, Y1 = 0.088, -0.193
    T0, T1 = 0.060, 0.042
    NSP, NC = 12, 20
    be = (1 - np.cos(np.linspace(0, math.pi, NC))) / 2
    P, N, UV, tris = [], [], [], []
    ss = list(np.linspace(0, 1, NSP)) + [1.0]
    for j, s in enumerate(ss):
        le, te = LE0 + (LE1 - LE0) * s, TE0 + (TE1 - TE0) * s
        ch = np.linalg.norm(te - le)
        ym = Y0 + (Y1 - Y0) * s
        tk = (T0 + (T1 - T0) * s) * (0.0 if j == len(ss) - 1 else 1.0)
        out = 0.012 if j == len(ss) - 1 else 0.0
        ring = []
        for side in (1, -1):
            rng = range(NC) if side == 1 else range(NC - 2, 0, -1)
            for i in rng:
                xz = le + (te - le) * be[i]
                yt = naca(be[i], tk) * ch
                ring.append((np.array([sx * (xz[0] + out), ym + side * yt, xz[1]]), side, be[i]))
        for p, side, b_ in ring:
            P.append(p)
            UV.append(look(p[0], p[2], side > 0))
            dyt = (naca(min(b_ + 0.01, 1), 1.0) - naca(max(b_ - 0.01, 0), 1.0)) / 0.02
            sl = dyt * (T0 + (T1 - T0) * s)
            d = (te - le) / max(ch, 1e-9)
            n = np.array([-sx * 0.0, side * 1.0, 0.0]) - np.array([sx * d[0], 0, d[1]]) * sl
            if b_ < 1e-6:
                n = -np.array([sx * d[0], 0.0, d[1]])
            N.append(n + (np.array([sx * 2.0, 0, 0]) if j == len(ss) - 1 else 0))
    M = 2 * NC - 2
    for j in range(len(ss) - 1):
        for i in range(M):
            a, b = j * M + i, j * M + (i + 1) % M
            c, d = a + M, b + M
            tris += [(a, b, d), (a, d, c)]
    c0 = len(P)
    P.append(np.mean([P[i] for i in range(M)], axis=0))
    UV.append(UV[0])
    N.append(np.array([-sx * 1.0, 0, 0]))
    for i in range(M):
        P.append(P[i]); UV.append(UV[i]); N.append(np.array([-sx * 1.0, 0, 0]))
    for i in range(M):
        tris.append((c0, c0 + 1 + i, c0 + 1 + (i + 1) % M))
    return P, UV, N, tris


for nm, sx in (("canard_R", 1), ("canard_L", -1)):
    g = by[nm]
    P, UV, N, tris = build_canard(sx, g)
    remove(g)
    n_c = emit(nm, g["mtl"] or "airframe", P, UV, N, tris)
    print("%s: %d old faces -> %d triangles" % (nm, len(g["faces"]), n_c))


def revolve(profile, ax, seg, flip=False):
    P, N, tris = [], [], []
    for k, (z, r) in enumerate(profile):
        z0, r0 = profile[max(k - 1, 0)]
        z1, r1 = profile[min(k + 1, len(profile) - 1)]
        nz, nr = -(r1 - r0), (z1 - z0)
        if flip:
            nz, nr = -nz, -nr
        for i in range(seg):
            a = 2 * math.pi * i / seg
            P.append(np.array([ax[0] + r * math.cos(a), ax[1] + r * math.sin(a), z]))
            N.append(np.array([nr * math.cos(a), nr * math.sin(a), nz]))
    for k in range(len(profile) - 1):
        for i in range(seg):
            a, b = k * seg + i, k * seg + (i + 1) % seg
            tris += [(a, b, b + seg), (a, b + seg, a + seg)]
    return P, N, tris


def box(c, ux, uy, uz, hx, hy, hz):
    P, N, tris = [], [], []
    for axis, (u, h) in enumerate(((ux, hx), (uy, hy), (uz, hz))):
        o = [(ux, hx), (uy, hy), (uz, hz)]
        a, b = o[(axis + 1) % 3], o[(axis + 2) % 3]
        for sg in (1, -1):
            base = len(P)
            for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                P.append(c + u * h * sg + a[0] * a[1] * sa + b[0] * b[1] * sb)
                N.append(u * sg)
            tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return P, N, tris


for nm, sx in (("engine_core_R", 1), ("engine_core_L", -1)):
    ax = (sx * 0.4855, -0.0392)
    P, N, tris = [], [], []

    def addm(m):
        base = len(P)
        P.extend(m[0]); N.extend(m[1]); tris.extend([(a + base, b + base, c + base) for a, b, c in m[2]])
    ZF = -2.98
    addm(revolve([(-2.50, 0.125), (-2.80, 0.118), (-3.00, 0.092), (-3.14, 0.052), (-3.22, 0.012), (-3.235, 0.0)], ax, 28, flip=True))
    addm(revolve([(-2.52, 0.34), (-2.50, 0.34), (-2.50, 0.125)], ax, 40, flip=True))
    addm(revolve([(ZF + 0.03, 0.262), (ZF - 0.025, 0.245), (ZF - 0.025, 0.285), (ZF + 0.03, 0.268), (ZF + 0.03, 0.262)], ax, 48))
    for k in range(15):
        a = 2 * math.pi * (k + 0.5) / 15
        ur = np.array([math.cos(a), math.sin(a), 0.0])
        ut = np.array([-math.sin(a), math.cos(a), 0.0])
        uz = np.array([0.0, 0.0, 1.0])
        c = np.array([ax[0], ax[1], ZF]) + ur * 0.225
        addm(box(c, ur, ut, uz, 0.118, 0.011, 0.030))
    UV = [(0.5, 0.5)] * len(P)
    n_e = emit(nm, "abmetal", P, UV, N, tris)
    print("%s: %d triangles" % (nm, n_e))

from PIL import Image
SRCP = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dev", "inputs", "airframe_src_base.png")
if os.path.exists(SRCP):
    simg = np.asarray(Image.open(SRCP).convert("RGB")).astype(np.float32) / 255
    slum, ssat = simg.mean(2), simg.max(2) - simg.min(2)
    SH, SW = slum.shape

    def px_of(uv):
        return min(max(int((1 - uv[1]) * SH), 0), SH - 1), min(max(int(uv[0] * SW), 0), SW - 1)
    ball = []
    for gname in ("fuselage_nose", "fuselage_cockpit"):
        for f in by[gname]["faces"]:
            if any(c[1] == 0 for c in f):
                continue
            c_ = V[[c[0] - 1 for c in f]].mean(0)
            if not (-0.52 < c_[0] < -0.15 and 0.50 < c_[1] < 0.85 and 8.2 < c_[2] < 8.75):
                continue
            if 0.12 < slum[px_of(VT[[c[1] - 1 for c in f]].mean(0))] < 0.33:
                ball.append(f)
    if len(ball) >= 12:
        BP = V[sorted({c[0] - 1 for f in ball for c in f})]
        A_ = np.c_[2 * BP, np.ones(len(BP))]
        sol = np.linalg.lstsq(A_, (BP ** 2).sum(1), rcond=None)[0]
        C = sol[:3]
        R0 = math.sqrt(sol[3] + (C ** 2).sum())
        dist = np.linalg.norm(BP - C, axis=1)
        Rb = min(float(dist.max()) + 0.003, R0 + 0.015)
        look = np.array([-0.50, 0.22, 0.84])
        look = look / np.linalg.norm(look)
        e1 = np.cross(look, [0.0, 1.0, 0.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(look, e1)
        RL, RBZ = min(0.036, Rb * 0.42), min(0.045, Rb * 0.52)
        a_b = math.asin(RBZ / Rb)
        SEG, RINGS = 32, 20
        P, N, tris = [], [], []
        for j in range(RINGS + 1):
            th = a_b + (math.pi - a_b) * j / RINGS
            for i in range(SEG):
                ph = 2 * math.pi * i / SEG
                n = math.cos(th) * look + math.sin(th) * (math.cos(ph) * e1 + math.sin(ph) * e2)
                P.append(C + Rb * n)
                N.append(n)
        for j in range(RINGS):
            for i in range(SEG):
                a, b = j * SEG + i, j * SEG + (i + 1) % SEG
                tris += [(a, b, b + SEG), (a, b + SEG, a + SEG)]
        nb = emit("irst_ball", "irstglass", P, [(0.5, 0.5)] * len(P), N, tris)
        hb = Rb * math.cos(a_b)
        P, N, tris = [], [], []
        for r_, h_, n_ in ((RBZ, hb, 0.55), (RBZ - 0.003, hb + 0.0025, 1.0), (RL, hb + 0.0025, 1.0), (RL, hb - 0.0005, -0.6)):
            for i in range(SEG):
                ph = 2 * math.pi * i / SEG
                rad = math.cos(ph) * e1 + math.sin(ph) * e2
                P.append(C + h_ * look + r_ * rad)
                N.append(look * abs(n_) + rad * (math.sqrt(1 - n_ * n_) * (1 if n_ > 0 else -1)))
        for j in range(3):
            for i in range(SEG):
                a, b = j * SEG + i, j * SEG + (i + 1) % SEG
                tris += [(a, b, b + SEG), (a, b + SEG, a + SEG)]
        nz_ = emit("irst_bezel", "irstmetal", P, [(0.5, 0.5)] * len(P), N, tris)
        P, N, tris = [C + (hb - 0.0005) * look], [look], []
        for i in range(SEG):
            ph = 2 * math.pi * i / SEG
            P.append(C + (hb - 0.0005) * look + RL * (math.cos(ph) * e1 + math.sin(ph) * e2))
            N.append(look)
        for i in range(SEG):
            tris.append((0, 1 + i, 1 + (i + 1) % SEG))
        nl = emit("irst_lens", "irstlens", P, [(0.5, 0.5)] * len(P), N, tris)
        print("irst: %d source faces, centre %s, radius %.3f (fit %.3f), looks %s; ball %d, bezel %d, lens %d triangles"
              % (len(ball), np.round(C, 3), Rb, R0, np.round(look, 2), nb, nz_, nl))
    else:
        print("irst: sensor ball not found in the source model (%d faces); left as it is" % len(ball))

NZ_PIV = -3.55
NZ_ROOT, NZ_EXIT = -3.56, -4.17
NZ_FLAPS = 16


def nz_outer(t):
    return 0.440 - (0.440 - 0.338) * t ** 1.04


def rec_t(t):
    a = min(max(t / 0.08, 0.0), 1.0)
    b = min(max((1.0 - t) / 0.10, 0.0), 1.0)
    return a * a * (3 - 2 * a) * b * b * (3 - 2 * b)


def nz_inner(t):
    if t < 0.55:
        return 0.322 - (0.322 - 0.292) * (t / 0.55) ** 0.9
    return 0.292 + (0.312 - 0.292) * ((t - 0.55) / 0.45) ** 1.3


for nm, sx in (("petals_R", 1), ("petals_L", -1)):
    if nm in by:
        remove(by[nm])
    fx_ = by.get("nozzle_" + nm[-1])
    if fx_ is not None:
        n_cut = 0
        for f, li in zip(fx_["faces"], fx_["flines"]):
            p_ = V[[c[0] - 1 for c in f]]
            r_ = np.hypot(p_[:, 0] - sx * 0.4855, p_[:, 1] + 0.0392)
            if p_[:, 2].max() < -3.585 and r_.max() < 0.445:
                drop.add(li)
                n_cut += 1
        print("nozzle_%s: %d faces inside the petals' envelope removed" % (nm[-1], n_cut))
    A = np.array([sx * 0.4855, -0.0392])
    P, N, UV, tris = [], [], [], []
    NT = 18
    ts = [(i / NT) for i in range(NT + 1)]

    def zt(t):
        return NZ_ROOT + (NZ_EXIT - NZ_ROOT) * t

    def pt(r, a, z):
        return np.array([A[0] + r * math.cos(a), A[1] + r * math.sin(a), z])

    def strip(rows, cols_u, nfun, uvfun):
        base = len(P)
        nr, nc = len(rows), len(rows[0])
        for i in range(nr):
            for j in range(nc):
                P.append(rows[i][j]); N.append(nfun(i, j)); UV.append(uvfun(i, j))
        for i in range(nr - 1):
            for j in range(nc - 1):
                a_, b_ = base + i * nc + j, base + i * nc + j + 1
                c_, d_ = base + (i + 1) * nc + j + 1, base + (i + 1) * nc + j
                tris.extend([(a_, b_, c_), (a_, c_, d_)])
    dA = 2 * math.pi / NZ_FLAPS
    slope_o = lambda t: (nz_outer(min(t + 0.01, 1)) - nz_outer(max(t - 0.01, 0))) / ((NZ_EXIT - NZ_ROOT) * 0.02)
    for k in range(NZ_FLAPS):
        a0 = k * dA
        parts = ((a0, a0 + 0.62 * dA, 0.0), (a0 + 0.62 * dA, a0 + dA, 0.006))
        for (aa, ab, rec) in parts:
            cols = 6
            rows = []
            for t in ts:
                r = nz_outer(t) - rec * rec_t(t)
                pa, pb = pt(r, aa, zt(t)), pt(r, ab, zt(t))
                rows.append([pa + (pb - pa) * (c / cols) for c in range(cols + 1)])
            am = (aa + ab) / 2

            def nf(i, j, am=am, t_=None):
                t = ts[i]
                sl = -slope_o(t)
                n = np.array([math.cos(am), math.sin(am), -sl * 1.0])
                return n / np.linalg.norm(n)

            def uvf(i, j, aa=aa, ab=ab, cols=cols):
                return ((aa + (ab - aa) * j / cols) / (2 * math.pi), 0.5 + 0.5 * ts[i])
            strip(rows, cols, nf, uvf)
        for a_e, sgn in ((a0 + 0.62 * dA, 1), (a0 + dA, -1)):
            rows = []
            for t in ts:
                r = nz_outer(t)
                rows.append([pt(r - 0.006 * rec_t(t), a_e, zt(t)), pt(r, a_e, zt(t))])
            tn = np.array([-math.sin(a_e), math.cos(a_e), 0.0]) * sgn
            strip(rows, 1, lambda i, j, tn=tn: tn, lambda i, j, a_e=a_e: (a_e / (2 * math.pi), 0.5 + 0.5 * ts[i]))
    SEGI = NZ_FLAPS * 4
    rows = []
    for t in ts:
        rows.append([pt(nz_inner(t), 2 * math.pi * j / SEGI, zt(t)) for j in range(SEGI + 1)])

    def nfi(i, j):
        a = 2 * math.pi * j / SEGI
        t = ts[i]
        sl = (nz_inner(min(t + 0.01, 1)) - nz_inner(max(t - 0.01, 0))) / ((NZ_EXIT - NZ_ROOT) * 0.02)
        n = -np.array([math.cos(a), math.sin(a), -sl])
        return n / np.linalg.norm(n)
    strip(rows, SEGI, nfi, lambda i, j: (j / SEGI, 0.5 * ts[i] * 0.97))
    rows = []
    for t in ts:
        rows.append([pt(nz_inner(t) + 0.003, 2 * math.pi * j / SEGI, zt(t)) for j in range(SEGI + 1)])
    strip(rows, SEGI, lambda i, j: -nfi(i, j), lambda i, j: (j / SEGI, 0.5 + 0.5 * ts[i]))
    SEGL = 96
    lipr = []
    for q in range(5):
        th = math.pi * q / 4
        ro, ri = nz_outer(1.0) - 0.002, nz_inner(1.0)
        rc, rr = (ro + ri) / 2, (ro - ri) / 2
        lipr.append((rc + rr * math.cos(th), NZ_EXIT - rr * math.sin(th) * 0.8, th))
    rows = [[pt(r_, 2 * math.pi * j / SEGL, z_) for j in range(SEGL + 1)] for (r_, z_, th) in lipr]

    def nfl(i, j):
        a = 2 * math.pi * j / SEGL
        th = lipr[i][2]
        n = np.array([math.cos(a) * math.cos(th), math.sin(a) * math.cos(th), -math.sin(th)])
        return n / np.linalg.norm(n)
    strip(rows, SEGL, nfl, lambda i, j: (j / SEGL, 0.4915 + 0.0085 * i / 4))
    rows = [[pt(nz_inner(0.0), 2 * math.pi * j / SEGL, NZ_ROOT) for j in range(SEGL + 1)],
            [pt(nz_outer(0.0), 2 * math.pi * j / SEGL, NZ_ROOT) for j in range(SEGL + 1)]]
    strip(rows, SEGL, lambda i, j: np.array([0.0, 0.0, 1.0]), lambda i, j: (j / SEGL, 0.001))
    rows = [[pt(nz_inner(0.0), 2 * math.pi * j / SEGL, NZ_ROOT - 0.002) for j in range(SEGL + 1)],
            [pt(nz_outer(0.0), 2 * math.pi * j / SEGL, NZ_ROOT - 0.002) for j in range(SEGL + 1)]]
    strip(rows, SEGL, lambda i, j: np.array([0.0, 0.0, -1.0]), lambda i, j: (j / SEGL, 0.001))
    n_p = emit(nm, "nozzle", P, UV, N, tris)
    print("%s: rebuilt, %d triangles (root r %.3f, exit r %.3f / %.3f, throat %.3f)" % (nm, n_p, nz_outer(0), nz_outer(1), nz_inner(1), nz_inner(0.6)))

RS, BAND = 0.436, math.radians(40)
new_surf = []
for nm, sx in (("nozcollar_R", 1), ("nozcollar_L", -1)):
    Cc = np.array([sx * 0.4855, -0.0392, -3.55])
    SEGc, RNG = 48, 10
    P, N, tris = [], [], []
    for j in range(RNG + 1):
        th = BAND * j / RNG
        for i in range(SEGc):
            ph = 2 * math.pi * i / SEGc
            n = np.array([math.cos(th) * math.cos(ph), math.cos(th) * math.sin(ph), math.sin(th)])
            P.append(Cc + RS * n)
            N.append(n)
    for j in range(RNG):
        for i in range(SEGc):
            a_, b_ = j * SEGc + i, j * SEGc + (i + 1) % SEGc
            tris += [(a_, b_, b_ + SEGc), (a_, b_ + SEGc, a_ + SEGc)]
    nb_ = len(P)
    for k_ in range(nb_):
        P.append(Cc + (RS - 0.002) * N[k_])
        N.append(-N[k_])
    for (a_, b_, c_) in list(tris):
        tris.append((nb_ + a_, nb_ + c_, nb_ + b_))
    n_k = emit(nm, "nozjoint", P, [(0.5, 0.5)] * len(P), N, tris)
    new_surf.append("%s %.4f %.4f %.4f %.4f %.4f %.4f vectoring" % (nm, Cc[0], Cc[1], Cc[2], Cc[0], Cc[1], Cc[2] - 1.0))
    print("%s: %d triangles" % (nm, n_k))
_mp = os.path.join(ST, "typhoon_materials.txt")
if os.path.exists(_mp):
    _mt = open(_mp).read().rstrip("\n")
    if not any(x.startswith("nozjoint ") for x in _mt.split("\n")):
        open(_mp, "w").write(_mt + "\nnozjoint color=#1B1D1F smooth=0.46 metal=0.55\n")
sp = os.path.join(ST, "typhoon_surfaces.txt")
if os.path.exists(sp):
    stxt = open(sp).read().rstrip("\n")
    for l_ in new_surf:
        if not any(x.startswith(l_.split()[0] + " ") for x in stxt.split("\n")):
            stxt += "\n" + l_
    open(sp, "w").write(stxt + "\n")

from scipy.spatial import cKDTree
_fus = by["fuselage"]
_moved = {"wing_L": [], "wing_R": []}
_wing_planes = {}
for nm in ("wing_L", "wing_R"):
    cs, ns_, ps = [], [], []
    for f in by[nm]["faces"]:
        p_ = V[[c[0] - 1 for c in f]]
        n = np.cross(p_[1] - p_[0], p_[2] - p_[0])
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        cs.append(p_.mean(0)); ns_.append(n / ln); ps.append(p_[0])
    _wing_planes[nm] = (cKDTree(np.array(cs)), np.array(ns_), np.array(ps))
_keep_f, _keep_l = [], []
for f, li in zip(_fus["faces"], _fus["flines"]):
    p_ = V[[c[0] - 1 for c in f]]
    c_ = p_.mean(0)
    n = np.cross(p_[1] - p_[0], p_[2] - p_[0])
    ln = np.linalg.norm(n)
    nm = "wing_R" if c_[0] > 0 else "wing_L"
    hit = False
    if ln > 1e-12 and abs(c_[0]) > 0.70 and abs(n[1] / ln) > 0.8:
        n /= ln
        tree, wn, wp = _wing_planes[nm]
        for k in tree.query_ball_point(c_, 0.9):
            if abs(n @ wn[k]) > math.cos(math.radians(15)) and np.abs((p_ - wp[k]) @ wn[k]).max() < 0.025:
                hit = True
                break
    if hit:
        _moved[nm].append(f)
        drop.add(li)
    else:
        _keep_f.append(f)
        _keep_l.append(li)
_fus["faces"] = _keep_f
_fus["flines"] = _keep_l
for nm in ("wing_L", "wing_R"):
    by[nm]["faces"] = by[nm]["faces"] + _moved[nm]
print("wing roots: %d / %d fuselage faces in the wings' planes moved to wing_L / wing_R" % (len(_moved["wing_L"]), len(_moved["wing_R"])))
WING_SUB = int(os.environ.get("WING_SUB", "4"))
WING_R = float(os.environ.get("WING_R", "0.16"))
for nm in ("wing_L", "wing_R"):
    g = by[nm]
    faces = [[c[0] - 1 for c in f] for f in g["faces"] if len(f) == 3]
    fuv = [[VT[c[1] - 1] if c[1] else np.zeros(2) for c in f] for f in g["faces"] if len(f) == 3]
    fn, fa = [], []
    for f in faces:
        n = np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]]) * WIND
        a_ = np.linalg.norm(n)
        fn.append(n / max(a_, 1e-12))
        fa.append(a_ / 2)
    fn, fa = np.array(fn), np.array(fa)
    sp, sn, sw = [], [], []
    for k, f in enumerate(faces):
        P0, P1, P2 = V[f[0]], V[f[1]], V[f[2]]
        L = max(np.linalg.norm(P1 - P0), np.linalg.norm(P2 - P1), np.linalg.norm(P0 - P2))
        m = int(min(max(math.ceil(L / 0.025), 1), 160))
        pts = [(i / m, j / m) for i in range(m + 1) for j in range(m + 1 - i)]
        for u_, v_ in pts:
            sp.append(P0 + (P1 - P0) * u_ + (P2 - P0) * v_)
            sn.append(fn[k])
            sw.append(fa[k] / len(pts))
    sgn_x = -1.0 if nm == "wing_L" else 1.0
    n_wing_samples = len(sp)
    root_faces = []
    for f, li in zip(by["fuselage"]["faces"], by["fuselage"]["flines"]):
        if len(f) != 3 or li in drop:
            continue
        p_ = V[[c[0] - 1 for c in f]]
        c_ = p_.mean(0)
        if not (0.45 < c_[0] * sgn_x < 1.75 and -3.8 < c_[2] < 3.3 and -0.75 < c_[1] < 0.75):
            continue
        n = np.cross(p_[1] - p_[0], p_[2] - p_[0]) * WIND
        a_ = np.linalg.norm(n)
        if a_ < 1e-12 or abs(n[1] / a_) < 0.35:
            continue
        root_faces.append((f, li, n / a_))
        L = max(np.linalg.norm(p_[1] - p_[0]), np.linalg.norm(p_[2] - p_[1]), np.linalg.norm(p_[0] - p_[2]))
        m = int(min(max(math.ceil(L / 0.025), 1), 160))
        pts = [(i / m, j / m) for i in range(m + 1) for j in range(m + 1 - i)]
        for u_, v_ in pts:
            sp.append(p_[0] + (p_[1] - p_[0]) * u_ + (p_[2] - p_[0]) * v_)
            sn.append(n / a_)
            sw.append(a_ / 2 / len(pts))
    sp, sn, sw = np.array(sp), np.array(sn), np.array(sw)
    tree = cKDTree(sp)
    cosl = math.cos(math.radians(55))

    def _terms(x, z):
        return np.stack([x ** i * z ** j for i in range(5) for j in range(5 - i)], -1)
    fits = {}
    for side, sg in (("up", 1.0), ("low", -1.0)):
        msk = (sn[:, 1] * sg > 0.93) & (np.arange(len(sn)) < n_wing_samples)
        if msk.sum() < 200:
            continue
        A_ = _terms(sp[msk, 0], sp[msk, 2]) * np.sqrt(sw[msk])[:, None]
        coef = np.linalg.lstsq(A_, sp[msk, 1] * np.sqrt(sw[msk]), rcond=None)[0]
        fits[side] = (coef, sg)

    def fit_normal(p, sg_coef):
        coef, sg = sg_coef
        x, z, e = p[0], p[2], 1e-3
        f0 = _terms(np.array([x - e, x + e, x, x]), np.array([z, z, z - e, z + e])) @ coef
        dx, dz = (f0[1] - f0[0]) / (2 * e), (f0[3] - f0[2]) / (2 * e)
        n = np.array([-dx, 1.0, -dz]) * sg
        return n / np.linalg.norm(n)

    def field0(p, own):
        idx = tree.query_ball_point(p, WING_R)
        if not idx:
            return own
        d2 = ((sp[idx] - p) ** 2).sum(1)
        w = sw[idx] * np.exp(-d2 / (2 * (WING_R / 2.2) ** 2)) * ((sn[idx] @ own) > cosl)
        n = (sn[idx] * w[:, None]).sum(0)
        ln = np.linalg.norm(n)
        return n / ln if ln > 1e-9 else own

    def field(p, own):
        n = field0(p, own)
        side = "up" if n[1] > 0 else "low"
        if side not in fits or abs(n[1]) < 0.85:
            return n
        nf = fit_normal(p, fits[side])
        ang = math.degrees(math.acos(min(1.0, max(-1.0, float(nf @ n)))))
        w = min(max((5.0 - ang) / 2.5, 0.0), 1.0)
        if w <= 0:
            return n
        m_ = nf * w + n * (1 - w)
        return m_ / np.linalg.norm(m_)
    vkey = {}
    P, Nl, nkey, F = [], [], {}, []
    Tl, tkey = [], {}

    def vert(ws):
        key = tuple(sorted((i, w) for i, w in ws if w > 0))
        if key not in vkey:
            vkey[key] = len(P)
            P.append(sum(V[i] * (w / WING_SUB) for i, w in key))
        return vkey[key]
    for k, f in enumerate(faces):
        ia, ib, ic = f
        grid = {}
        for i in range(WING_SUB + 1):
            for j in range(WING_SUB + 1 - i):
                grid[(i, j)] = vert(((ia, WING_SUB - i - j), (ib, i), (ic, j)))
        uvg = {}
        for i in range(WING_SUB + 1):
            for j in range(WING_SUB + 1 - i):
                uv_ = (fuv[k][0] * (WING_SUB - i - j) + fuv[k][1] * i + fuv[k][2] * j) / WING_SUB
                ur = (round(float(uv_[0]), 6), round(float(uv_[1]), 6))
                if ur not in tkey:
                    tkey[ur] = len(Tl)
                    Tl.append(ur)
                uvg[grid[(i, j)]] = tkey[ur]
        tl = []
        for i in range(WING_SUB):
            for j in range(WING_SUB - i):
                tl.append((grid[(i, j)], grid[(i + 1, j)], grid[(i, j + 1)]))
                if i + j < WING_SUB - 1:
                    tl.append((grid[(i + 1, j)], grid[(i + 1, j + 1)], grid[(i, j + 1)]))
        for t in tl:
            ts = [uvg[v_] for v_ in t]
            ns = []
            for v_ in t:
                ck = (v_, k)
                if ck not in nkey:
                    n = field(P[v_], fn[k])
                    nr = tuple(np.round(n, 4))
                    if nr not in nkey:
                        nkey[nr] = len(Nl)
                        Nl.append(n)
                    nkey[ck] = nkey[nr]
                ns.append(nkey[ck])
            a_, b_, c_ = t
            nsum = Nl[ns[0]] + Nl[ns[1]] + Nl[ns[2]]
            if (np.cross(P[b_] - P[a_], P[c_] - P[a_]) * WIND) @ nsum < 0:
                t, ns, ts = (a_, c_, b_), [ns[0], ns[2], ns[1]], [ts[0], ts[2], ts[1]]
            F.append((t, ns, ts))
    remove(g)
    for p_ in P:
        tail.append("v %.6f %.6f %.6f" % tuple(p_))
    for t_ in Tl:
        tail.append("vt %.6f %.6f" % t_)
    for n in Nl:
        tail.append("vn %.5f %.5f %.5f" % tuple(n))
    tail.append("o " + nm)
    tail.append("usemtl " + (g["mtl"] or "airframe"))
    for t, ns, ts in F:
        tail.append("f " + " ".join("%d/%d/%d" % (nv + t[q] + 1, nvt + ts[q] + 1, nvn + ns[q] + 1) for q in range(3)))
    nv += len(P)
    nvt += len(Tl)
    nvn += len(Nl)
    tris = F
    if root_faces:
        rn = []
        fl = []
        for f, li, n0 in root_faces:
            ids = []
            for c in f:
                nn_ = field0(V[c[0] - 1], n0)
                ids.append(len(rn))
                rn.append(nn_)
            fl.append((f, ids))
            drop.add(li)
        for n in rn:
            tail.append("vn %.5f %.5f %.5f" % tuple(n))
        tail.append("o fuselage_root_" + nm[-1])
        tail.append("usemtl " + (by["fuselage"]["mtl"] or "airframe"))
        for f, ids in fl:
            tail.append("f " + " ".join("%d/%s/%d" % (c[0], c[1] if c[1] else "", nvn + ids[q] + 1) for q, c in enumerate(f)))
        nvn += len(rn)
        dropped = {li for _, li, _ in root_faces}
        keep_ = [(f, li) for f, li in zip(by["fuselage"]["faces"], by["fuselage"]["flines"]) if li not in dropped]
        by["fuselage"]["faces"] = [f for f, _ in keep_]
        by["fuselage"]["flines"] = [li for _, li in keep_]
        print("%s root: %d fuselage faces given normals from the wing's field (fuselage_root_%s)" % (nm, len(root_faces), nm[-1]))
    print("%s: %d faces -> %d triangles, %d vertices, normals from a %.2f m field" % (nm, len(faces), len(tris), len(P), WING_R))

try:
    import bpy
    from mathutils import Vector as _V3
    from mathutils.bvhtree import BVHTree as _BVH
    _skin_f = []
    for gname in ("fuselage", "fuselage_cockpit", "fuselage_nose"):
        if gname in by:
            _skin_f += [[c[0] - 1 for c in f] for f in by[gname]["faces"]]
    _bvh = _BVH.FromPolygons([_V3(v) for v in V], _skin_f)
    _box = by.get("bay_box")
    n_in = 0
    if _box is not None and "bay_boxribs" in by:
        print("bay box: made to fit by bay_rework.py (2.3.4), left as it is")
        _box = None
    if _box is not None:
        vids = sorted({c[0] - 1 for f in _box["faces"] for c in f})
        for vi in vids:
            p_ = V[vi]
            if p_[1] < 0.0:
                continue
            o = _V3((0.0, -0.10, float(p_[2])))
            d = _V3(tuple(p_)) - o
            L = d.length
            if L < 1e-6:
                continue
            hit = _bvh.ray_cast(o, d.normalized(), L + 0.05)
            if hit[0] is not None and hit[3] < L + 0.012:
                q = o + d.normalized() * max(hit[3] - 0.012, 0.0)
                V[vi] = np.array(q)
                lines[VLINE[vi]] = "v %.6f %.6f %.6f" % tuple(q)
                n_in += 1
    print("bay box: %d vertices pulled inside the skin" % n_in)
except Exception as _e:
    print("bay box: skipped (%s)" % _e)

out = [l for i, l in enumerate(lines) if i not in drop]
while out and out[-1] == "":
    out.pop()
open(path, "w").write("\n".join(out + tail) + "\n")
mt = os.path.join(ST, "typhoon_materials.txt")
txt = open(mt).read()
if not any(l.startswith("nozzle ") for l in txt.split("\n")):
    txt = txt.rstrip("\n") + "\nnozzle base=nozzle_base.png normal=nozzle_normal.png mask=nozzle_mask.png smooth=1 metal=1\n"
    open(mt, "w").write(txt)
if not any(l.startswith("abmetal ") for l in txt.split("\n")):
    open(mt, "w").write(txt.rstrip("\n") + "\nabmetal color=#3A3530 smooth=0.42 metal=0.85\n")
txt = open(mt).read()
for ln_ in ("irstglass color=#0A0C11 smooth=0.95 metal=0", "irstlens color=#5A4630 smooth=0.97 metal=1", "irstmetal color=#5C6064 smooth=0.62 metal=0.9"):
    if not any(l.startswith(ln_.split()[0] + " ") for l in txt.split("\n")):
        txt = txt.rstrip("\n") + "\n" + ln_ + "\n"
open(mt, "w").write(txt)
print("exterior_geo: OBJ rewritten (%d vertices, %d groups)" % (nv, len(groups) + 2))
