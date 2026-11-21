import math

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector


def obj_from_bm(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def bm_from_obj(ob, apply_mods=True):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps) if apply_mods else ob
    me = bpy.data.meshes.new_from_object(ev)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(ob.matrix_world)
    bpy.data.meshes.remove(me)
    return bm


def remove(ob):
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


def modded(bm, bevel=0.0, seg=2, subsurf=0, angle=None, harden=False):
    ob = obj_from_bm("tmp_mod", bm)
    if bevel > 0:
        b = ob.modifiers.new("bev", 'BEVEL')
        b.width = bevel
        b.segments = seg
        b.limit_method = 'ANGLE'
        b.angle_limit = math.radians(angle if angle is not None else 30)
        b.harden_normals = harden
    if subsurf:
        s = ob.modifiers.new("sub", 'SUBSURF')
        s.levels = subsurf
        s.render_levels = subsurf
        s.uv_smooth = 'PRESERVE_CORNERS'
    out = bm_from_obj(ob)
    remove(ob)
    return out


def part(name, bm, surface, group, uvmode="pack", smooth=40.0):
    ob = obj_from_bm(name, bm)
    bm.free()
    ob["surface"] = surface
    ob["group"] = group
    ob["uvmode"] = uvmode
    ob["smooth"] = smooth
    return ob


def frame(ex, ey, ez):
    return Matrix((ex, ey, ez)).transposed()


def to_world(origin, F, p):
    return Vector(origin) + F @ Vector(p)


def box(bm, centre, size, F=None):
    m = Matrix.Translation(centre) @ (F.to_4x4() if F is not None else Matrix()) @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    return bmesh.ops.create_cube(bm, size=1.0, matrix=m)


def rbox(centre, size, F=None, bevel=0.01, seg=3, subsurf=0):
    bm = bmesh.new()
    box(bm, centre, size, F)
    if bevel > 0 or subsurf:
        out = modded(bm, bevel=min(bevel, 0.49 * min(size)), seg=seg, subsurf=subsurf)
        bm.free()
        return out
    return bm


def prism_profile(bm, pts2d, origin, F, depth):
    vs0 = [bm.verts.new(to_world(origin, F, (p[0], p[1], -depth / 2))) for p in pts2d]
    vs1 = [bm.verts.new(to_world(origin, F, (p[0], p[1], depth / 2))) for p in pts2d]
    n = len(pts2d)
    bm.faces.new(list(reversed(vs0)))
    bm.faces.new(vs1)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([vs0[i], vs0[j], vs1[j], vs1[i]])
    return bm


def cylinder(bm, base, axis, r, h, seg=16, r_top=None, cap=True):
    axis = Vector(axis).normalized()
    t = axis.orthogonal().normalized()
    b = axis.cross(t)
    rt = r if r_top is None else r_top
    ring0, ring1 = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        d = t * math.cos(a) + b * math.sin(a)
        ring0.append(bm.verts.new(Vector(base) + d * r))
        ring1.append(bm.verts.new(Vector(base) + axis * h + d * rt))
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new([ring0[i], ring0[j], ring1[j], ring1[i]])
    if cap:
        bm.faces.new(list(reversed(ring0)))
        bm.faces.new(ring1)
    return ring0, ring1


def catmull(points, per=6):
    P = [Vector(p) for p in points]
    if len(P) < 3:
        return P
    out = []
    ext = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    out.append(P[-1])
    return out


def _frames(path, up_hint):
    T, N, B = [], [], []
    n = len(path)
    for i in range(n):
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, n - 1)]
        t = (b - a).normalized()
        u = Vector(up_hint[i] if isinstance(up_hint, list) else up_hint)
        bn = t.cross(u)
        if bn.length < 1e-6:
            bn = t.orthogonal()
        bn.normalize()
        nn = bn.cross(t).normalized()
        T.append(t); N.append(nn); B.append(bn)
    return T, N, B


