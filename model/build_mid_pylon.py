import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

args = [a for a in sys.argv[1:] if not a.startswith("--")]
OBJ_IN, TEX, OUT = args[-3], args[-2], args[-1]
MERGE = "--merge" in sys.argv
os.makedirs(OUT, exist_ok=True)

STATION_X = 3.20
HINGE = ((1.22, -1.546), (3.555, -1.713))
TAIL_GAP = 0.30
NOSE_GAP = 0.03
KEEL_Y = -0.76
HALF_W_TOP = 0.072
HALF_W_KEEL = 0.060
SINK = 0.035
NOSE_LEN = 0.16
NOSE_PLAN = 0.15
TAIL_START = 0.68
TAPER_START = 0.55
RINGS = 56
SIDE_PTS = 5
ARC_PTS = 9
TEXEL = 100.0
TEX_PATCH = (600, 96, 920, 216)
TEX_SIZE = 2048


def read_obj(path):
    V, VT, VN, groups, cur = [], [], [], [], None
    with open(path) as f:
        for line in f:
            if line.startswith("v "):
                V.append(tuple(float(x) for x in line.split()[1:4]))
            elif line.startswith("vt "):
                VT.append(tuple(float(x) for x in line.split()[1:3]))
            elif line.startswith("vn "):
                VN.append(tuple(float(x) for x in line.split()[1:4]))
            elif line.startswith("o "):
                cur = {"name": line[2:].strip(), "faces": []}
                groups.append(cur)
            elif line.startswith("f ") and cur is not None:
                cur["faces"].append([tuple(int(p) if p else 0 for p in (t.split("/") + ["", ""])[:3]) for t in line.split()[1:]])
    return V, VT, VN, groups


V, VT, VN, GROUPS = read_obj(OBJ_IN)


def u2b(p):
    return Vector((p[0], p[2], p[1]))


def b2u(p):
    return (p[0], p[2], p[1])


def group_bvh(name):
    g = next(g for g in GROUPS if g["name"] == name)
    verts, polys, remap = [], [], {}
    for f in g["faces"]:
        poly = []
        for t in f:
            if t[0] not in remap:
                remap[t[0]] = len(verts)
                verts.append(u2b(V[t[0] - 1]))
            poly.append(remap[t[0]])
        polys.append(poly)
    return BVHTree.FromPolygons(verts, polys), g


def lower_skin(bvh, x, z):
    hit = bvh.ray_cast(Vector((x, z, -3.0)), Vector((0, 0, 1)), 6.0)
    return hit[0].z if hit[0] is not None else None


def leading_edge(bvh, x):
    z = 6.0
    while z > -3.0:
        if lower_skin(bvh, x, z) is not None:
            return z
        z -= 0.005
    raise SystemExit(f"no wing found at x={x}")


