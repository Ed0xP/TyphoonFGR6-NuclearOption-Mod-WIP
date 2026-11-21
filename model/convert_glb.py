import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix
from PIL import Image

GLB, OUT = sys.argv[-2], sys.argv[-1]
TEX_SIZE = 2048
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

TO_MOD = Matrix.Rotation(math.radians(90), 4, 'Z') @ Matrix.Scale(0.1, 4)

SOURCES = {
    "Airframe_0": "airframe",
    "Canopy_1": "glass",
    "Cockpit_2": "cockpit",
    "LandingOff_5": "doors",
}


def mesh_under(empty_name):
    e = bpy.data.objects.get(empty_name)
    if e is None:
        raise SystemExit(f"node {empty_name} not found")
    kids = [c for c in e.children_recursive if c.type == 'MESH']
    if not kids:
        raise SystemExit(f"no mesh under {empty_name}")
    return kids[0]


def baked_bmesh(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(TO_MOD @ obj.matrix_world)
    bm.normal_update()
    return bm


def classify(c):
    x, y, z = c
    side = "L" if x < 0 else "R"
    ax = abs(x)
    if z > 1.15 and ax < 0.5 and y < 1.0:
        return "fin"
    if ax > 5.0:
        return "pod_" + side
    if ax > 0.95 and y > 5.6:
        return "canard_" + side
    if ax > 1.55 and y < 4.5:
        return "wing_" + side
    if y < -3.0 and z < 0.9 and ax < 1.3:
        return "nozzle_" + side
    if y > 8.5:
        return "fuselage_nose"
    if y > 4.3:
        return "fuselage_cockpit"
    return "fuselage"


def split(bm, names_for_face):
    groups = {}
    for f in bm.faces:
        groups.setdefault(names_for_face(f), []).append(f)
    out = {}
    uv_layer = bm.loops.layers.uv.active
    for name, faces in groups.items():
        nb = bmesh.new()
        nuv = nb.loops.layers.uv.new("UVMap")
        vmap = {}
        for f in faces:
            vs = []
            for v in f.verts:
                if v not in vmap:
                    vmap[v] = nb.verts.new(v.co)
                vs.append(vmap[v])
            try:
                nf = nb.faces.new(vs)
            except ValueError:
                continue
            nf.smooth = f.smooth
            if uv_layer is not None:
                for l_new, l_old in zip(nf.loops, f.loops):
                    l_new[nuv].uv = l_old[uv_layer].uv
        out[name] = nb
    return out


parts = {}
for node, role in SOURCES.items():
    obj = mesh_under(node)
    bm = baked_bmesh(obj)
    if role == "airframe":
        for name, nb in split(bm, lambda f: classify(f.calc_center_median())).items():
            parts[name] = (nb, "airframe")
    elif role == "glass":
        parts["canopy"] = (bm, "glass")
    elif role == "cockpit":
        parts["canopy_interior"] = (bm, "cockpit")
    elif role == "hud":
        parts["cockpit_hud"] = (bm, "hudglass")
    elif role == "doors":
        parts["geardoors"] = (bm, "airframe")

from mathutils import Vector


def cut_off(bm, plane_co, plane_no):
    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5, plane_co=plane_co, plane_no=plane_no)


def take(name, bm, pred):
    groups = split(bm, lambda f: "moved" if pred(f.calc_center_median()) else "rest")
    if "moved" in groups:
        parts[name] = (groups["moved"], "airframe")
    return groups.get("rest", bmesh.new())


def mean_z_near(bm, a, b, tol=0.12):
    a2, b2 = Vector((a.x, a.y)), Vector((b.x, b.y))
    d = (b2 - a2).normalized()
    zs = []
    for v in bm.verts:
        p = Vector((v.co.x, v.co.y))
        t = (p - a2).dot(d)
        if 0 <= t <= (b2 - a2).length and abs((p - a2 - d * t).length) < tol:
            zs.append(v.co.z)
    return sum(zs) / len(zs) if zs else a.z


SURFACES = []

