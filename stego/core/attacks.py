"""Attack simulation (the Attack Lab).

Who is who
----------
DEFENDER: our tool. protect() on the sender side, verify() on the receiver side.
ATTACKER: anyone who gets hold of a stego file and tries to fool verify().

This module is the defender's test bench. We wrote it to play the attacker, but
it has one advantage a real attacker doesn't: it holds the stego key, so it knows
exactly where the payload sits and can aim each attack. Every attack below says
what a REAL attacker would need to pull that move off.

How a run works
---------------
run_all() first verifies the untouched file, which must come back Authentic.
Then each attack gets its own fresh copy of that genuine file. The attacks are
independent: none of them builds on another one's damage, and each changes
exactly one thing, so each row proves exactly one defence works.

verify() (core/protect.py) runs its checks in this order, stopping at the first
one that fails:

  check 1  find the header at the key-derived start  -> Wrong Start Location
  check 2  the header's body length fits in the file -> Payload Missing
  check 3  Ed25519 signature over the payload        -> Signature Invalid
  check 4  media hash stored inside the payload      -> Tampered
  check 5  nonce not accepted before                 -> Replay Detected

Attacks 1-8 go after those checks in that order. Attacks 9-11 aren't tricks:
they're damage a file picks up on the way (noise, a scratch, lossy saving),
and they show robust mode and our limitation.

No Qt in here: the Attack Lab tab and try_attack.py just call run_all().
"""

import io
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from . import lsb, media, protect, replay, visual
from .protect import (AUTHENTIC, HEADER_UNITS, PAYLOAD_MISSING, REPLAY_DETECTED,
                      SIGNATURE_INVALID, TAMPERED, WRONG_START)

# The ways a payload can be lost: wrong place, broken header, or broken signature
LOST = (WRONG_START, SIGNATURE_INVALID, PAYLOAD_MISSING)


@dataclass
class Attack:
    number: int
    name: str
    check: str                   # which verify() check it goes after
    attacker_has: str            # what a real attacker needs for this move
    what: str                    # what it does to the file
    expected: tuple | Callable   # verdicts that count as caught, or a function of the file's details
    run: Callable


@dataclass
class AttackResult:
    number: int
    name: str
    check: str
    attacker_has: str
    what: str
    expected: tuple       # verdicts that count as "caught"
    got: str              # what verify() actually said
    reason: str
    recovered: bool = False   # did the signed payload still come out intact?

    @property
    def passed(self) -> bool:
        return self.got in self.expected


# --- bench helpers (defender side, not attacker capabilities) ---

@contextmanager
def scratch_replay_store():
    # verify() remembers every Authentic nonce in keys/seen_nonces.json, the
    # receiver's real replay log. The bench verifies the same payload over and
    # over, so point that log at a throwaway file while it runs. Otherwise our
    # own testing would fill the real log and the demo files would come back as
    # "Replay Detected".
    old = replay.DEFAULT_STORE
    with tempfile.TemporaryDirectory() as tmp:
        replay.DEFAULT_STORE = Path(tmp) / "seen_nonces.json"
        try:
            yield
        finally:
            replay.DEFAULT_STORE = old


def payload_region(where: dict) -> np.ndarray:
    """Carrier indices holding the header + body, same maths as protect._region.

    `where` is the details dict verify() returned for the genuine file. We only
    have it because the bench holds the stego key. In robust mode the header is
    stored 7 times and the body `reps` times, so the region is bigger.
    """
    k, n, reps = where["k"], where["carrier_units"], where.get("reps", 1)
    total = where.get("header_units", HEADER_UNITS) + lsb.units_needed(where["body_len"] * reps, k)
    return (where["start"] + np.arange(total)) % n


def _body_positions(where: dict) -> np.ndarray:
    # skip the header copies, leaving only where the body bits sit
    return payload_region(where)[where.get("header_units", HEADER_UNITS):]


# =============================================================================
# Part 1: attacks on the security checks, in the order verify() runs them
# =============================================================================

