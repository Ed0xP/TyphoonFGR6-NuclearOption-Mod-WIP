import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

GLB, OBJ_IN, OUT = sys.argv[-3], sys.argv[-2], sys.argv[-1]
os.makedirs(OUT, exist_ok=True)

MAIN_FOLD_RANGE = (88.0, 112.0)
NOSE_SLIDER_Y = -1.62
MAIN_SLIDER_Y = -1.80
BAY_Z = (-2.15, 0.80)
BAY_HALF_OPEN = 0.30
BAY_HALF_WALL = 0.56
SLOT_R = 0.29
STORE_CLEAR = 0.28
DOOR_OPEN_DEG = 100.0
BAY_STORE_Z = 0.30

SWAP = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], float)


def b2u(v):
    return np.array([v[0], v[2], v[1]], float)


def rot_axis_angle(R):
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2))))
    ax = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    n = np.linalg.norm(ax)
    if n < 1e-9:
        w, v = np.linalg.eig(R); ax = np.real(v[:, np.argmin(np.abs(w - 1))]); n = np.linalg.norm(ax)
    return ax / n, ang


def rot(axis, deg):
    a = np.asarray(axis, float); a = a / np.linalg.norm(a)
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    x, y, z = a
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def fit_rigid(A, B):
    keep = np.ones(len(A), bool)
    for _ in range(8):
        a, b = A[keep], B[keep]
        ca, cb = a.mean(0), b.mean(0)
        U, S, Vt = np.linalg.svd((a - ca).T @ (b - cb))
        D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])
        R = Vt.T @ D @ U.T
        t = cb - R @ ca
        e = np.sqrt(((A @ R.T + t - B) ** 2).sum(1))
        keep = e < max(0.005, np.percentile(e[keep], 50) * 1.5)
    return R, t, float(np.median(e[keep])), int(keep.sum())


def point_on_axis(R, t, axis):
    p = np.linalg.lstsq(np.eye(3) - R, t, rcond=None)[0]
    return p - axis * np.dot(p, axis)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
TO_MOD = Matrix.Rotation(math.radians(90), 4, 'Z') @ Matrix.Scale(0.1, 4)


def node_bm(node):
    o = [x for x in bpy.data.objects if x.parent and x.parent.name == node][0]
    bm = bmesh.new(); bm.from_mesh(o.data); bm.transform(TO_MOD @ o.matrix_world)
    bm.faces.ensure_lookup_table(); bm.verts.ensure_lookup_table()
    return bm


on = node_bm("LandingOn_6")
off = node_bm("LandingOff_5")
lamp = node_bm("LandingLight_7")
uv_on = on.loops.layers.uv.active
uv_off = off.loops.layers.uv.active

cell = {}
for v in on.verts:
    cell.setdefault(tuple(round(c / 0.0005) for c in v.co), []).append(v)
parent = list(range(len(on.faces)))


def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]; a = parent[a]
    return a


for vs in cell.values():
    fs = [f.index for v in vs for f in v.link_faces]
    for f in fs[1:]:
        ra, rb = find(fs[0]), find(f)
        if ra != rb: parent[ra] = rb
parts = {}
for f in on.faces:
    parts.setdefault(find(f.index), []).append(f)


def bbox(fs):
    P = np.array([v.co[:] for f in fs for v in f.verts]); return P.min(0), P.max(0)


label = {}
for pid, fs in parts.items():
    mn, mx = bbox(fs)
    s = "R" if (mn[0] + mx[0]) > 0 else "L"
    if mn[1] > 2.0:
        thin_left_plate = mx[0] <= -0.14 and mn[0] >= -0.235 and mn[1] > 3.55 and mx[1] < 5.30 and mn[2] > -1.31
        label[pid] = "nose_door" if thin_left_plate else "nose_leg"
        continue
    amn, amx = sorted((abs(mn[0]), abs(mx[0])))
    if np.sign(mn[0]) != np.sign(mx[0]):
        label[pid] = "main_leg_" + s
    elif amx <= 0.6:
        label[pid] = "main_doorbelly_" + s
    elif amn >= 1.925 and amx > 2.15:
        label[pid] = "main_doorout_" + s
    elif amn >= 1.10 and amx <= 1.56 and mx[2] > -0.30:
        label[pid] = "main_stayup_" + s
    elif 1.45 <= amn <= 1.52 and 1.9 <= amx <= 1.96 and mx[2] < -0.55:
        label[pid] = "main_staylo_" + s
    else:
        label[pid] = "main_leg_" + s
