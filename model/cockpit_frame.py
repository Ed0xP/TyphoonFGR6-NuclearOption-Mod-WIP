import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ckpaint as cp
import ckskin

ST = sys.argv[1]
R = int(os.environ.get("FRAME_RES", "4096"))
PART = os.environ.get("SHELL_PART", "frame")
TUB = PART == "tub"
PARTS = {"frame": ("ckframe", "cockpit_shellframe"), "deck": ("ckfdeck", "cockpit_shelldeck"), "aft": ("ckfaft", "cockpit_shellaft"),
         "tub": ("cktub", "cockpit_shelltub"), "rest": ("ckrest", "cockpit_shellrest")}
REST = PART == "rest"
NAME, GROUP = PARTS[PART]
Z_AFT, Z_DECK = 6.20, 7.40
lines = open(os.path.join(ST, "typhoon.obj")).read().split("\n")
V, VT, VN = [], [], []
faces = []
moved = []
occl = []
cur = None
for li, l in enumerate(lines):
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vt "):
        VT.append([float(x) for x in l.split()[1:3]])
    elif l.startswith("vn "):
        VN.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ("o ", "g "):
        cur = l.split()[1]
        assert cur != GROUP, "cockpit_frame.py has already run on this OBJ for this part"
    elif l.startswith("f ") and cur is not None and (cur == "canopy_interior" or cur.startswith("cockpit_")):
        f_ = [tuple(int(a) if a else 0 for a in (c.split("/") + ["", ""])[:3]) for c in l.split()[1:]]
        if cur == "canopy_interior":
            faces.append((li, f_))
        elif cur.startswith("cockpit_shell") and cur != "cockpit_shelltub":
            moved.append(f_)
        if cur not in ("cockpit_labels", "cockpit_hudglass"):
            for j_ in range(1, len(f_) - 1):
                occl.append((f_[0][0] - 1, f_[j_][0] - 1, f_[j_ + 1][0] - 1))
V, VT, VN = np.array(V), np.array(VT), np.array(VN)

key, par = {}, {}


def kid(i):
    return key.setdefault(tuple(np.round(V[i - 1], 4)), len(key))


def find(a):
    while par.setdefault(a, a) != a:
        par[a] = par[par[a]]
        a = par[a]
    return a


for li, f in faces:
    ks = [kid(c[0]) for c in f]
    for a in ks[1:]:
        par[find(a)] = find(ks[0])
comp = {}
for fi, (li, f) in enumerate(faces):
    comp.setdefault(find(kid(f[0][0])), []).append(fi)
old = np.asarray(Image.open(os.path.join(ST, "cockpit_base.png")).convert("RGB")).astype(np.float32) / 255
OH, OW = old.shape[:2]
old_l = old.mean(2)
sel, kinds = [], []
others = []
deck = set()
for c, fs in comp.items():
    P_ = V[[c_[0] - 1 for fi in fs for c_ in faces[fi][1]]]
    lo, hi = P_.min(0), P_.max(0)
    if len(fs) < 100 and hi[2] > 8.4 and lo[1] > 0.6 and hi[1] < 1.05:
        deck.update(fs)
for fi, (li, f) in enumerate(faces):
    if any(c_[1] == 0 for c_ in f):
        continue
    cen = V[[c_[0] - 1 for c_ in f]].mean(0)
    if REST:
        sel.append(fi)
        kinds.append(1)
        continue
    if TUB:
        if not (cen[1] < 0.66 and 5.85 < cen[2] < 7.75 and abs(cen[0]) < 0.56):
            continue
    elif cen[1] < 0.66:
        continue
    elif abs(cen[0]) < 0.40 and cen[1] < 1.10 and 7.14 < cen[2] < 7.70 and fi not in deck:
        continue
    uvc = VT[[c_[1] - 1 for c_ in f]].mean(0)
    px = old[min(max(int((1 - uvc[1]) * OH), 0), OH - 1), min(max(int(uvc[0] * OW), 0), OW - 1)]
    if px.mean() > 0.34 or px.max() - px.min() > 0.08:
        continue
    if not TUB:
        part = "deck" if (fi in deck or cen[2] >= Z_DECK) else "aft" if cen[2] < Z_AFT else "frame"
        if part != PART:
            others.append(f)
            continue
    sel.append(fi)
    kinds.append(2 if fi in deck else 1)
