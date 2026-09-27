"""Steganalysis: look at a file WITHOUT the stego key and ask "is something hidden here?"

Two methods:

1. The chi-square attack (Westfeld & Pfitzmann, 2000). LSB replacement pushes
   each pair of values (2i, 2i+1) towards equal counts, and the test measures how
   equal they are. It is the textbook method, but on real photos and audio the
   lowest bit is already noisy, so clean covers often look "embedded" too. We
   report it, but it can't tell our covers from our stego files.

2. A structure scan. For every LSB count k = 1..8 and every bit alignment, decode
   the low bits into bytes and look for long runs of readable text. Random noise
   is printable only ~38% of the time, so 60+ printable bytes in a row don't
   happen by chance. Printable alone isn't enough though: at k = 8 the "decoded"
   bytes are just the pixel values, and a dark photo is full of values in the
   printable range, even the '"' character (value 34). So a window only counts
   if it also looks like JSON: a few '"' characters AND mostly lowercase letters
   (keys, hex digests, words), where pixel values give mostly capitals and symbols. Version 1 payloads are plain JSON, so this finds them, shows
   k and the location, and even reads the text out, all without the key. Version 2
   masks the body with a key-derived stream, so there's nothing left to find.
"""

import math
from dataclasses import dataclass, field

import numpy as np

WINDOW = 64            # decoded bytes per window
THRESHOLD = 0.95       # share of printable bytes that counts as "text"
MIN_QUOTES = 3         # JSON keys and strings are quoted
MIN_LOWER = 0.40       # and JSON is mostly lowercase, dark pixel values mostly aren't

# printable ASCII plus tab/newline/carriage return
PRINTABLE = np.zeros(256, dtype=bool)
PRINTABLE[0x20:0x7F] = True
PRINTABLE[[0x09, 0x0A, 0x0D]] = True


@dataclass
class ScanResult:
    found: bool
    k: int | None = None                  # LSB count the text was found at
    start: int | None = None              # carrier index where the text starts
    end: int | None = None
    carrier_units: int = 0
    text: str = ""                        # what we managed to read, without the key
    profile: np.ndarray = field(default_factory=lambda: np.zeros(0))   # best score along the file
    chi_square_embedded: float = 0.0      # share of chunks the chi-square test calls "embedded"


def chi_square_pvalue(values: np.ndarray) -> float | None:
    """Westfeld & Pfitzmann's pairs-of-values test on one chunk of bytes.

    Near 1 means the pairs (2i, 2i+1) are suspiciously equal, i.e. "looks embedded".
    """
    hist = np.bincount(values, minlength=256).astype(float)
    even, odd = hist[0::2], hist[1::2]
    expected = (even + odd) / 2
    used = expected > 4                       # the usual rule for chi-square cells
    if used.sum() < 2:
        return None
    chi = float(((even[used] - expected[used]) ** 2 / expected[used]).sum())
    df = int(used.sum()) - 1
    # Wilson-Hilferty: turns chi-square into a normal z-score, so we don't need scipy
    z = ((chi / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    return 0.5 * math.erfc(z / math.sqrt(2))


def chi_square_share(carrier: np.ndarray, chunk: int = 1024) -> float:
    ps = [chi_square_pvalue(carrier[i:i + chunk]) for i in range(0, len(carrier) - chunk + 1, chunk)]
    ps = [p for p in ps if p is not None]
    return float(np.mean([p > 0.9 for p in ps])) if ps else 0.0


def _decode(carrier: np.ndarray, k: int, offset: int) -> np.ndarray:
    # Same bit order as lsb.embed: the low k bits of each byte, most significant first
    bits = np.unpackbits((carrier & ((1 << k) - 1))[:, None], axis=1)[:, 8 - k:].reshape(-1)
    m = (len(bits) - offset) // 8
    return np.packbits(bits[offset:offset + 8 * m].reshape(m, 8), axis=1).reshape(-1)


def scan(cover) -> ScanResult:
    car = cover.carrier
    n = len(car)
    profile = np.zeros(n)
    best = None                                   # (count of text windows, k, offset, score array)
    for k in range(1, 9):
        for offset in range(8):
            decoded = _decode(car, k, offset)
            if len(decoded) < WINDOW:
                continue
            printable = np.concatenate([[0], np.cumsum(PRINTABLE[decoded])])
            quotes = np.concatenate([[0], np.cumsum(decoded == ord('"'))])
            lower = np.concatenate([[0], np.cumsum((decoded >= ord("a")) & (decoded <= ord("z")))])
            share = (printable[WINDOW:] - printable[:-WINDOW]) / WINDOW   # sliding share of printable bytes
            json_like = (((quotes[WINDOW:] - quotes[:-WINDOW]) >= MIN_QUOTES)
                         & ((lower[WINDOW:] - lower[:-WINDOW]) >= MIN_LOWER * WINDOW))
            score = np.where(json_like, share, 0.0)
            hits = int((score >= THRESHOLD).sum())
            # map each window back to the carrier byte it starts at, for the plot
            pos = (offset + 8 * np.arange(len(score))) // k
            np.maximum.at(profile, pos, score)
            if hits and (best is None or hits > best[0]):
                best = (hits, k, offset, score, decoded)

    result = ScanResult(False, carrier_units=n, profile=profile,
                        chi_square_embedded=chi_square_share(car))
    if best is None:
        return result

    _, k, offset, score, decoded = best
    windows = np.flatnonzero(score >= THRESHOLD)
    first, last = windows[0], windows[-1] + WINDOW
    # show the odd non-printable byte as "." so the text stays readable
    text = "".join(chr(b) if PRINTABLE[b] and b >= 0x20 else "." for b in decoded[first:last])
    to_carrier = lambda j: (offset + 8 * int(j)) // k
    result.found, result.k = True, k
    result.start, result.end = to_carrier(first), to_carrier(last)
    result.text = text
    return result
