"""Robust mode: a repetition code with majority voting.

Every bit is stored `reps` times. The copies are laid out one whole copy after
another (copy 1 of the data, then copy 2, ...), so the copies of any one bit
sit len(data) * 8 bits apart. A scratch or a burst of noise in one place then
only hits one copy of each bit, and the majority vote on read puts it right.

reps must be odd (3, 5, 7 ...) so the vote can never tie.
"""

import numpy as np


def spread(data: bytes, reps: int) -> bytes:
    # Repeating the bytes is the same as repeating the whole bit stream, which
    # is exactly the interleaved layout described above
    return data * reps


def vote(raw: bytes, nbytes: int, reps: int) -> bytes:
    """Undo spread(): for each bit, take whatever most of its copies say."""
    if reps == 1:
        return raw[:nbytes]
    bits = np.unpackbits(np.frombuffer(raw[:nbytes * reps], dtype=np.uint8))
    copies = bits.reshape(reps, nbytes * 8)        # one row per copy
    return np.packbits(copies.sum(axis=0) > reps // 2).tobytes()
