import math
import os
import sys

import numpy as np

ST = sys.argv[1]
path = os.path.join(ST, "typhoon.obj")
MINE = ("cockpit_arch", "cockpit_archchannel", "cockpit_archstuds", "cockpit_archliner")
DROP = MINE + ("cockpit_archcover", "cockpit_archbolts", "cockpit_mirror")
CUT = ("cockpit_shellframe", "cockpit_panel", "cockpit_controls", "cockpit_shellrest", "cockpit_frame", "cockpit_skinliner")
TH_END = float(os.environ.get("ARCH_END", "101"))
TH_CUT = float(os.environ.get("ARCH_CUT", "101"))
D = float(os.environ.get("ARCH_DEPTH", "0.022"))

src = open(path).read().split("\n")
V = np.array([[float(x) for x in l.split()[1:4]] for l in src if l.startswith("v ")])
VN = np.array([[float(x) for x in l.split()[1:4]] for l in src if l.startswith("vn ")])
nvt = sum(1 for l in src if l.startswith("vt "))

C = np.array([0.0, 0.93, 7.085])
N = np.array([0.0, -0.152, 0.988]); N /= np.linalg.norm(N)
X = np.array([1.0, 0.0, 0.0])
U = np.cross(N, X); U /= np.linalg.norm(U); U = U if U[1] > 0 else -U


def cyl(P):
    d = P - C
    return np.degrees(np.arctan2(d @ X, d @ U)), np.hypot(d @ X, d @ U), d @ N


th_v, rho_v, s_v = cyl(V)
ZONE = (np.abs(th_v) <= TH_CUT) & (rho_v > 0.335) & (rho_v < 0.47) & (s_v > -0.095) & (s_v < 0.092)

lines, g, skip, ncut = [], None, False, {}
F = {}
for l in src:
    if l[:2] in ("o ", "g "):
        g = l.split()[1]
        skip = g in DROP
        if skip:
            continue
    if skip and l.startswith(("f ", "usemtl ")):
        continue
    if l.startswith("f "):
        idx = [int(t.split("/")[0]) - 1 for t in l.split()[1:]]
        if g in CUT and ZONE[idx].all():
            ncut[g] = ncut.get(g, 0) + 1
            continue
        if g in ("fuselage_cockpit", "canopy", "fuselage"):
            c = [t.split("/") for t in l.split()[1:]]
            F.setdefault(g, []).append([(int(c[k][0]) - 1, int(c[k][2]) - 1) for k in range(3)])
    lines.append(l)
f0 = np.array(F["fuselage"])
gn = np.cross(V[f0[:, 1, 0]] - V[f0[:, 0, 0]], V[f0[:, 2, 0]] - V[f0[:, 0, 0]])
WIND = 1 if (gn * VN[f0[:, 0, 1]]).sum() >= 0 else -1

glass = V[sorted({i for f in F["canopy"] for i, _ in f})]
band = sorted({i for f in F["fuselage_cockpit"] for i, _ in f})
aft, fwd, mid, row2 = {}, {}, {}, {}
for i in band:
    t, r, s = th_v[i], rho_v[i], s_v[i]
    if V[i][0] < -1e-6 or not (0.37 < r < 0.47 and abs(s) < 0.09 and t < 104.0):
        continue
    if np.linalg.norm(glass - V[i], axis=1).min() > 0.0008:
        mid[round(float(t), 2)] = V[i].copy()
    else:
        (aft if s < 0 else fwd)[round(float(t), 2)] = V[i].copy()
_gt, _gr, _gs = cyl(glass)
for k in np.nonzero((glass[:, 0] > -1e-6) & (_gs < -0.15) & (_gs > -0.21) & (_gr > 0.38) & (_gr < 0.48) & (_gt < 112.0))[0]:
    row2[round(float(_gt[k]), 2)] = glass[k].copy()


def edge(d):
    t = np.array(sorted(d))
    P = np.array([d[k] for k in sorted(d)])
    P[0, 0] = 0.0
    t = np.concatenate([-t[:0:-1], t])
    P = np.concatenate([P[:0:-1] * [-1, 1, 1], P])
    return t, P


TA, PA = edge(aft)
TF, PF = edge(fwd)
TM, PM = edge(mid)
TG, PG = edge(row2)
assert len(TA) > 20 and len(TF) > 20, (len(TA), len(TF))
assert np.diff(TA).max() < 9.5 and np.diff(TF).max() < 9.5, "a corner of the skin's band was not found: %s %s" % (np.round(TA, 1), np.round(TF, 1))


def on(T, P, t):
    k = int(np.clip(np.searchsorted(T, t) - 1, 0, len(T) - 2))
    f = (t - T[k]) / (T[k + 1] - T[k])
    return P[k] + (P[k + 1] - P[k]) * f


TH = sorted(set(np.round(np.arange(-TH_END, TH_END + 1e-6, 1.5), 3)) | {float(round(t, 3)) for t in TF if abs(t) < TH_END})
RIM_O, CH_W, CH_D, RC = 0.0055, 0.0100, 0.0038, 0.0045


