import os
import sys

import numpy as np
from scipy.spatial import cKDTree

ST = sys.argv[1]
SKINS = ("wing_L", "wing_R", "fuselage", "fuselage_root_L", "fuselage_root_R", "fuselage_nose", "fuselage_baylip", "fin", "pod_L", "pod_R",
         "nozzle_L", "nozzle_R")
HALF, HALF_SHARP, DEPTH, NEAR = 0.003, 0.0012, 0.0006, 0.003
path = os.path.join(ST, "typhoon.obj")
lines = open(path).read().split("\n")
out, skip = [], False
for l in lines:
    if l[:2] in ("o ", "g "):
        skip = l.split()[1].startswith("seam_")
        if skip:
            continue
    if not (skip and l.startswith(("f ", "usemtl "))):
        out.append(l)
lines = out
V, VT, VN, g, faces, mtl = [], [], [], None, {}, {}
for l in lines:
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vt "):
        VT.append([float(x) for x in l.split()[1:3]])
    elif l.startswith("vn "):
        VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ("o ", "g "):
        g = l.split()[1]
    elif l.startswith("usemtl ") and g in SKINS:
        mtl[g] = l.split()[1]
    elif l.startswith("f ") and g in SKINS:
        c = [t.split("/") for t in l.split()[1:]]
        for j in range(1, len(c) - 1):
            faces.setdefault(g, []).append([(int(c[k][0]) - 1, int(c[k][1]) - 1, int(c[k][2]) - 1) for k in (0, j, j + 1)])
V, VT, VN = np.array(V), np.array(VT), np.array(VN)
f0 = np.array(faces["fuselage"])
gn = np.cross(V[f0[:, 1, 0]] - V[f0[:, 0, 0]], V[f0[:, 2, 0]] - V[f0[:, 0, 0]])
WIND = 1 if (gn * VN[f0[:, 0, 2]]).sum() >= 0 else -1
key, edges = {}, {}
for gname, fl in faces.items():
    for tri in fl:
        ks = [key.setdefault(tuple(np.round(V[v], 4)), len(key)) for v, _, _ in tri]
        n = np.cross(V[tri[1][0]] - V[tri[0][0]], V[tri[2][0]] - V[tri[0][0]]) * WIND
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if ks[a] != ks[b]:
                edges.setdefault((min(ks[a], ks[b]), max(ks[a], ks[b])), []).append((gname, tri[a], tri[b], n / ln))
open_ = [v[0] for v in edges.values() if len(v) == 1]
sp, se = [], []
for e, (gname, a, b, n) in enumerate(open_):
    p0, p1 = V[a[0]], V[b[0]]
    k = max(2, int(np.linalg.norm(p1 - p0) / 0.004) + 1)
    for t in np.linspace(0, 1, k):
        sp.append(p0 + (p1 - p0) * t)
        se.append(e)
sp, se = np.array(sp), np.array(se)
tree = cKDTree(sp)
tail, tail_f = [], {}
nv, nvt, nvn = len(V), len(VT), len(VN)
n_seam = 0
for e, (gname, a, b, n) in enumerate(open_):
    p0, p1 = V[a[0]], V[b[0]]
    L = np.linalg.norm(p1 - p0)
    if L < 2e-4:
        continue
    mate = None
    for t in (0.25, 0.5, 0.75):
        idx = [i for i in tree.query_ball_point(p0 + (p1 - p0) * t, NEAR) if se[i] != e]
        if idx:
            mate = open_[se[idx[0]]]
            break
    if mate is None:
        continue
    half = HALF if n @ mate[3] > 0.866 else HALF_SHARP
    n_seam += 1
    tdir = np.cross(n, (p1 - p0) / L)
    q = [p0 - tdir * half - n * DEPTH, p0 + tdir * half - n * DEPTH, p1 + tdir * half - n * DEPTH, p1 - tdir * half - n * DEPTH]
    uv = [VT[a[1]], VT[a[1]], VT[b[1]], VT[b[1]]]
    for tri in ((0, 1, 2), (0, 2, 3)):
        A, B, C = (q[i] for i in tri)
        order = tri if np.cross(B - A, C - A) @ n * WIND > 0 else (tri[0], tri[2], tri[1])
        ids = []
        for i in order:
            tail.append("v %.5f %.5f %.5f" % tuple(q[i]))
            tail.append("vt %.5f %.5f" % tuple(uv[i]))
            tail.append("vn %.4f %.4f %.4f" % tuple(n))
            nv += 1; nvt += 1; nvn += 1
            ids.append("%d/%d/%d" % (nv, nvt, nvn))
        tail_f.setdefault(gname, []).append("f " + " ".join(ids))
grp = []
for gname, fl in tail_f.items():
    grp += ["o seam_" + gname, "usemtl " + mtl.get(gname, "body")] + fl
open(path, "w").write("\n".join(lines + tail + grp) + "\n")
print("seam_backs: %d open edges on the skin, %d of them along a seam; strips: %s (winding %+d)" % (
    len(open_), n_seam, ", ".join("%s %d" % (k, len(v) // 2) for k, v in sorted(tail_f.items())), WIND))
