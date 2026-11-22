import sys, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];VN=[];F=[];FG=[];FN=[];g=None
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('vn '): VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f '):
        c=[t.split('/') for t in l.split()[1:]]
        for j in range(1,len(c)-1):
            F.append((int(c[0][0])-1,int(c[j][0])-1,int(c[j+1][0])-1)); FG.append(g); FN.append(int(c[0][2])-1)
V=np.array(V); VN=np.array(VN)
tree=BVHTree.FromPolygons([Vector(v) for v in V],F)
fa=np.array(F); gn=np.cross(V[fa[:,1]]-V[fa[:,0]],V[fa[:,2]]-V[fa[:,0]])
f0=[i for i,gname in enumerate(FG) if gname=='fuselage']
W=1 if (gn[f0]*VN[[FN[i] for i in f0]]).sum()>=0 else -1
C=np.array([0,0.93,7.085]); N=np.array([0,-0.152,0.988]); N/=np.linalg.norm(N); U=np.cross(N,[1,0,0]); U/=np.linalg.norm(U); U=U if U[1]>0 else -U
for k in range(2,len(sys.argv),2):
    o=np.array([float(x) for x in sys.argv[k].split(',')]); t=np.array([float(x) for x in sys.argv[k+1].split(',')]); d=(t-o)/np.linalg.norm(t-o)
    print('ray',o,'->',t)
    p=Vector(o)
    for _ in range(40):
        h=tree.ray_cast(p,Vector(d),3.0)
        if h[0] is None: break
        i=h[2]; q=np.array(h[0]); dd=q-C
        print('   %-22s (%.4f %.4f %.4f) %s   th %.1f rho %.4f s %+.4f'%(FG[i],q[0],q[1],q[2],'FRONT' if (gn[i]*W)@d<0 else 'back ',np.degrees(np.arctan2(dd[0],dd@U)),np.hypot(dd[0],dd@U),dd@N))
        if FG[i]=="cockpit_arch":
            for vv in fa[i]:
                dd=V[vv]-C; print('        v (%.4f %.4f %.4f) th %.2f rho %.4f s %+.4f  vn %s'%(V[vv][0],V[vv][1],V[vv][2],np.degrees(np.arctan2(dd[0],dd@U)),np.hypot(dd[0],dd@U),dd@N, 'n/a'))
        p=h[0]+Vector(d)*2e-4
