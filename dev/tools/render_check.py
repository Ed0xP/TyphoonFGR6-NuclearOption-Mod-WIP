import math, os, sys
import numpy as np
import bpy, bmesh
from mathutils import Vector, Euler, Matrix

OBJ, TEXDIR, OUTP = sys.argv[1], sys.argv[2], sys.argv[3]
STORES = sys.argv[4] if len(sys.argv) > 4 else None
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.samples = 24
sc.cycles.device = 'CPU'
sc.render.resolution_x, sc.render.resolution_y = 1400, 800

def u2b(p): return Vector((p[0], p[2], p[1]))

def mk_mat(name, color=None, tex=None, rough=0.5, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    if tex:
        t = m.node_tree.nodes.new("ShaderNodeTexImage"); t.image = bpy.data.images.load(tex)
        m.node_tree.links.new(t.outputs["Color"], b.inputs["Base Color"])
    else:
        b.inputs["Base Color"].default_value = color
    return m

mats = {
    "airframe": mk_mat("airframe", tex=os.path.join(TEXDIR, "airframe_base.png")),
    "glass": mk_mat("glass", (0.05, 0.07, 0.1, 1), rough=0.1),
    "dark": mk_mat("dark", (0.03, 0.03, 0.03, 1)),
    "lamp": mk_mat("lamp", (0.95, 0.95, 0.9, 1), rough=0.2),
    "bayinner": mk_mat("bayinner", (0.42, 0.45, 0.47, 1), rough=0.6),
    "baywall": mk_mat("baywall", (0.37, 0.40, 0.42, 1), rough=0.6),
    "bayrib": mk_mat("bayrib", (0.21, 0.23, 0.25, 1), rough=0.6),
    "baylip": mk_mat("baylip", (0.043, 0.048, 0.055, 1), rough=0.6),
    "drum": mk_mat("drum", (0.3, 0.31, 0.33, 1), rough=0.4, metal=0.6),
}
def mk_pbr(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage"); t.image = bpy.data.images.load(os.path.join(TEXDIR, name + "_base.png"))
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    mp = os.path.join(TEXDIR, name + "_mask.png")
    if os.path.exists(mp):
        tm = nt.nodes.new("ShaderNodeTexImage"); tm.image = bpy.data.images.load(mp); tm.image.colorspace_settings.name = "Non-Color"
        inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
        nt.links.new(tm.outputs["Alpha"], inv.inputs[1]); nt.links.new(inv.outputs[0], b.inputs["Roughness"])
        sepm = nt.nodes.new("ShaderNodeSeparateColor"); nt.links.new(tm.outputs["Color"], sepm.inputs[0]); nt.links.new(sepm.outputs[0], b.inputs["Metallic"])
    npth = os.path.join(TEXDIR, name + "_normal.png")
    if os.path.exists(npth):
        tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = bpy.data.images.load(npth); tn.image.colorspace_settings.name = "Non-Color"
        sep = nt.nodes.new("ShaderNodeSeparateColor"); comb = nt.nodes.new("ShaderNodeCombineColor")
        nt.links.new(tn.outputs["Color"], sep.inputs[0])
        nt.links.new(tn.outputs["Alpha"], comb.inputs[0]); nt.links.new(sep.outputs[1], comb.inputs[1]); comb.inputs[2].default_value = 1.0
        nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(comb.outputs[0], nm.inputs["Color"]); nt.links.new(nm.outputs[0], b.inputs["Normal"])
    return m
mats["abmetal"] = mk_mat("abmetal", (0.045, 0.038, 0.032, 1), rough=0.55, metal=0.85)
mats["irstglass"] = mk_mat("irstglass", (0.003, 0.004, 0.006, 1), rough=0.05)
mats["irstlens"] = mk_mat("irstlens", (0.10, 0.06, 0.03, 1), rough=0.03, metal=1.0)
mats["irstmetal"] = mk_mat("irstmetal", (0.11, 0.12, 0.13, 1), rough=0.38, metal=0.9)
for _n in ("exfus", "exwing", "exfin", "exmisc", "nozzle"):
    if os.path.exists(os.path.join(TEXDIR, _n + "_base.png")):
        mats[_n] = mk_pbr(_n)
V, VT = [], []
groups, cur = [], None
for line in open(OBJ):
    if line.startswith("v "): V.append([float(x) for x in line.split()[1:4]])
    elif line.startswith("vt "): VT.append([float(x) for x in line.split()[1:3]])
    elif line.startswith("o "): cur = {"name": line[2:].strip(), "mtl": "airframe", "f": []}; groups.append(cur)
    elif line.startswith("usemtl"): cur["mtl"] = line.split()[1]
    elif line.startswith("f "): cur["f"].append([[int(p) if p else 0 for p in (t.split("/") + ["", ""])[:3]] for t in line.split()[1:]])
VECTOR = math.radians(float(os.environ.get("VECTOR", "0")))
BAYOPEN = float(os.environ.get("BAYOPEN", "0"))
_BAYD = {}
if BAYOPEN:
    _gf = os.path.join(os.path.dirname(OBJ), "typhoon_gear.txt")
    for _l in open(_gf):
        _t = _l.split()
        if _t and _t[0] == "baydoor":
            _h = [float(v) for v in _t[_t.index("hinge") + 1:_t.index("hinge") + 4]]
            _a = np.array([float(v) for v in _t[_t.index("axis") + 1:_t.index("axis") + 4]]); _a /= np.linalg.norm(_a)
            _ang = math.radians(float(_t[_t.index("open") + 1]) * BAYOPEN)
            _K = np.array([[0, -_a[2], _a[1]], [_a[2], 0, -_a[0]], [-_a[1], _a[0], 0]])
            _R = np.eye(3) + math.sin(_ang) * _K + (1 - math.cos(_ang)) * _K @ _K
            for _n in (_t[1], _t[2]): _BAYD[_n] = (np.array(_h), _R)
def _vec(name, p):
    if name in _BAYD:
        h, R = _BAYD[name]; return list(R @ (np.array(p) - h) + h)
    if not VECTOR or not name.startswith(("petals_", "nozcollar_")): return p
    y, z = p[1] + 0.0392, p[2] + 3.55
    return [p[0], y * math.cos(VECTOR) - z * math.sin(VECTOR) - 0.0392, y * math.sin(VECTOR) + z * math.cos(VECTOR) - 3.55]
for g in groups:
    if g["name"].startswith(("cockpit", "canopy_interior")): continue
    bm = bmesh.new(); uvl = bm.loops.layers.uv.new("UVMap"); remap = {}
    for f in g["f"]:
        vs = []
        for t in f:
            if t[0] not in remap: remap[t[0]] = bm.verts.new(u2b(_vec(g["name"], V[t[0] - 1])))
            vs.append(remap[t[0]])
        try: face = bm.faces.new(list(reversed(vs)))
        except ValueError: continue
        for loop, t in zip(face.loops, list(reversed(f))):
            if t[1]: loop[uvl].uv = VT[t[1] - 1]
    me = bpy.data.meshes.new(g["name"]); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(g["name"], me); sc.collection.objects.link(o)
    o.data.materials.append(mats.get(g["mtl"], mats["airframe"]) if g["mtl"] in mats else mats["airframe"])

store_mat = mk_mat("store", (0.85, 0.85, 0.8, 1), rough=0.4)
rail_mat = mk_mat("rail", (0.25, 0.25, 0.27, 1), rough=0.5)
if STORES:
    for line in open(STORES):
        p = line.split()
        if not p or p[0].startswith("#"): continue
        kind = p[0]
        x, y, z, pi, ya, ro = map(float, p[1:7])
        if kind == "box":
            sx, sy, sz = map(float, p[7:10])
            bpy.ops.mesh.primitive_cube_add(size=1)
            o = bpy.context.object; o.scale = (sx, sz, sy); bpy.ops.object.transform_apply(scale=True)
            o.data.materials.append(rail_mat)
        else:
            L, r = float(p[7]), float(p[8]); span = float(p[9]) if len(p) > 9 else r * 4
            bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=L, vertices=20)
            o = bpy.context.object; o.rotation_euler = (math.radians(90), 0, 0)
            bpy.ops.object.transform_apply(rotation=True)
            bpy.ops.mesh.primitive_cone_add(radius1=r, depth=r * 4, vertices=20, location=(0, L / 2 + r * 2, 0), rotation=(math.radians(-90), 0, 0))
            cone = bpy.context.object
            for a in (45, 135):
                bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -L / 2 + 0.2, 0), rotation=(0, math.radians(a), 0))
                f = bpy.context.object; f.scale = (span, 0.3, 0.01)
                bpy.ops.object.transform_apply(scale=True, rotation=True)
                f.select_set(True)
            cone.select_set(True); o.select_set(True); bpy.context.view_layer.objects.active = o
            bpy.ops.object.join()
            o.data.materials.append(store_mat)
        q = (Matrix.Rotation(math.radians(ya), 4, 'Y') @ Matrix.Rotation(math.radians(pi), 4, 'X') @ Matrix.Rotation(math.radians(ro), 4, 'Z'))
        swap = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
        Mb = swap @ Matrix.Translation((x, y, z)) @ q @ swap
        o.matrix_world = Mb

