import math

import numpy as np

import panelkit as pk

FACE_U = np.array([[-0.0964, 0.5031, 7.1689], [0.0964, 0.5031, 7.1689], [0.1026, 0.5982, 7.2705], [-0.1027, 0.5974, 7.2715]])
TOP = 0.003
FR = pk.Frame((FACE_U[0] + FACE_U[1]) / 2, (1.0, 0.0, 0.0), (FACE_U[2] + FACE_U[3]) / 2 - (FACE_U[0] + FACE_U[1]) / 2, top=TOP)
_fx, _fy, _fl = FR.local_u(FACE_U)
FACE = [(float(a), float(b)) for a, b in zip(_fx, _fy)]
WIN = (-105.0, 105.0, -35.0, 175.0)

Z_MAIN, Z_SUB, Z_RAIL = 2.4, 4.0, 4.0
MAIN = [(-94, 135), (94, 135), (94, 30), (80, 9), (50, 9), (40, 10.5), (32, 15), (24, 18.5), (12, 21.2), (0, 22), (-12, 21.2),
        (-24, 18.5), (-32, 15), (-40, 10.5), (-50, 9), (-80, 9), (-94, 30)]
RAIL = (-74.0, 77.0, 26.0, 98.0, 2.5)
LKEYS = [("NVE", 111.0, "g"), ("FLIR", 87.0, "g"), ("CHAN|SEL", 63.0, "w"), ("T/C", 39.0, "w")]
LEDGES = [123.3, 99.0, 75.0, 51.0]
SUB = (-20.0, 79.5, 72.0, 105.0, 3.0)
KNOBS = [(-38.0, 106.0, 25.0), (-2.0, 106.0, -30.0), (-34.0, 84.0, 10.0)]
GND = (3.0, 86.0)
DISP = {"R": (-42.0, 56.0), "ARROW": (-22.0, 56.0), "L": (-2.0, 56.0), "DL": (-42.0, 38.0), "C": (-22.0, 38.0), "DR": (-2.0, 38.0)}
RKEYS = [("T/O", 30.0, 80.0), ("AA", 52.0, 66.0), ("NAV", 74.0, 52.0)]
DRF = (64.0, 109.0, 38.0)
Z_DRF = 5.0
DRF_PLATE = [(36.0, 133.0), (92.0, 133.0), (92.0, 84.0), (63.0, 84.0), (36.0, 103.0)]
DRF_HAZ = (66.5, 106.5, 31.0, 30.0)
BOLTS = [(-78.0, 18.5, 4.6), (78.0, 18.5, 4.6), (-87.5, 130.6, 3.3)]
DRF_BOLT = (86.5, 127.0, 3.6)
KNOB_R = 7.4
GREEN = (0.45, 1.0, 0.5)
WHITE = (0.90, 0.91, 0.87)
C_SLAB = np.array([0.45, 0.465, 0.48], np.float32)
C_SUB = np.array([0.455, 0.47, 0.485], np.float32)
C_RAIL = np.array([0.215, 0.222, 0.232], np.float32)


def footprint(p):
    x, y, l = FR.local(p)
    return -104 < x < 104 and -3 < y < 142 and -10 < l < 40


def shell_remove_mask(P):
    dist = np.linalg.norm(P[:, :, None, :] - FACE_U[None, None, :, :], axis=3).min(2)
    return (dist < 0.0015).all(1)


def labels():
    kz = Z_RAIL + 6.0
    L = []
    for text, y, c in LKEYS:
        L.append(FR.label(text, -74.0, y, 3.3 if "|" not in text else 2.8, z=kz, col=GREEN if c == "g" else WHITE, spacing=1.25))
    L += [FR.label("NVE/FLIR", -20.0, 126.5, 1.9, z=Z_SUB), FR.label("BRT", -38.0, 117.6, 1.8, z=Z_SUB),
          FR.label("CONT", -2.0, 117.6, 1.8, z=Z_SUB), FR.label("SYMB|BRT", -48.5, 94.0, 1.7, z=Z_SUB, spacing=1.3),
          FR.label("GND", GND[0], GND[1], 3.0, z=Z_SUB + 6.0, col=GREEN),
          FR.label("DISP CHANGE", -22.0, 69.0, 1.8, z=Z_SUB)]
    for k in ("R", "L", "C"):
        L.append(FR.label(k, DISP[k][0], DISP[k][1], 3.0, z=Z_SUB))
    L += [FR.label("↔", DISP["ARROW"][0], DISP["ARROW"][1], 7.0, z=Z_SUB + 6.0, col=WHITE),
          FR.label("↘", DISP["DL"][0], DISP["DL"][1], 7.0, z=Z_SUB + 6.0, col=WHITE),
          FR.label("↗", DISP["DR"][0], DISP["DR"][1], 7.0, z=Z_SUB + 6.0, col=WHITE)]
    for text, x, y in RKEYS:
        L.append(FR.label(text, x, y, 3.1, z=Z_RAIL + 6.0, col=GREEN))
    L.append(FR.label("DRF", DRF[0], DRF[1] + 20.4, 1.9, z=Z_DRF))
    return L


