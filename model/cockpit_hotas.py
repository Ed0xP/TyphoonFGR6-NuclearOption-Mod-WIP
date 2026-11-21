import math

import bmesh
from mathutils import Vector

import ckmodel as ck


def loft(sections, N=40, cap=True):
    bm_ = bmesh.new()
    rings = []
    for s in sections:
        c_, a_, b_, e_ = s[:4]
        tilt = s[4] if len(s) > 4 else 0.0
        ring = []
        for k in range(N):
            t = 2 * math.pi * k / N
            ct, st_ = math.cos(t), math.sin(t)
            x_ = math.copysign(abs(ct) ** (2 / e_), ct) * a_
            y_ = math.copysign(abs(st_) ** (2 / e_), st_) * b_
            ring.append(bm_.verts.new(Vector(c_) + Vector((x_, y_, tilt * y_))))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(N):
            k2 = (k + 1) % N
            bm_.faces.new([rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]])
    if cap:
        bm_.faces.new(list(reversed(rings[0])))
        bm_.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm_, faces=bm_.faces[:])
    return bm_


def gear(base, axis, r, h, teeth=20, depth=0.0006, r_top=None):
    bm_ = bmesh.new()
    axis = Vector(axis).normalized()
    t = axis.orthogonal().normalized()
    b = axis.cross(t)
    rt = r if r_top is None else r_top
    n = teeth * 2
    r0, r1 = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        d = t * math.cos(a) + b * math.sin(a)
        k = depth if i % 2 == 0 else 0.0
        r0.append(bm_.verts.new(Vector(base) + d * (r - k)))
        r1.append(bm_.verts.new(Vector(base) + axis * h + d * (rt - k)))
    for i in range(n):
        j = (i + 1) % n
        bm_.faces.new([r0[i], r0[j], r1[j], r1[i]])
    bm_.faces.new(list(reversed(r0)))
    bm_.faces.new(r1)
    bmesh.ops.recalc_face_normals(bm_, faces=bm_.faces[:])
    return bm_


def cyl(base, axis, r, h, seg=24, r_top=None):
    bm_ = bmesh.new()
    ck.cylinder(bm_, base, axis, r, h, seg=seg, r_top=r_top)
    bmesh.ops.recalc_face_normals(bm_, faces=bm_.faces[:])
    return bm_


def frame_z(axis, hint=(0, 1, 0)):
    ez = Vector(axis).normalized()
    ex = Vector(hint).cross(ez)
    if ex.length < 1e-4:
        ex = Vector((1, 0, 0)).cross(ez)
    ex.normalize()
    ey = ez.cross(ex)
    return ck.frame(ex, ey, ez)


def hat(base, axis, r, kind, hint=(0, 1, 0)):
    out = []
    axis = Vector(axis).normalized()
    F = frame_z(axis, hint)
    out.append(("darkgrey", cyl(base, axis, r * 0.95, 0.0025, seg=20)))
    out.append(("black", cyl(base + axis * 0.0025, axis, r * 0.42, 0.004, seg=12)))
    top = base + axis * 0.0065
    if kind == "ribbed":
        out.append(("darkgrey", ck.rbox(top + axis * 0.002, (r * 1.9, r * 1.9, 0.004), F, bevel=0.0009, seg=2)))
        for i in range(-2, 3):
            out.append(("black", ck.rbox(top + axis * 0.0044 + F @ Vector((i * r * 0.36, 0, 0)), (r * 0.16, r * 1.7, 0.0012), F, bevel=0.0003, seg=1)))
    elif kind == "cross":
        for sz in ((r * 2.1, r * 0.75, 0.0045), (r * 0.75, r * 2.1, 0.0045)):
            out.append(("darkgrey", ck.rbox(top + axis * 0.002, sz, F, bevel=0.0008, seg=2)))
        out.append(("black", cyl(top + axis * 0.004, axis, r * 0.32, 0.0012, seg=12)))
    else:
        out.append(("darkgrey", gear(top, axis, r, 0.0042, teeth=14, depth=0.0005, r_top=r * 0.82)))
        out.append(("black", cyl(top + axis * 0.0042, axis, r * 0.6, 0.0008, seg=16, r_top=r * 0.4)))
    return out


def button(base, axis, r, col, guard=True, h=0.0035):
    out = []
    axis = Vector(axis).normalized()
    if guard:
        out.append(("black", cyl(base, axis, r * 1.35, h * 0.75, seg=24, r_top=r * 1.25)))
    out.append((col, cyl(base, axis, r, h * 1.3, seg=20, r_top=r * 0.88)))
    return out


def _prism(pts, ax_u, ax_v, ax_w, w0, w1):
    bm_ = bmesh.new()
    U, Vv, W = Vector(ax_u), Vector(ax_v), Vector(ax_w)
    lo = [bm_.verts.new(U * u + Vv * v + W * w0) for u, v in pts]
    hi = [bm_.verts.new(U * u + Vv * v + W * w1) for u, v in pts]
    bm_.faces.new(lo[::-1]); bm_.faces.new(hi)
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm_.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bmesh.ops.recalc_face_normals(bm_, faces=bm_.faces[:])
    return bm_


