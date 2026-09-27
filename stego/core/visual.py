"""Pictures of where the payload sits, for the GUI difference view (no Qt here)."""

import numpy as np

from .media import Cover


def image_rgb(cover: Cover) -> np.ndarray:
    """The image as an (h, w, 3) array."""
    p = cover.params
    return cover.data.reshape(p["height"], p["width"], -1)[..., :3]


def difference(cover: Cover, stego: Cover) -> np.ndarray:
    """|stego - cover| per channel, stretched so the biggest change is 255.

    A change of 1 is invisible to the eye, so without stretching this would
    look completely black.
    """
    diff = np.abs(image_rgb(stego).astype(np.int16) - image_rgb(cover).astype(np.int16))
    peak = int(diff.max())
    if peak:
        diff = diff * 255 // peak
    return np.ascontiguousarray(diff, dtype=np.uint8)


def lsb_plane(cover: Cover, bit: int = 0) -> np.ndarray:
    """One bit of every RGB byte as black/white. Hidden data shows up as noise."""
    return np.ascontiguousarray(((image_rgb(cover) >> bit) & 1) * 255, dtype=np.uint8)


def changed_pixels(cover: Cover, stego: Cover) -> int:
    return int(np.any(image_rgb(cover) != image_rgb(stego), axis=2).sum())


def frame_cover(cover: Cover, i: int) -> Cover:
    """One frame of a video as an image Cover, so all the image views work on it."""
    p = cover.params
    size = p["width"] * p["height"] * 3
    return Cover("image", cover.data[i * size:(i + 1) * size], 1,
                 {"width": p["width"], "height": p["height"]})


def first_changed_frame(cover: Cover, stego: Cover) -> int:
    """The frame the key-derived start landed in (where the first change is)."""
    changed = np.flatnonzero(cover.data != stego.data)
    size = cover.params["width"] * cover.params["height"] * 3
    return int(changed[0] // size) if len(changed) else 0


def shrink_max(arr: np.ndarray, f: int) -> np.ndarray:
    """Shrink by f keeping the brightest pixel of each f x f block, so a single
    changed pixel can't disappear when the image is scaled down for display."""
    h, w = arr.shape[:2]
    ph, pw = -h % f, -w % f
    a = np.pad(arr, [(0, ph), (0, pw)] + [(0, 0)] * (arr.ndim - 2))
    a = a.reshape((h + ph) // f, f, (w + pw) // f, f, *arr.shape[2:])
    return np.ascontiguousarray(a.max(axis=(1, 3)))
