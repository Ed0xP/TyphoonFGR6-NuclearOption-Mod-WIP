import sys, collections
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
V=[];g=None;F=[];S=collections.defaultdict(set)
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g:
        ids=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        if g=='canopy':
            for j in range(1,len(ids)-1): F.append((ids[0],ids[j],ids[j+1]))
        elif g.startswith('cockpit') or g.startswith('canopy_'):
            S[g].update(ids)
t=BVHTree.FromPolygons([Vector(v) for v in V],F)
cy=[V[i] for f in F for i in f]
print('canopy glass: y max %.3f, z %.3f..%.3f'%(max(p[1] for p in cy), min(p[2] for p in cy), max(p[2] for p in cy)))
for g,ids in sorted(S.items()):
    worst=None; n=0; top=max(V[i][1] for i in ids)
    if top<1.15: continue
    for i in ids:
        p=Vector(V[i])
        if p.y<1.10: continue
        h=t.ray_cast(p,Vector((0,1,0)),3.0)
        loc,nrm,idx,d=t.find_nearest(p)
        if h[0] is None:
            n+=1
            if worst is None or d>worst[0]: worst=(d,tuple(round(x,3) for x in p))
    lo=min((t.find_nearest(Vector(V[i]))[3], tuple(round(x,3) for x in V[i])) for i in ids if V[i][1]>1.1)
    print('%-28s top y %.3f  outside the glass: %d verts%s   closest to glass %.1f mm at %s'%(g, top, n, (' worst %.1f mm at %s'%(worst[0]*1000,worst[1])) if worst else '', lo[0]*1000, lo[1]))
