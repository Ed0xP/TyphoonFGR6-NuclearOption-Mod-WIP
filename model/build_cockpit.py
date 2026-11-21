import math
import os
import sys

import bpy
import bmesh
import numpy as np
from PIL import Image, ImageFilter
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ckmodel as ck

OBJ_IN, TEX_IN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PREVIEW = os.environ.get("PREVIEW", "")
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)


HUD_GLB = os.environ.get("HUD_GLB", "")
HUD_PANES = None
if HUD_GLB and os.path.exists(HUD_GLB):
    bpy.ops.import_scene.gltf(filepath=HUD_GLB)
    _e = bpy.data.objects.get("HUD_3")
    _kids = [c for c in _e.children_recursive if c.type == 'MESH'] if _e else []
    if _kids:
        _TO_MOD = Matrix.Rotation(math.radians(90), 4, 'Z') @ Matrix.Scale(0.1, 4)
        HUD_PANES = bmesh.new()
        HUD_PANES.from_mesh(_kids[0].data)
        HUD_PANES.transform(_TO_MOD @ _kids[0].matrix_world)
        bmesh.ops.remove_doubles(HUD_PANES, verts=HUD_PANES.verts[:], dist=0.0003)
        HUD_PANES.normal_update()
        for f in list(HUD_PANES.faces):
            if f.normal.y > -0.2:
                HUD_PANES.faces.remove(f)
        for v in [v for v in HUD_PANES.verts if not v.link_faces]:
            HUD_PANES.verts.remove(v)
        print(f"HUD glass: {len(HUD_PANES.faces)} faces from the GLB")
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.textures):
        for it in list(coll):
            if it.users == 0:
                coll.remove(it)

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
if any(g[0] in ("cockpit_seat", "cockpit_controls") for g in model):
    raise SystemExit("typhoon.obj already has the cockpit detail pass: run this on the model from build_gear_bay.py.")


def group(name):
    return next(g for g in model if g[0] == name)


def u2b(p):
    return Vector((p[0], p[2], p[1]))


def bm_from_tris(P, UV=None):
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    for t in range(len(P)):
        vs = [bm.verts.new(u2b(P[t][j])) for j in (0, 2, 1)]
        try:
            f = bm.faces.new(vs)
        except ValueError:
            continue
        if UV is not None:
            for lp, j in zip(f.loops, (0, 2, 1)):
                lp[uvl].uv = UV[t][j]
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.normal_update()
    return bm


shell_name = "canopy_interior"
shell = group(shell_name)
SHELL_ORIG = (shell[1].copy(), shell[2].copy())

SEAT_BOX = ((-0.33, 0.25, 5.5), (0.33, 1.45, 6.8))


