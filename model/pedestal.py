import math

import numpy as np

SLOPE = 0.60
PANEL_SLOPE, PANEL_Z0, PANEL_Y0 = 0.9335, 0.5072, 7.1689
YF, YC, YA = 7.1695, 7.1640, 7.038
W, WA = 0.1065, 0.064
PANEL_TOP = (7.2705, 0.5980)
CUP_Y, R_CUP, D_CUP = 7.100, 0.046, 0.016
WELL_X, WELL_Y, WELL_N = 0.056, 0.050, 5.0


def well(k, n, grow=0.0):
    t = 2 * math.pi * k / n
    ct, st = math.cos(t), math.sin(t)
    return (math.copysign(abs(ct) ** (2 / WELL_N), ct) * (WELL_X + grow), math.copysign(abs(st) ** (2 / WELL_N), st) * (WELL_Y + grow))


def zpanel(y):
    return PANEL_Z0 + (y - PANEL_Y0) * PANEL_SLOPE


def ztop(y):
    return zpanel(YF) + (y - YF) * SLOPE


def shell_remove_mask(P):
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    return ((np.abs(x) <= 0.1045) & (z >= 7.040) & (z <= 7.1697) & (y >= 0.170) & (y <= 0.5036)).all(1)


def _outline(w, wa, ya, grow=0.0):
    return [(-w - grow, YF), (w + grow, YF), (w + grow, YC), (wa + grow * 0.7, ya - grow), (-wa - grow * 0.7, ya - grow), (-w - grow, YC)]


