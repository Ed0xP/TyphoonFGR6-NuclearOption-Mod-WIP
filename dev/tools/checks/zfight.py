import math
import re
import sys

import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

a = sys.argv[1:]
ST = a[0]
CAM, TGT = (np.array([float(x) for x in s.split(",")]) for s in a[1:3])
FOV = float(a[3])
W = int(a[4]) if len(a) > 4 else 480
GAP = float(a[5]) / 1000 if len(a) > 5 else 0.0006
SKIP = re.compile(a[6]) if len(a) > 6 else None
H = int(W * 9 / 16)
V, VN, F, FG, FNI = [], [], [], [], []
g = None
for l in open(ST + "/typhoon.obj"):
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vn "):
        VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ("o ", "g "):
        g = l[2:].strip()
    elif l.startswith("f ") and not (SKIP and SKIP.search(g)):
        c = [t.split("/") for t in l.split()[1:]]
        for j in range(1, len(c) - 1):
            F.append((int(c[0][0]) - 1, int(c[j][0]) - 1, int(c[j + 1][0]) - 1)); FG.append(g); FNI.append(int(c[0][2]) - 1)
V, VN, Fa = np.array(V), np.array(VN), np.array(F)
GN = np.cross(V[Fa[:, 1]] - V[Fa[:, 0]], V[Fa[:, 2]] - V[Fa[:, 0]])
GN /= np.maximum(np.linalg.norm(GN, axis=1), 1e-12)[:, None]
f0 = [i for i, n in enumerate(FG) if n == "fuselage"]
WIND = 1 if (GN[f0] * VN[[FNI[i] for i in f0]]).sum() >= 0 else -1
GN *= WIND
GLASS = np.array([n in ("canopy", "cockpit_hudglass", "cockpit_sbyglass") for n in FG])
tree = BVHTree.FromPolygons([Vector(v) for v in V], F)
fw = TGT - CAM; fw /= np.linalg.norm(fw)
rt = np.cross([0, 1, 0], fw); rt /= np.linalg.norm(rt)
up = np.cross(fw, rt)
th = math.tan(math.radians(FOV) / 2)
pairs = {}
for y in range(H):
    for x in range(W):
        d = fw + rt * ((x + 0.5) / W * 2 - 1) * th + up * (1 - (y + 0.5) / H * 2) * th * H / W
        d /= np.linalg.norm(d)
        dv, o = Vector(d), Vector(CAM)
        first = None
        for _ in range(40):
            h = tree.ray_cast(o, dv, 20.0)
            if h[0] is None:
                break
            i = h[2]
            if not GLASS[i] and GN[i] @ d < 0:
                if first is None:
                    first = (i, np.array(h[0]))
                else:
                    gap = abs((np.array(h[0]) - first[1]) @ GN[first[0]])
                    if gap < GAP and i != first[0] and GN[i] @ GN[first[0]] > 0.97:
                        k = tuple(sorted((FG[first[0]], FG[i])))
                        pairs.setdefault(k, []).append((gap, first[1]))
                    break
            o = h[0] + dv * 1e-5
for k, v in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
    gp = np.array([q[0] for q in v]); P = np.array([q[1] for q in v])
    print("%-24s / %-24s %6d px  gap min %.3f median %.3f mm   x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f" % (
        k[0], k[1], len(v), gp.min() * 1000, np.median(gp) * 1000, P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max(), P[:, 2].min(), P[:, 2].max()))
print("zfight: %d x %d rays, %d pairs of groups" % (W, H, len(pairs)))