def loose_parts(P):
    key = {}
    tri_v = np.zeros((len(P), 3), int)
    for t in range(len(P)):
        for j in range(3):
            tri_v[t, j] = key.setdefault(tuple(np.round(P[t][j], 4)), len(key))
    par = np.arange(len(key))

    def fnd(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for t in range(len(P)):
        for j in (1, 2):
            ra, rb = fnd(tri_v[t, 0]), fnd(tri_v[t, j])
            if ra != rb:
                par[ra] = rb
    roots = np.array([fnd(tri_v[t, 0]) for t in range(len(P))])
    return [np.nonzero(roots == r)[0] for r in np.unique(roots)]


lo, hi = np.array(SEAT_BOX[0]), np.array(SEAT_BOX[1])
JUNK_BOX = ((-0.400, 0.688, 7.168), (-0.305, 0.731, 7.285))
jlo, jhi = np.array(JUNK_BOX[0]), np.array(JUNK_BOX[1])
keep = np.ones(len(shell[1]), bool)
junk = np.zeros(len(shell[1]), bool)
n_old = n_junk = 0
for idx in loose_parts(shell[1]):
    pts = shell[1][idx].reshape(-1, 3)
    if (pts.min(0) >= lo).all() and (pts.max(0) <= hi).all():
        keep[idx] = False
        n_old += 1
    elif (pts.min(0) >= jlo).all() and (pts.max(0) <= jhi).all():
        junk[idx] = True
        n_junk += 1
print(f"old seat: {n_old} loose parts, {np.count_nonzero(~keep)} triangles removed; under the left keypad: {n_junk} loose parts, {np.count_nonzero(junk)} triangles removed")
OLD_SEAT = [shell[1][~keep], shell[2][~keep], shell[3][~keep]]
keep &= ~junk
for k in (1, 2, 3):
    shell[k] = shell[k][keep]

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("cockpit_extra", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cockpit_extra.py"))
cxm = _ilu.module_from_spec(_spec); _spec.loader.exec_module(cxm)
ARCH_PARTS = [((-0.45, 0.68, 4.63), (0.45, 1.33, 7.37)), ((-0.44, 0.65, 7.05), (0.44, 1.30, 8.56))]
sel = np.zeros(len(shell[1]), bool)
for idx in loose_parts(shell[1]):
    pts = shell[1][idx].reshape(-1, 3)
    for a_, b_ in ARCH_PARTS:
        if len(idx) > 100 and (np.abs(pts.min(0) - a_) < 0.02).all() and (np.abs(pts.max(0) - b_) < 0.02).all():
            sel[idx] = True
if sel.any() and not os.environ.get("NO_ARCH_SMOOTH"):
    abm = bm_from_tris(shell[1][sel], shell[2][sel])
    bmesh.ops.join_triangles(abm, faces=abm.faces[:], angle_face_threshold=math.radians(25),
                             angle_shape_threshold=math.radians(45), cmp_uvs=True, cmp_seam=False, cmp_sharp=False)
    n_in = len(abm.faces)
    abm = cxm.smooth_part(abm, 2, crease_angle=50)
    tmp = ck.obj_from_bm("arch_tmp", abm)
    tmp["smooth"] = 50.0
    Pb, UVb, Nb = ck.triangles(tmp)
    ck.remove(tmp)
    Pa, UVa, Na = ck.to_unity(Pb, UVb, Nb)
    for k, arr in ((1, Pa), (2, UVa), (3, Na)):
        shell[k] = np.concatenate([shell[k][~sel], arr])
    print(f"canopy arch smoothed: {np.count_nonzero(sel)} triangles ({n_in} faces) -> {len(Pa)}")

shell_bm = bm_from_tris(shell[1], shell[2])
shell_bvh = BVHTree.FromBMesh(shell_bm)

PACK_REGION = (0.0, 0.20, 0.80, 1.0)
STRIP_H = 0.016
_strip_next = [0.0]
CUSTOM = {}


def strip_rect(kind, length_m, px_per_m=2600.0, extra=None):
    w = min(length_m * px_per_m / 4096.0, 1.0)
    v0 = 0.0625 + _strip_next[0]
    _strip_next[0] += STRIP_H + 0.002
    assert v0 + STRIP_H < PACK_REGION[1], "strip band full"
    r = (0.0625 + 0.0, v0, 0.0625 + w * 0.93, v0 + STRIP_H)
    CUSTOM[len(CUSTOM)] = (r, kind, extra)
    return r


QRB_RECT = (0.0, 0.0, 0.0625, 0.0625)
CUSTOM["qrb"] = (QRB_RECT, "qrbface", None)
SW = {}
for i, name in enumerate(["black", "chrome", "white", "yellow", "red", "darkgrey", "hazard", "olive", "metal", "green",
                          "orange", "ltgrey", "keyblue", "pedgrey", "boxgrey"]):
    u0 = 0.75 + (i % 8) * 0.03125
    v0 = 0.0 + (i // 8) * 0.03125
    SW[name] = (u0 + 0.0156, v0 + 0.0156)
    CUSTOM["sw_" + name] = ((u0, v0, u0 + 0.03125, v0 + 0.03125), "swatch", name)

import ctl_parts
for _cn, _cr in ctl_parts.CELLS.items():
    CUSTOM["tx_" + _cn] = (_cr, "swtex", _cn)

parts = []


def add(name, bm, surface, group="cockpit_seat", uvmode="pack", smooth=40.0):
    parts.append(ck.part(name, bm, surface, group, uvmode, smooth))
    return parts[-1]


S = Vector((0.0, 6.66, 0.47))
EX = Vector((1, 0, 0))
EB = Vector((0, -0.38, 0.925)).normalized()
EN = EB.cross(EX).normalized()
a5 = math.radians(5)
EF = Vector((0, math.cos(a5), math.sin(a5)))
EU = EX.cross(EF).normalized()
FB = ck.frame(EX, EB, EN)
FP = ck.frame(EX, EF, EU)


def pb(x, b, n):
    return S + EX * x + EB * b + EN * n


def pp(x, f, u):
    return S + EX * x + EF * f + EU * u


bm = bmesh.new()
prof = [(-0.20, -0.01), (0.20, -0.01), (0.20, 0.355), (0.065, 0.355), (0.065, 0.215), (-0.065, 0.215), (-0.065, 0.355), (-0.20, 0.355)]
ck.prism_profile(bm, prof, pp(0, 0, -0.035), FP, 0.07)
bm = ck.modded(bm, bevel=0.022, seg=4, angle=40)
add("seat_pan", bm, "fabric", smooth=50)
for sx in (-1, 1):
    bm = ck.rbox(pp(sx * 0.175, 0.17, 0.012), (0.055, 0.33, 0.05), FP, bevel=0.022, seg=4)
    add(f"seat_thighroll_{'LR'[sx > 0]}", bm, "fabric_dark", smooth=60)
bm = ck.rbox(pp(0, 0.16, -0.135), (0.42, 0.36, 0.13), FP, bevel=0.012, seg=2)
add("seat_pack", bm, "fabric_dark", smooth=35)

bm = ck.rbox(pb(0, 0.30, -0.035), (0.30, 0.60, 0.06), FB, bevel=0.02, seg=4)
add("seat_back", bm, "mesh", smooth=50)
for sx in (-1, 1):
    bm = ck.rbox(pb(sx * 0.175, 0.29, -0.02), (0.07, 0.56, 0.085), FB, bevel=0.026, seg=4)
    add(f"seat_bolster_{'LR'[sx > 0]}", bm, "fabric_dark", smooth=60)
bm = ck.tube([pb(-0.15, 0.04, -0.005), pb(0.15, 0.04, -0.005)], 0.03, seg=14, up=EN)[0]
add("seat_lumbar", bm, "fabric", smooth=60)

bm = ck.rbox(pb(0, 0.30, -0.17), (0.42, 0.68, 0.19), FB, bevel=0.02, seg=3)
add("seat_shell", bm, "black", smooth=35)
bm = ck.rbox(pb(0, 0.765, -0.16), (0.30, 0.37, 0.27), FB, bevel=0.028, seg=4)
add("seat_headbox", bm, "black", smooth=35)
bm = ck.rbox(pb(0, 0.75, -0.012), (0.20, 0.23, 0.05), FB, bevel=0.02, seg=4)
add("seat_headpad", bm, "fabric_dark", smooth=60)
for sx in (-1, 1):
    bm = bmesh.new()
    ck.prism_profile(bm, [(-0.03, 0.0), (0.03, 0.0), (0.0, 0.07)], pb(sx * 0.085, 0.948, -0.09), ck.frame(EN, EB, EX), 0.018)
    bm = ck.modded(bm, bevel=0.004, seg=2)
    add(f"seat_breaker_{'LR'[sx > 0]}", bm, "metal", smooth=30)
bm = ck.rbox(pb(0, 0.948, -0.20), (0.26, 0.012, 0.16), FB, bevel=0.004, seg=2)
add("seat_headbox_band", bm, "darkgrey", smooth=30)
bm = ck.tube([pb(0.0, 0.955, -0.24), pb(0.0, 1.0, -0.24)], 0.028, seg=16, up=EN)[0]
add("seat_drogue", bm, "darkgrey", smooth=40)

for sx in (-1, 1):
    x0 = sx * 0.218
    outline = [pp(x0, 0.31, -0.21), pp(x0, 0.31, 0.03), pp(x0, 0.18, 0.06), pp(x0, 0.02, 0.10),
               pb(x0, 0.20, 0.05), pb(x0, 0.40, 0.0), pb(x0, 0.50, -0.08), pb(x0, 0.60, -0.14), pb(x0, 0.60, -0.26),
               pb(x0, -0.10, -0.26), pp(x0, -0.12, -0.21)]
    bm = bmesh.new()
    t = 0.022
    v0 = [bm.verts.new(p - EX * t / 2) for p in outline]
    v1 = [bm.verts.new(p + EX * t / 2) for p in outline]
    n = len(outline)
    bm.faces.new(v0)
    bm.faces.new(list(reversed(v1)))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([v0[i], v1[i], v1[j], v0[j]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm = ck.modded(bm, bevel=0.009, seg=3, angle=30)
    add(f"seat_side_{'LR'[sx > 0]}", bm, "carbon", smooth=35)
    bm = ck.rbox(pp(sx * 0.234, 0.24, -0.04), (0.018, 0.07, 0.035), FP, bevel=0.006, seg=2)
    add(f"seat_sidebox_{'LR'[sx > 0]}", bm, "black", smooth=30)
for sx in (-1, 1):
    bm = ck.rbox(pb(sx * 0.11, 0.42, -0.285), (0.045, 1.16, 0.04), FB, bevel=0.006, seg=2)
    add(f"seat_rail_{'LR'[sx > 0]}", bm, "metal", smooth=30)

loop = [pp(-0.045, 0.252, -0.07), pp(-0.045, 0.262, 0.03), pp(-0.040, 0.255, 0.085), pp(-0.018, 0.245, 0.112),
        pp(0.0, 0.243, 0.116), pp(0.018, 0.245, 0.112), pp(0.040, 0.255, 0.085), pp(0.045, 0.262, 0.03), pp(0.045, 0.252, -0.07)]
path = ck.catmull(loop, 6)
L = sum((path[i + 1] - path[i]).length for i in range(len(path) - 1))
bm, _ = ck.tube(path, 0.0078, seg=14, up=EF, uv_rect=strip_rect("handle", L, 2600))
add("seat_handle", bm, "custom", uvmode="custom", smooth=60)
bm = ck.rbox(pp(0, 0.258, -0.06), (0.12, 0.05, 0.04), FP, bevel=0.008, seg=2)
add("seat_handle_base", bm, "black", smooth=30)

QRB_C = pp(0.0, 0.135, 0.014)
QRB_AX = (EU * 0.9 + EN * 0.1).normalized()
bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")
r0, r1 = ck.cylinder(bm, QRB_C, QRB_AX, 0.044, 0.018, seg=40, r_top=0.042)
t_ax = (EF - QRB_AX * EF.dot(QRB_AX)).normalized()
b_ax = QRB_AX.cross(t_ax)
u0, v0, u1, v1 = QRB_RECT
for f in bm.faces:
    for lp in f.loops:
        d = lp.vert.co - QRB_C
        su, sv = d.dot(b_ax) / 0.09 + 0.5, -d.dot(t_ax) / 0.09 + 0.5
        lp[uvl].uv = (u0 + (u1 - u0) * su, v0 + (v1 - v0) * sv)
bm = ck.modded(bm, bevel=0.003, seg=2, angle=40)
add("seat_qrb", bm, "custom", uvmode="custom", smooth=40)

WEB_W, WEB_T = 0.044, 0.003


def strap(name, pts, nrms, surface, width=WEB_W):
    path, nn = [], []
    P = [Vector(p) for p in pts]
    N = [Vector(n) for n in nrms]
    sm = ck.catmull(P, 5)
    seglen = [0.0]
    for i in range(1, len(sm)):
        seglen.append(seglen[-1] + (sm[i] - sm[i - 1]).length)
    cl = [0.0]
    for i in range(1, len(P)):
        cl.append(cl[-1] + (P[i] - P[i - 1]).length)
    for i, p in enumerate(sm):
        s = seglen[i] / seglen[-1] * cl[-1]
        k = max(0, min(len(P) - 2, next((j for j in range(len(P) - 1) if cl[j + 1] >= s), len(P) - 2)))
        w = (s - cl[k]) / max(cl[k + 1] - cl[k], 1e-6)
        nn.append((N[k] * (1 - w) + N[k + 1] * w).normalized())
        path.append(p)
    rect = strip_rect(surface, seglen[-1], 2600)
    bm, _ = ck.ribbon(path, nn, width, WEB_T, uv_rect=rect)
    add(name, bm, "custom", uvmode="custom", smooth=30)


for sx in (-1, 1):
    side = 'LR'[sx > 0]
    strap(f"seat_shoulder_{side}",
          [pb(sx * 0.07, 0.62, -0.03), pb(sx * 0.07, 0.60, 0.004), pb(sx * 0.066, 0.42, 0.006), pb(sx * 0.06, 0.22, 0.006),
           pb(sx * 0.055, 0.09, 0.008), pp(sx * 0.05, 0.03, 0.03), pp(sx * 0.04, 0.085, 0.022), QRB_C + EF * -0.03 + EX * sx * 0.022 + EU * 0.012],
          [-EB, EN, EN, EN, EN, (EN + EU).normalized(), EU, EU], "webbing")
    strap(f"seat_lap_{side}",
          [pp(sx * 0.215, 0.05, -0.02), pp(sx * 0.19, 0.07, 0.01), pp(sx * 0.13, 0.10, 0.012), QRB_C + EX * sx * 0.038 + EU * 0.01],
          [EX * -sx, (EU - EX * sx).normalized(), EU, EU], "webbing_grey")
    bm = ck.rbox(pb(sx * 0.066, 0.36, 0.010), (0.052, 0.03, 0.008), FB, bevel=0.002, seg=1)
    add(f"seat_buckle_{side}", bm, "metal", smooth=30)
strap("seat_negg", [pp(0.0, 0.21, -0.005), pp(0.0, 0.185, 0.012), QRB_C + EF * 0.04 + EU * 0.01], [EU, EU, EU], "webbing", 0.04)

print(f"seat: {len(parts)} parts")

TEX_W, TEX_H = 2828, 4138
SP, SUV = shell[1], shell[2]


def locate(px, py):
    u, v = (px + 0.5) / TEX_W, 1.0 - (py + 0.5) / TEX_H
    a, b, c = SUV[:, 0], SUV[:, 1], SUV[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    with np.errstate(divide="ignore", invalid="ignore"):
        w1 = ((b[:, 1] - c[:, 1]) * (u - c[:, 0]) + (c[:, 0] - b[:, 0]) * (v - c[:, 1])) / d
        w2 = ((c[:, 1] - a[:, 1]) * (u - c[:, 0]) + (a[:, 0] - c[:, 0]) * (v - c[:, 1])) / d
    w3 = 1 - w1 - w2
    m = (np.abs(d) > 1e-14) & (w1 >= -1e-6) & (w2 >= -1e-6) & (w3 >= -1e-6)
    idx = np.nonzero(m)[0]
    if len(idx) == 0:
        return None
    t = idx[0]
    p = w1[t] * SP[t, 0] + w2[t] * SP[t, 1] + w3[t] * SP[t, 2]
    n = np.cross(SP[t, 1] - SP[t, 0], SP[t, 2] - SP[t, 0])
    n /= np.linalg.norm(n)
    return u2b(p), u2b(n), t


def uv_at(t, q_b):
    P = [np.array(u2b(SP[t, j])) for j in range(3)]
    q = np.array(q_b)
    v0, v1, v2 = P[1] - P[0], P[2] - P[0], q - P[0]
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    b1 = (d11 * d20 - d01 * d21) / den
    b2 = (d00 * d21 - d01 * d20) / den
    return tuple((1 - b1 - b2) * SUV[t, 0] + b1 * SUV[t, 1] + b2 * SUV[t, 2])


def local_frame(n):
    up = Vector(n).normalized()
    fwd = Vector((0, 1, 0))
    fwd = (fwd - up * fwd.dot(up))
    if fwd.length < 0.2:
        fwd = Vector((0, 0, 1)) - up * up.z
    fwd.normalize()
    right = fwd.cross(up).normalized()
    return ck.frame(right, fwd, up)


feats = []
for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cockpit_features.txt")):
    t = line.split("#")[0].split()
    if not t:
        continue
    kind = t[0]
    xs = t[1]
    x = float(xs[1:]) + 1159 if xs.startswith("+") else float(xs)
    y = float(t[2])
    size = t[3] if len(t) > 3 else None
    feats.append((kind, x, y, size))

try:
    from PIL import Image
    from scipy import ndimage as ndi
    _B = np.asarray(Image.open(os.path.join(TEX_IN, "cockpit_base.png")).convert("RGB")).astype(np.float32) / 255
    _lum = _B.mean(2)
    _bg = ndi.gaussian_filter(ndi.maximum_filter(_lum, 41), 20)
    _ratio = _lum / np.maximum(_bg, 1e-3)
    _panel = ndi.binary_erosion(ndi.uniform_filter((_bg > 0.30).astype(float), 5) > 0.99, iterations=6)
    _dark = ndi.binary_opening((_ratio < 0.5) & _panel, iterations=1)
    _lab, _n = ndi.label(_dark)
    n_f = 0
    for i, sl in enumerate(ndi.find_objects(_lab)):
        msk = _lab[sl] == i + 1
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        s = max(h, w)
        if not (7 <= s <= 16) or msk.sum() / (h * w) < 0.5 or max(h, w) / max(min(h, w), 1) > 1.6:
            continue
        cy, cx = ndi.center_of_mass(msk)
        cx += sl[1].start; cy += sl[0].start
        if any(abs(cx - f[1]) < 22 and abs(cy - f[2]) < 22 for f in feats):
            continue
        loc = locate(cx, cy)
        if loc is None:
            continue
        pu = loc[0]; nu = loc[1]
        if abs(pu.x) > 0.25 and nu.z > 0.6:
            feats.append(("fastener", cx, cy, None))
            n_f += 1
    print(f"fasteners from the texture: {n_f}")
except ImportError as e:
    print("no fastener detection:", e)

ctrl_bms = []
SW_PARTS, SW_LINES = [], []
relief_bms = []
SWR = {k: v[0] for k, v in CUSTOM.items() if isinstance(k, str) and k.startswith("sw_")}


def sw(bm, name):
    return ck.set_uv_all(bm, SW[name])


def planar_uv(bm, rect, origin, ax_u, ax_v, size_u, size_v):
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = rect
    for f in bm.faces:
        for lp in f.loops:
            d = lp.vert.co - origin
            su = min(max(d.dot(ax_u) / size_u + 0.5, 0.02), 0.98)
            sv = min(max(d.dot(ax_v) / size_v + 0.5, 0.02), 0.98)
            lp[uvl].uv = (u0 + (u1 - u0) * su, v0 + (v1 - v0) * sv)
    return bm


def place(bm, pos, F, lift=0.0004):
    M = Matrix.Translation(pos + F.col[2] * lift) @ F.to_4x4()
    bm.transform(M)
    return bm


def proto_toggle(tilt_deg, s=1.0):
    return ctl_parts.toggle(sw, "bat", lean=tilt_deg, lean_dir=90.0, s=s)


def proto_knob(d, pointer=False, body="black", tall=0.85, ribs=18, seg=28):
    return ctl_parts.knob(sw, d, "pointer" if pointer else "plain", 0.0)


def proto_fastener():
    b = bmesh.new(); ck.cylinder(b, (0, 0, 0), (0, 0, 1), 0.0034, 0.0009, seg=10, r_top=0.0029)
    sw(b, "darkgrey")
    s = ck.rbox(Vector((0, 0, 0.001)), (0.0045, 0.0008, 0.0004), bevel=0); sw(s, "black")
    return ck.merge([b, s])


THR_C = Vector((float(os.environ.get("THR_X", "-0.405")), float(os.environ.get("THR_Y", "6.915")), float(os.environ.get("THR_Z", "0.4843"))))
n_kind = {}
CTRL_LIST = []
import console_layout
import gear_panel
import pedestal
import dwp_panel
import nve_panel
import console_panel
import json
LAYOUTS = [(L_, sd_) for L_, sd_ in ((console_layout.load("console_right.txt"), 1), (console_layout.load("console_left.txt"), -1),
                                    (console_layout.load("console_gear.txt"), -1), (console_layout.load("console_pedestal.txt"), 1),
                                    (console_layout.load("console_rfwd.txt"), 1)) if L_ is not None]
for _L, _sd in LAYOUTS:
    if _sd in console_panel.FILES and os.path.basename(console_panel.FILES[_sd][0]) in ("console_right.txt", "console_left.txt") and _L.x0 > 0.2 and _L.nzmin >= 0.7:
        _L.lift_fn = console_panel.lift_fn(_L, _sd)
n_rc_skip = 0


def in_layout(p):
    for L_, sd_ in LAYOUTS:
        xa, xb, za, zb = L_.region()
        if xa - 0.01 < p[0] * sd_ < xb + 0.03 and za - 0.01 < p[1] < zb + 0.012 and p[2] < L_.ymax + 0.01:
            return True
    return False
for i, (kind, x, y, size) in enumerate(feats):
    loc = locate(x, y)
    if loc is None:
        print("  not on the shell:", kind, x, y)
        continue
    pos, nrm, tri = loc
    if in_layout(pos) or gear_panel.footprint(pos) or dwp_panel.footprint(pos) or nve_panel.footprint(pos):
        n_rc_skip += 1
        continue
    if abs(pos[0] - THR_C.x) < 0.074 and -0.095 < pos[1] - THR_C.y < 0.160 and pos[2] < THR_C.z + 0.05:
        print("  under the throttle quadrant, skipped:", kind, x, y)
        continue
    F = local_frame(nrm)
    n_kind[kind] = n_kind.get(kind, 0) + 1
    _rad = None
    if kind in ("toggle", "lever"):
        _rad = 0.0075
    elif kind == "fastener":
        _rad = 0.0045
    elif kind in ("knob", "pointer"):
        _rad = (float(size) / 2000 if size else 0.009) * 1.3
    elif kind in ("guardbox", "cover"):
        _rad = max(float(v) for v in size.split("x")) / 2000 + 0.004
    elif kind == "button":
        _rad = (float(size) / 1000 if size else 0.012) * 0.85
    elif kind == "drf":
        _rad = (float(size) / 1000 if size else 0.022) * 1.05
    if _rad is not None:
        CTRL_LIST.append((kind, np.array(pos), np.array(F.col[0]), np.array(F.col[1]), np.array(F.col[2]), _rad))
    if kind in ("toggle", "lever"):
        tilt = (18 if (i % 3) else -18) if kind == "toggle" else -25
        ctrl_bms.append(place(proto_toggle(tilt), pos, F))
    elif kind in ("knob", "pointer"):
        d = float(size) / 1000 if size else 0.018
        ctrl_bms.append(place(proto_knob(d, pointer=(kind == "pointer")), pos, F))
    elif kind == "fastener":
        ctrl_bms.append(place(proto_fastener(), pos, F, lift=0.0))
    elif kind in ("guardbox", "cover"):
        w, h = (float(v) / 1000 for v in size.split("x"))
        rect = CUSTOM["sw_hazard"][0]
        if kind == "guardbox":
            frame_parts = []
            t_ = 0.004
            for (cx_, cy_, sx_, sy_) in ((0, h / 2 - t_ / 2, w, t_), (0, -h / 2 + t_ / 2, w, t_), (w / 2 - t_ / 2, 0, t_, h), (-w / 2 + t_ / 2, 0, t_, h)):
                frame_parts.append(ck.rbox(Vector((cx_, cy_, 0.009)), (sx_, sy_, 0.018), bevel=0.001, seg=1))
            g = ck.merge(frame_parts)
            planar_uv(g, rect, Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((0, 1, 0)) + Vector((0, 0, 1)), w, h + 0.02)
            btn = ck.rbox(Vector((0, 0, 0.006)), (w * 0.55, w * 0.55, 0.012), bevel=0.002, seg=2); sw(btn, "red")
            ctrl_bms.append(place(ck.merge([g, btn]), pos, F))
        else:
            c = ck.rbox(Vector((0, 0, 0.007)), (w, h, 0.006), bevel=0.0015, seg=1)
            planar_uv(c, rect, Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((0, 1, 0)), w, h)
            hinge = ck.rbox(Vector((0, -h / 2, 0.004)), (w * 0.9, 0.004, 0.006), bevel=0); sw(hinge, "black")
            ctrl_bms.append(place(ck.merge([c, hinge]), pos, F))
    elif kind == "button":
        d = float(size) / 1000 if size else 0.012
        bz = ck.rbox(Vector((0, 0, 0.0010)), (d * 1.22, d * 1.22, 0.0020), bevel=0.0006, seg=1); sw(bz, "black")
        cap = ck.rbox(Vector((0, 0, 0.0036)), (d, d, 0.0052), bevel=0.0011, seg=2); sw(cap, "darkgrey")
        face = ck.rbox(Vector((0, 0, 0.0063)), (d * 0.74, d * 0.74, 0.0004), bevel=0); sw(face, "black")
        bits = [bz, cap, face]
        if i % 3 == 0:
            for dy_ in (-0.16, 0.16):
                b_ = ck.rbox(Vector((0, d * dy_, 0.0066)), (d * 0.46, d * 0.085, 0.0003), bevel=0); sw(b_, "green"); bits.append(b_)
        elif i % 3 == 1:
            b_ = ck.rbox(Vector((0, 0, 0.0066)), (d * 0.50, d * 0.10, 0.0003), bevel=0); sw(b_, "white"); bits.append(b_)
        else:
            for dx_, dy_, sx_, sy_ in ((0, 0, 0.10, 0.48), (0, 0.20, 0.34, 0.10)):
                b_ = ck.rbox(Vector((d * dx_, d * dy_, 0.0066)), (d * sx_, d * sy_, 0.0003), bevel=0); sw(b_, "white"); bits.append(b_)
        ctrl_bms.append(place(ck.merge(bits), pos, F))
    elif kind == "drf":
        d = float(size) / 1000 if size else 0.022
        bits = []
        nseg = 16
        r0, r1 = d * 0.50, d * 0.86
        for k in range(nseg):
            a0, a1 = 2 * math.pi * k / nseg, 2 * math.pi * (k + 1) / nseg
            b_ = bmesh.new()
            ck.prism_profile(b_, [(r0 * math.cos(a0), r0 * math.sin(a0)), (r1 * math.cos(a0), r1 * math.sin(a0)),
                                  (r1 * math.cos((a0 + a1) / 2), r1 * math.sin((a0 + a1) / 2)), (r1 * math.cos(a1), r1 * math.sin(a1)),
                                  (r0 * math.cos(a1), r0 * math.sin(a1))], Vector((0, 0, 0.0020)), Matrix.Identity(3), 0.0040)
            bmesh.ops.recalc_face_normals(b_, faces=b_.faces[:])
            sw(b_, "yellow" if k % 2 == 0 else "black"); bits.append(b_)
        base_ = bmesh.new(); ck.cylinder(base_, (0, 0, 0), (0, 0, 1), d * 0.92, 0.0016, seg=40); sw(base_, "black"); bits.append(base_)
        gd_ = ck.rbox(Vector((0, 0, 0.0035)), (d * 0.66, d * 0.66, 0.0070), bevel=0.0012, seg=2); sw(gd_, "black"); bits.append(gd_)
        cap = ck.rbox(Vector((0, 0, 0.0060)), (d * 0.46, d * 0.46, 0.0060), bevel=0.0012, seg=2); sw(cap, "darkgrey"); bits.append(cap)
        ctrl_bms.append(place(ck.merge(bits), pos, F))
print("controls:", n_kind)
_SPn = np.cross(SP[:, 1] - SP[:, 0], SP[:, 2] - SP[:, 0])
_SPn /= np.maximum(np.linalg.norm(_SPn, axis=1), 1e-12)[:, None]
for RC_LAYOUT, _side in LAYOUTS:
    _xa, _xb, _za, _zb = RC_LAYOUT.region()
    _cx = SP[:, :, 0].mean(1) * _side
    _cz = SP[:, :, 2].mean(1)
    _up = ((np.abs(_SPn[:, 1]) > RC_LAYOUT.nzmin * 0.9) & (SP[:, :, 1].max(1) < RC_LAYOUT.ymax + 0.01)
           & (_cx > _xa - 0.08) & (_cx < _xb + 0.08) & (_cz > _za - 0.08) & (_cz < _zb + 0.08))
    _ST = SP[_up]

    def rc_surf(x, z, _ST=_ST):
        a_, b_, c_ = _ST[:, 0][:, [0, 2]], _ST[:, 1][:, [0, 2]], _ST[:, 2][:, [0, 2]]
        d_ = (b_[:, 1] - c_[:, 1]) * (a_[:, 0] - c_[:, 0]) + (c_[:, 0] - b_[:, 0]) * (a_[:, 1] - c_[:, 1])
        with np.errstate(divide="ignore", invalid="ignore"):
            w1 = ((b_[:, 1] - c_[:, 1]) * (x - c_[:, 0]) + (c_[:, 0] - b_[:, 0]) * (z - c_[:, 1])) / d_
            w2 = ((c_[:, 1] - a_[:, 1]) * (x - c_[:, 0]) + (a_[:, 0] - c_[:, 0]) * (z - c_[:, 1])) / d_
        w3 = 1 - w1 - w2
        ok = np.nonzero((np.abs(d_) > 1e-12) & (w1 >= -1e-4) & (w2 >= -1e-4) & (w3 >= -1e-4))[0]
        if len(ok) == 0:
            return None
        ys_ = [(w1[t] * _ST[t, 0] + w2[t] * _ST[t, 1] + w3[t] * _ST[t, 2]) for t in ok]
        t = ok[int(np.argmax([q[1] for q in ys_]))]
        p_ = w1[t] * _ST[t, 0] + w2[t] * _ST[t, 1] + w3[t] * _ST[t, 2]
        n_ = np.cross(_ST[t, 1] - _ST[t, 0], _ST[t, 2] - _ST[t, 0]); n_ /= np.linalg.norm(n_)
        if n_[1] < 0:
            n_ = -n_
        return u2b(p_), u2b(n_)
    _rc_bms, _rc_ctrl = console_layout.build(RC_LAYOUT, rc_surf, local_frame, sw, place, ck, side=_side)
    ctrl_bms.extend(_rc_bms)
    CTRL_LIST.extend(_rc_ctrl)
    for _st, _lv, _pv, _ax, _tl in getattr(RC_LAYOUT, "moving", []):
        _gn = "cockpit_sw_%s_%d" % (_st, len(SW_LINES))
        SW_PARTS.append((_gn, _lv))
        _b = _pv + _ax
        SW_LINES.append("%s %.4f %.4f %.4f %.4f %.4f %.4f sw_%s %.1f" % (_gn, _pv.x, _pv.z, _pv.y, _b.x, _b.z, _b.y, _st, _tl))
    RC_LAYOUT.moving = []
    print(f"console layout ({'right' if _side > 0 else 'left'}): {len(_rc_ctrl)} controls")
print(f"photo layouts: {n_rc_skip} old features dropped")
add("controls", ck.merge(ctrl_bms), "custom", group="cockpit_controls", uvmode="custom", smooth=35)
for _gn, _lv in SW_PARTS:
    add(_gn[8:], _lv, "custom", group=_gn, uvmode="custom", smooth=35)
open(os.path.join(OUT, "sw_hinges.txt"), "w").write("".join(l + "\n" for l in SW_LINES))
print("state switches:", SW_LINES)
if relief_bms:
    add("relief", ck.merge(relief_bms), "cockpit", group="cockpit_relief", uvmode="atlas", smooth=30)

EYE_B = Vector((0.0, 6.5, 1.16))
ARCH_C = Vector((0.0, 7.06, 0.859))
ARCH_R = 0.44

MIRROR_BOXES = {"top": ((-0.10, 1.29, 7.05), (0.10, 1.335, 7.14)),
                "R": ((0.20, 1.15, 7.02), (0.35, 1.285, 7.12)),
                "L": ((-0.35, 1.15, 7.02), (-0.20, 1.285, 7.12))}
keep = np.ones(len(shell[1]), bool)
mirror_pads = {}
for idx in loose_parts(shell[1]):
    pts = shell[1][idx].reshape(-1, 3)
    for k, (lo_, hi_) in MIRROR_BOXES.items():
        if (pts.min(0) >= np.array(lo_)).all() and (pts.max(0) <= np.array(hi_)).all() and len(idx) > 20:
            keep[idx] = False
            mirror_pads[k] = pts
print("mirror pads replaced:", sorted(mirror_pads))
for k in (1, 2, 3):
    shell[k] = shell[k][keep]
SP, SUV = shell[1], shell[2]
shell_bm.free()
shell_bm = bm_from_tris(shell[1], shell[2])
shell_bvh = BVHTree.FromBMesh(shell_bm)

mir_bms, mglass_bms = [], []
MIRROR_SIZE = {"top": (0.17, 0.042), "L": (0.115, 0.042), "R": (0.115, 0.042)}
for k, pts in mirror_pads.items():
    P = np.array([u2b(p) for p in pts])
    c = Vector(P.mean(0))
    to_eye = (EYE_B - c).normalized()
    n = (to_eye + Vector((0, -1, 0.1)).normalized()).normalized()
    a1 = Vector((1, 0, 0)) if k == "top" else (Vector((0, 0, 1)).cross(n) if k == "R" else n.cross(Vector((0, 0, 1))))
    a1 = (a1 - n * a1.dot(n)).normalized()
    if k != "top":
        radial = Vector((c.x, 0, c.z - ARCH_C.z)).normalized()
        a1 = Vector((radial.z, 0, -radial.x))
        a1 = (a1 - n * a1.dot(n)).normalized()
    a2 = n.cross(a1).normalized()
    ext1, ext2 = MIRROR_SIZE[k]
    Fm = ck.frame(a1, a2, n)
    cen = c + n * 0.006
    hb = ck.rbox(cen - n * 0.007, (ext1 + 0.012, ext2 + 0.012, 0.018), Fm, bevel=0.006, seg=3)
    mir_bms.append(hb)
    gl = ck.rbox(cen + n * 0.0026, (ext1, ext2, 0.0015), Fm, bevel=0.0006, seg=1)
    _uvl = gl.loops.layers.uv.active or gl.loops.layers.uv.new("UVMap")
    _d1 = [(v.co - cen).dot(a1) for v in gl.verts]
    _d2 = [(v.co - cen).dot(a2) for v in gl.verts]
    _band = {"R": 0, "L": 1, "top": 2}[k]
    for _f in gl.faces:
        for _lp in _f.loops:
            _u = ((_lp.vert.co - cen).dot(a1) - min(_d1)) / max(max(_d1) - min(_d1), 1e-9)
            _v = ((_lp.vert.co - cen).dot(a2) - min(_d2)) / max(max(_d2) - min(_d2), 1e-9)
            _lp[_uvl].uv = (0.02 + 0.96 * _u, (_band + 0.04 + 0.92 * _v) / 3.0)
    mglass_bms.append(gl)
    st = bmesh.new()
    ck.cylinder(st, cen - n * 0.012, (-n + Vector((0, 1, 0))).normalized(), 0.006, 0.035, seg=10)
    mir_bms.append(st)
if mir_bms:
    add("mirror_housings", ck.merge(mir_bms), "black", group="cockpit_frame", smooth=40)
    gl = ck.merge(mglass_bms)
    add("mirror_glass", gl, "custom", group="cockpit_mirror", uvmode="custom", smooth=20)

bolt_bms = []
hits = []
for k in range(-48, 49):
    th = math.radians(k * 2.0)
    radial = Vector((math.sin(th), 0, math.cos(th)))
    face_pts = []
    for rr in np.linspace(ARCH_R - 0.08, ARCH_R + 0.08, 33):
        tgt = ARCH_C + radial * rr
        d = (tgt - EYE_B).normalized()
        hit = shell_bvh.ray_cast(EYE_B, d, 1.0)
        if hit[0] is None:
            continue
        loc, nrm = hit[0], hit[1]
        if nrm.dot(-d) < 0:
            nrm = -nrm
        if nrm.y < -0.75 and 7.0 < loc.y < 7.22:
            face_pts.append((rr, loc, nrm))
    if len(face_pts) >= 3:
        rr = [f[0] for f in face_pts]
        mid = face_pts[len(face_pts) // 2]
        hits.append((th, mid[1], mid[2], max(rr) - min(rr)))
placed = []
for th, loc, nrm, width in hits:
    if placed and (loc - placed[-1]).length < 0.04:
        continue
    placed.append(loc)
    Fb = local_frame(nrm)
    b = bmesh.new()
    ck.cylinder(b, loc - nrm * 0.0005, nrm, 0.0042, 0.0028, seg=6, r_top=0.0036)
    w_ = bmesh.new()
    ck.cylinder(w_, loc - nrm * 0.0005, nrm, 0.0058, 0.0008, seg=16)
    bolt_bms.append(ck.merge([b, w_]))
print(f"arch bolts: {len(placed)} (of {len(hits)} hits)")
if bolt_bms:
    bb = ck.merge(bolt_bms)
    ck.set_uv_all(bb, SW["darkgrey"])
    add("arch_bolts", bb, "custom", group="cockpit_controls", uvmode="custom", smooth=30)

_Pb = shell[1]
_inbox = ((np.abs(_Pb[:, :, 0]) > 0.362) & (np.abs(_Pb[:, :, 0]) < 0.462) & (_Pb[:, :, 1] > 0.605) & (_Pb[:, :, 1] < 0.742)
          & (_Pb[:, :, 2] > 6.662) & (_Pb[:, :, 2] < 6.768)).all(1)
if os.environ.get("KEEP_SILL_BOX") is None and _inbox.any():
    for k in (1, 2, 3):
        shell[k] = shell[k][~_inbox]
    print(f"sill boxes removed: {int(_inbox.sum())} triangles")
_CP = {_sd: console_panel.build(_sd, ck, sw, shell[1]) for _sd in (1, -1)}
for _sd in (1, -1):
    _f, _mt, _nm = console_panel.FILES[_sd]
    json.dump(_CP[_sd]["labels"], open(os.path.join(OUT, "labels_%s.json" % _nm), "w"))
    add(_nm + "_panel", _CP[_sd]["slab"], "custom", group="cockpit_" + _nm, uvmode="custom", smooth=25)
    print("console panel", _nm, ":", _CP[_sd]["tris"], "top triangles,", len(_CP[_sd]["labels"]), "labels")
_rm = (gear_panel.shell_remove_mask(shell[1]) | pedestal.shell_remove_mask(shell[1]) | dwp_panel.shell_remove_mask(shell[1])
       | nve_panel.shell_remove_mask(shell[1]) | console_panel.shell_remove_mask(shell[1]))
if os.environ.get("KEEP_OLD_PED") is None and _rm.any():
    for k in (1, 2, 3):
        shell[k] = shell[k][~_rm]
    print(f"gear panel face and pedestal shelf cut out of the shell: {int(_rm.sum())} triangles")

Pu = shell[1]
_cr = np.cross(Pu[:, 1] - Pu[:, 0], Pu[:, 2] - Pu[:, 0])
_ln = np.linalg.norm(_cr, axis=1)
_n = _cr / np.maximum(_ln, 1e-12)[:, None]
_c = Pu.mean(1)
_x, _y, _z = _c[:, 0], _c[:, 1], _c[:, 2]
_ax = np.abs(_x)
_panel = (_ax < 0.40) & (_y > 0.58) & (_y < 1.30) & (_z > 7.12) & (_z < 7.60) & (_n[:, 2] < -0.15)
_cons = (_ax > 0.22) & (_ax < 0.52) & (_y > 0.36) & (_y < 0.72) & (_z > 5.8) & (_z < 7.4) & (_n[:, 1] > 0.3)
_walls = (_ax > 0.15) & (_ax < 0.50) & (_y > 0.28) & (_y < 0.66) & (_z > 6.1) & (_z < 7.35) & (_n[:, 0] * np.sign(_x) < -0.55)
_ped = (_ax < 0.16) & (_z > 6.95) & (_z < 7.40) & (_y > 0.30) & (_y < 0.66) & ((_n[:, 2] < -0.3) | (np.abs(_n[:, 0]) > 0.6))
_sillstrip = (_ax > 0.375) & (_y > 0.69) & (_z > 7.10)
skin_sel = (_cons | _walls | _ped) & ~_panel & ~_sillstrip & (_ln > 1e-10)
SKIN = [shell[k][skin_sel] for k in (1, 2, 3)]
for k in (1, 2, 3):
    shell[k] = shell[k][~skin_sel]
SP, SUV = shell[1], shell[2]
shell_bm.free()
shell_bm = bm_from_tris(shell[1], shell[2])
shell_bvh = BVHTree.FromBMesh(shell_bm)
_bm = bm_from_tris(SKIN[0], SKIN[1])
_old = _bm.loops.layers.uv.get("UVMap")
_new = _bm.loops.layers.uv.new("UVNEW")
for f in _bm.faces:
    for lp in f.loops:
        lp[_new].uv = lp[_old].uv
skin_ob = add("console_skin", _bm, "skin", group="cockpit_consoles", uvmode="skin", smooth=30)
skin_ob.data.uv_layers["UVMap"].name = "OLD"
skin_ob.data.uv_layers["UVNEW"].name = "UVMap"
skin_ob.data.uv_layers.active = skin_ob.data.uv_layers["UVMap"]
skin_ob.data.uv_layers["UVMap"].active_render = True
print(f"console skin: {np.count_nonzero(skin_sel)} shell triangles, {(_ln[skin_sel] / 2).sum():.3f} m2")

import ckpanel
_sw3 = [0, 2, 1]
ATLAS_P = SHELL_ORIG[0][:, :, _sw3].astype(np.float32)
ATLAS_UV = SHELL_ORIG[1].astype(np.float32)
PANEL_ITEMS = ckpanel.resolve(ckpanel.parse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cockpit_panel.txt")),
                              ckpanel.Atlas(ATLAS_P, ATLAS_UV))
KEYS = []
cap_bms, pk_bms = [], []
for it in PANEL_ITEMS:
    p0, r_, u_, n0 = Vector(it["pos"]), Vector(it["r"]), Vector(it["u"]), Vector(it["n"])
    Fk = ck.frame(r_, u_, n0)
    if it["kind"] == "key":
        KEYS.append((p0, r_, u_, n0, it["wr"], it["hu"]))
        cap_bms.append(ck.rbox(p0 + n0 * 0.0016, (it["wr"], it["hu"], 0.0032), Fk, bevel=0.0007, seg=1))
    elif it["kind"] == "disc" and it["sub"] == "knob":
        pk_bms.append(place(proto_knob(it["d"], body="darkgrey", tall=0.55, ribs=8, seg=18), p0, Fk))
    elif it["kind"] == "slider":
        sl = ck.rbox(Vector((0, 0, 0.004)), (it["wr"], it["hu"], 0.008), bevel=0.0012, seg=2); sw(sl, "darkgrey")
        ix = ck.rbox(Vector((0, 0, 0.0082)), (it["wr"] * 0.12, it["hu"] * 0.8, 0.0005), bevel=0); sw(ix, "white")
        pk_bms.append(place(ck.merge([sl, ix]), p0, Fk))
keys_ob = add("keycaps", ck.merge(cap_bms), "keys", group="cockpit_keys", uvmode="keys", smooth=30) if cap_bms else None
if pk_bms:
    add("panel_knobs", ck.merge(pk_bms), "custom", group="cockpit_controls", uvmode="custom", smooth=35)
print(f"panel: {len(PANEL_ITEMS)} items, {len(KEYS)} raised key caps, {len(pk_bms)} knobs and sliders")
Pu = shell[1]
_cr = np.cross(Pu[:, 1] - Pu[:, 0], Pu[:, 2] - Pu[:, 0])
_ln = np.linalg.norm(_cr, axis=1)
_n = _cr / np.maximum(_ln, 1e-12)[:, None]
_c = Pu.mean(1)
_x, _y, _z = _c[:, 0], _c[:, 1], _c[:, 2]
panel_sel = (np.abs(_x) < 0.40) & (_y > 0.58) & (_y < 1.30) & (_z > 7.12) & (_z < 7.60) & (_n[:, 2] < -0.15) & (_ln > 1e-10)
PANEL = [shell[k][panel_sel] for k in (1, 2, 3)]
for k in (1, 2, 3):
    shell[k] = shell[k][~panel_sel]
SP, SUV = shell[1], shell[2]
shell_bm.free()
shell_bm = bm_from_tris(shell[1], shell[2])
shell_bvh = BVHTree.FromBMesh(shell_bm)
_bm = bm_from_tris(PANEL[0], PANEL[1])
_old = _bm.loops.layers.uv.get("UVMap")
_new = _bm.loops.layers.uv.new("UVNEW")
for f in _bm.faces:
    for lp in f.loops:
        lp[_new].uv = lp[_old].uv
panel_ob = add("panel_skin", _bm, "skin", group="cockpit_panel", uvmode="skin", smooth=30)
panel_ob.data.uv_layers["UVMap"].name = "OLD"
panel_ob.data.uv_layers["UVNEW"].name = "UVMap"
panel_ob.data.uv_layers.active = panel_ob.data.uv_layers["UVMap"]
panel_ob.data.uv_layers["UVMap"].active_render = True
print(f"panel skin: {np.count_nonzero(panel_sel)} shell triangles, {(_ln[panel_sel] / 2).sum():.3f} m2")

def closed_spline(pts, per=8):
    P = [Vector(p) for p in pts]
    n = len(P)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = P[(i - 1) % n], P[i], P[(i + 1) % n], P[(i + 2) % n]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    return out


def boundary_loop(bm_):
    edges = [e for e in bm_.edges if len(e.link_faces) == 1]
    if not edges:
        return []
    nxt = {}
    for e in edges:
        a_, b_ = e.verts
        nxt.setdefault(a_.index, []).append(b_.index)
        nxt.setdefault(b_.index, []).append(a_.index)
    start = edges[0].verts[0].index
    loop, prev, cur = [start], None, start
    while True:
        cand = [v for v in nxt[cur] if v != prev]
        if not cand:
            break
        prev, cur = cur, cand[0]
        if cur == start:
            break
        loop.append(cur)
    bm_.verts.ensure_lookup_table()
    return [bm_.verts[i].co.copy() for i in loop]


HUD_OUT = None
if HUD_PANES is not None and len(HUD_PANES.faces):
    panes = []
    seen = set()
    HUD_PANES.faces.ensure_lookup_table()
    for f in HUD_PANES.faces:
        if f.index in seen:
            continue
        st, comp = [f], []
        seen.add(f.index)
        while st:
            g_ = st.pop(); comp.append(g_)
            for e in g_.edges:
                for h_ in e.link_faces:
                    if h_.index not in seen:
                        seen.add(h_.index); st.append(h_)
        panes.append(comp)
    panes.sort(key=lambda c: sum(f.calc_center_median().y for f in c) / len(c))
    pb_ = bmesh.new()
    for f in panes[0]:
        vs = [pb_.verts.new(v.co) for v in f.verts]
        pb_.faces.new(vs)
    bmesh.ops.remove_doubles(pb_, verts=pb_.verts, dist=1e-5)
    outline = boundary_loop(pb_)
    pane_n = sum((f.normal for f in panes[0]), Vector()).normalized()
    depth = 0.012
    if len(panes) > 1:
        c0 = sum((f.calc_center_median() for f in panes[0]), Vector()) / len(panes[0])
        c1 = sum((f.calc_center_median() for f in panes[1]), Vector()) / len(panes[1])
        depth = max(0.006, min(0.025, abs((c1 - c0).dot(pane_n))))
    pb_.free()
    if len(outline) >= 6:
        cen = sum(outline, Vector()) / len(outline)
        loop = closed_spline(outline, 10)
        W_, R_ = 0.0075, 0.0022
        sec = []
        for k in range(16):
            a_ = 2 * math.pi * k / 16
            cx_, cy_ = math.cos(a_), math.sin(a_)
            sx = math.copysign(abs(cx_) ** 0.35, cx_) * W_ / 2
            sy = math.copysign(abs(cy_) ** 0.35, cy_) * (depth / 2 + 0.002)
            sec.append((sx, sy))
        fb = bmesh.new()
        rings = []
        n_ = len(loop)
        for i, p in enumerate(loop):
            tng = (loop[(i + 1) % n_] - loop[(i - 1) % n_]).normalized()
            out_ = tng.cross(pane_n).normalized()
            if out_.dot(p - cen) < 0:
                out_ = -out_
            mid = p + pane_n * (-depth / 2) + out_ * (W_ / 2 - 0.0015)
            rings.append([fb.verts.new(mid + out_ * sx + pane_n * sy) for sx, sy in sec])
        for i in range(n_):
            j = (i + 1) % n_
            for k in range(16):
                k2 = (k + 1) % 16
                try:
                    fb.faces.new([rings[i][k], rings[i][k2], rings[j][k2], rings[j][k]])
                except ValueError:
                    pass
        bmesh.ops.recalc_face_normals(fb, faces=fb.faces[:])
        ck.set_uv_all(fb, SW["black"])
        HUD_OUT = add("hud_frame", fb, "custom", group="cockpit_hudframe", uvmode="custom", smooth=60)
        gb = bmesh.new()
        c_v = gb.verts.new(cen - pane_n * 0.0)
        ring_v = [gb.verts.new(p) for p in loop]
        for i in range(n_):
            f = gb.faces.new([c_v, ring_v[i], ring_v[(i + 1) % n_]])
        gb.normal_update()
        if sum((f.normal for f in gb.faces), Vector()).dot(pane_n) < 0:
            bmesh.ops.reverse_faces(gb, faces=gb.faces[:])
        ck.set_uv_all(gb, (0.5, 0.5))
        add("hud_glass", gb, "custom", group="cockpit_hudglass", uvmode="custom", smooth=20)
        print(f"HUD combiner: outline {len(outline)} -> {n_} points, frame depth {depth * 1000:.0f} mm")
        group("cockpit_hudframe")[1] = np.zeros((0, 3, 3))
        group("cockpit_hudframe")[2] = np.zeros((0, 3, 2))
        group("cockpit_hudframe")[3] = np.zeros((0, 3, 3))

STICK_PIVOT = Vector((0.0, 7.10, 0.46))
stick_parts = []


def loft(sections, cap=True):
    bm_ = bmesh.new()
    rings = []
    N = 28
    for c_, a_, b_, e_ in sections:
        ring = []
        for k in range(N):
            t = 2 * math.pi * k / N
            ct, st_ = math.cos(t), math.sin(t)
            x_ = math.copysign(abs(ct) ** (2 / e_), ct) * a_
            y_ = math.copysign(abs(st_) ** (2 / e_), st_) * b_
            ring.append(bm_.verts.new(c_ + Vector((x_, y_, 0))))
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


import cockpit_hotas as hotas

for _nm, _bm, _surf, _uvm in hotas.build_stick(STICK_PIVOT, SW):
    add(_nm, _bm, _surf, group="cockpit_stick", uvmode=_uvm, smooth=50)
_g = group("cockpit_stick")
_g[1], _g[2], _g[3] = np.zeros((0, 3, 3)), np.zeros((0, 3, 2)), np.zeros((0, 3, 3))
print("control stick rebuilt")

THR_ROLL = Matrix.Rotation(math.atan(0.09), 4, 'Y')
_mv, _fx = hotas.build_throttle(THR_C, SW)
_xf = Matrix.Translation(THR_C) @ THR_ROLL @ Matrix.Translation(-THR_C)
for _lst, _grp in ((_mv, "cockpit_throttle"), (_fx, "cockpit_controls")):
    for _nm, _bm, _surf, _uvm in _lst:
        bmesh.ops.transform(_bm, matrix=_xf, verts=_bm.verts[:])
        add(_nm, _bm, _surf, group=_grp, uvmode=_uvm, smooth=50)
_R3 = THR_ROLL.to_3x3()
_thl = []
for _l in hotas.THR_LABELS:
    _l = dict(_l)
    _l["pos"] = [float(v) for v in (_xf @ Vector(_l["pos"]))]
    for _k in ("r", "u", "n"):
        _l[_k] = [float(v) for v in (_R3 @ Vector(_l[_k]))]
    _thl.append(_l)
json.dump(_thl, open(os.path.join(OUT, "labels_thr.json"), "w"))
if any(g[0] == "cockpit_throttle" for g in model):
    _g = group("cockpit_throttle")
    _g[1], _g[2], _g[3] = np.zeros((0, 3, 3)), np.zeros((0, 3, 2)), np.zeros((0, 3, 3))
print("throttle rebuilt")
_ped, PEDAL_HINGE = hotas.build_pedals(0.174, 7.626, SW, x_c=0.197)
open(os.path.join(OUT, "pedal_hinge.txt"), "w").write("".join(
    "cockpit_pedal_%s %.4f %.4f %.4f %.4f %.4f %.4f pedal_%s\n" % (_k, _v.x, _v.z, _v.y, _v.x + 1.0, _v.z, _v.y, _k.lower()) for _k, _v in sorted(PEDAL_HINGE.items())))
for _key, _grp in (("L", "cockpit_pedal_L"), ("R", "cockpit_pedal_R"), ("fixed", "cockpit_controls")):
    for _nm, _bm, _surf, _uvm in _ped[_key]:
        add(_nm, _bm, _surf, group=_grp, uvmode=_uvm, smooth=50)
_GP = gear_panel.build(ck, sw)
GEAR_Q = Vector(_GP["hinge_b"])
_ao_gp = None
if not PREVIEW and os.environ.get("GEAR_AO_BAKE"):
    _ao_gp = cxm.bake_ao(_GP["slab"].copy(), [_GP["fixed"].copy(), _GP["lever"].copy()], (1024, 1024), distance=0.03,
                         samples=int(os.environ.get("AO_SAMPLES", "48")))
gear_panel.paint(OUT, _ao_gp)
json.dump(_GP["labels"], open(os.path.join(OUT, "labels_gear.json"), "w"))
open(os.path.join(OUT, "gear_hinge.txt"), "w").write(_GP["surface_line"] + "\n")
add("gear_panel", _GP["slab"], "custom", group="cockpit_gearpanel", uvmode="custom", smooth=25)
_mv = [("gearlever_bits", _GP["lever"], "custom", "custom")]
_fx = [("gearpanel_bits", _GP["fixed"], "custom", "custom")]
print("gear panel:", _GP["surface_line"])
for _lst, _grp in ((_mv, "cockpit_gearlever"), (_fx, "cockpit_controls")):
    for _nm, _bm, _surf, _uvm in _lst:
        add(_nm, _bm, _surf, group=_grp, uvmode=_uvm, smooth=50)
for _mod, _grp, _nm in ((dwp_panel, "cockpit_dwppanel", "dwp"), (nve_panel, "cockpit_nvepanel", "nve")):
    _PN = _mod.build(ck, sw)
    if not PREVIEW or os.environ.get("PANEL_PAINT"):
        _mod.paint(OUT)
    json.dump(_PN["labels"], open(os.path.join(OUT, "labels_%s.json" % _nm), "w"))
    add(_nm + "_panel", _PN["slab"], "custom", group=_grp, uvmode="custom", smooth=25)
    add(_nm + "_panel_bits", _PN["bits"], "custom", group="cockpit_controls", uvmode="custom", smooth=50)
    print(_nm, "panel rebuilt:", len(_PN["labels"]), "labels")
_wx = -0.2915
_oxy = []
_Fw = ck.frame(Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0)))
_P0 = Vector((_wx, 6.800, 0.420))
_b = bmesh.new(); ck.cylinder(_b, _P0, Vector((1, 0, 0)), 0.014, 0.008, seg=24); _oxy.append(sw(_b, "black"))
_b = bmesh.new(); ck.cylinder(_b, _P0 + Vector((0.008, 0, 0)), Vector((1, 0, 0)), 0.008, 0.006, seg=16); _oxy.append(sw(_b, "metal"))
_ang = math.radians(55)
_dir = Vector((0, math.cos(_ang), math.sin(_ang)))
_Fl = ck.frame(_dir, Vector((0, -math.sin(_ang), math.cos(_ang))), Vector((1, 0, 0)))
_lv = ck.rbox(_P0 + Vector((0.012, 0, 0)) + _dir * 0.040, (0.070, 0.020, 0.006), _Fl, bevel=0.002, seg=2)
planar_uv(_lv, CUSTOM["sw_hazard"][0], _P0, _dir, Vector((0, -math.sin(_ang), math.cos(_ang))), 0.070, 0.020)
_oxy.append(_lv)
_b = bmesh.new(); ck.cylinder(_b, _P0 + Vector((0.009, 0, 0)) + _dir * 0.075, Vector((1, 0, 0)), 0.006, 0.010, seg=12); _oxy.append(sw(_b, "black"))
_P1 = Vector((_wx, 6.690, 0.345))
_oxy.append(sw(ck.rbox(_P1 + Vector((0.008, 0, 0)), (0.016, 0.040, 0.050), bevel=0.002, seg=2), "black"))
_oxy.append(sw(ck.rbox(_P1 + Vector((0.018, 0, 0.010)), (0.008, 0.026, 0.012), bevel=0.0015, seg=2), "darkgrey"))
for _k in range(5):
    _oxy.append(sw(ck.rbox(_P1 + Vector((0.0225, -0.010 + _k * 0.005, 0.010)), (0.0012, 0.0012, 0.010), bevel=0), "black"))
_oxy.append(sw(ck.rbox(_P1 + Vector((0.0165, 0, -0.012)), (0.0005, 0.003, 0.016), bevel=0), "white"))
add("wall_controls", ck.merge(_oxy), "custom", group="cockpit_controls", uvmode="custom", smooth=35)
print("inboard wall: OXY lever and MAIN / REV selector")
for _nm, _bm, _surf, _uvm in pedestal.build(ck, sw):
    add(_nm, _bm, _surf, group="cockpit_controls", uvmode=_uvm, smooth=28)
print("stick pedestal rebuilt")
import shutil
_SG = os.path.join(TEX_IN, "stickgrip.npz")
if os.path.exists(_SG) and os.environ.get("OWN_STICK") is None:
    _d = np.load(_SG)
    _V, _T, _UV = _d["V"].astype(float), _d["T"], _d["UV"]
    if "local" in _d.files:
        _base, _rot = Vector((0, 0, 0)), Matrix.Identity(3)
    else:
        _base = Vector((-0.013, -0.049, 0.187))
        _rot = Matrix.Rotation(math.radians(-8.0), 3, 'X')
    _O = Vector((0.0, 7.10, 0.46 + hotas.GRIP_Z))
    _sg = bmesh.new()
    _vv = [_sg.verts.new(_O + _rot @ (Vector(p_) - _base)) for p_ in _V]
    _sg.verts.ensure_lookup_table()
    _uvl = _sg.loops.layers.uv.new("UVMap")
    for _ti, _t in enumerate(_T):
        try:
            _f = _sg.faces.new([_vv[i] for i in _t])
        except ValueError:
            continue
        for _k, _lp in enumerate(_f.loops):
            _lp[_uvl].uv = (float(_UV[_ti, _k, 0]), float(_UV[_ti, _k, 1]))
    _nsg = len(_sg.faces)
    add("stick_grip_model", _sg, "custom", group="cockpit_stickgrip", uvmode="custom", smooth=40)
    for _f in ("ckstick_base.png", "ckstick_normal.png", "ckstick_mask.png"):
        shutil.copy(os.path.join(TEX_IN, _f), os.path.join(OUT, _f))
    print(f"stick grip model: {_nsg} triangles")
_eg = [sw(ck.rbox(pp(0.214, 0.300, -0.005), (0.020, 0.040, 0.030), FP, bevel=0.004, seg=2), "black"),
       sw(ck.rbox(pp(0.214, 0.302, 0.040), (0.018, 0.026, 0.062), FP, bevel=0.005, seg=2), "yellow"),
       sw(ck.rbox(pp(0.214, 0.302, 0.052), (0.0186, 0.0266, 0.014), FP, bevel=0.003, seg=1), "white")]
add("seat_egress", ck.merge(_eg), "custom", group="cockpit_seat", uvmode="custom", smooth=40)
print("hinges (Unity axes): pedals", {k: (round(v.x, 4), round(v.z, 4), round(v.y, 4)) for k, v in PEDAL_HINGE.items()}, "gear lever", (GEAR_Q.x, GEAR_Q.z, GEAR_Q.y))

try:
    if not os.environ.get("CANOPY_MDC"):
        raise RuntimeError("off (the Typhoon jettisons its canopy)")
    _cg = next((g for g in model if g[0] == "canopy"), None)
    _cv = [Vector((p[0], p[2], p[1])) for t in _cg[1] for p in t]
    _cbvh = BVHTree.FromPolygons(_cv, [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(_cg[1]))])

    def _on_canopy(y, phi_deg):
        o = Vector((0.0, y, 0.90)); a = math.radians(phi_deg)
        d = Vector((math.sin(a), 0.0, math.cos(a)))
        hit = _cbvh.ray_cast(o, d, 1.5)
        if hit[0] is None:
            return None
        return hit[0] - d * 0.004, d

    def _ribbon(pts, width=0.0045):
        bm_ = bmesh.new()
        prev = None
        for k, (p, d) in enumerate(pts):
            q = pts[min(k + 1, len(pts) - 1)][0] - pts[max(k - 1, 0)][0]
            side = q.cross(d)
            if side.length < 1e-6:
                continue
            side.normalize()
            a_, b_ = bm_.verts.new(p - side * width / 2), bm_.verts.new(p + side * width / 2)
            a2, b2 = bm_.verts.new(p - side * width / 2 - d * 0.0006), bm_.verts.new(p + side * width / 2 - d * 0.0006)
            if prev is not None:
                bm_.faces.new([prev[0], prev[1], b_, a_])
                bm_.faces.new([a2, b2, prev[3], prev[2]])
            prev = (a_, b_, a2, b2)
        return bm_

    _lines = [[(6.22 + 0.02 * k, 0.0) for k in range(42)]]
    for sgn in (-1, 1):
        zz = []
        for k in range(61):
            t = k / 60.0
            ph = 30 + 20 * abs(((t * 5) % 1.0) * 2 - 1)
            zz.append((6.26 + 0.74 * t, sgn * ph))
        _lines.append(zz)
        _lines.append([(6.26, sgn * (30 * k / 12.0)) for k in range(13)])
    _mdc = []
    for ln in _lines:
        pts = [h for h in (_on_canopy(y, ph) for y, ph in ln) if h is not None]
        if len(pts) > 3:
            _mdc.append(sw(_ribbon(pts), "darkgrey"))
    if _mdc:
        add("canopy_mdc", ck.merge(_mdc), "custom", group="cockpit_frame", uvmode="custom", smooth=30)
        print("canopy detonating cord:", len(_mdc), "ribbons")
except Exception as _e:
    print("canopy detonating cord skipped:", _e)
print("rudder pedals added")

SURF_COL = {"fabric": (0.10, 0.11, 0.05), "fabric_dark": (0.06, 0.07, 0.035), "mesh": (0.09, 0.10, 0.05), "black": (0.015, 0.015, 0.016),
            "carbon": (0.025, 0.025, 0.027), "metal": (0.2, 0.2, 0.21), "darkgrey": (0.05, 0.05, 0.055), "custom": (0.6, 0.45, 0.0), "cockpit": (0.5, 0.2, 0.2), "skin": (0.6, 0.05, 0.05), "black": (0.015, 0.015, 0.016)}


def preview(prefix, views):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.samples = 16; sc.cycles.device = 'CPU'
    sc.view_settings.view_transform = 'Standard'
    mats = {}
    for ob in parts:
        s = ob["surface"]
        if s not in mats:
            m = bpy.data.materials.new(s); m.use_nodes = True
            m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*SURF_COL.get(s, (0.5, 0.5, 0.5)), 1)
            mats[s] = m
        ob.data.materials.append(mats[s])
        for p in ob.data.polygons: p.use_smooth = True
    sh = ck.obj_from_bm("shell", shell_bm.copy())
    m = bpy.data.materials.new("shell"); m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.25, 0.26, 0.27, 1)
    sh.data.materials.append(m)
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.62, 0.72, 1)
    sun = bpy.data.lights.new("sun", 'SUN'); sun.energy = 3.5
    so = bpy.data.objects.new("sun", sun); sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(35), math.radians(-20), math.radians(30))
    cam = bpy.data.cameras.new("cam"); co = bpy.data.objects.new("cam", cam); sc.collection.objects.link(co); sc.camera = co
    eye = Vector((0, 6.5, 1.16))
    V = {"eye": (eye, eye + Vector((0, 1, -0.32)), 85), "down": (eye, eye + Vector((0, 0.5, -1)), 90),
         "ext": (eye + Vector((1.3, 1.0, 0.8)), eye + Vector((0, -0.05, -0.4)), 50),
         "side": (eye + Vector((2.0, 0.2, -0.2)), eye + Vector((0, 0.2, -0.35)), 40),
         "front": (eye + Vector((0.0, 0.62, 0.30)), eye + Vector((0, -0.05, -0.5)), 75),
         "rear": (eye + Vector((-0.9, -1.3, 0.8)), eye + Vector((0, 0.1, -0.3)), 50),
         "left": (eye + Vector((0.05, 0.05, -0.05)), eye + Vector((-0.6, 0.45, -0.55)), 75),
         "right": (eye + Vector((-0.05, 0.05, -0.05)), eye + Vector((0.6, 0.45, -0.55)), 75),
         "lcon": (Vector((-0.25, 6.75, 0.80)), Vector((-0.42, 6.85, 0.48)), 55),
         "rcon": (Vector((0.25, 6.75, 0.80)), Vector((0.42, 6.85, 0.50)), 55),
         "arch": (eye + Vector((0, -0.1, 0.0)), Vector((0, 7.06, 1.05)), 70),
         "stick": (Vector((0.32, 6.80, 0.80)), Vector((0, 7.12, 0.62)), 38),
         "stick2": (Vector((-0.22, 6.86, 0.78)), Vector((0, 7.12, 0.64)), 40),
         "stickf": (Vector((0.10, 7.42, 0.70)), Vector((0, 7.12, 0.64)), 40),
         "thr": (Vector((-0.12, 6.70, 0.78)), Vector((-0.38, 6.92, 0.52)), 42),
         "foot": (Vector((0.0, 6.95, 0.80)), Vector((0.10, 7.50, 0.28)), 60),
         "gearl": (Vector((-0.12, 6.86, 0.92)), Vector((-0.303, 7.222, 0.66)), 34),
         "mdc": (Vector((0.0, 6.5, 1.16)), Vector((0.25, 6.75, 1.5)), 85),
         "mdc2": (Vector((0.0, 6.3, 1.0)), Vector((0.0, 6.9, 1.45)), 90),
         "thrtop": (Vector((-0.38, 6.90, 1.00)), Vector((-0.38, 6.93, 0.48)), 50),
         "threye": (eye, Vector((-0.38, 6.92, 0.52)), 22),
         "stickeye": (eye, Vector((0, 7.12, 0.68)), 16),
         "thr2": (Vector((-0.36, 7.20, 0.72)), Vector((-0.38, 6.92, 0.52)), 42),
         "hud": (eye + Vector((0.0, 0.05, 0.0)), Vector((0, 7.33, 1.12)), 45),
         "ped": (eye + Vector((0, 0.35, -0.25)), Vector((0, 7.2, 0.55)), 40),
         "gearp": (eye, Vector(gear_panel.pt(100, 115)), 22),
         "gearn": (Vector(gear_panel.pt(100, 115, 0.42)), Vector(gear_panel.pt(100, 115)), 36),
         "ped2": (Vector((0.24, 6.82, 0.80)), Vector((0, 7.10, 0.45)), 36),
         "ped3": (Vector((-0.20, 6.86, 0.70)), Vector((0, 7.11, 0.47)), 36),
         "pedeye": (eye, Vector((0, 7.09, 0.47)), 24),
         "dwpe": (eye, Vector(dwp_panel.FR.pt(30, 10)), 22),
         "dwpn": (Vector(dwp_panel.FR.pt(35, 15, 400)), Vector(dwp_panel.FR.pt(35, 15)), 38),
         "nvee": (eye, Vector(nve_panel.FR.pt(0, 70)), 20),
         "nven": (Vector(nve_panel.FR.pt(0, 70, 330)), Vector(nve_panel.FR.pt(0, 70)), 40),
         "nvel": (Vector((-0.20, 6.84, 0.80)), Vector(nve_panel.FR.pt(-20, 70)), 30)}
    for v in views:
        p, t, f = V[v]
        co.location = p; co.rotation_euler = (t - p).normalized().to_track_quat('-Z', 'Y').to_euler()
        cam.angle = math.radians(f); cam.clip_start = 0.02
        sc.render.resolution_x = 800; sc.render.resolution_y = 600
        sc.render.filepath = f"{prefix}_{v}.png"
        bpy.ops.render.render(write_still=True)


