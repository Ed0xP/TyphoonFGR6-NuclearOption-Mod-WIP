import sys, numpy as np
path=sys.argv[1]; lo=np.array([float(x) for x in sys.argv[2].split(',')]); hi=np.array([float(x) for x in sys.argv[3].split(',')])
V=[];VT=[];G={};cur=None;M={}
mtl=None
for l in open(path):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('vt '): VT.append([float(x) for x in l.split()[1:3]])
    elif l[:2] in ('o ','g '): cur=l.split()[1]
    elif l.startswith('usemtl '): M[cur]=l.split()[1]
    elif l.startswith('f '):
        G.setdefault(cur,[]).append([tuple(int(a) if a else 0 for a in (c.split('/')+['',''])[:2]) for c in l.split()[1:4]])
V=np.array(V); VT=np.array(VT)
for g,fs in G.items():
    P=V[np.array([[c[0]-1 for c in f] for f in fs])]
    c=P.mean(1)
    m=((c>=lo)&(c<=hi)).all(1)
    if m.sum():
        n=np.cross(P[m][:,1]-P[m][:,0],P[m][:,2]-P[m][:,0]); a=np.linalg.norm(n,axis=1)/2
        nn=(n/np.maximum(np.linalg.norm(n,axis=1),1e-12)[:,None])
        print("%-22s %-10s %4d tris area %.4f m2  mean|ny| %.2f  y %.3f..%.3f x %.3f..%.3f"%(g,M.get(g,'?'),int(m.sum()),a.sum(),np.abs(nn[:,1]).mean(),c[m][:,1].min(),c[m][:,1].max(),c[m][:,0].min(),c[m][:,0].max()))