face_label = {f.index: label[pid] for pid, fs in parts.items() for f in fs}

wheel_pids = sorted(parts, key=lambda p: -len(parts[p]))[:3]
for pid in wheel_pids:
    mn, mx = bbox(parts[pid])
    cx = 0.5 * (mn[0] + mx[0])
    lab = "nose_wheel" if mn[1] > 2.0 else "main_wheel_" + ("R" if cx > 0 else "L")
    for f in parts[pid]: face_label[f.index] = lab
for f in on.faces:
    lab = face_label[f.index]
    cy = f.calc_center_median().z
    if lab == "nose_leg" and cy < NOSE_SLIDER_Y: face_label[f.index] = "nose_slider"
    if lab.startswith("main_leg_") and cy < MAIN_SLIDER_Y: face_label[f.index] = "main_slider_" + lab[-1]

def key(f, ul):
    return tuple(sorted((round(l[ul].uv.x, 4), round(l[ul].uv.y, 4)) for l in f.loops))


offkeys = {}
for f in off.faces:
    offkeys.setdefault(key(f, uv_off), []).append(f)


def closed_to_open(pred):
    A, B = [], []
    for g in on.faces:
        if not pred(g): continue
        cand = offkeys.get(key(g, uv_on))
        if not cand: continue
        c = g.calc_center_median()
        cand = [f for f in cand if (f.calc_center_median().x > 0) == (c.x > 0)] or cand
        fm = {(round(l[uv_off].uv.x, 4), round(l[uv_off].uv.y, 4)): l.vert.co for l in cand[0].loops}
        for l in g.loops:
            p = fm.get((round(l[uv_on].uv.x, 4), round(l[uv_on].uv.y, 4)))
            if p is not None:
                A.append(b2u(p)); B.append(b2u(l.vert.co))
    A, B = np.array(A), np.array(B)
    R, t, err, n = fit_rigid(A, B)
    ax, ang = rot_axis_angle(R)
    p = point_on_axis(R, t, ax)
    return dict(axis=ax, angle=ang, point=p, err=err, n=n)


HINGES = {}
HINGES["nose_leg"] = closed_to_open(lambda g: face_label[g.index] in ("nose_leg", "nose_slider", "nose_wheel"))
HINGES["nose_door"] = closed_to_open(lambda g: face_label[g.index] == "nose_door")
for s in "LR":
    HINGES["main_doorout_" + s] = closed_to_open(lambda g, s=s: face_label[g.index] == "main_doorout_" + s)
    HINGES["main_doorbelly_" + s] = closed_to_open(lambda g, s=s: face_label[g.index] == "main_doorbelly_" + s)
for k, h in HINGES.items():
    print(f"hinge {k:18s} {h['angle']:6.1f} deg about {np.round(h['axis'], 3)} through {np.round(h['point'], 3)}  "
          f"(fit {h['err'] * 1000:.2f} mm, {h['n']} points)")

def part_mesh(name, faces_src, src_bm, uvl):
    nb = bmesh.new(); nuv = nb.loops.layers.uv.new("UVMap"); vm = {}
    for f in faces_src:
        vs = []
        for v in f.verts:
            if v.index not in vm: vm[v.index] = nb.verts.new(v.co)
            vs.append(vm[v.index])
        try:
            nf = nb.faces.new(vs)
        except ValueError:
            continue
        for ln, lo in zip(nf.loops, f.loops):
            ln[nuv].uv = lo[uvl].uv
    me = bpy.data.meshes.new(name); nb.to_mesh(me); nb.free()
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(40))
    return me


