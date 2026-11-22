import sys, math, numpy as np
import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
V=[];g=None;F=[];PET=set()
for l in open(sys.argv[1]):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('o '): g=l[2:].strip()
    elif l.startswith('f ') and g:
        ids=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        if g in ('fuselage','nozzle_L','fuselage_root_L','fuselage_bay','fuselage_baylip'): F.append(ids)
        if g=='petals_L': PET.update(ids)
V=np.array(V); t=BVHTree.FromPolygons([Vector(v) for v in V],F)
P=V[sorted(PET)]; piv=np.array([-0.4855,-0.0392,-3.55])
ANG=float(sys.argv[2]) if len(sys.argv)>2 else 20
for name,axis in (('pitch+',(1,0,0)),('pitch-',(-1,0,0)),('yaw+',(0,1,0)),('yaw-',(0,-1,0))):
    R=np.array(Matrix.Rotation(math.radians(ANG),3,Vector(axis)))
    Q=(P-piv)@R.T+piv
    bad=0; worst=0
    for q in Q:
        if q[2]<-3.535: continue
        o=Vector((piv[0],piv[1],q[2])); d=Vector(q)-o; L=d.length
        if L<1e-6: continue
        dn=d.normalized(); far=o+dn*1.5
        h=t.ray_cast(far,-dn,1.5)
        if h[0] is None: continue
        skin=1.5-h[3]
        if L>skin+0.002:
            bad+=1; worst=max(worst,L-skin)
    print(name, 'vertices outside the fixed skin:', bad, 'worst %.3f m'%worst)
