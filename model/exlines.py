import math
import os

import cv2
import numpy as np
from PIL import Image

K = 8
KS = 4
KP = 4


def _dp(pts, eps):
    n = len(pts)
    if n < 3:
        return pts
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    st = [(0, n - 1)]
    while st:
        a, b = st.pop()
        if b <= a + 1:
            continue
        p, q = pts[a], pts[b]
        d = q - p
        L = math.hypot(d[0], d[1])
        seg = pts[a + 1:b]
        if L < 1e-9:
            dist = np.hypot(seg[:, 0] - p[0], seg[:, 1] - p[1])
        else:
            dist = np.abs(d[0] * (seg[:, 1] - p[1]) - d[1] * (seg[:, 0] - p[0])) / L
        i = int(dist.argmax())
        if dist[i] > eps:
            keep[a + 1 + i] = True
            st.append((a, a + 1 + i))
            st.append((a + 1 + i, b))
    return pts[keep]


def _round(pts, closed, max_turn=38.0, it=2):
    for _ in range(it):
        n = len(pts)
        if n < 3:
            return pts
        out = []
        rng = range(n) if closed else range(1, n - 1)
        if not closed:
            out.append(pts[0])
        for i in rng:
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
            u, v = b - a, c - b
            lu, lv = math.hypot(*u), math.hypot(*v)
            if lu < 1e-6 or lv < 1e-6:
                out.append(b)
                continue
            ang = math.degrees(math.acos(max(-1.0, min(1.0, float(u @ v) / (lu * lv)))))
            if 2.0 < ang < max_turn:
                out.append(b - u * 0.25)
                out.append(b + v * 0.25)
            else:
                out.append(b)
        if not closed:
            out.append(pts[-1])
        pts = np.array(out)
    return pts


def _trace(sk):
    H, W = sk.shape
    ys, xs = np.nonzero(sk)
    idx = -np.ones((H, W), np.int32)
    idx[ys, xs] = np.arange(len(ys))
    nb = [[] for _ in range(len(ys))]
    for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
        y2, x2 = ys + dy, xs + dx
        ok = (y2 >= 0) & (y2 < H) & (x2 >= 0) & (x2 < W)
        j = np.full(len(ys), -1, np.int32)
        j[ok] = idx[y2[ok], x2[ok]]
        for i in np.nonzero(j >= 0)[0]:
            nb[i].append(int(j[i]))
    for i in range(len(ys)):
        if len(nb[i]) > 2:
            four = [j for j in nb[i] if abs(ys[j] - ys[i]) + abs(xs[j] - xs[i]) == 1]
            diag = [j for j in nb[i] if abs(ys[j] - ys[i]) + abs(xs[j] - xs[i]) == 2]
            keepd = [j for j in diag if not any(abs(ys[j] - ys[f]) + abs(xs[j] - xs[f]) == 1 for f in four)]
            nb[i] = four + keepd
    deg = np.array([len(n) for n in nb])
    node = deg != 2
    used = set()
    paths = []

    def walk(a, b):
        p = [a, b]
        used.add((a, b))
        used.add((b, a))
        while not node[b]:
            nx = [j for j in nb[b] if j != p[-2]]
            if not nx:
                break
            c = nx[0]
            if (b, c) in used:
                break
            used.add((b, c))
            used.add((c, b))
            p.append(c)
            b = c
            if c == p[0]:
                break
        return p
    for i in np.nonzero(node)[0]:
        for j in nb[i]:
            if (int(i), j) not in used:
                paths.append(walk(int(i), j))
    for i in np.nonzero(~node)[0]:
        for j in nb[i]:
            if (int(i), j) not in used:
                paths.append(walk(int(i), j))
    return [np.stack([xs[p], ys[p]], 1).astype(np.float32) for p in paths], node, idx


def _deg(sk, p):
    y, x = int(p[1]), int(p[0])
    return int(sk[max(y - 1, 0):y + 2, max(x - 1, 0):x + 2].sum()) - 1


def _straight(p, tol):
    c = p.mean(0)
    u, s_, vt = np.linalg.svd(p - c, full_matrices=False)
    d = vt[0]
    t = (p - c) @ d
    off = np.abs((p - c) @ vt[1])
    if off.max() > tol:
        return None
    return np.array([c + d * t.min(), c + d * t.max()]) if t[0] <= t[-1] else np.array([c + d * t.max(), c + d * t.min()])


