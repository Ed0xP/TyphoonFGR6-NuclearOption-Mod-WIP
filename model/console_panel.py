import math

import numpy as np

import console_layout as cl
import panelkit as pk

PLATE_Z, INNER_Z, GAP = 3.0, 1.7, 0.5
BEVEL = 1.0
SCREW = np.array([0.60, 0.55, 0.40], np.float32)
FILES = {1: ("console_right.txt", "ckconr", "conr"), -1: ("console_left.txt", "ckconl", "conl")}
WINS = {1: (268.0, 536.0, 6200.0, 7272.0), -1: (-536.0, -268.0, 6200.0, 7272.0)}
RES = (2048, 8192)


def top_mask(P, side):
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    a = np.linalg.norm(n, axis=1)
    n = n / np.maximum(a, 1e-12)[:, None]
    c = P.mean(1)
    return ((n[:, 1] > 0.97) & (a / 2 > 0.01) & (c[:, 0] * side > 0.26) & (c[:, 0] * side < 0.54) & (c[:, 1] > 0.40) & (c[:, 1] < 0.56)
            & (c[:, 2] > 6.2) & (c[:, 2] < 7.2))


def shell_remove_mask(P):
    return top_mask(P, 1) | top_mask(P, -1)


class Plan:

    def __init__(self, T):
        self.T = np.asarray(T, float)
        n = np.cross(self.T[:, 1] - self.T[:, 0], self.T[:, 2] - self.T[:, 0])
        n /= np.linalg.norm(n, axis=1)[:, None]
        self.n = np.where(n[:, 1:2] < 0, -n, n)
        self.c = self.T.mean(1)
        self.X, self.Y, self.N = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
        self.top = 0.0

    def tri(self, x, y):
        q = np.array([x / 1000.0, y / 1000.0])
        best, bd = 0, 1e9
        for i, t in enumerate(self.T):
            a, b, c = t[:, [0, 2]]
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-12:
                continue
            w1 = ((b[1] - c[1]) * (q[0] - c[0]) + (c[0] - b[0]) * (q[1] - c[1])) / d
            w2 = ((c[1] - a[1]) * (q[0] - c[0]) + (a[0] - c[0]) * (q[1] - c[1])) / d
            out = max(0.0, -w1, -w2, -(1 - w1 - w2))
            if out < bd:
                best, bd = i, out
        return best

    def height(self, x, y):
        i = self.tri(x, y)
        n, p = self.n[i], self.T[i, 0]
        return p[1] - (n[0] * (x / 1000.0 - p[0]) + n[2] * (y / 1000.0 - p[2])) / n[1], n

    def pt(self, x, y, z=0.0):
        h, _ = self.height(x, y)
        return np.array([x / 1000.0, y / 1000.0, h + z / 1000.0])

    def local(self, p):
        x, y = p[0] * 1000.0, p[1] * 1000.0
        h, _ = self.height(x, y)
        return x, y, (p[2] - h) * 1000.0

    def label(self, text, x, y, cap, z=0.0, col=None, spacing=1.35):
        _, n = self.height(x, y)
        nb = np.array([n[0], n[2], n[1]])
        r = np.array([1.0, 0, 0]) - nb * nb[0]
        r /= np.linalg.norm(r)
        u = np.cross(nb, r)
        return {"pos": [float(v) for v in self.pt(x, y, z)], "r": [float(v) for v in r], "u": [float(v) for v in u],
                "n": [float(v) for v in nb], "text": text, "cap": cap, "font": "FONT", "spacing": spacing,
                "col": list(col) if col is not None else [0.89, 0.90, 0.86], "seen": True}


class Lay:

    def __init__(self, side):
        self.side = side
        self.L = cl.load(FILES[side][0])
        self.plates, self.recs = [], []
        for it in self.L.items:
            if it["kind"] in ("plate", "recess"):
                poly = [self.mm(px, py) for px, py in it["pts"]]
                (self.plates if it["kind"] == "plate" else self.recs).append(poly)
        self.inner = [any(pk._inside(*np.mean(p, 0), r) for r in self.recs) for p in self.plates]

    def mm(self, px, py):
        x, z = self.L.to_xz(px, py)
        return self.side * x * 1000.0, z * 1000.0

    def box(self, it):
        (xa, ya), (xb, yb) = self.mm(it["x0"], it["y0"]), self.mm(it["x1"], it["y1"])
        return (xa + xb) / 2, (ya + yb) / 2, abs(xb - xa), abs(yb - ya)

    def lift(self, x, y):
        for p, inn in zip(self.plates, self.inner):
            if inn and pk._inside(x, y, p):
                return INNER_Z
        if any(pk._inside(x, y, r) for r in self.recs):
            return 0.0
        return PLATE_Z if any(pk._inside(x, y, p) for p in self.plates) else 0.0


