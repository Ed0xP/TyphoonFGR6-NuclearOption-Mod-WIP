import math, os, sys
import bpy, bmesh
from mathutils import Vector, Matrix

OBJ, TEXDIR, OUTP = sys.argv[1], sys.argv[2], sys.argv[3]
VIEWS = sys.argv[4].split(",") if len(sys.argv) > 4 else ["eye", "seat", "left", "right", "canopy"]
RES = int(sys.argv[5]) if len(sys.argv) > 5 else 1000
SAMPLES = int(os.environ.get("SAMPLES", "32"))
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.samples = SAMPLES
sc.cycles.device = 'CPU'
sc.cycles.use_denoising = os.environ.get("NO_DENOISE") is None
sc.view_settings.view_transform = 'Standard'

def u2b(p): return Vector((p[0], p[2], p[1]))

imgs = {}
def img(name, noncolor=False):
    p = os.path.join(TEXDIR, name)
    if p not in imgs:
        im = bpy.data.images.load(p)
        if noncolor: im.colorspace_settings.name = 'Non-Color'
        imgs[p] = im
    return imgs[p]

def hexcol(s):
    s = s.lstrip('#'); c = [int(s[i:i+2], 16) / 255 for i in (0, 2, 4)]
    return [((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c] + [1]

mats = {}
for line in open(os.path.join(TEXDIR, "typhoon_materials.txt")):
    t = line.split()
    if not t or t[0].startswith('#'): continue
    kv = dict(x.split('=', 1) for x in t[1:] if '=' in x)
    m = bpy.data.materials.new(t[0]); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    sm = float(kv.get("smooth", 0.5)); mt = float(kv.get("metal", 0))
    b.inputs["Roughness"].default_value = 1 - sm
    b.inputs["Metallic"].default_value = mt
    tile = float(kv.get("tile", 1))
    uvn = None
    if tile != 1:
        tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (tile, tile, 1)
        nt.links.new(tc.outputs["UV"], mp.inputs["Vector"]); uvn = mp.outputs["Vector"]
    col = hexcol(kv["color"]) if "color" in kv else None
    if "base" in kv:
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = img(kv["base"])
        if col:
            mix = nt.nodes.new("ShaderNodeMixRGB"); mix.blend_type = 'MULTIPLY'; mix.inputs[0].default_value = 1
            nt.links.new(tx.outputs["Color"], mix.inputs[1]); mix.inputs[2].default_value = col
            nt.links.new(mix.outputs[0], b.inputs["Base Color"])
        else:
            nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
    elif col:
        b.inputs["Base Color"].default_value = col
    if "mask" in kv:
        mk = nt.nodes.new("ShaderNodeTexImage"); mk.image = img(kv["mask"], True)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(mk.outputs["Color"], sep.inputs[0])
        mul = nt.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = mt
        nt.links.new(sep.outputs[0], mul.inputs[0]); nt.links.new(mul.outputs[0], b.inputs["Metallic"])
        inv = nt.nodes.new("ShaderNodeMath"); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1
        sm2 = nt.nodes.new("ShaderNodeMath"); sm2.operation = 'MULTIPLY'; sm2.inputs[1].default_value = sm
        nt.links.new(mk.outputs["Alpha"], sm2.inputs[0]); nt.links.new(sm2.outputs[0], inv.inputs[1])
        nt.links.new(inv.outputs[0], b.inputs["Roughness"])
        if uvn: nt.links.new(uvn, mk.inputs["Vector"])
    if "normal" in kv:
        nm = nt.nodes.new("ShaderNodeTexImage"); nm.image = img(kv["normal"], True)
        nn = nt.nodes.new("ShaderNodeNormalMap"); nn.inputs["Strength"].default_value = float(kv.get("bump", 1))
        if nm.image.channels == 4:
            sp = nt.nodes.new("ShaderNodeSeparateColor"); cb = nt.nodes.new("ShaderNodeCombineColor")
            nt.links.new(nm.outputs["Color"], sp.inputs[0])
            nt.links.new(nm.outputs["Alpha"], cb.inputs[0]); nt.links.new(sp.outputs[1], cb.inputs[1]); cb.inputs[2].default_value = 1
            nt.links.new(cb.outputs[0], nn.inputs["Color"])
        else:
            nt.links.new(nm.outputs["Color"], nn.inputs["Color"])
        nt.links.new(nn.outputs["Normal"], b.inputs["Normal"])
        if uvn: nt.links.new(uvn, nm.inputs["Vector"])
    if "emit" in kv:
        em = nt.nodes.new("ShaderNodeTexImage"); em.image = img(kv["emit"])
        nt.links.new(em.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = float(kv.get("emitstrength", 1))
    if uvn:
        for n in nt.nodes:
            if n.type == 'TEX_IMAGE' and not n.inputs["Vector"].links: nt.links.new(uvn, n.inputs["Vector"])
    if float(kv.get("alpha", 1)) < 1:
        b.inputs["Alpha"].default_value = float(kv["alpha"])
        if "base" in kv:
            for n_ in nt.nodes:
                if n_.type == 'TEX_IMAGE' and n_.image is not None and n_.image.name.startswith(os.path.basename(kv["base"])[:20]):
                    nt.links.new(n_.outputs["Alpha"], b.inputs["Alpha"])
                    break
        try:
            m.blend_method = 'BLEND'
        except Exception:
            pass
    mats[t[0]] = m

V, VT, VN = [], [], []
groups, cur = [], None
for line in open(OBJ):
    if line.startswith("v "): V.append([float(x) for x in line.split()[1:4]])
    elif line.startswith("vt "): VT.append([float(x) for x in line.split()[1:3]])
    elif line.startswith("vn "): VN.append([float(x) for x in line.split()[1:4]])
    elif line.startswith("o "): cur = {"name": line[2:].strip(), "mtl": "airframe", "f": []}; groups.append(cur)
    elif line.startswith("usemtl"): cur["mtl"] = line.split()[1]
    elif line.startswith("f "): cur["f"].append([[int(p) if p else 0 for p in (t.split("/") + ["", ""])[:3]] for t in line.split()[1:]])
SKIP = os.environ.get("SKIP", "^(canopy|gear_|bay_|wing|flaperon|pod|pylon|nozzle|petals|fin|rudder|airbrake)").strip()
import re
skip = re.compile(SKIP) if SKIP else None
for g in groups:
    if skip and skip.search(g["name"]) and g["name"] != "canopy_interior": continue
    bm = bmesh.new(); uvl = bm.loops.layers.uv.new("UVMap"); remap = {}
    normals = []
    for f in g["f"]:
        vs = []
        for t in f:
            if t[0] not in remap: remap[t[0]] = bm.verts.new(u2b(V[t[0] - 1]))
            vs.append(remap[t[0]])
        try: face = bm.faces.new(list(reversed(vs)))
        except ValueError: continue
        for loop, t in zip(face.loops, list(reversed(f))):
            if t[1]: loop[uvl].uv = VT[t[1] - 1]
            normals.append(u2b(VN[t[2] - 1]) if t[2] else None)
    me = bpy.data.meshes.new(g["name"]); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    if normals and all(n is not None for n in normals) and len(normals) == len(me.loops):
        try: me.normals_split_custom_set([tuple(n) for n in normals])
        except Exception: pass
    o = bpy.data.objects.new(g["name"], me); sc.collection.objects.link(o)
    o.data.materials.append(mats.get(g["mtl"]) or mats["airframe"])

scr = bpy.data.materials.new("screen"); scr.use_nodes = True
sb = scr.node_tree.nodes["Principled BSDF"]; sb.inputs["Base Color"].default_value = (0.02, 0.05, 0.25, 1)
sb.inputs["Emission Color"].default_value = (0.05, 0.15, 0.7, 1); sb.inputs["Emission Strength"].default_value = 2
eye = Vector((0, 6.5, 1.16))
for line in open(os.path.join(TEXDIR, "typhoon_cockpit.txt")):
    t = line.split()
    if t and t[0] == "eye": eye = u2b([float(x) for x in t[1:4]])
    if t and t[0] == "screen":
        pts = [u2b([float(x) for x in t[2 + 3 * i: 5 + 3 * i]]) for i in range(4)]
        n = (pts[1] - pts[0]).cross(pts[3] - pts[0]).normalized()
        pts = [p - n * ((float(t[14]) if len(t) > 14 else 0.0025) - 0.0003) for p in pts]
        me = bpy.data.meshes.new(t[1]); me.from_pydata(pts, [], [(0, 1, 2, 3)])
        o = bpy.data.objects.new("scr_" + t[1], me); sc.collection.objects.link(o); me.materials.append(scr)

w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.62, 0.72, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = float(os.environ.get("SKY", "1.0"))
sun = bpy.data.lights.new("sun", 'SUN'); sun.energy = float(os.environ.get("SUN", "3.5")); sun.angle = math.radians(2)
so = bpy.data.objects.new("sun", sun); sc.collection.objects.link(so)
so.rotation_euler = (math.radians(35), math.radians(-20), math.radians(30))

cam = bpy.data.cameras.new("cam"); co = bpy.data.objects.new("cam", cam); sc.collection.objects.link(co); sc.camera = co

def look(pos, target, fov=80, w_=RES, h_=None):
    co.location = pos
    d = (Vector(target) - Vector(pos)).normalized()
    co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam.angle = math.radians(fov); cam.clip_start = 0.02
    sc.render.resolution_x = w_; sc.render.resolution_y = h_ or int(w_ * 0.75)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'model'))
import dwp_panel, nve_panel
views = {
    "eye":    (eye, eye + Vector((0, 1, -0.32)), 85),
    "seat":   (eye + Vector((0.0, 0.85, 0.15)), eye + Vector((0, -0.15, -0.75)), 70),
    "left":   (eye + Vector((0.05, 0.05, -0.05)), eye + Vector((-0.6, 0.45, -0.55)), 75),
    "right":  (eye + Vector((-0.05, 0.05, -0.05)), eye + Vector((0.6, 0.45, -0.55)), 75),
    "pedestal": (Vector((0.16, 6.86, 0.64)), Vector((0.0, 7.08, 0.47)), 50),
    "pedside": (Vector((0.30, 7.02, 0.56)), Vector((0.0, 7.08, 0.42)), 50),
    "gearpanel": (Vector((-0.12, 6.80, 0.86)), Vector((-0.40, 7.15, 0.565)), 45),
    "geareye": (eye, Vector((-0.40, 7.145, 0.567)), 24),
    "gearn": (Vector((-0.341, 6.814, 0.819)), Vector((-0.40, 7.145, 0.567)), 36),
    "ped2": (Vector((0.24, 6.82, 0.80)), Vector((0, 7.10, 0.45)), 36),
    "pedeye": (eye, Vector((0, 7.09, 0.47)), 24),
    "dwpe": (eye, Vector(dwp_panel.FR.pt(30, 10)), 22),
    "dwpc": (Vector(dwp_panel.FR.pt(25, 15)) + (eye - Vector(dwp_panel.FR.pt(25, 15))).normalized() * 0.36, Vector(dwp_panel.FR.pt(25, 15)), 40),
    "nvee": (eye, Vector(nve_panel.FR.pt(0, 70)), 20),
    "nvel": (Vector((-0.20, 6.84, 0.80)), Vector(nve_panel.FR.pt(-20, 70)), 30),
    "nver": (Vector((0.20, 6.84, 0.80)), Vector(nve_panel.FR.pt(30, 75)), 30),
    "rcon":    (eye + Vector((-0.05, 0.05, -0.05)), eye + Vector((0.6, 0.45, -0.55)), 75),
    "canopy": (eye + Vector((0, -0.25, -0.1)), eye + Vector((0, 1, 0.35)), 100),
    "back":   (eye + Vector((0, 0.3, 0.05)), eye + Vector((0, -1, 0.15)), 95),
    "seatf":  (Vector((0, 7.02, 1.38)), Vector((0, 6.55, 0.62)), 62),
    "seatq":  (Vector((0.55, 7.0, 1.25)), Vector((0, 6.5, 0.7)), 55),
    "panelL": (eye + Vector((-0.05, 0.25, -0.12)), Vector((-0.24, 7.3, 0.86)), 50),
    "panelR": (eye + Vector((0.05, 0.25, -0.12)), Vector((0.24, 7.3, 0.86)), 50),
    "panelC": (eye + Vector((0.0, 0.3, -0.1)), Vector((0.0, 7.3, 0.84)), 42),
    "stick":  (eye + Vector((0.06, 0.25, -0.12)), Vector((0, 7.12, 0.66)), 26),
    "rclose": (Vector((0.22, 6.72, 0.80)), Vector((0.37, 6.93, 0.50)), 22),
    "lclose": (Vector((-0.22, 6.50, 0.80)), Vector((-0.37, 6.68, 0.48)), 22),
    "thr":    (eye + Vector((-0.05, 0.10, -0.10)), Vector((-0.352, 6.93, 0.52)), 30),
    "down":   (eye + Vector((0, 0.1, 0.0)), eye + Vector((0, 0.45, -1)), 95),
    "ext":    (eye + Vector((1.6, 1.2, 1.0)), eye + Vector((0, 0.3, -0.35)), 50),
    "extl":   (eye + Vector((-1.4, -0.6, 0.9)), eye + Vector((0, 0.35, -0.35)), 55),
}
for _x in filter(None, os.environ.get("XVIEWS", "").split(";")):
    _n, _p, _t, _f = _x.split(":")
    views[_n] = (u2b([float(q) for q in _p.split(",")]), u2b([float(q) for q in _t.split(",")]), float(_f))
    if _n not in VIEWS and os.environ.get("XONLY"): VIEWS.append(_n)
if os.environ.get("XONLY"): VIEWS = [v for v in VIEWS if v in views and v in os.environ.get("XVIEWS", "")]
for v in VIEWS:
    p, tg, fov = views[v]
    look(p, tg, fov)
    sc.render.filepath = f"{OUTP}_{v}.png"
    bpy.ops.render.render(write_still=True)
    print("wrote", sc.render.filepath)