for side, sx in (("R", 1), ("L", -1)):
    wbm, _ = parts["wing_" + side]
    A = Vector((1.22 * sx, -1.546, 0)); B = Vector((5.12 * sx, -1.825, 0))
    d = (B - A).normalized()
    n_aft = Vector((d.y, -d.x, 0)) * sx
    if n_aft.y > 0: n_aft = -n_aft
    SPLIT = 3.555
    cut_off(wbm, A, n_aft)
    cut_off(wbm, Vector((SPLIT * sx, 0, 0)), Vector((1, 0, 0)))
    aft = lambda c: (c - A).dot(n_aft) > 0 and 1.22 <= abs(c.x) <= 5.12
    zh = mean_z_near(wbm, A, B)
    rest = take("flaperon_in_" + side, wbm, lambda c: aft(c) and abs(c.x) < SPLIT)
    rest = take("flaperon_out_" + side, rest, lambda c: aft(c) and abs(c.x) >= SPLIT)
    parts["wing_" + side] = (rest, "airframe")
    ys = lambda x: -1.546 + (abs(x) - 1.22) * (-0.279 / 3.9)
    a_in, b_in = Vector((1.22 * sx, ys(1.22), zh)), Vector((SPLIT * sx, ys(SPLIT), zh))
    a_out, b_out = Vector((SPLIT * sx, ys(SPLIT), zh)), Vector((5.12 * sx, ys(5.12), zh))
    SURFACES.append(("flaperon_in_" + side, a_in, b_in, f"aileron_{side}_visible+flap_{side}_visible"))
    SURFACES.append(("flaperon_out_" + side, a_out, b_out, f"aileron_{side}_visible"))
    cbm, _ = parts["canard_" + side]
    zc = sum(v.co.z for v in cbm.verts) / max(1, len(cbm.verts))
    SURFACES.append(("canard_" + side, Vector((0.55 * sx, 7.65, zc)), Vector((1.9 * sx, 7.65, zc)), f"canard_{side}_visible"))

AB_X, AB_Z0, AB_Z1 = 0.19, 1.72, 3.48
fbm, _ = parts["fuselage"]
cut_off(fbm, Vector((0, AB_Z1, 0)), Vector((0, 1, 0)))
cut_off(fbm, Vector((0, AB_Z0, 0)), Vector((0, 1, 0)))
cut_off(fbm, Vector((AB_X, 0, 0)), Vector((1, 0, 0)))
cut_off(fbm, Vector((-AB_X, 0, 0)), Vector((1, 0, 0)))
def _is_ab(f):
    c = f.calc_center_median()
    return abs(c.x) < AB_X and AB_Z0 < c.y < AB_Z1 and c.z > 0.55 and f.normal.z > 0.4
groups = split(fbm, lambda f: "ab" if _is_ab(f) else "rest")
parts["fuselage"] = (groups["rest"], "airframe")
if "ab" in groups:
    abm = groups["ab"]
    parts["airbrake"] = (abm, "airframe")
    bay = abm.copy()
    for v in bay.verts: v.co.z -= 0.05
    parts["airbrake_bay"] = (bay, "dark")
    zh = max(v.co.z for v in abm.verts if v.co.y > AB_Z1 - 0.12)
    SURFACES.append(("airbrake", Vector((-AB_X, AB_Z1, zh)), Vector((AB_X, AB_Z1, zh)), "airbrake"))
    print("airbrake faces", len(abm.faces), "hinge height", round(zh, 3))

for side, sx in (("R", 1), ("L", -1)):
    nbm, _ = parts["nozzle_" + side]
    PETAL_Y = -3.55
    cut_off(nbm, Vector((0, PETAL_Y, 0)), Vector((0, 1, 0)))
    pet = lambda c: c.y < PETAL_Y and abs(c.x) > 0.15
    ring = [v.co for v in nbm.verts if v.co.y < -4.0 and abs(v.co.x) > 0.15]
    cx = sum(v.x for v in ring) / len(ring); cz = sum(v.z for v in ring) / len(ring)
    parts["nozzle_" + side] = (take("petals_" + side, nbm, pet), "airframe")
    SURFACES.append(("petals_" + side, Vector((cx, PETAL_Y, cz)), Vector((cx, PETAL_Y - 1, cz)), "vectoring"))

