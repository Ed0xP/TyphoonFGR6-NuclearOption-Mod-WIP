import math
import os
import sys

import numpy as np
import bpy
import bmesh
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from scipy.interpolate import PchipInterpolator

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "model"))
import ckmodel as ck

a_ = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
OUT = a_[0]
PREVIEW = len(a_) > 1 and a_[1] == "preview"
os.makedirs(OUT, exist_ok=True)

SEC = [(0.000, 0.0000, 0.0000, 0.0160, 0.0160, 2.0), (0.017, 0.0000, 0.0005, 0.0175, 0.0175, 2.2),
       (0.025, -0.0010, 0.0010, 0.0210, 0.0200, 3.0), (0.039, -0.0020, 0.0015, 0.0235, 0.0230, 3.6),
       (0.061, -0.0040, 0.0025, 0.0265, 0.0250, 4.0), (0.086, -0.0060, 0.0040, 0.0290, 0.0260, 4.2),
       (0.108, -0.0065, 0.0060, 0.0290, 0.0260, 4.2), (0.119, -0.0060, 0.0080, 0.0280, 0.0250, 4.0),
       (0.126, -0.0020, 0.0100, 0.0200, 0.0200, 3.0), (0.132, 0.0005, 0.0120, 0.0150, 0.0160, 2.8),
       (0.138, 0.0010, 0.0140, 0.0142, 0.0150, 2.8), (0.158, 0.0010, 0.0190, 0.0142, 0.0150, 2.8),
       (0.166, 0.0010, 0.0220, 0.0120, 0.0130, 2.5)]
S = np.array(SEC)
F_ = [PchipInterpolator(S[:, 0], S[:, k]) for k in range(1, 6)]


def sec(z):
    return [float(f(z)) for f in F_]


def loft(nz=90, ns=64):
    bm = bmesh.new()
    rings = []
    for i in range(nz + 1):
        z = S[0, 0] + (S[-1, 0] - S[0, 0]) * i / nz
        cx, cy, a, b, e = sec(z)
        ring = []
        for k in range(ns):
            t = 2 * math.pi * k / ns
            c, s = math.cos(t), math.sin(t)
            ring.append(bm.verts.new((cx + a * math.copysign(abs(c) ** (2 / e), c), cy + b * math.copysign(abs(s) ** (2 / e), s), z)))
        rings.append(ring)
    for i in range(nz):
        for k in range(ns):
            bm.faces.new((rings[i][k], rings[i][(k + 1) % ns], rings[i + 1][(k + 1) % ns], rings[i + 1][k]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    return bm


def ellipsoid(c, r, seg=20):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=1.0)
    for v in bm.verts:
        v.co = Vector(c) + Vector((v.co.x * r[0], v.co.y * r[1], v.co.z * r[2]))
    return bm


def moulded(bms, cuts=(), voxel=0.0009, smooth=(0.55, 7), ratio=0.16):
    obs = []
    ncut = len(cuts)
    bms = list(bms) + list(cuts)
    for i, b in enumerate(bms):
        bmesh.ops.recalc_face_normals(b, faces=b.faces[:])
        me = bpy.data.meshes.new("m%d" % i)
        b.to_mesh(me)
        b.free()
        ob = bpy.data.objects.new("m%d" % i, me)
        bpy.context.scene.collection.objects.link(ob)
        obs.append(ob)
    base = obs[0]
    for k_, o in enumerate(obs[1:], 1):
        m = base.modifiers.new("u", "BOOLEAN")
        m.operation, m.solver, m.object = ("DIFFERENCE" if k_ >= len(obs) - ncut else "UNION"), "EXACT", o
    m = base.modifiers.new("r", "REMESH")
    m.mode, m.voxel_size = "VOXEL", voxel
    m = base.modifiers.new("s", "SMOOTH")
    m.factor, m.iterations = smooth
    m = base.modifiers.new("d", "DECIMATE")
    m.ratio = ratio
    ev = base.evaluated_get(bpy.context.evaluated_depsgraph_get())
    out = bmesh.new()
    out.from_mesh(ev.to_mesh())
    ev.to_mesh_clear()
    for o in obs:
        me = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(me)
    bmesh.ops.triangulate(out, faces=out.faces[:])
    return out


def cyl(base, axis, r, h, seg=20, r_top=None):
    bm = bmesh.new()
    ck.cylinder(bm, Vector(base), Vector(axis).normalized(), r, h, seg=seg, r_top=r_top)
    return bm


Xv, Yv, Zv = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
TILT = math.radians(35)
PV = Vector((0, math.sin(TILT), math.cos(TILT)))
PN = Vector((0, -math.cos(TILT), math.sin(TILT)))
P0 = Vector((0.001, 0.004, 0.156))
FP = ck.frame(Xv, PV, PN)
HEAD = [(-12.8, -9.0), (-12.8, 0.0), (-19.8, 7.0), (-27.3, 12.8), (-32.7, 20.4), (-34.9, 29.2), (-34.4, 37.9), (-31.4, 45.4),
        (-25.6, 50.1), (-17.5, 52.4), (-4.1, 53.0), (16.3, 52.4), (29.2, 47.8), (33.8, 40.8), (34.4, 26.2), (32.7, 16.3),
        (27.9, 9.3), (21.0, 4.6), (15.1, 0.0), (15.1, -9.0)]
T_HEAD = 0.024


def pl(u, v, w=0.0):
    return P0 + Xv * (u * 0.001) + PV * (v * 0.001) + PN * w


def plate():
    bm = bmesh.new()
    fr_ = [bm.verts.new(pl(u, v, 0.0)) for u, v in HEAD]
    bk_ = [bm.verts.new(pl(u, v, -T_HEAD)) for u, v in HEAD]
    n_ = len(HEAD)
    bm.faces.new(fr_)
    bm.faces.new(bk_[::-1])
    for i in range(n_):
        j = (i + 1) % n_
        bm.faces.new((fr_[j], fr_[i], bk_[i], bk_[j]))
    return ck.modded(bm, bevel=0.0035, seg=3, angle=30)


def ell_f(c, F, r, seg=24):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=1.0)
    for v in bm.verts:
        v.co = Vector(c) + F @ Vector((v.co.x * r[0], v.co.y * r[1], v.co.z * r[2]))
    return bm


