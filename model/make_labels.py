import json
import os
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ckpanel

D = sys.argv[1]
labels = []
for f in sys.argv[2:]:
    for l in json.load(open(f)):
        l["src"] = os.path.basename(f)
        labels.append(l)
labels = [l for l in labels if l.get("seen", True) and l["text"].strip()]

from ckkeys import OFF_COL, LIT_COL, key_state

nkey = 0
mdef = None
for l in labels:
    if "lcd" in l and l["text"].startswith("WPT"):
        mdef = l
        continue
    st = key_state(l)
    if st:
        nkey += 1
        l["state"], l["uid"] = st, nkey
        l["col"] = list(LIT_COL)
labels = [l for l in labels if l is not mdef]
PPM = 22000.0
AW = AH = 4096
PAD = 3
fonts = {"FONT": ckpanel.FONT, "MONO": ckpanel.MONO}

cells = {}
order = []
for l in labels:
    fpx = max(int(round(l["cap"] * PPM / 0.729)), 8)
    key = (l["text"], fpx, l["font"], round(l["spacing"], 2), tuple(int(round(c * 255)) for c in l["col"]), l.get("uid", 0))
    l["key"] = key
    if "uid" in l:
        l["offkey"] = key[:4] + (tuple(int(round(c * 255)) for c in OFF_COL), -l["uid"])
    if key in cells:
        continue
    f = ImageFont.truetype(fonts[l["font"]], fpx)
    lines = l["text"].split("|")
    lh = l["cap"] * PPM * l["spacing"]
    w = int(max(max(f.getlength(ln) for ln in lines), 1) + 8)
    h = int(lh * len(lines) + 8)
    im = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        dr.text((w / 2, h / 2 + (i - (len(lines) - 1) / 2) * lh), ln, fill=255, font=f, anchor="mm")
    cells[key] = {"im": im, "w": w, "h": h}
    order.append(key)
    if "uid" in l:
        cells[l["offkey"]] = {"im": im, "w": w, "h": h}
        order.append(l["offkey"])

atlas = np.zeros((AH, AW, 4), np.uint8)
atlas[..., :3] = (226, 228, 220)
x = y = PAD
row = 0
for key in sorted(order, key=lambda k: -cells[k]["h"]):
    c = cells[key]
    if x + c["w"] + PAD > AW:
        x, y, row = PAD, y + row + PAD, 0
    if y + c["h"] + PAD > AH:
        raise SystemExit("label atlas full: lower PPM or raise the atlas size")
    c["x"], c["y"] = x, y
    atlas[max(y - PAD, 0):y + c["h"] + PAD, max(x - PAD, 0):x + c["w"] + PAD, :3] = key[4]
    atlas[y:y + c["h"], x:x + c["w"], 3] = np.asarray(c["im"])
    x += c["w"] + PAD
    row = max(row, c["h"])
Image.fromarray(atlas, "RGBA").save(os.path.join(D, "cklabel.png"), optimize=True)

obj = os.path.join(D, "typhoon.obj")
src = open(obj).read()
cut = src.find("\no cockpit_labels")
if cut >= 0 and os.environ.get("RELABEL"):
    end = src.find("\no ", cut + 3)
    end = len(src) if end < 0 else end + 1
    blk = [ln for ln in src[cut + 1:end].split("\n") if ln[:2] in ("v ", "vt", "vn")]
    src = src[:cut + 1] + "\n".join(blk) + ("\n" if blk else "") + src[end:]
elif cut >= 0:
    src = src[:cut + 1]
_v, _tris, _g = [], [], None
for ln in src.split("\n"):
    if ln.startswith("v "):
        t = ln.split(); _v.append(Vector((float(t[1]), float(t[3]), float(t[2]))))
    elif ln[:2] in ("o ", "g "):
        _g = ln.split()[1]
    elif ln.startswith("f ") and _g and (_g.startswith("cockpit_") or _g == "canopy_interior") and "glass" not in _g:
        ix = [int(x.split("/")[0]) - 1 for x in ln.split()[1:]]
        for i in range(1, len(ix) - 1):
            _tris.append((ix[0], ix[i], ix[i + 1]))
_bvh = BVHTree.FromPolygons(_v, _tris)


def surface_lift(P, r, u, n, hw, hh):
    best = None
    for a, b in ((0, 0), (-0.7, -0.7), (0.7, -0.7), (0.7, 0.7), (-0.7, 0.7)):
        o = P + r * (a * hw) + u * (b * hh) + n * 0.008
        hit = _bvh.ray_cast(Vector(o), Vector(-n), 0.012)
        if hit[0] is not None:
            h = 0.008 - hit[3]
            best = h if best is None else max(best, h)
    return 0.0 if best is None else best