def lift_fn(L, side):
    lay = Lay(side)
    return lambda px, py: lay.lift(*lay.mm(px, py)) / 1000.0


def build(side, ck, sw, shell_P):
    import bmesh
    from mathutils import Vector
    lay = Lay(side)
    T = shell_P[top_mask(shell_P, side)]
    plan = Plan(T)
    b = pk.Builder(ck, sw, plan, WINS[side])
    base = bmesh.new()
    for t in T:
        vs = [base.verts.new(Vector((p[0], p[2], p[1]))) for p in t]
        f = base.faces.new(vs)
        f.normal_update()
        if f.normal.z < 0:
            f.normal_flip()
    bmesh.ops.remove_doubles(base, verts=base.verts[:], dist=1e-5)
    b.slab.append(b._uv(base))
    for poly, inn in zip(lay.plates, lay.inner):
        holes = [] if inn else [r for r in lay.recs if pk._inside(*np.mean(r, 0), poly)]
        zt = INNER_Z if inn else PLATE_Z
        b.prism(pk.inset_poly(poly, GAP), -0.3, zt, bevel=min(BEVEL, 0.42 * (zt + 0.3)), holes=holes, seg=3)
    labels = []
    L = lay.L
    for it in L.items:
        if it["kind"] == "label":
            x, y = lay.mm(it["x"], it["y"])
            labels.append(plan.label(it["text"], x, y, float(it["cap"]), z=lay.lift(x, y)))
        elif it["kind"] == "key" and it["text"]:
            x, y = lay.mm(it["x"], it["y"])
            col = {"green": [0.45, 1.0, 0.5], "blue": [0.75, 0.85, 1.0]}.get(it["colour"], [0.9, 0.9, 0.86])
            labels.append(plan.label(it["text"], x, y, min(it["w"], it["h"]) * 0.30, z=lay.lift(x, y), col=col))
    return {"slab": ck.merge(b.slab), "labels": labels, "tris": len(T)}