def mesh_tris(me):
    me.calc_loop_triangles()
    uvd = me.uv_layers.active.data
    cn = me.corner_normals
    P, UV, N = [], [], []
    for tri in me.loop_triangles:
        ls = [tri.loops[0], tri.loops[2], tri.loops[1]]
        P.append([b2u(me.vertices[me.loops[l].vertex_index].co) for l in ls])
        UV.append([tuple(uvd[l].uv) for l in ls])
        N.append([b2u(cn[l].vector) for l in ls])
    return np.array(P), np.array(UV), np.array(N)


groups_new = {}
by_label = {}
for f in on.faces: by_label.setdefault(face_label[f.index], []).append(f)
for lab, fs in sorted(by_label.items()):
    me = part_mesh(lab, fs, on, uv_on)
    groups_new["gear_" + lab] = (*mesh_tris(me), "airframe")
lamp_by_side = {"L": [], "R": []}
for f in lamp.faces: lamp_by_side["R" if f.calc_center_median().x > 0 else "L"].append(f)
for s, fs in lamp_by_side.items():
    if fs:
        me = part_mesh("lamp_" + s, fs, lamp, lamp.loops.layers.uv.active) if lamp.loops.layers.uv.active else None
        if me is None:
            nb = bmesh.new(); nb.loops.layers.uv.new("UVMap"); vm = {}
            for f in fs:
                vs = [vm.setdefault(v.index, nb.verts.new(v.co)) for v in f.verts]
                try: nb.faces.new(vs)
                except ValueError: pass
            me = bpy.data.meshes.new("lamp_" + s); nb.to_mesh(me)
            for p in me.polygons: p.use_smooth = False
        groups_new["gear_main_lamp_" + s] = (*mesh_tris(me), "lamp")


def verts_of(name):
    return groups_new[name][0].reshape(-1, 3)


def bmin(name): return verts_of(name).min(0)
def bmax(name): return verts_of(name).max(0)


def read_obj(path):
    V, VT, VN, groups, cur = [], [], [], [], None
    for line in open(path):
        if line.startswith("v "): V.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("vt "): VT.append([float(x) for x in line.split()[1:3]])
        elif line.startswith("vn "): VN.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("o "): cur = {"name": line[2:].strip(), "mtl": "airframe", "f": []}; groups.append(cur)
        elif line.startswith("usemtl") and cur is not None: cur["mtl"] = line.split()[1]
        elif line.startswith("f ") and cur is not None:
            cur["f"].append([[int(p) if p else 0 for p in (t.split("/") + ["", ""])[:3]] for t in line.split()[1:]])
    V, VT, VN = np.array(V), np.array(VT), np.array(VN)
    out = []
    for g in groups:
        P, UV, N = [], [], []
        for f in g["f"]:
            for i in range(1, len(f) - 1):
                c = [f[0], f[i], f[i + 1]]
                P.append([V[k[0] - 1] for k in c])
                UV.append([VT[k[1] - 1] if k[1] else (0.0, 0.0) for k in c])
                N.append([VN[k[2] - 1] if k[2] else (0.0, 1.0, 0.0) for k in c])
        out.append([g["name"], np.array(P), np.array(UV), np.array(N), g["mtl"]])
    return out


model = read_obj(OBJ_IN)
if any(g[0].startswith(("gear_", "bay_")) for g in model):
    raise SystemExit("typhoon.obj already has the gear and bay (and the bay opening cut into the belly): "
                     "run this on the model from before, e.g. the one from build_mid_pylon.py --merge.")
names = [g[0] for g in model]
print("model groups:", len(model))


def group(name):
    return next(g for g in model if g[0] == name)