REST_C = Vector((0.0330, 0.0080, 0.0560))
lumps = [loft(nz=120), plate(),
         ck.rbox(REST_C, (0.022, 0.040, 0.032), None, bevel=0.003, seg=2),
         ellipsoid((0.001, 0.036, 0.150), (0.0080, 0.0090, 0.0150))]
cuts = [ell_f(pl(-27.3, 32.0, 0.0030), FP, (0.0150, 0.0150, 0.0062)),
        ell_f(pl(15.1, 26.2, 0.0020), FP, (0.0072, 0.0140, 0.0042)),
        ellipsoid((0.0020, 0.0005, 0.1500), (0.0098, 0.0050, 0.0098)),
        ck.rbox(Vector((-0.0370, 0.0100, 0.0950)), (0.0060, 0.0170, 0.0170), None, bevel=0.003, seg=2)]
body = moulded(lumps, cuts, voxel=0.0008, smooth=(0.5, 4), ratio=0.20)
body.verts.ensure_lookup_table(); body.faces.ensure_lookup_table(); body.normal_update()
bvh = BVHTree.FromPolygons([v.co.copy() for v in body.verts], [tuple(v.index for v in f.verts) for f in body.faces])
parts = [("black", body)]


def put(col, bm):
    parts.append((col, bm))


def on_plate(u, v):
    h = bvh.ray_cast(pl(u, v, 0.05), -PN, 0.2)
    return h[0]


def on_rear(x, z):
    h = bvh.ray_cast(Vector((x, -0.3, z)), Yv, 1.0)
    return h[0], h[1]


def fr(n, up=Zv):
    ex = up.cross(n).normalized()
    return ck.frame(ex, n.cross(ex).normalized(), n)


def rz(F, deg):
    return F @ Matrix.Rotation(math.radians(deg), 3, 'Z')


p = on_plate(-27.3, 32.0)
put("metal", cyl(p - PN * 0.0004, PN, 0.0092, 0.0012, 32, 0.0086))
put("darkgrey", cyl(p + PN * 0.0008, PN, 0.0058, 0.0070, 20))
put("black", cyl(p + PN * 0.0078, PN, 0.0074, 0.0062, 28, 0.0068))
for k in range(4):
    c = p + PN * 0.0078 + rz(FP, 45 + 90 * k).col[0] * 0.0072
    put("black", cyl(c, PN, 0.0046, 0.0062, 18, 0.0040))
put("darkgrey", cyl(p + PN * 0.0140, PN, 0.0034, 0.0004, 16))
p = on_plate(11.3, 45.5)
put("black", ck.rbox(p + PN * 0.0040 + PV * 0.0040, (0.0190, 0.0180, 0.0110), FP, bevel=0.0028, seg=3))
for i in range(7):
    put("darkgrey", ck.rbox(p + PN * 0.0100 + PV * (-0.0026 + i * 0.0022), (0.0172, 0.0011, 0.0022), FP, bevel=0.0004, seg=1))