REHEAT = float(os.environ["REHEAT"]) if os.environ.get("REHEAT") else None
if REHEAT:
    import numpy as np
    from scipy.ndimage import gaussian_filter
    sc.cycles.transparent_max_bounces = 64
    def _mix(a_, b_, t_): return a_ + (b_ - a_) * np.clip(t_, 0, 1)[..., None]
    _ss = lambda e0, e1, x: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0, 1))
    orange, yellow, red, violet = (np.array(c_) for c_ in ((1.0, 0.42, 0.10), (1.0, 0.84, 0.52), (0.92, 0.22, 0.07), (0.60, 0.42, 1.0)))
    QH, INS = 1.30, 0.11
    VE = INS / (1 + INS)
    def _half(s_): return (1.0 + (0.42 - 1.0) * s_ ** 0.75) + 0.07 * np.sin(np.clip(s_ / 0.10, 0, 1) * np.pi)
    W_, H_ = 256, 1024
    v_ = ((np.arange(H_) + 0.5) / H_)[:, None]; q_ = np.abs((np.arange(W_) + 0.5) / W_ * 2 - 1)[None, :]
    s_ = np.clip((v_ - VE) / (1 - VE), 0, 1); outside = _ss(VE - 0.012, VE + 0.02, v_)
    along = (1 - s_) ** 2.0 * _ss(0, 1, v_ / (VE * 0.35))
    f_ = (s_ / 0.058 + 0.5) % 1.0; amp = np.exp(-5.0 * s_); cw = 0.16 + 0.34 * np.sin(np.pi * f_); node = 1 + 0.25 * amp * np.cos(2 * np.pi * f_)
    rho = q_ * QH / _half(s_)
    body = np.maximum((1 - 0.5 * np.minimum(rho * rho, 2)) / (1 + np.exp(np.clip((rho - 0.93) / 0.045, -50, 50))), 0)
    core0 = np.exp(-(rho / 0.42) ** 2); core = core0 + (np.exp(-(rho / cw) ** 2.2) - core0) * amp
    iOut = along * body * (0.45 + 0.80 * core) * node; iIn = along * body * (0.90 + 0.50 * core0)
    rng = np.random.default_rng(3)
    n1 = gaussian_filter(rng.random((H_, W_)), (45, 7)); n2 = gaussian_filter(rng.random((H_, W_)), (20, 2.5))
    nz_ = 0.6 * (n1 - n1.min()) / np.ptp(n1) + 0.4 * (n2 - n2.min()) / np.ptp(n2)
    turb = 0.82 + 0.36 * nz_
    inten = (iIn + (iOut - iIn) * outside) * (turb + (1 - turb) * core * 0.6)
    c_ = _mix(orange, yellow, (core0 + (core - core0) * outside) * 1.1); c_ = _mix(c_, red, s_ * 0.9 + 0 * rho)
    c_ = _mix(c_, violet, np.clip((rho - 0.62) / 0.38, 0, 1) * np.clip(1 - s_ * 4, 0, 1) * 0.45)
    plume_px = np.concatenate([c_, np.clip(inten, 0, 1)[..., None]], 2)
    G_ = 256
    d_ = (np.arange(G_) + 0.5) / G_ * 2 - 1; dx_, dy_ = np.meshgrid(d_, d_); rr_ = np.hypot(dx_, dy_)
    g_ = np.clip(1 - rr_ * rr_, 0, 1) ** 1.3
    glow_px = np.concatenate([_mix(orange, np.array((1.0, 0.90, 0.70)), g_ ** 1.5), g_[..., None]], 2)
    ft = 1 / (1 + np.exp((rr_ - 0.80) / 0.07)); spokes = 0.5 + 0.5 * np.cos(np.arctan2(dy_, dx_) * 15)
    band = np.clip((rr_ - 0.25) * 4, 0, 1) * np.clip((0.80 - rr_) * 6, 0, 1); ring = np.exp(-((rr_ - 0.62) / 0.05) ** 2)
    hot = np.clip(1 - rr_ * rr_, 0, 1) ** 0.8
    core_px = np.concatenate([_mix(np.array((1.0, 0.50, 0.15)), np.array((1.0, 0.95, 0.80)), hot ** 1.2), (ft * (1 - 0.12 * spokes * band - 0.10 * ring))[..., None]], 2)
    def _img(name, px):
        im = bpy.data.images.new(name, px.shape[1], px.shape[0], alpha=True); im.pixels = px.astype(np.float32).ravel(); im.alpha_mode = 'STRAIGHT'; return im
    _imgs = {"plume": _img("plume", plume_px), "glow": _img("glow", glow_px), "core": _img("core", core_px)}
    PREM = all(os.path.exists(os.path.join(TEXDIR, "reheat_%s.png" % k_)) for k_ in ("plume", "core", "glow", "liner"))
    if PREM:
        for k_ in ("plume", "core", "glow", "liner"):
            im_ = bpy.data.images.load(os.path.join(os.path.abspath(TEXDIR), "reheat_%s.png" % k_))
            im_.alpha_mode = 'CHANNEL_PACKED'
            _imgs[k_] = im_
    def _addmat(name, img, strength, opacity=1.0):
        m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
        for n_ in list(nt.nodes):
            if n_.type != 'OUTPUT_MATERIAL': nt.nodes.remove(n_)
        outn = [n_ for n_ in nt.nodes if n_.type == 'OUTPUT_MATERIAL'][0]
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img; t.extension = 'EXTEND'
        em = nt.nodes.new("ShaderNodeEmission")
        tr = nt.nodes.new("ShaderNodeBsdfTransparent"); add = nt.nodes.new("ShaderNodeAddShader")
        if PREM:
            em.inputs["Strength"].default_value = strength
            nt.links.new(t.outputs["Color"], em.inputs["Color"])
            blk = nt.nodes.new("ShaderNodeEmission"); blk.inputs["Strength"].default_value = 0.0
            mul = nt.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = opacity
            nt.links.new(t.outputs["Alpha"], mul.inputs[0])
            mx = nt.nodes.new("ShaderNodeMixShader"); nt.links.new(mul.outputs[0], mx.inputs[0]); nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(blk.outputs[0], mx.inputs[2])
            nt.links.new(mx.outputs[0], add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1]); nt.links.new(add.outputs[0], outn.inputs["Surface"])
            return m
        mul = nt.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = strength
        nt.links.new(t.outputs["Alpha"], mul.inputs[0]); nt.links.new(t.outputs["Color"], em.inputs["Color"]); nt.links.new(mul.outputs[0], em.inputs["Strength"])
        nt.links.new(tr.outputs[0], add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1]); nt.links.new(add.outputs[0], outn.inputs["Surface"])
        return m
    def _mesh(name, verts, uvs, quads, mat):
        me = bpy.data.meshes.new(name); me.from_pydata([u2b(v) for v in verts], [], quads); uvl = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li, vi in zip(poly.loop_indices, poly.vertices): uvl.data[li].uv = uvs[vi]
        o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); o.data.materials.append(mat); o.visible_shadow = False
    def reheat_build(cam):
        for o in [o for o in bpy.data.objects if o.name.startswith("rh_")]: bpy.data.objects.remove(o)
        K_ = REHEAT; GAIN = float(os.environ.get("REHEAT_GAIN", "1.6"))
        LEN = 5.0 * (0.5 + 0.5 * K_); ES = 1.0 + 0.18 * K_
        for sx in (1, -1):
            E = np.array([sx * 0.4855, -0.0392, -4.17]); R0 = 0.331 * ES * 0.94
            d = np.array(cam, float) - (E + np.array([0, 0, -0.35 * LEN])); side = math.hypot(d[0], d[1]); dist = np.linalg.norm(d)
            sinT, cosAft = side / dist, -d[2] / dist
            nrm_ = np.array([d[0], d[1], 0.0]) / max(side, 1e-6); wdir = np.cross([0, 0, 1.0], nrm_)
            wS = min(max(1 / max(sinT, 0.4), 1), 1.8) * float(_ss(0, 1, (sinT - 0.03) / 0.11)); wD = float(_ss(0, 1, (cosAft - 0.80) / 0.175))
            vs, uv, q = [], [], []
            for i in range(17):
                v = i / 16; z = E[2] + LEN * INS - v * LEN * (1 + INS)
                vs.append(tuple(E + wdir * (-R0 * QH) + [0, 0, z - E[2]])); uv.append((0, v)); vs.append(tuple(E + wdir * (R0 * QH) + [0, 0, z - E[2]])); uv.append((1, v))
            for i in range(16): q.append((i * 2, i * 2 + 2, i * 2 + 3, i * 2 + 1))
            _mesh("rh_plume%d" % sx, vs, uv, q, _addmat("rh_pm%d" % sx, _imgs["plume"], (2.5 if PREM else 1.6) * K_ * wS * GAIN, min(1.0, K_ * min(wS, 1.3))))
            if wD > 0.01:
                vs, uv, q = [], [], []
                for s2 in (-0.03, 0.0, 0.03, 0.07, 0.12, 0.18, 0.26, 0.36, 0.48):
                    w = float(_half(np.array(max(s2, 0.0)))) * (1.04 - 0.3 * max(s2, 0)) * R0; b_ = len(vs)
                    for (ax_, ay_, u_, v2_) in ((-1, -1, 0, 0), (1, -1, 1, 0), (1, 1, 1, 1), (-1, 1, 0, 1)):
                        vs.append((E[0] + ax_ * w, E[1] + ay_ * w, E[2] - s2 * LEN)); uv.append((u_, v2_))
                    q.append((b_, b_ + 1, b_ + 2, b_ + 3))
                _mesh("rh_discs%d" % sx, vs, uv, q, _addmat("rh_dm%d" % sx, _imgs["glow"], (0.55 if PREM else 0.40) * K_ * wD * GAIN, K_ * wD))
            w = 0.331 * (1 + (ES - 1) * 0.55)
            _mesh("rh_core%d" % sx, [(E[0] - w, E[1] - w, E[2] + 0.36), (E[0] + w, E[1] - w, E[2] + 0.36), (E[0] + w, E[1] + w, E[2] + 0.36), (E[0] - w, E[1] + w, E[2] + 0.36)], [(0, 0), (1, 0), (1, 1), (0, 1)], [(0, 1, 2, 3)], _addmat("rh_cm%d" % sx, _imgs["core"], (4.2 if PREM else 3.0) * math.sqrt(K_) * GAIN, min(1.0, K_ * 1.2)))
            if PREM:
                vs, uv, q = [], [], []
                NS_, NR_ = 40, 6
                for i in range(NR_ + 1):
                    v2 = i / NR_; z = 0.36 * (1 + (0.02 - 1) * v2); rr2 = R0 * (0.84 + (0.97 - 0.84) * v2)
                    for k in range(NS_ + 1):
                        a2 = 2 * math.pi * k / NS_; vs.append((E[0] + rr2 * math.cos(a2), E[1] + rr2 * math.sin(a2), E[2] + z)); uv.append((k / NS_, v2))
                for i in range(NR_):
                    for k in range(NS_):
                        a0 = i * (NS_ + 1) + k; q.append((a0, a0 + NS_ + 1, a0 + NS_ + 2, a0 + 1))
                _mesh("rh_liner%d" % sx, vs, uv, q, _addmat("rh_lm%d" % sx, _imgs["liner"], 3.2 * K_ * GAIN, K_))
            bpy.ops.object.light_add(type='POINT', location=u2b((E[0], E[1], E[2] + 0.12))); bpy.context.object.name = "rh_lamp%d" % sx
            L_ = bpy.context.object.data; L_.color = (1.0, 0.52, 0.22); L_.energy = 300 * K_; L_.shadow_soft_size = 0.05

