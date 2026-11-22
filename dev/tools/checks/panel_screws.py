import math
import os
import sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../model/cockpit_panel.txt")
boxes, screws = [], []


def box(what, x, y, w, h, ang=0.0):
    if ang:
        a = math.radians(ang)
        w, h = abs(w * math.cos(a)) + abs(h * math.sin(a)), abs(w * math.sin(a)) + abs(h * math.cos(a))
    boxes.append((what, x, y, w / 2, h / 2))


for n, raw in enumerate(open(path), 1):
    t = raw.split("#")[0].split()
    if not t:
        continue
    k = t[0]
    f = lambda i: float(t[i])
    if k == "key":
        box("key %s (line %d)" % (t[5], n), f(1), f(2), f(3), f(4), float(t[7]) if len(t) > 7 else 0.0)
    elif k == "grid":
        nx, ny = int(t[5]), int(t[6])
        for j in range(ny):
            for i in range(nx):
                x = f(1) + (f(3) - f(1)) * (i / (nx - 1) if nx > 1 else 0)
                y = f(2) + (f(4) - f(2)) * (j / (ny - 1) if ny > 1 else 0)
                box("grid key (line %d)" % n, x, y, f(7), f(8))
    elif k in ("lcd", "lamp", "slider"):
        box("%s (line %d)" % (k, n), f(1), f(2), f(3), f(4))
    elif k in ("label", "text"):
        lines = t[4].split("|")
        cap = f(3)
        box("%s %s (line %d)" % (k, t[4], n), f(1), f(2), max(len(s) for s in lines) * cap * 0.85, cap * 1.6 * len(lines))
    elif k == "vent":
        box("vent (line %d)" % n, f(1), f(2), f(3), f(3))
    elif k == "disc":
        if t[4] == "screw":
            screws.append((n, f(1), f(2), f(3) / 2))
        else:
            box("%s (line %d)" % (t[4], n), f(1), f(2), f(3), f(3))
bad = 0
for n, x, y, r in screws:
    best = (1e9, "")
    for what, cx, cy, hw, hh in boxes:
        d = math.hypot(max(abs(x - cx) - hw, 0), max(abs(y - cy) - hh, 0)) - r
        best = min(best, (d, what))
    for m, ox, oy, orr in screws:
        if m != n:
            best = min(best, (math.hypot(ox - x, oy - y) - r - orr, "screw (line %d)" % m))
    flag = "TOUCHES" if best[0] < 2.0 else "clear  "
    bad += best[0] < 2.0
    print("line %3d screw (%7.1f %7.1f) d %4.1f  %s %5.1f px from %s" % (n, x, y, 2 * r, flag, best[0], best[1]))
print("%d screws, %d touching something" % (len(screws), bad))
