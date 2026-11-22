import sys, os, math, numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
ST = sys.argv[1]
mats = {}
for l in open(os.path.join(ST, "typhoon_materials.txt")):
    t = l.split()
    if not t or t[0].startswith("#"): continue
    kv = dict(x.split("=", 1) for x in t[1:] if "=" in x)
    mats[t[0]] = kv
size = {}
def tsize(name):
    if name not in size:
        p = os.path.join(ST, name)
        size[name] = Image.open(p).size if os.path.exists(p) else None
    return size[name]
V = []; VT = []; g = None; m = None; acc = {}
for l in open(os.path.join(ST, "typhoon.obj")):
    if l.startswith("v "): V.append([float(x) for x in l.split()[1:4]])
    elif l.startswith("vt "): VT.append([float(x) for x in l.split()[1:3]])
    elif l.startswith("o "): g = l[2:].strip(); m = None
    elif l.startswith("usemtl"): m = l.split()[1]
    elif l.startswith("f ") and g and (g.startswith(("cockpit", "canopy")) or (len(sys.argv) > 2 and g.startswith(sys.argv[2]))):
        c = [t.split("/") for t in l.split()[1:]]
        for j in range(1, len(c) - 1):
            tri = [c[0], c[j], c[j + 1]]
            P = np.array([V[int(t[0]) - 1] for t in tri])
            a3 = np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])) / 2
            if all(len(t) > 1 and t[1] for t in tri):
                U = np.array([VT[int(t[1]) - 1] for t in tri])
                a2 = abs((U[1, 0] - U[0, 0]) * (U[2, 1] - U[0, 1]) - (U[2, 0] - U[0, 0]) * (U[1, 1] - U[0, 1])) / 2
            else: a2 = 0.0
            k = (g, m)
            e = acc.setdefault(k, [0.0, 0.0, 0])
            e[0] += a3; e[1] += a2; e[2] += 1
rows = []
for (g, m), (a3, a2, n) in acc.items():
    kv = mats.get(m, {})
    base = kv.get("base")
    sz = tsize(base) if base else None
    tile = float(kv.get("tile", 1))
    dens = math.sqrt(a2 * sz[0] * sz[1] / a3) * tile if (sz and a3 > 1e-9 and a2 > 0) else 0
    rows.append((g, m, n, a3, base, sz, dens))
rows.sort(key=lambda r: (r[0], -r[3]))
print("%-26s %-12s %7s %8s %-22s %-12s %s" % ("group", "material", "tris", "area m2", "base", "size", "texels/m"))
for g, m, n, a3, base, sz, dens in rows:
    if a3 < 0.002: continue
    print("%-26s %-12s %7d %8.3f %-22s %-12s %6.0f" % (g, m, n, a3, base or "-", ("%dx%d" % sz) if sz else "-", dens))