def silhouette_body(side, top, back, voxel=0.0016, smooth=(0.6, 10), ratio=0.14):
    import bpy
    big = 0.3
    A = _prism(side, (0, 1, 0), (0, 0, 1), (1, 0, 0), -big, big)
    B = _prism(top, (1, 0, 0), (0, 1, 0), (0, 0, 1), -big, big)
    Cc = _prism(back, (1, 0, 0), (0, 0, 1), (0, 1, 0), -big, big)
    obs = []
    for nm, bm_ in (("sa", A), ("sb", B), ("sc", Cc)):
        me = bpy.data.meshes.new(nm); bm_.to_mesh(me); bm_.free()
        ob = bpy.data.objects.new(nm, me); bpy.context.scene.collection.objects.link(ob); obs.append(ob)
    base = obs[0]
    for other in obs[1:]:
        m = base.modifiers.new("i", "BOOLEAN"); m.operation = "INTERSECT"; m.solver = "EXACT"; m.object = other
    m = base.modifiers.new("r", "REMESH"); m.mode = "VOXEL"; m.voxel_size = voxel
    m = base.modifiers.new("s", "SMOOTH"); m.factor, m.iterations = smooth
    m = base.modifiers.new("d", "DECIMATE"); m.ratio = ratio
    dg = bpy.context.evaluated_depsgraph_get()
    ev = base.evaluated_get(dg)
    out = bmesh.new(); out.from_mesh(ev.to_mesh()); ev.to_mesh_clear()
    for ob in obs:
        me = ob.data; bpy.data.objects.remove(ob); bpy.data.meshes.remove(me)
    bmesh.ops.triangulate(out, faces=out.faces[:])
    if len(out.faces) > 6000:
        bmesh.ops.dissolve_degenerate(out, edges=out.edges[:], dist=1e-6)
    return out


def _sw(items, SW, name, group_parts):
    bms = []
    for col, bm_ in items:
        bms.append(bm_ if col is None else ck.set_uv_all(bm_, SW[col]))
    group_parts.append((name, ck.merge(bms), "custom", "custom"))


GRIP_Z = 0.060


def scan_switches(d, G):
    from mathutils.bvhtree import BVHTree
    V = [G + Vector(p_) for p_ in d["V"].astype(float)]
    tree = BVHTree.FromPolygons(V, d["T"].tolist())
    n = Vector((-0.26, -0.97, 0.0)).normalized()
    rt = Vector((0.97, -0.26, 0.0))
    if "yawd" in d.files:
        from mathutils import Matrix as _Mx
        _R = _Mx.Rotation(math.radians(float(d["yawd"][0])), 3, 'Z')
        n, rt = _R @ n, _R @ rt
        G = G + Vector([float(q) for q in d["shift"]])
    out = []
    for kind, u, z, r_ in (("castle", -0.0169, 0.175, 0.0062), ("round", 0.0180, 0.1775, 0.0052),
                           ("trim", 0.0006, 0.191, 0.0), ("red", 0.0069, 0.170, 0.0), ("pyramid", 0.0, 0.148, 0.0),
                           ("button", -0.0080, 0.160, 0.0030)):
        p0 = G + rt * u + Vector((0, 0, z)) + n * 0.05
        loc, nor, _, _ = tree.ray_cast(p0, -n, 0.2)
        if loc is None:
            print("  stick switch missed:", kind)
            continue
        nor = nor.normalized()
        if nor.dot(n) < 0:
            nor = -nor
        ex = Vector((1, 0, 0)) - nor * nor.x
        ex.normalize()
        F = ck.frame(ex, nor.cross(ex), nor)
        if kind == "castle":
            b_ = loc - nor * 0.0012
            for a_ in range(4):
                ang = math.radians(90 * a_)
                v_ = F @ Vector((math.cos(ang), math.sin(ang), 0))
                Fl = ck.frame(v_, nor.cross(v_).normalized(), nor)
                out.append(("darkgrey", ck.rbox(b_ + nor * 0.0035 + v_ * 0.0042, (0.0066, 0.0072, 0.0046), Fl, bevel=0.0016, seg=2)))
            out.append(("darkgrey", cyl(b_, nor, 0.0046, 0.0055, seg=16)))
            out.append(("black", cyl(b_ + nor * 0.0055, nor, 0.0020, 0.0006, seg=12)))
        elif kind == "round":
            out += hat(loc - nor * 0.0015, nor, r_, "round")
        elif kind == "trim":
            out.append(("darkgrey", ck.rbox(loc + nor * 0.0015, (0.012, 0.010, 0.0050), F, bevel=0.0014, seg=2)))
            for k in range(-3, 4):
                out.append(("black", ck.rbox(loc + nor * 0.0041 + F @ Vector((0, k * 0.0013, 0)), (0.0115, 0.0005, 0.0008), F, bevel=0)))
        elif kind == "red":
            out.append(("red", ck.rbox(loc + nor * 0.0008, (0.0050, 0.0040, 0.0024), F, bevel=0.0005, seg=1)))
        elif kind == "pyramid":
            for k in range(4):
                w_ = 0.0090 - k * 0.0021
                out.append(("darkgrey" if k % 2 == 0 else "black", ck.rbox(loc - nor * 0.0004 + nor * (k * 0.0011), (w_, w_, 0.0012), F, bevel=0.0003, seg=1)))
        elif kind == "button":
            out += button(loc - nor * 0.0005, nor, r_, "darkgrey")
    print(f"stick switches set into the scanned grip: {len(out)} parts")
    return out


