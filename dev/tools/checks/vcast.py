import sys, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];F=[];FG=[];g=None
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f '):
        ids=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        for j in range(1,len(ids)-1): F.append((ids[0],ids[j],ids[j+1])); FG.append(g)
tree=BVHTree.FromPolygons([Vector(v) for v in V],F)
for a in sys.argv[2:]:
    x,z=(float(t) for t in a.split(','))
    o=Vector((x,3.0,z)); d=Vector((0,-1,0)); s=[]
    for _ in range(14):
        h=tree.ray_cast(o,d,6.0)
        if h[0] is None: break
        s.append('%s %.3f'%(FG[h[2]][:14],h[0].y)); o=h[0]+d*1e-4
    print(a,' | '.join(s))
