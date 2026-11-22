import sys, re
sys.path.insert(0, '/work/t2/source/model')
import bpy, bmesh
import ckmodel as ck
import pedestal
src, out = sys.argv[-2:]
parts = []
def sw(bm_, name):
    parts.append(('bits_' + name, bm_)); return bm_
for nm, bm_, surf, uvm in pedestal.build(ck, sw):
    if nm == 'ped_body': parts.append(('body', bm_))
lines = []; nv = 0
keep = re.compile(r'cockpit_(nvepanel|stick\w*|seat|shelltub|pedal_\w|keys|panel|dwppanel|gearpanel|bezels)$')
P = []; g = None; on = False; remap = {}
def idx(i):
    global nv
    if i not in remap:
        nv += 1; remap[i] = nv; lines.append('v %s %s %s' % tuple(P[i - 1]))
    return remap[i]
for l in open(src, errors='ignore'):
    if l.startswith('v '):
        P.append(l.split()[1:4])
    elif l[:2] in ('o ', 'g '):
        g = l.split()[1]; on = bool(keep.search(g))
        if on: lines.append('o ' + g)
    elif l.startswith('f ') and on:
        ii = [idx(int(t.split('/')[0])) for t in l.split()[1:]]
        lines.append('f ' + ' '.join(map(str, ii)))
for col, bm_ in parts:
    lines.append('o newped_' + col)
    bmesh.ops.triangulate(bm_, faces=bm_.faces[:])
    bm_.verts.ensure_lookup_table()
    for v in bm_.verts: lines.append('v %.5f %.5f %.5f' % (v.co.x, v.co.z, v.co.y))
    for f in bm_.faces: lines.append('f ' + ' '.join(str(nv + v.index + 1) for v in f.verts))
    nv += len(bm_.verts)
open(out, 'w').write('\n'.join(lines) + '\n')
print('written', out, nv)