if PREVIEW:
    if os.environ.get("NOSHELL"):
        pass
    preview(os.path.join(OUT, "prev"), PREVIEW.split(","))
    raise SystemExit(0)

import ckpaint as cp

ATLAS = int(os.environ.get("ATLAS", "4096"))
for ob in parts:
    if not ob.data.uv_layers:
        ob.data.uv_layers.new(name="UVMap")
pack_obs = [o for o in parts if o["uvmode"] == "pack"]
for o in bpy.context.view_layer.objects:
    o.select_set(False)
for o in pack_obs:
    o.select_set(True)
bpy.context.view_layer.objects.active = pack_obs[0]
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(50), island_margin=0.003)
bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.average_islands_scale()
bpy.ops.uv.pack_islands(margin=0.003, rotate=True)
bpy.ops.object.mode_set(mode='OBJECT')
pu0, pv0, pu1, pv1 = PACK_REGION
for o in pack_obs:
    uv = o.data.uv_layers.active.data
    for d in uv:
        d.uv = (pu0 + d.uv[0] * (pu1 - pu0), pv0 + d.uv[1] * (pv1 - pv0))

SKIN_RES = int(os.environ.get("SKIN_RES", "4096"))
for o in bpy.context.view_layer.objects:
    o.select_set(False)
