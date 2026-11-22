import sys
sys.path.insert(0, '/work/t2/source/model')
import bpy, bmesh
import ckmodel as ck
import cockpit_hotas as h
class D(dict):
    def __missing__(self, k): return (0.5, 0.5)
out = sys.argv[-1]
parts = []
def _sw(items, SW, name, group_parts):
    for col, bm_ in items: parts.append((col or 'own', bm_))
h._sw = _sw
mv, fx = h.build_throttle((0, 0, 0), D())
for nm, bm_, surf, uvm in mv + fx: parts.append((surf, bm_))
lines = []; nv = 0; by = {}
for col, bm_ in parts: by.setdefault(col, []).append(bm_)
for col, bms in by.items():
    lines.append('o thr_' + col)
    for bm_ in bms:
        bmesh.ops.triangulate(bm_, faces=bm_.faces[:])
        bm_.verts.ensure_lookup_table()
        for v in bm_.verts: lines.append('v %.5f %.5f %.5f' % (v.co.x, v.co.z, v.co.y))
        for f in bm_.faces: lines.append('f ' + ' '.join(str(nv + v.index + 1) for v in f.verts))
        nv += len(bm_.verts)
open(out, 'w').write('\n'.join(lines) + '\n')
print('written', out, nv, 'vertices', {c: sum(len(b.faces) for b in bs) for c, bs in by.items()}, len(h.THR_LABELS), 'labels')