nv = sum(1 for ln in src.split("\n") if ln.startswith("v "))
nt = sum(1 for ln in src.split("\n") if ln.startswith("vt "))
nn = sum(1 for ln in src.split("\n") if ln.startswith("vn "))
out = ["o cockpit_labels", "usemtl cklabel"]
keylines = ["# TyphoonMod key lights: key <state> <lit cell u0 v0 u1 v1> <dim cell u0 v0 u1 v1> <legend>   (made by make_labels.py)"]


def rect(c):
    return (c["x"] / AW, 1 - (c["y"] + c["h"]) / AH, (c["x"] + c["w"]) / AW, 1 - c["y"] / AH)


def unity(v):
    return (v[0], v[2], v[1])


LIFT = 0.0005
for l in labels:
    c = cells[l["key"]]
    P, r, u, n = (np.array(l[k], float) for k in ("pos", "r", "u", "n"))
    r /= np.linalg.norm(r); n /= np.linalg.norm(n)
    u = np.cross(n, r); u /= np.linalg.norm(u)
    if np.dot(u, np.array(l["u"], float)) < 0:
        u = -u
    hw, hh = c["w"] / PPM / 2, c["h"] / PPM / 2
    P = P + n * (surface_lift(P, r, u, n, hw, hh) + LIFT)
    corners = [P - r * hw + u * hh, P + r * hw + u * hh, P + r * hw - u * hh, P - r * hw - u * hh]
    u0, u1 = c["x"] / AW, (c["x"] + c["w"]) / AW
    v1, v0 = 1 - c["y"] / AH, 1 - (c["y"] + c["h"]) / AH
    uvs = [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]
    cu = [np.array(unity(q)) for q in corners]
    nu = np.array(unity(n))
    for q in cu:
        out.append("v %.5f %.5f %.5f" % tuple(q))
    for t in uvs:
        out.append("vt %.5f %.5f" % t)
    out.append("vn %.4f %.4f %.4f" % tuple(nu))
    tri = [(0, 1, 2), (0, 2, 3)]
    if np.dot(np.cross(cu[1] - cu[0], cu[2] - cu[0]), nu) < 0:
        tri = [(0, 2, 1), (0, 3, 2)]
    nn += 1
    for a, b, c_ in tri:
        out.append("f %d/%d/%d %d/%d/%d %d/%d/%d" % (nv + a + 1, nt + a + 1, nn, nv + b + 1, nt + b + 1, nn, nv + c_ + 1, nt + c_ + 1, nn))
    nv += 4; nt += 4
    if "uid" in l:
        keylines.append("key %s %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f %s" % ((l["state"],) + rect(cells[l["key"]]) + rect(cells[l["offkey"]])
                                                                                  + (l["text"].replace("|", "_").replace(" ", "_"),)))
open(obj, "w").write(src.rstrip("\n") + "\n" + "\n".join(out) + "\n")
mt = os.path.join(D, "typhoon_materials.txt")
ms = open(mt).read()
if "\ncklabel " not in "\n" + ms:
    open(mt, "w").write(ms.rstrip("\n") + "\ncklabel base=cklabel.png alpha=0.998 smooth=0.25 metal=0\n")
open(os.path.join(D, "typhoon_keys.txt"), "w").write("\n".join(keylines) + "\n")
ck = os.path.join(D, "typhoon_cockpit.txt")
if mdef is not None and os.path.exists(ck):
    P, r, u, n = (np.array(mdef[k], float) for k in ("pos", "r", "u", "n"))
    r /= np.linalg.norm(r); n /= np.linalg.norm(n)
    u2 = np.cross(n, r); u2 /= np.linalg.norm(u2)
    if np.dot(u2, u) < 0:
        u2 = -u2
    hw, hh = mdef["lcd"][0] / 2 - 0.0012, mdef["lcd"][1] / 2 - 0.0012
    P = P + n * surface_lift(P, r, u2, n, hw, hh)
    cs = [P - r * hw + u2 * hh, P + r * hw + u2 * hh, P + r * hw - u2 * hh, P - r * hw - u2 * hh]
    lines = [ln for ln in open(ck).read().split("\n") if not ln.startswith("screen mdef ")]
    while lines and not lines[-1].strip():
        lines.pop()
    lines.append("screen mdef " + " ".join("%.4f %.4f %.4f" % unity(c) for c in cs) + " 0.0007")
    open(ck, "w").write("\n".join(lines) + "\n")
    print("mdef screen %.1f x %.1f mm" % (hw * 2000, hh * 2000))
print(f"key lights: {nkey} legends with a state")
print(f"labels: {len(labels)} quads, {len(order)} atlas cells, atlas rows used {y + row} of {AH}")