world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.8, 0.88, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = float(os.environ.get("SKY", "0.9"))
bpy.ops.object.light_add(type='SUN', rotation=(math.radians(50), math.radians(-20), math.radians(30))); bpy.context.object.data.energy = 3.5 * float(os.environ.get("SUN", "1"))
bpy.ops.object.light_add(type='SUN', rotation=(math.radians(150), 0, math.radians(-40))); bpy.context.object.data.energy = 1.2

def shot(name, loc, target, lens=35):
    cam = bpy.data.cameras.new(name)
    if isinstance(lens, str) and lens.startswith("o"):
        cam.type = 'ORTHO'; cam.ortho_scale = float(lens[1:])
    else:
        cam.lens = float(lens)
    co = bpy.data.objects.new(name, cam); sc.collection.objects.link(co)
    co.location = u2b(loc)
    if REHEAT: reheat_build(loc)
    d = u2b(target) - co.location
    co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    sc.camera = co
    if os.environ.get("PICK"):
        bpy.context.view_layer.update()
        fr = [co.matrix_world @ v for v in cam.view_frame(scene=sc)]
        dg = bpy.context.evaluated_depsgraph_get()
        for pp in os.environ["PICK"].split(";"):
            px, py = [float(v) for v in pp.split(",")]
            u, v = px / sc.render.resolution_x, py / sc.render.resolution_y
            top = fr[3] + (fr[0] - fr[3]) * u
            bot = fr[2] + (fr[1] - fr[2]) * u
            tgt = top + (bot - top) * v
            d = (tgt - co.location).normalized()
            hit, loc_, nrm_, idx_, ob_, _m = sc.ray_cast(dg, co.location, d)
            print("PICK", name, px, py, ob_.name if hit else None, tuple(round(c, 3) for c in (loc_.x, loc_.z, loc_.y)) if hit else "")
    sc.render.filepath = f"{OUTP}_{name}.png"
    bpy.ops.render.render(write_still=True)