skin_ob.select_set(True)
bpy.context.view_layer.objects.active = skin_ob
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(40), island_margin=0.002)
bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.average_islands_scale()
bpy.ops.object.mode_set(mode='OBJECT')
_bm = bmesh.new(); _bm.from_mesh(skin_ob.data)
_uvl = _bm.loops.layers.uv.active
_bm.faces.ensure_lookup_table()
_par = list(range(len(_bm.faces)))


def _f(a):
    while _par[a] != a:
        _par[a] = _par[_par[a]]
        a = _par[a]
    return a


for e in _bm.edges:
    lf = e.link_faces
    if len(lf) != 2:
        continue
    f1, f2 = lf

    def _uv_at(face, v):
        for lp in face.loops:
            if lp.vert == v:
                return tuple(np.round(lp[_uvl].uv, 6))
    if all(_uv_at(f1, v) == _uv_at(f2, v) for v in e.verts):
        _par[_f(f1.index)] = _f(f2.index)
_isl = {}
for f in _bm.faces:
    _isl.setdefault(_f(f.index), []).append(f)
for fs in _isl.values():
    area = sum(f.calc_area() for f in fs)
    nz = sum(f.normal.z * f.calc_area() for f in fs) / max(area, 1e-12)
    c = sum((f.calc_center_median() * f.calc_area() for f in fs), Vector()) / max(area, 1e-12)
    if nz > 0.3 and abs(c.x) > 0.22 and c.z > 0.36:
        k = 2.4
    elif abs(c.x) < 0.16 and c.y > 6.95 and c.z > 0.40:
        k = 1.0
    elif c.z < 0.30:
        k = 0.5
    elif abs(nz) < 0.3:
        k = 0.75
    else:
        k = 1.0
    if k != 1.0:
        uvs = [lp[_uvl].uv.copy() for f in fs for lp in f.loops]
        cu = sum(uvs, Vector((0, 0))) / len(uvs)
        for f in fs:
            for lp in f.loops:
                lp[_uvl].uv = cu + (lp[_uvl].uv - cu) * k
