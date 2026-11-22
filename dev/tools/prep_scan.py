import sys, math, numpy as np, bpy, bmesh
from mathutils import Vector, Matrix
GLB, OUTD = sys.argv[1], sys.argv[2]
PREV = sys.argv[3] if len(sys.argv) > 3 else None
CUT, YAW, H = -0.74, -95.0, 0.200
HC, YAW0 = 0.100, -105.0
AXY0 = 0.0039
AXY1 = AXY0 + 0.05 * HC
TEX = 2048
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=GLB)
ob = [o for o in sc.objects if o.type == 'MESH'][0]
for o in list(sc.objects):
    if o is not ob:
        bpy.data.objects.remove(o)
bpy.context.view_layer.objects.active = ob; ob.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = ob.data
bm = bmesh.new(); bm.from_mesh(me)
r = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, CUT), plane_no=(0, 0, 1), clear_inner=True)
edges = [e for e in r['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
bmesh.ops.holes_fill(bm, edges=bm.edges[:], sides=0)
bmesh.ops.triangulate(bm, faces=bm.faces[:])
ring = np.array([v.co[:] for v in bm.verts if abs(v.co.z - CUT) < 1e-4])
c0 = Vector((ring[:, 0].mean(), ring[:, 1].mean(), CUT)) if len(ring) else Vector((0, 0, CUT))
top = max(v.co.z for v in bm.verts)
s = H / (top - CUT)
M = Matrix.Scale(s, 4) @ Matrix.Rotation(math.radians(YAW), 4, 'Z') @ Matrix.Translation(-c0)
bmesh.ops.transform(bm, matrix=M, verts=bm.verts[:])
bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, HC), plane_no=(0, 0, 1), clear_inner=True)
bv = [v for v in bm.verts if abs(v.co.z - HC) < 1e-5]
csec = np.array([v.co[:2] for v in bv]).mean(0)
SHIFT = Vector((-csec[0], AXY1 - csec[1], 0.0))
bmesh.ops.translate(bm, vec=SHIFT, verts=bm.verts[:])
ang = np.array([math.atan2(v.co.y - AXY1, v.co.x) for v in bv])
od = np.argsort(ang)
bv = [bv[i] for i in od]; ang = ang[od]
rtop = np.array([math.hypot(v.co.x, v.co.y - AXY1) for v in bv])
RB = float(rtop.mean()) + 0.0004
print('grip cut at %.3f: %d points, section radius %.4f..%.4f, head moved %s' % (HC, len(bv), rtop.min(), rtop.max(), np.round(SHIFT[:2], 4)))
prev, Mv = bv, len(bv)
for z in list(np.arange(HC - 0.0025, 0.0005, -0.0025)) + [0.0]:
    w = min(max((HC - z) / 0.020, 0.0), 1.0); w = w * w * (3 - 2 * w)
    cy = AXY0 + (AXY1 - AXY0) * z / HC
    rc = 0.0225 + (RB - 0.0225) * min(max((z - 0.0180) / 0.0030, 0.0), 1.0)
    ring = [bm.verts.new((r * math.cos(t), cy + r * math.sin(t), z)) for t, r in zip(ang, rtop + (rc - rtop) * w)]
    for i in range(Mv):
        bm.faces.new((prev[i], prev[(i + 1) % Mv], ring[(i + 1) % Mv], ring[i]))
    prev = ring
cb = bm.verts.new((0.0, AXY0, 0.0))
for i in range(Mv):
    bm.faces.new((prev[(i + 1) % Mv], prev[i], cb))