def build(ck, sw):
    b = pk.Builder(ck, sw, FR, WIN)
    b.prism(FACE, -(TOP * 1000 + 12.0), 0.0, bevel=1.2)
    b.prism(pk.round_poly(MAIN, 3.0), -0.5, Z_MAIN, bevel=0.8)
    b.prism(pk.rrect_pts(*RAIL), Z_MAIN - 0.5, Z_RAIL, bevel=0.6)
    for (text, y, c) in LKEYS:
        b.key(-74.0, y, Z_RAIL, 15.5, 15.5, face="black", cap=5.0)
        if c == "g":
            for dy in (-5.3, 5.3):
                b.box(-74.0, y + dy, Z_RAIL + 5.95, (9.5, 0.9, 0.25), "green", bevel=0)
    for y in LEDGES:
        b.prism(pk.rrect_pts(-74.0, y, 25.0, 3.6, 0.8), Z_RAIL - 0.5, Z_RAIL + 6.2, bevel=0.7)
    b.prism(pk.rrect_pts(*SUB), Z_MAIN - 0.5, Z_SUB, bevel=0.6)
    for x, y, a in KNOBS:
        b.cyl(x, y, Z_SUB, KNOB_R * 1.32, 2.6, "darkgrey", seg=6)
        b.cyl(x, y, Z_SUB + 2.6, KNOB_R, 13.5, "black", seg=28, r_top=KNOB_R * 0.94)
        b.cyl(x, y, Z_SUB + 16.1, KNOB_R * 0.94, 0.9, "black", seg=28, r_top=KNOB_R * 0.80)
        b.box(x + 0.60 * KNOB_R * math.sin(math.radians(a)), y + 0.60 * KNOB_R * math.cos(math.radians(a)), Z_SUB + 17.05,
              (0.9, KNOB_R * 0.62, 0.25), "white", bevel=0, ang=-a)
    b.key(GND[0], GND[1], Z_SUB, 14.0, 14.0, cap=5.0)
    for k in ("ARROW", "DL", "DR"):
        b.key(DISP[k][0], DISP[k][1], Z_SUB, 15.0, 13.0, cap=5.0)
    for text, x, y in RKEYS:
        b.prism(pk.rrect_pts(x, y, 22.5, 22.5, 2.0), Z_MAIN - 0.5, Z_RAIL, bevel=0.6)
        b.key(x, y, Z_RAIL, 15.0, 15.0, cap=5.0)
        b.prism(pk.rrect_pts(x - 10.4, y, 2.6, 21.0, 0.9), Z_RAIL - 0.5, Z_RAIL + 11.5, bevel=0.7, col="black")
    b.prism(pk.rrect_pts(GND[0] - 9.9, GND[1], 2.6, 19.0, 0.9), Z_SUB - 0.5, Z_SUB + 11.5, bevel=0.7, col="black")
    dx, dy, ds = DRF
    b.prism(pk.round_poly(DRF_PLATE, 3.0), Z_MAIN - 0.5, Z_DRF, bevel=0.8)
    b.prism(pk.circle_pts(dx, dy, 16.6, 44), Z_DRF - 0.3, Z_DRF + 9.0, bevel=2.2, col="black", holes=[pk.circle_pts(dx, dy, 11.6, 36)], seg=3)
    b.cyl(dx, dy, Z_DRF, 11.8, 1.2, "black", seg=32)
    b.box(dx, dy, Z_DRF + 3.0, (13.0, 13.0, 5.0), "black", bevel=1.0)
    b.box(dx, dy, Z_DRF + 5.75, (10.4, 10.4, 0.5), "white", bevel=0)
    b.hexbolt(DRF_BOLT[0], DRF_BOLT[1], Z_DRF, r=DRF_BOLT[2], h=2.8)
    for x, y, r in BOLTS:
        b.hexbolt(x, y, Z_MAIN, r=r, h=2.8)
    slab, bits = b.merged()
    return {"slab": slab, "bits": bits, "labels": labels()}


