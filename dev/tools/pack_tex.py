import os
import struct
import sys
import time

import numpy as np
from PIL import Image

import etcpak

Image.MAX_IMAGE_PIXELS = None
BC7 = 25


def to_lin(a):
    a = a.astype(np.float32) / 255
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def to_srgb(a):
    a = np.clip(a, 0, 1)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055)


def half(a):
    h, w = a.shape[:2]
    h2, w2 = max(h // 2, 1), max(w // 2, 1)
    a = a[:h2 * 2 if h > 1 else 1, :w2 * 2 if w > 1 else 1]
    if h > 1:
        a = (a[0::2] + a[1::2]) * 0.5
    if w > 1:
        a = (a[:, 0::2] + a[:, 1::2]) * 0.5
    return a


def encode(rgba8):
    h, w = rgba8.shape[:2]
    if h % 4 or w % 4:
        p = np.zeros((max(4, (h + 3) // 4 * 4), max(4, (w + 3) // 4 * 4), 4), np.uint8)
        p[:h, :w] = rgba8
        p[h:, :w] = rgba8[-1:, :]
        p[:, w:] = p[:, w - 1:w]
        rgba8 = p
    rgba8 = np.ascontiguousarray(rgba8)
    return etcpak.compress_bc7(rgba8.tobytes(), rgba8.shape[1], rgba8.shape[0])


def pack(png, out):
    t0 = time.time()
    im = Image.open(png)
    colour = png.endswith(("_base.png", "_emit.png"))
    a = np.asarray(im.convert("RGBA"))
    h, w = a.shape[:2]
    assert h % 4 == 0 and w % 4 == 0, "size must be a multiple of 4"
    blobs = []
    cur8 = a
    if colour:
        lin = np.concatenate([to_lin(a[..., :3]), a[..., 3:4].astype(np.float32) / 255], axis=2)
    else:
        lin = a.astype(np.float32) / 255
    del a
    n = 0
    while True:
        blobs.append(encode(cur8[::-1]))
        n += 1
        if lin.shape[0] == 1 and lin.shape[1] == 1:
            break
        lin = half(lin)
        if colour:
            cur8 = (np.concatenate([to_srgb(lin[..., :3]), lin[..., 3:4]], axis=2) * 255 + 0.5).astype(np.uint8)
        else:
            cur8 = (np.clip(lin, 0, 1) * 255 + 0.5).astype(np.uint8)
    data = b"".join(blobs)
    with open(out, "wb") as f:
        f.write(struct.pack("<6i", 0x31545954, w, h, BC7, n, len(data)))
        f.write(data)
    print("   %s: %dx%d, %d mips, %.1f MB, %.0f s" % (os.path.basename(out), w, h, n, len(data) / 1e6, time.time() - t0))


def check(png, tex):
    import texture2ddecoder
    with open(tex, "rb") as f:
        magic, w, h, fmt, mips, ln = struct.unpack("<6i", f.read(24))
        raw = f.read()
    assert magic == 0x31545954 and fmt == BC7 and len(raw) == ln
    exp = sum(max(1, ((w >> i) + 3) // 4) * max(1, ((h >> i) + 3) // 4) * 16 for i in range(mips))
    assert exp == ln, (exp, ln)
    n0 = (w // 4) * (h // 4) * 16
    dec = np.frombuffer(texture2ddecoder.decode_bc7(raw[:n0], w, h), np.uint8).reshape(h, w, 4)[::-1, :, [2, 1, 0, 3]]
    ref = np.asarray(Image.open(png).convert("RGBA"))
    e = dec[..., :3].astype(np.int16) - ref[..., :3]
    return float(np.sqrt((e.astype(np.float32) ** 2).mean())), int(np.abs(e).max())


if __name__ == "__main__":
    st = sys.argv[1]
    for name in sys.argv[2:]:
        png = os.path.join(st, name)
        tex = os.path.splitext(png)[0] + ".tex"
        pack(png, tex)
        if os.environ.get("TEX_CHECK"):
            print("      check: rms error %.2f, worst %d (of 255)" % check(png, tex))