_bm.to_mesh(skin_ob.data); _bm.free()
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.pack_islands(margin=0.0015, rotate=True)
bpy.ops.object.mode_set(mode='OBJECT')
_me = skin_ob.data
_new = _me.uv_layers["UVMap"].data
_oldl = _me.uv_layers["OLD"].data
if len(_me.polygons) == len(SKIN[0]):
    SKIN_UVN = np.zeros((len(SKIN[0]), 3, 2)); SKIN_UVO = np.zeros((len(SKIN[0]), 3, 2))
    for i, poly in enumerate(_me.polygons):
        for kk, li in enumerate(poly.loop_indices):
            SKIN_UVN[i, (0, 2, 1)[kk]] = _new[li].uv
            SKIN_UVO[i, (0, 2, 1)[kk]] = _oldl[li].uv
    SKIN_KEEP_NORMALS = True
else:
    print("console skin: face count changed, normals recomputed")
    SKIN_KEEP_NORMALS = False
_area3 = np.linalg.norm(np.cross(SKIN[0][:, 1] - SKIN[0][:, 0], SKIN[0][:, 2] - SKIN[0][:, 0]), axis=1) / 2

PANEL_RES = int(os.environ.get("PANEL_RES", "4096"))
for o in bpy.context.view_layer.objects:
    o.select_set(False)