def er(t):
    a = math.radians(t)
    return X * math.sin(a) + U * math.cos(a)


def polar(T, P):
    return T, np.hypot((P - C) @ X, (P - C) @ U), (P - C) @ N


RA_T, RA_R, RA_S = polar(TA, PA)
RF_T, RF_R, RF_S = polar(TF, PF)
RM_T, RM_R, RM_S = polar(TM, PM)
RG_T, RG_R, RG_S = polar(TG, PG)
LIP = float(os.environ.get("ARCH_LIP", "0.014"))
DEEP = float(os.environ.get("ARCH_DEEP", "0.036"))


def section(t):
    e = er(t)
    ra, sa = np.interp(t, RA_T, RA_R), np.interp(t, RA_T, RA_S)
    rm, sm = np.interp(t, RM_T, RM_R), np.interp(t, RM_T, RM_S)
    rf, sf = np.interp(t, RF_T, RF_R), np.interp(t, RF_T, RF_S)
    rg, sg = np.interp(t, RG_T, RG_R), np.interp(t, RG_T, RG_S)
    A = C + e * ra + N * sa
    Fp = on(TF, PF, t)
    at = lambda r, s_: C + e * r + N * s_
    pt = lambda dr, ds: A - e * dr + N * ds
    nm = lambda nr, ns: (e * nr + N * ns) / math.hypot(nr, ns)
    s0 = 0.001
    r1, r2 = RIM_O, RIM_O + CH_W
    kg = (rg - ra) / (sa - sg)
    lip_r = lambda w: ra + kg * w
    runs = [
        ("arch", [(at(ra - 0.0010, sa + s0), nm(1, kg)), (at(lip_r(LIP) - 0.0010, sa - LIP), nm(1, kg))]),
        ("arch", [(at(lip_r(LIP) - 0.0010, sa - LIP), nm(0, -1)), (at(lip_r(LIP) - 0.0024, sa - LIP), nm(0, -1))]),
        ("arch", [(at(lip_r(LIP) - 0.0024, sa - LIP), nm(-1, -kg)), (pt(0.0024, s0), nm(-1, -kg))]),
        ("arch", [(pt(0.0024, s0), nm(0, -1)), (pt(r1, s0), nm(0, -1))]),
        ("arch", [(pt(r1, s0), nm(-1, 0)), (pt(r1, s0 + CH_D), nm(-1, 0))]),
        ("channel", [(pt(r1, s0 + CH_D), nm(0, -1)), (pt(r2, s0 + CH_D), nm(0, -1))]),
        ("arch", [(pt(r2, s0 + CH_D), nm(1, 0)), (pt(r2, s0), nm(1, 0))]),
    ]
    run = [(pt(r2, s0), nm(0, -1)), (pt(D - RC, s0), nm(0, -1))]
    for k in range(1, 5):
        a = math.radians(90 * k / 5)
        run.append((pt(D - RC + RC * math.sin(a), s0 + RC - RC * math.cos(a)), nm(-math.sin(a), -math.cos(a))))
    run += [(pt(D, s0 + RC), nm(-1, 0)), (pt(D, s0 + DEEP), nm(-1, 0))]
    runs.append(("arch", run))

    def skin_r(s_):
        return float(np.interp(s_, [sa, sm, sf], [ra, rm, rf]))
    sd = sa + s0 + DEEP
    runs.append(("liner", [(pt(D, s0 + DEEP), nm(0, 1)), (at(skin_r(sd) - 0.0035, sd), nm(0, 1))]))
    smm = min(max(sm, sd + 0.004), sf - 0.006)
    ln = [at(skin_r(sd) - 0.0035, sd), at(skin_r(smm) - 0.0035, smm), at(rf - 0.0035, sf - 0.002)]
    lnn = []
    for k, p_ in enumerate(ln):
        v = ln[min(k + 1, 2)] - ln[max(k - 1, 0)]
        vr, vs = v @ e, v @ N
        lnn.append((p_, nm(-vs, vr) if -vs < 0 else nm(vs, -vr)))
    runs.append(("liner", lnn))
    runs.append(("liner", [(ln[2], nm(0, 1)), (Fp - e * 0.0003, nm(0, 1))]))
    return runs


groups = {k: ([], [], [], []) for k in MINE}
secs = [section(t) for t in TH]
arc = [math.radians(t) * 0.42 for t in TH]
GROUP = {"arch": "cockpit_arch", "channel": "cockpit_archchannel", "liner": "cockpit_archliner"}
for r in range(len(secs[0])):
    P, Nn, UV, T = groups[GROUP[secs[0][r][0]]]
    b0 = len(P)
    n = len(secs[0][r][1])
    v0 = sum(np.linalg.norm(secs[0][q][1][-1][0] - secs[0][q][1][0][0]) for q in range(r))
    for i, sec in enumerate(secs):
        v = v0
        for j, (p, nn) in enumerate(sec[r][1]):
            if j:
                v += np.linalg.norm(p - sec[r][1][j - 1][0])
            P.append(p); Nn.append(nn); UV.append((arc[i] * 3.0, v * 3.0))
    for i in range(len(secs) - 1):
        for j in range(n - 1):
            a, b, c, d = b0 + i * n + j, b0 + (i + 1) * n + j, b0 + (i + 1) * n + j + 1, b0 + i * n + j + 1
            T += [(a, b, c), (a, c, d)]
