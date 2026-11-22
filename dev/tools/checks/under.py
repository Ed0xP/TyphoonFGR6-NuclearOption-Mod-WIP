import sys, re, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
top=sys.argv[2]; rx=re.compile(sys.argv[3]); dmax=float(sys.argv[4])/1000 if len(sys.argv)>4 else 0.0015
V=[];VN=[];F={};g=None;FN={}
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('vn '): VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f '):
        c=[t.split('/') for t in l.split()[1:]]
        for j in range(1,len(c)-1):
            F.setdefault(g,[]).append((int(c[0][0])-1,int(c[j][0])-1,int(c[j+1][0])-1)); FN.setdefault(g,[]).append(int(c[0][2])-1)
V=np.array(V); VN=np.array(VN)
f0=np.array(F['fuselage']); gn=np.cross(V[f0[:,1]]-V[f0[:,0]],V[f0[:,2]]-V[f0[:,0]]); W=1 if (gn*VN[FN['fuselage']]).sum()>=0 else -1
T=np.array(F[top]); tn=np.cross(V[T[:,1]]-V[T[:,0]],V[T[:,2]]-V[T[:,0]])*W; ta=np.linalg.norm(tn,axis=1); tn/=np.maximum(ta,1e-12)[:,None]
tree=BVHTree.FromPolygons([Vector(v) for v in V],[tuple(t) for t in T])
lo=V[T].reshape(-1,3).min(0)-0.01; hi=V[T].reshape(-1,3).max(0)+0.01
print(top,'box',lo.round(3),hi.round(3))
for g in F:
    if not rx.search(g) or g==top: continue
    A=np.array(F[g]); P=V[A]; cen=P.mean(1)
    m=((cen>lo)&(cen<hi)).all(1)
    if not m.any(): continue
    A=A[m]; P=P[m]; cen=cen[m]
    n=np.cross(P[:,1]-P[:,0],P[:,2]-P[:,0])*W; ar=np.linalg.norm(n,axis=1)/2; n/=np.maximum(ar*2,1e-12)[:,None]
    hist={}; ex=[]
    for k in range(len(A)):
        offs=[]
        for q in (cen[k],P[k,0]*0.8+cen[k]*0.2,P[k,1]*0.8+cen[k]*0.2,P[k,2]*0.8+cen[k]*0.2):
            h=tree.find_nearest(Vector(q),dmax*2)
            if h[0] is None: offs=None; break
            j=h[2]
            if abs(tn[j]@n[k])<0.985: offs=None; break
            dq=q-np.array(h[0]); o_=dq@tn[j]
            if np.linalg.norm(dq-tn[j]*o_)>0.0003: offs=None; break
            offs.append(o_)
        if offs is None or max(abs(o) for o in offs)>dmax: continue
        b=round(float(np.mean(offs))*1000*4)/4
        hist[b]=hist.get(b,0)+ar[k]*1e4; ex.append(cen[k])
    if hist:
        ex=np.array(ex)
        print('  %-22s %s cm2 by offset mm; box %s %s'%(g,{k:round(v,1) for k,v in sorted(hist.items())},ex.min(0).round(3),ex.max(0).round(3)))
