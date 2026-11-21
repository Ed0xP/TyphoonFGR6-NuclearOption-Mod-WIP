import glob
import os
import sys

ST = sys.argv[1]
n = 0
for p in sorted(glob.glob(os.path.join(ST, "typhoon_*.txt")) + glob.glob(os.path.join(ST, "sounds", "flyby.txt"))):
    rows = open(p, encoding="utf-8").read().split("\n")
    keep = [r for r in rows if not r.lstrip().startswith("#")]
    while keep and not keep[0].strip():
        keep.pop(0)
    out, blank = [], 0
    for r in keep:
        blank = blank + 1 if not r.strip() else 0
        if blank <= 1:
            out.append(r)
    n += len(rows) - len(keep)
    open(p, "w", encoding="utf-8").write("\n".join(out).rstrip("\n") + "\n")
print("strip_comments: %d comment lines removed from the data files" % n)