print("frame: %d of %d shell faces move to their own atlas (%d frame, %d deck)" % (len(sel), len(faces), kinds.count(1), kinds.count(2)))

import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
polys = [[c_[0] - 1 for c_ in faces[fi][1]] for fi in sel]
used = sorted({v for p in polys for v in p})
rm = {v: i for i, v in enumerate(used)}
ok = [len(set(p)) == len(p) and len(p) >= 3 for p in polys]
me = bpy.data.meshes.new("u")
me.from_pydata([tuple(V[v]) for v in used], [], [[rm[v] for v in p] for p, k in zip(polys, ok) if k])
me.update()
ob = bpy.data.objects.new("u", me)
bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
me.uv_layers.new(name="UVMap")
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0)
bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.average_islands_scale()
bpy.ops.uv.pack_islands(margin=0.003, rotate=True)
bpy.ops.object.mode_set(mode='OBJECT')
uvl = np.array([l.uv[:] for l in me.uv_layers.active.data], np.float64)
new_uv, k0 = [], 0
for p, good in zip(polys, ok):
    if good:
        new_uv.append(uvl[k0:k0 + len(p)])
        k0 += len(p)
    else:
        new_uv.append(np.zeros((len(p), 2)))

P, UVn, A = [], [], []
tri_of = []
for q, (fi, k) in enumerate(zip(sel, kinds)):
    f = faces[fi][1]
    for j in range(1, len(f) - 1):
        tri = (0, j, j + 1)
        p = np.array([V[f[a][0] - 1] for a in tri])
        n = np.cross(p[1] - p[0], p[2] - p[0])
        n /= max(np.linalg.norm(n), 1e-12)
        if f[0][2] and len(VN) >= f[0][2] and n @ VN[f[0][2] - 1] < 0:
            n = -n
        P.append(p)
        UVn.append([new_uv[q][a] for a in tri])
        A.append([[n[0], n[1], n[2], k, VT[f[a][1] - 1][0], VT[f[a][1] - 1][1]] for a in tri])
