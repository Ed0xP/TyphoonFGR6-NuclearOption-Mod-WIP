import sys, math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];g=None;F=[];N=[]
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g and g.startswith(('cockpit','canopy_i')):
        ids=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        for j in range(1,len(ids)-1): F.append((ids[0],ids[j],ids[j+1])); N.append(g)
t=BVHTree.FromPolygons([Vector(v) for v in V],F)
e=Vector([float(x) for x in sys.argv[2].split(',')]); tg=Vector([float(x) for x in sys.argv[3].split(',')])
fov=math.radians(float(sys.argv[4])); w=float(sys.argv[5]); h=float(sys.argv[6])
fw=(tg-e).normalized(); up=Vector((0,1,0)); r=up.cross(fw).normalized(); cu=fw.cross(r).normalized()
th=math.tan(fov/2)
for a in sys.argv[7:]:
    px,py=[float(x) for x in a.split(',')]
    d=(fw+r*((px/w*2-1)*th)+cu*((1-py/h*2)*th*h/w)).normalized()
    hit=t.ray_cast(e,d,5)
    print(a,'->',N[hit[2]] if hit[0] else None, tuple(round(x,3) for x in hit[0]) if hit[0] else '', 'n', tuple(round(x,2) for x in hit[1]) if hit[0] else '')