def paint(side, out_dir):
    lay = Lay(side)
    L = lay.L
    name = FILES[side][1]
    c = pk.Canvas(WINS[side], RES, cl.C_BACK, seed=70 + side)
    c.paintm[...] = 0.35
    rng = np.random.default_rng(7)
    mmk = 0.001 / L.K
    screws, corner = [], []
    pi = 0
    for it in L.items:
        k = it["kind"]
        if k == "plate":
            poly, inn = lay.plates[pi], lay.inner[pi]
            pi += 1
            P = np.asarray(poly)
            s = c.sub(P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max())
            col = (L.plate_col if L.plate_col is not None else cl.C_PLATE) * (1.0 + rng.uniform(-0.03, 0.03))
            s.plate(pk.sd_poly(s.X, s.Y, pk.inset_poly(poly, GAP)), INNER_Z if inn else PLATE_Z, col, smooth=0.36, wear=1.5)
            for i in range(len(P)):
                p, e1, e2 = P[i], P[i - 1] - P[i], P[(i + 1) % len(P)] - P[i]
                l1, l2 = np.linalg.norm(e1), np.linalg.norm(e2)
                if min(l1, l2) < 1e-6:
                    continue
                e1, e2 = e1 / l1, e2 / l2
                half = math.acos(float(np.clip(e1 @ e2, -1, 1))) / 2
                if half < math.radians(20) or half > math.radians(80):
                    continue
                k = 9.0 / (2 * math.cos(half))
                k = max(k, 6.0 / math.sin(2 * half))
                alts = [p + e1 * (k + a) + e2 * (k + b) for a, b in ((0, 0), (4, 0), (0, 4), (4, 4), (8, 0), (0, 8), (12, 0), (0, 12),
                                                                     (17, 0), (0, 17), (8, 8), (23, 0), (0, 23))
                        if k + a < 0.45 * l1 and k + b < 0.45 * l2]
                if alts:
                    corner.append((alts, INNER_Z if inn else PLATE_Z))
        elif k == "recess":
            poly = [lay.mm(px, py) for px, py in it["pts"]]
            P = np.asarray(poly)
            s = c.sub(P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max())
            s.plate(pk.sd_poly(s.X, s.Y, poly), 0.0, cl.C_RECESS, smooth=0.28, paint=0.3)
        elif k in ("hazard", "slot", "guard"):
            cx, cy, w, h = lay.box(it)
            s = c.sub(cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2)
            sd = pk.sd_rrect(s.X, s.Y, cx, cy, w, h, 0.4)
            if k == "hazard":
                yb = it["style"] == "yb"
                s.put(s.cov(sd - 0.4), cl.C_SEAM, None, 0.25)
                s.hazard(sd, period=7.0, a=cl.C_YEL if yb else cl.C_ORA, b=cl.C_BLK if yb else cl.C_WSTR)
                if not yb:
                    for sx in (-1, 1):
                        for sy in (-1, 1):
                            screws.append(np.array([cx + sx * (w / 2 - 5), cy + sy * (h / 2 - 5)]))
            elif k == "slot":
                s.plate(sd, -3.0, cl.C_SLOT, smooth=0.2, paint=0.0)
            else:
                s.put(s.cov(sd), cl.C_SLOT, None, 0.2, 0.0)
        elif k == "line":
            c.line([lay.mm(px, py) for px, py in it["pts"]], 0.7, cl.C_WHITE)
        elif k == "screw":
            screws.append(np.array(lay.mm(it["x"], it["y"])))
    for it in L.items:
        k = it["kind"]
        if k in ("toggle", "knob", "key", "lpcock", "probe", "rocker", "lamp", "pin", "drf"):
            x, y = lay.mm(it["x"], it["y"])
            z0 = lay.lift(x, y)
            if k == "key":
                w, h = it["w"] * 1000 + 4.4, it["h"] * 1000 + 4.4
                s = c.sub(x - w, x + w, y - h, y + h)
                s.stand(pk.sd_rrect(s.X, s.Y, x, y, w, h, 1.0), z0 + 6.0)
                s.mark(pk.sd_rrect(s.X, s.Y, x, y, w + 0.8, h + 0.8, 1.3), pk.BLACK * 1.4, None, 0.25)
            else:
                r, z = {"toggle": (6.0, 7.0), "lpcock": (8.0, 12.0), "probe": (9.0, 14.0), "rocker": (10.0, 6.0), "lamp": (5.0, 3.0),
                        "pin": (6.0, 12.0)}.get(k, (it.get("d", 0.02) * 1000 * (0.47 if k == "knob" else 0.9), 12.0 if k == "knob" else 6.0))
                s = c.sub(x - r, x + r, y - r, y + r, pad=r + 8)
                s.stand(pk.sd_circle(s.X, s.Y, x, y, r), z0 + z)
                s.mark(pk.sd_circle(s.X, s.Y, x, y, r + 0.6), pk.BLACK * 1.4, None, 0.25)
                d = np.hypot(s.X - x, s.Y - y)
                s.base *= (1 + 0.035 * np.clip(1 - np.abs(d - r - 6.0) / 6.0, 0, 1) * (s.paintm > 0.6))[..., None]
        elif k in ("canopy", "guard"):
            cx, cy, w, h = lay.box(it)
            s = c.sub(cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2, pad=16)
            s.stand(pk.sd_rrect(s.X, s.Y, cx, cy, w * (0.5 if k == "canopy" else 1.0), h * (0.9 if k == "canopy" else 1.0), 2.0), lay.lift(cx, cy) + (20.0 if k == "canopy" else 12.0))
    keep = []
    for it in L.items:
        if it["kind"] == "label" and it["text"]:
            x, y = lay.mm(it["x"], it["y"])
            cap = float(it["cap"])
            lines = str(it["text"]).split("|")
            hw = 0.5 * max(len(ln) for ln in lines) * cap * 0.85
            hh = cap * 0.8 + (len(lines) - 1) * cap * 1.35
            keep.append((x - hw, x + hw, y - hh, y + hh))
    c.keep = keep
    placed = []
    moved = dropped = 0
    for p in screws:
        q = c.clear_spot(float(p[0]), float(p[1]), 2.7, placed, keep)
        if q is None:
            q = (float(p[0]), float(p[1]))
            print("console screw at (%.1f, %.1f): no clear spot within 8 mm, left where it is" % q)
        elif q != (float(p[0]), float(p[1])):
            print("console screw moved (%.1f, %.1f) -> (%.1f, %.1f)" % (p[0], p[1], q[0], q[1]))
        placed.append((q[0], q[1], 2.7))
    n_named = len(placed)
    for alts, zt in corner:
        for i, p in enumerate(alts):
            if c.screw_fault(float(p[0]), float(p[1]), 2.7, placed, keep, want_z=zt) is None:
                placed.append((float(p[0]), float(p[1]), 2.7))
                moved += i > 0
                break
        else:
            dropped += 1
    for x, y, r in placed:
        c.screw(x, y, r, "cross", rng.uniform(0, math.pi), SCREW)
    print("console corner screws: %d placed (%d moved off something), %d corners left bare" % (len(placed) - n_named, moved, dropped))
    c.edge = dict(hl=0.24, bw=0.55, chamfer=(0.04, 0.9))
    c.finish(wear=1.45, gain=1.15)
    c.save(out_dir, name)
    print("console panel painted:", name, len(placed), "screws")
