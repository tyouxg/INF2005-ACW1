"""Statistical Steganalysis: detect payload presence via chi-square pairs-of-values testing.

Evaluates carriers purely through statistical pair distributions (Westfeld & Pfitzmann, 2000)
without attempting to decode or parse embedded text.
"""

import math
from dataclasses import dataclass, field

import numpy as np

CHUNK = 1024           # carrier bytes per analysis window
THRESHOLD = 0.90       # p-value threshold above which a chunk is flagged as embedded
DETECTION_SHARE = 0.70 # fraction of embedded chunks required to trigger a positive verdict


@dataclass
class ScanResult:
    found: bool
    k: int | None = None
    start: int | None = None              # first carrier byte of the suspicious span
    end: int | None = None                # end carrier byte of the suspicious span
    carrier_units: int = 0
    text: str = ""                        # diagnostic readout instead of decoded text
    profile: np.ndarray = field(default_factory=lambda: np.zeros(0))   # p-values across carrier bytes
    chi_square_embedded: float = 0.0      # overall share of chunks scoring above THRESHOLD


def chi_square_pvalue(values: np.ndarray) -> float | None:
    """Westfeld & Pfitzmann's pairs-of-values test on one chunk of bytes."""
    hist = np.bincount(values, minlength=256).astype(float)
    even, odd = hist[0::2], hist[1::2]
    expected = (even + odd) / 2
    used = expected > 4
    if used.sum() < 2:
        return None
    chi = float(((even[used] - expected[used]) ** 2 / expected[used]).sum())
    df = int(used.sum()) - 1
    # Wilson-Hilferty transformation to obtain a standard normal z-score
    z = ((chi / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    return 0.5 * math.erfc(z / math.sqrt(2))


def scan(cover, chunk: int = CHUNK) -> ScanResult:
    """Evaluates the carrier using localized chi-square tests without decoding."""
    car = cover.carrier
    n = len(car)
    profile = np.zeros(n, dtype=float)
    
    num_chunks = n // chunk
    if num_chunks == 0:
        return ScanResult(False, carrier_units=n, profile=profile)

    p_values = []
    suspicious_chunk_indices = []

    for idx in range(num_chunks):
        c_start = idx * chunk
        c_end = c_start + chunk
        p = chi_square_pvalue(car[c_start:c_end])
        score = p if p is not None else 0.0
        p_values.append(score)
        profile[c_start:c_end] = score
        
        if score >= THRESHOLD:
            suspicious_chunk_indices.append(idx)

    # Pad remaining trailing bytes with the final chunk's score
    if n % chunk != 0:
        profile[num_chunks * chunk:] = p_values[-1] if p_values else 0.0

    chi_share = float(np.mean([p >= THRESHOLD for p in p_values])) if p_values else 0.0
    found = chi_share >= DETECTION_SHARE

    start_byte = None
    end_byte = None
    if suspicious_chunk_indices:
        start_byte = suspicious_chunk_indices[0] * chunk
        end_byte = min(n, (suspicious_chunk_indices[-1] + 1) * chunk)

    summary = (
        f"Statistical Analysis Summary:\n"
        f"- Total Carrier Units: {n:,} bytes\n"
        f"- Total 1 KB Chunks Evaluated: {num_chunks:,}\n"
        f"- Chunks Exceeding Threshold (p >= {THRESHOLD:.2f}): {len(suspicious_chunk_indices):,} ({chi_share * 100:.1f}%)\n"
        f"- Method: Pairs-of-values chi-square test with Wilson-Hilferty transformation\n"
        f"- Decoding Status: Bypassed (purely statistical detection)"
    )

    return ScanResult(
        found=found,
        k=None,
        start=start_byte,
        end=end_byte,
        carrier_units=n,
        text=summary,
        profile=profile,
        chi_square_embedded=chi_share
    )