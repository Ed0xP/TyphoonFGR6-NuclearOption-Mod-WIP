import math

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def _obj_from_bm(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _bm_from_obj(ob):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = bpy.data.meshes.new_from_object(ev)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(ob.matrix_world)
    bm.normal_update()
    return bm


def _remove(ob):
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


def smooth_part(bm, levels=2, crease_angle=None):
    ob = _obj_from_bm("tmp_smooth", bm)
    me = ob.data
    if crease_angle is not None:
        me.update()
        bm2 = bmesh.new(); bm2.from_mesh(me)
        cl = bm2.edges.layers.float.get("crease_edge") or bm2.edges.layers.float.new("crease_edge")
        for e in bm2.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(crease_angle):
                e[cl] = 1.0
        bm2.to_mesh(me); bm2.free()
    mod = ob.modifiers.new("sub", 'SUBSURF')
    mod.levels = levels
    mod.render_levels = levels
    mod.uv_smooth = 'PRESERVE_CORNERS'
    out = _bm_from_obj(ob)
    _remove(ob)
    return out


def _box(bm, centre, size, rot=None):
    m = Matrix.Translation(centre) @ (rot.to_4x4() if rot else Matrix()) @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)


def _beveled(bm_parts, width, segments=3):
    ob = _obj_from_bm("tmp_bevel", bm_parts)
    bev = ob.modifiers.new("bev", 'BEVEL')
    bev.width = width
    bev.segments = segments
    bev.limit_method = 'ANGLE'
    out = _bm_from_obj(ob)
    _remove(ob)
    return out


def make_throttles(shell_bm, x, y, top=None):
    if top is None:
        tree = BVHTree.FromBMesh(shell_bm)
        hit = tree.ray_cast(Vector((x, y, 2.0)), Vector((0, 0, -1)))
        top = hit[0].z if hit[0] is not None else 0.6
    base = bmesh.new()
    _box(base, Vector((x, y, top + 0.006)), (0.09, 0.15, 0.012))
    base = _beveled(base, 0.004, 2)
    lev = bmesh.new()
    pivot = Vector((x, y - 0.02, top + 0.012))
    for dx in (-0.024, 0.024):
        sh = Vector((x + dx, y - 0.005, top + 0.045))
        _box(lev, sh, (0.016, 0.022, 0.075))
        g = Vector((x + dx * 1.15, y + 0.012, top + 0.095))
        _box(lev, g, (0.034, 0.062, 0.042))
        _box(lev, g + Vector((0, -0.012, 0.026)), (0.030, 0.034, 0.016))
    lev = _beveled(lev, 0.006, 3)
    lev = smooth_part(lev, 1)
    return lev, base, pivot, pivot + Vector((1, 0, 0)), top


def make_hud_frame(hud_bm, thickness=0.004):
    ob = _obj_from_bm("tmp_hud", hud_bm)
    bpy.context.view_layer.objects.active = ob
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(5), verts=bm.verts, edges=bm.edges)
    for f in list(bm.faces):
        f.normal_update()
        if f.normal.y > 0:
            bm.faces.remove(f)
    bm.to_mesh(me); bm.free()
    wf = ob.modifiers.new("wf", 'WIREFRAME')
    wf.thickness = thickness
    wf.use_boundary = True
    wf.use_even_offset = True
    wf.use_relative_offset = False
    out = _bm_from_obj(ob)
    _remove(ob)
    return out


def bake_ao(target_bm, occluders, size, distance=0.25, samples=48):
    import numpy as np
    w, h = size
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.render.bake.margin = 6
    scene.world = scene.world or bpy.data.worlds.new("w")
    scene.world.light_settings.distance = distance
    tgt = _obj_from_bm("ao_target", target_bm)
    occ = [_obj_from_bm(f"ao_occ{i}", b) for i, b in enumerate(occluders)]
    img = bpy.data.images.new("ao", w, h, alpha=False, float_buffer=True)
    img.generated_color = (1, 1, 1, 1)
    mat = bpy.data.materials.new("ao_mat"); mat.use_nodes = True
    node = mat.node_tree.nodes.new('ShaderNodeTexImage'); node.image = img
    mat.node_tree.nodes.active = node
    tgt.data.materials.append(mat)
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    tgt.select_set(True)
    bpy.context.view_layer.objects.active = tgt
    bpy.ops.object.bake(type='AO', margin=6)
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    ao = px.reshape(h, w, 4)[::-1, :, 0].copy()
    for ob in [tgt] + occ:
        _remove(ob)
    bpy.data.images.remove(img)
    return ao
