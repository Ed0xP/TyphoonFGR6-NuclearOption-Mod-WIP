import math, os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
hot = open(os.path.join(here, "cockpit_hotas.py")).read()
bc = open(os.path.join(here, "build_cockpit.py")).read()
m = re.search(r"^THR_TRAVEL, THR_RADIUS = ([0-9.]+), ([0-9.]+)", hot, re.M)
travel, radius = float(m.group(1)), float(m.group(2))
yoff = float(re.search(r"^THR_Y_OFF = ([0-9.]+)", hot, re.M).group(1))
cx, cy, cz = (float(re.search(r'"THR_%s", "(-?[0-9.]+)"' % a, bc).group(1)) for a in "XYZ")
hy, hz = cz + 0.005 - radius, cy + yoff
ang = math.degrees(math.asin(travel / radius))
line = "cockpit_throttle %.4f %.4f %.4f %.4f %.4f %.4f throttle %.2f" % (cx, hy, hz, cx + 1.0, hy, hz, ang)
p = os.path.join(sys.argv[1], "typhoon_surfaces.txt")
rows = open(p).read().rstrip("\n").split("\n")
hit = [i for i, r in enumerate(rows) if r.split()[:1] == ["cockpit_throttle"]]
if hit:
    rows[hit[0]] = line
else:
    rows.append(line)
open(p, "w").write("\n".join(rows) + "\n")
print("throttle surface:", line)
