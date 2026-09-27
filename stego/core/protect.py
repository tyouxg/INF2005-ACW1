"""Protect (sender side) and verify (receiver side) pipelines.

Layout inside the carrier, starting at the key-derived offset and wrapping
around the end if needed:

    [ header: 8 bytes, 1 LSB per unit, XOR-masked ][ body: payload JSON + signature, k LSBs per unit ]

From version 2 the body is XOR-masked too, with a keystream derived from the
stego key, so the LSBs look like noise instead of readable JSON. In robust mode
(reps > 1) the header is stored 7 times and the body `reps` times, and each bit
is read back by majority vote (see core/robust.py).
"""

from dataclasses import dataclass, field

import numpy as np

from . import crypto, lsb, replay, robust
from .media import Cover
from .payload import (HEADER_LEN, MAX_REPS, VERSION, build_payload, decode_payload,
                      encode_payload, pack_header, unpack_header)

HEADER_UNITS = HEADER_LEN * 8
ROBUST_HEADER_COPIES = 7

AUTHENTIC = "Authentic"
TAMPERED = "Tampered"
SIGNATURE_INVALID = "Signature Invalid"
PAYLOAD_MISSING = "Payload Missing"
WRONG_START = "Wrong Start Location"
CANNOT_VERIFY = "Cannot Verify"
REPLAY_DETECTED = "Replay Detected"


class CapacityError(Exception):
    pass


@dataclass
class VerifyResult:
    verdict: str
    reason: str
    payload: dict | None = None
    message: str | None = None
    details: dict = field(default_factory=dict)


def _xor(a: bytes, b: bytes) -> bytes:
    return np.bitwise_xor(np.frombuffer(a, np.uint8), np.frombuffer(b, np.uint8)).tobytes()


def header_units(reps: int) -> int:
    # robust files keep 7 copies of the header, so noise can't knock out the
    # one thing that tells us k and the length
    return HEADER_UNITS * (ROBUST_HEADER_COPIES if reps > 1 else 1)


def _region(n: int, start: int, k: int, body_len: int, reps: int = 1) -> np.ndarray:
    total = header_units(reps) + lsb.units_needed(body_len * reps, k)
    return (start + np.arange(total)) % n


def media_hash(cover: Cover, start: int, k: int, body_len: int, reps: int = 1) -> str:
    """SHA-256 of the file with only our embedding bits cleared.

    Sender computes this on the cover, receiver on the stego file; both give the
    same value unless something outside those bits was changed.
    """
    buf = cover.data.copy()
    car = cover.carrier_of(buf)
    idx = _region(len(car), start, k, body_len, reps)
    car[idx] &= np.uint8((0xFF << k) & 0xFF)
    params = "|".join(f"{key}={cover.params[key]}" for key in sorted(cover.params))
    return crypto.sha256_hex(f"{cover.kind}|{params}|".encode() + buf.tobytes())