fbm, _ = parts["fin"]
P1, P2 = Vector((0, -3.042, 0.835)), Vector((0, -4.514, 3.004))
n_fin = (P2 - P1).cross(Vector((1, 0, 0))).normalized()
if n_fin.y > 0: n_fin = -n_fin
cut_off(fbm, P1, n_fin)
cut_off(fbm, Vector((0, 0, 3.0)), Vector((0, 0, 1)))
cut_off(fbm, Vector((0, 0, 0.85)), Vector((0, 0, 1)))
parts["fin"] = (take("rudder", fbm, lambda c: (c - P1).dot(n_fin) > 0 and 0.85 <= c.z <= 3.0), "airframe")
SURFACES.append(("rudder", P1, P2, "rudder_visible"))

TEX_FULL = 4096
CK_X0 = int(0.655 * TEX_FULL)
CK_Y0 = int((1 - 0.505) * TEX_FULL)
CK_U0, CK_W = CK_X0 / TEX_FULL, (TEX_FULL - CK_X0) / TEX_FULL
CK_H = (TEX_FULL - CK_Y0) / TEX_FULL
cbm_orig, _ = parts["canopy_interior"]


def uv_to_3d(bm, uvq, region):
    uvl = bm.loops.layers.uv.active
    best = None
    for f in bm.faces:
        if not region(f.calc_center_median()):
            continue
        ls = f.loops
        for i in range(1, len(ls) - 1):
            tri = (ls[0], ls[i], ls[i + 1])
            (a, b, c) = [Vector(l[uvl].uv) for l in tri]
            d = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y)
            if abs(d) < 1e-12:
                continue
            w1 = ((b.y - c.y) * (uvq[0] - c.x) + (c.x - b.x) * (uvq[1] - c.y)) / d
            w2 = ((c.y - a.y) * (uvq[0] - c.x) + (a.x - c.x) * (uvq[1] - c.y)) / d
            w3 = 1 - w1 - w2
            m = min(w1, w2, w3)
            if best is None or m > best[0]:
                best = (m, tri[0].vert.co * w1 + tri[1].vert.co * w2 + tri[2].vert.co * w3)
    return best[1]


SCREENS_PX = {"mfd_L": (886 + CK_X0, 1013 + CK_X0, 1914 + CK_Y0, 2039 + CK_Y0),
              "mfd_C": (1065 + CK_X0, 1190 + CK_X0, 1864 + CK_Y0, 1989 + CK_Y0),
              "mfd_R": (1243 + CK_X0, 1368 + CK_X0, 1915 + CK_Y0, 2039 + CK_Y0),
              "ufcp": (856 + CK_X0, 913 + CK_X0, 460 + CK_Y0, 543 + CK_Y0),
              "sadi": (350 + CK_X0, 412 + CK_X0, 122 + CK_Y0, 184 + CK_Y0)}
panel = lambda c: c.y > 6.9 and c.z > 0.6
SCREENS = {}
for name, (x0, x1, y0, y1) in SCREENS_PX.items():
    u0, u1 = x0 / TEX_FULL, x1 / TEX_FULL
    v0, v1 = 1 - y1 / TEX_FULL, 1 - y0 / TEX_FULL
    pts = [uv_to_3d(cbm_orig, (u, v), panel) for (u, v) in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
    cen = sum(pts, Vector()) / 4
    tl = min(pts, key=lambda p: (p - cen).x - (p - cen).z)
    tr = max(pts, key=lambda p: (p - cen).x + (p - cen).z)
    br = max(pts, key=lambda p: (p - cen).x - (p - cen).z)
    bl = min(pts, key=lambda p: (p - cen).x + (p - cen).z)
    SCREENS[name] = (tl, tr, br, bl)
    print(name, "centre", tuple(round(v, 3) for v in cen), "size", round((tr - tl).length, 3), "x", round((tr - br).length, 3))

STICK_PIVOT = Vector((0.0, 7.10, 0.46))


def components(bm):
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop(); comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index); stack.append(h)
        out.append(comp)
    return out


