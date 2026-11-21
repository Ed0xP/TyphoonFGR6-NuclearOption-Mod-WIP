import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

OUT = sys.argv[-1] if len(sys.argv) > 1 and not sys.argv[-1].endswith(".py") else os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)

LENGTH = 15.96
NOSE_Y = LENGTH / 2


def y_at(s):
    return NOSE_Y - s


MATERIALS = {
    "body":  (0.47, 0.50, 0.53, 1.0),
    "glass": (0.06, 0.08, 0.11, 1.0),
    "dark":  (0.04, 0.04, 0.045, 1.0),
    "metal": (0.30, 0.29, 0.28, 1.0),
}

bpy.ops.wm.read_factory_settings(use_empty=True)
for name, rgba in MATERIALS.items():
    m = bpy.data.materials.new(name)
    m.diffuse_color = rgba
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = 0.15 if name == "glass" else 0.55
    bsdf.inputs["Metallic"].default_value = 0.6 if name == "metal" else 0.0


def make_object(name, rings, material, cap_start=True, cap_end=True, smooth_angle=35):
    bm = bmesh.new()
    vrings = [[bm.verts.new(p) for p in ring] for ring in rings]
    n = len(rings[0])
    for a, b in zip(vrings, vrings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    for ring, do in ((vrings[0], cap_start), (vrings[-1], cap_end)):
        if do:
            c = bm.verts.new(sum((v.co for v in ring), Vector()) / len(ring))
            for i in range(n):
                bm.faces.new((ring[i], ring[(i + 1) % n], c))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(bpy.data.materials[material])
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    for p in me.polygons:
        p.use_smooth = True
    bm = bmesh.new()
    bm.from_mesh(me)
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(smooth_angle):
            e.smooth = False
    bm.to_mesh(me)
    bm.free()
    obj["material"] = material
    return obj


def superellipse_ring(s, half_w, top, bottom, zc=0.0, n=2.6, count=40, x0=0.0):
    pts = []
    for k in range(count):
        t = 2 * math.pi * k / count
        c, si = math.cos(t), math.sin(t)
        x = half_w * math.copysign(abs(c) ** (2 / n), c)
        h = top if si >= 0 else bottom
        z = zc + h * math.copysign(abs(si) ** (2 / n), si)
        pts.append((x0 + x, y_at(s), z))
    return pts


def interp_stations(stations, count):
    out = []
    for i in range(len(stations) - 1):
        a, b = stations[i], stations[i + 1]
        steps = count
        for k in range(steps):
            t = k / steps
            t2 = 0.5 - 0.5 * math.cos(math.pi * t)
            out.append(tuple(a[j] + (b[j] - a[j]) * (t if j == 0 else t2) for j in range(len(a))))
    out.append(stations[-1])
    return out


def airfoil(chord, thickness, count=18):
    def yt(x):
        return 5 * thickness * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)
    xs = [0.5 - 0.5 * math.cos(math.pi * i / (count - 1)) for i in range(count)]
    upper = [(x, yt(x) * chord) for x in xs]
    lower = [(x, -yt(x) * chord) for x in reversed(xs[1:-1])]
    return upper + lower


def lifting_surface(name, sections, material, vertical=False):
    rings = []
    for span, le_s, chord, tr, off in sections:
        ring = []
        for u, h in airfoil(chord, tr):
            y = y_at(le_s + u * chord)
            if vertical:
                ring.append((off + h, y, span))
            else:
                ring.append((span, y, off + h))
        rings.append(ring)
    return make_object(name, rings, material)


def mirror(obj, new_name):
    me = obj.data.copy()
    me.name = new_name
    me.transform(__import__("mathutils").Matrix.Scale(-1, 4, (1, 0, 0)))
    me.flip_normals()
    o = bpy.data.objects.new(new_name, me)
    o["material"] = obj["material"]
    bpy.context.scene.collection.objects.link(o)
    return o


FUSE = [
    (0.00, 0.010, 0.010, 0.010, -0.05),
    (0.35, 0.150, 0.140, 0.150, -0.05),
    (1.00, 0.300, 0.280, 0.300, -0.04),
    (1.90, 0.430, 0.400, 0.430, -0.02),
    (2.80, 0.520, 0.500, 0.520, 0.00),
    (3.70, 0.580, 0.560, 0.580, 0.00),
    (4.70, 0.640, 0.640, 0.620, 0.00),
    (5.70, 0.720, 0.720, 0.660, 0.00),
    (6.80, 0.880, 0.760, 0.660, 0.00),
    (8.20, 1.020, 0.760, 0.650, 0.00),
    (10.0, 1.060, 0.720, 0.640, 0.00),
    (12.0, 1.080, 0.640, 0.580, -0.02),
    (14.0, 1.060, 0.560, 0.520, -0.05),
    (15.2, 1.000, 0.500, 0.480, -0.08),
]
rings, stations = [], []
for s, w, top, bot, zc in interp_stations(FUSE, 4):
    stations.append(s)
    rings.append(superellipse_ring(s, w, top, bot, zc, n=2.9 if s > 9 else (2.4 if s > 6 else 2.1)))
i_cockpit = min(range(len(stations)), key=lambda i: abs(stations[i] - 2.5))
i_rear = min(range(len(stations)), key=lambda i: abs(stations[i] - 6.3))
make_object("fuselage_nose", rings[:i_cockpit + 1], "body", cap_end=False)
make_object("fuselage_cockpit", rings[i_cockpit:i_rear + 1], "body", cap_start=False, cap_end=False)
make_object("fuselage", rings[i_rear:], "body", cap_start=False)

