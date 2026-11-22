import math
import sys

import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ST = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else None
V, VN, F, FG, FNI = [], [], [], [], []
g = None
for l in open(ST + "/typhoon.obj"):
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vn "):
        VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ("o ", "g "):
        g = l.split()[1]
    elif l.startswith("f ") and g and not g.startswith(("gear_", "bay_", "pod", "pylon", "cockpit_labels")):
        c = [t.split("/") for t in l.split()[1:]]
        ids = [int(t[0]) - 1 for t in c]
        ni = [int(t[2]) - 1 if len(t) > 2 and t[2] else -1 for t in c]
        for j in range(1, len(ids) - 1):
            F.append((ids[0], ids[j], ids[j + 1]))
            FNI.append((ni[0], ni[j], ni[j + 1]))
            FG.append(g)
V, VN = np.array(V), np.array(VN)
F = np.array(F)
P0, P1, P2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
GN = np.cross(P1 - P0, P2 - P0)
GN /= np.maximum(np.linalg.norm(GN, axis=1), 1e-12)[:, None]
FNI = np.array(FNI)
ok = (FNI >= 0).all(1)
avg = np.zeros_like(GN)
avg[ok] = VN[FNI[ok, 0]] + VN[FNI[ok, 1]] + VN[FNI[ok, 2]]
flip = (GN * avg).sum(1) < 0
GN[flip] *= -1
tree = BVHTree.FromPolygons([Vector(v) for v in V], [tuple(int(i) for i in f) for f in F])
GLASS = np.array([n in ("canopy",) or n.endswith("glass") for n in FG])
INT = np.array([n.startswith(("cockpit_", "canopy_")) for n in FG])
EYES = [np.array(e) for e in ((0.0, 1.16, 6.50), (0.10, 1.12, 6.56), (-0.10, 1.12, 6.56), (0.0, 1.05, 6.62), (0.0, 1.20, 6.45))]


def look(o, d):
    o = Vector(o)
    d = Vector(d)
    glass = False
    first_back = None
    for _ in range(40):
        h = tree.ray_cast(o, d, 60.0)
        if h[0] is None:
            return (2 if glass else 3), first_back, None
        i = h[2]
        if GLASS[i]:
            glass = True
        elif GN[i] @ np.array(d) < 0:
            if INT[i]:
                return 0, np.array(h[0]), FG[i]
            return (1 if glass else 3), (first_back if first_back is not None else np.array(h[0])), FG[i]
        elif not INT[i] and first_back is None:
            first_back = np.array(h[0])
        o = h[0] + d * 2e-4
    return 0, None, None


AZ = np.arange(-180, 180, 1.0)
EL = np.arange(-80, 81, 1.0)
img = np.zeros((len(EL), len(AZ), 3), np.uint8)
holes = []
for ei, E in enumerate(EYES):
    for a_i, az in enumerate(AZ):
        for e_i, el in enumerate(EL):
            ca = math.cos(math.radians(el))
            d = np.array([ca * math.sin(math.radians(az)), math.sin(math.radians(el)), ca * math.cos(math.radians(az))])
            k, p, gname = look(E, d)
            if ei == 0:
                img[len(EL) - 1 - e_i, a_i] = ((70, 70, 70), (60, 110, 60), (60, 90, 200), (255, 30, 30))[k]
            if k == 3 and p is not None:
                holes.append((ei, az, el, p, gname))
print("holes.py: %d of %d rays leave through the skin" % (len(holes), len(EYES) * len(AZ) * len(EL)))
cells = {}
for ei, az, el, p, gname in holes:
    cells.setdefault(tuple(np.floor(p / 0.10).astype(int)), []).append((ei, az, el, p, gname))
for key, hs in sorted(cells.items(), key=lambda kv: -len(kv[1])):
    P = np.array([h[3] for h in hs])
    c0 = [h for h in hs if h[0] == 0]
    print("  %4d rays  skin left at about (%6.2f %5.2f %5.2f) +- %.2f; from the eye point az %s el %s; beyond: %s" % (
        len(hs), *P.mean(0), float(np.abs(P - P.mean(0)).max()),
        ("%.0f..%.0f" % (min(h[1] for h in c0), max(h[1] for h in c0))) if c0 else "-",
        ("%.0f..%.0f" % (min(h[2] for h in c0), max(h[2] for h in c0))) if c0 else "-",
        sorted({str(h[4]) for h in hs})[:4]))
if OUT:
    from PIL import Image
    Image.fromarray(img).resize((len(AZ) * 3, len(EL) * 3), Image.NEAREST).save(OUT + "_holes.png")
