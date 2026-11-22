import json
import math
import os
import sys

import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ST = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else None
INTERIOR = ("cockpit_", "canopy_interior")
SKIP_SURF = ("cockpit_labels", "cockpit_placards", "cockpit_disptext", "cockpit_dispmarks", "cockpit_hudglass", "cockpit_sbyglass")
ALWAYS = ("cockpit_detscrews",)

V, groups, g = [], {}, None
for l in open(os.path.join(ST, "typhoon.obj")):
    if l.startswith("v "):
        V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("o "):
        g = l[2:].strip()
    elif l.startswith("f ") and g and g.startswith(INTERIOR):
        groups.setdefault(g, []).append([int(t.split("/")[0]) - 1 for t in l.split()[1:]])
V = np.array(V)


def components(faces):
    key, par = {}, {}

    def kid(i):
        return key.setdefault(tuple(np.round(V[i], 4)), len(key))

    def find(a):
        while par.setdefault(a, a) != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for f in faces:
        ks = [kid(i) for i in f]
        for a in ks[1:]:
            par[find(a)] = find(ks[0])
    comp = {}
    for fi, f in enumerate(faces):
        comp.setdefault(find(kid(f[0])), []).append(fi)
    return list(comp.values())


def describe(P):
    c = P.mean(0)
    ext = P.max(0) - P.min(0)
    if ext.max() > 0.030 or ext.max() < 0.0015:
        return None
    w, vec = np.linalg.eigh(np.cov((P - c).T))
    ax = vec[:, 0]
    t = (P - c) @ ax
    rad = np.linalg.norm((P - c) - np.outer(t, ax), axis=1)
    h = t.max() - t.min()
    rim = rad[rad > 0.55 * rad.max()]
    if len(rim) < 6 or h > 1.3 * rad.max() or rim.std() > 0.12 * rim.mean():
        return None
    return c, ax, float(rim.max()), float(h)


NOT_FASTENERS = ("cockpit_stick", "cockpit_throttle", "cockpit_keys", "cockpit_sbyneedle", "cockpit_sw_", "cockpit_gearlever",
                 "cockpit_pedal", "cockpit_cables", "cockpit_bezels", "cockpit_mirror", "cockpit_pin")
fast = []
tri_all, tri_tag = [], []
for gname, faces in groups.items():
    comps = components(faces)
    own = {}
    look = gname in ALWAYS or not (gname in SKIP_SURF or gname.startswith(NOT_FASTENERS))
    for ci, fs in enumerate(comps):
        ids = sorted({i for fi in fs for i in faces[fi]})
        d = describe(V[ids]) if (look and (gname in ALWAYS or len(ids) <= 120)) else None
        if d is not None and gname not in ALWAYS:
            if d[3] > 0.9 * d[2] or d[2] > 0.0052 or d[2] < 0.0012 or d[3] > 0.0036:
                d = None
        if d is not None and d[2] > 0.0052:
            d = None
        if d is not None:
            fast.append(dict(group=gname, c=d[0], ax=d[1], r=d[2], h=d[3], id=len(fast)))
            for fi in fs:
                own[fi] = len(fast) - 1
    if gname in SKIP_SURF:
        continue
    for fi, f in enumerate(faces):
        for j in range(1, len(f) - 1):
            tri_all.append((f[0], f[j], f[j + 1]))
            tri_tag.append((gname, own.get(fi, -1)))
print("fasteners3d: %d interior groups, %d triangles, %d fasteners (%d in cockpit_detscrews)" %
      (len(groups), len(tri_all), len(fast), sum(1 for f in fast if f["group"] == "cockpit_detscrews")))

verts = [Vector(v) for v in V]
keep = [k for k, tg in enumerate(tri_tag) if tg[1] < 0 and tg[0] not in ("cockpit_detscrews", "cockpit_detholes")]
base_tris = [tri_all[k] for k in keep]
base_tag = [tri_tag[k][0] for k in keep]
bvh = BVHTree.FromPolygons(verts, base_tris)
wsum = 0.0
for nm in ("cockpit_conr", "cockpit_conl", "cockpit_panel"):
    for f in groups.get(nm, [])[:4000]:
        n = np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]])
        wsum += n[1] if nm != "cockpit_panel" else -n[2]
WIND = 1.0 if wsum >= 0 else -1.0


def cast(o, d, dist):
    h = bvh.ray_cast(Vector(o), Vector(d), dist)
    if h[0] is None:
        return None, None, False
    return h[3], base_tag[h[2]], (np.array(h[1]) @ np.asarray(d)) * WIND < 0


_par = list(range(len(fast)))


def _find(a):
    while _par[a] != a:
        _par[a] = _par[_par[a]]
        a = _par[a]
    return a


_C = np.array([f["c"] for f in fast]) if fast else np.zeros((0, 3))
for i, f in enumerate(fast):
    near = np.nonzero(np.linalg.norm(_C - f["c"], axis=1) < 0.012)[0]
    for j in near:
        if j <= i or fast[j]["group"] != f["group"]:
            continue
        g_ = fast[j]
        big = f if f["r"] >= g_["r"] else g_
        off = g_["c"] - f["c"]
        along = abs(off @ big["ax"])
        lateral = np.linalg.norm(off - (off @ big["ax"]) * big["ax"])
        if abs(abs(f["ax"] @ g_["ax"]) - 1) < 0.05 and lateral < 0.5 * big["r"] and along < f["h"] / 2 + g_["h"] / 2 + 0.0012:
            _par[_find(j)] = _find(i)
