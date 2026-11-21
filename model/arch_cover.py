import math
import os
import sys

import numpy as np

ST = sys.argv[1]
path = os.path.join(ST, "typhoon.obj")
MINE = ("cockpit_archcover", "cockpit_archbolts")
lines, skip = [], False
for l in open(path).read().split("\n"):
    if l[:2] in ("o ", "g "):
        skip = l.split()[1] in MINE
        if skip:
            continue
    if not (skip and l.startswith(("f ", "usemtl "))):
        lines.append(l)
V, VN, g, F, nvt = [], [], None, {}, 0
for l in lines:
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vn "):
        VN.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vt "):
        nvt += 1
    elif l[:2] in ("o ", "g "):
        g = l.split()[1]
    elif l.startswith("f ") and g in ("cockpit_shellframe", "canopy_frame", "fuselage"):
        c = [t.split("/") for t in l.split()[1:]]
        for j in range(1, len(c) - 1):
            F.setdefault(g, []).append([(int(c[k][0]) - 1, int(c[k][2]) - 1) for k in (0, j, j + 1)])
V, VN = np.array(V), np.array(VN)
f0 = np.array(F["fuselage"])
gn = np.cross(V[f0[:, 1, 0]] - V[f0[:, 0, 0]], V[f0[:, 2, 0]] - V[f0[:, 0, 0]])
WIND = 1 if (gn * VN[f0[:, 0, 1]]).sum() >= 0 else -1


def samples(name, zlo=6.97, zhi=7.22, ylo=0.93):
    T = np.array([[V[i] for i, _ in f] for f in F[name]])
    cen = T.mean(1)
    T = T[(cen[:, 2] > zlo) & (cen[:, 2] < zhi) & (cen[:, 1] > ylo)]
    out = [T.reshape(-1, 3)]
    for _ in range(3):
        a, b, c = T[:, 0], T[:, 1], T[:, 2]
        ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
        out += [ab, bc, ca]
        T = np.concatenate([np.stack([a, ab, ca], 1), np.stack([ab, b, bc], 1), np.stack([ca, bc, c], 1), np.stack([ab, bc, ca], 1)])
    return np.concatenate(out)


A = samples("cockpit_shellframe")
cen = A.mean(0)
N = np.linalg.svd(A - cen, full_matrices=False)[2][2]
N = N if N[2] > 0 else -N
C = np.array([0.0, 0.93, 0.0])
C[2] = cen[2] - N[1] * (C[1] - cen[1]) / N[2]
X = np.array([1.0, 0, 0])
U = np.cross(N, X); U /= np.linalg.norm(U); U = U if U[1] > 0 else -U


def cyl(P):
    d = P - C
    return np.degrees(np.arctan2(d @ X, d @ U)), np.hypot(d @ X, d @ U), d @ N


TH = np.arange(-86.0, 86.01, 2.0)


def envelope(P, lo_rho=True):
    th, rho, s = cyl(P)
    r_in, s_aft, s_fwd, r_out = [], [], [], []
    for t in TH:
        m = np.abs(th - t) < 3.0
        if m.sum() < 5:
            r_in.append(np.nan); s_aft.append(np.nan); s_fwd.append(np.nan); r_out.append(np.nan)
            continue
        r_in.append(rho[m].min()); r_out.append(rho[m].max()); s_aft.append(s[m].min())
        inner = m & (rho < rho[m].min() + 0.012)
        s_fwd.append(s[inner].max())
    return [np.array(v) for v in (r_in, r_out, s_aft, s_fwd)]


def fill(a):
    ok = ~np.isnan(a)
    return np.interp(TH, TH[ok], a[ok])


def smooth(a, lower=True, w=5):
    a = fill(a)
    pad = np.pad(a, w, mode="edge")
    ext = np.array([(pad[i:i + 2 * w + 1].min() if lower else pad[i:i + 2 * w + 1].max()) for i in range(len(a))])
    k = np.exp(-0.5 * (np.arange(-w, w + 1) / (w / 2.0)) ** 2); k /= k.sum()
    sm = np.convolve(np.pad(ext, w, mode="edge"), k, mode="valid")
    return np.minimum(sm, ext) if lower else np.maximum(sm, ext)


r_in, r_out, s_aft, s_fwd = envelope(A)
sym = lambda a, f: f(np.stack([a, a[::-1]]), 0)
RI = smooth(sym(fill(r_in), np.min)) - 0.0025
SA = smooth(sym(fill(s_aft), np.min)) - 0.0020
SF = smooth(sym(fill(s_fwd), np.max), lower=False) + 0.004
if "canopy_frame" in F:
    cr = envelope(samples("canopy_frame", zlo=6.90))[0]
    RO = smooth(sym(fill(cr), np.min)) - 0.0015
else:
    RO = smooth(sym(fill(r_out), np.max), lower=False)
RO = np.maximum(RO, RI + 0.03)
BEV = 0.011


def profile(i):
    ri, ro, sa, sf = RI[i], RO[i], SA[i], SF[i]
    p = [(ro, sa + 0.016, 1.0, 0.0), (ro, sa + 0.003, 1.0, 0.0),
         (ro - 0.003, sa, 0.0, -1.0), (ri + BEV, sa, 0.0, -1.0)]
    for k in range(1, 6):
        a = math.radians(90 * k / 6)
        p.append((ri + BEV - BEV * math.sin(a), sa + BEV - BEV * math.cos(a), -math.sin(a), -math.cos(a)))
    p += [(ri, sa + BEV, -1.0, 0.0), (ri, sf, -1.0, 0.0)]
    return p


