import sys, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];VN=[];F=[];FG=[];FNI=[];g=None
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('vn '): VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and not g.startswith(('canopy','gear_','cockpit')):
        c=[t.split('/') for t in l.split()[1:]]; ids=[int(t[0])-1 for t in c]; ni=[int(t[2])-1 if len(t)>2 and t[2] else -1 for t in c]
        for j in range(1,len(ids)-1): F.append((ids[0],ids[j],ids[j+1])); FNI.append(ni[0]); FG.append(g)
V=np.array(V);VN=np.array(VN);F=np.array(F);FNI=np.array(FNI)
GN=np.cross(V[F[:,1]]-V[F[:,0]],V[F[:,2]]-V[F[:,0]]); GN/=np.maximum(np.linalg.norm(GN,axis=1),1e-12)[:,None]
fu=np.array([n=='fuselage' for n in FG])&(FNI>=0)
GN*=1 if (GN[fu]*VN[FNI[fu]]).sum()>=0 else -1
tree=BVHTree.FromPolygons([Vector(v) for v in V],[tuple(int(i) for i in f) for f in F])
b=[float(x) for x in (sys.argv[2] if len(sys.argv)>2 else '-1.2,1.2,-0.6,0.8,0.025').split(',')]
D=np.array(eval(sys.argv[3])) if len(sys.argv)>3 else np.array([0,0,1.0]); D=D/np.linalg.norm(D)
cnt={}
for y in np.arange(b[3],b[2]-1e-9,-b[4]):
    row=''
    for x in np.arange(b[0],b[1]+1e-9,b[4]/2):
        o=Vector(np.array([x,y,-3.6])-D*4.0); d=Vector(D); first=None; ch=' '
        for _ in range(40):
            h=tree.ray_cast(o,d,200.0)
            if h[0] is None:
                if first is not None: ch='X'; cnt[first]=cnt.get(first,0)+1
                break
            i=h[2]
            if GN[i]@D<0: ch='#' if first is None else 'o'; break
            if first is None: first=FG[i]
            o=h[0]+d*1e-4
        row+=ch
    print(row)
print(sorted(cnt.items(), key=lambda kv:-kv[1])[:8])