def build_stick(O, SW):
    O = Vector(O)
    parts = []
    bits = []
    bits.append(("darkgrey", cyl(O + Vector((0, 0, -0.030)), (0, 0, 1), 0.040, 0.006, seg=40, r_top=0.038)))
    for i in range(8):
        a = math.radians(22.5 + 45 * i)
        bits.append(("metal", cyl(O + Vector((0.034 * math.cos(a), 0.034 * math.sin(a), -0.024)), (0, 0, 1), 0.0026, 0.0018, seg=6)))
    boot = []
    nb = 7
    for i in range(nb):
        f = i / (nb - 1)
        r_ = 0.0305 - 0.0050 * f ** 0.85 + (0.0036 if i % 2 == 0 else -0.0034) * (1 - 0.25 * f)
        boot.append((O + Vector((0, 0.002 * f, -0.004 + 0.045 * f)), r_, r_, 2.0))
    parts.append(("stick_boot", ck.modded(loft(boot, N=36), subsurf=1), "black", "pack"))
    ax = Vector((0, 0.05, 1)).normalized()
    import ctl_parts as _cp
    _cb, _cl = O + Vector((0, 0.003, 0.040)), 0.0176
    bits.append((None, _cp.uv_axis(gear(_cb, ax, 0.0288, 0.0125, teeth=64, depth=0.0009), "steel", _cb, ax, _cl, 0.0, 0.72)))
    Fc_ = frame_z(ax)
    for k in range(22):
        a_ = 2 * math.pi * k / 22
        v_ = Fc_ @ Vector((math.cos(a_), math.sin(a_), 0))
        bits.append((None, _cp.uv_axis(ck.rbox(O + Vector((0, 0.003, 0.0540)) + v_ * 0.0272, (0.0030, 0.0040, 0.0034),
                                               ck.frame(v_, ax.cross(v_).normalized(), ax), bevel=0.0006, seg=1), "steel", _cb, ax, _cl, 0.0, 1.0)))
    bits.append(("metal", cyl(O + Vector((0, 0.0034, 0.0525)), ax, 0.0255, 0.0040, seg=40)))
    bits.append(("black", cyl(O + Vector((0, 0.0036, 0.0562)), ax, 0.0240, 0.0060, seg=36, r_top=0.0225)))
    import os as _os
    _sgp = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "dev", "inputs", "stickgrip.npz")
    if _os.path.exists(_sgp) and _os.environ.get("OWN_STICK") is None:
        import numpy as _np
        _d = _np.load(_sgp)
        if "local" in _d.files and "own" not in _d.files:
            bits += scan_switches(_d, O + Vector((0, 0, GRIP_Z)))
        _sw(bits, SW, "stick_bits", parts)
        return parts
    spine = [(0.000, 0.002, 0.094, 0.0200, 0.0225, 2.3), (0.000, 0.003, 0.120, 0.0205, 0.0235, 2.3),
             (0.001, 0.006, 0.145, 0.0210, 0.0250, 2.4), (0.002, 0.011, 0.165, 0.0210, 0.0262, 2.4),
             (0.004, 0.017, 0.182, 0.0205, 0.0272, 2.5), (0.008, 0.026, 0.196, 0.0205, 0.0262, 2.6),
             (0.014, 0.040, 0.207, 0.0250, 0.0300, 2.8), (0.019, 0.051, 0.218, 0.0330, 0.0330, 3.0),
             (0.021, 0.057, 0.230, 0.0380, 0.0350, 3.2), (0.021, 0.060, 0.241, 0.0395, 0.0370, 3.3),
             (0.020, 0.059, 0.252, 0.0380, 0.0385, 3.3), (0.019, 0.057, 0.262, 0.0340, 0.0345, 3.1),
             (0.016, 0.054, 0.271, 0.0270, 0.0230, 2.7), (0.012, 0.049, 0.278, 0.0120, 0.0100, 2.2)]
    secs = [(O + Vector((cx, cy, zz)), a_, b_, e_, 0.0) for cx, cy, zz, a_, b_, e_ in spine]
    parts.append(("stick_grip", ck.modded(loft(secs, N=48), subsurf=1), "rubber", "pack"))

    def aft(z):
        for (x0, y0, z0, _, b0, _), (x1, y1, z1, _, b1, _) in zip(spine[:-1], spine[1:]):
            if z0 <= z <= z1:
                f = (z - z0) / (z1 - z0)
                return O + Vector((x0 * (1 - f) + x1 * f, (y0 - b0) * (1 - f) + (y1 - b1) * f, z))
        return O + Vector((spine[-1][0], spine[-1][1] - spine[-1][4], z))
    fn = Vector((0, -0.92, 0.39)).normalized()

    def on_face(u, z, lift=0.0004):
        return aft(z) + Vector((u, 0, 0)) + fn * lift
    Fc = ck.frame(Vector((1, 0, 0)), fn.cross(Vector((1, 0, 0))).normalized() * -1, fn)
    bits.append(("black", cyl(on_face(-0.008, 0.260, -0.001), fn, 0.0115, 0.0040, seg=28)))
    for a_ in range(4):
        ang = math.radians(90 * a_)
        v = Fc @ Vector((math.cos(ang), math.sin(ang), 0))
        Fl = ck.frame(v, fn.cross(v).normalized(), fn)
        bits.append(("darkgrey", ck.rbox(on_face(-0.008, 0.260, 0.0055) + v * 0.0048, (0.0075, 0.0080, 0.0050), Fl, bevel=0.0018, seg=2)))
    bits.append(("darkgrey", cyl(on_face(-0.008, 0.260, 0.0030), fn, 0.0052, 0.0050, seg=16)))
    bits.append(("darkgrey", ck.rbox(on_face(0.010, 0.270, 0.0040), (0.013, 0.010, 0.0080), Fc, bevel=0.0015, seg=2)))
    for k in range(-3, 4):
        bits.append(("black", ck.rbox(on_face(0.010, 0.270 + k * 0.0013, 0.0082), (0.0125, 0.0005, 0.0010), Fc, bevel=0)))
    bits.append(("red", ck.rbox(on_face(0.006, 0.2615, 0.0012), (0.0045, 0.0035, 0.0025), Fc, bevel=0.0005, seg=1)))
    bits.append(("black", ck.rbox(on_face(0.012, 0.249, 0.0045), (0.011, 0.016, 0.0090), Fc, bevel=0.0012, seg=2)))
    bits.append(("red", ck.rbox(on_face(0.012, 0.249, 0.0002), (0.0055, 0.0090, 0.0022), Fc, bevel=0.0004, seg=1)))
    bits += button(on_face(-0.006, 0.245), fn, 0.0036, "darkgrey")
    for k in range(4):
        w_ = 0.0095 - k * 0.0022
        bits.append(("darkgrey" if k % 2 == 0 else "black", ck.rbox(on_face(-0.003, 0.231, 0.0006 + k * 0.0011), (w_, w_, 0.0012), Fc, bevel=0.0003, seg=1)))
    bits.append(("black", cyl(on_face(-0.003, 0.231, -0.0012), fn, 0.0075, 0.0016, seg=20)))
    for u_, z_ in ((-0.013, 0.271), (-0.012, 0.246), (0.014, 0.238)):
        bits.append(("metal", cyl(on_face(u_, z_, -0.0002), fn, 0.0013, 0.0007, seg=8)))
    sh = O + Vector((0.006, 0.018, 0.190))
    bits.append(("black", cyl(sh, (0, 0, 1), 0.0225, 0.004, seg=32, r_top=0.0205)))
    up = Vector((0, -0.25, 1)).normalized()
    bits.append(("black", cyl(sh + Vector((-0.006, -0.015, 0.003)), up, 0.0030, 0.007, seg=12)))
    Fh = ck.frame(Vector((1, 0, 0)), up.cross(Vector((1, 0, 0))).normalized() * -1, up)
    bits.append(("darkgrey", ck.rbox(sh + Vector((-0.006, -0.016, 0.0125)), (0.0095, 0.0060, 0.0085), Fh, bevel=0.0012, seg=2)))
    for k in range(-2, 3):
        bits.append(("black", ck.rbox(sh + Vector((-0.006, -0.019, 0.0125 + k * 0.0015)), (0.0090, 0.0008, 0.0006), Fh, bevel=0)))
    bits.append(("metal", cyl(sh + Vector((0.009, -0.014, 0.003)), (0, 0, 1), 0.0040, 0.0020, seg=16)))
    bits += button(sh + Vector((0.009, -0.014, 0.005)), (0, 0, 1), 0.0026, "darkgrey", guard=False)
    for sx in (-1, 1):
        bits.append(("metal", cyl(O + Vector((sx * 0.0195, -0.012, 0.150)), (sx, 0, 0), 0.0013, 0.0008, seg=8)))
    Fpk = ck.frame(Vector((1, 0, 0)), Vector((0, 1, 0.15)).normalized(), Vector((0, -0.15, 1)).normalized())
    bits.append(("darkgrey", ck.rbox(O + Vector((0.016, 0.040, 0.140)), (0.026, 0.020, 0.0045), Fpk, bevel=0.002, seg=2)))
    bits.append(("metal", cyl(O + Vector((0.014, 0.032, 0.100)), (0, 0, 1), 0.0028, 0.040, seg=12)))
    bits.append(("black", ck.rbox(O + Vector((0.014, 0.032, 0.100)), (0.016, 0.014, 0.024), bevel=0.0015, seg=2)))
    bits += button(O + Vector((0.0, 0.0262, 0.128)), (0, 1, -0.1), 0.0050, "darkgrey")
    tr = bmesh.new()
    Ft = ck.frame(Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0)))
    ck.prism_profile(tr, [(0.000, 0.000), (0.010, 0.000), (0.020, 0.006), (0.026, 0.018), (0.028, 0.034), (0.022, 0.040), (0.016, 0.026), (0.008, 0.012)],
                     O + Vector((0, 0.034, 0.172)), Ft, 0.012)
    bits.append(("darkgrey", ck.modded(tr, bevel=0.0018, seg=2)))
    gd = bmesh.new()
    ck.prism_profile(gd, [(0.000, -0.004), (0.018, -0.004), (0.033, 0.008), (0.036, 0.026), (0.033, 0.026), (0.0305, 0.010), (0.017, -0.001), (0.000, -0.001)],
                     O + Vector((0, 0.034, 0.166)), Ft, 0.015)
    bits.append(("black", ck.modded(gd, bevel=0.0008, seg=1)))
    _sw(bits, SW, "stick_bits", parts)
    return parts


