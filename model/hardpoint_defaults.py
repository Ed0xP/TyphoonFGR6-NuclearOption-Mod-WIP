import math
import sys

import numpy as np

OBJ, OUT = sys.argv[1], sys.argv[2]
STORES = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3].endswith("stores.txt") else None
GEAR = next((a for a in sys.argv[3:] if a.endswith("typhoon_gear.txt")), None)
BAY_STATION = None
if GEAR:
    for line in open(GEAR):
        if line.startswith("# bay stations"):
            BAY_STATION = line.split(":", 1)[1].strip()

OUTER_PITCH = 4.6
MID_X, MID_KEEL_Y, MID_KEEL_Z = 3.20, -0.76, 0.366
BELLY_X = 0.50
BELLY_Z = -0.30
RECESS = 0.30
GUN_FLASH = (0.84, -0.12, 5.00)

V, groups, cur = [], {}, None
for line in open(OBJ):
    if line.startswith("v "):
        V.append([float(x) for x in line.split()[1:4]])
    elif line.startswith("o "):
        cur = line[2:].strip(); groups[cur] = []
    elif line.startswith("f "):
        groups[cur].append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
V = np.array(V)


def tris(names):
    T = [V[f] for n in names for f in groups[n]]
    return np.array(T)


def surface(T, x, z, lowest=True):
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    d = (b[:, 2] - c[:, 2]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 2] - c[:, 2])
    with np.errstate(divide="ignore", invalid="ignore"):
        w1 = ((b[:, 2] - c[:, 2]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (z - c[:, 2])) / d
        w2 = ((c[:, 2] - a[:, 2]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (z - c[:, 2])) / d
    w3 = 1 - w1 - w2
    m = (np.abs(d) > 1e-12) & (w1 >= 0) & (w2 >= 0) & (w3 >= 0)
    if not m.any():
        return None
    y = w1[m] * a[m, 1] + w2[m] * b[m, 1] + w3[m] * c[m, 1]
    return y.min() if lowest else y.max()


P = V[np.unique(np.concatenate([np.array(f) for f in groups["wing_L"]]))]
blade = P[(P[:, 0] > -4.62) & (P[:, 0] < -4.38) & (P[:, 1] < -0.42)]
bx = 0.5 * (blade[:, 0].min() + blade[:, 0].max())
z0, z1 = blade[:, 2].min(), blade[:, 2].max()
pts = []
for zz in np.linspace(z0, z1, 40):
    s = blade[np.abs(blade[:, 2] - zz) < 0.05]
    if len(s):
        pts.append((s[:, 2][np.argmin(s[:, 1])], s[:, 1].min()))
pts = np.array(pts)
k, c = np.polyfit(pts[:, 0], pts[:, 1], 1)
for _ in range(3):
    r = pts[:, 1] - (k * pts[:, 0] + c)
    pts = pts[r < 0.01]
    k, c = np.polyfit(pts[:, 0], pts[:, 1], 1)
blade_pitch = math.degrees(math.atan(-k))
OUTER_Z = -0.20
outer = (bx, k * OUTER_Z + c, OUTER_Z)
print(f"outer blade: x {bx:.3f}, z {z0:.2f}..{z1:.2f}, keel y = {k:.4f} z + {c:.4f} ({blade_pitch:.2f} deg nose-down)")

OUTER_WEAPONS = {
    "AAM2_single": (0.167, 0.17),
    "AAM1_single": (0.156, 0.20),
    "AAM4_single": (0.167, 0.20),
    "ARM2_single": (0.122, 0.28),
}
GAP = 0.004

body = tris(["fuselage", "fuselage_cockpit", "geardoors"])


def belly_line(xs, za, zb):
    zs = np.linspace(za, zb, 25)
    Y = []
    for zz in zs:
        ys = [surface(body, x, zz) for x in xs]
        ys = [y for y in ys if y is not None]
        if ys:
            Y.append((zz, float(np.mean(ys))))
    Y = np.array(Y)
    return np.polyfit(Y[:, 0], Y[:, 1], 1)


mx = [-BELLY_X - 0.162, -BELLY_X + 0.184]
bk, bc = belly_line(mx, BELLY_Z + 0.30 - 1.6, BELLY_Z + 0.30 + 1.6)
belly_pitch = math.degrees(math.atan(-bk))
r_aam2 = 0.087
centre_y = bk * (BELLY_Z + 0.30) + bc - RECESS * r_aam2
belly = (-BELLY_X, centre_y + 0.067, BELLY_Z)
print(f"belly line under the missiles: y = {bk:.4f} z + {bc:.4f} ({belly_pitch:.2f} deg), station y {belly[1]:.3f}")

BAY = {
    "AAM2_double_internal": ("missile", -0.067, 0.098, 0.087),
    "AAM1_double_internal": ("missile", -0.142, 0.034, 0.055),
    "AAM4_double_internal_compact": ("missile", -0.100, 0.041, 0.120),
    "AAM3_triple_internal_flat": ("missile", -0.150, -0.036, 0.050),
    "AGM_heavy_internal": ("missile", -0.137, 0.110, 0.125),
    "ARM2_single_internal": ("missile", -0.120, 0.065, 0.100),
    "bomb_500_internal": ("bomb", -0.150, 0.077, 0.0),
    "nuclearBomb1_internal": ("bomb", -0.175, 0.010, 0.0),
    "nuclearBomb1_strategic_internal": ("bomb", -0.175, 0.010, 0.0),
    "bomb_250_internalx2": ("bomb", -0.150, 0.007, 0.0),
    "bomb_125_internalx4": ("bomb", -0.120, 0.000, 0.0),
    "bomb_glide1_quad_internal": ("bomb", -0.180, -0.016, 0.0),
    "bomb_250_glide_internalx2": ("bomb", -0.180, 0.021, 0.0),
    "bomb_cluster1_single_internal": ("bomb", -0.175, 0.089, 0.0),
}
skin_at_station = bk * BELLY_Z + bc
bay_offsets = {}
for key, (kind, cy, top, r) in BAY.items():
    if key == "AAM2_double_internal":
        continue
    if kind == "missile":
        dy = -0.067 - cy - RECESS * (r - r_aam2)
    else:
        dy = (skin_at_station - 0.01 - top) - belly[1]
    bay_offsets[key] = dy

gun = (GUN_FLASH[0], GUN_FLASH[1] - 0.038, GUN_FLASH[2] - 0.764)

def f3(v):
    return ", ".join(f"{x:.3f}" for x in v)


def mirror(p):
    return (-p[0], p[1], p[2])


L = []
L += [
    "# Typhoon weapon placement (TyphoonMod). Edit it in the hangar with the placement editor (F8), or by hand.",
    "#",
    "#   <hardpoint>          = x, y, z | pitch, yaw, roll [| hide | show]",
    "#   <hardpoint>/<weapon> = x, y, z | pitch, yaw, roll [| hide | show]",
    "#",
    "# <hardpoint> is the base jet's hardpoint name. x, y, z: metres in the Typhoon model's space (right, up, forward;",
    "# the axes of typhoon.obj, so places follow the model whatever its Offset / ScaleMultiplier).",
    "# pitch, yaw, roll: degrees relative to the aircraft. pitch + = nose down, yaw + = nose right, roll + = right side up.",
    "# <hardpoint>/<weapon>: extra offset while that weapon mount is loaded (mount key, e.g. AAM2_single), in the",
    "# station's own axes; its angles are added on top.",
    "# hide / show: the base jet's launch rails and adapters on that station (stores are never hidden). A weapon",
    "# entry's flag wins over its station's; nothing set = show.",
    "# A hardpoint with no line stays where the base jet has it.",
    "",
    "# --- Wingtip Pylons -> Typhoon outer underwing pylons (nothing on the wingtip pods, as on the real jet).",
    f"#     Missiles {OUTER_PITCH:.1f} deg nose-down; the blade itself is the launcher, so the base jet's rail is hidden",
    "#     and each missile type is raised until its body sits under the blade.",
    f"hardpoint_wingtip_L = {f3(outer)} | {OUTER_PITCH:.1f}, 0.0, 0.0 | hide",
]
for key, (rail, _) in OUTER_WEAPONS.items():
    L.append(f"hardpoint_wingtip_L/{key} = 0.000, {rail - GAP:.3f}, 0.000 | 0.0, 0.0, 0.0")
L.append(f"hardpoint_wingtip_R = {f3(mirror(outer))} | {OUTER_PITCH:.1f}, 0.0, 0.0 | hide")
for key, (rail, _) in OUTER_WEAPONS.items():
    L.append(f"hardpoint_wingtip_R/{key} = 0.000, {rail - GAP:.3f}, 0.000 | 0.0, 0.0, 0.0")
L += [
    "",
    "# --- Wing Pylons -> the middle underwing pylons (pylon_mid_L / _R in typhoon.obj): bottom of the keel, middle",
    "#     of its flat part. The game's own adapters and racks hang from it.",
]
mid = (-MID_X, MID_KEEL_Y, MID_KEEL_Z)
L.append(f"pylon_wing_L = {f3(mid)} | 0.0, 0.0, 0.0 | show")
L.append(f"pylon_wing_R = {f3(mirror(mid))} | 0.0, 0.0, 0.0 | show")
if BAY_STATION:
    pos, rest = BAY_STATION.split("|", 1)
    pos = ", ".join(f"{float(v):.3f}" for v in pos.split())
    L += [
        "",
        "# --- Internal Weapon Bays -> the centre weapon bay: both stations sit on the rotary launcher's axis and their",
        "#     stores go round the drum; the next one to fire waits at the bottom, by the doors.",
        f"weaponbayMount_L = {pos} |{rest}",
        f"weaponbayMount_R = {pos} |{rest}",
    ]
else:
    L += [
        "",
        "# --- Internal Weapon Bays -> under the belly, no pylons: missiles semi-recessed along the fuselage contour",
        f"#     (centre {RECESS:.1f} body radii below the skin line), bombs tucked up under the skin.",
        f"weaponbayMount_L = {f3(belly)} | {belly_pitch:.2f}, 0.0, 0.0",
    ]
    for key, dy in bay_offsets.items():
        L.append(f"weaponbayMount_L/{key} = 0.000, {dy:.3f}, 0.000 | 0.0, 0.0, 0.0")
    L.append(f"weaponbayMount_R = {f3(mirror(belly))} | {belly_pitch:.2f}, 0.0, 0.0")
    for key, dy in bay_offsets.items():
        L.append(f"weaponbayMount_R/{key} = 0.000, {dy:.3f}, 0.000 | 0.0, 0.0, 0.0")
L += [
    "",
    "# --- Internal Cannon -> starboard gun port (the muzzle flash shows 0.76 m ahead of this point).",
    f"cannon = {f3(gun)} | 0.0, 0.0, 0.0",
    "",
]
open(OUT, "w").write("\n".join(L))
print(open(OUT).read())

if STORES:
    def place(st, pitch, local):
        a = math.radians(pitch)
        x, y, z = local
        return (st[0] + x, st[1] + y * math.cos(a) - z * math.sin(a), st[2] + y * math.sin(a) + z * math.cos(a))
    S = []
    for side in (1, -1):
        o = (outer[0] * side, outer[1], outer[2])
        rail = OUTER_WEAPONS["AAM2_single"][0] - GAP
        c = place(o, OUTER_PITCH, (0, -0.254 + rail, 0.17))
        S.append(f"missile {c[0]:.3f} {c[1]:.3f} {c[2]:.3f} {OUTER_PITCH} 0 0 3.6 0.087 0.33")
        m = (mid[0] * side, mid[1], mid[2])
        S.append(f"box {m[0]:.3f} {m[1] - 0.098:.3f} {m[2] - 0.03:.3f} 0 0 0 0.44 0.196 1.21")
        for dx in (-0.36, 0.36):
            S.append(f"missile {m[0] + dx:.3f} {m[1] - 0.258:.3f} {m[2] + 0.075:.3f} 0 0 0 2.9 0.055 0.35")
        b = (belly[0] * side, belly[1], belly[2])
        for dx in (-0.162, 0.184):
            c = place(b, belly_pitch, (dx * (1 if side == 1 else 1), -0.067, 0.30))
            S.append(f"missile {c[0]:.3f} {c[1]:.3f} {c[2]:.3f} {belly_pitch:.2f} 0 0 3.6 0.087 0.33")
    open(STORES, "w").write("\n".join(S) + "\n")
