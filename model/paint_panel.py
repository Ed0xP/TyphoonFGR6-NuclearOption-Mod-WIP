import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ckpanel
import ckpaint as cp

dump, cockpit_txt, out = sys.argv[1], sys.argv[2], sys.argv[3]
layout = sys.argv[4] if len(sys.argv) > 4 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "cockpit_panel.txt")
d = np.load(dump)
atlas = ckpanel.Atlas(d["atlas_P"], d["atlas_UV"])
items = ckpanel.resolve(ckpanel.parse(layout), atlas)
cover = d["cover"]
R = cover.shape[0]
ckpanel.DECALS = os.environ.get("NO_DECALS") is None
ckpanel.KEY_SRC = "labels_panel.json"
base, emit, height, smooth = ckpanel.paint(d["pos"], cover, d["old"].astype(np.float32), d["ao"].astype(np.float32), float(d["dens"]),
                                           items, ckpanel.read_screens(cockpit_txt), d["nrm"] if "nrm" in d else None)
del d
base = cp.dilate(base, cover); emit = cp.dilate(emit, cover); height = cp.dilate(height, cover); smooth = cp.dilate(smooth, cover)
nx, ny, nz = cp.normal_from_height(height, strength=3.0)
cp.save(base, os.path.join(out, "ckpanel_base.png"), "RGB")
cp.save(emit, os.path.join(out, "ckpanel_emit.png"), "RGB")
cp.save(cp.pack_normal(nx, ny), os.path.join(out, "ckpanel_normal.png"), "RGBA")
m = np.zeros((R, R, 4), np.float32)
m[..., 3] = smooth
cp.save(m, os.path.join(out, "ckpanel_mask.png"), "RGBA")
print("panel textures written")

import json
json.dump([dict(l, font="MONO" if l["font"] == ckpanel.MONO else "FONT") for l in ckpanel.LABELS], open(os.path.join(sys.argv[3], "labels_panel.json"), "w"))
print("panel:", len(ckpanel.LABELS), "labels for make_labels.py")