# --- Attack 1: wrong stego key (check 1) ---
# Attacker has: the stego file and the public key (both are public), not the stego key.
# Attacker does: guesses a passphrase and tries to extract.
# Caught by: a different key gives a different start AND a different header mask,
#   so the "SG" marker never shows up. They can't even tell a payload exists.
def wrong_stego_key(stego, key, pub, where):
    return protect.verify(stego, key + "x", pub)


# --- Attack 2: off-by-one start (check 1) ---
# Attacker has: the file, and (generously) a start position just 1 byte off.
#   A real attacker doesn't even get that close, and still lacks the header mask.
# Attacker does: reads the payload from the wrong spot.
# Caught by: one byte off is already the wrong place, which is why guessing the
#   start among hundreds of thousands of positions doesn't work.
def shifted_start(stego, key, pub, where):
    return protect.verify(stego, key, pub, start_override=where["start"] + 1)


# --- Attack 3: crop / trim (check 1) ---
# Attacker has: just the file. No keys needed.
# Attacker does: crops a row off the image, drops the last video frame, or trims audio.
# Caught by: the start is derived from the key AND the file's size, so a smaller
#   file points somewhere else entirely. That's why this is Wrong Start, not Tampered.
def crop(stego, key, pub, where):
    p = dict(stego.params)
    if stego.kind == "image":
        cut = p["width"] * 3                           # one row of RGB pixels
        p["height"] -= 1
    elif stego.kind == "video":
        cut = p["width"] * p["height"] * 3             # the last frame
        p["frames"] -= 1
    else:
        cut = 100 * p["channels"] * p["sampwidth"]     # 100 audio frames
        p["nframes"] -= 100
    t = media.Cover(stego.kind, stego.data[:-cut].copy(), stego.step, p)
    return protect.verify(t, key, pub)


