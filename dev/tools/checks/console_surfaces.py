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
def cast_down(x,z,groups,ytop=0.75):
    best=[]
    for g in groups:
        T=np.array(G[g]); A,B,C=V[T[:,0]],V[T[:,1]],V[T[:,2]]
        d0=(B[:,2]-C[:,2])*(A[:,0]-C[:,0])+(C[:,0]-B[:,0])*(A[:,2]-C[:,2])
        ok=np.abs(d0)>1e-12
        with np.errstate(all='ignore'):
            l0=((B[:,2]-C[:,2])*(x-C[:,0])+(C[:,0]-B[:,0])*(z-C[:,2]))/d0
            l1=((C[:,2]-A[:,2])*(x-C[:,0])+(A[:,0]-C[:,0])*(z-C[:,2]))/d0
        l2=1-l0-l1
        m=ok&(l0>=0)&(l1>=0)&(l2>=0)
        y=l0*A[:,1]+l1*B[:,1]+l2*C[:,1]
        for yy in y[m]:
            if yy<ytop: best.append((round(float(yy),4),g))
    best.sort(reverse=True)
    return best[:4]
others=[g for g in G if g not in ('cockpit_blankplates','cockpit_detscrews','cockpit_labels')]
for side in (1,-1):
    print('side',side)
    for x in (0.30,0.36,0.42,0.48,0.52):
        for z in (6.34,6.40,6.45,6.50,6.55,6.60,6.70):
            bp=cast_down(side*x,z,['cockpit_blankplates'])
            ot=cast_down(side*x,z,others)
            print('  x %.2f z %.2f  blank top %s | others: %s'%(side*x,z, bp[0][0] if bp else None, ', '.join('%.4f %s'%(a,b.replace('cockpit_','')) for a,b in ot[:3])))
