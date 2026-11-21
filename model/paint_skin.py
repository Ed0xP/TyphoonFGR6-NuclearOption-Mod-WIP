import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ckskin
import ckpaint as cp

dump, out = sys.argv[1], sys.argv[2]
d = np.load(dump)
P_sk, UVN_sk = d["P"], d["UVN"]
_cent = P_sk.mean(1)


def skin_uv_of(p):
    dd = np.linalg.norm(_cent - p, axis=1)
    for t in np.argsort(dd)[:12]:
        f = ckskin.tri_affine(P_sk[t], UVN_sk[t])
        e1, e2 = P_sk[t][1] - P_sk[t][0], P_sk[t][2] - P_sk[t][0]
        n = np.cross(e1, e2)
        b = np.linalg.solve(np.array([e1, e2, n]).T, p - P_sk[t][0])
        if b[0] >= -0.02 and b[1] >= -0.02 and b[0] + b[1] <= 1.02 and abs(b[2]) * np.linalg.norm(n) < 0.01:
            return f
    return None


controls = []
for kind, c in zip(d["ctrl_kind"], d["ctrl"]):
    p, r_, f_, u_, rad = c[0:3], c[3:6], c[6:9], c[9:12], float(c[12])
    fmap = skin_uv_of(p)
    if fmap is not None:
        controls.append((str(kind), p, r_, f_, u_, rad, fmap))
print(f"console skin: {len(controls)} of {len(d['ctrl'])} controls on the skin")
cover = d["cover"]
ckskin.DECALS = os.environ.get("NO_DECALS") is None
pos = d["pos"].astype(np.float32)
old = d["old_rgb"].astype(np.float32)
ao_ = d["ao"].astype(np.float32)
dens_ = float(d["dens"])
R = cover.shape[0]
tid_, nrm_ = d["tid"], d["nrm"]
del d
import console_layout
LAYS = [(L_, sd_) for L_, sd_ in ((console_layout.load("console_right.txt"), 1), (console_layout.load("console_left.txt"), -1))
        if L_ is not None and os.environ.get("SKIN_LAYOUTS")]
for _L, _sd in LAYS:
    if _L.nzmin >= 0.7 and _L.x0 > 0.2:
        ckskin.SKIP_SIDES.add(_sd)
base, height, smooth, emit = ckskin.paint(tid_, pos, nrm_, old, ao_, cover, controls, dens_, R, skin_uv_of)
keep = np.zeros(cover.shape, np.float32)
for _L, _sd in LAYS:
    ckskin.LABELS_OUT.extend(console_layout.paint(_L, pos, nrm_, cover, base, height, smooth, keep, side=_sd))
if LAYS:
    _k = keep > 0
    base[_k] = base[_k] * (0.55 + 0.45 * ao_[_k])[:, None]
    emit[_k] = 0
del tid_, nrm_
import cv2
mx_, mn_ = old.max(2), old.min(2)
yel = cover & (old[..., 0] > 0.42) & (old[..., 1] > 0.30) & (old[..., 2] < 0.6 * old[..., 0]) & (mx_ - mn_ > 0.22)
k_ = max(int(dens_ * 0.005), 5)
ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k_ + 1, 2 * k_ + 1))
reg = cv2.morphologyEx(yel.astype(np.uint8), cv2.MORPH_CLOSE, ker)
reg = cv2.morphologyEx(reg, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
nlab, lab, stats, _ = cv2.connectedComponentsWithStats(reg, 8)
keep_cc = np.zeros(nlab, bool)
keep_cc[1:] = stats[1:, cv2.CC_STAT_AREA] > (dens_ * 0.008) ** 2
reg = keep_cc[lab] & cover
reg &= ~(keep > 0)
for kind, p, r_, f_, u_, rad, fmap in controls:
    if kind in ("drf", "button", "guardbox", "cover"):
        reg &= ~(np.linalg.norm(pos - np.asarray(p, np.float32), axis=2) < rad * 1.4)
ph = (pos[..., 0] + pos[..., 1] + pos[..., 2]) / 0.012
tri_ = np.abs(ph - np.floor(ph) - 0.5) * 2
aa = 0.012 * dens_ * 0.5 / 1.7320508
st_ = np.clip((tri_ - 0.5) * aa + 0.5, 0, 1)[..., None]
haz = st_ * np.array([0.86, 0.66, 0.05], np.float32) + (1 - st_) * np.array([0.045, 0.045, 0.05], np.float32)
soft = cv2.GaussianBlur(reg.astype(np.float32), (0, 0), 1.0)[..., None]
base = base * (1 - soft) + haz * (0.55 + 0.45 * ao_)[..., None] * soft
emit = emit * (1 - soft)
smooth = smooth * (1 - soft[..., 0]) + 0.35 * soft[..., 0]
print(f"hazard markings repainted: {int(reg.sum())} texels in {int(keep_cc.sum())} areas")
del pos, old, ao_, mx_, mn_, yel, lab, ph, tri_, st_, haz, soft
base = cp.dilate(base, cover); height = cp.dilate(height, cover); smooth = cp.dilate(smooth, cover)
nx, ny, nz = cp.normal_from_height(height, strength=3.0)
cp.save(base, os.path.join(out, "ckconsole_base.png"), "RGB")
cp.save(cp.dilate(emit, cover), os.path.join(out, "ckconsole_emit.png"), "RGB")
cp.save(cp.pack_normal(nx, ny), os.path.join(out, "ckconsole_normal.png"), "RGBA")
m = np.zeros((R, R, 4), np.float32)
m[..., 3] = smooth
cp.save(m, os.path.join(out, "ckconsole_mask.png"), "RGBA")
cp.save(cp.dilate(keep, cover), os.path.join(out, "ckconsole_keep.png"), "L")
import json
json.dump(ckskin.LABELS_OUT, open(os.path.join(out, "labels_console.json"), "w"))
print("console skin textures written;", len(ckskin.LABELS_OUT), "labels for make_labels.py")