_cl = {}
for i in range(len(fast)):
    _cl.setdefault(_find(i), []).append(fast[i])
merged = []
for parts in _cl.values():
    big = max(parts, key=lambda q: q["r"])
    ax = big["ax"]
    lo = min((q["c"] - big["c"]) @ ax - q["h"] / 2 for q in parts)
    hi = max((q["c"] - big["c"]) @ ax + q["h"] / 2 for q in parts)
    merged.append(dict(group=big["group"], c=big["c"] + ax * ((lo + hi) / 2), ax=ax, r=big["r"], h=hi - lo, parts=len(parts)))
print("fasteners3d: %d pieces -> %d fasteners" % (len(fast), len(merged)))
fast = merged

LIFT = 0.004
COVER = 0.006
EYE = np.array([0.0, 1.16, 6.5])
SEEN_FROM = [EYE] + [np.array([x, y, z]) for x in (-0.15, 0.0, 0.15) for y in (0.75, 1.0) for z in (6.6, 7.0)] + [np.array([0.0, 1.05, 7.5])]


def open_rays(p):
    n = 0
    for q in SEEN_FROM:
        d = q - p
        L = np.linalg.norm(d)
        if cast(p, d / L, L)[0] is None:
            n += 1
    return n


faults = []
for f in fast:
    c, ax, r, h = f["c"], f["ax"], f["r"], f["h"]
    free = []
    for s in (1.0, -1.0):
        t_ = cast(c + ax * s * (h / 2 + 0.0003), ax * s, 0.03)[0]
        free.append(0.03 if t_ is None else t_)
    if abs(free[0] - free[1]) > 0.002:
        s = 1.0 if free[0] > free[1] else -1.0
    else:
        sc = [open_rays(c + ax * s * (h / 2 + 0.0006)) for s in (1.0, -1.0)]
        s = 1.0 if sc[0] > sc[1] else -1.0 if sc[1] > sc[0] else (1.0 if ax @ (EYE - c) > 0 else -1.0)
    up = ax * s
    f["ax"] = up
    top_p = c + up * (h / 2)
    e1 = np.cross(up, [1.0, 0, 0] if abs(up[0]) < 0.9 else [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(up, e1)
    ring = [(e1 * math.cos(2 * math.pi * k / 8) + e2 * math.sin(2 * math.pi * k / 8)) for k in range(8)]
    fl = []
    cv, gcv, _ = cast(top_p + up * 0.0003, up, COVER)
    lift = LIFT
    if cv is not None:
        fl.append("covered")
        f["under"] = "%s at %.1f mm" % (gcv, (cv + 0.0003) * 1000)
        lift = min(LIFT, max(cv + 0.0003 - 0.0002, 0.0002))
    t0, g0, _ = cast(top_p + up * lift, -up, lift + h + 0.012)
    if t0 is None:
        f["faults"] = fl + ["float"]
        f["note"] = "nothing under it within 12 mm"
        faults.append(f)
        continue
    proud = t0 - lift
    f["on"] = g0
    f["proud_mm"] = round(proud * 1000, 2)
    if proud > h + 0.0006:
        fl.append("float")
    if proud < 0.00015:
        fl.append("sunk")
    miss = 0
    for q in ring:
        d, _, _ = cast(top_p + up * lift + q * (0.85 * r), -up, lift + max(proud, 0.0) + 0.0015 + 0.3 * r)
        if d is None:
            miss += 1
    if miss >= 2:
        fl.append("overhang")
    f["rim_missing"] = miss
    f["faults"] = fl
    if fl:
        faults.append(f)

C = np.array([f["c"] for f in fast]) if fast else np.zeros((0, 3))
for i, f in enumerate(fast):
    d = np.linalg.norm(C - f["c"], axis=1)
    d[i] = 9
    j = int(d.argmin())
    if d[j] < f["r"] + fast[j]["r"] + 0.0005 and d[j] > 0.0002:
        off = (fast[j]["c"] - f["c"])
        lateral = np.linalg.norm(off - (off @ f["ax"]) * f["ax"])
        if lateral > 0.35 * (f["r"] + fast[j]["r"]):
            f.setdefault("faults", []).append("crowd")
            f["near"] = "%s %.1f mm away" % (fast[j]["group"], d[j] * 1000)
            if not any(x is f for x in faults):
                faults.append(f)

by = {}
for f in faults:
    for k in f["faults"]:
        by[k] = by.get(k, 0) + 1
print("fasteners3d: %d with faults: %s" % (len(faults), ", ".join("%s %d" % kv for kv in sorted(by.items())) or "none"))
rows = []
for f in sorted(faults, key=lambda f: (f["group"], round(f["c"][2], 2), f["c"][0])):
    c = f["c"]
    print("  %-20s (%+.3f %.3f %.3f) r %.1f h %.1f mm  %-24s on %-20s proud %s rim-miss %s %s %s" % (
        f["group"], c[0], c[1], c[2], f["r"] * 1000, f["h"] * 1000, "+".join(f["faults"]), f.get("on"), f.get("proud_mm"),
        f.get("rim_missing"), f.get("under", ""), f.get("near", "")))
    rows.append(dict(group=f["group"], pos=[round(float(x), 4) for x in c], r_mm=round(f["r"] * 1000, 2), faults=f["faults"],
                     on=f.get("on"), proud_mm=f.get("proud_mm"), rim_missing=f.get("rim_missing"), under=f.get("under"), near=f.get("near")))
if OUT:
    json.dump(dict(count=len(fast), faults=rows), open(OUT, "w"), indent=1)
