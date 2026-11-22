import sys, math, numpy as np
S=float(sys.argv[3]); PIT=math.radians(float(sys.argv[4])) if len(sys.argv)>4 else 0.0
L=open(sys.argv[1], errors='ignore').read().split('\n')
g=None; use={}
for l in L:
    if l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g in ('petals_L','petals_R','nozcollar_L','nozcollar_R'):
        for t in l.split()[1:]: use.setdefault(g,set()).add(int(t.split('/')[0]))
vidx=[k for k,l in enumerate(L) if l.startswith('v ')]
P=np.array([[float(q) for q in L[k].split()[1:4]] for k in vidx])
for g,ids in use.items():
    ids=np.array(sorted(ids))-1
    A=np.array([0.4855 if g.endswith('R') else -0.4855,-0.0392,-3.55]); ax=np.array([0,0,-1.0])
    B=P[ids]-A
    if g.startswith('petals'):
        along=B@ax; rad=B-np.outer(along,ax); t=np.maximum(0,along); t=t/t.max()
        r=np.linalg.norm(rad,axis=1); rM=np.sort(r[t>0])[int((t>0).sum()*0.98)]
        t=np.where(r>rM*1.3,0,t)
        B=B+rad*((S-1)*t)[:,None]
    c,s=math.cos(PIT),math.sin(PIT)
    y=B[:,1]*c-B[:,2]*s; z=B[:,1]*s+B[:,2]*c; B[:,1]=y; B[:,2]=z
    P[ids]=B+A
for k,p in zip(vidx,P): L[k]='v %.5f %.5f %.5f'%tuple(p)
open(sys.argv[2],'w').write('\n'.join(L)); print('posed', {g:len(i) for g,i in use.items()})
