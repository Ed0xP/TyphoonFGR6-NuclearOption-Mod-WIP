import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

import ckkeys

TEX_W, TEX_H = 2828, 4138
EYE = np.array([0.0, 6.5, 1.16])


def _font(name, fallback):
    try:
        ImageFont.truetype(name, 10)
        return name
    except OSError:
        return fallback


FONT = _font("DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf")
MONO = _font("DejaVuSansMono-Bold.ttf", FONT)


def _txt(s):
    return "" if s == "-" else s.replace("_", " ")


def parse(path):
    items = []
    for raw in open(path, encoding="utf-8"):
        t = raw.split("#")[0].split()
        if not t:
            continue
        k = t[0]
        f = lambda i: float(t[i])
        if k == "key":
            items.append(dict(kind="key", x=f(1), y=f(2), w=f(3), h=f(4), text=_txt(t[5]) if len(t) > 5 else "",
                              style=t[6] if len(t) > 6 else "led", ang=float(t[7]) if len(t) > 7 else 0.0))
        elif k == "grid":
            x0, y0, x1, y1 = f(1), f(2), f(3), f(4)
            nx, ny = int(t[5]), int(t[6])
            legends = " ".join(t[10:]).split(",") if len(t) > 10 else []
            i = 0
            for iy in range(ny):
                for ix in range(nx):
                    x = x0 + (x1 - x0) * (ix / (nx - 1) if nx > 1 else 0)
                    y = y0 + (y1 - y0) * (iy / (ny - 1) if ny > 1 else 0)
                    items.append(dict(kind="key", x=x, y=y, w=f(7), h=f(8), style=t[9], ang=0.0,
                                      text=_txt(legends[i].strip()) if i < len(legends) else ""))
                    i += 1
        elif k == "lcd":
            items.append(dict(kind="lcd", x=f(1), y=f(2), w=f(3), h=f(4), text=_txt(t[5]), colour=t[6] if len(t) > 6 else "green"))
        elif k == "text":
            items.append(dict(kind="text", x=f(1), y=f(2), cap=f(3), text=_txt(t[4]), colour=t[5] if len(t) > 5 else "green"))
        elif k == "label":
            items.append(dict(kind="label", x=f(1), y=f(2), cap=f(3), text=_txt(t[4])))
        elif k == "lamp":
            items.append(dict(kind="lamp", x=f(1), y=f(2), w=f(3), h=f(4), colour=t[5]))
        elif k == "disc":
            items.append(dict(kind="disc", x=f(1), y=f(2), d=f(3), sub=t[4]))
        elif k == "vent":
            items.append(dict(kind="vent", x=f(1), y=f(2), d=f(3)))
        elif k == "plate":
            items.append(dict(kind="plate", x=f(1), y=f(2), w=f(3), h=f(4), colour=t[5] if len(t) > 5 else "black"))
        elif k == "blank":
            items.append(dict(kind="blank", x=f(1), y=f(2), w=f(3), h=f(4)))
        elif k == "line":
            items.append(dict(kind="line", x=(f(1) + f(3)) / 2, y=(f(2) + f(4)) / 2, x0=f(1), y0=f(2), x1=f(3), y1=f(4), width=f(5)))
        elif k == "slider":
            items.append(dict(kind="slider", x=f(1), y=f(2), w=f(3), h=f(4)))
        elif k == "paint":
            items.append(dict(kind="paint", x=f(1), y=f(2), colour=t[3]))
        else:
            raise ValueError("cockpit_panel.txt: unknown item '%s'" % k)
    return items


class Atlas:

    def __init__(self, P, UV):
        self.P = np.asarray(P, np.float64)
        self.px = np.asarray(UV)[..., 0] * TEX_W
        self.py = (1 - np.asarray(UV)[..., 1]) * TEX_H

    def at(self, x, y):
        a = np.stack([self.px[:, 0], self.py[:, 0]], 1); b = np.stack([self.px[:, 1], self.py[:, 1]], 1); c = np.stack([self.px[:, 2], self.py[:, 2]], 1)
        d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
        with np.errstate(divide="ignore", invalid="ignore"):
            w1 = ((b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])) / d
            w2 = ((c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])) / d
        w3 = 1 - w1 - w2
        ok = np.nonzero((np.abs(d) > 1e-9) & (w1 >= -1e-6) & (w2 >= -1e-6) & (w3 >= -1e-6))[0]
        if len(ok) == 0:
            return None
        t = ok[0]
        P = self.P[t]
        pos = w1[t] * P[0] + w2[t] * P[1] + w3[t] * P[2]
        n = np.cross(P[1] - P[0], P[2] - P[0]); n /= np.linalg.norm(n)
        if n @ (EYE - pos) < 0:
            n = -n
        E = np.array([P[1] - P[0], P[2] - P[0]]).T
        A = np.array([b[t] - a[t], c[t] - a[t]]).T
        J = E @ np.linalg.inv(A)
        return pos, n, J


