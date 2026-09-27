"""Attack simulation: take an authentic stego file, attack it, and check that
verify() catches every attack with the right verdict.

Each attack starts from the same genuine file and changes exactly one thing,
so every row proves one specific defence works. No Qt in here, the Attack Lab
tab just calls run_all() and shows the results.
"""

import io
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from . import lsb, media, protect, replay, visual
from .protect import (AUTHENTIC, PAYLOAD_MISSING, REPLAY_DETECTED, SIGNATURE_INVALID,
                      TAMPERED, WRONG_START, HEADER_UNITS)


@dataclass
class AttackResult:
    name: str
    what: str              # what the attacker did, in plain words
    expected: tuple        # verdicts that count as "caught"
    got: str               # what verify() actually said
    reason: str

    @property
    def passed(self) -> bool:
        return self.got in self.expected


@contextmanager
def scratch_replay_store():
    # The lab verifies the same payload over and over. Point the replay check
    # at a throwaway file so the real keys/seen_nonces.json is never touched,
    # otherwise the demo files would come back as "Replay Detected" later.
    old = replay.DEFAULT_STORE
    with tempfile.TemporaryDirectory() as tmp:
        replay.DEFAULT_STORE = Path(tmp) / "seen_nonces.json"
        try:
            yield
        finally:
            replay.DEFAULT_STORE = old


def payload_region(where: dict) -> np.ndarray:
    """Carrier indices holding the header + body, same maths as protect._region.

    `where` is the details dict verify() returns for the genuine file, so we
    only know where the payload is because we hold the stego key.
    """
    k, n = where["k"], where["carrier_units"]
    total = HEADER_UNITS + lsb.units_needed(where["body_len"], k)
    return (where["start"] + np.arange(total)) % n


# --- the attacks: each gets the untouched stego file and returns verify()'s result ---

def edit_outside_payload(stego, key, pub, where):
    # Someone edits the picture/sound itself but leaves the hidden data alone.
    # The signature still checks out, the media hash inside it doesn't.
    t = stego.copy()
    outside = np.ones(len(t.carrier), dtype=bool)
    outside[payload_region(where)] = False
    idx = np.flatnonzero(outside)[:500]
    car = t.carrier            # a view, so writing here changes t.data
    car[idx] ^= 0x80           # flip the top bit of 500 bytes, a big visible change
    return protect.verify(t, key, pub)