def capacity_bytes(cover: Cover, k: int, reps: int = 1) -> int:
    """How many body bytes (payload + signature) fit at this LSB setting."""
    return max(0, (len(cover.carrier) - header_units(reps)) * k // 8 // reps)


def body_size(cover: Cover, filename: str, text: str, k: int,
              encrypt_message: bool = False) -> int:
    """Exact body length protect() will produce, without needing the real keys.

    Apart from the text and filename, every payload field has a fixed width (hex
    digests, uuid, timestamp, AES salt/nonce), so a build with dummy values
    comes out the same size.
    """
    if encrypt_message:
        message = {"enc": True, **crypto.encrypt(bytes(32), text.encode("utf-8"))}
    else:
        message = {"enc": False, "text": text}
    payload = build_payload(cover.kind, filename, "0" * 64, k, message, "0" * 16)
    return len(encode_payload(payload)) + crypto.SIG_LEN


def protect(cover: Cover, filename: str, text: str, k: int, passphrase: str,
            priv, encrypt_message: bool = False, reps: int = 1, version: int = VERSION):
    if not 1 <= k <= 8:
        raise ValueError("LSB count must be 1-8")
    if not passphrase:
        raise ValueError("A stego key (passphrase) is required")
    if reps < 1 or reps % 2 == 0 or reps > MAX_REPS:
        raise ValueError(f"Repetition must be an odd number from 1 to {MAX_REPS}")
    if version == 1 and reps != 1:
        raise ValueError("Robust mode needs format version 2")

    master = crypto.master_key(passphrase)
    n = len(cover.carrier)
    start = crypto.derive_start(master, n, cover.kind)

    if encrypt_message:
        message = {"enc": True, **crypto.encrypt(master, text.encode("utf-8"))}
    else:
        message = {"enc": False, "text": text}

    signer = crypto.public_key_fingerprint(priv.public_key())
    # The hash depends on which bits we'll overwrite, which depends on the body
    # length. A SHA-256 hex digest is always 64 chars, so a placeholder gives us
    # the final length up front.
    payload = build_payload(cover.kind, filename, "0" * 64, k, message, signer)
    body_len = len(encode_payload(payload)) + crypto.SIG_LEN

    hu = header_units(reps)
    needed = hu + lsb.units_needed(body_len * reps, k)
    if needed > n:
        extra = f" with x{reps} repetition" if reps > 1 else ""
        raise CapacityError(
            f"Payload needs {body_len:,} bytes but this cover only holds "
            f"{capacity_bytes(cover, k, reps):,} bytes at {k} LSB(s){extra}. "
            f"Use more LSBs, a bigger cover, or a shorter message.")

    payload["media_hash"] = media_hash(cover, start, k, body_len, reps)
    payload_bytes = encode_payload(payload)
    body = payload_bytes + crypto.sign(priv, payload_bytes)
    if version >= 2:
        # without this mask the LSBs spell out the JSON for anyone who looks
        body = _xor(body, crypto.keystream(master, "body-mask", len(body)))

    header = _xor(pack_header(k, body_len, reps, version),
                  crypto.subkey(master, "header-mask", HEADER_LEN))
    copies = ROBUST_HEADER_COPIES if reps > 1 else 1

    stego = cover.copy()
    lsb.embed(stego.carrier, robust.spread(header, copies), start, 1)
    lsb.embed(stego.carrier, robust.spread(body, reps), (start + hu) % n, k)

    info = {
        "start": start,
        "k": k,
        "reps": reps,
        "version": version,
        "body_len": body_len,
        "units_used": needed,
        "carrier_units": n,
        "percent_used": 100 * needed / n,
    }
    return stego, payload, info


def verify(cover: Cover, passphrase: str, pub, start_override: int | None = None) -> VerifyResult:
    try:
        return _verify(cover, passphrase, pub, start_override)
    except Exception as e:  # anything unexpected shouldn't crash the GUI
        return VerifyResult(CANNOT_VERIFY, f"Verification failed with an error: {e}")


def _read_header(carrier, start, mask):
    # Robust files keep 7 copies of the header, so try a majority vote over 7
    # first. On a normal file those "copies" are really body bits, the vote comes
    # out as rubbish and fails the checks, and we fall back to the single copy.
    n = len(carrier)
    if n >= ROBUST_HEADER_COPIES * HEADER_UNITS:
        raw = lsb.extract(carrier, start, HEADER_LEN * ROBUST_HEADER_COPIES, 1)
        hdr = unpack_header(_xor(robust.vote(raw, HEADER_LEN, ROBUST_HEADER_COPIES), mask))
        if hdr is not None and hdr.reps > 1:
            return hdr
    hdr = unpack_header(_xor(lsb.extract(carrier, start, HEADER_LEN, 1), mask))
    return hdr if hdr is not None and hdr.reps == 1 else None


def _verify(cover, passphrase, pub, start_override):
    n = len(cover.carrier)
    if n < HEADER_UNITS + 8:
        return VerifyResult(CANNOT_VERIFY, "File is too small to hold a payload.")
    if not passphrase:
        return VerifyResult(CANNOT_VERIFY, "No stego key given, can't locate the payload.")

    master = crypto.master_key(passphrase)
    start = crypto.derive_start(master, n, cover.kind) if start_override is None else start_override % n
    details = {"start": start, "carrier_units": n}

    hdr = _read_header(cover.carrier, start, crypto.subkey(master, "header-mask", HEADER_LEN))
    if hdr is None:
        return VerifyResult(WRONG_START, (
            f"No valid header at offset {start}. Either the stego key is wrong (so the "
            "derived start location is wrong) or this file has no payload."), details=details)

    k, body_len, reps = hdr.k, hdr.body_len, hdr.reps
    hu = header_units(reps)
    details.update(k=k, body_len=body_len, reps=reps, version=hdr.version, header_units=hu)
    if body_len <= crypto.SIG_LEN or hu + lsb.units_needed(body_len * reps, k) > n:
        return VerifyResult(PAYLOAD_MISSING,
                            "Header found but the payload body is missing or truncated.",
                            details=details)

    raw = lsb.extract(cover.carrier, (start + hu) % n, body_len * reps, k)
    body = robust.vote(raw, body_len, reps)
    if hdr.version >= 2:
        body = _xor(body, crypto.keystream(master, "body-mask", body_len))
    payload_bytes, sig = body[:-crypto.SIG_LEN], body[-crypto.SIG_LEN:]

    if not crypto.verify(pub, sig, payload_bytes):
        return VerifyResult(SIGNATURE_INVALID, (
            "Signature check failed. The embedded payload was altered, or it was "
            "signed by a different key than the public key provided."), details=details)

    payload = decode_payload(payload_bytes)
    current = media_hash(cover, start, k, body_len, reps)
    details.update(expected_hash=payload["media_hash"], current_hash=current)

    msg = payload["message"]
    if msg.get("enc"):
        plain = crypto.decrypt(master, msg)
        text = plain.decode("utf-8") if plain is not None else None
    else:
        text = msg.get("text")

    if current != payload["media_hash"]:
        return VerifyResult(TAMPERED, (
            "Signature is valid, but the media hash doesn't match. The file was "
            "modified after it was protected."), payload, text, details)

    # Replay check from M3, see core/replay.py
    if replay.seen_before(payload["nonce"]):
        return VerifyResult(REPLAY_DETECTED, (
            "Signature and hash are valid, but this exact payload has been verified "
            "before. This file may be a replay of an earlier legitimate message. If you "
            "are only re-checking a file you already accepted, clear the replay history "
            "and verify again."),
            payload, text, details)
    replay.record(payload["nonce"])

    return VerifyResult(AUTHENTIC, "Signature valid and media hash matches.",
                        payload, text, details)