P, Nn, UV, T = groups["cockpit_arch"]
for i, sgn in ((0, -1), (len(TH) - 1, 1)):
    a = math.radians(TH[i])
    en = (X * math.cos(a) - U * math.sin(a)) * sgn
    ring = [p for _, run in secs[i] for (p, _) in run]
    cen = sum(ring) / len(ring)
    b0 = len(P)
    P.append(cen); Nn.append(en); UV.append((0.5, 0.5))
    for q in ring:
        P.append(q); Nn.append(en); UV.append((0.5 + (q - cen) @ er(TH[i]) * 3, 0.5 + (q - cen) @ N * 3))
    for j in range(len(ring)):
        T.append((b0, b0 + 1 + j, b0 + 1 + (j + 1) % len(ring)))

P, Nn, UV, T = groups["cockpit_archstuds"]
STEP = float(os.environ.get("ARCH_STUD_STEP", "5.5"))
nst = int(math.floor((TH_END - 4.0) / STEP))
for k in range(-nst, nst + 1):
    t = (k + 0.5) * STEP if os.environ.get("ARCH_STUD_HALF") else k * STEP
    e = er(t)
    A = C + e * np.interp(t, RA_T, RA_R) + N * np.interp(t, RA_T, RA_S)
    c0 = A - e * (RIM_O + CH_W / 2) + N * (0.001 + CH_D)
    n = -N
    a = math.radians(t)
    e1 = X * math.cos(a) - U * math.sin(a)
    SEG, R, H = 8, 0.0030, CH_D + 0.0010
    b0 = len(P)
    P.append(c0 + n * H); Nn.append(n); UV.append((0.5, 0.5))
    for q in range(SEG):
        w = 2 * math.pi * q / SEG
        P.append(c0 + n * H + (e1 * math.cos(w) + e * math.sin(w)) * R * 0.85); Nn.append(n); UV.append((0.5, 0.5))
    for q in range(SEG):
        w = 2 * math.pi * q / SEG
        d = e1 * math.cos(w) + e * math.sin(w)
        P.append(c0 + n * H + d * R * 0.85); Nn.append(d); UV.append((0.5, 0.5))
        P.append(c0 + d * R); Nn.append(d); UV.append((0.5, 0.5))
    for q in range(SEG):
        q2 = (q + 1) % SEG
        T.append((b0, b0 + 1 + q, b0 + 1 + q2))
        a_, b_, c_, d_ = b0 + 1 + SEG + 2 * q, b0 + 1 + SEG + 2 * q2, b0 + 2 + SEG + 2 * q2, b0 + 2 + SEG + 2 * q
        T += [(a_, b_, c_), (a_, c_, d_)]

MTL = {"cockpit_arch": os.environ.get("ARCH_MTL", "ckrail"), "cockpit_archchannel": "ckmetaldark", "cockpit_archstuds": "ckscrew", "cockpit_archliner": "ckbezel"}
tail, tail_f = [], []
nv, nvn = len(V), len(VN)
ntri = 0
for name, (P, Nn, UV, T) in groups.items():
    P, Nn = np.array(P), np.array(Nn)
    fl = ["o " + name, "usemtl " + MTL[name]]
    for p, n, uv in zip(P, Nn, UV):
        tail.append("v %.5f %.5f %.5f" % tuple(p)); tail.append("vn %.4f %.4f %.4f" % tuple(n)); tail.append("vt %.4f %.4f" % tuple(uv))
    for (a, b, c) in T:
        fn = np.cross(P[b] - P[a], P[c] - P[a])
        if np.linalg.norm(fn) < 1e-14:
            continue
        if fn @ (Nn[a] + Nn[b] + Nn[c]) * WIND < 0:
            b, c = c, b
        fl.append("f " + " ".join("%d/%d/%d" % (nv + k + 1, nvt + k + 1, nvn + k + 1) for k in (a, b, c)))
        ntri += 1
    nv += len(P); nvt += len(P); nvn += len(P)
    tail_f += fl
while lines and lines[-1] == "":
    lines.pop()
open(path, "w").write("\n".join(lines + tail + tail_f) + "\n")
mp = os.path.join(ST, "typhoon_materials.txt")
rows = [r for r in open(mp).read().rstrip("\n").split("\n") if not r.startswith(("ckarch ", "ckmirror "))]
open(mp, "w").write("\n".join(rows) + "\n")
mirror_png = os.path.join(ST, "ckmirror.png")
if os.path.exists(mirror_png):
    os.remove(mirror_png)
top = on(TA, PA, 0.0)
print("arch_slim: old arch removed %s; hoop to %.0f deg, flange %.0f mm, skin band %.0f mm deep at the top, %d studs, %d triangles" % (
    ncut, TH_END, D * 1000, np.linalg.norm(on(TF, PF, 0.0) - top) * 1000, 2 * nst + 1, ntri))
