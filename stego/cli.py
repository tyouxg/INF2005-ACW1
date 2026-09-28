"""Command line front end, handy for testing the core without the GUI.

    python -m stego.cli keygen
    python -m stego.cli protect cover.png stego.png -k 2 --key "secret" --msg "hello"
    python -m stego.cli verify stego.png --key "secret"
    python -m stego.cli capacity cover.png -k 1 --msg-file long.txt
    python -m stego.cli clear-replay
    python -m stego.cli protect clip.mkv out.mkv -k 1 --key "secret" --msg "hi" --robust 5
    python -m stego.cli scan suspicious.png
    python -m stego.cli damage stego.png hurt.png --box 100 145 60 4 --noise 1
    python -m stego.cli shrink-video phone.mp4 small.mkv --seconds 5 --width 640
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .core import crypto, media, protect, replay, steganalysis, visual

KEYS_DIR = Path(__file__).resolve().parent.parent / "keys"


def cmd_keygen(args):
    priv_path, pub_path = crypto.save_keypair(crypto.generate_keypair(), args.out)
    print(f"Private key: {priv_path}\nPublic key:  {pub_path}")


def cmd_protect(args):
    text = Path(args.msg_file).read_text(encoding="utf-8") if args.msg_file else args.msg
    cover = media.load_cover(args.cover)
    priv = crypto.load_private_key(args.priv)
    try:
        stego, payload, info = protect.protect(cover, Path(args.cover).name, text, args.k,
                                               args.key, priv, args.encrypt, reps=args.robust,
                                               version=1 if args.legacy_v1 else protect.VERSION)
    except protect.CapacityError as e:
        sys.exit(f"Capacity check failed: {e}")
    media.save_cover(stego, args.out)
    print(f"Payload sits in {visual.payload_location(cover, info)}")
    print(json.dumps({"saved": args.out, **info, "payload": payload}, indent=2))


def cmd_capacity(args):
    text = Path(args.msg_file).read_text(encoding="utf-8") if args.msg_file else args.msg
    cover = media.load_cover(args.cover)
    need = protect.body_size(cover, Path(args.cover).name, text, args.k, args.encrypt)
    cap = protect.capacity_bytes(cover, args.k)
    print(f"{cover.describe()}\nPayload {need:,} bytes, capacity {cap:,} bytes at {args.k} LSB(s)")
    print("Fits" if need <= cap else "Does NOT fit")
    sys.exit(0 if need <= cap else 1)


def cmd_verify(args):
    cover = media.load_cover(args.file)
    pub = crypto.load_public_key(args.pub)
    res = protect.verify(cover, args.key, pub, args.start)
    print(f"Verdict: {res.verdict}\n{res.reason}")
    if res.message is not None:
        print(f"Message: {res.message}")
    print(json.dumps({"details": res.details, "payload": res.payload}, indent=2))
    sys.exit(0 if res.verdict == protect.AUTHENTIC else 1)


def cmd_scan(args):
    r = steganalysis.scan(media.load_cover(args.file))
    print(f"Chi-square attack: {100 * r.chi_square_embedded:.0f}% of chunks look embedded")
    if not r.found:
        print("Structure scan: nothing readable in the low bits (clean, or a masked version 2 payload)")
        sys.exit(0)
    print(f"Structure scan: readable JSON at k={r.k}, carrier bytes {r.start:,}-{r.end:,}")
    print(r.text)
    sys.exit(1)


def cmd_shrink_video(args):
    out = media.shrink_video(args.src, args.out, args.seconds, args.width)
    print(f"Wrote {out}: {media.load_cover(out).describe()}")


def cmd_damage(args):
    # Damage a file like an attacker or a noisy channel would: no keys needed.
    # Useful for showing robust mode: damage a normal and a robust file the same way.
    cover = media.load_cover(args.file)
    if args.box:
        if cover.kind != "image":
            sys.exit("--box only works on images")
        x, y, w, h = args.box
        p = cover.params
        pixels = cover.data.reshape(p["height"], p["width"], 3)   # a view, edits go into the file
        pixels[y:y + h, x:x + w] = 0
        print(f"Blacked out a {w}x{h} box at x={x}, y={y}")
    if args.noise:
        car = cover.carrier
        rng = np.random.default_rng(args.seed)
        idx = rng.choice(len(car), size=max(1, int(len(car) * args.noise / 100)), replace=False)
        car[idx] ^= 1
        print(f"Flipped the lowest bit of {len(idx):,} of {len(car):,} carrier bytes ({args.noise}%)")
    media.save_cover(cover, args.out)
    print(f"Saved the damaged copy as {args.out}")


def cmd_clear_replay(args):
    n = replay.count()
    replay.clear()
    print(f"Forgot {n} accepted payload(s). Verifying them again will say Authentic.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="stego")
    sub = ap.add_subparsers(required=True)

    p = sub.add_parser("keygen", help="create an Ed25519 key pair")
    p.add_argument("--out", default=KEYS_DIR)
    p.set_defaults(func=cmd_keygen)

    p = sub.add_parser("protect", help="embed a signed payload")
    p.add_argument("cover")
    p.add_argument("out")
    p.add_argument("-k", type=int, default=1, help="LSBs to use (1-8)")
    p.add_argument("--key", required=True, help="stego key / passphrase")
    p.add_argument("--msg", default="")
    p.add_argument("--msg-file")
    p.add_argument("--encrypt", action="store_true", help="AES-GCM encrypt the message")
    p.add_argument("--priv", default=KEYS_DIR / "private_key.pem")
    p.add_argument("--robust", type=int, default=1, help="store every bit this many times (odd, e.g. 5)")
    p.add_argument("--legacy-v1", action="store_true",
                   help="old format with an unmasked body, only to show the steganalysis scan finding it")
    p.set_defaults(func=cmd_protect)

    p = sub.add_parser("verify", help="extract and verify a payload")
    p.add_argument("file")
    p.add_argument("--key", required=True)
    p.add_argument("--pub", default=KEYS_DIR / "public_key.pem")
    p.add_argument("--start", type=int, help="force a start offset (wrong-start test)")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("capacity", help="check whether a message fits, without embedding")
    p.add_argument("cover")
    p.add_argument("-k", type=int, default=1, help="LSBs to use (1-8)")
    p.add_argument("--msg", default="")
    p.add_argument("--msg-file")
    p.add_argument("--encrypt", action="store_true")
    p.set_defaults(func=cmd_capacity)

    p = sub.add_parser("scan", help="look for hidden data without any key (steganalysis)")
    p.add_argument("file")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("shrink-video", help="make a short, small, lossless copy of a video")
    p.add_argument("src")
    p.add_argument("out", help="should end in .mkv")
    p.add_argument("--seconds", type=float, default=5)
    p.add_argument("--width", type=int, default=640)
    p.set_defaults(func=cmd_shrink_video)

    p = sub.add_parser("damage", help="damage a stego file (black box and/or LSB noise), no key needed")
    p.add_argument("file")
    p.add_argument("out")
    p.add_argument("--box", type=int, nargs=4, metavar=("X", "Y", "W", "H"), help="black out a box (images)")
    p.add_argument("--noise", type=float, default=0, help="flip the lowest bit of this %% of carrier bytes")
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=cmd_damage)

    p = sub.add_parser("clear-replay", help="forget which payloads were already verified")
    p.set_defaults(func=cmd_clear_replay)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
