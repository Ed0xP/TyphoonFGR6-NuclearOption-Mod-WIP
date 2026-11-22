import sys, math, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];VN=[];F=[];FG=[];FNI=[];g=None
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('vn '): VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f '):
        c=[t.split('/') for t in l.split()[1:]]; ids=[int(t[0])-1 for t in c]; ni=[int(t[2])-1 if len(t)>2 and t[2] else -1 for t in c]
        for j in range(1,len(ids)-1): F.append((ids[0],ids[j],ids[j+1])); FNI.append(ni[0]); FG.append(g)
V=np.array(V);VN=np.array(VN);F=np.array(F);FNI=np.array(FNI)
GN=np.cross(V[F[:,1]]-V[F[:,0]],V[F[:,2]]-V[F[:,0]]); GN/=np.maximum(np.linalg.norm(GN,axis=1),1e-12)[:,None]
fu=np.array([n=='fuselage' for n in FG])&(FNI>=0)
WIND=1 if (GN[fu]*VN[FNI[fu]]).sum()>=0 else -1
GN*=WIND
tree=BVHTree.FromPolygons([Vector(v) for v in V],[tuple(int(i) for i in f) for f in F])
CAM,TGT=(np.array([float(x) for x in s.split(',')]) for s in sys.argv[2:4]); FOV=float(sys.argv[4]); W,H=int(sys.argv[5]),int(sys.argv[6])
fw=TGT-CAM; fw/=np.linalg.norm(fw); rt=np.cross([0,1.0,0],fw); rt/=np.linalg.norm(rt); up=np.cross(fw,rt); th=math.tan(math.radians(FOV)/2)
for a in sys.argv[7:]:
    x,y=(float(t) for t in a.split(','))
    d=fw+rt*((x+0.5)/W*2-1)*th*(W/H)+up*(1-(y+0.5)/H*2)*th; d/=np.linalg.norm(d)
    o=Vector(CAM); print(a)
    for _ in range(12):
        h=tree.ray_cast(o,Vector(d),200.0)
        if h[0] is None: print('   -> nothing'); break
        i=h[2]; print('   %-22s at (%.3f, %.3f, %.3f) %s' % (FG[i],h[0].x,h[0].y,h[0].z,'DRAWN' if GN[i]@d<0 else 'back'))
        if GN[i]@d<0: break
        o=h[0]+Vector(d)*1e-4
