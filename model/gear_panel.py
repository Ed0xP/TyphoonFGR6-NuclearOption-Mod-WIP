import math

import numpy as np

import panelkit as pk

A_U = np.array([-0.2897, 0.4714, 7.0991])
N_U = np.array([0.1392, 0.6002, -0.7877])
EU_U = np.array([-0.9847, 0.0, -0.1740])
EV_U = np.array([-0.1044, 0.7999, 0.5910])
FACE_U = np.array([[-0.2897, 0.4714, 7.0991], [-0.5287, 0.4923, 7.0728], [-0.5228, 0.5721, 7.1339],
                   [-0.4571, 0.6538, 7.2085], [-0.3809, 0.6567, 7.2173], [-0.2897, 0.6667, 7.2462]])
TOP = 0.006
FR = pk.Frame(A_U, -EU_U, EV_U, top=TOP)
OUTLINE = [(0, 0), (-240, 26), (-223.5, 125.5), (-146, 228), (25.6, 243)]
WIN = (-247.0, 33.0, -15.0, 265.0)
C_PANEL = pk.PANEL_DARK
C_SUBPL = C_PANEL * 0.86

SLOT = (-44.0, 118.0, 46.0, 92.0, 10.0)
SLOT_Z = -7.0
LAMPS = [(-58.0, 150.0), (-44.0, 150.0), (-30.0, 150.0)]
HINGE = (-44.0, 112.0, -4.0)
LEVER_MID = 11.0
CAP = (-14.5, 210.0)
CAP_R = (30.0, 22.6, 21.4, 32.5, 7.0, 20.6)
EARS = [(CAP[0] + CAP_R[3] * math.cos(math.radians(a)), CAP[1] + CAP_R[3] * math.sin(math.radians(a))) for a in (45, 135, 225, 315)]
HAZ_JETT = (-110.0, 150.0, 44.0, 34.0)
JETT_GUARD = (-112.0, 149.0)
JETT_KEY = (-120.0, 98.0)
PROG = (-152.0, 100.0)
FRIC = (-180.0, 82.0)
HAZ_GEAR = (-191.0, 39.0, 30.0, 38.0)
LAND = (-112.0, 36.0)
SCREWS = [(-78, 60), (-36, 56), (-8, 8), (-120, 14), (-228, 33), (-215, 112), (-150, 210), (-98, 222), (5, 118)]
GREEN = (0.45, 1.0, 0.5)


def _b(v):
    return np.array([v[0], v[2], v[1]], float)


def pt(s, t, h=0.0):
    return FR.pt(-s, t, h * 1000.0)


def footprint(p):
    x, y, l = FR.local(p)
    return -246 < x < 30 and -6 < y < 248 and -12 < l < 50


def shell_remove_mask(P):
    d = P - A_U
    s, t, l = d @ EU_U * 1000, d @ EV_U * 1000, d @ N_U
    dist = np.linalg.norm(P[:, :, None, :] - FACE_U[None, None, :, :], axis=3).min(2)
    face = (dist < 0.0015).all(1)
    socket = ((s > 8) & (s < 92) & (t > 48) & (t < 152) & (l > -0.02) & (l < 0.095)).all(1)
    return face | socket


def hinge_unity():
    a = _b(FR.pt(*HINGE))
    return a, a + EU_U


def surface_line():
    a, b = hinge_unity()
    return "cockpit_gearlever %.4f %.4f %.4f %.4f %.4f %.4f gearlever" % (a[0], a[1], a[2], b[0], b[1], b[2])


def labels():
    L = [FR.label("OPEN", CAP[0], CAP[1] + 14.0, 3.0, z=5.0, col=(0.80, 0.81, 0.78)),
         FR.label("UP", -8.0, 146.0, 2.3), FR.label("DOWN", -7.0, 84.0, 2.3),
         FR.label("EMGY|JETT", HAZ_JETT[0], HAZ_JETT[1] + HAZ_JETT[3] / 2 + 6.0, 2.2),
         FR.label("SEL JETT", -122.0, 126.0, 2.2),
         FR.label("PROG", PROG[0], PROG[1] + 12.5, 2.0), FR.label("TANKS", PROG[0], PROG[1] - 13.0, 2.0),
         FR.label("JETT", JETT_KEY[0], JETT_KEY[1], 3.3, z=8.4, col=GREEN),
         FR.label("THROTTLE|FRIC", FRIC[0] + 6.0, FRIC[1] + 17.0, 2.0),
         FR.label("EMGY|GEAR", HAZ_GEAR[0] + 1.0, HAZ_GEAR[1] + HAZ_GEAR[3] / 2 + 6.0, 2.0),
         FR.label("RSET", -163.0, 50.0, 2.0), FR.label("NORM", -163.0, 39.0, 2.0), FR.label("DOWN", -163.0, 28.0, 2.0),
         FR.label("LAND", LAND[0], LAND[1] + 15.5, 2.1), FR.label("OFF", LAND[0] + 17.0, LAND[1], 2.1),
         FR.label("TAXI", LAND[0], LAND[1] - 15.0, 2.1)]
    return L


