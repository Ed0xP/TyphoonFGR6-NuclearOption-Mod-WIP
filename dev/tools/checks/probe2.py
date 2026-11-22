import sys, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];VN=[];F=[];FG=[];FNI=[];FL=[];g=None
for li,l in enumerate(open(sys.argv[1], errors='ignore')):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('vn '): VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f '):
        c=[t.split('/') for t in l.split()[1:]]
        for j in range(1,len(c)-1):
            F.append((int(c[0][0])-1,int(c[j][0])-1,int(c[j+1][0])-1)); FG.append(g); FNI.append(int(c[0][2])-1); FL.append(li)
V=np.array(V); VN=np.array(VN); Fa=np.array(F)
GN=np.cross(V[Fa[:,1]]-V[Fa[:,0]],V[Fa[:,2]]-V[Fa[:,0]]); AR=np.linalg.norm(GN,axis=1)/2; GN/=np.maximum(AR*2,1e-12)[:,None]
f0=[i for i,n in enumerate(FG) if n=='fuselage']; W=1 if (GN[f0]*VN[[FNI[i] for i in f0]]).sum()>=0 else -1
GN*=W
tree=BVHTree.FromPolygons([Vector(v) for v in V],F)
top=sys.argv[2]
idx=[i for i,n in enumerate(FG) if n==top]
big=sorted(idx,key=lambda i:-AR[i])[:1]; n=GN[big[0]]
P=V[np.unique(Fa[idx])]
c=P.mean(0); u=np.cross(n,[0,0,1.0]); u/=np.linalg.norm(u); w=np.cross(n,u)
found={}
for a in np.linspace(-0.11,0.11,60):
    for b in np.linspace(-0.08,0.08,45):
        o=c+u*a+w*b+n*0.02
        h=tree.ray_cast(Vector(o),Vector(-n),0.05)
        if h[0] is None or FG[h[2]]!=top or GN[h[2]]@n<0.9: continue
        o2=h[0]-Vector(n)*1e-5; h2=None
        for _ in range(6):
            hh=tree.ray_cast(o2,Vector(-n),0.002)
            if hh[0] is None: break
            if GN[hh[2]]@n>0.2: h2=hh; break
            o2=hh[0]-Vector(n)*1e-5
        if h2 is None: continue
        gap=(np.array(h[0])-np.array(h2[0]))@n
        k=(FG[h2[2]],FL[h2[2]])
        found.setdefault(k,[]).append((gap,GN[h2[2]]@n))
for k,v in sorted(found.items(),key=lambda kv:-len(kv[1]))[:14]:
    v=np.array(v); i=[j for j in range(len(FL)) if FL[j]==k[1]][0]
    print('%-18s line %d: %d samples, gap %.3f..%.3f mm, dot %.3f, face area %.1f cm2, box %s %s'%(k[0],k[1],len(v),v[:,0].min()*1000,v[:,0].max()*1000,v[:,1].mean(),sum(AR[j] for j in range(len(FL)) if FL[j]==k[1])*1e4,V[Fa[i]].min(0).round(3),V[Fa[i]].max(0).round(3)))
