r"""Generate reproducible M2 WAV demo assets without storing a private key.

Run from the repository root with:
    .venv\Scripts\python tools\generate_audio_samples.py

The generated public key and passphrase are for this coursework demonstration
only. Do not reuse either in a real deployment.
"""

import json
import sys
import wave
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stego import messages
from stego.core import crypto, media, protect

OUTPUT = ROOT / "samples" / "audio"
DEMO_KEY = "m2-audio-demo-key"
RATE = 44_100
CHANNELS = 2
DURATION_SECONDS = 8


def make_cover(path: Path) -> None:
    """Write a small, original, music-like stereo PCM WAV cover."""
    frames = RATE * DURATION_SECONDS
    t = np.arange(frames) / RATE
    envelope = 0.55 + 0.45 * np.sin(2 * np.pi * 0.35 * t) ** 2
    left = envelope * (0.34 * np.sin(2 * np.pi * 220 * t)
                       + 0.18 * np.sin(2 * np.pi * 440 * t)
                       + 0.08 * np.sin(2 * np.pi * 660 * t))
    right = envelope * (0.32 * np.sin(2 * np.pi * 277.18 * t)
                        + 0.18 * np.sin(2 * np.pi * 554.37 * t)
                        + 0.08 * np.sin(2 * np.pi * 831.61 * t))
    stereo = np.column_stack((left, right))
    samples = np.round(np.clip(stereo, -0.95, 0.95) * 32_767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(samples.tobytes())


def find_clear_section(info: dict, frames: int, channels: int, span_frames: int) -> int:
    """Find a frame range that does not overlap the embedded header/body."""
    occupied = np.zeros(info["carrier_units"], dtype=bool)
    indices = (info["start"] + np.arange(info["units_used"])) % info["carrier_units"]
    occupied[indices] = True
    for start in range(0, frames - span_frames):
        carrier_start = start * channels
        carrier_end = (start + span_frames) * channels
        if not occupied[carrier_start:carrier_end].any():
            return start
    raise RuntimeError("No clear audio section was available for the tamper sample")


def amplify_clear_section(stego: media.Cover, info: dict) -> tuple[media.Cover, int]:
    """Create a valid-length but hash-tampered WAV by amplifying 0.5 seconds."""
    tampered = stego.copy()
    p = tampered.params
    span = RATE // 2
    start = find_clear_section(info, p["nframes"], p["channels"], span)
    samples = np.frombuffer(tampered.data.tobytes(), dtype="<i2").copy()
    samples = samples.reshape(p["nframes"], p["channels"])
    changed = np.round(samples[start:start + span].astype(float) * 1.35)
    samples[start:start + span] = np.clip(changed, -32_768, 32_767).astype("<i2")
    tampered.data[:] = np.frombuffer(samples.tobytes(), dtype=np.uint8)
    return tampered, start


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cover_path = OUTPUT / "cover_stereo_music.wav"
    stego_path = OUTPUT / "stego_long_message.wav"
    tampered_path = OUTPUT / "tampered_amplified_section.wav"
    public_key_path = OUTPUT / "demo_public_key.pem"
    evidence_path = OUTPUT / "generation-details.json"

    make_cover(cover_path)
    private = crypto.generate_keypair()
    public_key_path.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

    cover = media.load_cover(cover_path)
    stego, _, info = protect.protect(
        cover, cover_path.name, messages.LONG, 2, DEMO_KEY, private)
    media.save_cover(stego, stego_path)

    tampered, frame_start = amplify_clear_section(stego, info)
    result = protect.verify(tampered, DEMO_KEY, private.public_key())
    if result.verdict != protect.TAMPERED:
        raise RuntimeError(f"Expected tampered demo asset, got {result.verdict}")
    media.save_cover(tampered, tampered_path)

    evidence_path.write_text(json.dumps({
        "cover": cover_path.name,
        "stego": stego_path.name,
        "tampered": tampered_path.name,
        "sample_rate_hz": RATE,
        "channels": CHANNELS,
        "sample_width_bits": 16,
        "duration_seconds": DURATION_SECONDS,
        "lsbs": 2,
        "stego_key_for_coursework_demo_only": DEMO_KEY,
        "payload_start_carrier_index": info["start"],
        "embedded_carrier_units": info["units_used"],
        "tampered_section_start_seconds": frame_start / RATE,
        "tampered_section_duration_seconds": span / RATE if (span := RATE // 2) else 0,
        "expected_tampered_verdict": result.verdict,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Generated WAV assets in {OUTPUT}")


if __name__ == "__main__":
    main()