def build(ck, sw):
    import bmesh
    from cockpit_hotas import cyl, gear
    b = pk.Builder(ck, sw, FR, WIN)
    Xv, Yv, Nv = b.Xv, b.Yv, b.Nv
    slot = pk.rrect_pts(*SLOT)
    b.prism(OUTLINE, -(TOP * 1000 + 14.0), 0.0, bevel=1.5, holes=[slot])
    b.box(SLOT[0], SLOT[1], SLOT_Z - 0.4, (SLOT[2] + 2, SLOT[3] + 2, 0.8), "black", bevel=0)
    a = math.radians(25)
    ez = (Nv * math.cos(a) - Yv * math.sin(a)).normalized()
    Fw = ck.frame(Xv, (Yv * math.cos(a) + Nv * math.sin(a)).normalized(), ez)
    for x, y in LAMPS:
        c = b.P(x, y, -1.8)
        b.bits.append(sw(ck.rbox(c, (0.0118, 0.0135, 0.0095), Fw, bevel=0.0012, seg=2), "darkgrey"))
        b.bits.append(sw(cyl(c + ez * 0.00475, ez, 0.0047, 0.0005, seg=20), "black"))
        b.bits.append(sw(cyl(c + ez * 0.0052, ez, 0.0036, 0.0011, seg=18, r_top=0.0028), "green"))
    b.cyl(SLOT[0], 108.0, SLOT_Z, 16.0, 3.0, "black", seg=28, r_top=15.0)
    b.cyl(SLOT[0], 108.0, SLOT_Z + 3.0, 14.0, 5.0, "black", seg=28, r_top=10.5)
    b.cyl(SLOT[0], 108.0, SLOT_Z + 8.0, 10.0, 3.0, "black", seg=24, r_top=7.5)
    for sx in (-1, 1):
        b.screw(SLOT[0] + sx * 15.0, 131.0, SLOT_Z, r=2.2, ang=0.4 + sx)
    fixed_bits, b.bits = b.bits, []
    H = b.P(*HINGE)
    m = math.radians(LEVER_MID)
    d0 = (Nv * math.cos(m) - Yv * math.sin(m)).normalized()
    b.bits.append(sw(cyl(H, d0, 0.0046, 0.026, seg=14, r_top=0.0040), "darkgrey"))
    b.bits.append(sw(cyl(H + d0 * 0.010, d0, 0.0068, 0.006, seg=18, r_top=0.0052), "black"))
    Cw = H + d0 * 0.036
    wb = bmesh.new()
    ck.cylinder(wb, Cw - Xv * 0.0125, Xv, 0.0155, 0.025, seg=36)
    bmesh.ops.recalc_face_normals(wb, faces=wb.faces[:])
    b.bits.append(sw(ck.modded(wb, bevel=0.0032, seg=3, angle=40), "black"))
    for sx in (-1, 1):
        b.bits.append(sw(cyl(Cw + Xv * sx * 0.0125, Xv * sx, 0.0085, 0.0008, seg=20), "darkgrey"))
    for th in (-8.0, 34.0):
        t_ = math.radians(th)
        dr = (Nv * math.cos(t_) - Yv * math.sin(t_)).normalized()
        b.bits.append(sw(cyl(Cw + dr * 0.0150, dr, 0.0040, 0.0009, seg=16), "darkgrey"))
        b.bits.append(sw(cyl(Cw + dr * 0.0156, dr, 0.0031, 0.0010, seg=16, r_top=0.0024), "red"))
    lever = ck.merge(b.bits)
    b.bits = fixed_bits
    cx, cy = CAP
    for ex, ey in EARS:
        b.prism(pk.circle_pts(ex, ey, CAP_R[4], 20), -0.5, 3.0, bevel=0.7)
        b.hexbolt(ex, ey, 3.0, r=3.3, h=2.4, washer=False)
    b.prism(pk.circle_pts(cx, cy, CAP_R[0], 56), -0.5, 4.2, bevel=0.9, holes=[pk.circle_pts(cx, cy, CAP_R[1], 48)])
    b.prism(pk.circle_pts(cx, cy, CAP_R[2], 48), -0.5, 5.0, bevel=0.8)
    for ang in (0, 180):
        b.box(cx + CAP_R[5] * math.cos(math.radians(ang)), cy + CAP_R[5] * math.sin(math.radians(ang)), 4.4, (4.2, 6.0, 2.2), "black", bevel=0.5, seg=1)
    gx, gy = JETT_GUARD
    for dx, dy, sx, sy in ((0, 11.5, 27, 4), (0, -11.5, 27, 4), (11.5, 0, 4, 19), (-11.5, 0, 4, 19)):
        b.box(gx + dx, gy + dy, 4.5, (sx, sy, 9.0), "darkgrey", bevel=1.0, seg=2)
    b.box(gx, gy, 2.6, (18.5, 18.5, 5.2), "darkgrey", bevel=1.0)
    b.box(gx, gy, 5.35, (14.0, 14.0, 0.4), "black", bevel=0)
    b.key(JETT_KEY[0], JETT_KEY[1], 0.0, 19.5, 19.5, cap=7.0)
    lean = (Nv * math.cos(math.radians(30)) - Xv * math.sin(math.radians(30))).normalized()
    p0 = b.P(PROG[0], PROG[1], 0.0)
    b.cyl(PROG[0], PROG[1], 0.0, 8.6, 1.4, "black", seg=24)
    b.bits.append(sw(gear(p0, lean, 0.0064, 0.015, teeth=16, depth=0.0005), "darkgrey"))
    b.bits.append(sw(cyl(p0 + lean * 0.015, lean, 0.0058, 0.0012, seg=18, r_top=0.0046), "darkgrey"))
    f0 = b.P(FRIC[0], FRIC[1], 0.0)
    b.cyl(FRIC[0], FRIC[1], 0.0, 12.0, 1.6, "black", seg=28)
    b.bits.append(sw(gear(f0, lean, 0.0098, 0.022, teeth=22, depth=0.0007), "darkgrey"))
    b.bits.append(sw(cyl(f0 + lean * 0.022, lean, 0.0090, 0.0016, seg=24, r_top=0.0074), "darkgrey"))
    hx, hy, hw, hh = HAZ_GEAR
    b.cyl(hx, hy - 9.0, 0.0, 5.6, 2.2, "metal", seg=6)
    b.bits.append(sw(cyl(b.P(hx, hy - 9.0, 3.0), (-Xv * 0.94 + Nv * 0.34).normalized(), 0.0021, 0.019, seg=12, r_top=0.0027), "darkgrey"))
    b.box(hx, hy + hh / 2 - 2.0, 4.0, (17.0, 6.0, 8.0), "darkgrey", bevel=1.2)
    dl = (-Yv * math.cos(math.radians(16)) + Nv * math.sin(math.radians(16))).normalized()
    Fl = ck.frame(Xv, (-dl), Xv.cross(-dl).normalized())
    for k in range(5):
        b.bits.append(sw(ck.rbox(b.P(hx, hy + hh / 2 - 5.0, 8.5) + dl * (0.0030 + k * 0.0062), (0.0150, 0.0062, 0.0050), Fl,
                                 bevel=0.0014 if k == 4 else 0.0004, seg=2), "yellow" if k % 2 == 0 else "black"))
    b.toggle(LAND[0], LAND[1], 0.0, lean=34.0, lean_dir=180.0, long=True)
    for i, (x, y) in enumerate(SCREWS):
        b.screw(x, y, 0.0, r=3.0, ang=0.7 + 1.3 * i)
    slab, bits = b.merged()
    return {"slab": slab, "fixed": bits, "lever": lever, "labels": labels(), "surface_line": surface_line(),
            "hinge_b": (float(H.x), float(H.y), float(H.z))}


