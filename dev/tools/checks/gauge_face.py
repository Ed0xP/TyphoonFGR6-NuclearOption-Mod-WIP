import sys, numpy as np, math
obj=sys.argv[1]
V=[];G={};cur=None
for l in open(obj):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): cur=l.split()[1]
    elif l.startswith('f ') and cur in ('cockpit_panel','cockpit_controls','canopy_interior','cockpit_shellframe','cockpit_shelldeck','cockpit_shellaft'):
        G.setdefault(cur,[]).append([int(c.split('/')[0]) for c in l.split()[1:]])
V=np.array(V)
unit=lambda v: v/np.linalg.norm(v)
eye=np.array([0,1.16,6.5]); tgt=np.array([0.362,0.790,7.300]); d=unit(tgt-eye)
PT=[]
for f in G['cockpit_panel']:
    p=V[[c-1 for c in f]]
    for k in range(1,len(p)-1): PT.append((p[0],p[k],p[k+1]))
hit=None
for a,b,c in PT:
    e1,e2=b-a,c-a; h=np.cross(d,e2); det=e1@h
    if abs(det)<1e-12: continue
    s0=eye-a; uu=(s0@h)/det; q0=np.cross(s0,e1); vv=(d@q0)/det; tt=(e2@q0)/det
    if uu>=0 and vv>=0 and uu+vv<=1 and tt>0.1 and (hit is None or tt<hit[0]): hit=(tt,eye+d*tt,unit(np.cross(e1,e2)))
C0,gn=hit[1],hit[2]
if gn@(eye-C0)<0: gn=-gn
up=np.array([0,1.0,0]); upp=unit(up-gn*(up@gn)); rp=np.cross(gn,upp)
print('C0',np.round(C0,4),'gn',np.round(gn,3),'upp',np.round(upp,3),'rp',np.round(rp,3))
pts=[]
area=0
for a,b,c in PT:
    n=np.cross(b-a,c-a); ar=np.linalg.norm(n)/2
    if ar<1e-9: continue
    n=unit(n)
    if abs(n@gn)>0.995 and abs(((a+b+c)/3-C0)@gn)<0.0015:
        for p in (a,b,c): pts.append(((p-C0)@rp*1000,(p-C0)@upp*1000))
        area+=ar
pts=np.array(pts)
print('coplanar verts',len(pts),'area cm2 %.1f'%(area*1e4))
print('rp range %.1f..%.1f mm, upp range %.1f..%.1f mm'%(pts[:,0].min(),pts[:,0].max(),pts[:,1].min(),pts[:,1].max()))
u=np.unique(np.round(pts,1),axis=0)
print(u)
key={};par={}
def kid(i): return key.setdefault(tuple(np.round(V[i-1],4)),len(key))
def find(a):
    while par.setdefault(a,a)!=a:
        par[a]=par[par[a]]; a=par[a]
    return a
F=G['cockpit_controls']
for f in F:
    ks=[kid(c) for c in f]
    for a in ks[1:]: par[find(a)]=find(ks[0])
comp={}
for f in F: comp.setdefault(find(kid(f[0])),set()).update(c-1 for c in f)
for vs in comp.values():
    P=V[sorted(vs)]; c=P.mean(0)
    a,b,w=(c-C0)@rp*1000,(c-C0)@upp*1000,(c-C0)@gn*1000
    if abs(a)<80 and abs(b)<130 and abs(w)<40:
        print('controls comp at rp %.1f up %.1f w %.1f  size %.1f x %.1f x %.1f  nv %d'%(a,b,w,np.ptp((P-C0)@rp)*1000,np.ptp((P-C0)@upp)*1000,np.ptp((P-C0)@gn)*1000,len(P)))