def lowest(name_list, x, z):
    best = None
    for nm in name_list:
        P = group(nm)[1]
        a, b, c = P[:, 0], P[:, 1], P[:, 2]
        d = (b[:, 2] - c[:, 2]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 2] - c[:, 2])
        with np.errstate(divide="ignore", invalid="ignore"):
            w1 = ((b[:, 2] - c[:, 2]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (z - c[:, 2])) / d
            w2 = ((c[:, 2] - a[:, 2]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (z - c[:, 2])) / d
        w3 = 1 - w1 - w2
        m = (np.abs(d) > 1e-12) & (w1 >= 0) & (w2 >= 0) & (w3 >= 0)
        if m.any():
            y = (w1[m] * a[m, 1] + w2[m] * b[m, 1] + w3[m] * c[m, 1]).min()
            best = y if best is None else min(best, y)
    return best


GEAR = []


def fmt(v):
    return " ".join(f"{x:.4f}" for x in v)


MAIN = {}
PIV_RAW = {}
for s in "LR":
    strut = verts_of("gear_main_leg_" + s); up = strut[strut[:, 1] > -1.2]; top_y = up[:, 1].max()
    core = up[np.abs(up[:, 1] - (top_y - 0.25)) < 0.12]
    PIV_RAW[s] = np.array([abs(np.median(core[:, 0])), top_y - 0.02, np.median(core[:, 2])])
PIV_SYM = 0.5 * (PIV_RAW["L"] + PIV_RAW["R"])
for s, sx in (("L", -1.0), ("R", 1.0)):
    strut = verts_of("gear_main_leg_" + s)
    wheel = verts_of("gear_main_wheel_" + s)
    wc = 0.5 * (wheel.min(0) + wheel.max(0))
    up = strut[strut[:, 1] > -1.2]
    top_y = up[:, 1].max()
    core = up[np.abs(up[:, 1] - (top_y - 0.25)) < 0.12]
    piv = np.array([sx * PIV_SYM[0], PIV_SYM[1], PIV_SYM[2]])
    axis = np.array([0.0, 0.0, -sx])
    wheel_r = 0.5 * (wheel.max(0)[1] - wheel.min(0)[1])
    best = None
    for ang in np.arange(MAIN_FOLD_RANGE[0], MAIN_FOLD_RANGE[1] + 0.1, 1.0):
        for sh in np.arange(0.0, 0.36, 0.02):
            R = rot(axis, ang)
            w = (wheel - piv + np.array([0, sh, 0])) @ R.T + piv
            xin = np.abs(w[:, 0]).min(); xout = np.abs(w[:, 0]).max()
            cz = w[:, 2].mean()
            bottom = w[:, 1].min()
            door_y = lowest(["geardoors", "fuselage"], sx * 0.6, cz) or -0.75
            pen = max(0.0, 0.17 - xin) * 10 + max(0.0, xout - 1.02) * 10 + max(0.0, door_y + 0.02 - bottom) * 4 \
                  + abs(ang - 95) * 0.002 + sh * 0.05
            if best is None or pen < best[0]:
                best = (pen, ang, sh, xin, xout, bottom, door_y)
    pen, ang, sh, xin, xout, bottom, door_y = best
    print(f"main {s}: pivot {np.round(piv, 3)}, fold {ang:.0f} deg, oleo shortens {sh:.2f} m: "
          f"folded wheel x {xin:.2f}..{xout:.2f}, bottom {bottom:.3f} (door {door_y:.3f})")
    su, sl = verts_of("gear_main_stayup_" + s), verts_of("gear_main_staylo_" + s)
    A = su[np.argmax(su[:, 1])]
    k_up = su[np.argmin(su[:, 1])]
    B = sl[np.argmin(sl[:, 1])]
    k_lo = sl[np.argmax(sl[:, 1])]
    K = 0.5 * (k_up + k_lo)
    MAIN[s] = dict(piv=piv, axis=axis, ang=ang, sh=sh, wc=wc, r=wheel_r, A=A, K=K, B=B)
    GEAR.append(f"unit main_{s} pivot {fmt(piv)} axis {fmt(axis)} fold {ang:.2f} shorten {sh:.3f}")
    GEAR.append(f"  leg gear_main_leg_{s} gear_main_lamp_{s}")
    GEAR.append(f"  slider gear_main_slider_{s} dir 0 1 0")
    GEAR.append(f"  wheel gear_main_wheel_{s} centre {fmt(wc)} axle 1 0 0 radius {wheel_r:.4f}")
    GEAR.append(f"  stay gear_main_stayup_{s} gear_main_staylo_{s} A {fmt(A)} K {fmt(K)} B {fmt(B)}")
    for d in ("doorout", "doorbelly"):
        h = HINGES[f"main_{d}_{s}"]
        GEAR.append(f"  door gear_main_{d}_{s} hinge {fmt(h['point'])} axis {fmt(h['axis'])} open {h['angle']:.2f}")

hn = HINGES["nose_leg"]
nw = verts_of("gear_nose_wheel")
nwc = 0.5 * (nw.min(0) + nw.max(0))
nr = 0.5 * (nw.max(0)[1] - nw.min(0)[1])
GEAR.append(f"unit nose pivot {fmt(hn['point'])} axis {fmt(-hn['axis'])} fold {hn['angle']:.2f} shorten 0.0")
GEAR.append("  leg gear_nose_leg")
GEAR.append("  slider gear_nose_slider dir 0 1 0")
GEAR.append(f"  steer axis 0 1 0 through {fmt(np.array([0.0, nwc[1], nwc[2]]))}")
GEAR.append(f"  wheel gear_nose_wheel centre {fmt(nwc)} axle 1 0 0 radius {nr:.4f}")
hd = HINGES["nose_door"]
GEAR.append(f"  door gear_nose_door hinge {fmt(hd['point'])} axis {fmt(hd['axis'])} open {hd['angle']:.2f}")
main_bottom = min(verts_of("gear_main_wheel_L")[:, 1].min(), verts_of("gear_main_wheel_R")[:, 1].min())
GEAR.append(f"ground main {main_bottom:.4f} nose {nw[:, 1].min():.4f}")

fus = group("fuselage")
z0, z1 = BAY_Z
zs = np.linspace(z0, z1, 13)
pts = []
for z in zs:
    for x in (-BAY_HALF_OPEN, 0.0, BAY_HALF_OPEN):
        y = lowest(["fuselage"], x, z)
        if y is not None: pts.append((z, y))
pts = np.array(pts)
k, c = np.polyfit(pts[:, 0], pts[:, 1], 1)
pitch = math.degrees(math.atan(-k))
print(f"belly under the bay: y = {k:.4f} z + {c:.4f}  ({pitch:.2f} deg), spread {np.ptp(pts[:, 1] - (k * pts[:, 0] + c)):.3f} m")
F = np.array([0.0, k, 1.0]); F /= np.linalg.norm(F)
U = np.array([0.0, 1.0, -k]); U /= np.linalg.norm(U)
Rr = np.array([1.0, 0.0, 0.0])
zc = 0.5 * (z0 + z1)
O = np.array([0.0, k * zc + c, zc])
L_half = 0.5 * (z1 - z0) * np.sqrt(1 + k * k)
top_dev = (pts[:, 1] - (k * pts[:, 0] + c)).max()
O = O + U * top_dev


def frame(r, u, s):
    return O + Rr * r + U * u + F * s


axis_u = SLOT_R + STORE_CLEAR
ceil_u = axis_u + SLOT_R + STORE_CLEAR + 0.03

def clip(poly, keep):
    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        da, db = keep(a[0]), keep(b[0])
        if da >= 0: out.append(a)
        if (da >= 0) != (db >= 0):
            t = da / (da - db)
            out.append(tuple(a[j] + (b[j] - a[j]) * t for j in range(3)))
    return out


P, UVf, Nf, mtl = fus[1], fus[2], fus[3], fus[4]
planes = [lambda p: p[0] + BAY_HALF_OPEN, lambda p: BAY_HALF_OPEN - p[0], lambda p: p[2] - z0, lambda p: z1 - p[2]]
outside, inside = [], []
for i in range(len(P)):
    cen = P[i].mean(0)
    nrm = np.cross(P[i][1] - P[i][0], P[i][2] - P[i][0])
    belly = cen[1] < O[1] + 0.25 and nrm[1] < -1e-6 * np.linalg.norm(nrm) * 0 - 0.3 * np.linalg.norm(nrm)
    tri = [(P[i][j], UVf[i][j], Nf[i][j]) for j in range(3)]
    if not belly or cen[2] < z0 - 1 or cen[2] > z1 + 1 or abs(cen[0]) > BAY_HALF_OPEN + 1:
        outside.append(tri); continue
    poly_in = tri
    for pl in planes: poly_in = clip(poly_in, pl) if poly_in else []
    rest = tri
    for pl in planes:
        if not rest: break
        o = clip(rest, lambda p, pl=pl: -pl(p))
        if len(o) >= 3: outside.append(o)
        rest = clip(rest, pl)
    if len(poly_in) >= 3: inside.append(poly_in)


def fan(polys):
    T = []
    for poly in polys:
        for j in range(1, len(poly) - 1):
            T.append([poly[0], poly[j], poly[j + 1]])
    return (np.array([[c[0] for c in t] for t in T]), np.array([[c[1] for c in t] for t in T]),
            np.array([[c[2] for c in t] for t in T]))


fus[1], fus[2], fus[3] = fan(outside)
door_polys = {"L": [], "R": []}
for poly in inside:
    for s, sgn in (("L", -1), ("R", 1)):
        half = clip(poly, lambda p, sgn=sgn: sgn * p[0])
        if len(half) >= 3: door_polys[s].append(half)
for s, sgn in (("L", -1), ("R", 1)):
    Pd, UVd, Nd = fan(door_polys[s])
    groups_new["bay_door_" + s] = (Pd, UVd, Nd, "airframe")
    Pi = Pd[:, ::-1, :] + U * 0.012
    Ni = -Nd[:, ::-1, :]
    groups_new["bay_doorinner_" + s] = (Pi, UVd[:, ::-1, :], Ni, "bayinner")
    edge = Pd.reshape(-1, 3)
    edge = edge[np.abs(np.abs(edge[:, 0]) - BAY_HALF_OPEN) < 0.002]
    u_edge = np.median((edge - O) @ U) if len(edge) else 0.0
    hinge = frame(sgn * BAY_HALF_OPEN, u_edge + 0.006, 0.0)
    ax = F * (1 if s == "L" else -1)
    test = (np.array([0.0, hinge[1], zc]) - hinge) @ rot(ax, 60).T + hinge
    if test[1] > hinge[1]: ax = -ax
    GEAR.append(f"baydoor bay_door_{s} bay_doorinner_{s} hinge {fmt(hinge)} axis {fmt(ax)} open {DOOR_OPEN_DEG:.1f}")
print("bay doors:", {s: len(v) for s, v in door_polys.items()}, "belly triangles left", len(fus[1]))


def quad(a, b, c, d, n):
    tris = [[a, b, c], [a, c, d]]
    out = []
    for t in tris:
        if np.dot(np.cross(t[1] - t[0], t[2] - t[0]), n) < 0: t = [t[0], t[2], t[1]]
        out.append(t)
    return out


def box_tris(cmin, cmax, inward=False):
    (r0, u0, s0), (r1, u1, s1) = cmin, cmax
    Pts = {}
    for i, r in enumerate((r0, r1)):
        for j, u in enumerate((u0, u1)):
            for kk, s_ in enumerate((s0, s1)):
                Pts[(i, j, kk)] = frame(r, u, s_)
    faces = [((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1), -Rr), ((1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0), Rr),
             ((0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0), -U), ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1), U),
             ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), -F), ((0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1), F)]
    T, Nn = [], []
    for a, b, c_, d, n in faces:
        n = -n if inward else n
        for t in quad(Pts[a], Pts[b], Pts[c_], Pts[d], n):
            T.append(t); Nn.append([n, n, n])
    return T, Nn


