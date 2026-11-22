import sys, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];g=None;F=[];N=[]
for l in open(sys.argv[1]):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('o '): g=l[2:].strip()
    elif l.startswith('f ') and g and g.startswith(('cockpit','canopy_interior')) and g not in ('cockpit_labels',):
        ids=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        for j in range(1,len(ids)-1): F.append((ids[0],ids[j],ids[j+1])); N.append(g)
t=BVHTree.FromPolygons([Vector(v) for v in V],F)
def col(o,d,n=4,far=0.5):
    out=[];o=Vector(o);d=Vector(d).normalized()
    for _ in range(n):
        h=t.ray_cast(o,d,far)
        if h[0] is None: break
        out.append((N[h[2]].replace('cockpit_',''), tuple(round(c,4) for c in h[0])))
        o=h[0]+d*1e-5
    return out
if __name__=='__main__':
    for spec in sys.argv[2:]:
        o,d=spec.split(':'); o=[float(a) for a in o.split(',')]; d=[float(a) for a in d.split(',')]
        print(spec, col(o,d))