panel_ob.select_set(True)
bpy.context.view_layer.objects.active = panel_ob
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(40), island_margin=0.002)
bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.average_islands_scale()
bpy.ops.uv.pack_islands(margin=0.0015, rotate=True)
bpy.ops.object.mode_set(mode='OBJECT')
_me = panel_ob.data
_new = _me.uv_layers["UVMap"].data
_oldl = _me.uv_layers["OLD"].data
PANEL_KEEP_NORMALS = len(_me.polygons) == len(PANEL[0])
if PANEL_KEEP_NORMALS:
    PANEL_UVN = np.zeros((len(PANEL[0]), 3, 2)); PANEL_UVO = np.zeros((len(PANEL[0]), 3, 2))
    for i, poly in enumerate(_me.polygons):
        for kk, li in enumerate(poly.loop_indices):
            PANEL_UVN[i, (0, 2, 1)[kk]] = _new[li].uv
            PANEL_UVO[i, (0, 2, 1)[kk]] = _oldl[li].uv
else:
    raise SystemExit("panel skin: face count changed")
_sw = [0, 2, 1]
P_pn = PANEL[0][:, _sw][:, :, [0, 2, 1]]
UVN_pn, UVO_pn = PANEL_UVN[:, _sw], PANEL_UVO[:, _sw]
_cent_pn = P_pn.mean(1)


