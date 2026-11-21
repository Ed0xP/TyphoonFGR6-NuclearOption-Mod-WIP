import os
import sys

import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ST = sys.argv[1]
path = os.path.join(ST, "typhoon.obj")
RULES = [(top, ("cockpit_controls", "cockpit_consoles")) for top in ("cockpit_nvepanel", "cockpit_dwppanel", "cockpit_gearpanel", "cockpit_conl", "cockpit_conr")]
LO, HI, SINK, LAT, PAR, COVER = -0.0009, 0.00016, 0.0014, 0.0003, 0.985, 0.45
REMOVE = ("cockpit_controls",)

lines = open(path).read().split("\n")
V, VN, vline = [], [], []
faces = {}
g = None
for li, l in enumerate(lines):
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]]); vline.append(li)
    elif l.startswith("vn "):
        VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ("o ", "g "):
        g = l.split()[1]
    elif l.startswith("f "):
        c = [t.split("/") for t in l.split()[1:]]
        faces.setdefault(g, []).append((li, [int(t[0]) - 1 for t in c], int(c[0][2]) - 1 if len(c[0]) > 2 and c[0][2] else -1))
V, VN = np.array(V), np.array(VN)
f0 = faces["fuselage"]
s_ = 0.0
for li, ids, ni in f0[:2000]:
    s_ += np.cross(V[ids[1]] - V[ids[0]], V[ids[2]] - V[ids[0]]) @ VN[ni]
WIND = 1 if s_ >= 0 else -1

drop, moved, report = set(), {}, []
for top, unders in RULES:
    if top not in faces:
        continue
    tris = []
    for li, ids, ni in faces[top]:
        for k in range(1, len(ids) - 1):
            tris.append((ids[0], ids[k], ids[k + 1]))
    T = np.array(tris)
    tn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]) * WIND
    tn /= np.maximum(np.linalg.norm(tn, axis=1), 1e-12)[:, None]
    tree = BVHTree.FromPolygons([Vector(v) for v in V], tris)
    lo, hi = V[T].reshape(-1, 3).min(0) - 0.004, V[T].reshape(-1, 3).max(0) + 0.004

    def under(q, n=None):
        h = tree.find_nearest(Vector(q), 0.003)
        if h[0] is None:
            return None
        j = h[2]
        dq = q - np.array(h[0])
        o = float(dq @ tn[j])
        if np.linalg.norm(dq - tn[j] * o) > LAT or (n is not None and tn[j] @ n < PAR):
            return None
        return o, tn[j]
    nd, ns, area = 0, 0, 0.0
    for ug in unders:
        for li, ids, ni in faces.get(ug, []):
            if li in drop:
                continue
            P = V[ids]
            cen = P.mean(0)
            if (cen < lo).any() or (cen > hi).any():
                continue
            n = np.cross(P[1] - P[0], P[2] - P[0]) * WIND
            a2 = np.linalg.norm(n)
            if a2 < 1e-14:
                continue
            n /= a2
            res = []
            for i_ in range(6):
                for j_ in range(6 - i_):
                    wa, wb = (i_ + 0.4) / 6.2, (j_ + 0.4) / 6.2
                    res.append(under(P[0] * (1 - wa - wb) + P[1] * wa + P[2] * wb, n))
            hit = [r for r in res if r is not None and LO <= r[0] <= HI]
            if len(hit) >= COVER * len(res) and ug in REMOVE:
                k_ = [i_ for i_, r in enumerate(res) if r is not None and LO <= r[0] <= HI][0]
                npl = hit[0][1]
                i_, j_ = [(a_, b_) for a_ in range(6) for b_ in range(6 - a_)][k_]
                wa, wb = (i_ + 0.4) / 6.2, (j_ + 0.4) / 6.2
                qp = P[0] * (1 - wa - wb) + P[1] * wa + P[2] * wb - npl * hit[0][0]
                for vi in ids:
                    if vi not in moved:
                        moved[vi] = V[vi] - npl * (float((V[vi] - qp) @ npl) + SINK)
                nd += 1; area += a2 / 2
                continue
            if not hit:
                continue
            for vi in ids:
                r = under(V[vi], n)
                if r is not None and LO <= r[0] <= HI and vi not in moved:
                    moved[vi] = V[vi] - r[1] * (r[0] + SINK)
                    ns += 1
    report.append("%s: %d faces under it sunk whole (%.1f cm2), %d corners of others sunk" % (top.replace("cockpit_", ""), nd, area * 1e4, ns))

for vi, p in moved.items():
    lines[vline[vi]] = "v %.5f %.5f %.5f" % tuple(p)
out = [l for li, l in enumerate(lines) if li not in drop]
open(path, "w").write("\n".join(out))
print("declash: " + "; ".join(report))