def flip_payload_bit(stego, key, pub, where):
    # Trying to alter the hidden message. One bit is enough to break Ed25519.
    t = stego.copy()
    body = payload_region(where)[HEADER_UNITS:]
    car = t.carrier
    # middle of the body on purpose: the last unit can hold padding bits,
    # but bit 0 of any body unit is always real payload
    car[body[len(body) // 2]] ^= 1
    return protect.verify(t, key, pub)


def break_length_field(stego, key, pub, where):
    # Header bits 32-63 are the 4-byte body length. Flipping bit 32 (its top
    # bit) makes the length about 2 GB, which can't fit in any cover. The XOR
    # mask doesn't matter: flip a stored bit and the same bit flips after unmasking.
    t = stego.copy()
    car = t.carrier
    car[payload_region(where)[32]] ^= 1
    return protect.verify(t, key, pub)


def wrong_stego_key(stego, key, pub, where):
    # A wrong key derives a different start AND a different header mask, so
    # the attacker can't even tell there's a payload in there.
    return protect.verify(stego, key + "x", pub)


def shifted_start(stego, key, pub, where):
    # Even one byte off is enough to miss, which is why guessing doesn't work
    return protect.verify(stego, key, pub, start_override=where["start"] + 1)


def crop(stego, key, pub, where):
    # The start location is derived from the key and the carrier length, so a
    # cropped/trimmed file points somewhere else entirely.
    p = dict(stego.params)
    if stego.kind == "image":
        cut = p["width"] * 3                           # one row of RGB pixels
        p["height"] -= 1
    else:
        cut = 100 * p["channels"] * p["sampwidth"]     # 100 audio frames
        p["nframes"] -= 100
    t = media.Cover(stego.kind, stego.data[:-cut].copy(), stego.step, p)
    return protect.verify(t, key, pub)


def _different_content(cover):
    # Reverse the order of the pixels / audio frames: same size and format,
    # but a different picture or sound. Grouping by pixel or frame first means
    # we never split one sample's bytes apart.
    if cover.kind == "image":
        unit = 3
    else:
        unit = cover.params["channels"] * cover.params["sampwidth"]
    data = cover.data.reshape(-1, unit)[::-1].reshape(-1).copy()
    return media.Cover(cover.kind, data, cover.step, dict(cover.params))


def substitute_payload(stego, key, pub, where):
    # Lift the genuine, validly signed payload out and paste it into a fake
    # file, hoping the real signature vouches for it. The signature does pass,
    # but it covers the ORIGINAL file's hash, so the fake shows up as Tampered.
    donor = _different_content(stego)
    region = payload_region(where)
    low = np.uint8((1 << where["k"]) - 1)
    d, s = donor.carrier, stego.carrier
    d[region] = (d[region] & ~low) | (s[region] & low)   # same formula lsb.embed uses
    return protect.verify(donor, key, pub)


def lossy_reencode(stego, key, pub, where):
    # Not really an attack, it's our limitation: lossy saving wipes the LSBs.
    # The tool refuses to call it authentic, so it fails safe, but the data is gone.
    if stego.kind == "image":
        buf = io.BytesIO()
        Image.fromarray(visual.image_rgb(stego)).save(buf, "JPEG", quality=95)
        pixels = np.array(Image.open(buf).convert("RGB"))
        t = media.Cover("image", pixels.reshape(-1).copy(), 1, dict(stego.params))
    else:
        t = stego.copy()
        rng = np.random.default_rng(0)       # fixed seed so every run gives the same result
        car = t.carrier
        car ^= rng.integers(0, 2, len(car), dtype=np.uint8)   # random noise in every LSB
    return protect.verify(t, key, pub)


def replay_same_file(stego, key, pub, where):
    # run_all already verified this exact file once, so this is the second time
    # the same nonce turns up
    return protect.verify(stego, key, pub)


ATTACKS = [
    ("Edit outside payload", "Flipped the top bit of 500 bytes that hold no payload",
     (TAMPERED,), edit_outside_payload),
    ("Flip one payload bit", "Changed a single bit inside the hidden payload",
     (SIGNATURE_INVALID,), flip_payload_bit),
    ("Break length field", "Flipped the top bit of the header's length field",
     (PAYLOAD_MISSING,), break_length_field),
    ("Wrong stego key", "Tried to extract with a guessed passphrase",
     (WRONG_START,), wrong_stego_key),
    ("Off-by-one start", "Read the payload one byte after the real start",
     (WRONG_START,), shifted_start),
    ("Crop / trim", "Removed one pixel row, or 100 audio frames",
     (WRONG_START,), crop),
    ("Substitute payload", "Pasted the genuine payload into a different file",
     (TAMPERED,), substitute_payload),
    ("Lossy re-encode", "JPEG re-compressed the image, or added LSB noise to the audio",
     (WRONG_START, SIGNATURE_INVALID, PAYLOAD_MISSING), lossy_reencode),
    ("Replay", "Presented the same authentic file a second time",
     (REPLAY_DETECTED,), replay_same_file),
]


def run_all(stego, key, pub) -> list[AttackResult]:
    with scratch_replay_store():
        # Start from a file we know is genuine. Catching "attacks" on a file
        # that was already broken wouldn't prove anything. This also tells us
        # where the payload sits, and records the nonce for the replay attack.
        base = protect.verify(stego, key, pub)
        if base.verdict != AUTHENTIC:
            raise ValueError(f"Attacks need an authentic stego file to start from, "
                             f"but this one is '{base.verdict}': {base.reason}")
        results = []
        for name, what, expected, attack in ATTACKS:
            res = attack(stego, key, pub, base.details)
            results.append(AttackResult(name, what, expected, res.verdict, res.reason))
        return results
