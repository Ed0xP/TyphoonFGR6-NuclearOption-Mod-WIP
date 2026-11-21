import os
import sys

import cv2
import numpy as np
from PIL import Image

ST = sys.argv[1]
Image.MAX_IMAGE_PIXELS = None


def noise(shape, sig, seed, ax=None):
    r = np.random.default_rng(seed).standard_normal((shape[0] // 4 + 1, shape[1] // 4 + 1)).astype(np.float32)
    r = cv2.GaussianBlur(r, (0, 0), sigmaX=(ax or (sig, sig))[0] / 4, sigmaY=(ax or (sig, sig))[1] / 4)
    r = cv2.resize(r, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    return (r - r.mean()) / max(float(r.std()), 1e-6)


for name in ("ckconr", "ckconl", "ckgear", "ckdwp", "cknve"):
    bp = os.path.join(ST, name + "_base.png")
    if not os.path.exists(bp):
        continue
    b = np.asarray(Image.open(bp).convert("RGB")).astype(np.float32) / 255
    lum = b.mean(2)
    sat = b.max(2) - b.min(2)
    plate = cv2.GaussianBlur(((lum > 0.30) & (sat < 0.10)).astype(np.float32), (0, 0), 1.0)
    dark = cv2.GaussianBlur((lum < 0.22).astype(np.float32), (0, 0), 5)
    dark2 = cv2.GaussianBlur((lum < 0.22).astype(np.float32), (0, 0), 13)
    sh = lum.shape
    tone = 0.90 - 0.020 * noise(sh, 260, 1) - 0.008 * noise(sh, 40, 2)
    grime = np.clip(0.60 * dark + 0.20 * dark2, 0, 1) * (0.80 + 0.20 * noise(sh, 14, 3))
    tone *= 1 - 0.22 * grime
    st = noise(sh, 3, 4, ax=(22, 1.2)) + noise(sh, 3, 5, ax=(1.2, 22))
    scuff = np.clip((st - 2.45) * 0.9, 0, 1)
    chips = np.clip((noise(sh, 1.6, 6) - 2.3) * 1.5, 0, 1) * np.clip(dark * 2.5, 0, 1)
    out = b * tone[..., None]
    out[..., 2] *= 0.975
    out += (np.array([0.50, 0.51, 0.50], np.float32) - out) * (0.30 * scuff + 0.70 * chips)[..., None]
    a = plate[..., None]
    Image.fromarray((np.clip(b * (1 - a) + out * a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(bp)
    print("aged", name)
