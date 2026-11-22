import numpy as np, pickle, itertools
G=pickle.load(open('geo.pkl','rb'))
C=np.concatenate([G[k][0] for k in G]); N=np.concatenate([G[k][1] for k in G]); A=np.concatenate([G[k][2] for k in G])
lab=np.concatenate([[k]*len(G[k][2]) for k in G])
con=(lab=='cockpit_consoles')&(N[:,1]>0.8)&(C[:,1]<0.56)&(C[:,2]<7.1)&(np.abs(C[:,0])>0.2)
def irr(L,r):
    E=np.zeros(len(A))
    for p in L:
        d=p-C; d2=(d*d).sum(1); dist=np.sqrt(d2)
        cos=np.clip((d*N).sum(1)/np.maximum(dist,1e-6),0,None)
        w=np.clip(1-(d2/r**2)**2,0,None)**2
        E+=cos*w/np.maximum(d2,1e-4)
    return E
def wq(v,a,q):
    o=np.argsort(v); c=np.cumsum(a[o])/a.sum(); return v[o][np.searchsorted(c,q)]
def score(L,r,verbose=False):
    E=irr(L,r); m=wq(E[con],A[con],0.5); E=E/m
    lo,hi=wq(E[con],A[con],0.1),wq(E[con],A[con],0.9)
    oth=~con
    spill=(E[oth]*A[oth]).sum()/A[con].sum(); p99=wq(E[oth],A[oth],0.99); mx=E[oth].max()
    if verbose:
        print('console p10 %.2f p90 %.2f  gain(median irr per unit I) %.1f'%(lo,hi,m))
        for k in G:
            mm=(lab==k)&oth
            print('  %-18s mean %.2f p90 %.2f p99 %.2f max %.1f'%(k,(E[mm]*A[mm]).sum()/A[mm].sum(),wq(E[mm],A[mm],.9),wq(E[mm],A[mm],.99),E[mm].max()))
    return (hi/lo)*0.5+spill*1.0+p99*0.3, lo,hi,spill,p99,m
def mk(x,y,z1,z2): return [np.array([s*x,y,z]) for s in (-1,1) for z in (z1,z2)]
if __name__=='__main__':
    print('CURRENT'); score([np.array(p) for p in [(-.27,.8,6.78),(.27,.8,6.78),(0,.93,7.10),(0,.66,6.98)]],0.55,True)
    best=[]
    for r in (0.35,0.45,0.55):
        for x in np.arange(0.2,0.75,0.05):
            for y in np.arange(0.6,1.05,0.05):
                for z1,z2 in ((6.6,6.95),(6.65,7.0),(6.55,6.9),(6.7,6.9)):
                    s=score(mk(x,y,z1,z2),r); best.append((s[0],r,x,y,z1,z2)+s[1:])
    best.sort()
    for b in best[:12]: print(np.round(b,2))
    b=best[0]; print('BEST'); score(mk(*b[2:6]),b[1],True)
