import sys, numpy as np
ST=sys.argv[1]
keys=[]
for l in open(ST+'/typhoon_keys.txt'):
    t=l.split()
    if t and t[0]=='key': keys.append((t[1],[float(x) for x in t[2:10]],' '.join(t[10:])))
VT=[];uv=set();g=None
for l in open(ST+'/typhoon.obj'):
    if l.startswith('vt '): VT.append((float(l.split()[1]),float(l.split()[2])))
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g=='cockpit_labels':
        for t in l.split()[1:]: uv.add(int(t.split('/')[1])-1)
U=np.array([VT[i] for i in uv]); E=0.00012
for flip in (False,True):
    P=U.copy()
    if flip: P[:,1]=1-P[:,1]
    ok=0; bad=[]
    for st,c,leg in keys:
        best=0
        for (u0,v0,u1,v1) in (c[:4],c[4:]):
            cs=[(u0,v0),(u1,v0),(u0,v1),(u1,v1)]
            n=sum(int(((abs(P[:,0]-a)<E)&(abs(P[:,1]-b)<E)).sum()) for a,b in cs)
            best=max(best,n)
        if best>=4: ok+=1
        else: bad.append((st,leg,best))
    print('v %s: %d of %d keys matched'%('flipped' if flip else 'as written',ok,len(keys)), bad[:6])