def paint(out_dir, res=2048):
    c = pk.Canvas(WIN, res, C_SLAB, seed=47)
    X, Y = c.X, c.Y
    sdf = pk.sd_poly(X, Y, FACE)
    c.plate(sdf, 0.0, wear=0.8)
    c.put(c.cov(-sdf), pk.DARK, None, 0.3, 0.0)
    c.plate(pk.sd_poly(X, Y, pk.round_poly(MAIN, 3.0)), Z_MAIN, pk.GREY, wear=1.1)
    c.plate(pk.sd_rrect(X, Y, *RAIL), Z_RAIL, C_RAIL, smooth=0.30, wear=0.8)
    for (_, y, _c) in LKEYS:
        c.stand(pk.sd_rrect(X, Y, -74.0, y, 19.9, 19.9, 1.0), Z_RAIL + 6.0)
    for y in LEDGES:
        c.plate(pk.sd_rrect(X, Y, -74.0, y, 25.0, 3.6, 0.8), Z_RAIL + 6.2, pk.GREY_D, wear=1.4)
    c.plate(pk.sd_rrect(X, Y, *SUB), Z_SUB, C_SUB, wear=1.0)
    for x, y, _a in KNOBS:
        c.mark(pk.sd_circle(X, Y, x, y, KNOB_R * 1.32 + 0.6), pk.BLACK * 1.4, None, 0.25)
        c.stand(pk.sd_circle(X, Y, x, y, KNOB_R * 1.32), Z_SUB + 17.0)
    for (x, y, w, h) in [(GND[0], GND[1], 18.4, 18.4)] + [(DISP[k][0], DISP[k][1], 19.4, 17.4) for k in ("ARROW", "DL", "DR")]:
        c.mark(pk.sd_rrect(X, Y, x, y, w + 0.8, h + 0.8, 1.2), pk.BLACK * 1.4, None, 0.25)
        c.stand(pk.sd_rrect(X, Y, x, y, w, h, 1.0), Z_SUB + 6.0)
    for pts in ([(-50, 122.5), (-50, 126.5), (-33.5, 126.5)], [(-6.5, 126.5), (10, 126.5), (10, 122.5)],
                [(-50, 65.5), (-50, 69), (-34.5, 69)], [(-9.5, 69), (6, 69), (6, 65.5)]):
        c.line(pts, 0.5)
    for k in ("R", "L", "C"):
        x, y = DISP[k]
        c.mark(np.abs(pk.sd_rrect(X, Y, x, y, 8.6, 8.6, 0.8)) - 0.25, pk.WHITE, -0.03, 0.35)
    for _t, x, y in RKEYS:
        c.plate(pk.sd_rrect(X, Y, x, y, 22.5, 22.5, 2.0), Z_RAIL, C_RAIL, smooth=0.30, wear=0.8)
        c.stand(pk.sd_rrect(X, Y, x, y, 19.4, 19.4, 1.0), Z_RAIL + 6.0)
    dx, dy, ds = DRF
    c.plate(pk.sd_poly(X, Y, pk.round_poly(DRF_PLATE, 3.0)), Z_DRF, C_SUB, wear=1.0)
    sdh = pk.sd_rrect(X, Y, *DRF_HAZ, 1.0)
    c.put(c.cov(sdh - 0.5), pk.BLACK * 1.5, None, 0.3, 0.3)
    c.hazard(sdh, period=6.0)
    c.mark(pk.sd_circle(X, Y, dx, dy, 17.2), pk.BLACK * 1.4, None, 0.25)
    c.stand(pk.sd_circle(X, Y, dx, dy, 16.6), Z_DRF + 9.0)
    c.stand(pk.sd_circle(X, Y, DRF_BOLT[0], DRF_BOLT[1], DRF_BOLT[2] * 1.42), Z_DRF + 3.4)
    for x, y, r in BOLTS:
        c.stand(pk.sd_circle(X, Y, x, y, r * 1.42), Z_MAIN + 3.4)
    for cx_, cy_, r_ in ((-20, 100, 34), (-22, 47, 30), (0, 14, 40)):
        d = np.hypot(X - cx_, Y - cy_)
        c.base *= (1 + 0.03 * np.clip(1 - d / r_, 0, 1))[..., None]
    c.finish(wear=1.0)
    c.save(out_dir, "cknve")