def hinge_z(x):
    (x0, z0), (x1, z1) = HINGE
    t = (abs(x) - x0) / (x1 - x0)
    return z0 + (z1 - z0) * t


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def build_pylon(side):
    sx = -1.0 if side == "L" else 1.0
    bvh, _ = group_bvh("wing_" + side)
    xc = sx * STATION_X
    z_front = leading_edge(bvh, xc) - NOSE_GAP
    z_back = hinge_z(xc) + TAIL_GAP
    length = z_front - z_back

    def skin(x, z):
        y = lower_skin(bvh, x, z)
        if y is None:
            for k in range(1, 40):
                y = lower_skin(bvh, x, z - 0.01 * k)
                if y is not None:
                    break
        return y

    rings = []
    for i in range(RINGS + 1):
        s = 0.5 - 0.5 * math.cos(math.pi * i / RINGS)
        z = z_front - s * length
        if s < NOSE_PLAN:
            k = (s / NOSE_PLAN) ** 0.55
            k = max(k, 0.0)
        elif s > TAPER_START:
            k = 1 - 0.9 * smooth((s - TAPER_START) / (1 - TAPER_START)) ** 0.9
        else:
            k = 1.0
        wt, wk = HALF_W_TOP * k, HALF_W_KEEL * k
        top_c = skin(xc, z) + SINK
        if s < NOSE_LEN:
            e = 1 - (1 - s / NOSE_LEN) ** 2.2
            keel = top_c + (KEEL_Y - top_c) * e
        elif s > TAIL_START:
            t = (s - TAIL_START) / (1 - TAIL_START)
            keel = KEEL_Y + (top_c - 0.006 - KEEL_Y) * smooth(t) ** 0.85
        else:
            keel = KEEL_Y
        r = max(0.002, min(wk, (top_c - keel) * 0.45))
        ring = []
        ytl = skin(xc - wt, z) + SINK
        ytr = skin(xc + wt, z) + SINK
        for j in range(SIDE_PTS):
            t = j / SIDE_PTS
            y = ytl + (keel + r - ytl) * t
            w = wt + (wk - wt) * smooth(t)
            ring.append((xc - w, y, z))
        for j in range(ARC_PTS + 1):
            a = math.pi * j / ARC_PTS
            ring.append((xc - wk * math.cos(a), keel + r - r * math.sin(a) * (1.0 if wk > 1e-4 else 0.0), z))
        for j in range(1, SIDE_PTS + 1):
            t = 1 - j / SIDE_PTS
            y = ytr + (keel + r - ytr) * t
            w = wt + (wk - wt) * smooth(t)
            ring.append((xc + w, y, z))
        rings.append((s, z, ring))

    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    n = len(rings[0][2])
    vrows = [[bm.verts.new(u2b(p)) for p in ring] for _, _, ring in rings]
    x0, y0, x1, y1 = TEX_PATCH
    cy = (y0 + y1) * 0.5

    def girth(ring):
        d = [0.0]
        for a, b in zip(ring, ring[1:]):
            d.append(d[-1] + math.dist(a, b))
        mid = d[(len(d) - 1) // 2] if len(d) % 2 else (d[len(d) // 2 - 1] + d[len(d) // 2]) * 0.5
        return [t - mid for t in d]

    uvs = []
    for s, z, ring in rings:
        g = girth(ring)
        row = []
        for j in range(n):
            px = x0 + 4 + (z_front - z) * TEXEL
            py = cy + g[j] * TEXEL * (1 if side == "L" else -1)
            row.append((px / TEX_SIZE, 1 - py / TEX_SIZE))
        uvs.append(row)

    for i in range(len(rings) - 1):
        for j in range(n - 1):
            a, b, c, d = vrows[i][j], vrows[i][j + 1], vrows[i + 1][j + 1], vrows[i + 1][j]
            quad = (a, d, c, b) if side == "L" else (a, b, c, d)
            uq = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)] if side == "L" else [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)]
            try:
                f = bm.faces.new(quad)
            except ValueError:
                continue
            for loop, (ri, ci) in zip(f.loops, uq):
                loop[uv_layer].uv = uvs[ri][ci]
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=1e-5)
    bm.normal_update()
    centre = Vector((xc, 0.5 * (z_front + z_back), KEEL_Y + 0.15))
    out = sum((f.normal.dot(f.calc_center_median() - centre) for f in bm.faces), 0.0)
    if out < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bm.normal_update()

    mesh = bpy.data.meshes.new("pylon_mid_" + side)
    bm.to_mesh(mesh)
    bm.free()
    for p in mesh.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new("pylon_mid_" + side, mesh)
    bpy.context.collection.objects.link(obj)

    flat0 = z_front - NOSE_LEN * length
    flat1 = z_front - TAIL_START * length
    keel_mid = 0.5 * (flat0 + flat1)
    print(f"pylon_mid_{side}: x {xc:+.3f}, z {z_back:.3f}..{z_front:.3f} (length {length:.2f} m), "
          f"keel y {KEEL_Y:.3f} flat from z {flat1:.3f} to {flat0:.3f}, middle {keel_mid:.3f}")
    return obj, (xc, KEEL_Y, keel_mid)


bpy.ops.wm.read_factory_settings(use_empty=True)