def paint(out_dir, ao=None, res=2048):
    c = pk.Canvas(WIN, res, C_PANEL, seed=21)
    X, Y = c.X, c.Y
    sdf = pk.sd_poly(X, Y, OUTLINE)
    c.plate(sdf, 0.0, wear=1.0)
    c.put(c.cov(-sdf), pk.DARK, None, 0.3, 0.0)
    c.base *= (1 - 0.08 * np.clip(1 - (Y + X * 26 / 240) / 9.0, 0, 1))[..., None]
    for cx_, cy_, r_ in ((-44, 100, 40), (LAND[0], LAND[1], 18), (-120, 98, 20)):
        c.base *= (1 + 0.03 * np.clip(1 - np.hypot(X - cx_, Y - cy_) / r_, 0, 1))[..., None]
    sds = pk.sd_rrect(X, Y, *SLOT)
    c.plate(sds, SLOT_Z, pk.BLACK * 1.3, smooth=0.28, paint=0.0)
    c.mark(np.abs(sds - 1.4) - 0.14, C_PANEL * 0.78, -0.03, None)
    hx, hy, hw, hh = HAZ_JETT
    sdh = pk.sd_rrect(X, Y, hx, hy, hw, hh, 0.6)
    c.put(c.cov(sdh - 0.5), pk.BLACK * 1.5, None, 0.3, 0.3)
    c.hazard(sdh, period=7.5)
    hx, hy, hw, hh = HAZ_GEAR
    sdh = pk.sd_rrect(X, Y, hx, hy, hw, hh, 0.6)
    c.put(c.cov(sdh - 0.5), pk.BLACK * 1.5, None, 0.3, 0.3)
    c.hazard(sdh, period=6.5)
    for pts in ([(-86, 121.5), (-86, 126), (-104, 126)], [(-140, 126), (-158, 126), (-158, 121.5)]):
        c.line(pts, 0.55)
    for x0, y0, x1, y1 in ((-170, 50, -173.5, 50), (-170, 39, -173.5, 39), (-170, 28, -173.5, 28),
                           (LAND[0], LAND[1] + 8.5, LAND[0], LAND[1] + 11.5), (LAND[0] + 8.5, LAND[1], LAND[0] + 11.5, LAND[1]),
                           (LAND[0], LAND[1] - 8.5, LAND[0], LAND[1] - 11.5)):
        c.line([(x0, y0), (x1, y1)], 0.55)
    cx, cy = CAP
    for ex, ey in EARS:
        c.plate(pk.sd_circle(X, Y, ex, ey, CAP_R[4]), 3.0, C_SUBPL)
        c.stand(pk.sd_circle(X, Y, ex, ey, 3.3), 5.4)
    R = np.hypot(X - cx, Y - cy)
    c.plate(R - CAP_R[0], 4.2, C_SUBPL, wear=1.3)
    c.plate(R - CAP_R[1], 0.6, pk.BLACK * 1.3, smooth=0.28, paint=0.0)
    C_CAP = np.array([0.105, 0.108, 0.113], np.float32)
    capc = c.plate(R - CAP_R[2], 5.0, C_CAP, smooth=0.36, paint=0.0)
    turn = 0.5 + 0.5 * np.cos(R * 2 * math.pi / 0.9)
    c.put(capc * turn * 0.5, C_CAP * 1.18, None, None)
    c.bump += capc * 0.012 * turn
    c.put(capc * c.cov(np.abs(R - 20.3) - 0.9), C_CAP * 1.45, 0.05, 0.42)
    c.put(capc * c.cov(-(Y - cy - 9.5)) * c.cov(R - 18.6), C_CAP * 0.62, -0.04, 0.30)
    smile = np.abs(np.hypot(X - cx, Y - cy - 6.0) - 19.0) - 0.35
    c.put(capc * c.cov(smile) * (Y < cy - 6.5) * c.cov(R - 17.5), C_CAP * 1.9, -0.03, None)
    for sx in (-1, 1):
        c.put(capc * c.cov(pk.sd_rrect(X, Y, cx + sx * 15.5, cy, 1.6, 7.0, 0.5)), C_CAP * 0.45, -0.08, None)
    gx, gy = JETT_GUARD
    c.stand(pk.sd_rrect(X, Y, gx, gy, 27, 27, 1.5), 9.0)
    c.stand(pk.sd_rrect(X, Y, JETT_KEY[0], JETT_KEY[1], 23.9, 23.9, 1.0), 7.5)
    c.mark(pk.sd_rrect(X, Y, JETT_KEY[0], JETT_KEY[1], 24.6, 24.6, 1.4), pk.BLACK * 1.4, None, 0.25)
    c.stand(pk.sd_circle(X, Y, PROG[0], PROG[1], 8.6), 12.0)
    c.mark(pk.sd_circle(X, Y, PROG[0], PROG[1], 9.1), pk.BLACK * 1.4, None, 0.25)
    c.stand(pk.sd_circle(X, Y, FRIC[0], FRIC[1], 12.0), 16.0)
    c.mark(pk.sd_circle(X, Y, FRIC[0], FRIC[1], 12.5), pk.BLACK * 1.4, None, 0.25)
    c.stand(pk.sd_rrect(X, Y, HAZ_GEAR[0], HAZ_GEAR[1] + 2.0, 16, 34, 2), 11.0)
    c.stand(pk.sd_circle(X, Y, LAND[0], LAND[1], 5.8), 6.5)
    c.mark(pk.sd_circle(X, Y, LAND[0], LAND[1], 6.9), pk.BLACK * 1.3, None, 0.25)
    for x, y in SCREWS:
        c.stand(pk.sd_circle(X, Y, x, y, 3.0), 1.1)
    c.finish(wear=1.0)
    c.save(out_dir, "ckgear")
