import math

import numpy as np

import panelkit as pk

SCREEN_U = np.array([[0.2980, 0.6026, 7.1969], [0.4025, 0.6215, 7.1927], [0.4140, 0.5391, 7.1269], [0.3095, 0.5197, 7.1327]])
FACE_U = np.array([[0.2897, 0.6667, 7.2463], [0.3687, 0.6733, 7.2374], [0.3806, 0.6541, 7.2207], [0.4514, 0.6538, 7.2085],
                   [0.5003, 0.5721, 7.1339], [0.5287, 0.5378, 7.1079], [0.2897, 0.5051, 7.1253]])
TOP = 0.0045
FR = pk.Frame(SCREEN_U.mean(0), SCREEN_U[1] - SCREEN_U[0] + SCREEN_U[2] - SCREEN_U[3],
              SCREEN_U[0] - SCREEN_U[3] + SCREEN_U[1] - SCREEN_U[2], top=TOP)
assert FR.N_u[1] > 0.3, "DWP frame: normal should point up / aft"
_fx, _fy, _fl = FR.local_u(FACE_U)
FACE = [(float(a), float(b)) for a, b in zip(_fx, _fy)]
WIN = (-78.0, 168.0, -91.0, 155.0)

HOLE = (0.0, 0.0, 104.0, 104.0, 6.5)
BEZ = (12.75, 0.0, 142.5, 119.0, 5.0)
BEZ_Z = 3.2
KEYS = [("REV", 71.0, 8.0), ("AGE", 71.0, -18.0)]
CAP = (-20.0, 96.0)
EARS = [(CAP[0] + 32.5 * math.cos(math.radians(a)), CAP[1] + 32.5 * math.sin(math.radians(a))) for a in (45, 135, 225, 315)]
SWPLATE = [(88, -22), (104, -22), (124, -50), (124, -70), (88, -70)]
TOGGLES = [(97.0, -40.0), (112.0, -60.0)]
BOSSES = [(-57.0, 58.0), (82.5, 58.0), (82.5, -58.0), (-57.0, -58.0)]
BEZ_SCREWS = [(-30, 55.9), (18, 55.9), (-30, -55.9), (18, -55.9), (-55.6, 22), (-55.6, -22), (55.9, -42), (55.9, 42),
              (79.5, 30), (79.5, -40)]
SCREWS = [(-67, -62), (154, -71), (134.5, -33), (98.5, 75), (22, 117.5), (40, -68)]
GREEN = (0.45, 1.0, 0.5)
C_FACE = pk.PANEL_DARK
C_BEZ = C_FACE * 1.16
C_SUBPL = C_FACE * 0.86
C_SW = C_FACE * 0.82
C_CAP = np.array([0.105, 0.108, 0.113], np.float32)


def footprint(p):
    x, y, l = FR.local(p)
    return pk._inside(x, y, FACE) and -12 < l < 60


def shell_remove_mask(P):
    dist = np.linalg.norm(P[:, :, None, :] - FACE_U[None, None, :, :], axis=3).min(2)
    return (dist < 0.0015).all(1)


def labels():
    L = [FR.label("OPEN", CAP[0], CAP[1] + 14.0, 3.0, z=5.0, col=(0.80, 0.81, 0.78))]
    for name, x, y in KEYS:
        L.append(FR.label(name, x, y, 3.7, z=BEZ_Z + 6.7, col=GREEN))
    t1, t2 = TOGGLES
    L += [FR.label("HEA VENT|AUTO", t1[0], t1[1] + 12.6, 1.8, z=1.2), FR.label("REV", t1[0] + 11.5, t1[1] + 1.5, 1.8, z=1.2),
          FR.label("OFF", t1[0], t1[1] - 10.4, 1.8, z=1.2),
          FR.label("ECS|NORM", t2[0] - 13.6, t2[1] + 0.5, 1.8, z=1.2), FR.label("LSP", t2[0], t2[1] - 8.3, 1.8, z=1.2)]
    return L


def build(ck, sw):
    b = pk.Builder(ck, sw, FR, WIN)
    hole = pk.rrect_pts(*HOLE)
    b.prism(FACE, -(TOP * 1000 + 14.0), 0.0, bevel=1.4, holes=[hole])
    b.prism(pk.rrect_pts(*BEZ), -0.5, BEZ_Z, bevel=0.9, holes=[hole])
    b.box(0, 0, -3.6, (108, 108, 0.8), "black", bevel=0)
    for x, y in BOSSES:
        b.cyl(x, y, 0.0, 3.9, 4.6, "darkgrey", seg=20, r_top=3.5)
    for name, x, y in KEYS:
        b.key(x, y, BEZ_Z, 15.0, 15.0, face="black", cap=5.6)
    b.box(71.0, -5.0, BEZ_Z + 0.7, (13.0, 2.6, 1.4), "darkgrey", bevel=0.4, seg=1)
    cx, cy = CAP
    for ex, ey in EARS:
        b.prism(pk.circle_pts(ex, ey, 7.0, 20), -0.5, 3.0, bevel=0.7)
        b.hexbolt(ex, ey, 3.0, r=3.3, h=2.4, washer=False)
    b.prism(pk.circle_pts(cx, cy, 30.0, 56), -0.5, 4.2, bevel=0.9, holes=[pk.circle_pts(cx, cy, 22.6, 48)])
    b.prism(pk.circle_pts(cx, cy, 21.4, 48), -0.5, 5.0, bevel=0.8)
    for a in (0, 180):
        b.box(cx + 20.6 * math.cos(math.radians(a)), cy + 20.6 * math.sin(math.radians(a)), 4.4, (4.2, 6.0, 2.2), "black", bevel=0.5, seg=1)
    b.prism(pk.round_poly(SWPLATE, 4.0), -0.5, 1.2, bevel=0.5)
    for x, y in TOGGLES:
        b.toggle(x, y, 1.2, lean=15.0, lean_dir=90.0)
    for i, (x, y) in enumerate(SCREWS):
        b.screw(x, y, 0.0, r=3.0, ang=0.6 + 1.3 * i)
    slab, bits = b.merged()
    return {"slab": slab, "bits": bits, "labels": labels()}


