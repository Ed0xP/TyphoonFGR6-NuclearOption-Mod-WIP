import sys
import numpy as np
import bpy
from mathutils.bvhtree import BVHTree
from mathutils import Vector
ST = sys.argv[1]
V, names, F, cur = [], [], [], None
for l in open(ST + '/typhoon.obj'):
    if l.startswith('v '):
        V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ', 'g '):
        cur = l.split()[1]
    elif l.startswith('f ') and (cur.startswith('cockpit_') or cur == 'canopy_interior'):
        F.append([int(c.split('/')[0]) - 1 for c in l.split()[1:4]])
bvh = BVHTree.FromPolygons([Vector(v) for v in V], F)
eye = np.array([0, 1.16, 6.5])
for l in open(ST + '/typhoon_cockpit.txt'):
    t = l.split()
    if len(t) < 14 or t[0] != 'screen':
        continue
    q, proud = np.array([float(x) for x in t[2:14]]).reshape(4, 3), float(t[14]) if len(t) > 14 else 0.0025
    o = q.mean(0); u = q[1] - q[0]; wd = np.linalg.norm(u); u /= wd; v = q[0] - q[3]; ht = np.linalg.norm(v); v /= ht
    n = np.cross(u, v); n /= np.linalg.norm(n)
    if n @ (eye - o) < 0:
        n = -n
    out = []
    for a, b, lab in ((wd / 2 + 0.004, 0, 'R'), (-wd / 2 - 0.004, 0, 'L'), (0, ht / 2 + 0.004, 'T'), (0, -ht / 2 - 0.004, 'B')):
        p = o + u * a + v * b
        h = bvh.ray_cast(Vector(p + n * 0.06), Vector(-n), 0.12)
        out.append("%s %.1f" % (lab, ((np.array(h[0]) - p) @ n) * 1000) if h[0] else lab + " none")
    print("%-6s %.0f x %.0f mm, picture at %.1f mm, surround: %s" % (t[1], wd * 1000, ht * 1000, proud * 1000, ", ".join(out)))