p = on_plate(15.1, 26.2)
put("yellow", ck.rbox(p + PN * 0.0022, (0.0088, 0.0215, 0.0056), FP, bevel=0.0027, seg=4))
hx = pl(25.6, 26.2, 0.0020)
put("darkgrey", cyl(hx - PV * 0.0200, PV, 0.0024, 0.0400, 12))
put("black", ck.rbox(hx - PN * 0.0010, (0.0070, 0.0440, 0.0030), FP, bevel=0.0010, seg=1))
Rg = FP @ Matrix.Rotation(math.radians(-58), 3, 'Y')
gc = hx + Rg.col[0] * (-0.0100) + Rg.col[2] * 0.0012
put("metal", ck.rbox(gc, (0.0200, 0.0390, 0.0012), Rg, bevel=0.0004, seg=1))
for sy in (-1, 1):
    put("metal", ck.rbox(gc + Rg.col[1] * (sy * 0.0190) - Rg.col[2] * 0.0042, (0.0200, 0.0012, 0.0096), Rg, bevel=0.0003, seg=1))
put("metal", ck.rbox(gc + Rg.col[0] * (-0.0100) - Rg.col[2] * 0.0042, (0.0012, 0.0390, 0.0096), Rg, bevel=0.0003, seg=1))
p = on_plate(-5.8, 12.8)
put("darkgrey", cyl(p - PN * 0.0003, PN, 0.0031, 0.0010, 14))
put("black", ck.rbox(p + PN * 0.0008, (0.0046, 0.0008, 0.0003), rz(FP, 30), bevel=0))
p, n = on_rear(0.0020, 0.1500)
n = Vector((0, -1, 0.15)).normalized()
put("darkgrey", cyl(p - n * 0.0006, n, 0.0086, 0.0020, 28, 0.0080))
put("black", cyl(p + n * 0.0010, n, 0.0060, 0.0030, 24, 0.0052))
p, n = on_rear(-0.0175, 0.1080)
put("darkgrey", cyl(p - n * 0.0006, n, 0.0056, 0.0018, 20, 0.0050))
put("black", cyl(p + n * 0.0008, n, 0.0038, 0.0030, 16, 0.0032))
h = bvh.ray_cast(Vector((-0.0300, 0.0080, 0.30)), -Zv, 1.0)
p, n = h[0], Vector((-0.38, -0.20, 0.90)).normalized()
Fc = fr(n, Yv)
put("darkgrey", cyl(p - n * 0.0015, n, 0.0074, 0.0050, 22, 0.0048))
put("black", cyl(p + n * 0.0030, n, 0.0034, 0.0100, 14))
put("black", cyl(p + n * 0.0125, n, 0.0048, 0.0050, 18, 0.0042))
for k in range(4):
    R = rz(Fc, 90 * k)
    put("black", ck.rbox(p + n * 0.0150 + R.col[0] * 0.0062, (0.0070, 0.0046, 0.0046), R, bevel=0.0015, seg=2))
h = bvh.ray_cast(Vector((-0.2, 0.0100, 0.0950)), Xv, 1.0)
if h[0] is not None:
    Fq = ck.frame(Yv, Zv, -Xv)
    for k_, (w_, d_) in enumerate(((0.0140, 0.0014), (0.0100, 0.0026), (0.0058, 0.0038))):
        put("darkgrey" if k_ == 0 else "black", ck.rbox(h[0] - Xv * (d_ / 2 - 0.0006), (w_, w_, d_), Fq, bevel=0.0012, seg=2))
for i in range(6):
    p, n = on_rear(0.0175, 0.0380 + i * 0.0040)
    put("black", ck.rbox(p + n * 0.0006, (0.0105, 0.0016, 0.0020), rz(fr(n), 22), bevel=0.0006, seg=1))
tp = [Vector((0.001, 0.0440, 0.158)), Vector((0.001, 0.0490, 0.147)), Vector((0.001, 0.0505, 0.136)), Vector((0.001, 0.0480, 0.126))]
for a, b in zip(tp[:-1], tp[1:]):
    d = (b - a).normalized()
    put("black", ck.rbox((a + b) / 2, (0.0120, 0.0056, (b - a).length + 0.004), ck.frame(Xv, d.cross(Xv).normalized(), d), bevel=0.0022, seg=2))