def pack(T, Nn, uvscale=0.0):
    T = np.array(T); Nn = np.array(Nn)
    UV = np.zeros(T.shape[:2] + (2,))
    return T, UV, Nn


T, Nn = box_tris((-BAY_HALF_WALL, -0.02, -L_half), (BAY_HALF_WALL, ceil_u, L_half), inward=True)
keep = [i for i, n in enumerate(Nn) if not np.allclose(n[0], U)]
T = [T[i] for i in keep]; Nn = [Nn[i] for i in keep]
for sf in np.arange(-L_half + 0.45, L_half - 0.3, 0.5):
    for cmin, cmax in (((-BAY_HALF_WALL, 0.02, sf), (-BAY_HALF_WALL + 0.04, ceil_u, sf + 0.035)),
                       ((BAY_HALF_WALL - 0.04, 0.02, sf), (BAY_HALF_WALL, ceil_u, sf + 0.035)),
                       ((-BAY_HALF_WALL, ceil_u - 0.04, sf), (BAY_HALF_WALL, ceil_u, sf + 0.035))):
        t2, n2 = box_tris(cmin, cmax)
        T += t2; Nn += n2
groups_new["bay_box"] = (*pack(T, Nn), "baywall")

def cylinder(r, s0, s1, seg=24, u_c=axis_u):
    T, Nn = [], []
    for i in range(seg):
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        p = lambda a, s_: frame(r * math.sin(a), u_c - r * math.cos(a), s_)
        n0 = Rr * math.sin(a0) - U * math.cos(a0); n1 = Rr * math.sin(a1) - U * math.cos(a1)
        for t, nn in ((([p(a0, s0), p(a1, s0), p(a1, s1)]), [n0, n1, n1]), (([p(a0, s0), p(a1, s1), p(a0, s1)]), [n0, n1, n0])):
            if np.dot(np.cross(t[1] - t[0], t[2] - t[0]), nn[0] + nn[1]) < 0:
                t = [t[0], t[2], t[1]]; nn = [nn[0], nn[2], nn[1]]
            T.append(t); Nn.append(nn)
        for s_, nn in ((s0, -F), (s1, F)):
            t = [frame(0, u_c, s_), p(a0, s_), p(a1, s_)]
            if np.dot(np.cross(t[1] - t[0], t[2] - t[0]), nn) < 0: t = [t[0], t[2], t[1]]
            T.append(t); Nn.append([nn, nn, nn])
    return T, Nn


