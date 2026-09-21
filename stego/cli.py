"""Command line front end, handy for testing the core without the GUI.

    python -m stego.cli keygen
    python -m stego.cli protect cover.png stego.png -k 2 --key "secret" --msg "hello"
    python -m stego.cli verify stego.png --key "secret"
"""

import argparse
import json
import sys
from pathlib import Path

from .core import crypto, media, protect

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
                                               args.key, priv, args.encrypt)
    except protect.CapacityError as e:
        sys.exit(f"Capacity check failed: {e}")
    media.save_cover(stego, args.out)
    print(json.dumps({"saved": args.out, **info, "payload": payload}, indent=2))


def cmd_verify(args):
    cover = media.load_cover(args.file)
    pub = crypto.load_public_key(args.pub)
    res = protect.verify(cover, args.key, pub, args.start)
    print(f"Verdict: {res.verdict}\n{res.reason}")
    if res.message is not None:
        print(f"Message: {res.message}")
    print(json.dumps({"details": res.details, "payload": res.payload}, indent=2))
    sys.exit(0 if res.verdict == protect.AUTHENTIC else 1)


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
    p.set_defaults(func=cmd_protect)

    p = sub.add_parser("verify", help="extract and verify a payload")
    p.add_argument("file")
    p.add_argument("--key", required=True)
    p.add_argument("--pub", default=KEYS_DIR / "public_key.pem")
    p.add_argument("--start", type=int, help="force a start offset (wrong-start test)")
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