cbm_orig.faces.ensure_lookup_table()
stick_faces = set()
for comp in components(cbm_orig):
    vs = {v for f in comp for v in f.verts}
    mn = Vector((min(v.co.x for v in vs), min(v.co.y for v in vs), min(v.co.z for v in vs)))
    mx = Vector((max(v.co.x for v in vs), max(v.co.y for v in vs), max(v.co.z for v in vs)))
    if mn.y > 7.06 and mx.y < 7.215 and mn.x > -0.07 and mx.x < 0.07 and mn.z > 0.45 and mx.z < 0.75:
        stick_faces.update(f.index for f in comp)
print("stick faces", len(stick_faces))
groups = split(cbm_orig, lambda f: "stick" if f.index in stick_faces else "rest")
parts["canopy_interior"] = (groups["rest"], "cockpit")
parts["cockpit_stick"] = (groups["stick"], "cockpit")
SURFACES.append(("cockpit_stick", STICK_PIVOT, STICK_PIVOT + Vector((1, 0, 0)), "stick"))

for name in ("canopy_interior", "cockpit_stick"):
    bm_, _ = parts[name]
    uvl = bm_.loops.layers.uv.active
    for f in bm_.faces:
        for l in f.loops:
            u, v = l[uvl].uv
            l[uvl].uv = ((u - CK_U0) / CK_W, v / CK_H)

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("cockpit_extra", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cockpit_extra.py"))
cx = _ilu.module_from_spec(_spec); _spec.loader.exec_module(cx)
stick_bm, _ = parts["cockpit_stick"]
parts["cockpit_stick"] = (cx.smooth_part(stick_bm, 2, crease_angle=75), "cockpit")
shell_bm, _ = parts["canopy_interior"]
shell_bm.faces.index_update()
thr_faces = set()
for comp in components(shell_bm):
    vs = {v for f in comp for v in f.verts}
    if all(-0.445 < v.co.x < -0.305 and 6.86 < v.co.y < 6.975 and 0.47 < v.co.z < 0.585 for v in vs):
        thr_faces.update(f.index for f in comp)
shell_bm.faces.ensure_lookup_table()
groups = split(shell_bm, lambda f: "thr" if f.index in thr_faces else "rest")
parts["canopy_interior"] = (groups["rest"], "cockpit")
parts["cockpit_throttle"] = (groups["thr"], "cockpit")
TH_PIVOT = Vector((-0.352, 6.921, 0.18))
SURFACES.append(("cockpit_throttle", TH_PIVOT, TH_PIVOT + Vector((1, 0, 0)), "throttle"))
print("throttle faces", len(thr_faces))
hud_bm = baked_bmesh(mesh_under("HUD_3"))
parts["cockpit_hudframe"] = (cx.make_hud_frame(hud_bm), "cockpitdark")

EYE = Vector((0.0, 6.50, 1.16))

def export(path):
    lines = ["# Eurofighter Typhoon for Nuclear Option.",
             "# Source model: 'Eurofighter Typhoon - Fighter Jet - Free' by bohmerang (Sketchfab), CC BY-NC-SA 4.0.",
             "# Converted and split into parts for the mod. Unity axes: +X right, +Y up, +Z forward, metres."]
    vbase = tbase = nbase = 1
    total = 0
    order = ["canopy"] + sorted(k for k in parts if k != "canopy")
    for name in order:
        bm, mat = parts[name]
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.calc_loop_triangles()
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=math.radians(40))
        uv = me.uv_layers.active.data if me.uv_layers.active else None
        normals = me.corner_normals
        lines.append(f"o {name}")
        lines.append(f"usemtl {mat}")
        for v in me.vertices:
            x, y, z = v.co
            lines.append(f"v {x:.4f} {z:.4f} {y:.4f}")
        tidx, tlist, nidx, nlist, corner_t, corner_n = {}, [], {}, [], {}, {}
        for tri in me.loop_triangles:
            for li in tri.loops:
                if uv is not None:
                    u, w = uv[li].uv
                    k = f"{u:.5f} {w:.5f}"
                    if k not in tidx:
                        tidx[k] = len(tlist); tlist.append(k)
                    corner_t[li] = tidx[k]
                nx, ny, nz = normals[li].vector
                k = f"{nx:.4f} {nz:.4f} {ny:.4f}"
                if k not in nidx:
                    nidx[k] = len(nlist); nlist.append(k)
                corner_n[li] = nidx[k]
        lines.extend("vt " + k for k in tlist)
        lines.extend("vn " + k for k in nlist)
        for tri in me.loop_triangles:
            (a, b, c), (la, lb, lc) = tri.vertices, tri.loops
            def ref(vi, li):
                t = f"{tbase + corner_t[li]}" if uv is not None else ""
                return f"{vbase + vi}/{t}/{nbase + corner_n[li]}"
            lines.append(f"f {ref(a, la)} {ref(c, lc)} {ref(b, lb)}")
        vbase += len(me.vertices); tbase += len(tlist); nbase += len(nlist)
        total += len(me.loop_triangles)
        print(f"  {name:18} {mat:9} tris={len(me.loop_triangles)}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {path}: {len(parts)} parts, {total} triangles")


