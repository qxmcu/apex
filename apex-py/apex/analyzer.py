"""
ApexCompress File & Entropy Analyzer.
Provides Shannon entropy, compressibility prediction, character classification,
and theoretical information-theoretic bounds for any byte sequence or file.
"""

import math
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class EntropyReport:
    total_bytes: int
    unique_bytes: int
    shannon_entropy: float          # 0.00 to 8.00 bits per byte
    theoretical_max_ratio: float    # 8.0 / entropy
    theoretical_min_size: int       # ceil(total_bytes * (entropy / 8.0))
    zero_bytes: int
    zero_ratio: float
    ascii_printable: int
    ascii_ratio: float
    high_bytes: int                 # > 127
    high_byte_ratio: float
    classification: str
    recommended_mode: str
    compressibility_pct: float       # 0% to 100%


def analyze_data(data: bytes) -> EntropyReport:
    """Computes full information-theoretic entropy profile for raw data."""
    n = len(data)
    if n == 0:
        return EntropyReport(
            total_bytes=0,
            unique_bytes=0,
            shannon_entropy=0.0,
            theoretical_max_ratio=float("inf"),
            theoretical_min_size=0,
            zero_bytes=0,
            zero_ratio=0.0,
            ascii_printable=0,
            ascii_ratio=0.0,
            high_bytes=0,
            high_byte_ratio=0.0,
            classification="Empty Data",
            recommended_mode="fast",
            compressibility_pct=100.0,
        )

    # Byte frequency count
    counts = Counter(data)
    unique_count = len(counts)

    # Shannon Entropy H(X) = -sum(P(x) * log2(P(x)))
    entropy = 0.0
    for count in counts.values():
        p = count / n
        entropy -= p * math.log2(p)

    # Clamp to [0.0, 8.0]
    entropy = max(0.0, min(8.0, entropy))

    theoretical_ratio = (8.0 / entropy) if entropy > 0.0001 else 999.99
    theoretical_min_bytes = math.ceil(n * (entropy / 8.0))
    compressibility = max(0.0, min(100.0, (1.0 - (entropy / 8.0)) * 100.0))

    zero_count = counts.get(0, 0)
    zero_ratio = zero_count / n

    # Printable ASCII: 32..126 + newline (\n), carriage return (\r), tab (\t)
    ascii_count = sum(
        counts.get(b, 0)
        for b in range(32, 127)
    ) + counts.get(10, 0) + counts.get(13, 0) + counts.get(9, 0)
    ascii_ratio = ascii_count / n

    # High bytes (> 127)
    high_count = sum(counts.get(b, 0) for b in range(128, 256))
    high_ratio = high_count / n

    # Classification heuristics
    if entropy > 7.95:
        classification = "High Entropy (Pre-compressed, encrypted, or random noise)"
        recommended_mode = "fast (or store)"
    elif zero_ratio > 0.40:
        classification = "Sparse Binary / Repeated Blocks"
        recommended_mode = "ultra (Delta / RLE Tournament)"
    elif ascii_ratio > 0.85:
        classification = "Natural Text / Source Code / Structured Markup"
        recommended_mode = "ultra (Brotli / LZMA Tournament)"
    elif high_ratio > 0.30 and entropy < 7.5:
        classification = "Compiled Binary Executable / Vector Data"
        recommended_mode = "ultra (Planar / Delta Tournament)"
    else:
        classification = "Mixed Binary Data"
        recommended_mode = "balanced"

    return EntropyReport(
        total_bytes=n,
        unique_bytes=unique_count,
        shannon_entropy=entropy,
        theoretical_max_ratio=theoretical_ratio,
        theoretical_min_size=theoretical_min_bytes,
        zero_bytes=zero_count,
        zero_ratio=zero_ratio,
        ascii_printable=ascii_count,
        ascii_ratio=ascii_ratio,
        high_bytes=high_count,
        high_byte_ratio=high_ratio,
        classification=classification,
        recommended_mode=recommended_mode,
        compressibility_pct=compressibility,
    )


def analyze_file(file_path: str, max_sample_bytes: int = 16 * 1024 * 1024) -> EntropyReport:
    """Reads up to max_sample_bytes of a file and returns an EntropyReport."""
    with open(file_path, "rb") as f:
        data = f.read(max_sample_bytes)
    return analyze_data(data)
