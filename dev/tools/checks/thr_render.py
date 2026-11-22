import sys, math
import bpy
from mathutils import Vector
obj, out = sys.argv[-2:]
COL = {'rubber': (0.035, 0.035, 0.038), 'black': (0.02, 0.02, 0.02), 'darkgrey': (0.10, 0.10, 0.11), 'ltgrey': (0.42, 0.44, 0.46), 'pedgrey': (0.30, 0.32, 0.34),
       'olive': (0.45, 0.38, 0.18), 'metal': (0.55, 0.56, 0.58), 'chrome': (0.8, 0.8, 0.82), 'white': (0.9, 0.9, 0.88)}
U = lambda p: (-p[0], -p[2], p[1])
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
V = []; groups = {}; g = None
for l in open(obj):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith('o '): g = l.split()[1]
    elif l.startswith('f '): groups.setdefault(g, []).append([int(t) - 1 for t in l.split()[1:]])
for g, F in groups.items():
    used = sorted({i for f in F for i in f}); idx = {v: i for i, v in enumerate(used)}
    me = bpy.data.meshes.new(g); me.from_pydata([U(V[i]) for i in used], [], [[idx[i] for i in f][::-1] for f in F]); me.update()
    for p in me.polygons: p.use_smooth = g.endswith('rubber')
    ob = bpy.data.objects.new(g, me); sc.collection.objects.link(ob)
    m = bpy.data.materials.new(g); m.use_nodes = True; b = m.node_tree.nodes['Principled BSDF']
    c = COL.get(g.replace('thr_', ''), (0.5, 0.1, 0.5)); b.inputs['Base Color'].default_value = (*c, 1); b.inputs['Roughness'].default_value = 0.45
    if g.endswith(('metal', 'chrome', 'olive')): b.inputs['Metallic'].default_value = 0.8
    me.materials.append(m)
sc.render.engine = 'CYCLES'; sc.cycles.samples = 48; sc.cycles.use_denoising = True
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (0.75, 0.78, 0.85, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 1.2
s = bpy.data.lights.new('s', 'SUN'); s.energy = 3.5; so = bpy.data.objects.new('s', s); sc.collection.objects.link(so); so.rotation_euler = (math.radians(40), 0, math.radians(200))
c = bpy.data.cameras.new('c'); co = bpy.data.objects.new('c', c); sc.collection.objects.link(co); sc.camera = co; c.clip_start = 0.005; c.angle = math.radians(32)
sc.render.resolution_x = 760; sc.render.resolution_y = 560
VIEWS = [('front', (0.02, 0.22, 0.42)), ('outboard', (-0.45, 0.07, 0.02)), ('in_front', (0.30, 0.16, 0.30)), ('out_front_high', (-0.24, 0.30, 0.28)),
         ('top', (0.0, 0.50, -0.03)), ('aft_in', (0.28, 0.14, -0.30)), ('aft_out', (-0.28, 0.16, -0.30)), ('eye', (0.40, 0.55, -0.42))]
from PIL import Image
tiles = []
for nm, cam in VIEWS:
    p = Vector(U(cam)); t = Vector(U((0.0, 0.045, 0.0)))
    co.location = p; co.rotation_euler = (t - p).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = out + '_' + nm + '.png'; bpy.ops.render.render(write_still=True)
    tiles.append(Image.open(sc.render.filepath).convert('RGB'))
W, H = tiles[0].size
sheet = Image.new('RGB', (W * 2, H * 2))
for i, t in enumerate(tiles[:4]): sheet.paste(t, ((i % 2) * W, (i // 2) * H))
sheet.save(out + '_A.png')
sheet = Image.new('RGB', (W * 2, H * 2))
for i, t in enumerate(tiles[4:8]): sheet.paste(t, ((i % 2) * W, (i // 2) * H))
sheet.save(out + '_B.png')