export(os.path.join(OUT, "typhoon.obj"))

mat = bpy.data.materials["Airframe"]
nodes = mat.node_tree.nodes
img_base = img_mr = img_nrm = None
mr_channels = {}
for n in nodes:
    if n.type != 'TEX_IMAGE' or n.image is None:
        continue
    for link in n.outputs[0].links:
        dest = link.to_node
        if dest.type == 'BSDF_PRINCIPLED' and link.to_socket.name == "Base Color":
            img_base = n.image
        elif dest.type == 'NORMAL_MAP':
            img_nrm = n.image
        elif dest.type in ('SEPARATE_COLOR', 'SEPRGB'):
            img_mr = n.image
            for out in dest.outputs:
                for l2 in out.links:
                    mr_channels[l2.to_socket.name] = out.name


def pixels(img):
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)[::-1]


def save(arr, path, mode="RGBA"):
    im = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode)
    im = im.resize((TEX_SIZE, TEX_SIZE), Image.LANCZOS)
    im.save(path, optimize=True)
    print("wrote", path, os.path.getsize(path) // 1024, "KB")


def save_full(arr, path, mode="RGBA"):
    im = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode)
    im.save(path, optimize=True)
    print("wrote", path, im.size, os.path.getsize(path) // 1024, "KB")


def crop(a):
    return a[CK_Y0:, CK_X0:]


b = pixels(img_base)
save(b[:, :, :3], os.path.join(OUT, "airframe_base.png"), "RGB")

CK_SCALE = 2
ck_h, ck_w = crop(b).shape[:2]
UPSCALED = os.environ.get("COCKPIT_UPSCALED", "")


def up2(a, mode):
    im = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), mode)
    return np.asarray(im.resize((ck_w * CK_SCALE, ck_h * CK_SCALE), Image.LANCZOS)).astype(np.float32) / 255.0


if UPSCALED and os.path.exists(UPSCALED):
    ckb = np.asarray(Image.open(UPSCALED).convert("RGB")).astype(np.float32) / 255.0
    print("cockpit colour: using", UPSCALED)
else:
    ckb = up2(crop(b)[:, :, :3], "RGB")