def resolve(items, atlas, log=print):
    out = []
    for it in items:
        hit = atlas.at(it["x"], it["y"])
        if hit is None:
            log("  panel item not on the model: %s at %.0f, %.0f" % (it["kind"], it["x"], it["y"]))
            continue
        pos, n, J = hit
        jx, jy = J[:, 0], J[:, 1]
        scale = math.sqrt(np.linalg.norm(jx) * np.linalg.norm(jy))
        up = np.array([0, 0, 1.0]) - n * n[2]
        if np.linalg.norm(up) < 0.2:
            up = np.array([0, 1.0, 0]) - n * n[1]
        up /= np.linalg.norm(up)
        rs = np.cross(up, n)
        ang = math.radians(it.get("ang", 0.0))
        a = jx * math.cos(ang) + jy * math.sin(ang)
        b = -jx * math.sin(ang) + jy * math.cos(ang)
        la, lb = np.linalg.norm(a), np.linalg.norm(b)
        ah, bh = a / la, b / lb
        w, h = it.get("w", 0.0), it.get("h", 0.0)
        if abs(ah @ rs) >= abs(bh @ rs):
            r = ah * (1 if ah @ rs >= 0 else -1); wr, hu = w * la, h * lb
        else:
            r = bh * (1 if bh @ rs >= 0 else -1); wr, hu = h * lb, w * la
        r = r - n * (r @ n); r /= np.linalg.norm(r)
        o = dict(it)
        o.update(pos=pos, n=n, r=r, u=np.cross(n, r), wr=wr, hu=hu, scale=scale)
        if "d" in it:
            o["d"] = it["d"] * scale
        if "cap" in it:
            o["cap"] = it["cap"] * scale
        if it["kind"] == "line":
            h0, h1 = atlas.at(it["x0"], it["y0"]), atlas.at(it["x1"], it["y1"])
            if h0 is None or h1 is None:
                continue
            o["p0"], o["p1"], o["width"] = h0[0], h1[0], it["width"] * scale
        out.append(o)
    return out


def read_screens(path):
    scr = {}
    for line in open(path):
        t = line.split()
        if t and t[0] == "screen" and len(t) >= 14:
            v = [float(x) for x in t[2:14]]
            scr[t[1]] = np.array([[v[i], v[i + 2], v[i + 1]] for i in (0, 3, 6, 9)])
    return scr


def unit_boxes(items, screens, margin=0.0045):
    fr = {}
    for name, q in screens.items():
        if not name.startswith("mfd_"):
            continue
        c0 = q.mean(0)
        ex, ey = q[1] - q[0], q[3] - q[0]
        n = np.cross(ex, ey); n /= np.linalg.norm(n)
        if n @ (EYE - c0) < 0:
            n = -n
        hw, hh = np.linalg.norm(ex) / 2, np.linalg.norm(ey) / 2
        fr[name] = [c0, ex / (2 * hw), -ey / (2 * hh), n, hw, hh, [-hw, hw, -hh, hh]]
    for it in items:
        if it["kind"] != "key":
            continue
        best = None
        for name, (c0, r, u, n, hw, hh, bx) in fr.items():
            d = np.asarray(it["pos"], float) - c0
            a, b, w = d @ r, d @ u, d @ n
            dist = math.hypot(max(abs(a) - hw, 0), max(abs(b) - hh, 0))
            if abs(w) < 0.03 and dist < 0.045 and (best is None or dist < best[0]):
                best = (dist, name, a, b)
        if best:
            c0, r, u, n, hw, hh, bx = fr[best[1]]
            ka = abs(np.asarray(it["r"]) @ r) * it["wr"] / 2 + abs(np.asarray(it["u"]) @ r) * it["hu"] / 2
            kb = abs(np.asarray(it["r"]) @ u) * it["wr"] / 2 + abs(np.asarray(it["u"]) @ u) * it["hu"] / 2
            bx[0], bx[1] = min(bx[0], best[2] - ka), max(bx[1], best[2] + ka)
            bx[2], bx[3] = min(bx[2], best[3] - kb), max(bx[3], best[3] + kb)
    out = {}
    for name, (c0, r, u, n, hw, hh, bx) in fr.items():
        cen = c0 + r * (bx[0] + bx[1]) / 2 + u * (bx[2] + bx[3]) / 2
        out[name] = (cen, r, u, n, (bx[1] - bx[0]) / 2 + margin, (bx[3] - bx[2]) / 2 + margin)
    return out


