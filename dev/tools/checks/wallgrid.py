import sys, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];F=[];FG=[];g=None
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f '):
        c=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        for j in range(1,len(c)-1): F.append((c[0],c[j],c[j+1])); FG.append(g)
tree=BVHTree.FromPolygons([Vector(v) for v in V],F)
sx=float(sys.argv[2]); xs=float(sys.argv[3])
print('y:      '+' '.join('%-9.3f'%y for y in np.arange(0.44,0.64,0.02)))
for z in np.arange(6.30,6.95,0.04):
    row=[]
    for y in np.arange(0.44,0.64,0.02):
        h=tree.ray_cast(Vector((sx*xs,y,z)),Vector((sx,0,0)),0.3)
        row.append('%s%.3f'%(FG[h[2]].replace('cockpit_','')[:4],abs(h[0].x)) if h[0] else '  --    ')
    print('z %.2f  '%z+' '.join('%-9s'%r for r in row))