P, UVn, A = np.array(P), np.array(UVn), np.array(A)
tid, pos, att = ckskin.raster_attr(UVn, P, A, R, R)
cover = tid >= 0
area = np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1).sum() / 2
dens = math.sqrt(cover.sum() / max(area, 1e-9))
print(PART + ": %.2f m2, %d %% of %d px used, %d texels per metre" % (area, 100 * cover.mean(), R, dens))
Z = pos[..., 2]
NYa = np.abs(att[..., 1])
knd = np.round(att[..., 3])
mx = (att[..., 4] * OW - 0.5).astype(np.float32)
my = ((1 - att[..., 5]) * OH - 0.5).astype(np.float32)
ol = cv2.remap(cv2.GaussianBlur(old_l, (0, 0), 0.8), mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
olb = cv2.remap(cv2.GaussianBlur(old_l, (0, 0), 10), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
detail = np.clip((ol + 0.03) / (olb + 0.03), 0.55, 1.04) ** 0.6
detail = cv2.GaussianBlur(detail, (0, 0), 1.5)
detail = 1 + (detail - 1) * float(os.environ.get("FRAME_DETAIL", "0.4" if TUB else "0"))

LONG_EDGE, LONG_WEAR = float(os.environ.get("FRAME_LONG_EDGE", "0.07")), float(os.environ.get("FRAME_LONG_WEAR", "0.35"))
edges = {}
elen = {}
fnorm = []
farea = []


def _fn(f):
    p = V[[c_[0] - 1 for c_ in f]]
    n = np.zeros(3)
    for a in range(len(p)):
        n += np.cross(p[a], p[(a + 1) % len(p)])
    ar = float(np.linalg.norm(n)) / 2
    n = n / max(np.linalg.norm(n), 1e-12)
    if f[0][2] and len(VN) >= f[0][2] and n @ VN[f[0][2] - 1] < 0:
        n = -n
    return n, ar


for q, fi in enumerate(sel):
    f = faces[fi][1]
    p = V[[c_[0] - 1 for c_ in f]]
    n, ar = _fn(f)
    fnorm.append(n)
    farea.append(ar)
    for a in range(len(f)):
        b = (a + 1) % len(f)
        e = tuple(sorted((kid(f[a][0]), kid(f[b][0]))))
        edges.setdefault(e, []).append((q, a, b))
        elen[e] = float(np.linalg.norm(p[a] - p[b]))
nb_n = []
vfaces = {}
for q, fi in enumerate(sel):
    for c_ in faces[fi][1]:
        vfaces.setdefault(kid(c_[0]), []).append((fnorm[q], farea[q]))
if not TUB:
    for f in others + moved:
        n, ar = _fn(f)
        nb_n.append(n)
        for a in range(len(f)):
            b = (a + 1) % len(f)
            e = tuple(sorted((kid(f[a][0]), kid(f[b][0]))))
            if e in edges:
                edges[e].append((-len(nb_n), a, b))
            vfaces.setdefault(kid(f[a][0]), []).append((n, ar))


def _n_of(q):
    return fnorm[q] if q >= 0 else nb_n[-q - 1]
emask = np.zeros((R, R), np.uint8)
lmask = np.zeros((R, R), np.uint8)
wd = max(int(round(dens * 0.0022)), 2)
n_sharp = 0
for e, us in edges.items():
    sharp = len(us) == 1 or any(_n_of(us[0][0]) @ _n_of(u[0]) < math.cos(math.radians(30)) for u in us[1:])
    if not sharp:
        continue
    n_sharp += 1
    for q, a, b in us:
        if q < 0:
            continue
        pa, pb = new_uv[q][a], new_uv[q][b]
        cv2.line(emask, (int(pa[0] * R * 16), int((1 - pa[1]) * R * 16)), (int(pb[0] * R * 16), int((1 - pb[1]) * R * 16)), 255, wd, cv2.LINE_AA, 4)
        if elen[e] >= LONG_EDGE:
            cv2.line(lmask, (int(pa[0] * R * 16), int((1 - pa[1]) * R * 16)), (int(pb[0] * R * 16), int((1 - pb[1]) * R * 16)), 255, wd, cv2.LINE_AA, 4)
edge = cv2.GaussianBlur(emask.astype(np.float32) / 255, (0, 0), max(dens * 0.0016, 1.0))
edge = np.clip(edge * 1.5, 0, 1)
wide = np.clip(cv2.GaussianBlur(emask.astype(np.float32) / 255, (0, 0), max(dens * 0.012, 2.0)) * 2.5, 0, 1)
crowd = cv2.GaussianBlur(emask.astype(np.float32) / 255, (0, 0), dens * 0.022)
calm = np.clip(1 - (crowd - 0.065) / 0.08, 0.0, 1)
edge *= calm
wide *= calm
long_ = np.clip(cv2.GaussianBlur(lmask.astype(np.float32) / 255, (0, 0), max(dens * 0.0016, 1.0)) * 1.5, 0, 1)
edge = np.maximum(edge, long_ * np.clip(1 - (crowd - 0.17) / 0.12, 0.0, 1) * LONG_WEAR)
print("frame: long edges cover %.2f %% of the atlas" % (100 * float((lmask > 0).mean())))
print("frame: %d sharp edges of %d; %d %% of the edge wear kept after thinning crowded places" % (n_sharp, len(edges), 100 * float(calm[emask > 0].mean())))


def noise(sig, seed):
    r = np.random.default_rng(seed).standard_normal((R // 2, R // 2)).astype(np.float32)
    r = cv2.GaussianBlur(r, (0, 0), max(sig / 2, 0.5))
    r = cv2.resize(r, (R, R), interpolation=cv2.INTER_LINEAR)
    return (r - r.mean()) / max(float(r.std()), 1e-6)


_tiles = {}


def n3(size_m, seed):
    if seed not in _tiles:
        t = np.random.default_rng(100 + seed).standard_normal((1024, 1024)).astype(np.float32)
        t = cv2.GaussianBlur(np.tile(t, (3, 3)), (0, 0), 6)[1024:2048, 1024:2048]
        _tiles[seed] = t / max(float(t.std()), 1e-6)
    k = 12.0 / size_m
    u = ((pos[..., 0] + 0.37 * pos[..., 1]) * k) % 1024
    v = ((pos[..., 2] + 0.61 * pos[..., 1]) * k) % 1024
    return cv2.remap(_tiles[seed], u.astype(np.float32), v.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


SILL, ARCH, DECK = (0.345, 0.355, 0.350), (0.330, 0.340, 0.335), (0.215, 0.222, 0.220)
if TUB:
    SILL = ARCH = (0.235, 0.242, 0.246)
arch = np.clip((Z - 6.98) / 0.06, 0, 1) * (knd == 1)
detail = np.where(arch > 0.5, np.clip(detail, 0.93, 1.05), detail)
edge = edge * (1 - 0.85 * arch)
col = np.empty((R, R, 3), np.float32)
for c in range(3):
    col[..., c] = np.where(knd == 2, DECK[c], SILL[c] + (ARCH[c] - SILL[c]) * arch)
col *= (detail * (1 + 0.035 * n3(0.25, 1) + 0.010 * noise(1.5, 2)))[..., None]
chip_n = 0.6 * noise(2.5, 3) + 0.4 * n3(0.012, 4)
chips = edge * np.clip((chip_n - 0.15) * 1.6, 0, 1)
chips = np.maximum(chips, wide * np.clip((0.7 * noise(1.4, 12) + 0.3 * noise(4, 13) - 2.35) * 3.0, 0, 1))
up = np.full((R, R), 0.7, np.float32)
rub = np.clip((n3(0.18, 5) - 0.10) * 1.2, 0, 1) * np.clip(0.80 + 0.20 * noise(2.0, 6), 0, 1) * (0.25 + 0.75 * up) * (knd == 1)
rub = rub * (1 - 0.8 * arch)
st = np.random.default_rng(7).standard_normal((R, R)).astype(np.float32)
st = cv2.GaussianBlur(st, (0, 0), sigmaX=5, sigmaY=0.7) + cv2.GaussianBlur(st.T.copy(), (0, 0), sigmaX=5, sigmaY=0.7)
scratch = np.clip((st / max(float(st.std()), 1e-6) - 2.5) * 1.6, 0, 1) * (0.35 + 0.65 * up)
dust = up * np.clip(0.7 + 0.3 * n3(0.22, 8), 0, 1)
BARE, RUB = np.array([0.62, 0.63, 0.61], np.float32), np.array([0.46, 0.47, 0.455], np.float32)
col += (RUB - col) * (float(os.environ.get("FRAME_RUB", "0.20")) * rub)[..., None]


def part_shadows():
    ps = pos[::4, ::4].reshape(-1, 3).astype(np.float32)
    sh = np.zeros(len(ps), np.float32)

    def wp(sx, t, h):
        return np.array([sx * (0.3833 - 0.0056 * t), 0.757 - 0.048 * t + 0.129 * h, 6.545 + 0.41 * t], np.float32)
    segs = []
    for sx in (1, -1):
        m = np.array([sx, 1, 1], np.float32)
        segs.append((np.array([0.4010, 0.8910, 6.535]) * m, np.array([0.3975, 0.8400, 6.975]) * m, 0.030, 0.024, 0.30))
        segs.append((wp(sx, 0, 0.6), wp(sx, 1, 0.6), 0.007, 0.014, 0.28))
        segs.append((wp(sx, 0, 0.0), wp(sx, 1, 0.0), 0.009, 0.016, 0.28))
        for t in (0.10, 0.365, 0.63, 0.895):
            segs.append((wp(sx, t, 0.145), wp(sx, t, 0.905), 0.005, 0.011, 0.22))
        cab = [(0.352, 0.900, 6.972), (0.358, 0.872, 6.948), (0.3705, 0.822, 6.915), (0.3715, 0.790, 6.840), (0.3725, 0.776, 6.700), (0.3735, 0.778, 6.575)]
        for a, b in zip(cab[:-1], cab[1:]):
            segs.append((np.array(a) * m, np.array(b) * m, 0.0055, 0.012, 0.22))
        f = np.array([0.372, 0.872, 6.975]) * m
        segs.append((f, f, 0.026, 0.024, 0.30))
        segs.append((wp(sx, 0.5, 0.13), wp(sx, 0.5, 0.13), 0.022, 0.020, 0.25))
    for a, b, r0, fall, k in segs:
        a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
        ab = b - a
        l2 = float(ab @ ab)
        t = np.clip(((ps - a) @ ab) / l2, 0, 1) if l2 > 1e-12 else np.zeros(len(ps), np.float32)
        d = np.linalg.norm(ps - (a + t[:, None] * ab), axis=1)
        sh = np.maximum(sh, k * np.clip(1 - (d - r0) / fall, 0, 1) ** 1.5)
    return cv2.resize(sh.reshape(pos[::4, ::4].shape[:2]), (R, R), interpolation=cv2.INTER_LINEAR)


if PART == "frame":
    col *= (1 - part_shadows())[..., None]


def ambient():
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons([Vector(v) for v in V], occl)
    K = int(os.environ.get("FRAME_AO_RAYS", "32"))
    FAR = 0.30
    S = 4
    ps, ns, cv_ = pos[S // 2::S, S // 2::S], att[S // 2::S, S // 2::S, :3], cover[S // 2::S, S // 2::S]
    ao = np.ones(cv_.shape, np.float32)
    rng = np.random.default_rng(5)
    u1, u2 = rng.random(K), rng.random(K)
    rr, ph = np.sqrt(u1), 2 * np.pi * u2
    loc = np.stack([rr * np.cos(ph), rr * np.sin(ph), np.sqrt(1 - u1)], 1)
    ii, jj = np.nonzero(cv_)
    for i, j in zip(ii, jj):
        n = ns[i, j].astype(np.float64)
        ln = np.linalg.norm(n)
        if ln < 1e-6:
            continue
        n /= ln
        t1 = np.cross(n, (0.0, 1.0, 0.0) if abs(n[1]) < 0.9 else (1.0, 0.0, 0.0))
        t1 /= np.linalg.norm(t1)
        t2 = np.cross(n, t1)
        o = Vector(ps[i, j].astype(np.float64) + n * 0.0012)
        a = (i * 7 + j * 13) % K
        open_ = 0.0
        for k in range(K):
            l = loc[(k + a) % K]
            d = t1 * l[0] + t2 * l[1] + n * l[2]
            h = bvh.ray_cast(o, Vector(d), FAR)
            open_ += 1.0 if h[0] is None else min(h[3] / FAR, 1.0) ** 1.5
        ao[i, j] = open_ / K
    w = cv_.astype(np.float32)
    num = cv2.GaussianBlur(ao * w, (0, 0), 2.2)
    den = cv2.GaussianBlur(w, (0, 0), 2.2)
    ao = np.where(w > 0, num / np.maximum(den, 1e-6), 0)
    filled_ = w.copy()
    for _ in range(6):
        num = cv2.blur(ao * filled_, (3, 3))
        den = cv2.blur(filled_, (3, 3))
        grow = (filled_ == 0) & (den > 0)
        ao[grow] = (num / np.maximum(den, 1e-6))[grow]
        filled_[grow] = 1
    ao[filled_ == 0] = 1
    return cv2.resize(ao, (R, R), interpolation=cv2.INTER_LINEAR)


AO_K = float(os.environ.get("FRAME_AO", "0.30" if TUB else "0.40"))
if AO_K > 0:
    AO = ambient()
    ref = float(np.percentile(AO[cover], 75))
    shade = (1 - AO_K * (1 - AO)) / (1 - AO_K * (1 - ref))
    shade = np.clip(shade, 0.35, 1.05)
    print("%s: ambient occlusion %.2f mean, %.2f darkest percentile; shade %.2f - %.2f" % (
        PART, float(AO[cover].mean()), float(np.percentile(AO[cover], 1)), float(shade[cover].min()), float(shade[cover].max())))
    col *= shade[..., None]
    grime = np.clip((0.75 - AO) / 0.5, 0, 1)
    col *= (1 - 0.10 * grime * np.clip(0.6 + 0.4 * n3(0.05, 31), 0, 1))[..., None]
else:
    AO = np.ones((R, R), np.float32)
    grime = np.zeros((R, R), np.float32)
col *= (1 - 0.09 * np.clip((n3(0.09, 21) - 0.55) * 1.2, 0, 1))[..., None]
col += (BARE - col) * (0.22 * scratch)[..., None]
col += 0.022 * dust[..., None]
col += (BARE - col) * (0.65 * chips)[..., None]
col *= (1 - 0.10 * np.clip(edge - chips, 0, 1))[..., None]

_fine = cv2.GaussianBlur(np.random.default_rng(91).standard_normal((R, R)).astype(np.float32), (0, 0), 0.6)
_fine /= max(float(_fine.std()), 1e-6)
col *= (1 + 0.030 * _fine + 0.014 * noise(3.0, 92))[..., None]
base8 = (np.clip(col, 0, 1) * 255 + 0.5).astype(np.uint8)
filled = cover.astype(np.uint8)
k3 = np.ones((3, 3), np.uint8)
for _ in range(8):
    d = cv2.dilate(base8, k3)
    grow = cv2.dilate(filled, k3)
    new = (grow > 0) & (filled == 0)
    base8[new] = d[new]
    filled = grow
Image.fromarray(base8, "RGB").save(os.path.join(ST, NAME + "_base.png"))
RN = R // 2
h = cv2.resize(0.06 * noise(1.2, 9) + 0.05 * _fine - 0.7 * chips - 0.4 * scratch, (RN, RN), interpolation=cv2.INTER_AREA)
nx, ny, _ = cp.normal_from_height(h, 0.35)
cp.save(cp.pack_normal(nx, ny), os.path.join(ST, NAME + "_normal.png"), "RGBA")
mk = np.zeros((RN, RN, 4), np.float32)
mk[..., 0] = cv2.resize(np.clip(0.55 * chips + 0.3 * scratch, 0, 1), (RN, RN), interpolation=cv2.INTER_AREA)
mk[..., 3] = cv2.resize(np.clip(0.30 + 0.14 * chips + 0.05 * rub - 0.04 * dust - 0.08 * grime, 0.05, 0.9), (RN, RN), interpolation=cv2.INTER_AREA)
cp.save(mk, os.path.join(ST, NAME + "_mask.png"), "RGBA")

drop = {faces[fi][0] for fi in sel}
out = [l for i, l in enumerate(lines) if i not in drop]
while out and out[-1] == "":
    out.pop()
nvt = len(VT)
nvn = len(VN)
tail = []
flines = []
SMOOTH = math.cos(math.radians(float(os.environ.get("FRAME_SMOOTH", "0" if TUB else "40"))))
for q, fi in enumerate(sel):
    f = faces[fi][1]
    for u_, v_ in new_uv[q]:
        tail.append("vt %.6f %.6f" % (u_, v_))
    if SMOOTH < 0.9999:
        ns_ = []
        for c_ in f:
            m = np.zeros(3)
            for n_, a_ in vfaces.get(kid(c_[0]), ()):
                if n_ @ fnorm[q] > SMOOTH:
                    m += n_ * a_
            m = m / np.linalg.norm(m) if np.linalg.norm(m) > 1e-9 else fnorm[q]
            ns_.append(m)
            tail.append("vn %.5f %.5f %.5f" % tuple(m))
        flines.append("f " + " ".join("%d/%d/%d" % (c_[0], nvt + j + 1, nvn + j + 1) for j, c_ in enumerate(f)))
        nvn += len(f)
    else:
        flines.append("f " + " ".join("%d/%d/%s" % (c_[0], nvt + j + 1, c_[2] if c_[2] else "") for j, c_ in enumerate(f)))
    nvt += len(f)
tail += ["o " + GROUP, "usemtl " + NAME] + flines
open(os.path.join(ST, "typhoon.obj"), "w").write("\n".join(out + tail) + "\n")
mt = os.path.join(ST, "typhoon_materials.txt")
txt = open(mt).read()
if not any(l.startswith(NAME + " ") for l in txt.split("\n")):
    open(mt, "w").write(txt.rstrip("\n") + "\n%s base=%s_base.png normal=%s_normal.png mask=%s_mask.png smooth=1 metal=1\n" % (NAME, NAME, NAME, NAME))
print("frame: %s textures written, OBJ rewritten (group %s, %d faces)" % (NAME, GROUP, len(sel)))
