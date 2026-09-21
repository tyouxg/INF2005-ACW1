"""LSB replacement on a 1-D uint8 carrier.

Each carrier byte holds k bits of the message (k = 1..8). Bits are written
starting at `start` and wrap around to the beginning if they run past the end.
"""

import numpy as np


def units_needed(nbytes: int, k: int) -> int:
    return -(-nbytes * 8 // k)  # ceiling division


def _indices(carrier_len: int, start: int, count: int) -> np.ndarray:
    return (start + np.arange(count)) % carrier_len


def _to_chunks(data: bytes, k: int) -> np.ndarray:
    """Split bytes into k-bit numbers, most significant bit first."""
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    pad = (-len(bits)) % k
    bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    weights = 1 << np.arange(k - 1, -1, -1)
    return (bits.reshape(-1, k) * weights).sum(axis=1).astype(np.uint8)


def _from_chunks(chunks: np.ndarray, k: int, nbytes: int) -> bytes:
    shifts = np.arange(k - 1, -1, -1)
    bits = ((chunks[:, None] >> shifts) & 1).astype(np.uint8).reshape(-1)
    return np.packbits(bits[: nbytes * 8]).tobytes()


def embed(carrier: np.ndarray, data: bytes, start: int, k: int) -> np.ndarray:
    """Write data into the carrier in place. Returns the indices that were touched."""
    if not 1 <= k <= 8:
        raise ValueError("k must be between 1 and 8")
    chunks = _to_chunks(data, k)
    if len(chunks) > len(carrier):
        raise ValueError("data does not fit in carrier")
    idx = _indices(len(carrier), start, len(chunks))
    keep = np.uint8((0xFF << k) & 0xFF)
    carrier[idx] = (carrier[idx] & keep) | chunks
    return idx


def extract(carrier: np.ndarray, start: int, nbytes: int, k: int) -> bytes:
    n = units_needed(nbytes, k)
    if n > len(carrier):
        raise ValueError("asked for more bytes than the carrier can hold")
    idx = _indices(len(carrier), start, n)
    chunks = carrier[idx] & np.uint8((1 << k) - 1)
    return _from_chunks(chunks, k, nbytes)