views = os.environ.get("VIEWS", "front,side,below").split(",")
if os.environ.get("RES"): sc.render.resolution_x, sc.render.resolution_y = [int(v) for v in os.environ["RES"].split(",")]
if os.environ.get("SAMPLES"): sc.cycles.samples = int(os.environ["SAMPLES"])
for _s in [x for x in os.environ.get("SHOTS", "").split(";") if x]:
    _n, _l, _t, _f = _s.split(":")
    shot(_n, [float(v) for v in _l.split(",")], [float(v) for v in _t.split(",")], _f)
if "stbd" in views: shot("stbd", (24.0, 0.8, 2.6), (0.0, 0.45, 2.6), 55)
if "port" in views: shot("port", (-24.0, 0.8, 2.6), (0.0, 0.45, 2.6), 55)
if "top" in views: shot("top", (0.0, 30.0, 2.7), (0.0, 0.0, 2.75), 60)
if "under" in views: shot("under", (0.0, -30.0, 2.7), (0.0, 0.0, 2.75), 60)
if "q34" in views: shot("q34", (11.0, 6.5, 15.0), (0.3, 0.2, 2.2), 50)
if "closefwd" in views: shot("closefwd", (5.2, 1.3, 6.6), (0.5, 0.25, 4.7), 45)
if "wingtop" in views: shot("wingtop", (-4.6, 4.2, -4.8), (-3.0, -0.4, 0.2), 40)
if "tail" in views: shot("tail", (9.0, 2.6, -3.2), (0.0, 1.7, -3.2), 40)
if "tailp" in views: shot("tailp", (-9.0, 2.6, -3.2), (0.0, 1.7, -3.2), 40)
if "front" in views: shot("front", (-6.5, -2.2, 7.5), (-3.0, -0.6, 0.3), 40)
if "side" in views: shot("side", (-9.5, -1.4, 0.3), (-2.8, -0.65, 0.2), 32)
if "below" in views: shot("below", (-2.6, -5.0, 2.0), (-1.6, -0.6, 0.2), 30)
if "rear" in views: shot("rear", (-5.5, -1.6, -7.5), (-2.8, -0.6, 0.2), 38)
if "belly" in views: shot("belly", (2.5, -3.2, 5.5), (0.0, -0.8, 0.3), 32)
if "close" in views: shot("close", (-5.2, -1.5, 4.2), (-3.2, -0.6, 0.3), 45)
if "closeside" in views: shot("closeside", (-5.8, -1.0, 0.4), (-3.2, -0.6, 0.2), 40)
if "inboard" in views: shot("inboard", (-1.5, -1.25, 0.9), (-3.4, -0.55, 0.0), 24)

if "gearfront" in views: shot("gearfront", (0.0, -1.2, 9.5), (0.0, -1.2, 2.0), 35)
if "gearside" in views: shot("gearside", (-7.5, -1.3, 3.0), (0.0, -1.2, 3.0), 35)
if "gear34" in views: shot("gear34", (-4.2, -2.6, 5.2), (-0.8, -1.0, 1.8), 30)
if "bay" in views: shot("bay", (-2.2, -3.4, 1.6), (0.0, -0.5, -0.8), 32)
if "baylow" in views: shot("baylow", (0.0, -3.6, 2.2), (0.0, -0.4, -0.9), 28)
