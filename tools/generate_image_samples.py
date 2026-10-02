r"""Make M1's image demo files (samples/images) and M1's extra evidence.

Run from the repository root:
    .venv\Scripts\python tools\generate_image_samples.py

samples/images/      stego, tampered and JPEG-recompressed copies of demo1.png and
                     demo3.jpg, each checked against the verdict it should give
tests/evidence/      P5/P6 and psnr_k1/k8 screenshots (real GUI, offscreen) and
                     logs/P6.txt:
                     a JPEG cover, a long message in an image, and the
                     difference view with PSNR/MSE at k=1 and k=8

generate_evidence.py wipes tests/evidence/screenshots and logs, so run this
after it. Stego key: p6-4-demo-key. Public key: keys/public_key.pem. Runs inside a
throwaway replay store, so keys/seen_nonces.json is never touched.
"""

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# Reuses M6's offscreen GUI driver and CLI transcript helper (this also sets
# up offscreen Qt and changes into the repo root).
import generate_evidence as ev                                   # noqa: E402
import numpy as np                                               # noqa: E402
from PIL import Image                                            # noqa: E402

from stego import messages                                       # noqa: E402
from stego.core import attacks, crypto, imagetools, media, protect, replay  # noqa: E402

KEY = ev.KEY
IMG = Path("samples/images")
priv = crypto.load_private_key(ev.PRIV)
pub = crypto.load_public_key(ev.PUB)
log_lines = []


def check(path: Path, expected: str) -> str:
    """CLI-verify a file, save the transcript, stop if the verdict is wrong."""
    replay.clear()
    out = ev.cli_run(["verify", path.as_posix(), "--key", KEY, "--pub", ev.PUB])
    ok = f"Verdict: {expected}" in out
    print(f"  {'OK ' if ok else 'BAD'} {path.name:34} expected {expected}")
    if not ok:
        sys.exit(f"{path} did not give {expected}:\n{out}")
    log_lines.append(out)
    return out


def tamper_away_from_payload(stego_path: Path, info: dict, out: Path) -> int:
    """Paint a 40-row black bar where the payload isn't. Returns the first row."""
    cover = media.load_cover(stego_path)
    w, h = cover.params["width"], cover.params["height"]
    units = (info["start"] + np.arange(info["units_used"])) % info["carrier_units"]
    busy = set((units // 3 // w).tolist())
    top = next(r for r in range(10, h - 40) if not busy & set(range(r, r + 40)))
    rgb = cover.data.reshape(h, w, 3).copy()
    rgb[top:top + 40, : w // 3] = 0
    Image.fromarray(rgb).save(out)
    return top


def main():
    print("M1 image samples")
    demo1, demo3 = IMG / "demo1.png", IMG / "demo3.jpg"

    # Core-level files (no screenshots needed)
    c1 = media.load_cover(demo1)
    s, _, info = protect.protect(c1, demo1.name, messages.SHORT, 2, KEY, priv)
    media.save_cover(s, IMG / "demo1_stego_k2.png")
    check(IMG / "demo1_stego_k2.png", protect.AUTHENTIC)

    row = tamper_away_from_payload(IMG / "demo1_stego_k2.png", info, IMG / "demo1_tampered.png")
    check(IMG / "demo1_tampered.png", protect.TAMPERED)

    buf = io.BytesIO()
    Image.open(IMG / "demo1_stego_k2.png").convert("RGB").save(buf, "JPEG", quality=95)
    (IMG / "demo1_stego_resaved.jpg").write_bytes(buf.getvalue())
    check(IMG / "demo1_stego_resaved.jpg", protect.WRONG_START)

    # GUI cases with screenshots
    gui = ev.Gui()
    sender = gui.win.sender

    # P5: JPEG cover -> PNG stego
    gui.protect(demo3, "Short (learning outcome)", 2, IMG / "demo3_jpeg_cover_stego.png")
    gui.shot("P5_jpeg_cover_sender", 0)
    replay.clear()
    verdict = gui.verify(IMG / "demo3_jpeg_cover_stego.png")
    gui.shot("P5_jpeg_cover_receiver", 1)
    print(f"  GUI demo3_jpeg_cover_stego.png -> {verdict}")
    check(IMG / "demo3_jpeg_cover_stego.png", protect.AUTHENTIC)

    # P6: long message in an image, plus the PSNR view at k=1 and k=8
    psnr_rows = []
    for k in (1, 8):
        out = IMG / f"demo1_long_k{k}.png"
        gui.protect(demo1, "Long (project overview)", k, out)
        sender.diff_view.mode.setCurrentIndex(0)
        gui.shot(f"psnr_k{k}", 0)
        q = imagetools.compare(c1, media.load_cover(out))
        psnr_rows.append(f"k={k}: PSNR {q['psnr_db']:.1f} dB, MSE {q['mse']:.4f}, "
                         f"{q['changed_pixels']:,} of {q['total_pixels']:,} pixels changed")
        check(out, protect.AUTHENTIC)
    replay.clear()
    gui.verify(IMG / "demo1_long_k1.png")
    gui.shot("P6_image_long_receiver", 1)

    log = ev.write_log("P6", "# M1 image samples (samples/images), CLI verification",
                       "## PSNR / MSE (core/imagetools.py)", "\n".join(psnr_rows),
                       f"## Tampered file: black bar from row {row}, away from the payload",
                       *log_lines)
    print("\n".join(psnr_rows))
    print(f"Log: {log}")


if __name__ == "__main__":
    with attacks.scratch_replay_store():
        main()
