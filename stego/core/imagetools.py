"""Image quality numbers for cover vs stego (MSE, PSNR).

visual.py draws where the payload went; this puts a number on how much the
image changed, which is what makes the k (LSB count) trade-off measurable.
"""

import math

import numpy as np

from .media import Cover
from .visual import changed_pixels, image_rgb


def _check_pair(cover: Cover, stego: Cover) -> None:
    if cover.kind != "image" or stego.kind != "image":
        raise ValueError("Image comparison needs two images")
    if (cover.params["width"], cover.params["height"]) != (stego.params["width"], stego.params["height"]):
        raise ValueError("Cover and stego images must be the same size")


def mse(cover: Cover, stego: Cover) -> float:
    """Mean squared error over every RGB byte."""
    _check_pair(cover, stego)
    diff = image_rgb(cover).astype(np.int32) - image_rgb(stego).astype(np.int32)
    return float(np.mean(diff ** 2))


def psnr(cover: Cover, stego: Cover) -> float:
    """Peak signal-to-noise ratio in dB (higher = less visible). inf if identical.

    Rough guide: above ~40 dB the change is invisible to the eye, below ~30 dB
    it usually starts to show. It averages over the whole image, so a small
    payload at high k can still score well while its own region is visibly noisy.
    """
    err = mse(cover, stego)
    if err == 0:
        return math.inf
    return 10 * math.log10(255 ** 2 / err)


def compare(cover: Cover, stego: Cover) -> dict:
    _check_pair(cover, stego)
    total = cover.params["width"] * cover.params["height"]
    changed = changed_pixels(cover, stego)
    return {
        "mse": mse(cover, stego),
        "psnr_db": psnr(cover, stego),
        "changed_pixels": changed,
        "total_pixels": total,
        "percent_changed": 100 * changed / total,
    }