def prism(cx, cy, z0, z1, hw, hh, rad, ch=0.0012):
    def outline(d):
        pts = []
        a_, b_, r_ = hw - d, hh - d, max(rad - d, 0.0006)
        for sx, sy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
            for k in range(5):
                t = math.radians(a0 + 90 * k / 4)
                pts.append((cx + sx * (a_ - r_) + r_ * math.cos(t), cy + sy * (b_ - r_) + r_ * math.sin(t)))
        out = []
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            n_ = max(int(math.hypot(q[0] - p[0], q[1] - p[1]) / 0.003), 1)
            out += [(p[0] + (q[0] - p[0]) * k / n_, p[1] + (q[1] - p[1]) * k / n_) for k in range(n_)]
        return out
    levels = [(z0, ch), (z0 + ch, 0.0)] + [(z, 0.0) for z in np.arange(z0 + ch + 0.003, z1 - ch - 0.001, 0.003)] + [(z1 - ch, 0.0), (z1, ch)]
    n0 = len(outline(0.0))
    rings = []
    for z, d in levels:
        o = outline(d)[:n0] if len(outline(d)) >= n0 else outline(0.0)
        rings.append([bm.verts.new((x, y, z)) for x, y in o])
    for a_, b_ in zip(rings[:-1], rings[1:]):
        for i in range(n0):
            bm.faces.new((a_[i], a_[(i + 1) % n0], b_[(i + 1) % n0], b_[i]))
    for rg, z in ((rings[0], z0), (rings[-1], z1)):
        c = bm.verts.new((cx, cy, z))
        for i in range(n0):
            bm.faces.new((rg[i], rg[(i + 1) % n0], c))


prism(0.0335, AXY0 - 0.004, 0.0395, 0.0440, 0.0118, 0.0132, 0.0045, ch=0.0009)
prism(0.0245, AXY0 - 0.004, 0.0200, 0.0400, 0.0060, 0.0105, 0.0028)
bmesh.ops.triangulate(bm, faces=bm.faces[:])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(me); bm.free(); me.update()
for p in me.polygons: p.use_smooth = True
P = np.array([v.co[:] for v in me.vertices]); print('grip bounds', P.min(0).round(4), P.max(0).round(4), 'scale', round(s, 4))
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004)
bpy.ops.object.mode_set(mode='OBJECT')
img = bpy.data.images.new('ao', TEX, TEX, float_buffer=False)
mat = bpy.data.materials.new('m'); mat.use_nodes = True; me.materials.append(mat)
tn = mat.node_tree.nodes.new('ShaderNodeTexImage'); tn.image = img; mat.node_tree.nodes.active = tn
sc.render.engine = 'CYCLES'; sc.cycles.samples = 48; sc.cycles.device = 'CPU'
sc.render.bake.margin = 6
bpy.ops.object.bake(type='AO')
ao = np.array(img.pixels[:], np.float32).reshape(TEX, TEX, 4)[::-1, :, 0]
bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
co = np.array([v.co[:] for v in bm.verts]); nb = [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]
sm = co.copy()
for _ in range(12):
    sm = np.array([sm[n].mean(0) if n else sm[i] for i, n in enumerate(nb)])
nrm = np.array([v.normal[:] for v in bm.verts])
bump = ((co - sm) * nrm).sum(1)
cap = np.clip((bump - 0.0006) / 0.0012, 0, 1)
uvl = bm.loops.layers.uv.active
capimg = np.zeros((TEX, TEX), np.float32); wimg = np.zeros((TEX, TEX), np.float32); zimg = np.zeros((TEX, TEX), np.float32)
V = co.astype(np.float32); T = []; UV = []
for f in bm.faces:
    T.append([l.vert.index for l in f.loops]); UV.append([l[uvl].uv[:] for l in f.loops])
    u = np.array(UV[-1]) * (TEX - 1); cv = cap[T[-1]]; zv = co[T[-1], 2]
    x0, y0 = np.floor(u.min(0)).astype(int); x1, y1 = np.ceil(u.max(0)).astype(int)
    xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
    a, b, c = u
    d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(d) < 1e-9: continue
    w1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
    w2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
    w3 = 1 - w1 - w2
    ok = (w1 >= -0.02) & (w2 >= -0.02) & (w3 >= -0.02)
    yy, xx = TEX - 1 - ys[ok], xs[ok]
    capimg[yy, xx] += w1[ok] * cv[0] + w2[ok] * cv[1] + w3[ok] * cv[2]; wimg[yy, xx] += 1
    zimg[yy, xx] += w1[ok] * zv[0] + w2[ok] * zv[1] + w3[ok] * zv[2]
