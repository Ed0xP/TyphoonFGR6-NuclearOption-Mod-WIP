import re
import sys

import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ST = sys.argv[1]
GAP = float(sys.argv[2]) / 1000 if len(sys.argv) > 2 else 0.001
SKIP = re.compile(r"cockpit_(labels|.*glass|sbyneedle|hudglass|mirror)|canopy$")
V, F, FG = [], [], []
g = None
for l in open(ST + "/typhoon.obj"):
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ("o ", "g "):
        g = l.split()[1]
    elif l.startswith("f ") and g and (g.startswith("cockpit_") or g == "canopy_interior") and not SKIP.search(g):
        ids = [int(t.split("/")[0]) - 1 for t in l.split()[1:]]
        for j in range(1, len(ids) - 1):
            F.append((ids[0], ids[j], ids[j + 1]))
            FG.append(g)
V = np.array(V)
F = np.array(F)
key = np.round(V[F.reshape(-1)] / 2e-5).astype(np.int64)
_, inv = np.unique(key, axis=0, return_inverse=True)
W = inv.reshape(-1, 3)
par = np.arange(W.max() + 1)


def find(a):
    while par[a] != a:
        par[a] = par[par[a]]
        a = par[a]
    return a


for a, b, c in W:
    ra, rb, rc = find(a), find(b), find(c)
    par[rb] = ra
    par[find(rc)] = ra
comp = np.array([find(a) for a in W[:, 0]])
_, comp = np.unique(comp, return_inverse=True)
gid = {n: i for i, n in enumerate(sorted(set(FG)))}
comp = comp * len(gid) + np.array([gid[n] for n in FG])
_, comp = np.unique(comp, return_inverse=True)
tree = BVHTree.FromPolygons([Vector(v) for v in V], [tuple(int(i) for i in f) for f in F])
SHELL = ("canopy_interior", "cockpit_shellframe", "cockpit_shelldeck", "cockpit_shellaft", "cockpit_shelltub", "cockpit_consoles")
MOVING = re.compile(r"cockpit_(stick|throttle|pedal_|gearlever|sw_|canopyhandle)")
nc = comp.max() + 1
grp_of = [None] * nc
faces_of = [[] for _ in range(nc)]
for i, c in enumerate(comp):
    faces_of[c].append(i)
    grp_of[c] = FG[i]
adj = [set() for _ in range(nc)]
near = [9.0] * nc
for c in range(nc):
    fi = np.array(faces_of[c])
    vi = np.unique(F[fi].reshape(-1))
    sel = vi if len(vi) <= 240 else vi[:: len(vi) // 240 + 1]
    for i in sel:
        for pos, nrm, idx, d in tree.find_nearest_range(Vector(V[i]), 0.02):
            o = comp[idx]
            if o != c:
                near[c] = min(near[c], d)
                if d <= GAP:
                    adj[c].add(o)
                    adj[o].add(c)
    if len(fi) <= 4000:
        sub = BVHTree.FromPolygons([Vector(v) for v in V], [tuple(int(i) for i in f) for f in F[fi]])
        for a_, b_ in sub.overlap(tree):
            o = comp[b_]
            if o != c:
                adj[c].add(o)
                adj[o].add(c)
                near[c] = 0.0
held = [grp_of[c] in SHELL or bool(MOVING.search(grp_of[c])) for c in range(nc)]
todo = [c for c in range(nc) if held[c]]
while todo:
    c = todo.pop()
    for o in adj[c]:
        if not held[o]:
            held[o] = True
            todo.append(o)
seen = set()
out = []
for c in range(nc):
    if held[c] or c in seen:
        continue
    cl, todo = [], [c]
    seen.add(c)
    while todo:
        k = todo.pop()
        cl.append(k)
        for o in adj[k]:
            if o not in seen and not held[o]:
                seen.add(o)
                todo.append(o)
    fi = np.concatenate([faces_of[k] for k in cl])
    P = V[np.unique(F[fi].reshape(-1))]
    gap = min((near[k] for k in cl if near[k] > GAP), default=9.0)
    out.append((",".join(sorted({grp_of[k].replace("cockpit_", "") for k in cl})), P.mean(0), P.max(0) - P.min(0), gap, len(cl), len(fi)))
out.sort(key=lambda r: (r[0], r[1][2]))
for grp, cen, size, d, n, nt in out:
    print("%-28s at (%7.3f %6.3f %6.3f) size %5.1f x %5.1f x %5.1f mm  gap %s  (%d pieces, %d tris)" % (
        grp, *cen, *(size * 1000), "%.1f mm" % (d * 1000) if d < 9 else "> 20 mm", n, nt))
print(len(out), "loose clusters")
