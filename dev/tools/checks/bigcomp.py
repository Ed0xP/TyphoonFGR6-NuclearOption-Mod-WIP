import sys, numpy as np
path=sys.argv[1]
V=[];G={};cur=None
for l in open(path):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): cur=l.split()[1]
    elif l.startswith('f '):
        G.setdefault(cur,[]).append([int(c.split('/')[0])-1 for c in l.split()[1:4]])
V=np.array(V)
for g in G:
    if not g.startswith('cockpit_'): continue
    F=np.array(G[g]); P=V[F]
    e=np.linalg.norm(P[:,1]-P[:,0],axis=1); e2=np.linalg.norm(P[:,2]-P[:,0],axis=1)
    big=(e>0.8)|(e2>0.8)
    lo,hi=V[F.ravel()].min(0),V[F.ravel()].max(0)
    if big.any() or (hi-lo).max()>3.0:
        print(g, len(F), "bbox", np.round(lo,2), np.round(hi,2), "long-edge tris", int(big.sum()))
