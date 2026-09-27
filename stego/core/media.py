"""Loading and saving cover objects (PNG images, WAV audio, lossless video) as raw byte arrays."""

import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".bmp"}
AUDIO_EXTS = {".wav"}
PCM_SAMPLE_WIDTHS = {1, 2, 3, 4}
# Stego video is always written as FFV1, a lossless codec, in MKV or AVI. MP4/MOV
# are accepted as covers (we decode them to frames) but never as output, because
# H.264 and friends are lossy and would wipe the LSBs.
VIDEO_EXTS = {".mkv", ".avi"}
VIDEO_IN_EXTS = VIDEO_EXTS | {".mp4", ".mov", ".webm"}
MAX_VIDEO_BYTES = 400 * 1024 * 1024      # every frame is held in memory


class UnsupportedMedia(Exception):
    pass


@dataclass
class Cover:
    kind: str            # "image", "audio" or "video"
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
        if self.kind == "video":
            return (f"{p['width']}x{p['height']}, {p['frames']} frames at {p['fps']:g} fps, "
                    f"{len(self.carrier):,} carrier bytes")
        secs = p["nframes"] / p["framerate"]
        return (f"{p['channels']}ch {p['sampwidth'] * 8}-bit {p['framerate']} Hz, "
                f"{secs:.1f}s, {len(self.carrier):,} carrier bytes")

    def copy(self) -> "Cover":
        return Cover(self.kind, self.data.copy(), self.step, dict(self.params))


def media_kind(path) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_IN_EXTS:
        return "video"
    raise UnsupportedMedia(f"Unsupported file type '{ext}'. Use PNG/BMP for images, WAV for "
                           "audio, or MKV/AVI (FFV1) for video.")


def load_cover(path) -> Cover:
    kind = media_kind(path)
    if kind == "image":
        return load_image(path)
    if kind == "video":
        return load_video(path)
    return load_audio(path)


def save_cover(cover: Cover, path) -> None:
    if cover.kind == "image":
        save_image(cover, path)
    elif cover.kind == "video":
        save_video(cover, path)
    else:
        save_audio(cover, path)


def load_image(path) -> Cover:
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
    if params["sampwidth"] not in PCM_SAMPLE_WIDTHS:
        raise UnsupportedMedia(
            "Only 8-, 16-, 24-, and 32-bit PCM WAV files are supported.")
    expected = params["channels"] * params["sampwidth"] * params["nframes"]
    if len(frames) != expected:
        raise UnsupportedMedia("WAV frame data is incomplete or has an invalid layout.")
    data = np.frombuffer(frames, dtype=np.uint8).copy()
    # WAV samples are little-endian, so the first byte of each sample is the
    # least significant one. We only hide data there, never in the loud high byte.
    return Cover("audio", data, params["sampwidth"], params)


def save_audio(cover: Cover, path) -> None:
    if Path(path).suffix.lower() not in AUDIO_EXTS:
        raise UnsupportedMedia("Stego audio must be saved as WAV.")
    p = cover.params
    if p["sampwidth"] not in PCM_SAMPLE_WIDTHS:
        raise UnsupportedMedia(
            "Only 8-, 16-, 24-, and 32-bit PCM WAV files are supported.")
    expected = p["channels"] * p["sampwidth"] * p["nframes"]
    if len(cover.data) != expected:
        raise UnsupportedMedia("Audio data does not match its WAV metadata.")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(p["channels"])
        w.setsampwidth(p["sampwidth"])
        w.setframerate(p["framerate"])
        w.writeframes(cover.data.tobytes())


def load_video(path) -> Cover:
    # imageio-ffmpeg ships its own ffmpeg, so nothing extra to install. Every
    # frame is decoded to RGB and joined end to end: the carrier is then just
    # "all the pixels of all the frames", and the key-derived start picks which
    # frame(s) the payload lands in.
    import imageio_ffmpeg

    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
    meta = next(reader)
    w, h = meta["size"]
    frames, total = [], 0
    for raw in reader:
        total += len(raw)
        if total > MAX_VIDEO_BYTES:
            reader.close()
            raise UnsupportedMedia("Video too large to hold in memory, use a shorter or smaller clip.")
        frames.append(np.frombuffer(raw, dtype=np.uint8))
    if not frames:
        raise UnsupportedMedia("No video frames found.")
    # fps goes into the media hash, so round it the same way every time it's read
    params = {"width": w, "height": h, "frames": len(frames), "fps": round(float(meta["fps"]), 3)}
    return Cover("video", np.concatenate(frames), 1, params)


def save_video(cover: Cover, path) -> None:
    import imageio_ffmpeg

    if Path(path).suffix.lower() not in VIDEO_EXTS:
        raise UnsupportedMedia("Stego video must be saved losslessly as MKV or AVI (FFV1), not MP4.")
    p = cover.params
    # macro_block_size=1 stops imageio from resizing odd frame sizes, which would
    # rewrite every pixel. The audio track of the original, if any, isn't kept.
    writer = imageio_ffmpeg.write_frames(str(path), (p["width"], p["height"]), fps=p["fps"],
                                         codec="ffv1", pix_fmt_in="rgb24", pix_fmt_out="bgr0",
                                         macro_block_size=1)
    writer.send(None)
    frame_bytes = p["width"] * p["height"] * 3
    for i in range(p["frames"]):
        writer.send(cover.data[i * frame_bytes:(i + 1) * frame_bytes].tobytes())
    writer.close()


def video_frame(cover: Cover, i: int) -> np.ndarray:
    """Frame i as an (h, w, 3) array."""
    p = cover.params
    size = p["width"] * p["height"] * 3
    return cover.data[i * size:(i + 1) * size].reshape(p["height"], p["width"], 3)


def audio_waveform(cover: Cover, points: int = 180) -> tuple[np.ndarray, np.ndarray]:
    """Return normalised minimum/maximum amplitudes for a compact WAV preview.

    All channels are averaged for each frame before down-sampling.  This keeps
    the GUI preview useful for stereo files without changing any carrier data.
    """
    if cover.kind != "audio":
        raise ValueError("audio_waveform requires an audio cover")
    if points < 1:
        raise ValueError("points must be positive")

    p = cover.params
    nframes, channels, width = p["nframes"], p["channels"], p["sampwidth"]
    if nframes == 0:
        return np.zeros(1), np.zeros(1)

    raw = cover.data.reshape(nframes, channels, width).astype(np.int64)
    weights = 256 ** np.arange(width, dtype=np.int64)
    unsigned = (raw * weights).sum(axis=2)
    bits = width * 8
    if width == 1:
        values = (unsigned - 128) / 128
    else:
        sign_bit = 1 << (bits - 1)
        signed = (unsigned ^ sign_bit) - sign_bit
        values = signed / sign_bit
    frames = values.mean(axis=1)

    count = min(points, nframes)
    edges = np.linspace(0, nframes, count + 1, dtype=int)
    lows = np.empty(count, dtype=float)
    highs = np.empty(count, dtype=float)
    for i in range(count):
        block = frames[edges[i]:edges[i + 1]]
        lows[i] = block.min()
        highs[i] = block.max()
    return lows, highs