mat = bpy.data.materials.new("airframe")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
img = bpy.data.images.load(os.path.abspath(TEX))
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.55
normal_png = os.path.join(os.path.dirname(os.path.abspath(TEX)), "airframe_normal.png")
if os.path.exists(normal_png):
    nimg = bpy.data.images.load(normal_png)
    nimg.colorspace_settings.name = "Non-Color"
    ntex = nt.nodes.new("ShaderNodeTexImage")
    ntex.image = nimg
    comb = nt.nodes.new("ShaderNodeCombineColor")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(ntex.outputs["Color"], sep.inputs["Color"])
    nt.links.new(ntex.outputs["Alpha"], comb.inputs["Red"])
    nt.links.new(sep.outputs["Green"], comb.inputs["Green"])
    comb.inputs["Blue"].default_value = 1.0
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(comb.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])


def add_reference(name):
    g = next(g for g in GROUPS if g["name"] == name)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    remap = {}
    for f in g["faces"]:
        vs = []
        for t in f:
            if t[0] not in remap:
                remap[t[0]] = bm.verts.new(u2b(V[t[0] - 1]))
            vs.append(remap[t[0]])
        try:
            face = bm.faces.new(list(reversed(vs)))
        except ValueError:
            continue
        for loop, t in zip(face.loops, reversed(f)):
            if t[1]:
                loop[uvl].uv = VT[t[1] - 1]
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    return o


stations = {}
pylons = []
for side in ("L", "R"):
    obj, st = build_pylon(side)
    obj.data.materials.append(mat)
    pylons.append(obj)
    stations[side] = st
    add_reference("wing_" + side)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.abspath(OUT), "pylon_mid.blend"))


def export_obj_text(objs, v0, vt0, vn0):
    lines, nv, nt_, nn = [], 0, 0, 0
    for o in objs:
        me = o.data
        me.calc_loop_triangles()
        uvl = me.uv_layers.active.data
        corner_normals = me.corner_normals
        vbase, tbase, nbase = v0 + nv, vt0 + nt_, vn0 + nn
        lines.append(f"o {o.name}")
        lines.append("usemtl airframe")
        for v in me.vertices:
            lines.append("v %.5f %.5f %.5f" % b2u(v.co))
        nv += len(me.vertices)
        uv_index, n_index, faces = {}, {}, []
        for tri in me.loop_triangles:
            idx = []
            for li in tri.loops:
                lp = me.loops[li]
                uv = tuple(round(c, 6) for c in uvl[li].uv)
                nrm = tuple(round(c, 5) for c in b2u(corner_normals[li].vector))
                if uv not in uv_index:
                    uv_index[uv] = len(uv_index)
                if nrm not in n_index:
                    n_index[nrm] = len(n_index)
                idx.append((lp.vertex_index, uv_index[uv], n_index[nrm]))
            faces.append(list(reversed(idx)))
        for uv in uv_index:
            lines.append("vt %.6f %.6f" % uv)
        for nrm in n_index:
            lines.append("vn %.5f %.5f %.5f" % nrm)
        for f in faces:
            lines.append("f " + " ".join(f"{vbase + a + 1}/{tbase + b + 1}/{nbase + c + 1}" for a, b, c in f))
        nt_ += len(uv_index)
        nn += len(n_index)
    return lines


header = ["# Middle underwing pylons for the Typhoon (build_mid_pylon.py). Unity axes: +X right, +Y up, +Z forward, metres."]
with open(os.path.join(OUT, "pylon_mid.obj"), "w") as f:
    f.write("\n".join(header + export_obj_text(pylons, 0, 0, 0)) + "\n")

if MERGE:
    with open(OBJ_IN) as f:
        src = f.read().splitlines()
    keep, skipping = [], False
    for line in src:
        if line.startswith("o "):
            skipping = line[2:].strip().startswith("pylon_mid_")
        if not skipping:
            keep.append(line)
    nv = sum(1 for l in keep if l.startswith("v "))
    nt2 = sum(1 for l in keep if l.startswith("vt "))
    nn = sum(1 for l in keep if l.startswith("vn "))
    out_lines = keep + export_obj_text(pylons, nv, nt2, nn)
    with open(os.path.join(OUT, "typhoon.obj"), "w") as f:
        f.write("\n".join(out_lines) + "\n")
    print(f"merged into {os.path.join(OUT, 'typhoon.obj')}")

for side, (x, y, z) in stations.items():
    print(f"STATION {side} {x:.3f} {y:.3f} {z:.3f}")
