import sys, numpy as np, bpy, bmesh
OBJ, OUT = sys.argv[1], sys.argv[2]
PREV = sys.argv[3] if len(sys.argv) > 3 else None
want = {'cockpit_stick', 'cockpit_throttle'}
V = []; faces = {k: [] for k in want}; cur = None
for l in open(OBJ):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith(('o ', 'g ')): cur = l.split()[1]
    elif l.startswith('f ') and cur in want:
        faces[cur].append([int(t.split('/')[0]) for t in l.split()[1:]])
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
CFG = {'cockpit_stick': dict(voxel=0.0012, thick=0.006, smooth=(0.5, 6), tris=10000, clip=0.548, shrink=False),
       'cockpit_throttle': dict(voxel=0.0014, thick=0.0035, smooth=(0.7, 16), tris=5000, clip=None)}
res = {}
for k, F in faces.items():
    vids = sorted({a for f in F for a in f}); rm = {v: i for i, v in enumerate(vids)}
    verts = [(V[v - 1][0], V[v - 1][2], V[v - 1][1]) for v in vids]
    me = bpy.data.meshes.new(k); me.from_pydata(verts, [], [[rm[a] for a in reversed(f)] for f in F]); me.update()
    ob = bpy.data.objects.new(k, me); sc.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)
    c = CFG[k]
    if c['clip'] is not None:
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, c['clip']), plane_no=(0, 0, 1), clear_inner=True)
        bm.to_mesh(me); bm.free()
    ref = ob.copy(); ref.data = ob.data.copy(); sc.collection.objects.link(ref); ref.hide_render = True
    m = ob.modifiers.new('t', 'SOLIDIFY'); m.thickness = c['thick']; m.offset = 0.0; m.use_even_offset = True
    bpy.ops.object.modifier_apply(modifier='t')
    m = ob.modifiers.new('r', 'REMESH'); m.mode = 'VOXEL'; m.voxel_size = c['voxel']; m.use_smooth_shade = True
    bpy.ops.object.modifier_apply(modifier='r')
    bm = bmesh.new(); bm.from_mesh(ob.data)
    seen, comps = set(), []
    for f0 in bm.faces:
        if f0.index in seen: continue
        stack, comp = [f0], []
        seen.add(f0.index)
        while stack:
            f = stack.pop(); comp.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index); stack.append(g)
        comps.append(comp)
    def _vol(comp):
        return abs(sum(f.verts[0].co.dot(f.verts[1].co.cross(f.verts[2].co)) for f in comp if len(f.verts) >= 3)) / 6
    keep = set()
    vols = [(_vol(cm), cm) for cm in comps]
    big = max(v for v, _ in vols)
    for v, cm in vols:
        if v > big * 0.02:
            keep.add(id(cm))
    kept = [(v, cm) for v, cm in vols if id(cm) in keep]
    kept.sort(key=lambda t: -t[0])
    final = []
    for v, cm in kept:
        P = [vv.co for f in cm for vv in f.verts]
        mn = [min(p[i] for p in P) for i in range(3)]; mx = [max(p[i] for p in P) for i in range(3)]
        inside = False
        for v2, mn2, mx2 in final:
            if all(mn2[i] - 1e-4 <= mn[i] and mx[i] <= mx2[i] + 1e-4 for i in range(3)) and v > v2 * 0.3:
                inside = True; break
        if not inside:
            final.append((v, mn, mx));
        else:
            keep.discard(id(cm))
    drop = [f for cm in comps if id(cm) not in keep for f in cm]
    bmesh.ops.delete(bm, geom=drop, context='FACES')
    bm.to_mesh(ob.data); bm.free()
    print(k, 'surfaces after remesh:', len(comps), 'kept', len(keep))
    if c.get('shrink', True):
        m = ob.modifiers.new('w', 'SHRINKWRAP'); m.target = ref; m.wrap_method = 'NEAREST_SURFACEPOINT'; m.wrap_mode = 'OUTSIDE_SURFACE'
        bpy.ops.object.modifier_apply(modifier='w')
    else:
        m = ob.modifiers.new('d0', 'DISPLACE'); m.mid_level = 0.0; m.strength = -c['thick'] * 0.5
        bpy.ops.object.modifier_apply(modifier='d0')
    m = ob.modifiers.new('s', 'SMOOTH'); m.factor, m.iterations = c['smooth']
    bpy.ops.object.modifier_apply(modifier='s')
    n0 = len(ob.data.polygons) * 2
    if n0 > c['tris']:
        m = ob.modifiers.new('d', 'DECIMATE'); m.ratio = c['tris'] / n0
        bpy.ops.object.modifier_apply(modifier='d')
    bm = bmesh.new(); bm.from_mesh(ob.data); bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    P = np.array([v.co[:] for v in bm.verts], np.float32); T = np.array([[v.index for v in f.verts] for f in bm.faces], np.int32)
    bm.free()
    res[k] = (P, T)
    print(k, len(F), 'faces ->', len(T), 'triangles; bounds', P.min(0).round(3), P.max(0).round(3))
np.savez_compressed(OUT, stick_v=res['cockpit_stick'][0], stick_f=res['cockpit_stick'][1],
                    thr_v=res['cockpit_throttle'][0], thr_f=res['cockpit_throttle'][1])
if PREV:
    import math
    from mathutils import Vector
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (0.6, 0.62, 0.66, 1)
    sun = bpy.data.lights.new('s', 'SUN'); sun.energy = 3; so = bpy.data.objects.new('s', sun); sc.collection.objects.link(so); so.rotation_euler = (0.7, 0.2, 0.5)
    sc.render.engine = 'CYCLES'; sc.cycles.samples = 16; sc.render.resolution_x = sc.render.resolution_y = 500
    mat = bpy.data.materials.new('m'); mat.use_nodes = True; mat.node_tree.nodes['Principled BSDF'].inputs[0].default_value = (0.05, 0.05, 0.055, 1)
    cam = bpy.data.cameras.new('c'); co = bpy.data.objects.new('c', cam); sc.collection.objects.link(co); sc.camera = co; cam.lens = 60
    for ob in sc.objects:
        if ob.type == 'MESH': ob.data.materials.append(mat); [setattr(p, 'use_smooth', True) for p in ob.data.polygons]
    for k in want:
        ob = bpy.data.objects[k]
        P = np.array([v.co[:] for v in ob.data.vertices]); mn, mx = P.min(0), P.max(0)
        cc = Vector(((mn + mx) / 2).tolist()); r = float(np.linalg.norm(mx - mn))
        for vn, d in (('aft', Vector((0.3, -1, 0.5))), ('side', Vector((1, 0.1, 0.25))), ('front', Vector((-0.4, 1, 0.6)))):
            for o2 in sc.objects:
                if o2.type == 'MESH': o2.hide_render = o2.name != k
            co.location = cc + d.normalized() * r * 2.2
            co.rotation_euler = (cc - co.location).to_track_quat('-Z', 'Y').to_euler()
            sc.render.filepath = f'{PREV}/{k}_{vn}.png'; bpy.ops.render.render(write_still=True)
