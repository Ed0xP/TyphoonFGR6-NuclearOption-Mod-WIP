import sys, math, collections
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
grp=sys.argv[2]; H=[float(x) for x in sys.argv[3].split(',')]; angs=[float(x) for x in sys.argv[4].split(',')]
V=[];g=None;F=[];N=[];T=[]
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and g and g.startswith(('cockpit','canopy_i')):
        ids=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        for j in range(1,len(ids)-1):
            if g==grp: T.append((ids[0],ids[j],ids[j+1]))
            elif g not in ('cockpit_labels',): F.append((ids[0],ids[j],ids[j+1])); N.append(g)
rest=BVHTree.FromPolygons([Vector(v) for v in V],F)
used=sorted({i for t in T for i in t}); idx={i:k for k,i in enumerate(used)}
TT=[tuple(idx[i] for i in t) for t in T]
print(grp, len(T), 'triangles; bounds y', min(V[i][1] for i in used), max(V[i][1] for i in used), 'z', min(V[i][2] for i in used), max(V[i][2] for i in used), 'x', min(V[i][0] for i in used), max(V[i][0] for i in used))
for a in angs:
    r=math.radians(a); c,s=math.cos(r),math.sin(r)
    P=[]
    for i in used:
        x,y,z=V[i]; y-=H[1]; z-=H[2]
        P.append(Vector((x, H[1]+y*c-z*s, H[2]+y*s+z*c)))
    tb=BVHTree.FromPolygons(P,TT)
    ov=tb.overlap(rest)
    hit=collections.defaultdict(list)
    for i,j in ov:
        tri=F[j]; ctr=[sum(V[k][d] for k in tri)/3 for d in range(3)]
        hit[N[j]].append(ctr)
    print('angle %+.0f:'%a, 'clear' if not hit else '')
    for gname,pts in sorted(hit.items()):
        mn=[min(p[d] for p in pts) for d in range(3)]; mx=[max(p[d] for p in pts) for d in range(3)]
        print('   %-26s %4d tris  x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f'%(gname,len(pts),mn[0],mx[0],mn[1],mx[1],mn[2],mx[2]))