def panel_uv_of(p, max_d=0.01):
    d = np.linalg.norm(_cent_pn - p, axis=1)
    best = None
    for t in np.argsort(d)[:16]:
        e1, e2 = P_pn[t][1] - P_pn[t][0], P_pn[t][2] - P_pn[t][0]
        n = np.cross(e1, e2)
        b = np.linalg.solve(np.array([e1, e2, n]).T, np.asarray(p) - P_pn[t][0])
        dist = abs(b[2]) * np.linalg.norm(n)
        if b[0] >= -0.01 and b[1] >= -0.01 and b[0] + b[1] <= 1.01 and dist < max_d:
            if best is None or dist < best[0]:
                best = (dist, t)
    if best is None:
        return None
    return ckskin.tri_affine(P_pn[best[1]], UVN_pn[best[1]])


import ckskin
if keys_ob is not None:
    kb = bmesh.new(); kb.from_mesh(keys_ob.data)
    uvl = kb.loops.layers.uv.active or kb.loops.layers.uv.new("UVMap")
    kc = [(np.array(p0), np.array(ax), np.array(ay), np.array(n0)) for p0, ax, ay, n0, kw, kh in KEYS]
    kpos = np.array([k[0] for k in kc])
    fmaps = [panel_uv_of(k[0]) for k in kc]
    n_ok = 0
    for f in kb.faces:
        cc = np.array(f.calc_center_median())
        ki = int(np.argmin(np.linalg.norm(kpos - cc, axis=1)))
        p0, ax, ay, n0 = kc[ki]
        fm = fmaps[ki]
        top = np.dot(np.array(f.normal), n0) > 0.7
        for lp in f.loops:
            q = np.array(lp.vert.co)
            q = q - n0 * np.dot(q - p0, n0)
            if not top:
                q = p0 + (q - p0) * 0.8
            lp[uvl].uv = tuple(fm(q)) if fm is not None else (0.0, 0.0)
        n_ok += fm is not None
    kb.to_mesh(keys_ob.data); kb.free()

tri = {o.name: ck.triangles(o) for o in parts}
if SKIN_KEEP_NORMALS:
    _sw = [0, 2, 1]
    tri["console_skin"] = (SKIN[0][:, _sw][:, :, [0, 2, 1]], SKIN_UVN[:, _sw], SKIN[2][:, _sw][:, :, [0, 2, 1]])
tri["panel_skin"] = (P_pn, UVN_pn, PANEL[2][:, _sw][:, :, [0, 2, 1]])
part_surface = {}
UVs, Ps, IDs = [], [], []
for pid, o in enumerate(parts):
    if o["uvmode"] != "pack":
        continue
    P, UV, N = tri[o.name]
    part_surface[pid] = o["surface"]
    UVs.append(UV); Ps.append(P); IDs.append(np.full(len(P), pid))
idmap, posmap = cp.raster(np.concatenate(UVs), np.concatenate(Ps), np.concatenate(IDs), ATLAS, ATLAS)
base, height, metal, smooth = cp.paint_surfaces(idmap, posmap, part_surface, ATLAS, ATLAS)
filled = idmap >= 0
for key, (rect, kind, extra) in CUSTOM.items():
    cp.paint_rect(base, height, metal, smooth, rect, kind, ATLAS, ATLAS, extra)
    u0, v0, u1, v1 = rect
    filled[int((1 - v1) * ATLAS):int(math.ceil((1 - v0) * ATLAS)), int(u0 * ATLAS):int(math.ceil(u1 * ATLAS))] = True
print(f"atlas painted: {filled.mean() * 100:.0f}% used")