def at(th, rho, s):
    t = math.radians(th)
    return C + X * (rho * math.sin(t)) + U * (rho * math.cos(t)) + N * s


def nrm(th, nr, ns):
    t = math.radians(th)
    n = X * (nr * math.sin(t)) + U * (nr * math.cos(t)) + N * ns
    return n / np.linalg.norm(n)


groups = {k: [] for k in MINE}
P, Nn, T = [], [], []
prof = [profile(i) for i in range(len(TH))]
NP = len(prof[0])
for i, th in enumerate(TH):
    for (rho, s, nr, ns) in prof[i]:
        P.append(at(th, rho, s)); Nn.append(nrm(th, nr, ns))
for i in range(len(TH) - 1):
    for j in range(NP - 1):
        a, b, c, d = i * NP + j, (i + 1) * NP + j, (i + 1) * NP + j + 1, i * NP + j + 1
        T += [(a, b, c), (a, c, d)]
for i, sgn in ((0, -1), (len(TH) - 1, 1)):
    t = math.radians(TH[i])
    en = (X * math.cos(t) - U * math.sin(t)) * sgn
    ring = [at(TH[i], rho, s) for (rho, s, _, _) in prof[i]]
    cen_ = at(TH[i], (RI[i] + RO[i]) / 2 + 0.01, SA[i] + 0.02)
    b0 = len(P)
    P.append(cen_); Nn.append(en)
    for q in ring:
        P.append(q); Nn.append(en)
    for j in range(NP - 1):
        T.append((b0, b0 + 1 + j, b0 + 2 + j))
groups["cockpit_archcover"] = (P, Nn, T)

BP, BN, BT = [], [], []
for th in (-84, -75, -66, -23, 23, 66, 75, 84):
    i = int(round((th + 86) / 2))
    rho = (RI[i] + BEV + RO[i]) / 2
    c0 = at(th, rho, SA[i]); n = nrm(th, 0, -1.0)
    t = math.radians(th)
    e1 = X * math.cos(t) - U * math.sin(t); e2 = X * math.sin(t) + U * math.cos(t)
    b0 = len(BP); SEG = 14; R = 0.0048; H = 0.0022
    BP.append(c0 + n * H); BN.append(n)
    for k in range(SEG):
        a = 2 * math.pi * k / SEG
        BP.append(c0 + n * H + (e1 * math.cos(a) + e2 * math.sin(a)) * R * 0.82); BN.append(n)
    for k in range(SEG):
        a = 2 * math.pi * k / SEG
        d = e1 * math.cos(a) + e2 * math.sin(a)
        BP.append(c0 + n * H + d * R * 0.82); BN.append(d)
        BP.append(c0 - n * 0.001 + d * R); BN.append(d)
    for k in range(SEG):
        k2 = (k + 1) % SEG
        BT.append((b0, b0 + 1 + k, b0 + 1 + k2))
        a_, b_, c_, d_ = b0 + 1 + SEG + 2 * k, b0 + 1 + SEG + 2 * k2, b0 + 2 + SEG + 2 * k2, b0 + 2 + SEG + 2 * k
        BT += [(a_, b_, c_), (a_, c_, d_)]
groups["cockpit_archbolts"] = (BP, BN, BT)

MTL = {"cockpit_archcover": "ckarch", "cockpit_archbolts": "ckbezel"}
tail, tail_f = [], []
nv, nvn = len(V), len(VN)
for name, (P, Nn, T) in groups.items():
    P, Nn = np.array(P), np.array(Nn)
    fl = ["o " + name, "usemtl " + MTL[name]]
    for p, n in zip(P, Nn):
        tail.append("v %.5f %.5f %.5f" % tuple(p)); tail.append("vn %.4f %.4f %.4f" % tuple(n)); tail.append("vt 0.5 0.5")
    for (a, b, c) in T:
        fn = np.cross(P[b] - P[a], P[c] - P[a])
        if fn @ (Nn[a] + Nn[b] + Nn[c]) * WIND < 0:
            b, c = c, b
        fl.append("f " + " ".join("%d/%d/%d" % (nv + k + 1, nvt + k + 1, nvn + k + 1) for k in (a, b, c)))
    nv += len(P); nvt += len(P); nvn += len(P)
    tail_f += fl
while lines and lines[-1] == "":
    lines.pop()
open(path, "w").write("\n".join(lines + tail + tail_f) + "\n")
mp = os.path.join(ST, "typhoon_materials.txt")
txt = open(mp).read().rstrip("\n")
rows = [r for r in txt.split("\n") if not r.startswith("ckarch ")]
rows.append("ckarch color=%s smooth=0.40 metal=0.15" % os.environ.get("ARCH_COL", "#4A4D4E"))
open(mp, "w").write("\n".join(rows) + "\n")
print("arch_cover: axis %s, inner radius %.3f (top) .. %.3f (feet), aft face %.3f .. %.3f, width %.0f .. %.0f mm, %d triangles" % (
    N.round(3), RI[len(TH) // 2], RI[0], SA[len(TH) // 2], SA[0], (RO - RI)[len(TH) // 2] * 1000, (RO - RI)[0] * 1000, len(groups["cockpit_archcover"][2])))