from PIL import ImageFilter
lum = ckb.mean(axis=2)
bg = np.asarray(Image.fromarray((lum * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))).astype(np.float32) / 255.0
green = (ckb[:, :, 1] > ckb[:, :, 0] + 0.12) & (ckb[:, :, 1] > 0.3)
legend = (lum - bg > 0.16) & (bg < 0.3)
emask = np.clip((green | legend).astype(np.float32), 0, 1)
emask = np.asarray(Image.fromarray((emask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))).astype(np.float32) / 255.0
emit = np.zeros_like(ckb)
tint = np.where(green[:, :, None], ckb, np.array([0.75, 1.0, 0.8], np.float32) * lum[:, :, None])
emit = np.clip(tint * emask[:, :, None] * 1.3, 0, 1)
save_full(emit, os.path.join(OUT, "cockpit_emit.png"), "RGB")
occ = [parts[k][0] for k in ("fuselage_cockpit", "fuselage", "cockpit_stick", "cockpit_throttle", "cockpit_throttle_base", "cockpit_hudframe") if k in parts]
ao = cx.bake_ao(parts["canopy_interior"][0], occ, (ck_w, ck_h), distance=0.22, samples=int(os.environ.get("AO_SAMPLES", "48")))
ao2 = np.asarray(Image.fromarray((np.clip(ao, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
                 .resize((ck_w * CK_SCALE, ck_h * CK_SCALE), Image.BILINEAR)).astype(np.float32) / 255.0
save_full(ao2, os.path.join(OUT, "cockpit_ao_preview.png"), "L")
ckb = ckb * (0.30 + 0.70 * ao2)[:, :, None]
save_full(ckb, os.path.join(OUT, "cockpit_base.png"), "RGB")

m = pixels(img_mr)
ch = {"Red": 0, "Green": 1, "Blue": 2}
rough = m[:, :, ch.get(mr_channels.get("Roughness", "Green"), 1)]
metal = m[:, :, ch.get(mr_channels.get("Metallic", "Blue"), 2)]
mask = np.zeros(m.shape, dtype=np.float32)
mask[:, :, 0] = metal
mask[:, :, 1] = metal
mask[:, :, 2] = metal
mask[:, :, 3] = 1.0 - rough
save(mask, os.path.join(OUT, "airframe_mask.png"))
save_full(crop(mask), os.path.join(OUT, "cockpit_mask.png"))
print("mask channels used:", mr_channels)

nm = pixels(img_nrm)
packed = np.ones(nm.shape, dtype=np.float32)
packed[:, :, 1] = nm[:, :, 1]
packed[:, :, 2] = nm[:, :, 1]
packed[:, :, 3] = nm[:, :, 0]
save(packed, os.path.join(OUT, "airframe_normal.png"))
save_full(crop(packed), os.path.join(OUT, "cockpit_normal.png"))

with open(os.path.join(OUT, "typhoon_surfaces.txt"), "w") as f:
    f.write("# part  hingeA(x y z)  hingeB(x y z)  drivers   -- Unity axes, metres. Drivers are the original jet's\n")
    f.write("# control-surface mesh names; '+' adds their deflections. The part rotates about A->B.\n")
    for name, a, b, drv in SURFACES:
        u = lambda v: f"{v.x:.4f} {v.z:.4f} {v.y:.4f}"
        f.write(f"{name} {u(a)} {u(b)} {drv}\n")

with open(os.path.join(OUT, "typhoon_materials.txt"), "w") as f:
    f.write("# name  key=value ...   (read by TyphoonMod; textures are next to this file)\n")
    f.write("airframe base=airframe_base.png normal=airframe_normal.png mask=airframe_mask.png smooth=1 metal=1\n")
    f.write("glass color=#141C24 alpha=0.35 smooth=0.95 metal=0\n")
    f.write("dark color=#0B0C0D smooth=0.2 metal=0\n")
    f.write("cockpit base=cockpit_base.png normal=cockpit_normal.png mask=cockpit_mask.png emit=cockpit_emit.png emitstrength=0.8 smooth=1 metal=1\n")
    f.write("cockpitdark color=#2B2E31 smooth=0.35 metal=0.1\n")

u3 = lambda v: f"{v.x:.4f} {v.z:.4f} {v.y:.4f}"
with open(os.path.join(OUT, "typhoon_cockpit.txt"), "w") as f:
    f.write("# Typhoon cockpit (Unity axes, metres, model space). Read by TyphoonMod.\n")
    f.write("# eye x y z            : the pilot's design eye point\n")
    f.write("# screen name  TL TR BR BL : display corners as the pilot sees them\n")
    f.write(f"eye {u3(EYE)}\n")
    f.write(f"stick {u3(STICK_PIVOT)}\n")
    for name, pts in SCREENS.items():
        f.write(f"screen {name} " + " ".join(u3(p) for p in pts) + "\n")
print("done")