def paint(out_dir, res=2048):
    c = pk.Canvas(WIN, res, C_FACE, seed=31)
    X, Y = c.X, c.Y
    c.plate(pk.sd_poly(X, Y, FACE), 0.0, wear=1.0)
    c.put(c.cov(-pk.sd_poly(X, Y, FACE)), pk.DARK, None, 0.3, 0.0)
    c.base *= (1 - 0.07 * np.clip(1 - (Y + 66 + (X + 75) * 0.05) / 7.0, 0, 1))[..., None]
    sd_hole = pk.sd_rrect(X, Y, *HOLE)
    sd_bez = pk.sd_rrect(X, Y, *BEZ)
    c.plate(sd_bez, BEZ_Z, C_BEZ, wear=1.2)
    c.plate(sd_hole, -6.0, pk.BLACK, smooth=0.3, paint=0.0)
    c.mark(np.abs(sd_hole - 0.7) - 0.7, pk.BLACK * 1.6, -0.05, 0.25)
    _line = np.abs(sd_hole - 2.2) - 0.12
    for x, y in BEZ_SCREWS:
        _line = np.maximum(_line, 1.55 + 1.0 - np.hypot(X - x, Y - y))
    c.mark(_line, C_BEZ * 0.74, -0.03, None)
    c.mark(pk.sd_seg(X, Y, 56.0, 54.0, 56.0, 46.0) - 0.15, C_BEZ * 0.68, -0.03, None)
    for _, x, y in KEYS:
        c.mark(pk.sd_rrect(X, Y, x, y, 20.4, 20.4, 1.5), pk.BLACK * 1.4, -0.1, 0.25)
        c.stand(pk.sd_rrect(X, Y, x, y, 19.4, 19.4, 1.0), BEZ_Z + 6.0)
    for x, y in BEZ_SCREWS:
        c.screw(x, y, 1.55, slot="slot")
    for x, y in BOSSES:
        c.stand(pk.sd_circle(X, Y, x, y, 3.9), 4.6)
        c.mark(pk.sd_circle(X, Y, x, y, 4.3), pk.BLACK * 1.5, None, 0.25)
    cx, cy = CAP
    for ex, ey in EARS:
        c.plate(pk.sd_circle(X, Y, ex, ey, 7.0), 3.0, C_SUBPL)
        c.stand(pk.sd_circle(X, Y, ex, ey, 3.3), 5.4)
    R = np.hypot(X - cx, Y - cy)
    c.plate(R - 30.0, 4.2, C_SUBPL, wear=1.3)
    c.plate(R - 22.6, 0.6, pk.BLACK * 1.3, smooth=0.28, paint=0.0)
    capc = c.plate(R - 21.4, 5.0, C_CAP, smooth=0.36, paint=0.0)
    turn = 0.5 + 0.5 * np.cos(R * 2 * math.pi / 0.9)
    c.put(capc * turn * 0.5, C_CAP * 1.18, None, None)
    c.bump += capc * 0.012 * turn
    c.put(capc * c.cov(np.abs(R - 20.3) - 0.9), C_CAP * 1.45, 0.05, 0.42)
    cres = capc * c.cov(-(Y - cy - 9.5)) * c.cov(R - 18.6)
    c.put(cres, C_CAP * 0.62, -0.04, 0.30)
    smile = np.abs(np.hypot(X - cx, Y - cy - 6.0) - 19.0) - 0.35
    c.put(capc * c.cov(smile) * (Y < cy - 6.5) * c.cov(R - 17.5), C_CAP * 1.9, -0.03, None)
    for sx in (-1, 1):
        c.put(capc * c.cov(pk.sd_rrect(X, Y, cx + sx * 15.5, cy, 1.6, 7.0, 0.5)), C_CAP * 0.45, -0.08, None)
    sdp = pk.sd_poly(X, Y, pk.round_poly(SWPLATE, 4.0))
    c.plate(sdp, 1.2, C_SW, smooth=0.30, wear=0.9)
    for x, y in TOGGLES:
        c.stand(pk.sd_circle(X, Y, x, y, 5.6), 6.0)
        c.mark(pk.sd_circle(X, Y, x, y, 6.9), pk.BLACK * 1.3, None, 0.25)
    t1, t2 = TOGGLES
    for x0, y0, x1, y1 in ((t1[0], t1[1] + 7.4, t1[0], t1[1] + 9.0), (t1[0] + 7.4, t1[1] + 1.5, t1[0] + 8.6, t1[1] + 1.5),
                           (t1[0], t1[1] - 7.4, t1[0], t1[1] - 8.6), (t2[0] - 7.4, t2[1] + 0.5, t2[0] - 8.4, t2[1] + 0.5),
                           (t2[0], t2[1] - 7.2, t2[0], t2[1] - 6.9)):
        c.line([(x0, y0), (x1, y1)], 0.45)
    for x, y in SCREWS:
        c.stand(pk.sd_circle(X, Y, x, y, 3.0), 1.1)
    c.finish(wear=1.0)
    c.save(out_dir, "ckdwp")
