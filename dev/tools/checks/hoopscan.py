import numpy as np,sys
V=[];G={};cur=None
for l in open(sys.argv[1]):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): cur=l[2:].strip()
    elif l.startswith('f '):
        G.setdefault(cur,[]).append([int(t.split('/')[0])-1 for t in l.split()[1:4]])
V=np.array(V)
C=np.array([0,0.93,7.085]); N=np.array([0,-0.152,0.988]); N/=np.linalg.norm(N); U=np.cross(N,[1,0,0]); U/=np.linalg.norm(U); U=U if U[1]>0 else -U
d=V-C; x=d[:,0]; y=d@U; s=d@N; th=np.degrees(np.arctan2(x,y)); rho=np.hypot(x,y)
inz=(np.abs(th)<float(sys.argv[2]) if len(sys.argv)>2 else 100)&(rho>0.33)&(rho<0.47)&(s>-0.10)&(s<0.095)
for g,f in G.items():
    f=np.array(f); m=inz[f].all(1)
    if m.sum():
        idx=np.unique(f[m]);
        print('%-26s tris %6d  th %6.1f..%5.1f rho %.3f..%.3f s %+.3f..%+.3f'%(g,m.sum(),np.abs(th[idx]).min(),np.abs(th[idx]).max(),rho[idx].min(),rho[idx].max(),s[idx].min(),s[idx].max()))
for g in sys.argv[3:]:
    f=np.array(G[g]); m=inz[f].all(1); f=f[m]
    print(g)
    cth=np.abs(th[f]).mean(1)
    for t0 in range(0,100,10):
        mm=(cth>=t0)&(cth<t0+10)
        if mm.sum():
            idx=np.unique(f[mm]); print('   th %2d-%3d tris %5d rho %.3f..%.3f s %+.3f..%+.3f  y %.3f..%.3f z %.3f..%.3f'%(t0,t0+10,mm.sum(),rho[idx].min(),rho[idx].max(),s[idx].min(),s[idx].max(),V[idx,1].min(),V[idx,1].max(),V[idx,2].min(),V[idx,2].max()))
