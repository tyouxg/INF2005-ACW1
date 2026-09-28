"""Loading and saving cover objects (PNG images, WAV audio, lossless video) as raw byte arrays."""

import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".bmp"}           # lossless, safe for stego output
JPEG_EXTS = {".jpg", ".jpeg"}           # accepted as a cover only, never as output
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


class VideoTooLarge(UnsupportedMedia):
    # separate type so the GUI can offer to make a smaller copy
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
    if ext in IMAGE_EXTS or ext in JPEG_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_IN_EXTS:
        return "video"
    raise UnsupportedMedia(f"Unsupported file type '{ext}'. Use PNG/BMP/JPEG for images, WAV for "
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
    fps = float(meta["fps"])
    frame_bytes = w * h * 3

    # Raw frames are huge next to MP4: one 1080p frame is ~6 MB, so a second of
    # 30 fps video is ~187 MB. Check the estimate before decoding anything.
    seconds = meta.get("duration") or 0
    estimate = int(seconds * fps) * frame_bytes
    if estimate > MAX_VIDEO_BYTES:
        reader.close()
        raise VideoTooLarge(
            f"This video is {w}x{h}, about {seconds:.1f} s at {fps:g} fps, which is roughly "
            f"{estimate / 2**20:,.0f} MB of raw pixels. The limit is {MAX_VIDEO_BYTES / 2**20:.0f} MB, "
            f"because every frame is held in memory. Use a short, small clip "
            f"(e.g. 5 s at 640 px wide, see shrink_video / 'stego.cli shrink-video').")

    buf = bytearray()          # grows in place, so we never hold two full copies
    for raw in reader:
        buf += raw
        if len(buf) > MAX_VIDEO_BYTES:       # the duration in the file can be missing or wrong
            reader.close()
            raise VideoTooLarge(f"This video is more than {MAX_VIDEO_BYTES / 2**20:.0f} MB of raw "
                                "pixels. Use a shorter or smaller clip.")
    if not buf:
        raise UnsupportedMedia("No video frames found.")
    # fps goes into the media hash, so round it the same way every time it's read
    params = {"width": w, "height": h, "frames": len(buf) // frame_bytes, "fps": round(fps, 3)}
    return Cover("video", np.frombuffer(buf, dtype=np.uint8), 1, params)


def shrink_video(src, dst, seconds: float = 5, width: int = 640):
    """Make a short, small, lossless copy of any video to use as a cover.

    Uses the ffmpeg that imageio-ffmpeg ships: keeps the first `seconds`, scales
    down to at most `width` pixels wide, drops the audio, writes FFV1.
    """
    import subprocess

    import imageio_ffmpeg

    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(src),
           "-t", str(seconds), "-vf", f"scale='min({width},iw)':-2", "-an",
           "-c:v", "ffv1", "-pix_fmt", "bgr0", str(dst)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise UnsupportedMedia(f"ffmpeg couldn't shrink the video: {result.stderr.strip()[-300:]}")
    return Path(dst)


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
