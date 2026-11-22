import sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];g=None;F=[];N=[]
skip=('cockpit_pedal','cockpit_labels','cockpit_controls')
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g and g.startswith(('cockpit','canopy_i')) and not g.startswith(skip):
        ids=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        for j in range(1,len(ids)-1): F.append((ids[0],ids[j],ids[j+1])); N.append(g)
t=BVHTree.FromPolygons([Vector(v) for v in V],F)
for y in (0.30,0.36,0.42,0.48,0.54,0.60):
    row=[]
    for z in (7.36,7.41,7.46):
        o=Vector((0.17,y,z)); a=t.ray_cast(o,Vector((-1,0,0)),0.3); b=t.ray_cast(o,Vector((1,0,0)),0.3)
        row.append('z %.2f: in %.3f (%s) out %.3f (%s)'%(z, a[0].x if a[0] else -9, N[a[2]][8:] if a[0] else '-', b[0].x if b[0] else 9, N[b[2]][8:] if b[0] else '-'))
    print('y %.2f  '%y+' | '.join(row))