lines, nv = [], 0
by = {}
for col, bm in parts:
    by.setdefault(col, []).append(bm)
ntri = 0
for col, bms in by.items():
    lines.append("o grip_" + col)
    for bm in bms:
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.verts.ensure_lookup_table()
        for v in bm.verts:
            lines.append("v %.5f %.5f %.5f" % (v.co.x, v.co.z, v.co.y))
        for f in bm.faces:
            lines.append("f " + " ".join(str(nv + v.index + 1) for v in f.verts))
        nv += len(bm.verts)
        ntri += len(bm.faces)
open(os.path.join(OUT, "grip_preview.obj"), "w").write("\n".join(lines) + "\n")
print("gripgen: %d parts, %d triangles (casting %d)" % (len(parts), ntri, len(body.faces)))

if not PREVIEW:
    from PIL import Image, ImageDraw
    COL = {"black": ((0.085, 0.088, 0.092), 0.0, 0.32), "darkgrey": ((0.170, 0.175, 0.182), 0.1, 0.36),
           "metal": ((0.50, 0.51, 0.52), 0.9, 0.58), "yellow": ((0.80, 0.66, 0.08), 0.0, 0.42)}
    allb = bmesh.new()
    cid = allb.faces.layers.int.new("col")
    names = list(COL)
    for col, bm in parts:
        vm = {v: allb.verts.new(v.co) for v in bm.verts}
        for f in bm.faces:
            try:
                nf = allb.faces.new([vm[v] for v in f.verts])
            except ValueError:
                continue
            nf[cid] = names.index(col)
    me = bpy.data.meshes.new("grip")
    allb.to_mesh(me)
    ob = bpy.data.objects.new("grip", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.006)
    bpy.ops.object.mode_set(mode="OBJECT")
    me = ob.data
    V = np.array([v.co[:] for v in me.vertices], np.float32)
    T = np.array([p.vertices[:] for p in me.polygons], np.int32)
    uvl = me.uv_layers.active.data
    UV = np.array([[uvl[li].uv[:] for li in p.loop_indices] for p in me.polygons], np.float32)
    fc = np.array([d.value for d in me.attributes["col"].data], np.int32)
    R = 2048
    base = Image.new("RGB", (R, R), (22, 23, 24))
    mk = Image.new("RGBA", (R, R), (0, 0, 0, 82))
    db, dm = ImageDraw.Draw(base), ImageDraw.Draw(mk)
    for t in range(len(T)):
        c, mt, sm = COL[names[fc[t]]]
        poly = [(float(u) * R, (1 - float(v)) * R) for u, v in UV[t]]
        db.polygon(poly, fill=tuple(int(x * 255 + 0.5) for x in c), outline=tuple(int(x * 255 + 0.5) for x in c))
        dm.polygon(poly, fill=(int(mt * 255), int(mt * 255), int(mt * 255), int(sm * 255)), outline=(int(mt * 255), int(mt * 255), int(mt * 255), int(sm * 255)))
    import cv2
    for im, nm in ((base, "ckstick_base.png"), (mk, "ckstick_mask.png")):
        a = np.asarray(im).copy()
        cov = np.zeros((R, R), np.uint8)
        dc = Image.new("L", (R, R), 0)
        dd = ImageDraw.Draw(dc)
        for t in range(len(T)):
            dd.polygon([(float(u) * R, (1 - float(v)) * R) for u, v in UV[t]], fill=255, outline=255)
        cov = np.asarray(dc) > 0
        k3 = np.ones((3, 3), np.uint8)
        f_ = cov.astype(np.uint8)
        for _ in range(8):
            d_ = cv2.dilate(a, k3)
            g_ = cv2.dilate(f_, k3)
            new = (g_ > 0) & (f_ == 0)
            a[new] = d_[new]
            f_ = g_
        Image.fromarray(a, im.mode).save(os.path.join(OUT, nm))
    nr = np.zeros((R, R, 4), np.uint8)
    nr[..., 0], nr[..., 1], nr[..., 2], nr[..., 3] = 255, 128, 128, 128
    Image.fromarray(nr, "RGBA").save(os.path.join(OUT, "ckstick_normal.png"))
    np.savez_compressed(os.path.join(OUT, "stickgrip.npz"), V=V, T=T, UV=UV, local=np.array([1]), own=np.array([1]))
    print("gripgen: stickgrip.npz %d vertices, %d triangles; UV range %.3f .. %.3f" % (len(V), len(T), UV.min(), UV.max()))