def build(src_png, cache=None, verbose=True):
    if cache:
        fs = [os.path.join(cache, n + ".npy") for n in ("ex_lines", "ex_rivets", "ex_panels")]
        if all(os.path.exists(f) and os.path.getmtime(f) > max(os.path.getmtime(src_png), os.path.getmtime(__file__)) for f in fs):
            return dict(lines=fs[0], rivets=fs[1], panels=fs[2], K=K, KP=KP)
    src = np.asarray(Image.open(src_png).convert("RGB")).astype(np.float32) / 255
    H, W = src.shape[:2]
    lum, sat = src.mean(2), src.max(2) - src.min(2)
    old = cv2.dilate(((lum < 0.27) | (sat > 0.20)).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    bh = cv2.morphologyEx(lum, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    bh = np.clip(bh / 0.10, 0, 1) * (1 - old)

    n, lab, st, cen = cv2.connectedComponentsWithStats((bh > 0.20).astype(np.uint8), connectivity=8)
    small = (st[:, cv2.CC_STAT_AREA] <= 6) & (st[:, cv2.CC_STAT_WIDTH] <= 3) & (st[:, cv2.CC_STAT_HEIGHT] <= 3)
    small[0] = False
    dots = cen[small]
    bh_l = bh * (~small[lab])

    up = cv2.resize(bh_l, (W * KS, H * KS), interpolation=cv2.INTER_CUBIC)
    strong = (up > 0.34).astype(np.uint8)
    weak = (up > 0.15).astype(np.uint8)
    n2, lab2 = cv2.connectedComponents(weak, connectivity=8)
    ok = np.zeros(n2, bool)
    ok[np.unique(lab2[strong > 0])] = True
    ok[0] = False
    m = ok[lab2]
    sk = cv2.ximgproc.thinning(m.astype(np.uint8) * 255) > 0
    for _ in range(3):
        paths, node, idx = _trace(sk)
        cut = 0
        for p_ in paths:
            if len(p_) > 3.4 * KS or len(p_) < 2:
                continue
            a, b = idx[int(p_[0, 1]), int(p_[0, 0])], idx[int(p_[-1, 1]), int(p_[-1, 0])]
            da, db = _deg(sk, p_[0]), _deg(sk, p_[-1])
            if (da == 1 and db >= 3) or (db == 1 and da >= 3):
                q_ = p_[:-1] if db >= 3 else p_[1:]
                sk[q_[:, 1].astype(int), q_[:, 0].astype(int)] = False
                cut += 1
        if cut == 0:
            break
        sk = cv2.ximgproc.thinning(sk.astype(np.uint8) * 255) > 0
    paths, node, idx = _trace(sk)
    if verbose:
        print("   lines: %d skeleton pixels, %d paths, %d source fastener dots" % (int(sk.sum()), len(paths), len(dots)))

    ncs, labs = cv2.connectedComponents(sk.astype(np.uint8), connectivity=8)
    comp = [int(labs[int(p[0, 1]), int(p[0, 0])]) for p in paths]
    by = {}
    for p, c in zip(paths, comp):
        by.setdefault(c, []).append(p)
    out = []
    dropped = 0
    for c, ps in by.items():
        allp = np.concatenate(ps)
        w_, h_ = np.ptp(allp[:, 0]) / KS, np.ptp(allp[:, 1]) / KS
        length = sum(len(p) for p in ps) / KS
        big = max(w_, h_)
        if length < 1.6:
            continue
        if big <= 14.0:
            straight = len(ps) == 1 and length <= 1.25 * math.hypot(w_, h_) + 1.0
            loop = len(ps) == 1 and np.hypot(*(ps[0][0] - ps[0][-1])) <= 1.5 and big >= 4.5 and min(w_, h_) >= 0.6 * big
            if not (straight or loop):
                dropped += 1
                continue
        elif big <= 20.0 and not any(len(p) > 8 and np.hypot(*(p[0] - p[-1])) <= 1.5 for p in ps) and not (len(ps) == 1 and length <= 1.1 * math.hypot(w_, h_) + 1.0):
            dropped += 1
            continue
        elif big <= 24.0 and len(ps) >= 3 and length > 2.0 * math.hypot(w_, h_):
            dropped += 1
            continue
        for p in ps:
            if len(p) < 2:
                continue
            closed = len(p) > 8 and np.hypot(*(p[0] - p[-1])) <= 1.5
            q = None if closed else _straight(p, 0.85 * KS)
            if q is None:
                q = _round(_dp(p, 0.55 * KS), closed)
            if len(q) < 2 or (len(q) == 2 and np.hypot(*(q[0] - q[1])) < 1.2 * KS and not closed):
                continue
            out.append(((q + 0.5) * (K / KS), closed))
    if verbose:
        print("   lines: %d polylines kept, %d small shapes (lettering) dropped" % (len(out), dropped))

    lines = np.zeros((H * K, W * K), np.uint8)
    SH = 4
    for q, closed in out:
        cv2.polylines(lines, [np.round(q * (1 << SH)).astype(np.int32)], closed, 255, 2, cv2.LINE_AA, SH)
    rivets = np.zeros((H * K, W * K), np.uint8)
    r_px = 2.6
    for cx, cy in dots:
        cv2.circle(rivets, (int(round((cx + 0.5) * K * 16)), int(round((cy + 0.5) * K * 16))), int(r_px * 16), 255, -1, cv2.LINE_AA, 4)
    near_src = cv2.dilate(cv2.resize((bh > 0.20).astype(np.uint8) * small[lab].astype(np.uint8), (W, H)), np.ones((7, 7), np.uint8))
    off, pitch = 1.55 * K, 3.4 * K
    added = 0
    for q, closed in out:
        seg = np.diff(q, axis=0)
        sl = np.hypot(seg[:, 0], seg[:, 1])
        total = float(sl.sum())
        if total < 9 * K:
            continue
        cum = np.concatenate([[0], np.cumsum(sl)])
        for s in np.arange(pitch * 0.5, total, pitch):
            i = min(int(np.searchsorted(cum, s)) - 1, len(seg) - 1)
            if sl[i] < 1e-6:
                continue
            t = seg[i] / sl[i]
            p = q[i] + t * (s - cum[i])
            nrm = np.array([-t[1], t[0]])
            for sg in (1, -1):
                c = p + nrm * off * sg
                xi, yi = int(c[0] / K), int(c[1] / K)
                if not (0 <= xi < W and 0 <= yi < H) or near_src[yi, xi] or old[yi, xi]:
                    continue
                if lines[int(c[1]), int(c[0])] > 40:
                    continue
                cv2.circle(rivets, (int(round(c[0] * 16)), int(round(c[1] * 16))), int(r_px * 0.85 * 16), 200, -1, cv2.LINE_AA, 4)
                added += 1
    if verbose:
        print("   fasteners: %d from the source, %d added beside panel edges" % (len(dots), added))
    rivets[lines > 60] = 0

    lp = cv2.resize(lines, (W * KP, H * KP), interpolation=cv2.INTER_AREA)
    lp = cv2.dilate((lp > 40).astype(np.uint8), np.ones((2, 2), np.uint8))
    npan, panels = cv2.connectedComponents((lp == 0).astype(np.uint8), connectivity=4)
    assert npan < 65000
    if verbose:
        print("   panels: %d areas" % npan)
    panels = panels.astype(np.uint16)
    if cache:
        os.makedirs(cache, exist_ok=True)
        for f, arr in zip(fs, (lines, rivets, panels)):
            np.save(f, arr)
        return dict(lines=fs[0], rivets=fs[1], panels=fs[2], K=K, KP=KP)
    return dict(lines=lines, rivets=rivets, panels=panels, K=K, KP=KP)


if __name__ == "__main__":
    import sys
    r = build(sys.argv[1])
    x0, y0, w = (int(v) for v in sys.argv[3:6]) if len(sys.argv) > 5 else (330, 900, 470)
    c = r["lines"][y0 * K:(y0 + w) * K, x0 * K:(x0 + w) * K]
    v = r["rivets"][y0 * K:(y0 + w) * K, x0 * K:(x0 + w) * K]
    img = np.full(c.shape + (3,), 40, np.uint8)
    img[..., 0] = np.clip(40 + c.astype(int), 0, 255)
    img[..., 1] = np.clip(40 + c.astype(int) + v.astype(int) // 2, 0, 255)
    img[..., 2] = np.clip(40 + c.astype(int), 0, 255)
    Image.fromarray(img).resize((1600, 1600), Image.LANCZOS).save(sys.argv[2])
