import sys, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];g=None;F=[];N=[]
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g and g.startswith(('cockpit','canopy_i')) and g not in ('cockpit_labels',):
        ids=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        for j in range(1,len(ids)-1): F.append((ids[0],ids[j],ids[j+1])); N.append(g)
t=BVHTree.FromPolygons([Vector(v) for v in V],F)
e=Vector([float(x) for x in sys.argv[2].split(',')])
for a in sys.argv[3:]:
    p=Vector([float(x) for x in a.split(',')]); d=(p-e).normalized(); h=t.ray_cast(e,d,5)
    print(a, '->', N[h[2]] if h[0] else None, tuple(round(x,3) for x in h[0]) if h[0] else '', 'n', tuple(round(x,2) for x in h[1]) if h[0] else '')
