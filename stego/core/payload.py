"""The verification payload (FR3) and the small header that points to it."""

import json
import os
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

MAGIC = b"SG"
# Version 2 XOR-masks the whole payload body, so the LSBs no longer spell out
# readable JSON (see core/steganalysis.py). Version 1 files are still readable.
VERSION = 2
SUPPORTED_VERSIONS = (1, 2)
HEADER_FMT = ">2sBBI"          # magic, version, k (+ repetition code on top), body length
HEADER_LEN = struct.calcsize(HEADER_FMT)
MAX_REPS = 15
TEAM_META = {"team": "P6-4", "tool": "INF2005-ACW1 stego"}


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


@dataclass
class Header:
    version: int
    k: int
    reps: int          # 1 = normal, 3/5/7... = robust mode repetition
    body_len: int


def pack_header(k: int, body_len: int, reps: int = 1, version: int = VERSION) -> bytes:
    # k only needs 4 bits (1-8), so the top 4 bits of that byte carry the
    # repetition count as (reps - 1) / 2. Old files have 0 there, i.e. reps = 1.
    return struct.pack(HEADER_FMT, MAGIC, version, k | ((reps - 1) // 2) << 4, body_len)


def unpack_header(raw: bytes) -> Header | None:
    """None if this doesn't look like our header."""
    magic, version, kbyte, body_len = struct.unpack(HEADER_FMT, raw)
    k, reps = kbyte & 0x0F, (kbyte >> 4) * 2 + 1
    if magic != MAGIC or version not in SUPPORTED_VERSIONS or not 1 <= k <= 8:
        return None
    if version == 1 and reps != 1:
        return None
    return Header(version, k, reps, body_len)
