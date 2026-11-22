import sys, re, numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
skip=re.compile(sys.argv[3]) if len(sys.argv)>3 else re.compile('^(cockpit_sillrail|cockpit_silllugs|cockpit_sillwedge|cockpit_cables|cockpit_sensor|canopy_frame|canopy_seal|canopy_framescrews|cockpit_detscrews|cockpit_seat|cockpit_head)')
V=[];F=[];FG=[];g=None
for l in open(sys.argv[1], errors='ignore'):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l[2:].strip()
    elif l.startswith('f ') and not skip.search(g):
        c=[int(t.split('/')[0])-1 for t in l.split()[1:]]
        for j in range(1,len(c)-1): F.append((c[0],c[j],c[j+1])); FG.append(g)
tree=BVHTree.FromPolygons([Vector(v) for v in V],F)
sx=float(sys.argv[2])
xs=np.arange(0.33,0.475,0.01)
print('x:      '+' '.join('%-8.2f'%x for x in xs))
for z in (5.7,5.9,6.1,6.2,6.3,6.4,6.5,6.6,6.7,6.8,6.9,6.95,7.0):
    row=[]
    for x in xs:
        h=tree.ray_cast(Vector((sx*x,1.05,z)),Vector((0,-1,0)),1.0)
        row.append('%s%.3f'%({'canopy':'G','cockpit_shellframe':'F','cockpit_shellaft':'A','cockpit_sillwall':'W','fuselage_cockpit':'S','cockpit_shelltub':'T','cockpit_consoles':'C','cockpit_skinliner':'L'}.get(FG[h[2]],FG[h[2]][8:10]),h[0].y) if h[0] else ' --   ')
    print('z %.2f  '%z+' '.join('%-8s'%r for r in row))