CANOPY = [
    (2.55, 0.05, 0.47),
    (2.90, 0.30, 0.70),
    (3.40, 0.40, 0.88),
    (3.95, 0.43, 0.96),
    (4.60, 0.42, 0.94),
    (5.20, 0.38, 0.86),
    (5.70, 0.30, 0.76),
    (6.00, 0.18, 0.72),
]
rings = []
for s, w, top in interp_stations(CANOPY, 3):
    base = 0.40
    rings.append(superellipse_ring(s, w, top - base, 0.05, zc=base, n=2.2, count=28))
make_object("canopy", rings, "glass")

INTAKE = [
    (5.55, 0.78, 0.26, 0.26, -0.98),
    (5.80, 0.80, 0.30, 0.30, -0.96),
    (7.00, 0.80, 0.34, 0.30, -0.90),
    (8.60, 0.76, 0.30, 0.26, -0.80),
    (10.2, 0.66, 0.18, 0.14, -0.66),
    (11.2, 0.50, 0.06, 0.05, -0.62),
]
rings = []
for s, w, top, bot, zc in interp_stations(INTAKE, 3):
    rings.append(superellipse_ring(s, w, top, bot, zc, n=4.0, count=32))
make_object("intake", rings, "body", cap_start=False)
rings = [superellipse_ring(5.60, 0.72, 0.22, 0.20, -0.98, n=4.0, count=32),
         superellipse_ring(6.30, 0.70, 0.20, 0.18, -0.96, n=4.0, count=32)]
make_object("intake_duct", rings, "dark")

ROOT_X, TIP_X = 0.70, 5.22
WING_Z = -0.30
wing = lifting_surface("wing_R", [
    (ROOT_X, 6.90, 7.75, 0.050, WING_Z),
    (2.40,   9.10, 5.45, 0.045, WING_Z - 0.03),
    (TIP_X, 12.85, 1.45, 0.040, WING_Z - 0.10),
], "body")
mirror(wing, "wing_L")

def pod(name, x, s0, length, r, z):
    rings = []
    for s, rr in ((s0, 0.01), (s0 + 0.25, r * 0.8), (s0 + 0.6, r), (s0 + length - 0.3, r), (s0 + length, r * 0.55)):
        rings.append(superellipse_ring(s, rr, rr, rr, z, n=2.0, count=16, x0=x))
    return make_object(name, rings, "body")

p = pod("pod_R", TIP_X + 0.05, 12.20, 2.55, 0.13, WING_Z - 0.10)
mirror(p, "pod_L")

canard = lifting_surface("canard_R", [
    (0.60, 4.15, 1.75, 0.06, -0.02),
    (2.15, 5.55, 0.60, 0.05, -0.08),
], "body")
mirror(canard, "canard_L")

lifting_surface("fin", [
    (0.55, 10.90, 4.20, 0.060, 0.0),
    (1.10, 11.75, 3.25, 0.055, 0.0),
    (3.40, 14.30, 1.15, 0.050, 0.0),
], "body", vertical=True)

def nozzle(name, x):
    z = -0.10
    outer = [(14.9, 0.46), (15.4, 0.45), (15.96, 0.40)]
    inner = [(15.96, 0.34), (15.3, 0.33)]
    rings = [superellipse_ring(s, r, r, r, z, n=2.0, count=24, x0=x) for s, r in outer + inner]
    make_object(name, rings, "metal", smooth_angle=60)
    make_object(name + "_core", [superellipse_ring(15.3, 0.33, 0.33, 0.33, z, n=2.0, count=24, x0=x),
                                 superellipse_ring(15.5, 0.20, 0.20, 0.20, z, n=2.0, count=24, x0=x)], "dark")

nozzle("nozzle_R", 0.50)
nozzle("nozzle_L", -0.50)


def export_obj(path):
    lines = ["# Eurofighter Typhoon-style airframe for Nuclear Option (procedural)",
             "# Unity axes: +X right, +Y up, +Z forward, metres"]
    vbase = nbase = 1
    for obj in sorted(bpy.data.objects, key=lambda o: o.name):
        if obj.type != "MESH":
            continue
        me = obj.data
        me.calc_loop_triangles()
        lines.append(f"o {obj.name}")
        lines.append(f"usemtl {obj['material']}")
        for v in me.vertices:
            x, y, z = v.co
            lines.append(f"v {x:.4f} {z:.4f} {y:.4f}")
        normals = me.corner_normals
        nidx, nlist = {}, []
        corner = {}
        for tri in me.loop_triangles:
            for li in tri.loops:
                nx, ny, nz = normals[li].vector
                key = f"{nx:.4f} {nz:.4f} {ny:.4f}"
                if key not in nidx:
                    nidx[key] = len(nlist)
                    nlist.append(key)
                corner[li] = nidx[key]
        lines.extend("vn " + k for k in nlist)
        for tri in me.loop_triangles:
            (a, b, c), (la, lb, lc) = tri.vertices, tri.loops
            na, nb, nc = (nbase + corner[l] for l in (la, lb, lc))
            lines.append(f"f {vbase + a}//{na} {vbase + c}//{nc} {vbase + b}//{nb}")
        vbase += len(me.vertices)
        nbase += len(nlist)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


export_obj(os.path.join(OUT, "typhoon.obj"))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "typhoon.blend"))

tris = sum(len(o.data.loop_triangles) for o in bpy.data.objects if o.type == "MESH")
print(f"objects={len([o for o in bpy.data.objects if o.type == 'MESH'])} triangles={tris}")
