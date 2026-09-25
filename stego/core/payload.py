"""The verification payload (FR3) and the small header that points to it."""

import json
import os
import struct
import uuid
from datetime import datetime, timezone

MAGIC = b"SG"
VERSION = 1
HEADER_FMT = ">2sBBI"          # magic, version, k, body length
HEADER_LEN = struct.calcsize(HEADER_FMT)
TEAM_META = {"team": "P1-3", "tool": "INF2005-ACW1 stego"}


def build_payload(kind: str, filename: str, media_hash: str, k: int,
                  message: dict, signer_fp: str) -> dict:
    return {
        "v": VERSION,
        "media_id": uuid.uuid4().hex[:12],
        "kind": kind,
        "file": filename,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "media_hash": media_hash,
        "nonce": os.urandom(16).hex(),
        "lsb": k,
        "signer": signer_fp,
        "meta": TEAM_META,
        "message": message,
    }


def encode_payload(payload: dict) -> bytes:
    # sort_keys + no spaces keeps the byte form stable, which matters because
    # these exact bytes are what gets signed
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def decode_payload(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8"))


def pack_header(k: int, body_len: int) -> bytes:
    return struct.pack(HEADER_FMT, MAGIC, VERSION, k, body_len)


def unpack_header(raw: bytes):
    """Returns (k, body_len) or None if this doesn't look like our header."""
    magic, version, k, body_len = struct.unpack(HEADER_FMT, raw)
    if magic != MAGIC or version != VERSION or not 1 <= k <= 8:
        return None
    return k, body_len
