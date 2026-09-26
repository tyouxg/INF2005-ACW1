"""Before/after comparison of a cover image and its stego image.

PSNR puts a number on how much LSB embedding changed the image, and the
difference map shows where the payload landed (start location + wrap-around).
"""

import math

import numpy as np
from PIL import Image

from .media import Cover


def _pixels(cover: Cover) -> np.ndarray:
    if cover.kind != "image":
        raise ValueError("Image comparison needs image covers")
    p = cover.params
    return cover.data.reshape(p["height"], p["width"], 3)


def _check_same_size(a: Cover, b: Cover) -> None:
    if (a.params["width"], a.params["height"]) != (b.params["width"], b.params["height"]):
        raise ValueError("Cover and stego images must be the same size")


def mse(cover: Cover, stego: Cover) -> float:
    """Mean squared error over every RGB byte."""
    _check_same_size(cover, stego)
    diff = _pixels(cover).astype(np.int32) - _pixels(stego).astype(np.int32)
    return float(np.mean(diff ** 2))


def psnr(cover: Cover, stego: Cover) -> float:
    """Peak signal-to-noise ratio in dB (higher = less visible). inf if identical.

    Rough guide: above ~40 dB the change is invisible to the eye, below ~30 dB
    it usually starts to show.
    """
    err = mse(cover, stego)
    if err == 0:
        return math.inf
    return 10 * math.log10(255 ** 2 / err)


def changed_pixels(cover: Cover, stego: Cover) -> int:
    """Number of pixels where at least one of R, G, B was changed."""
    _check_same_size(cover, stego)
    return int(np.any(_pixels(cover) != _pixels(stego), axis=2).sum())


def diff_map(cover: Cover, stego: Cover) -> Image.Image:
    """Dimmed grayscale copy of the cover with every changed pixel painted red."""
    _check_same_size(cover, stego)
    a, b = _pixels(cover), _pixels(stego)
    gray = (a.mean(axis=2) * 0.4).astype(np.uint8)
    out = np.stack([gray, gray, gray], axis=2)
    out[np.any(a != b, axis=2)] = (255, 0, 0)
    return Image.fromarray(out, "RGB")


def compare(cover: Cover, stego: Cover) -> dict:
    total = cover.params["width"] * cover.params["height"]
    changed = changed_pixels(cover, stego)
    return {
        "mse": mse(cover, stego),
        "psnr_db": psnr(cover, stego),
        "changed_pixels": changed,
        "total_pixels": total,
        "percent_changed": 100 * changed / total,
    }
