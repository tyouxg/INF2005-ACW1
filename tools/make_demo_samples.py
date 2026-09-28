r"""Make the demo files for M6 (samples/yekai) and the small capacity-check files
(samples/img_vid_small).

Run from the repository root:
    .venv\Scripts\python tools\make_demo_samples.py

Every file is checked against the verdict it should give before this finishes,
and each folder gets a README listing the files, the key and what to expect.
Stego key for everything here: p6-4-demo-key. Public key: keys/public_key.pem.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import matplotlib.cbook                                          # noqa: E402
import numpy as np                                               # noqa: E402
from PIL import Image                                            # noqa: E402

from stego import messages                                       # noqa: E402
from stego.core import attacks, crypto, media, protect, visual   # noqa: E402

KEY = "p6-4-demo-key"
YK = Path("samples/yekai")
SMALL = Path("samples/img_vid_small")
LOST = attacks.LOST
priv = crypto.load_private_key("keys/private_key.pem")
pub = crypto.load_public_key("keys/public_key.pem")
rows_out = {YK: [], SMALL: []}      # README rows per folder


def check(folder, name, expected, note, key=KEY, want_message=None):
    """Verify a file and record it for the README. Stops if it's not what we expect."""
    with attacks.scratch_replay_store():
        r = protect.verify(media.load_cover(folder / name), key, pub)
    ok = r.verdict in expected and (want_message is None or (r.message is not None) == want_message)
    shown = r.verdict + (", message still readable" if r.message and r.verdict != protect.AUTHENTIC else "")
    print(f"  {'OK ' if ok else 'BAD'} {name:28} {shown}")
    if not ok:
        sys.exit(f"{name} gave {r.verdict}, expected {expected}")
    rows_out[folder].append((name, shown, note))


def where(cover, info):
    """Which image rows (or video frame) the payload sits in, to aim damage by hand."""
    p = cover.params
    start, end = info["start"], (info["start"] + info["units_used"] - 1) % info["carrier_units"]
    if cover.kind == "video":
        size = p["width"] * p["height"] * 3
        return f"frame {start // size + 1}, rows {start % size // 3 // p['width']}-{end % size // 3 // p['width']}"
    return f"image rows {start // 3 // p['width']}-{end // 3 // p['width']} (y coordinates)"


def photo(width=400):
    # Grace Hopper's portrait (US Navy, public domain), shipped with matplotlib
    img = Image.open(matplotlib.cbook.get_sample_data("grace_hopper.jpg", asfileobj=False)).convert("RGB")
    return img.resize((width, round(width * img.height / img.width)))


def black_box(cover, x, y, w, h):
    t = cover.copy()
    p = t.params
    t.data.reshape(p["height"], p["width"], 3)[y:y + h, x:x + w] = 0
    return t


def noise(cover, percent=1, seed=1):
    t = cover.copy()
    car = t.carrier
    idx = np.random.default_rng(seed).choice(len(car), size=int(len(car) * percent / 100), replace=False)
    car[idx] ^= 1
    return t


def make_yekai():
    YK.mkdir(parents=True, exist_ok=True)
    photo().save(YK / "cover.png")
    cover = media.load_cover(YK / "cover.png")
    print("samples/yekai")
    rows_out[YK].append(("cover.png", "no payload (the original)", "Grace Hopper portrait, 400x469, public domain"))

    # Attack Lab and robust mode: same cover, same key, same message, normal vs x5
    info = {}
    for name, reps in (("stego_normal.png", 1), ("stego_robust_x5.png", 5)):
        st, _, info[reps] = protect.protect(cover, "cover.png", messages.SHORT, 2, KEY, priv, reps=reps)
        media.save_cover(st, YK / name)
        check(YK, name, (protect.AUTHENTIC,),
              f"k=2, {'x5 repetition, ' if reps > 1 else ''}payload in {where(cover, info[reps])}")

    # Damage both exactly the same way, right over the payload rows
    first_row = info[1]["start"] // 3 // cover.params["width"]
    box = (100, first_row + 1, 60, 4)
    for name, reps in (("normal", 1), ("robust_x5", 5)):
        st = media.load_cover(YK / f"stego_{name}.png")
        media.save_cover(black_box(st, *box), YK / f"{name}_scratched.png")
        media.save_cover(noise(st), YK / f"{name}_noise.png")
    x, y, w, h = box
    scratch = f"black {w}x{h} box at x={x}, y={y}, over the payload rows"
    check(YK, "normal_scratched.png", LOST, scratch)
    check(YK, "robust_x5_scratched.png", (protect.TAMPERED,), scratch + " (same box)", want_message=True)
    check(YK, "normal_noise.png", LOST, "lowest bit of 1% of all carrier bytes flipped")
    check(YK, "robust_x5_noise.png", (protect.TAMPERED,), "same 1% noise", want_message=True)

    # Video: a 24-frame pan across the photo, lossless FFV1
    img = np.array(photo())
    frames = np.stack([img[40 + 4 * i: 280 + 4 * i, 40:360] for i in range(24)])
    vcover = media.Cover("video", frames.reshape(-1).copy(), 1,
                         {"width": 320, "height": 240, "frames": 24, "fps": 12.0})
    media.save_cover(vcover, YK / "video_cover.mkv")
    vcover = media.load_cover(YK / "video_cover.mkv")
    vst, _, vinfo = protect.protect(vcover, "video_cover.mkv", messages.SHORT, 2, KEY, priv)
    media.save_cover(vst, YK / "video_stego.mkv")
    frame = visual.first_changed_frame(vcover, media.load_cover(YK / "video_stego.mkv"))
    rows_out[YK].append(("video_cover.mkv", "no payload (the original)", "24 frames, 320x240, 12 fps"))
    check(YK, "video_stego.mkv", (protect.AUTHENTIC,), f"k=2, payload in {where(vcover, vinfo)}")
    # edit a frame that does NOT hold the payload: still caught, the hash covers every frame
    edited = 0 if frame != 0 else 23
    t = media.load_cover(YK / "video_stego.mkv")
    size = 320 * 240 * 3
    t.data[edited * size:(edited + 1) * size].reshape(240, 320, 3)[60:140, 100:220] = 0
    media.save_cover(t, YK / "video_tampered.mkv")
    check(YK, "video_tampered.mkv", (protect.TAMPERED,),
          f"black box in frame {edited + 1} (the payload is in frame {frame + 1})")