THR_LABELS = []


THR_TRAVEL, THR_RADIUS = 0.040, 0.60
THR_Y_OFF = 0.036
SLOT_Y, SLOT_L = 0.0290, 0.158
LIFT_Y = -0.0720


def build_throttle(C, SW):
    C = Vector(C)
    moving, fixed = [], []
    mb, fb = [], []
    del THR_LABELS[:]
    GX = 0.032
    QY, QL = 0.031, 0.236
    plate = ck.rbox(C + Vector((0, QY, 0.0025)), (0.128, QL, 0.005), bevel=0.0016, seg=2)
    fixed.append(("thr_plate", plate, "pedgrey", "pack"))
    PZ = 0.0050
    for sx in (-1, 1):
        x_ = sx * GX
        fb.append(("ltgrey", ck.rbox(C + Vector((x_, QY, PZ + 0.0009)), (0.059, QL - 0.010, 0.0018), bevel=0.0005, seg=1)))
        fb.append(("darkgrey", ck.rbox(C + Vector((x_, SLOT_Y, PZ + 0.0019)), (0.0170, SLOT_L + 0.006, 0.0006), bevel=0.0002, seg=1)))
        fb.append(("black", ck.rbox(C + Vector((x_, SLOT_Y, PZ + 0.0022)), (0.0125, SLOT_L, 0.0006), bevel=0.0002, seg=1)))
        for ex in (-1, 1):
            for k in range(14):
                q = C + Vector((x_ + ex * 0.0252, -0.060 + k * 0.0140, PZ + 0.0018))
                fb.append(("olive", cyl(q, (0, 0, 1), 0.0021, 0.0007, seg=10, r_top=0.0017)))
                fb.append(("black", ck.rbox(q + Vector((0, 0, 0.00075)), (0.0032, 0.0005, 0.0002), ck.frame(Vector((math.cos(k * 1.7 + sx), math.sin(k * 1.7 + sx), 0)), Vector((-math.sin(k * 1.7 + sx), math.cos(k * 1.7 + sx), 0)), Vector((0, 0, 1))), bevel=0)))
            for ey in (-1, 1):
                q = C + Vector((x_ + ex * 0.0165, QY + ey * (QL / 2 - 0.0115), PZ + 0.0018))
                fb.append(("darkgrey", cyl(q, (0, 0, 1), 0.0044, 0.0010, seg=18)))
                fb.append(("metal", cyl(q + Vector((0, 0, 0.0010)), (0, 0, 1), 0.0036, 0.0008, seg=18, r_top=0.0030)))
                fb.append(("black", ck.rbox(q + Vector((0, 0, 0.0019)), (0.0052, 0.0008, 0.0002), ck.frame(Vector((0.7, 0.7 * ex * ey, 0)).normalized(), Vector((-0.7 * ex * ey, 0.7, 0)).normalized(), Vector((0, 0, 1))), bevel=0)))
        for yy, word, tick in ((0.101, "MAX RHT", 0.007), (0.084, "MIN RHT", 0.007), (0.064, "MAX DRY", 0.007),
                               (-0.038, "IDLE", 0.005), (-0.050, "HP SHUT", 0.005)):
            fb.append(("white", ck.rbox(C + Vector((x_ + 0.0062 + tick / 2 + 0.0008, yy - 0.0030, PZ + 0.0019)), (tick, 0.00045, 0.0002), bevel=0)))
            THR_LABELS.append(dict(pos=[C.x + x_ + 0.0152, C.y + yy, C.z + PZ + 0.0019], r=[1.0, 0.0, 0.0], u=[0.0, 1.0, 0.0], n=[0.0, 0.0, 1.0],
                                   text=word.replace(" ", "_") if False else word, cap=0.0015, font="FONT", spacing=1.35, col=[0.89, 0.90, 0.86], seen=True))
        q = C + Vector((x_ + 0.0190, LIFT_Y, PZ + 0.0018))
        fb.append(("darkgrey", cyl(q, (0, 0, 1), 0.0062, 0.0075, seg=20)))
        fb.append(("ltgrey", cyl(q + Vector((0, 0, 0.0075)), (0, 0, 1), 0.0050, 0.0150, seg=20)))
        fb.append(("metal", cyl(q + Vector((0, 0, 0.0100)), (0, 0, 1), 0.0054, 0.0012, seg=20)))
        bl = Vector((0.0, -0.80, 0.60))
        Fb = ck.frame(Vector((1, 0, 0)), bl, Vector((0, 0.60, 0.80)))
        fb.append(("ltgrey", ck.rbox(q + Vector((0, 0, 0.0222)) + bl * 0.0070, (0.0105, 0.0220, 0.0030), Fb, bevel=0.0010, seg=2)))
    _sw(fb, SW, "thr_fixed_bits", fixed)

    Y_OFF = THR_Y_OFF
    XO0, XO1 = -0.0450, 0.0165
    XI0, XI1 = 0.0185, 0.0495
    BY, BZ, BR = 0.0400, 0.0595, 0.0165
    side_o = [(-0.041, 0.012), (-0.044, 0.044), (-0.053, 0.062), (-0.0555, 0.080), (-0.052, 0.094), (-0.043, 0.103),
              (-0.030, 0.1075), (-0.019, 0.1055), (-0.010, 0.100), (-0.0055, 0.093), (-0.0075, 0.088), (-0.0135, 0.0835),
              (-0.0155, 0.079), (0.008, 0.064), (0.018, 0.0635)]
    side_o += [(BY + BR * math.cos(math.radians(a_)), BZ + BR * math.sin(math.radians(a_))) for a_ in (150, 120, 90, 60, 30, 0, -30, -60, -90, -115)]
    side_o += [(0.031, 0.040), (0.030, 0.012)]
    top_o = [(XO0 + 0.004, -0.0560), (XO1 - 0.0045, -0.0560), (XO1, -0.049), (XO1, 0.054), (XO1 - 0.003, 0.058),
             (XO0 + 0.006, 0.058), (XO0, 0.050), (XO0, -0.049)]
    back_o = [(XO0, 0.012), (-0.0175, 0.012), (-0.0175, 0.040), (XO1, 0.056), (XO1, 0.090), (XO1 - 0.0045, 0.101),
              (0.002, 0.1065), (-0.030, 0.1065), (XO0 + 0.005, 0.101), (XO0, 0.090)]
    side_i = [(-0.036, 0.012), (-0.038, 0.045), (-0.050, 0.060), (-0.056, 0.078), (-0.054, 0.093), (-0.046, 0.104),
              (-0.034, 0.109), (-0.022, 0.1075), (-0.013, 0.101), (-0.008, 0.091), (-0.006, 0.080), (0.000, 0.076),
              (0.026, 0.074), (0.034, 0.068), (0.036, 0.056), (0.032, 0.046), (0.030, 0.012)]
    top_i = [(XI0 + 0.003, -0.056), (XI1 - 0.003, -0.056), (XI1, -0.050), (XI1, 0.030), (XI1 - 0.004, 0.036),
             (XI0 + 0.004, 0.036), (XI0, 0.030), (XI0, -0.050)]
    back_i = [(0.0235, 0.012), (0.0445, 0.012), (0.0445, 0.040), (XI1, 0.050), (XI1, 0.094), (XI1 - 0.004, 0.104),
              (0.038, 0.109), (0.030, 0.109), (XI0 + 0.004, 0.104), (XI0, 0.094), (XI0, 0.050), (0.0235, 0.040)]
    for gi, (side, top, back) in enumerate(((side_o, top_o, back_o), (side_i, top_i, back_i))):
        dr = silhouette_body(side, top, back, voxel=0.0012, smooth=(0.6, 20), ratio=0.22)
        bmesh.ops.translate(dr, vec=C + Vector((0, Y_OFF, 0.0)), verts=dr.verts[:])
        moving.append((f"thr_grip_{gi}", dr, "gripgrey", "pack"))
    G = C + Vector((0, Y_OFF, 0.0))
    X1 = Vector((1, 0, 0))
    for xs, xa, xb in ((-GX, XO0, -0.0175), (GX, 0.0235, 0.0445)):
        mb.append(("black", ck.rbox(G + Vector((xs, 0.0, 0.0075)), (0.0105, 0.058, 0.013), bevel=0.0010, seg=1)))
        qc = G + Vector((xa, 0.002, 0.028))
        mb.append(("black", ck.rbox(qc - X1 * 0.0002, (0.0012, 0.044, 0.017), bevel=0.0003, seg=1)))
        mb.append(("olive", ck.rbox(qc - X1 * 0.0014, (0.0020, 0.036, 0.0105), bevel=0.0005, seg=1)))
        mb.append(("olive", ck.rbox(qc - X1 * 0.0030, (0.0022, 0.027, 0.0060), bevel=0.0005, seg=1)))
        for ey in (-1, 1):
            mb.append(("metal", cyl(qc + Vector((-0.0008, ey * 0.0200, 0)), -X1, 0.0016, 0.0016, seg=8)))
            qb = G + Vector((xb, ey * 0.0085, 0.027))
            mb.append(("darkgrey", cyl(qb, X1, 0.0052, 0.0008, seg=18)))
            mb.append(("chrome", cyl(qb + X1 * 0.0008, X1, 0.0040, 0.0030, seg=6)))
    bc = G + Vector((XO1 - 0.0085, BY, BZ))
    mb.append(("darkgrey", gear(bc, X1, BR + 0.0012, 0.0062, teeth=52, depth=0.0007)))
    mb.append(("black", cyl(bc + X1 * 0.0062, X1, BR - 0.0010, 0.0016, seg=32, r_top=BR - 0.0040)))
    nb = Vector((0.0, 0.588, 0.809))
    for xbtn in (-0.0260, -0.0040):
        qb = G + Vector((xbtn, -0.0030, 0.0715))
        mb.append(("black", cyl(qb - nb * 0.0010, nb, 0.0082, 0.0042, seg=24, r_top=0.0074)))
        mb.append(("darkgrey", cyl(qb + nb * 0.0026, nb, 0.0056, 0.0026, seg=20, r_top=0.0046)))
    qt = G + Vector((XO0, -0.0320, 0.0930))
    mb.append(("metal", cyl(qt + X1 * 0.0010, -X1, 0.0068, 0.0036, seg=6)))
    mb.append(("darkgrey", cyl(qt - X1 * 0.0026, -X1, 0.0044, 0.0016, seg=14)))
    tl = Vector((-0.88, 0.10, 0.46)).normalized()
    mb.append(("black", cyl(qt - X1 * 0.0036, tl, 0.0022, 0.0200, seg=12, r_top=0.0030)))
    mb.append(("black", cyl(qt - X1 * 0.0036 + tl * 0.0200, tl, 0.0030, 0.0016, seg=12, r_top=0.0018)))
    nd = Vector((0.0, 0.957, 0.290)).normalized()
    qd = G + Vector((0.0340, -0.0100, 0.0935))
    mb.append(("black", cyl(qd - nd * 0.0015, nd, 0.0112, 0.0040, seg=28, r_top=0.0104)))
    mb.append(("darkgrey", cyl(qd + nd * 0.0025, nd, 0.0090, 0.0010, seg=28)))
    Fd = frame_z(nd, (1, 0, 0))
    for rr in (0.0074, 0.0050):
        mb.append(("black", gear(qd + nd * 0.0035, nd, rr, 0.0006, teeth=24, depth=0.0003)))
        mb.append(("darkgrey", cyl(qd + nd * 0.0035, nd, rr - 0.0010, 0.0007, seg=24)))
    for k in range(8):
        a_ = math.radians(45 * k + 22.5)
        v_ = Fd @ Vector((math.cos(a_), math.sin(a_), 0))
        w_ = Fd @ Vector((-math.sin(a_), math.cos(a_), 0))
        mb.append(("black", ck.rbox(qd + nd * 0.0044 + v_ * 0.0050, (0.0072, 0.0007, 0.0006), ck.frame(v_, w_, nd), bevel=0)))
    mb.append(("black", cyl(qd + nd * 0.0042, nd, 0.0022, 0.0012, seg=14, r_top=0.0016)))
    qk = G + Vector((0.0365, 0.0110, 0.0750))
    ak = Vector((0.0, 0.10, 1.0)).normalized()
    mb.append(("darkgrey", cyl(qk - ak * 0.0010, ak, 0.0066, 0.0030, seg=6)))
    mb.append(("black", cyl(qk + ak * 0.0020, ak, 0.0046, 0.0092, seg=18, r_top=0.0041)))
    mb.append(("darkgrey", gear(qk + ak * 0.0080, ak, 0.0048, 0.0030, teeth=18, depth=0.0004)))
    mb += button(G + Vector((0.0260, 0.0230, 0.0735)), (0, 0.15, 1), 0.0030, "darkgrey")
    ah = Vector((0.90, -0.40, 0.15)).normalized()
    qh = G + Vector((XI1 - 0.0015, -0.0400, 0.0700))
    mb.append(("darkgrey", cyl(qh, ah, 0.0072, 0.0030, seg=6)))
    mb.append(("black", cyl(qh + ah * 0.0030, ah, 0.0034, 0.0050, seg=12)))
    Fh = frame_z(ah, (0, 0, 1))
    for k in range(4):
        a_ = math.radians(90 * k)
        v_ = Fh @ Vector((math.cos(a_), math.sin(a_), 0))
        w_ = Fh @ Vector((-math.sin(a_), math.cos(a_), 0))
        mb.append(("darkgrey", ck.rbox(qh + ah * 0.0095 + v_ * 0.0042, (0.0078, 0.0020, 0.0060), ck.frame(v_, w_, ah), bevel=0.0006, seg=1)))
    mb.append(("black", cyl(qh + ah * 0.0080, ah, 0.0030, 0.0052, seg=12, r_top=0.0022)))
    mb += hat(G + Vector((XI1 - 0.0008, -0.0150, 0.0600)), (1, 0, 0), 0.0052, "ribbed", hint=(0, 0, 1))
    _sw(mb, SW, "thr_bits", moving)
    return moving, fixed