T, Nn = cylinder(0.055, -L_half + 0.04, L_half - 0.04)
for s_end in (-L_half + 0.07, L_half - 0.10):
    t2, n2 = cylinder(0.11, s_end, s_end + 0.03)
    T += t2; Nn += n2
    for i in range(8):
        a = 2 * math.pi * i / 8
        d = Rr * math.sin(a) - U * math.cos(a)
        side = np.cross(F, d)
        c0 = frame(0, axis_u, s_end)
        corners = [c0 + side * w + F * f_ + d * rr for rr in (0.1, SLOT_R + 0.03) for w in (-0.018, 0.018) for f_ in (0, 0.03)]
        idx = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        cen = np.mean(corners, 0)
        for q in idx:
            pa, pb, pc, pd = [corners[j] for j in q]
            nq = np.cross(pb - pa, pc - pa); nq /= np.linalg.norm(nq)
            if np.dot(nq, (pa + pc) / 2 - cen) < 0: nq = -nq
            for t in quad(pa, pb, pc, pd, nq):
                T.append(t); Nn.append([nq, nq, nq])
groups_new["bay_drum"] = (*pack(T, Nn), "drum")
drum_axis_point = frame(0, axis_u, 0)
GEAR.append(f"bay frame {fmt(O)} forward {fmt(F)} up {fmt(U)} halflength {L_half:.4f}")
GEAR.append(f"drum bay_drum axis {fmt(F)} through {fmt(drum_axis_point)} slot {SLOT_R:.3f}")
station = drum_axis_point - F * BAY_STORE_Z
GEAR.append(f"# bay stations (typhoon_hardpoints.txt): {fmt(station)} | {pitch:.2f}, 0.0, 0.0 | rotary")
print("bay station:", np.round(station, 3), "pitch", round(pitch, 2))

