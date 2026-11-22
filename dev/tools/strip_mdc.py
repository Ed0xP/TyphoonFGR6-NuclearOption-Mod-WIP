import sys
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
path = sys.argv[1]
L = open(path).read().split("\n")
V = []; grp = None; canopy = []; frame = []
for i, l in enumerate(L):
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("o "):
        grp = l[2:].strip()
    elif l.startswith("f "):
        idx = [int(t.split("/")[0]) - 1 for t in l.split()[1:]]
        if grp == "canopy": canopy.append(idx)
        elif grp == "cockpit_frame": frame.append((i, idx))
V = np.array(V)
bvh = BVHTree.FromPolygons([Vector(v) for v in V], canopy)
fv = np.array([f[1] for f in frame])
n = len(V)
rows = np.concatenate([fv[:, 0], fv[:, 1]]); cols = np.concatenate([fv[:, 1], fv[:, 2]])
nc, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n)), directed=False)
drop = set()
for c in np.unique(lab[fv[:, 0]]):
    sel = np.where(lab[fv[:, 0]] == c)[0]
    vs = np.unique(fv[sel].ravel())
    P = V[vs]
    ext = np.linalg.norm(P.max(0) - P.min(0))
    d = [bvh.find_nearest(Vector(p))[3] for p in P]
    if ext > 0.12 and max(d) < 0.008:
        drop.update(frame[k][0] for k in sel)
        print(f"drop component: {len(sel)} faces, extent {ext:.2f} m, max {max(d)*1000:.1f} mm from glass")
open(path, "w").write("\n".join(l for i, l in enumerate(L) if i not in drop))
print("removed", len(drop), "faces")