COL = {
    "light": (0.405, 0.418, 0.428), "dark": (0.200, 0.206, 0.215), "black": (0.036, 0.038, 0.042),
    "key": (0.050, 0.053, 0.058), "keyrim": (0.135, 0.140, 0.148), "pocket": (0.020, 0.021, 0.023),
    "glass": (0.012, 0.020, 0.017), "white": (0.86, 0.87, 0.85), "green": (0.42, 1.0, 0.50), "amber": (1.0, 0.72, 0.18),
    "red": (0.55, 0.06, 0.05), "lampgreen": (0.10, 0.55, 0.32), "screw": (0.34, 0.35, 0.36), "grey": (0.30, 0.31, 0.32),
    "yellow": (0.92, 0.72, 0.05), "blue": (0.16, 0.30, 0.95), "panel": (0.385, 0.395, 0.405),
}


def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def sd_rrect(px, py, hw, hh, rad):
    rad = min(rad, hw, hh)
    qx, qy = np.abs(px) - (hw - rad), np.abs(py) - (hh - rad)
    return np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - rad


DECALS = False
LABELS = []
KEY_SRC = None
UNIT_FLOOR = 0.0035
PANEL_AGE = 1.0


class Painter:
    def __init__(self, pos, cover, density, nrm=None):
        self._cur, self._pn, self._pend = None, None, None
        self.pos, self.cover, self.den, self.nrm = pos, cover, float(density), nrm
        self.H, self.W = cover.shape
        self.base = np.zeros((self.H, self.W, 3), np.float32)
        self.emit = np.zeros((self.H, self.W, 3), np.float32)
        self.height = np.full((self.H, self.W), 0.5, np.float32)
        self.smooth = np.full((self.H, self.W), 0.3, np.float32)
        self.S8 = 8
        self.pos8 = pos[::self.S8, ::self.S8]
        self.cov8 = cover[::self.S8, ::self.S8]
        self._glyph = {}

    def local(self, it, rad):
        p0 = np.asarray(it["pos"], np.float32)
        d8 = np.linalg.norm(self.pos8 - p0, axis=2)
        near = self.cov8 & (d8 < rad + 0.004)
        if not near.any():
            return None
        ys, xs = np.nonzero(near)
        S = self.S8
        y0, y1 = max(ys.min() * S - S, 0), min(ys.max() * S + 2 * S, self.H)
        x0, x1 = max(xs.min() * S - S, 0), min(xs.max() * S + 2 * S, self.W)
        sub = (slice(y0, y1), slice(x0, x1))
        d = self.pos[sub] - p0
        pr = d @ np.asarray(it["r"], np.float32)
        pu = d @ np.asarray(it["u"], np.float32)
        pn = d @ np.asarray(it["n"], np.float32)
        m = self.cover[sub] & (np.abs(pn) < 0.012)
        self._cur, self._pn = it, pn
        if self.nrm is not None:
            m &= (self.nrm[sub].astype(np.float32) @ np.asarray(it["n"], np.float32)) > 0.80 * 127
        return sub, pr, pu, m

    def cov(self, sd):
        return np.clip(0.5 - sd * self.den, 0, 1)

    def put(self, sub, c, col=None, emit=None, h=None, sm=None):
        c = c.astype(np.float32)
        pend, self._pend = self._pend, None
        if pend is not None and col is not None and self._cur is not None:
            it = self._cur
            on = c > 0.35
            lift = float(np.median(self._pn[on])) if on.any() else 0.0
            LABELS.append({"pos": [float(v) for v in np.asarray(it["pos"], np.float32) + np.asarray(it["n"], np.float32) * lift],
                           "r": [float(v) for v in it["r"]], "u": [float(v) for v in it["u"]], "n": [float(v) for v in it["n"]],
                           "text": pend["text"], "cap": float(pend["cap"]), "font": pend["font"], "spacing": float(pend["spacing"]),
                           "col": [float(v) for v in np.asarray(col, np.float32).reshape(-1)[:3]], "seen": bool(on.any())})
            if it.get("kind") == "lcd":
                LABELS[-1]["lcd"] = [float(it["wr"]), float(it["hu"])]
            if DECALS:
                col, h = None, None
                if emit is None:
                    return
                if KEY_SRC and (ckkeys.key_state(dict(LABELS[-1], src=KEY_SRC)) or ("lcd" in LABELS[-1] and pend["text"].startswith("WPT"))):
                    return
        if col is not None:
            self.base[sub] += (np.asarray(col, np.float32) - self.base[sub]) * c[..., None]
            if emit is None:
                self.emit[sub] *= (1 - c[..., None])
        if emit is not None:
            self.emit[sub] += (np.asarray(emit, np.float32) - self.emit[sub]) * c[..., None]
        if h is not None:
            self.height[sub] += (h - self.height[sub]) * c
        if sm is not None:
            self.smooth[sub] += (sm - self.smooth[sub]) * c

    def text_cov(self, pr, pu, text, cap, font=FONT, spacing=1.45):
        self._pend = {"text": text, "cap": cap, "font": font, "spacing": spacing}
        lines = text.split("|")
        ppm = self.den * 2.0
        fpx = max(int(round(cap * ppm / 0.729)), 6)
        key = (text, fpx, font)
        if key not in self._glyph:
            f = ImageFont.truetype(font, fpx)
            lh = cap * ppm * spacing
            wmax = max(max(f.getlength(ln) for ln in lines), 1)
            Wp, Hp = int(wmax + 8), int(lh * len(lines) + 8)
            im = Image.new("L", (Wp, Hp), 0)
            dr = ImageDraw.Draw(im)
            for i, ln in enumerate(lines):
                yc = Hp / 2 + (i - (len(lines) - 1) / 2) * lh
                dr.text((Wp / 2, yc), ln, fill=255, font=f, anchor="mm")
            self._glyph[key] = np.asarray(im).astype(np.float32) / 255
        g = self._glyph[key]
        ix = pr * ppm + g.shape[1] / 2 - 0.5
        iy = -pu * ppm + g.shape[0] / 2 - 0.5
        return ndi.map_coordinates(g, [iy, ix], order=1, mode="constant", cval=0.0)

    @staticmethod
    def fit_cap(text, wr, hu, font=FONT, fill_w=0.84, fill_h=0.80, spacing=1.45):
        lines = text.split("|")
        f = ImageFont.truetype(font, 100)
        wmax = max(max(f.getlength(ln) for ln in lines), 1) / 72.9
        return min(wr * fill_w / wmax, hu * fill_h / (1 + spacing * (len(lines) - 1)))

    def paint_base(self, old, footprint, screens, paints=(), log=print, units=None):
        lum = old.mean(2)
        valid = self.cover & ~footprint
        idx = ndi.distance_transform_edt(~valid, return_distances=False, return_indices=True)
        lf = lum[idx[0], idx[1]]
        del idx
        L = ndi.gaussian_filter(lf, self.den * 0.0011)
        v = L[self.cover]
        log("panel paint: luminance percentiles 5/25/50/75/95: " + " ".join("%.2f" % q for q in np.percentile(v, [5, 25, 50, 75, 95])))
        t_dark, t_light = 0.15, 0.39
        rad = max(int(self.den * 0.0012), 2)
        yy, xx = np.mgrid[-rad:rad + 1, -rad:rad + 1]
        ball = (yy * yy + xx * xx) <= rad * rad
        min_px = (self.den * 0.006) ** 2

        def tidy(mask):
            mask = ndi.binary_opening(ndi.binary_closing(mask, ball), ball)
            for inv in (False, True):
                mm = ~mask if inv else mask
                lab, n = ndi.label(mm)
                if n:
                    sizes = ndi.sum(np.ones(mm.shape, np.float32), lab, index=np.arange(1, n + 1))
                    small = np.zeros(n + 1, bool); small[1:] = sizes < min_px
                    mm = mm & ~small[lab]
                mask = ~mm if inv else mm
            return mask
        m_light = tidy((L > t_light) & self.cover)
        m_dark = tidy((L > t_dark) & self.cover) | m_light
        lab, n = ndi.label(self.cover)
        m_panel = np.zeros_like(m_light)
        for it in paints:
            p0 = np.asarray(it["pos"], np.float32)
            d8 = np.linalg.norm(self.pos8 - p0, axis=2)
            d8[~self.cov8] = 9
            iy, ix = np.unravel_index(np.argmin(d8), d8.shape)
            if d8[iy, ix] > 0.01:
                continue
            comp = lab[iy * self.S8, ix * self.S8]
            if comp == 0:
                continue
            reg = lab == comp
            if self.nrm is not None:
                reg &= (self.nrm.astype(np.float32) @ np.asarray(it["n"], np.float32)) > 0.9 * 127
            reg &= np.abs((self.pos - p0) @ np.asarray(it["n"], np.float32)) < 0.02
            m_light[reg] = it["colour"] in ("light", "panel")
            m_dark[reg] = it["colour"] in ("light", "dark", "panel")
            m_panel[reg] = it["colour"] == "panel"
        del lab
        c_dark = ndi.gaussian_filter(m_dark.astype(np.float32), 0.8)
        c_light = ndi.gaussian_filter(m_light.astype(np.float32), 0.8)
        c_panel = ndi.gaussian_filter(m_panel.astype(np.float32), 0.8)
        del m_panel
        for name, q in screens.items():
            c0 = q.mean(0)
            ex, ey = q[1] - q[0], q[3] - q[0]
            n = np.cross(ex, ey); n /= np.linalg.norm(n)
            if n @ (EYE - c0) < 0:
                n = -n
            it = dict(pos=c0, r=ex / np.linalg.norm(ex), u=-ey / np.linalg.norm(ey), n=n)
            loc = self.local(it, 0.6 * max(np.linalg.norm(ex), np.linalg.norm(ey)) + 0.01)
            if loc is None:
                continue
            sub, pr, pu, m = loc
            c = self.cov(sd_rrect(pr, pu, np.linalg.norm(ex) / 2 + 0.003, np.linalg.norm(ey) / 2 + 0.003, 0.006)) * m
            c_dark[sub] *= (1 - c)
            c_light[sub] *= (1 - c)
            c_panel[sub] *= (1 - c)
        halo = np.zeros((self.H, self.W), np.float32)
        for name, (cen, r, u, n, hw, hh) in (units or {}).items():
            loc = self.local(dict(pos=cen, r=r, u=u, n=n), math.hypot(hw, hh) + 0.01)
            if loc is None:
                continue
            sub, pr, pu, m = loc
            c = self.cov(sd_rrect(pr, pu, hw, hh, 0.006)) * m
            c_light[sub] *= (1 - c)
            c_panel[sub] *= (1 - c)
            log("panel paint: display unit %s dark floor %.0f x %.0f mm" % (name, hw * 2000, hh * 2000))
            sdh = sd_rrect(pr, pu, hw + 0.0019, hh + 0.0019, 0.007)
            halo[sub] = np.maximum(halo[sub], 0.40 * np.clip(1 - sdh / 0.012, 0, 1) ** 1.6 * m)
        if units:
            g_c = np.array([0.3501, 7.2737, 0.8022]); g_n = np.array([-0.252, -0.934, 0.252])
            g_u = np.array([0.066, 0.243, 0.968]); g_r = np.array([0.966, -0.260, 0.0])
            loc = self.local(dict(pos=g_c + g_r * 0.001 + g_u * 0.0075, r=g_r, u=g_u, n=g_n), 0.095)
            if loc is not None:
                sub, pr, pu, m = loc
                sdh = sd_rrect(pr, pu, 0.0255, 0.0685, 0.006)
                halo[sub] = np.maximum(halo[sub], 0.40 * np.clip(1 - sdh / 0.012, 0, 1) ** 1.6 * m)
        rng = np.random.default_rng(5)
        grain = ndi.gaussian_filter(rng.standard_normal((self.H, self.W)).astype(np.float32), 1.0)
        base = np.empty((self.H, self.W, 3), np.float32)
        for k in range(3):
            base[..., k] = COL["black"][k] + (COL["dark"][k] - COL["black"][k]) * c_dark + (COL["light"][k] - COL["dark"][k]) * c_light
        for k in range(3):
            base[..., k] += (COL["panel"][k] - base[..., k]) * c_panel
        base *= (1 + 0.02 * grain)[..., None]
        base *= (1 - halo)[..., None]
        del halo
        if PANEL_AGE:
            rs = np.random.default_rng(77)
            drift = np.zeros((self.H, self.W), np.float32)
            P3 = np.asarray(self.pos, np.float32)
            for _ in range(6):
                kv = rs.standard_normal(3)
                kv *= (2 * math.pi / rs.uniform(0.10, 0.45)) / np.linalg.norm(kv)
                drift += np.sin(P3 @ kv.astype(np.float32) + np.float32(rs.uniform(0, 6.28)))
            drift /= 2.45
            grime = ndi.gaussian_filter(footprint.astype(np.float32), self.den * 0.0032)
            grime = np.clip(grime * 2.4, 0, 1)
            grime = np.maximum(grime, 0.6 * np.clip(ndi.gaussian_filter(footprint.astype(np.float32), self.den * 0.009) * 2.0, 0, 1))
            w = np.maximum(c_panel, c_light) * self.cover
            base *= (1 + PANEL_AGE * w * (0.065 * drift - 0.26 * grime))[..., None]
            del drift, grime, P3
        self.base = base
        lvl = 0.30 + 0.16 * c_dark + 0.10 * c_light
        self.height = (ndi.gaussian_filter(lvl, 1.6) + 0.008 * grain).astype(np.float32)
        self.smooth = (0.20 + 0.08 * c_dark + 0.05 * c_light).astype(np.float32)
        self.c_light = c_light
        try:
            import panelkit as pk
            ppm = self.den / 1000.0
            bump = np.zeros((self.H, self.W), np.float32)
            pk.paint_finish(self.base, bump, self.smooth, ppm, 61, (c_light * self.cover).astype(np.float32), 0.8, gain=1.2)
            self.height += bump * ppm / 3.0
            del bump
        except Exception as e:
            log("panel paint: finish skipped: %s" % e)

    def footprint(self, items):
        fp = np.zeros((self.H, self.W), bool)
        for it in items:
            k = it["kind"]
            if k in ("key", "lcd", "plate", "lamp", "blank"):
                loc = self.local(it, 0.6 * max(it["wr"], it["hu"]) + 0.004)
                if loc is None:
                    continue
                sub, pr, pu, m = loc
                fp[sub] |= m & (sd_rrect(pr, pu, it["wr"] / 2 + 0.0015, it["hu"] / 2 + 0.0015, 0.001) < 0)
            elif k in ("disc", "vent"):
                R = it["d"] / 2 * (1.5 if k == "vent" else 1.2) + 0.001
                loc = self.local(it, R + 0.002)
                if loc is None:
                    continue
                sub, pr, pu, m = loc
                fp[sub] |= m & (pr * pr + pu * pu < R * R)
            elif k in ("label", "text"):
                loc = self.local(it, it["cap"] * (0.5 * len(it["text"]) + 1))
                if loc is None:
                    continue
                sub, pr, pu, m = loc
                fp[sub] |= m & (np.abs(pu) < it["cap"] * 1.0) & (np.abs(pr) < it["cap"] * (0.45 * len(it["text"]) + 0.5))
            elif k == "line":
                a, b = np.asarray(it["p0"]), np.asarray(it["p1"])
                L = np.linalg.norm(b - a)
                loc = self.local(dict(pos=(a + b) / 2, r=(b - a) / L, u=np.cross(it["n"], (b - a) / L), n=it["n"]), L / 2 + 0.003)
                if loc is None:
                    continue
                sub, pr, pu, m = loc
                fp[sub] |= m & (np.abs(pr) < L / 2 + 0.001) & (np.abs(pu) < it["width"] + 0.001)
        return fp

    def draw(self, it):
        k = it["kind"]
        f = getattr(self, "_" + k, None)
        return f(it) if f else False

    def _plate(self, it):
        loc = self.local(it, 0.6 * max(it["wr"], it["hu"]) + 0.003)
        if loc is None:
            return False
        sub, pr, pu, m = loc
        col = COL.get(it.get("colour", "black"), COL["black"])
        c = self.cov(sd_rrect(pr, pu, it["wr"] / 2, it["hu"] / 2, 0.0008)) * m
        self.put(sub, c, col, h=0.28 if it.get("colour", "black") == "black" else 0.5, sm=0.22)
        return True

    def _key(self, it):
        wr, hu = it["wr"], it["hu"]
        loc = self.local(it, 0.6 * max(wr, hu) + 0.004)
        if loc is None:
            return False
        sub, pr, pu, m = loc
        self.put(sub, self.cov(sd_rrect(pr, pu, wr / 2 + 0.0011, hu / 2 + 0.0011, 0.0016)) * m, COL["pocket"], h=0.26, sm=0.15)
        sd = sd_rrect(pr, pu, wr / 2, hu / 2, 0.0012)
        self.put(sub, self.cov(sd) * m, COL["keyrim"], h=0.62, sm=0.38)
        self.put(sub, self.cov(sd + 0.0006) * m, COL["key"], h=0.64, sm=0.42)
        text, style = it.get("text", ""), it.get("style", "led")
        if style == "blue":
            ww, hh = wr / 2 - 0.0016, hu / 2 - 0.0016
            bl = np.array(COL["blue"], np.float32)
            self.put(sub, self.cov(sd_rrect(pr, pu, ww, hh, 0.0008)) * m, bl * 0.55, emit=bl * 0.55, h=0.62, sm=0.55)
            if text:
                cap = min(hu * 0.40, self.fit_cap(text, wr, hu, FONT, 0.74, 0.5))
                tc = self.text_cov(pr, pu, text, cap, FONT) * m
                w = np.array(COL["white"], np.float32)
                self.put(sub, tc, w, emit=w * 0.75)
            return True
        if text:
            if style == "led":
                ww, hh = wr / 2 - 0.0022, hu / 2 - 0.0022
                g = np.array(COL["green"], np.float32)
                self.put(sub, self.cov(sd_rrect(pr, pu, ww, hh, 0.0006)) * m, COL["glass"], emit=g * 0.10, h=0.60, sm=0.6)
                cap = self.fit_cap(text, 2 * ww, 2 * hh, MONO, 0.95, 0.84, 1.42)
                tc = self.text_cov(pr, pu, text, cap, MONO, 1.42) * m
                self.put(sub, tc, g * 0.80, emit=g * 1.0)
            elif style == "blue":
                pass
            elif style == "green":
                cap = min(hu * 0.46, self.fit_cap(text, wr, hu, FONT, 0.74, 0.5))
                tc = self.text_cov(pr, pu, text, cap, FONT) * m
                g = np.array((0.55, 0.95, 0.35), np.float32)
                self.put(sub, tc, g * 0.8, emit=g * 0.8)
            else:
                cap = min(hu * 0.42, self.fit_cap(text, wr, hu, FONT, 0.80, 0.5))
                tc = self.text_cov(pr, pu, text, cap, FONT) * m
                w = np.array(COL["white"], np.float32)
                self.put(sub, tc, w, emit=w * 0.75)
        return True

    def _lcd(self, it):
        wr, hu = it["wr"], it["hu"]
        loc = self.local(it, 0.6 * max(wr, hu) + 0.004)
        if loc is None:
            return False
        sub, pr, pu, m = loc
        sd = sd_rrect(pr, pu, wr / 2, hu / 2, 0.0009)
        self.put(sub, self.cov(sd - 0.0007) * m, COL["keyrim"], h=0.56, sm=0.3)
        self.put(sub, self.cov(sd) * m, COL["glass"], h=0.40, sm=0.62)
        col = np.array(COL.get(it.get("colour", "green"), COL["green"]), np.float32)
        text = it["text"]
        if it.get("colour") == "blue":
            bl = np.array(COL["blue"], np.float32)
            self.put(sub, self.cov(sd + 0.0004) * m, bl * 0.5, emit=bl * 0.65)
            col = np.array((0.80, 0.92, 1.0), np.float32)
            if not text:
                return True
        cap = self.fit_cap(text, wr, hu, MONO, 0.84, 0.70, 1.5)
        tc = self.text_cov(pr, pu, text, cap, MONO, 1.5) * m
        self.put(sub, tc, col * 0.8, emit=col)
        return True

    def _text(self, it):
        loc = self.local(it, it["cap"] * (0.5 * len(it["text"]) + 1.5))
        if loc is None:
            return False
        sub, pr, pu, m = loc
        col = np.array(COL.get(it.get("colour", "green"), COL["green"]), np.float32)
        tc = self.text_cov(pr, pu, it["text"], it["cap"], MONO) * m
        self.put(sub, tc, col * 0.8, emit=col)
        return True

    def _label(self, it):
        cap = max(it["cap"], 0.0019)
        loc = self.local(it, cap * (0.5 * len(it["text"]) + 1.5))
        if loc is None:
            return False
        sub, pr, pu, m = loc
        tc = self.text_cov(pr, pu, it["text"], cap, FONT) * m
        w = np.array(COL["white"], np.float32)
        self.put(sub, tc, w * 0.92, emit=w * 0.55, h=0.56)
        return True

    def _lamp(self, it):
        loc = self.local(it, 0.6 * max(it["wr"], it["hu"]) + 0.003)
        if loc is None:
            return False
        sub, pr, pu, m = loc
        col = np.array(COL["red"] if it["colour"] == "red" else COL["lampgreen"], np.float32)
        sd = sd_rrect(pr, pu, it["wr"] / 2, it["hu"] / 2, 0.0012)
        self.put(sub, self.cov(sd - 0.0008) * m, COL["pocket"], h=0.4, sm=0.3)
        self.put(sub, self.cov(sd) * m, col, emit=col * 0.22, h=0.6, sm=0.75)
        self.put(sub, self.cov(sd + 0.0012) * m * np.clip(0.5 + pu / max(it["hu"], 1e-4), 0, 1) * 0.35, col * 1.5)
        return True

    def _blank(self, it):
        loc = self.local(it, 0.6 * max(it["wr"], it["hu"]) + 0.003)
        if loc is None:
            return False
        sub, pr, pu, m = loc
        sd = sd_rrect(pr, pu, it["wr"] / 2, it["hu"] / 2, 0.0015)
        self.put(sub, self.cov(sd) * m, COL["pocket"], h=0.30)
        self.put(sub, self.cov(sd + 0.0006) * m, (0.135, 0.140, 0.148), h=0.52, sm=0.3)
        return True

    def _line(self, it):
        a, b = np.asarray(it["p0"]), np.asarray(it["p1"])
        L = np.linalg.norm(b - a)
        r = (b - a) / L
        loc = self.local(dict(pos=(a + b) / 2, r=r, u=np.cross(it["n"], r), n=it["n"]), L / 2 + 0.003)
        if loc is None:
            return False
        sub, pr, pu, m = loc
        w = np.array(COL["white"], np.float32)
        self.put(sub, self.cov(sd_rrect(pr, pu, L / 2, max(it["width"], 0.0007) / 2, 0.0002)) * m, w * 0.9, emit=w * 0.25)
        return True

    def _disc(self, it):
        R = it["d"] / 2
        sub_kind = it["sub"]
        loc = self.local(it, R * 1.4 + 0.003)
        if loc is None:
            return False
        sub, pr, pu, m = loc
        rr = np.sqrt(pr * pr + pu * pu)
        if sub_kind == "dot":
            self.put(sub, self.cov(rr - R * 1.25) * m, COL["keyrim"], h=0.58)
            self.put(sub, self.cov(rr - R) * m, COL["pocket"], h=0.25, sm=0.6)
        elif sub_kind == "screw":
            self.put(sub, self.cov(rr - R * 1.12) * m, COL["pocket"], h=0.40)
            dome = 0.60 + 0.12 * np.clip(1 - (rr / R) ** 2, 0, 1)
            c = self.cov(rr - R) * m
            self.put(sub, c, COL["screw"], sm=0.55)
            self.height[sub] += (dome - self.height[sub]) * c
            a = (hash((round(float(it["x"])), round(float(it["y"])))) % 180) * math.pi / 180
            ca, sa = math.cos(a), math.sin(a)
            for (cx, sx) in ((ca, sa), (-sa, ca)):
                sd = sd_rrect(pr * cx + pu * sx, -pr * sx + pu * cx, R * 0.72, R * 0.14, R * 0.05)
                self.put(sub, self.cov(sd) * m, COL["pocket"], h=0.42)
        elif sub_kind == "knob":
            self.put(sub, self.cov(rr - R * 1.22) * m, COL["pocket"], h=0.34, sm=0.2)
            self.put(sub, self.cov(rr - R * 1.02) * m, COL["key"], h=0.5, sm=0.4)
        elif sub_kind == "gauge":
            self.put(sub, self.cov(rr - R * 1.06) * m, COL["keyrim"], h=0.58, sm=0.35)
            self.put(sub, self.cov(rr - R) * m, COL["glass"], h=0.36, sm=0.8)
            ang = np.arctan2(pu, pr)
            tick = (np.abs(((ang / (2 * math.pi) * 24) % 1) - 0.5) > 0.42) & (rr > R * 0.80) & (rr < R * 0.93)
            w = np.array(COL["white"], np.float32)
            self.put(sub, tick.astype(np.float32) * m, w * 0.8, emit=w * 0.25)
        elif sub_kind == "ring":
            self.put(sub, self.cov(rr - R) * m, COL["keyrim"], h=0.58, sm=0.35)
            self.put(sub, self.cov(rr - R * 0.86) * m, COL["key"], h=0.40, sm=0.3)
            self.put(sub, self.cov(rr - R * 0.30) * m, COL["pocket"], h=0.30)
        elif sub_kind == "yring":
            stripe = (np.floor((pr + pu) / (R * 0.36)) % 2) > 0
            c = self.cov(rr - R) * m
            self.put(sub, c, COL["pocket"], h=0.52, sm=0.35)
            self.put(sub, c * stripe, COL["yellow"])
        return True

    def _vent(self, it):
        R = it["d"] / 2
        loc = self.local(it, R * 1.6 + 0.003)
        if loc is None:
            return False
        sub, pr, pu, m = loc
        rr = np.sqrt(pr * pr + pu * pu)
        body = (0.060, 0.063, 0.068)
        sd = rr - R
        ears = []
        for k in range(4):
            a = math.radians(45 + 90 * k)
            ex, ey = math.cos(a) * R * 1.13, math.sin(a) * R * 1.13
            de = np.sqrt((pr - ex) ** 2 + (pu - ey) ** 2)
            sd = np.minimum(sd, de - R * 0.24)
            ears.append(de)
        self.put(sub, self.cov(sd - 0.0008) * m, COL["pocket"], h=0.36)
        self.put(sub, self.cov(sd) * m, body, h=0.66, sm=0.32)
        for de in ears:
            c = self.cov(de - R * 0.11) * m
            self.put(sub, c, COL["screw"], h=0.74, sm=0.55)
            self.put(sub, self.cov(de - R * 0.035) * m, COL["pocket"], h=0.6)
        self.put(sub, self.cov(rr - R * 0.80) * m, (0.035, 0.037, 0.040), h=0.50, sm=0.25)
        rings = 0.5 + 0.5 * np.cos(rr / (R * 0.80) * math.pi * 9)
        c = self.cov(rr - R * 0.74) * m
        self.height[sub] += (0.40 + 0.14 * rings - self.height[sub]) * c
        self.base[sub] *= (1 - 0.35 * c * (1 - rings))[..., None]
        self.put(sub, self.cov(rr - R * 0.20) * m, body, h=0.62, sm=0.35)
        return True


def paint(pos, cover, old, ao, density, items, screens, nrm=None, log=print):
    p = Painter(pos, cover, density, nrm)
    fp = p.footprint(items)
    p.paint_base(old, fp, screens, [i for i in items if i["kind"] == "paint"], log,
                 None if UNIT_FLOOR is None else unit_boxes(items, screens, UNIT_FLOOR))
    del fp
    order = {"plate": 0, "vent": 0}
    n = {}
    for it in sorted(items, key=lambda i: order.get(i["kind"], 1 if not (i["kind"] == "disc" and i["sub"] in ("gauge", "yring")) else 0)):
        if p.draw(it):
            n[it["kind"]] = n.get(it["kind"], 0) + 1
    log("panel paint: " + ", ".join("%d %s" % (v, k) for k, v in sorted(n.items())))
    shade = (0.55 + 0.45 * ao)[..., None]
    p.base *= shade
    p.smooth *= (0.7 + 0.3 * ao)
    return p.base, p.emit, p.height, p.smooth