def make_small():
    SMALL.mkdir(parents=True, exist_ok=True)
    photo().crop((180, 120, 204, 144)).save(SMALL / "tiny_24x24.png")
    (SMALL / "project_overview.txt").write_text(messages.LONG, encoding="utf-8")
    (SMALL / "learning_outcome.txt").write_text(messages.SHORT, encoding="utf-8")
    # 4 frames of the same 24x24 spot drifting down, so it's a real (tiny) video
    img = np.array(photo())
    frames = np.stack([img[120 + 2 * i: 144 + 2 * i, 180:204] for i in range(4)])
    media.save_cover(media.Cover("video", frames.reshape(-1).copy(), 1,
                                 {"width": 24, "height": 24, "frames": 4, "fps": 4.0}),
                     SMALL / "tiny_24x24.mkv")
    print("samples/img_vid_small")
    for name in ("tiny_24x24.png", "tiny_24x24.mkv"):
        tiny = media.load_cover(SMALL / name)
        cap1 = protect.capacity_bytes(tiny, 1)
        for text, label in ((messages.LONG, "project_overview.txt"), (messages.SHORT, "learning_outcome.txt")):
            need = protect.body_size(tiny, name, text, 1)
            fits = [k for k in range(1, 9) if need <= protect.capacity_bytes(tiny, k)]
            if need <= cap1:
                verdict = f"needs {need:,} bytes; fits at 1 LSB ({cap1:,} bytes)"
            else:
                verdict = f"needs {need:,} bytes; DOES NOT FIT at 1 LSB ({cap1:,} bytes)"
                verdict += f", first fits at {fits[0]} LSBs" if fits else ", doesn't fit at any k"
            print(f"  OK  {name} + {label:22} {verdict}")
            rows_out[SMALL].append((f"{name} + {label}", verdict, "capacity check"))


def write_readme(folder, title, intro):
    lines = [f"# {title}", "", intro, "",
             "Stego key: `p6-4-demo-key` · Public key: `keys/public_key.pem` · "
             "Made by `tools/make_demo_samples.py` (every row below was checked when it ran).", "",
             "| File | Verify gives | Notes |", "|---|---|---|"]
    lines += [f"| `{n}` | {v} | {note} |" for n, v, note in rows_out[folder]]
    lines += ["", "Before a demo, press **Clear replay history** in the Receiver tab (or run "
              "`python -m stego.cli clear-replay`), or a file you already verified will say Replay Detected."]
    (folder / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    make_yekai()
    make_small()
    write_readme(YK, "M6 demo files (Ye Kai)",
                 "Attack Lab: load `stego_normal.png`, then `stego_robust_x5.png`, and compare rows 5, 9 "
                 "and 10. Robust demo: verify each `*_scratched.png` / `*_noise.png` pair in the Receiver "
                 "tab. The normal file loses its payload, the robust one keeps it. Video: verify "
                 "`video_stego.mkv` then `video_tampered.mkv`.")
    write_readme(SMALL, "Small files for the capacity check (Raffael)",
                 "In the Sender tab pick `tiny_24x24.png` (or the 4-frame `tiny_24x24.mkv`) as the "
                 "cover and *Load .txt* `project_overview.txt`: the capacity line turns red "
                 "(DOES NOT FIT) at 1 LSB, and pressing Protect shows the capacity-check error. "
                 "Raise the LSBs to see where it starts to fit.")
    print("Done.")