ao_targets = [o for o in parts if o["uvmode"] == "pack" or (o["uvmode"] == "custom" and o.name.startswith("seat_"))]
tgt = ck.merge([ck.bm_from_obj(o, apply_mods=False) for o in ao_targets])
occ = [shell_bm.copy()] + [ck.bm_from_obj(o, apply_mods=False) for o in parts if o not in ao_targets and o["group"] != "cockpit_hudglass"]
AO_RES = int(os.environ.get("AO_RES", "2048"))
ao = cxm.bake_ao(tgt, occ, (AO_RES, AO_RES), distance=0.12, samples=int(os.environ.get("AO_SAMPLES", "48")))
ao_full = np.asarray(Image.fromarray((np.clip(ao, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
                     .resize((ATLAS, ATLAS), Image.BILINEAR)).astype(np.float32) / 255
ao_mask = np.zeros((ATLAS, ATLAS), bool)
for pid, o in enumerate(parts):
    if o in ao_targets and o["uvmode"] == "pack":
        ao_mask |= idmap == pid
for key, (rect, kind, extra) in CUSTOM.items():
    if kind in ("webbing", "webbing_grey", "handle", "qrbface"):
        u0, v0, u1, v1 = rect
        ao_mask[int((1 - v1) * ATLAS):int(math.ceil((1 - v0) * ATLAS)), int(u0 * ATLAS):int(math.ceil(u1 * ATLAS))] = True
ao_full = np.where(ao_mask, ao_full, 1.0)
cp.save(ao_full, os.path.join(OUT, "ckdetail_ao_preview.png"), "L")
base = base * (0.42 + 0.58 * ao_full)[..., None]
base = cp.dilate(base, filled)
height = cp.dilate(height, filled)
metal = cp.dilate(metal, filled)
smooth = cp.dilate(smooth, filled) * (0.6 + 0.4 * ao_full)
nx, ny, nz = cp.normal_from_height(height, strength=2.2)
cp.save(base, os.path.join(OUT, "ckdetail_base.png"), "RGB")
del base, height, ao_full, ao_mask, filled
import gc; gc.collect()
cp.save(cp.pack_normal(nx, ny), os.path.join(OUT, "ckdetail_normal.png"), "RGBA")
del nx, ny, nz; gc.collect()
mask = np.zeros((ATLAS, ATLAS, 4), np.float32)
mask[..., 0] = mask[..., 1] = mask[..., 2] = metal
mask[..., 3] = smooth
cp.save(mask, os.path.join(OUT, "ckdetail_mask.png"), "RGBA")
print("textures written")


def _free(*names):
    import gc
    for n_ in names:
        v_ = globals().pop(n_, None)
        for b_ in (v_ if isinstance(v_, (list, tuple)) else [v_]):
            if isinstance(b_, bmesh.types.BMesh):
                try:
                    b_.free()
                except Exception:
                    pass
    for im_ in list(bpy.data.images):
        if im_.users == 0:
            bpy.data.images.remove(im_)
    gc.collect()


_free("idmap", "posmap", "base", "height", "metal", "smooth", "filled", "ao", "ao_full", "ao_mask", "mask", "nx", "ny", "nz", "tgt", "occ", "UVs", "Ps", "IDs")

import ckskin

occ_names = ("fuselage_cockpit", "fuselage", "cockpit_stick", "cockpit_throttle", "cockpit_hudframe")
occ_model = [bm_from_tris(group(n)[1]) for n in occ_names if any(g[0] == n for g in model)]
SW_, SH_ = 1414, 2069
n_s = int(os.environ.get("SHELL_AO_SAMPLES", "40"))
ao_old = cxm.bake_ao(bm_from_tris(*SHELL_ORIG), [b.copy() for b in occ_model], (SW_, SH_), distance=0.22, samples=n_s)
_sw = [0, 2, 1]
P_sk = SKIN[0][:, _sw][:, :, [0, 2, 1]]
UVN_sk, UVO_sk = SKIN_UVN[:, _sw], SKIN_UVO[:, _sw]
tid_sk, pos_sk, att_sk = ckskin.raster_attr(UVN_sk, P_sk, UVO_sk, SKIN_RES, SKIN_RES)
cover_sk = tid_sk >= 0
_orig = np.asarray(Image.open(os.path.join(TEX_IN, "cockpit_base.png")).convert("RGB")).astype(np.float32) / 255
old_rgb = ckskin.sample(_orig, att_sk)
old_ao = ckskin.sample(ao_old[..., None].astype(np.float32), att_sk)[..., 0]
old_rgb = np.clip(old_rgb / np.maximum(0.30 + 0.70 * old_ao, 0.15)[..., None], 0, 1)
old_rgb[~cover_sk] = 0
_tb = bmesh.new()
_uvl = _tb.loops.layers.uv.new("UVMap")
for t in range(len(P_sk)):
    vs = [_tb.verts.new(Vector(P_sk[t][j])) for j in range(3)]
    try:
        f = _tb.faces.new(vs)
    except ValueError:
        continue
    for lp, j in zip(f.loops, range(3)):
        lp[_uvl].uv = UVN_sk[t][j]
_tb.normal_update()
_occ = [shell_bm.copy()] + [b.copy() for b in occ_model] + [ck.bm_from_obj(o, apply_mods=False) for o in parts if o is not skin_ob and o["group"] not in ("cockpit_mirror", "cockpit_hudglass")]
AO_SK = int(os.environ.get("SKIN_AO_RES", "2048"))
ao_sk = cxm.bake_ao(_tb, _occ, (AO_SK, AO_SK), distance=0.035, samples=int(os.environ.get("AO_SAMPLES", "48")))
ao_sk = np.asarray(Image.fromarray((np.clip(ao_sk, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.6)).resize((SKIN_RES, SKIN_RES), Image.BICUBIC)).astype(np.float32) / 255
ao_sk = np.where(cover_sk, ao_sk, 1.0)
_e1, _e2 = UVN_sk[:, 1] - UVN_sk[:, 0], UVN_sk[:, 2] - UVN_sk[:, 0]
_uvarea = np.abs(_e1[:, 0] * _e2[:, 1] - _e1[:, 1] * _e2[:, 0]) / 2 * SKIN_RES ** 2
_nz = np.cross(P_sk[:, 1] - P_sk[:, 0], P_sk[:, 2] - P_sk[:, 0])
_top = (_nz[:, 2] / np.maximum(np.linalg.norm(_nz, axis=1), 1e-12) > 0.3) & (np.abs(P_sk.mean(1)[:, 0]) > 0.22)
dens = float(np.sqrt(_uvarea[_top].sum() / _area3[_top].sum()))
print(f"console skin: {dens:.0f} texels per metre on the console tops, {np.sqrt(_uvarea.sum() / _area3.sum()):.0f} overall")
_cent = P_sk.mean(1)


def skin_uv_of(p):
    d = np.linalg.norm(_cent - p, axis=1)
    for t in np.argsort(d)[:12]:
        f = ckskin.tri_affine(P_sk[t], UVN_sk[t])
        e1, e2 = P_sk[t][1] - P_sk[t][0], P_sk[t][2] - P_sk[t][0]
        n = np.cross(e1, e2)
        b = np.linalg.solve(np.array([e1, e2, n]).T, p - P_sk[t][0])
        if b[0] >= -0.02 and b[1] >= -0.02 and b[0] + b[1] <= 1.02 and abs(b[2]) * np.linalg.norm(n) < 0.01:
            return f
    return None


controls_sk = []
for kind, p, r_, f_, u_, rad in CTRL_LIST:
    fmap = skin_uv_of(p)
    if fmap is None:
        continue
    controls_sk.append((kind, p, r_, f_, u_, rad, fmap))
print(f"console skin: {len(controls_sk)} of {len(CTRL_LIST)} controls on the skin")
_tn = np.cross(P_sk[:, 1] - P_sk[:, 0], P_sk[:, 2] - P_sk[:, 0])
_tn /= np.maximum(np.linalg.norm(_tn, axis=1), 1e-12)[:, None]
nrm_sk = np.where(cover_sk[..., None], _tn[np.maximum(tid_sk, 0)], 0).astype(np.float32)
if os.environ.get("SKIN_DUMP"):
    np.savez_compressed(os.environ["SKIN_DUMP"], tid=tid_sk, pos=pos_sk, nrm=nrm_sk, old_rgb=old_rgb.astype(np.float16), ao=ao_sk.astype(np.float16),
                        cover=cover_sk, P=P_sk, UVN=UVN_sk, dens=dens,
                        ctrl=np.array([np.concatenate([c[1], c[2], c[3], c[4], [c[5]]]) for c in CTRL_LIST]),
                        ctrl_kind=np.array([c[0] for c in CTRL_LIST]))
if not os.environ.get("SKIP_SKIN_PAINT"):
    base_sk, height_sk, smooth_sk, emit_sk = ckskin.paint(tid_sk, pos_sk, nrm_sk, old_rgb, ao_sk, cover_sk, controls_sk, dens, SKIN_RES, skin_uv_of)
    base_sk = cp.dilate(base_sk, cover_sk)
    height_sk = cp.dilate(height_sk, cover_sk)
    smooth_sk = cp.dilate(smooth_sk, cover_sk)
    nx, ny, nz = cp.normal_from_height(height_sk, strength=3.0)
    cp.save(base_sk, os.path.join(OUT, "ckconsole_base.png"), "RGB")
    cp.save(cp.dilate(emit_sk, cover_sk), os.path.join(OUT, "ckconsole_emit.png"), "RGB")
    cp.save(cp.pack_normal(nx, ny), os.path.join(OUT, "ckconsole_normal.png"), "RGBA")
    _m = np.zeros((SKIN_RES, SKIN_RES, 4), np.float32)
    _m[..., 3] = smooth_sk
    cp.save(_m, os.path.join(OUT, "ckconsole_mask.png"), "RGBA")
    print("console skin textures written")

_free("_tb", "_occ", "cover_sk", "_tn", "_cent", "controls_sk")
for _v in ("old_rgb", "tid_sk", "pos_sk", "att_sk", "nrm_sk", "ao_sk", "old_ao", "base_sk", "height_sk", "smooth_sk", "emit_sk"):
    globals().pop(_v, None)
import gc; gc.collect()
tid_pn, pos_pn, att_pn = ckskin.raster_attr(UVN_pn, P_pn, UVO_pn, PANEL_RES, PANEL_RES)
cover_pn = tid_pn >= 0
old_pn = ckskin.sample(_orig, att_pn)
old_ao_pn = ckskin.sample(ao_old[..., None].astype(np.float32), att_pn)[..., 0]
old_pn = np.clip(old_pn / np.maximum(0.30 + 0.70 * old_ao_pn, 0.15)[..., None], 0, 1)
old_pn[~cover_pn] = 0
_tb = bmesh.new()
_uvl = _tb.loops.layers.uv.new("UVMap")
for t in range(len(P_pn)):
    vs = [_tb.verts.new(Vector(P_pn[t][j])) for j in range(3)]
    try:
        f = _tb.faces.new(vs)
    except ValueError:
        continue
    for lp, j in zip(f.loops, range(3)):
        lp[_uvl].uv = UVN_pn[t][j]
_tb.normal_update()
_occ = [shell_bm.copy()] + [b.copy() for b in occ_model] + [ck.bm_from_obj(o, apply_mods=False) for o in parts if o is not panel_ob and o["group"] not in ("cockpit_mirror", "cockpit_hudglass")]
ao_pn = cxm.bake_ao(_tb, _occ, (AO_SK, AO_SK), distance=0.035, samples=int(os.environ.get("AO_SAMPLES", "48")))
ao_pn = np.asarray(Image.fromarray((np.clip(ao_pn, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.6)).resize((PANEL_RES, PANEL_RES), Image.BICUBIC)).astype(np.float32) / 255
ao_pn = np.where(cover_pn, ao_pn, 1.0)
_e1, _e2 = UVN_pn[:, 1] - UVN_pn[:, 0], UVN_pn[:, 2] - UVN_pn[:, 0]
_uva = np.abs(_e1[:, 0] * _e2[:, 1] - _e1[:, 1] * _e2[:, 0]) / 2 * PANEL_RES ** 2
_a3 = np.linalg.norm(np.cross(P_pn[:, 1] - P_pn[:, 0], P_pn[:, 2] - P_pn[:, 0]), axis=1) / 2
dens_pn = float(np.sqrt(_uva.sum() / _a3.sum()))
print(f"panel skin: {dens_pn:.0f} texels per metre")
_tn = np.cross(P_pn[:, 1] - P_pn[:, 0], P_pn[:, 2] - P_pn[:, 0])
_tn /= np.maximum(np.linalg.norm(_tn, axis=1), 1e-12)[:, None]
nrm_pn = np.where(cover_pn[..., None], _tn[np.maximum(tid_pn, 0)], 0)
nrm_pn[np.einsum("ijk,ijk->ij", nrm_pn, ckpanel.EYE - pos_pn) < 0] *= -1
np.savez_compressed(os.path.join(OUT, "panel_dump.npz"), pos=pos_pn.astype(np.float32), nrm=np.round(nrm_pn * 127).astype(np.int8),
                    old=old_pn.astype(np.float16), ao=ao_pn.astype(np.float16), cover=cover_pn, dens=dens_pn,
                    atlas_P=ATLAS_P, atlas_UV=ATLAS_UV)
print("panel skin: data for paint_panel.py written (panel_dump.npz)")
_free("_tb", "_occ", "tid_pn", "pos_pn", "att_pn", "old_pn", "old_ao_pn", "ao_pn", "nrm_pn", "cover_pn", "_tn", "_orig")

if not os.environ.get("NO_SHELL_AO"):
    new_occ = [b.copy() for b in occ_model] + [ck.bm_from_obj(o, apply_mods=False) for o in parts if o["group"] not in ("cockpit_mirror", "cockpit_hudglass")]
    ao_new = cxm.bake_ao(bm_from_tris(shell[1], shell[2]), new_occ, (SW_, SH_), distance=0.22, samples=n_s)
    np.savez_compressed(os.path.join(OUT, "shell_ao.npz"), old=ao_old.astype(np.float16), new=ao_new.astype(np.float16))
    print("shell AO baked (old/new)")

GROUP_MTL = {"cockpit_conr": "ckconr", "cockpit_conl": "ckconl", "cockpit_gearpanel": "ckgear", "cockpit_dwppanel": "ckdwp", "cockpit_nvepanel": "cknve", "cockpit_stickgrip": "ckstick", "cockpit_panel": "ckpanel", "cockpit_keys": "ckpanel", "cockpit_stick": "ckdetail", "cockpit_hudframe": "ckdetail", "cockpit_hudglass": "hudglass", "cockpit_consoles": "ckconsole", "cockpit_seat": "ckdetail", "cockpit_controls": "ckdetail", "cockpit_frame": "ckdetail",
             "cockpit_mirror": "ckmirror", "cockpit_relief": "cockpit", "cockpit_throttle": "ckdetail", "cockpit_pedal_L": "ckdetail", "cockpit_pedal_R": "ckdetail", "cockpit_gearlever": "ckdetail"}
for _gn, _lv in SW_PARTS:
    GROUP_MTL[_gn] = "ckdetail"
new_groups = {}
for o in parts:
    P, UV, N = tri[o.name]
    if np.ndim(P) < 2 or len(P) == 0:
        print("  (empty part skipped:", o.name, ")")
        continue
    Pu, UVu, Nu = ck.to_unity(P, UV, N)
    g = o["group"]
    if g not in new_groups:
        new_groups[g] = [[], [], []]
    new_groups[g][0].append(Pu); new_groups[g][1].append(UVu); new_groups[g][2].append(Nu)
for g, (Pl, UVl, Nl) in new_groups.items():
    P = np.concatenate(Pl); N = np.concatenate(Nl)
    cr = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    ok = (np.einsum("ij,ij->i", cr, N.mean(1)) > 0).mean()
    print(f"  {g}: {len(P)} triangles, winding ok {ok * 100:.1f}%")


def write_obj(path, groups):
    lines = ["# Eurofighter Typhoon for Nuclear Option.",
             "# Source model: 'Eurofighter Typhoon - Fighter Jet - Free' by bohmerang (Sketchfab), CC BY-NC-SA 4.0.",
             "# Converted and split into parts for the mod (gear and weapon bay: build_gear_bay.py; cockpit detail: build_cockpit.py).",
             "# Unity axes: +X right, +Y up, +Z forward, metres."]
    vb = tb = nb = 1
    for name, P, UV, N, mtl in groups:
        if len(P) == 0:
            continue
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


allg = [tuple(g) for g in model]
for g, (Pl, UVl, Nl) in new_groups.items():
    allg.append((g, np.concatenate(Pl), np.concatenate(UVl), np.concatenate(Nl), GROUP_MTL[g]))
write_obj(os.path.join(OUT, "typhoon.obj"), allg)
tot = sum(len(np.concatenate(v[0])) for v in new_groups.values())
print(f"typhoon.obj written: {len(allg)} groups; cockpit detail {tot} triangles; seat triangles removed {len(OLD_SEAT[0])}")