def build_pedals(floor_z, wall_y, SW, x_c=0.17):
    out = {"L": [], "R": [], "fixed": []}
    hinges = {}
    fixed_bits = []
    HY, HZ = wall_y - 0.215, floor_z + 0.466
    Xa, Ya, Za = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
    Fp = ck.frame(Xa, Za, -Ya)
    T = 0.006
    RAIL_X, RAIL_W = 0.039, 0.016
    for sx in (-1, 1):
        key = "L" if sx < 0 else "R"
        X = sx * x_c
        anchor = Vector((X, HY, HZ))
        hinges[key] = anchor.copy()
        bits = []
        for dx in (-RAIL_X, RAIL_X):
            bits.append(("darkgrey", ck.rbox(Vector((X + dx, HY, HZ - 0.150)), (RAIL_W, 0.270, T), Fp, bevel=0.0018, seg=2)))
        bits.append(("darkgrey", ck.rbox(Vector((X, HY, HZ - 0.002)), (2 * RAIL_X + RAIL_W, 0.034, 0.028), Fp, bevel=0.004, seg=2)))
        rungs = ((-0.110, 0.020), (-0.200, 0.020))
        for dz_, hh in rungs:
            bits.append(("darkgrey", ck.rbox(Vector((X, HY, HZ + dz_)), (2 * RAIL_X, hh, T), Fp, bevel=0.0015, seg=1)))
        edges = [HZ - 0.019, HZ - 0.100, HZ - 0.120, HZ - 0.190, HZ - 0.210, HZ - 0.275]
        xi = RAIL_X - RAIL_W / 2
        c_ = 0.011
        for k_ in range(3):
            for zz, sz in ((edges[2 * k_], -1), (edges[2 * k_ + 1], 1)):
                for sxx in (-1, 1):
                    b = bmesh.new()
                    ck.prism_profile(b, [(0, 0), (-sxx * c_, 0), (0, sz * c_)], Vector((X + sxx * xi, HY, zz)), Fp, T * 0.92)
                    bmesh.ops.recalc_face_normals(b, faces=b.faces[:])
                    bits.append(("darkgrey", b))
        tilt = math.radians(10)
        up_ = Vector((0, math.sin(tilt), math.cos(tilt)))
        nrm = Vector((0, -math.cos(tilt), math.sin(tilt)))
        F = ck.frame(Xa, up_, nrm)
        pc = Vector((X, HY - 0.004, HZ - 0.322))
        out[key].append((f"pedal_{key}", ck.rbox(pc, (0.096, 0.096, 0.012), F, bevel=0.004, seg=2), "rubber", "pack"))
        for k in range(-2, 3):
            bits.append(("black", ck.rbox(pc + up_ * (k * 0.0165) + nrm * 0.0068, (0.084, 0.0070, 0.0030), F, bevel=0.0008, seg=1)))
        bits.append(("darkgrey", ck.rbox(pc - up_ * 0.049 + nrm * 0.009, (0.096, 0.008, 0.020), F, bevel=0.002, seg=1)))
        for dx in (-RAIL_X, RAIL_X):
            bits.append(("darkgrey", ck.rbox(Vector((X + dx, HY + 0.004, HZ - 0.310)), (RAIL_W, 0.060, T), Fp, bevel=0.0015, seg=1)))
            bits.append(("metal", cyl(Vector((X + dx, HY - 0.0030, HZ - 0.283)), -Ya, 0.0036, 0.0022, seg=6)))
        _sw(bits, SW, f"pedal_bits_{key}", out[key])
        fixed_bits.append(("darkgrey", cyl(Vector((X - 0.058, HY, HZ)), Xa, 0.0105, 0.116, seg=16)))
        for dx in (-0.052, 0.052):
            fixed_bits.append(("darkgrey", ck.rbox(Vector((X + dx, HY, HZ + 0.020)), (0.010, 0.026, 0.054), bevel=0.002, seg=1)))
    _sw(fixed_bits, SW, "pedal_fixed_bits", out["fixed"])
    return out, hinges


