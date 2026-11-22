import sys, numpy as np
obj=sys.argv[1]
V=[];G={};cur=None
for l in open(obj):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): cur=l.split()[1]
    elif l.startswith('f ') and cur and (cur.startswith('cockpit_') or cur=='canopy_interior'):
        ix=[int(c.split('/')[0])-1 for c in l.split()[1:]]
        for k in range(1,len(ix)-1): G.setdefault(cur,[]).append((ix[0],ix[k],ix[k+1]))
V=np.array(V)
def cast(o,d,groups):
    res=[]
    for g in groups:
        T=np.array(G[g]); A,B,C=V[T[:,0]],V[T[:,1]],V[T[:,2]]
        e1,e2=B-A,C-A; h=np.cross(d,e2); det=(e1*h).sum(1); ok=np.abs(det)>1e-12
        f=1/np.where(ok,det,1); s=o-A; u=f*(s*h).sum(1); q=np.cross(s,e1); v=f*(q@d); t=f*(e2*q).sum(1)
        m=ok&(u>=0)&(v>=0)&(u+v<=1)&(t>0.001)
        for tt in t[m]: res.append((round(float(tt),4),g.replace('cockpit_','')))
    res.sort(); return res[:4]
gs=[g for g in G if g not in ('cockpit_labels',)]
d=np.array([0,0,-1.0])
for side in (1,-1):
    print('side',side,'(ray from z=6.60 going aft; value = z of hit)')
    for x in (0.29,0.33,0.36,0.40,0.44):
        for y in (0.56,0.62,0.68,0.74):
            r=cast(np.array([side*x,y,6.60]),d,gs)
            print('  x %.2f y %.2f: '%(side*x,y)+', '.join('%.4f %s'%(6.60-t,g) for t,g in r))