def build(ck, sw):
    import bmesh
    from mathutils import Vector
    from cockpit_hotas import cyl
    up = Vector((0, -SLOPE, 1)).normalized()
    eyp = Vector((0, 1, SLOPE)).normalized()
    C0 = Vector((0, CUP_Y, ztop(CUP_Y)))
    T_COVER = 0.006
    o1 = _outline(W, WA, YA)
    FLARE, YS = 0.030, YC - 0.050
    o2 = [(-W, YF), (W, YF), (W + FLARE, YS), (W + FLARE, YA), (-W - FLARE, YA), (-W - FLARE, YS)]
    o3 = [(-W - 0.006, YF), (W + 0.006, YF), (W + FLARE + 0.006, YS), (W + FLARE + 0.006, YA - 0.004), (-W - FLARE - 0.006, YA - 0.004), (-W - FLARE - 0.006, YS)]
    rings = [[(x, y, ztop(y) - T_COVER) for x, y in o1], [(x, y, ztop(y) - 0.012) for x, y in o1],
             [(x, y, ztop(YA) - 0.075) for x, y in o2], [(x, y, 0.215) for x, y in o2], [(x, y, 0.196) for x, y in o3],
             [(x, y, 0.172) for x, y in o3]]
    b = bmesh.new()
    vs = [[b.verts.new(p) for p in r] for r in rings]
    for i in range(len(vs) - 1):
        for k in range(6):
            k2 = (k + 1) % 6
            b.faces.new((vs[i][k], vs[i][k2], vs[i + 1][k2], vs[i + 1][k]))
    ftop = b.faces.new(vs[0])
    b.faces.new(vs[-1][::-1])
    bmesh.ops.recalc_face_normals(b, faces=b.faces[:])
    bmesh.ops.delete(b, geom=[ftop], context='FACES_ONLY')
    body = ck.modded(b, bevel=0.0022, seg=2, angle=18); b.free()
    bk = bmesh.new()
    xw = W + 0.0003
    y0, y1 = YF - 0.004, PANEL_TOP[0] - 0.001
    zt0, zt1 = zpanel(y0) - 0.0006, zpanel(y1) - 0.0006
    q = [bk.verts.new(p) for p in ((-xw, y0, 0.175), (xw, y0, 0.175), (xw, y1, 0.175), (-xw, y1, 0.175),
                                   (-xw, y0, zt0), (xw, y0, zt0), (xw, y1, zt1), (-xw, y1, zt1))]
    for f in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bk.faces.new([q[i] for i in f])
    bmesh.ops.recalc_face_normals(bk, faces=bk.faces[:])
    back = ck.modded(bk, bevel=0.0022, seg=2, angle=18); bk.free()
    co = _outline(W, WA, YA, grow=0.0)
    co[0] = (co[0][0], YF); co[1] = (co[1][0], YF)
    cb = bmesh.new()
    ov = [cb.verts.new((x, y, ztop(y))) for x, y in co]
    NS = 72
    iv = [cb.verts.new(C0 + Vector((1, 0, 0)) * well(k, NS)[0] + eyp * well(k, NS)[1]) for k in range(NS)]
    ed = [cb.edges.new((ov[i], ov[(i + 1) % len(ov)])) for i in range(len(ov))]
    ed += [cb.edges.new((iv[i], iv[(i + 1) % NS])) for i in range(NS)]
    bmesh.ops.triangle_fill(cb, use_beauty=True, use_dissolve=False, edges=ed)
    ext = bmesh.ops.extrude_face_region(cb, geom=cb.faces[:])
    bmesh.ops.translate(cb, vec=-up * T_COVER, verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(cb, faces=cb.faces[:])
    cover = ck.modded(cb, bevel=0.0012, seg=2, angle=30); cb.free()
    cw = bmesh.new()
    r0, r1 = [], []
    for k in range(NS):
        d = Vector((1, 0, 0)) * well(k, NS)[0] + eyp * well(k, NS)[1]
        d1 = Vector((1, 0, 0)) * well(k, NS, -0.0022)[0] + eyp * well(k, NS, -0.0022)[1]
        r0.append(cw.verts.new(C0 + d - up * (T_COVER - 0.0005)))
        r1.append(cw.verts.new(C0 + d1 - up * D_CUP))
    for k in range(NS):
        k2 = (k + 1) % NS
        f = cw.faces.new((r0[k], r1[k], r1[k2], r0[k2]))
    cw.faces.new(r1)
    cw.normal_update()
    for f in cw.faces:
        c = f.calc_center_median()
        want = (C0 - up * (D_CUP * 0.5) - c) if len(f.verts) == 4 else up
        if f.normal.dot(want) < 0:
            f.normal_flip()
    rb = bmesh.new()
    RI, RO, RH = -0.0006, 0.0042, 0.0014
    rr = []
    for rad, hh_ in ((RI, -0.0015), (RI, RH), (RO, RH), (RO, -0.0005)):
        rr.append([rb.verts.new(C0 + Vector((1, 0, 0)) * well(k, NS, rad)[0] + eyp * well(k, NS, rad)[1] + up * hh_) for k in range(NS)])
    for ra_, rb_ in zip(rr[:-1], rr[1:]):
        for k in range(NS):
            k2 = (k + 1) % NS
            rb.faces.new((ra_[k], ra_[k2], rb_[k2], rb_[k]))
    bmesh.ops.recalc_face_normals(rb, faces=rb.faces[:])
    rb.normal_update()
    _f0 = max(rb.faces, key=lambda f_: f_.calc_center_median().dot(up))
    if _f0.normal.dot(up) < 0:
        bmesh.ops.reverse_faces(rb, faces=rb.faces[:])
    rim = ck.modded(rb, bevel=0.0009, seg=2, angle=30); rb.free()
    parts = [("ped_body", ck.merge([body, back, cover, cw, rim]), "pedmould", "pack")]
    bits = []

    def top_pt(x, y, h=0.0):
        return Vector((x, y, ztop(y))) + up * h
    for sx in (-1, 1):
        for y in (CUP_Y + WELL_Y * eyp.y + 0.0085,):
            bits.append(sw(cyl(top_pt(sx * 0.050, y), up, 0.0030, 0.0011, seg=12, r_top=0.0024), "metal"))
            bits.append(sw(ck.rbox(top_pt(sx * 0.050, y, 0.00118), (0.0042, 0.0007, 0.0003), ck.frame(Vector((0.8, 0.6 * eyp.y, 0.6 * eyp.z)).normalized(), up.cross(Vector((0.8, 0.6 * eyp.y, 0.6 * eyp.z)).normalized()), up), bevel=0), "black"))
    bits.append(sw(cyl(Vector((0, CUP_Y, 0.405)), Vector((0, 0, 1)), 0.0372, 0.0525, seg=36, r_top=0.0348), "black"))
    _sl = Vector((0.8, 0.6 * eyp.y, 0.6 * eyp.z)).normalized()
    for x in (-0.034, 0.0, 0.034):
        y = CUP_Y - WELL_Y * eyp.y - 0.0078
        bits.append(sw(cyl(top_pt(x, y), up, 0.0030, 0.0011, seg=12, r_top=0.0024), "metal"))
        bits.append(sw(ck.rbox(top_pt(x, y, 0.00118), (0.0042, 0.0007, 0.0003), ck.frame(_sl, up.cross(_sl), up), bevel=0), "black"))
    parts.append(("ped_bits", ck.merge(bits), "custom", "custom"))
    return parts
