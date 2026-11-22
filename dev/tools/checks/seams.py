import sys, collections
import numpy as np
G=('wing_L','wing_R','fuselage','fuselage_root_L','fuselage_root_R','fuselage_nose','fuselage_baylip','fin','pod_L','pod_R')
V=[];g=None;F=[]
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append(tuple(float(x) for x in l.split()[1:4]))
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g in G:
        ids=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        for j in range(1,len(ids)-1): F.append((g,ids[0],ids[j],ids[j+1]))
key={}
def K(i):
    return key.setdefault(tuple(round(c,4) for c in V[i]), len(key))
E=collections.defaultdict(list)
for g,a,b,c in F:
    ka,kb,kc=K(a),K(b),K(c)
    for u,v,(i,j) in ((ka,kb,(a,b)),(kb,kc,(b,c)),(kc,ka,(c,a))):
        if u!=v: E[(min(u,v),max(u,v))].append((g,i,j))
open_=[(k,v[0]) for k,v in E.items() if len(v)==1]
print(len(F),'triangles,',len(E),'edges,',len(open_),'open')
cnt=collections.Counter(v[0] for k,v in open_)
print(cnt)
for g in ('wing_L','fuselage_root_L','fuselage'):
    pts=[( (V[i][0]+V[j][0])/2, (V[i][1]+V[j][1])/2, (V[i][2]+V[j][2])/2, ((V[i][0]-V[j][0])**2+(V[i][1]-V[j][1])**2+(V[i][2]-V[j][2])**2)**0.5) for k,(gg,i,j) in open_ if gg==g]
    pts=[p for p in pts if p[0]<0.2]
    h=collections.Counter((round(p[0]*5)/5, round(p[2]/1.0)*1.0) for p in pts)
    print(g, len(pts), 'open edges (x<0.2); by (x 0.2 m, z 1 m):', sorted(h.items())[:60])
np.save('/tmp/open_edges.npy', np.array([[*V[i],*V[j]] for k,(gg,i,j) in open_]))
import pickle; pickle.dump([gg for k,(gg,i,j) in open_], open('/tmp/open_groups.pkl','wb'))
