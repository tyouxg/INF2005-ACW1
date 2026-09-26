"""Loading and saving cover objects (PNG images, WAV audio) as raw byte arrays."""

import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".bmp"}           # lossless, safe for stego output
JPEG_EXTS = {".jpg", ".jpeg"}           # accepted as a cover only, never as output
AUDIO_EXTS = {".wav"}


class UnsupportedMedia(Exception):
    pass


@dataclass
class Cover:
    kind: str            # "image" or "audio"
    data: np.ndarray     # full raw bytes (uint8, 1-D)
    step: int            # carrier = every step-th byte of data
    params: dict = field(default_factory=dict)

    @property
    def carrier(self) -> np.ndarray:
        # Basic slicing gives a view, so writing to the carrier writes into data
        return self.data[0::self.step]

    def carrier_of(self, buf: np.ndarray) -> np.ndarray:
        return buf[0::self.step]

    def describe(self) -> str:
        p = self.params
        if self.kind == "image":
            return f"{p['width']}x{p['height']} RGB, {len(self.carrier):,} carrier bytes"
        secs = p["nframes"] / p["framerate"]
        return (f"{p['channels']}ch {p['sampwidth'] * 8}-bit {p['framerate']} Hz, "
                f"{secs:.1f}s, {len(self.carrier):,} carrier bytes")

    def copy(self) -> "Cover":
        return Cover(self.kind, self.data.copy(), self.step, dict(self.params))


def media_kind(path) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS or ext in JPEG_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    raise UnsupportedMedia(f"Unsupported file type '{ext}'. Use PNG/BMP/JPEG for images or WAV for audio.")


def load_cover(path) -> Cover:
    return load_image(path) if media_kind(path) == "image" else load_audio(path)


def save_cover(cover: Cover, path) -> None:
    if cover.kind == "image":
        save_image(cover, path)
    else:
        save_audio(cover, path)


def load_image(path) -> Cover:
    # JPEG covers are decoded to plain pixels here, so embedding works the same.
    # The stego result must then be saved as PNG/BMP: re-encoding as JPEG would
    # requantise the pixels and wipe the LSBs.
    # Alpha is dropped on purpose: fully transparent pixels can get their RGB
    # zeroed by some editors, which would wipe the payload.
    img = Image.open(path).convert("RGB")
    arr = np.array(img, dtype=np.uint8)
    h, w, _ = arr.shape
    return Cover("image", arr.reshape(-1).copy(), 1, {"width": w, "height": h})


def save_image(cover: Cover, path) -> None:
    if Path(path).suffix.lower() not in IMAGE_EXTS:
        raise UnsupportedMedia("Stego images must be saved losslessly (PNG or BMP), not JPEG.")
    p = cover.params
    arr = cover.data.reshape(p["height"], p["width"], 3)
    Image.fromarray(arr, "RGB").save(path)


def load_audio(path) -> Cover:
    with wave.open(str(path), "rb") as w:
        if w.getcomptype() != "NONE":
            raise UnsupportedMedia("Only uncompressed PCM WAV files are supported.")
        params = {
            "channels": w.getnchannels(),
            "sampwidth": w.getsampwidth(),
            "framerate": w.getframerate(),
            "nframes": w.getnframes(),
        }
        frames = w.readframes(w.getnframes())
    data = np.frombuffer(frames, dtype=np.uint8).copy()
    # WAV samples are little-endian, so the first byte of each sample is the
    # least significant one. We only hide data there, never in the loud high byte.
    return Cover("audio", data, params["sampwidth"], params)


def save_audio(cover: Cover, path) -> None:
    if Path(path).suffix.lower() not in AUDIO_EXTS:
        raise UnsupportedMedia("Stego audio must be saved as WAV.")
    p = cover.params
    with wave.open(str(path), "wb") as w:
        w.setnchannels(p["channels"])
        w.setsampwidth(p["sampwidth"])
        w.setframerate(p["framerate"])
        w.writeframes(cover.data.tobytes())
