"""Protect (sender side) and verify (receiver side) pipelines.

Layout inside the carrier, starting at the key-derived offset and wrapping
around the end if needed:

    [ header: 8 bytes, 1 LSB per unit, XOR-masked ][ body: payload JSON + signature, k LSBs per unit ]
"""

from dataclasses import dataclass, field

import numpy as np

from . import crypto, lsb, replay
from .media import Cover
from .payload import (HEADER_LEN, build_payload, decode_payload, encode_payload,
                      pack_header, unpack_header)

HEADER_UNITS = HEADER_LEN * 8

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
    return bytes(x ^ y for x, y in zip(a, b))


def _region(n: int, start: int, k: int, body_len: int) -> np.ndarray:
    total = HEADER_UNITS + lsb.units_needed(body_len, k)
    return (start + np.arange(total)) % n


def media_hash(cover: Cover, start: int, k: int, body_len: int) -> str:
    """SHA-256 of the file with only our embedding bits cleared.

    Sender computes this on the cover, receiver on the stego file; both give the
    same value unless something outside those bits was changed.
    """
    buf = cover.data.copy()
    car = cover.carrier_of(buf)
    idx = _region(len(car), start, k, body_len)
    car[idx] &= np.uint8((0xFF << k) & 0xFF)
    params = "|".join(f"{key}={cover.params[key]}" for key in sorted(cover.params))
    return crypto.sha256_hex(f"{cover.kind}|{params}|".encode() + buf.tobytes())


def capacity_bytes(cover: Cover, k: int) -> int:
    """How many body bytes (payload + signature) fit at this LSB setting."""
    return max(0, (len(cover.carrier) - HEADER_UNITS) * k // 8)


def protect(cover: Cover, filename: str, text: str, k: int, passphrase: str,
            priv, encrypt_message: bool = False):
    if not 1 <= k <= 8:
        raise ValueError("LSB count must be 1-8")
    if not passphrase:
        raise ValueError("A stego key (passphrase) is required")

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

    needed = HEADER_UNITS + lsb.units_needed(body_len, k)
    if needed > n:
        raise CapacityError(
            f"Payload needs {body_len:,} bytes but this cover only holds "
            f"{capacity_bytes(cover, k):,} bytes at {k} LSB(s). "
            f"Use more LSBs, a bigger cover, or a shorter message.")

    payload["media_hash"] = media_hash(cover, start, k, body_len)
    payload_bytes = encode_payload(payload)
    body = payload_bytes + crypto.sign(priv, payload_bytes)

    stego = cover.copy()
    header = _xor(pack_header(k, body_len), crypto.subkey(master, "header-mask", HEADER_LEN))
    lsb.embed(stego.carrier, header, start, 1)
    lsb.embed(stego.carrier, body, (start + HEADER_UNITS) % n, k)

    info = {
        "start": start,
        "k": k,
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


def _verify(cover, passphrase, pub, start_override):
    n = len(cover.carrier)
    if n < HEADER_UNITS + 8:
        return VerifyResult(CANNOT_VERIFY, "File is too small to hold a payload.")
    if not passphrase:
        return VerifyResult(CANNOT_VERIFY, "No stego key given, can't locate the payload.")

    master = crypto.master_key(passphrase)
    start = crypto.derive_start(master, n, cover.kind) if start_override is None else start_override % n
    details = {"start": start, "carrier_units": n}

    raw = lsb.extract(cover.carrier, start, HEADER_LEN, 1)
    parsed = unpack_header(_xor(raw, crypto.subkey(master, "header-mask", HEADER_LEN)))
    if parsed is None:
        return VerifyResult(WRONG_START, (
            f"No valid header at offset {start}. Either the stego key is wrong (so the "
            "derived start location is wrong) or this file has no payload."), details=details)

    k, body_len = parsed
    details.update(k=k, body_len=body_len)
    if body_len <= crypto.SIG_LEN or HEADER_UNITS + lsb.units_needed(body_len, k) > n:
        return VerifyResult(PAYLOAD_MISSING,
                            "Header found but the payload body is missing or truncated.",
                            details=details)

    body = lsb.extract(cover.carrier, (start + HEADER_UNITS) % n, body_len, k)
    payload_bytes, sig = body[:-crypto.SIG_LEN], body[-crypto.SIG_LEN:]

    if not crypto.verify(pub, sig, payload_bytes):
        return VerifyResult(SIGNATURE_INVALID, (
            "Signature check failed. The embedded payload was altered, or it was "
            "signed by a different key than the public key provided."), details=details)

    payload = decode_payload(payload_bytes)
    current = media_hash(cover, start, k, body_len)
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
            "before. This file may be a replay of an earlier legitimate message."),
            payload, text, details)
    replay.record(payload["nonce"])

    return VerifyResult(AUTHENTIC, "Signature valid and media hash matches.",
                        payload, text, details)