def write_obj(path, groups):
    lines = ["# Eurofighter Typhoon for Nuclear Option.",
             "# Source model: 'Eurofighter Typhoon - Fighter Jet - Free' by bohmerang (Sketchfab), CC BY-NC-SA 4.0.",
             "# Converted and split into parts for the mod (gear and weapon bay: build_gear_bay.py).",
             "# Unity axes: +X right, +Y up, +Z forward, metres."]
    vb = tb = nb = 1
    for name, P, UV, N, mtl in groups:
        if len(P) == 0: continue
        lines.append(f"o {name}"); lines.append(f"usemtl {mtl}")
        vi, ti, ni = {}, {}, {}
        vl, tl, nl, fl = [], [], [], []
        for t in range(len(P)):
            idx = []
            for j in range(3):
                kv = tuple(np.round(P[t][j], 5)); kt = tuple(np.round(UV[t][j], 6)); kn = tuple(np.round(N[t][j], 4))
                if kv not in vi: vi[kv] = len(vl); vl.append(kv)
                if kt not in ti: ti[kt] = len(tl); tl.append(kt)
                if kn not in ni: ni[kn] = len(nl); nl.append(kn)
                idx.append(f"{vb + vi[kv]}/{tb + ti[kt]}/{nb + ni[kn]}")
            fl.append("f " + " ".join(idx))
        lines += ["v %.5f %.5f %.5f" % v for v in vl] + ["vt %.6f %.6f" % t for t in tl] + ["vn %.4f %.4f %.4f" % n for n in nl] + fl
        vb += len(vl); tb += len(tl); nb += len(nl)
    open(path, "w").write("\n".join(lines) + "\n")


