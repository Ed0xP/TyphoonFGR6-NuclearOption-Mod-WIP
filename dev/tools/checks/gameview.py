import colorsys
import math
import re
import sys
import zlib

import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image

a = sys.argv[1:]
ST, OUT = a[0], a[1]
CAM, TGT = (np.array([float(x) for x in s.split(",")]) for s in a[2:4])
FOV = float(a[4])
W = int(a[5]) if len(a) > 5 else 640
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
        g = l.split()[1]
    elif l.startswith("f ") and g and g != "cockpit_labels" and not (SKIP and SKIP.search(g)):
        c = [t.split("/") for t in l.split()[1:]]
        ids = [int(t[0]) - 1 for t in c]
        ni = [int(t[2]) - 1 if len(t) > 2 and t[2] else -1 for t in c]
        for j in range(1, len(ids) - 1):
            F.append((ids[0], ids[j], ids[j + 1]))
            FNI.append((ni[0], ni[j], ni[j + 1]))
            FG.append(g)
V, VN, F, FNI = np.array(V), np.array(VN), np.array(F), np.array(FNI)
P0, P1, P2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
GN = np.cross(P1 - P0, P2 - P0)
GN /= np.maximum(np.linalg.norm(GN, axis=1), 1e-12)[:, None]
_fu = np.array([n == "fuselage" for n in FG])
_ok = _fu & (FNI >= 0).all(1)
WIND = 1 if (GN[_ok] * VN[FNI[_ok, 0]]).sum(1).sum() >= 0 else -1
GN *= WIND
tree = BVHTree.FromPolygons([Vector(v) for v in V], [tuple(int(i) for i in f) for f in F])
GLASS = np.array([n == "canopy" or n.endswith("glass") for n in FG])
names = sorted(set(FG))
gid = {n: i for i, n in enumerate(names)}
FGI = np.array([gid[n] for n in FG])


def colour(n):
    h = (zlib.crc32(n.encode()) % 1000) / 1000.0
    return np.array(colorsys.hsv_to_rgb(h, 0.55, 0.95))


COL = np.array([colour(n) for n in names])
fw = TGT - CAM
fw /= np.linalg.norm(fw)
rt = np.cross([0, 1.0, 0], fw)
rt /= np.linalg.norm(rt)
up = np.cross(fw, rt)
th = math.tan(math.radians(FOV) / 2)
img = np.zeros((H, W, 3))
seen, through, where, where2 = {}, {}, {}, {}
for y in range(H):
    for x in range(W):
        d = fw + rt * ((x + 0.5) / W * 2 - 1) * th * (W / H) + up * (1 - (y + 0.5) / H * 2) * th
        d /= np.linalg.norm(d)
        dv = Vector(d)
        o = Vector(CAM)
        back = None
        px = np.array([1.0, 0.0, 1.0])
        for _ in range(60):
            h = tree.ray_cast(o, dv, 200.0)
            if h[0] is None:
                break
            i = h[2]
            if not GLASS[i]:
                if GN[i] @ d < 0:
                    sh = 0.35 + 0.65 * abs(GN[i] @ d)
                    px = COL[FGI[i]] * sh
                    seen[FG[i]] = seen.get(FG[i], 0) + 1
                    if back is not None:
                        px = px * 0.45 + np.array([0.9, 0.0, 0.0]) * 0.55
                        k = (back, FG[i])
                        through[k] = through.get(k, 0) + 1
                        where2.setdefault(k, []).append(bpos)
                    back = "done"
                    break
                if back is None:
                    back = FG[i]
                    bpos = np.array(h[0])
            o = h[0] + dv * 2e-4
        if back is not None and back != "done":
            through[(back, "NOTHING")] = through.get((back, "NOTHING"), 0) + 1
            where.setdefault(back, []).append(bpos)
        img[y, x] = px
Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(OUT)
print("gameview:", OUT, W, "x", H)
print(" seen:", ", ".join("%s %d" % kv for kv in sorted(seen.items(), key=lambda kv: -kv[1])[:24]))
for (b, f), n in sorted(through.items(), key=lambda kv: -kv[1])[:30]:
    pp = np.array(where2[(b, f)]) if (b, f) in where2 else None
    print("  through the back of %-22s -> %-24s %6d px%s" % (b, f, n, "" if pp is None else "   at x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f" % (
        pp[:, 0].min(), pp[:, 0].max(), pp[:, 1].min(), pp[:, 1].max(), pp[:, 2].min(), pp[:, 2].max())))
for b, pp in where.items():
    pp = np.array(pp)
    print("  back of %s, nothing behind: %d px, x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f; e.g. %s" % (
        b, len(pp), pp[:, 0].min(), pp[:, 0].max(), pp[:, 1].min(), pp[:, 1].max(), pp[:, 2].min(), pp[:, 2].max(), pp[::max(len(pp) // 4, 1)].round(4).tolist()))