capimg = np.where(wimg > 0, capimg / np.maximum(wimg, 1), 0)
zimg = np.where(wimg > 0, zimg / np.maximum(wimg, 1), 1.0)
from scipy import ndimage as ndi
capimg = ndi.grey_dilation(capimg, size=5)
rng = np.random.default_rng(3)
grain = ndi.gaussian_filter(rng.standard_normal((TEX, TEX)).astype(np.float32), 1.2)
body = np.array([0.155, 0.158, 0.165], np.float32); capc = np.array([0.085, 0.087, 0.092], np.float32)
col = body[None, None] * (1 - capimg[..., None]) + capc[None, None] * capimg[..., None]
slv = np.clip((0.0185 - zimg) / 0.0008, 0, 1)
rngs = np.maximum(np.clip(1 - np.abs(zimg - 0.0060) / 0.0007, 0, 1), np.clip(1 - np.abs(zimg - 0.0125) / 0.0007, 0, 1)) * slv
col = col * (1 - 0.30 * slv[..., None]) + (np.array([0.40, 0.41, 0.42], np.float32) - col) * (0.8 * rngs[..., None])
col = col * (0.45 + 0.55 * ao[..., None]) * (1 + 0.04 * grain[..., None])
from PIL import Image
Image.fromarray((np.clip(col, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGB').save(OUTD + '/ckstick_base.png', optimize=True)
nrmimg = np.ones((TEX, TEX, 4), np.float32); nrmimg[..., 1:] = 0.5
Image.fromarray((nrmimg * 255 + 0.5).astype(np.uint8), 'RGBA').save(OUTD + '/ckstick_normal.png', optimize=True)
mk = np.zeros((TEX, TEX, 4), np.float32); mk[..., 3] = 0.42 + 0.12 * capimg + 0.03 * grain + 0.14 * slv
mk[..., 0] = 0.6 * slv
Image.fromarray((np.clip(mk, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGBA').save(OUTD + '/ckstick_mask.png', optimize=True)
np.savez_compressed(OUTD + '/stickgrip.npz', V=V, T=np.array(T, np.int32), UV=np.array(UV, np.float32), local=np.array([1]),
                    yawd=np.array([YAW - YAW0]), shift=np.array(SHIFT[:], np.float32))
print('stick grip:', len(T), 'triangles,', 'caps %.1f%%' % (100 * (cap > 0.5).mean()))
if PREV:
    m2 = bpy.data.materials.new('p'); m2.use_nodes = True
    t2 = m2.node_tree.nodes.new('ShaderNodeTexImage'); t2.image = bpy.data.images.load(OUTD + '/ckstick_base.png')
    bs = m2.node_tree.nodes['Principled BSDF']; m2.node_tree.links.new(t2.outputs[0], bs.inputs[0]); bs.inputs['Roughness'].default_value = 0.5
    me.materials[0] = m2
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (0.6, 0.62, 0.65, 1)
    sun = bpy.data.lights.new('s', 'SUN'); sun.energy = 3.5; so = bpy.data.objects.new('s', sun); sc.collection.objects.link(so); so.rotation_euler = (0.8, 0.2, 2.6)
    sc.cycles.samples = 24; sc.render.resolution_x = 900; sc.render.resolution_y = 600
    cam = bpy.data.cameras.new('c'); cam.lens = 55; cam.clip_start = 0.005; co_ = bpy.data.objects.new('c', cam); sc.collection.objects.link(co_); sc.camera = co_
    c = Vector((0, 0.01, 0.10)); co_.location = c + Vector((-0.12, -0.38, 0.22)); co_.rotation_euler = (c - co_.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = PREV; bpy.ops.render.render(write_still=True)