def tube(path, r, seg=12, up=(0, 0, 1), uv_rect=None, closed=False):
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    path = [Vector(p) for p in path]
    T, N, B = _frames(path, up)
    L = [0.0]
    for i in range(1, len(path)):
        L.append(L[-1] + (path[i] - path[i - 1]).length)
    rings = []
    for i, p in enumerate(path):
        rings.append([bm.verts.new(p + (N[i] * math.cos(2 * math.pi * k / seg) + B[i] * math.sin(2 * math.pi * k / seg)) * r) for k in range(seg)])
    for i in range(len(path) - 1):
        for k in range(seg):
            k2 = (k + 1) % seg
            f = bm.faces.new([rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]])
            if uv_rect:
                u0, v0, u1, v1 = uv_rect
                for lp, (ii, kk) in zip(f.loops, [(i, k), (i, k + 1), (i + 1, k + 1), (i + 1, k)]):
                    lp[uvl].uv = (u0 + (u1 - u0) * L[ii] / L[-1], v0 + (v1 - v0) * kk / seg)
    if not closed:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bm.normal_update()
    return bm, L[-1]


def ribbon(path, normals, width, thick, uv_rect=None, px_per_m=None):
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    path = [Vector(p) for p in path]
    T, N, B = _frames(path, [Vector(n) for n in normals])
    L = [0.0]
    for i in range(1, len(path)):
        L.append(L[-1] + (path[i] - path[i - 1]).length)
    sec = [(-0.5, 0.0), (0.5, 0.0), (0.5, 1.0), (-0.5, 1.0)]
    rings = [[bm.verts.new(p + B[i] * (sb * width) + N[i] * (sn * thick)) for sb, sn in sec] for i, p in enumerate(path)]
    for i in range(len(path) - 1):
        for k in range(4):
            k2 = (k + 1) % 4
            f = bm.faces.new([rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]])
            if uv_rect:
                u0, v0, u1, v1 = uv_rect
                du = (L[-1] * px_per_m) if px_per_m else 1.0
                for lp, (ii, kk) in zip(f.loops, [(i, k), (i, k2), (i + 1, k2), (i + 1, k)]):
                    s = L[ii] / L[-1]
                    across = {0: 0.0, 1: 1.0, 2: 1.0, 3: 0.0}[kk]
                    lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * across)
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bm.normal_update()
    return bm, L[-1]


def set_uv_all(bm, uv):
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uvl].uv = uv
    return bm


def merge(bms):
    out = bmesh.new()
    for b in bms:
        me = bpy.data.meshes.new("tmp_merge")
        b.to_mesh(me)
        out.from_mesh(me)
        bpy.data.meshes.remove(me)
    return out


def triangles(ob, layer=None):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(ob.matrix_world)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.normal_update()
    uvl = bm.loops.layers.uv.get(layer) if layer else bm.loops.layers.uv.active
    lim = math.cos(math.radians(float(ob.get("smooth", 40.0))))
    P, UV, N = [], [], []
    for f in bm.faces:
        if f.calc_area() < 1e-12:
            continue
        fp, fu, fn = [], [], []
        for lp in f.loops:
            v = lp.vert
            acc = Vector()
            for lf in v.link_faces:
                if lf.normal.dot(f.normal) >= lim:
                    acc += lf.normal * lf.calc_area()
            if acc.length < 1e-9:
                acc = f.normal.copy()
            fp.append(tuple(v.co)); fn.append(tuple(acc.normalized()))
            fu.append(tuple(lp[uvl].uv) if uvl else (0.0, 0.0))
        P.append(fp); UV.append(fu); N.append(fn)
    bm.free()
    return np.array(P), np.array(UV), np.array(N)


def to_unity(P, UV, N):
    sw = [0, 2, 1]
    Pu = P[:, sw][:, :, [0, 2, 1]]
    Nu = N[:, sw][:, :, [0, 2, 1]]
    return Pu, UV[:, sw], Nu