def build_gear_lever(Q, n, SW):
    Q = Vector(Q); n = Vector(n).normalized()
    ex = Vector((1, 0, 0)); ey = n.cross(ex).normalized(); ex = ey.cross(n).normalized()
    F = ck.frame(ex, ey, n)
    fixed, moving = [], []
    fb = [("darkgrey", ck.rbox(Q + n * 0.002, (0.030, 0.074, 0.004), F, bevel=0.0012, seg=1)),
          ("black", ck.rbox(Q + n * 0.0042, (0.009, 0.058, 0.0010), F, bevel=0.0003, seg=1))]
    for sy in (-1, 1):
        fb.append(("chrome", cyl(Q + ey * sy * 0.032 + ex * 0.010 + n * 0.004, n, 0.0022, 0.0009, seg=8)))
        fb.append(("chrome", cyl(Q + ey * sy * 0.032 - ex * 0.010 + n * 0.004, n, 0.0022, 0.0009, seg=8)))
    fb.append(("white", ck.rbox(Q + ey * 0.024 + ex * 0.0105 + n * 0.0042, (0.006, 0.0012, 0.0006), F, bevel=0, seg=1)))
    fb.append(("green", ck.rbox(Q - ey * 0.024 + ex * 0.0105 + n * 0.0042, (0.006, 0.0012, 0.0006), F, bevel=0, seg=1)))
    _sw(fb, SW, "gearlever_fixed", fixed)
    mb = [("ltgrey", cyl(Q - n * 0.004, n, 0.0055, 0.050, seg=14)),
          ("ltgrey", cyl(Q + n * 0.052 - ex * 0.010, ex, 0.0215, 0.020, seg=36)),
          ("darkgrey", cyl(Q + n * 0.052 - ex * 0.0104, ex, 0.0222, 0.0030, seg=36)),
          ("darkgrey", cyl(Q + n * 0.052 + ex * 0.0074, ex, 0.0222, 0.0030, seg=36)),
          ("metal", cyl(Q + n * 0.052 - ex * 0.0108, ex, 0.0060, 0.0216, seg=16)),
          ("ltgrey", cyl(Q + n * 0.026 - ey * 0.006, -ey, 0.0060, 0.004, seg=14)),
          ("keyblue", cyl(Q + n * 0.026 - ey * 0.010, -ey, 0.0034, 0.0016, seg=12))]
    _sw(mb, SW, "gearlever_bits", moving)
    return moving, fixed
