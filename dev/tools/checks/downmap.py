import sys, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];VN=[];F=[];FG=[];FNI=[];g=None
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('vn '): VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f '):
        c=[t.split('/') for t in l.split()[1:]]
        for j in range(1,len(c)-1):
            F.append((int(c[0][0])-1,int(c[j][0])-1,int(c[j+1][0])-1)); FG.append(g); FNI.append(int(c[0][2])-1)
V=np.array(V); VN=np.array(VN); Fa=np.array(F)
GN=np.cross(V[Fa[:,1]]-V[Fa[:,0]],V[Fa[:,2]]-V[Fa[:,0]])
f0=[i for i,n in enumerate(FG) if n=='fuselage']; W=1 if (GN[f0]*VN[[FNI[i] for i in f0]]).sum()>=0 else -1
GN*=W
tree=BVHTree.FromPolygons([Vector(v) for v in V],F)
x0,x1,nx=[float(t) for t in sys.argv[2].split(',')]; z0,z1,nz=[float(t) for t in sys.argv[3].split(',')]
ytop=float(sys.argv[4]) if len(sys.argv)>4 else 1.0
names={}
print('rows: z from %.3f to %.3f; cols: x from %.3f to %.3f'%(z0,z1,x0,x1))
for z in np.linspace(z0,z1,int(nz)):
    row=[]
    for x in np.linspace(x0,x1,int(nx)):
        o=Vector((x,ytop,z)); d=Vector((0,-1,0)); hit=None
        for _ in range(30):
            h=tree.ray_cast(o,d,3.0)
            if h[0] is None: break
            if GN[h[2]][1]>0 and FG[h[2]] not in ('canopy',): hit=h; break
            o=h[0]+d*1e-5
        if hit is None: row.append('   --    ')
        else:
            n=FG[hit[2]].replace('cockpit_',''); k=names.setdefault(n,chr(65+len(names)) if len(names)<26 else chr(71+len(names)))
            row.append('%s%.3f '%(k,hit[0].y))
    print('z %.3f '%z+' '.join(row))
print({v:k for k,v in names.items()})