allg = [tuple(g) for g in model] + [(k, *v) for k, v in groups_new.items()]
write_obj(os.path.join(OUT, "typhoon.obj"), allg)
with open(os.path.join(OUT, "typhoon_gear.txt"), "w") as f:
    f.write("# Typhoon landing gear and weapon bay (build_gear_bay.py). Unity axes, metres, model space; read by TyphoonMod.\n"
            "# unit <name> pivot <p> axis <a> fold <deg> shorten <m> : the leg turns about a by fold * the game's gear fold\n"
            "#   leg / slider / wheel / steer / stay / door lines belong to the unit above them\n"
            "#   door <part> hinge <p> axis <a> open <deg> : modelled open; closes by turning -open about a\n"
            "# baydoor <part> <inner part> hinge <p> axis <a> open <deg> : modelled closed; opens by turning +open\n"
            "# drum <part> axis <a> through <p> slot <r> : rotary launcher\n")
    f.write("\n".join(GEAR) + "\n")
print(open(os.path.join(OUT, "typhoon_gear.txt")).read())

for name, P, UV, N, mtl in [(k, *v) for k, v in groups_new.items()]:
    me = bpy.data.meshes.new(name)
    verts = [Vector((p[0], p[2], p[1])) for t in P for p in t]
    me.from_pydata(verts, [], [(3 * i, 3 * i + 2, 3 * i + 1) for i in range(len(P))])
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
for o in list(bpy.data.objects):
    if not (o.type == 'MESH' and (o.name.startswith("gear_") or o.name.startswith("bay_"))): bpy.data.objects.remove(o)
for coll in (bpy.data.images, bpy.data.materials, bpy.data.textures):
    for item in list(coll): coll.remove(item)
for me in list(bpy.data.meshes):
    if me.users == 0: bpy.data.meshes.remove(me)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.abspath(OUT), "gear_bay.blend"))