# --- Attack 4: break the header's length field (check 2) ---
# Attacker has: the file. This is also what accidental corruption of the header looks like.
# Attacker does: flips the top bit of the 4-byte body length (header bits 32-63),
#   in every copy of the header (robust files keep 7).
# Caught by: the length becomes ~2 GB, more than any file holds, and the tool
#   reports it cleanly instead of crashing. The XOR mask doesn't matter: flip a
#   stored bit and the same bit flips after unmasking.
def break_length_field(stego, key, pub, where):
    t = stego.copy()
    car = t.carrier            # a view, so writing here changes t.data
    region = payload_region(where)
    for copy in range(where.get("header_units", HEADER_UNITS) // HEADER_UNITS):
        car[region[copy * HEADER_UNITS + 32]] ^= 1
    return protect.verify(t, key, pub)


# --- Attack 5: change the hidden message (check 3) ---
# Attacker has: the file, the payload's location, even the stego key. NOT the
#   sender's private key, so they can't make a new signature.
# Attacker does: flips one bit of the hidden payload, e.g. to change the message.
# Caught by: Ed25519 fails if a single signed bit changes. In robust mode the
#   other copies outvote the flipped bit, so the change doesn't even stick.
def flip_payload_bit(stego, key, pub, where):
    t = stego.copy()
    body = _body_positions(where)
    car = t.carrier
    # middle of the body on purpose: the last unit can hold padding bits,
    # but bit 0 of any body unit is always real payload
    car[body[len(body) // 2]] ^= 1
    return protect.verify(t, key, pub)


# --- Attack 6: edit the media itself (check 4) ---
# Attacker has: just the file. No keys needed.
# Attacker does: edits the picture/sound (500 bytes' top bits flipped) but leaves
#   every hidden bit alone, hoping the genuine signature still vouches for it.
# Caught by: the signature DOES still pass, since the payload wasn't touched. But
#   the payload contains a hash of the media, and the media changed.
def edit_outside_payload(stego, key, pub, where):
    t = stego.copy()
    outside = np.ones(len(t.carrier), dtype=bool)
    outside[payload_region(where)] = False
    idx = np.flatnonzero(outside)[:500]
    car = t.carrier
    car[idx] ^= 0x80           # flip the top bit: a big, visible change
    return protect.verify(t, key, pub)


def _different_content(cover):
    # Reverse the order of the pixels / audio frames: same size and format,
    # but a different picture or sound. Grouping by pixel or frame first means
    # we never split one sample's bytes apart.
    unit = 3 if cover.kind in ("image", "video") else cover.params["channels"] * cover.params["sampwidth"]
    data = cover.data.reshape(-1, unit)[::-1].reshape(-1).copy()
    return media.Cover(cover.kind, data, cover.step, dict(cover.params))


# --- Attack 7: move a genuine payload into a fake file (check 4) ---
# Attacker has: a genuine stego file and its stego key (say, an insider), and
#   their own fake file of the same size. NOT the private key.
# Attacker does: copies the genuine, validly signed payload bits into the fake,
#   hoping the real signature will vouch for it.
# Caught by: the signature passes and the message even decodes, but the signed
#   media hash belongs to the ORIGINAL file. The signature is bound to one file.
def substitute_payload(stego, key, pub, where):
    donor = _different_content(stego)
    region = payload_region(where)
    low = np.uint8((1 << where["k"]) - 1)
    d, s = donor.carrier, stego.carrier
    d[region] = (d[region] & ~low) | (s[region] & low)   # same formula lsb.embed uses
    return protect.verify(donor, key, pub)


# --- Attack 8: replay an old genuine file (check 5) ---
# Attacker has: a copy of a genuine file they intercepted earlier. No keys needed.
# Attacker does: sends it again unchanged, e.g. to repeat an old "approved".
# Caught by: every payload has a random nonce, and the receiver remembers the
#   nonces it has accepted. The first check below accepts it, the second is the replay.
def replay_same_file(stego, key, pub, where):
    protect.verify(stego, key, pub)
    return protect.verify(stego, key, pub)


# =============================================================================
# Part 2: damage in transit. Not tricks, they show robust mode and our limitation
# =============================================================================

# --- Attack 9: mild noise (robustness) ---
# Scenario: a noisy channel flips the lowest bit of 1% of all carrier bytes.
# Normal file: the payload always gets hit, so it's lost.
# Robust file (x5 or more): the vote repairs it, the signed payload survives,
#   and the verdict still reports the change as Tampered.
def mild_noise(stego, key, pub, where):
    t = stego.copy()
    car = t.carrier
    rng = np.random.default_rng(1)       # fixed seed so every run is the same
    idx = rng.choice(len(car), size=max(1, len(car) // 100), replace=False)
    car[idx] ^= 1
    return protect.verify(t, key, pub)


# --- Attack 10: a scratch right over the payload (robustness) ---
# Scenario: 200 bytes in the middle of the hidden payload get scribbled over,
#   like a small edit or a scratch exactly where the data sits.
# Normal file: lost. Robust file: its copies of each bit are far apart, so the
#   scratch only hits one copy of each bit and the vote puts it right.
def scratch(stego, key, pub, where):
    t = stego.copy()
    car = t.carrier
    body = _body_positions(where)
    mid = len(body) // 2
    hit = body[max(0, mid - 100):mid + 100]
    car[hit] = np.random.default_rng(2).integers(0, 256, len(hit), dtype=np.uint8)
    return protect.verify(t, key, pub)


def _h264_roundtrip(stego):
    # What happens when a video gets uploaded somewhere and re-compressed
    import imageio_ffmpeg

    p = stego.params
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "reencoded.mp4")
        writer = imageio_ffmpeg.write_frames(path, (p["width"], p["height"]), fps=p["fps"],
                                             codec="libx264", pix_fmt_in="rgb24",
                                             pix_fmt_out="yuv444p", macro_block_size=1,
                                             output_params=["-crf", "18"])
        writer.send(None)
        size = p["width"] * p["height"] * 3
        for i in range(p["frames"]):
            writer.send(stego.data[i * size:(i + 1) * size].tobytes())
        writer.close()
        return media.load_video(path)


# --- Attack 11: lossy re-encoding (our limitation) ---
# Scenario: the file goes through JPEG (images), H.264 (video), or heavy noise in
#   every LSB (audio), like a messaging app compressing it.
# Result: the payload is destroyed in every mode, even robust. The tool refuses
#   to call it authentic, so it fails safe, but the data is gone.
def lossy_reencode(stego, key, pub, where):
    if stego.kind == "image":
        buf = io.BytesIO()
        Image.fromarray(visual.image_rgb(stego)).save(buf, "JPEG", quality=95)
        pixels = np.array(Image.open(buf).convert("RGB"))
        t = media.Cover("image", pixels.reshape(-1).copy(), 1, dict(stego.params))
    elif stego.kind == "video":
        t = _h264_roundtrip(stego)
    else:
        t = stego.copy()
        car = t.carrier
        car ^= np.random.default_rng(0).integers(0, 2, len(car), dtype=np.uint8)
    return protect.verify(t, key, pub)


# Some expectations depend on whether the file was made in robust mode
def _one_bit(where):
    return (AUTHENTIC,) if where.get("reps", 1) > 1 else (SIGNATURE_INVALID,)


def _noise(where):
    # x3 usually copes with 1% noise but not always, x5 and up reliably do
    reps = where.get("reps", 1)
    return (TAMPERED,) if reps >= 5 else (TAMPERED,) + LOST if reps == 3 else LOST


def _scratch(where):
    return (TAMPERED,) if where.get("reps", 1) > 1 else LOST


ATTACKS = [
    Attack(1, "Wrong stego key", "1. find the header",
           "the file and the public key, not the stego key",
           "Tried to extract with a guessed passphrase", (WRONG_START,), wrong_stego_key),
    Attack(2, "Off-by-one start", "1. find the header",
           "the file and a start position 1 byte off",
           "Read the payload one byte after the real start", (WRONG_START,), shifted_start),
    Attack(3, "Crop / trim", "1. find the header",
           "just the file",
           "Removed a pixel row, the last video frame, or 100 audio frames", (WRONG_START,), crop),
    Attack(4, "Break length field", "2. body fits",
           "just the file (or accidental damage)",
           "Flipped the top bit of the header's length field", (PAYLOAD_MISSING,), break_length_field),
    Attack(5, "Flip one payload bit", "3. signature",
           "the file, the payload's location and the stego key, not the private key",
           "Changed a single bit inside the hidden payload", _one_bit, flip_payload_bit),
    Attack(6, "Edit outside payload", "4. media hash",
           "just the file",
           "Flipped the top bit of 500 bytes that hold no payload", (TAMPERED,), edit_outside_payload),
    Attack(7, "Substitute payload", "4. media hash",
           "a genuine file, its stego key and a fake file, not the private key",
           "Pasted the genuine payload into a different file", (TAMPERED,), substitute_payload),
    Attack(8, "Replay", "5. replay log",
           "an old genuine file they intercepted",
           "Presented the same authentic file a second time", (REPLAY_DETECTED,), replay_same_file),
    Attack(9, "Mild LSB noise", "damage (robustness)",
           "nothing: a noisy channel",
           "Flipped the lowest bit of 1% of all carrier bytes", _noise, mild_noise),
    Attack(10, "Scratch over payload", "damage (robustness)",
           "nothing: a local edit or scratch",
           "Overwrote 200 bytes in the middle of the hidden payload", _scratch, scratch),
    Attack(11, "Lossy re-encode", "damage (limitation)",
           "nothing: an app that compresses the file",
           "JPEG for images, H.264 for video, full LSB noise for audio", LOST, lossy_reencode),
]


def run_all(stego, key, pub) -> list[AttackResult]:
    with scratch_replay_store():
        # Start from a file we know is genuine. Catching "attacks" on a file
        # that was already broken wouldn't prove anything. This also tells us
        # where the payload sits and whether the file is in robust mode.
        base = protect.verify(stego, key, pub)
        if base.verdict != AUTHENTIC:
            raise ValueError(f"Attacks need an authentic stego file to start from, "
                             f"but this one is '{base.verdict}': {base.reason}")
        results = []
        for a in ATTACKS:
            replay.clear()    # independent: no attack sees another one's history
            res = a.run(stego, key, pub, base.details)
            expected = a.expected(base.details) if callable(a.expected) else a.expected
            results.append(AttackResult(a.number, a.name, a.check, a.attacker_has, a.what,
                                        expected, res.verdict, res.reason,
                                        recovered=res.payload is not None))
        return results
