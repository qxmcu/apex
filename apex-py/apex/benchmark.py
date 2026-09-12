"""
ApexCompress Benchmark Suite.
Races ApexCompress against standard industry engines (Gzip, Bzip2, XZ/LZMA, Zstandard, Brotli)
and presents an executive shootout comparison table.
"""

import gzip
import io
import os
import time
from dataclasses import dataclass
from typing import List, Optional

import bz2
import lzma
import zlib

try:
    import zstandard as zstd
    HAVE_ZSTD = True
except ImportError:
    HAVE_ZSTD = False

try:
    import brotli
    HAVE_BROTLI = True
except ImportError:
    HAVE_BROTLI = False

from apex.engine import Mode, compress_chunk, decompress_chunk
from apex.analyzer import analyze_data


@dataclass
class BenchmarkEntry:
    engine_name: str
    original_size: int
    compressed_size: int
    compression_ratio: float
    space_saved_pct: float
    compression_time_ms: float
    decompression_time_ms: float
    verified: bool


def format_bytes(size: int) -> str:
    """Formats raw bytes into human-readable notation."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size) < 1024.0:
            return f"{size:6.1f} {unit}"
        size /= 1024.0
    return f"{size:6.1f} TB"


def run_benchmark(data: bytes) -> List[BenchmarkEntry]:
    """Runs a full suite benchmark on the provided byte stream."""
    orig_len = len(data)
    results: List[BenchmarkEntry] = []

    # 1. Standard Deflate / Gzip (Level 9)
    try:
        t0 = time.perf_counter()
        c_gzip = gzip.compress(data, compresslevel=9)
        t_comp = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        d_gzip = gzip.decompress(c_gzip)
        t_decomp = (time.perf_counter() - t0) * 1000
        results.append(BenchmarkEntry(
            engine_name="Gzip (Deflate -9)",
            original_size=orig_len,
            compressed_size=len(c_gzip),
            compression_ratio=orig_len / len(c_gzip) if len(c_gzip) > 0 else 1.0,
            space_saved_pct=(1.0 - len(c_gzip) / orig_len) * 100.0 if orig_len > 0 else 0.0,
            compression_time_ms=t_comp,
            decompression_time_ms=t_decomp,
            verified=(d_gzip == data),
        ))
    except Exception:
        pass

    # 2. Bzip2 (Level 9)
    try:
        t0 = time.perf_counter()
        c_bz2 = bz2.compress(data, compresslevel=9)
        t_comp = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        d_bz2 = bz2.decompress(c_bz2)
        t_decomp = (time.perf_counter() - t0) * 1000
        results.append(BenchmarkEntry(
            engine_name="Bzip2 (Burrows-Wheeler -9)",
            original_size=orig_len,
            compressed_size=len(c_bz2),
            compression_ratio=orig_len / len(c_bz2) if len(c_bz2) > 0 else 1.0,
            space_saved_pct=(1.0 - len(c_bz2) / orig_len) * 100.0 if orig_len > 0 else 0.0,
            compression_time_ms=t_comp,
            decompression_time_ms=t_decomp,
            verified=(d_bz2 == data),
        ))
    except Exception:
        pass

    # 3. XZ / LZMA2 (Preset 9 Extreme)
    try:
        t0 = time.perf_counter()
        c_xz = lzma.compress(data, preset=9 | lzma.PRESET_EXTREME)
        t_comp = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        d_xz = lzma.decompress(c_xz)
        t_decomp = (time.perf_counter() - t0) * 1000
        results.append(BenchmarkEntry(
            engine_name="XZ / LZMA2 (Extreme -9e)",
            original_size=orig_len,
            compressed_size=len(c_xz),
            compression_ratio=orig_len / len(c_xz) if len(c_xz) > 0 else 1.0,
            space_saved_pct=(1.0 - len(c_xz) / orig_len) * 100.0 if orig_len > 0 else 0.0,
            compression_time_ms=t_comp,
            decompression_time_ms=t_decomp,
            verified=(d_xz == data),
        ))
    except Exception:
        pass

    # 4. Zstandard (Level 19)
    if HAVE_ZSTD:
        try:
            t0 = time.perf_counter()
            c_zstd = zstd.ZstdCompressor(level=19).compress(data)
            t_comp = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            d_zstd = zstd.ZstdDecompressor().decompress(c_zstd)
            t_decomp = (time.perf_counter() - t0) * 1000
            results.append(BenchmarkEntry(
                engine_name="Zstandard (Level 19)",
                original_size=orig_len,
                compressed_size=len(c_zstd),
                compression_ratio=orig_len / len(c_zstd) if len(c_zstd) > 0 else 1.0,
                space_saved_pct=(1.0 - len(c_zstd) / orig_len) * 100.0 if orig_len > 0 else 0.0,
                compression_time_ms=t_comp,
                decompression_time_ms=t_decomp,
                verified=(d_zstd == data),
            ))
        except Exception:
            pass

    # 5. Brotli (Level 11)
    if HAVE_BROTLI:
        try:
            t0 = time.perf_counter()
            c_br = brotli.compress(data, quality=11, lgwin=24)
            t_comp = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            d_br = brotli.decompress(c_br)
            t_decomp = (time.perf_counter() - t0) * 1000
            results.append(BenchmarkEntry(
                engine_name="Brotli (Quality 11)",
                original_size=orig_len,
                compressed_size=len(c_br),
                compression_ratio=orig_len / len(c_br) if len(c_br) > 0 else 1.0,
                space_saved_pct=(1.0 - len(c_br) / orig_len) * 100.0 if orig_len > 0 else 0.0,
                compression_time_ms=t_comp,
                decompression_time_ms=t_decomp,
                verified=(d_br == data),
            ))
        except Exception:
            pass

    # 6. ApexCompress FAST
    try:
        t0 = time.perf_counter()
        c_apex_fast = compress_chunk(data, mode=Mode.FAST)
        t_comp = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        d_apex_fast = decompress_chunk(c_apex_fast.data, c_apex_fast.pipeline_id)
        t_decomp = (time.perf_counter() - t0) * 1000
        results.append(BenchmarkEntry(
            engine_name="ApexCompress (Fast)",
            original_size=orig_len,
            compressed_size=c_apex_fast.compressed_len,
            compression_ratio=orig_len / c_apex_fast.compressed_len if c_apex_fast.compressed_len > 0 else 1.0,
            space_saved_pct=(1.0 - c_apex_fast.compressed_len / orig_len) * 100.0 if orig_len > 0 else 0.0,
            compression_time_ms=t_comp,
            decompression_time_ms=t_decomp,
            verified=(d_apex_fast == data),
        ))
    except Exception:
        pass

    # 7. ApexCompress BALANCED
    try:
        t0 = time.perf_counter()
        c_apex_bal = compress_chunk(data, mode=Mode.BALANCED)
        t_comp = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        d_apex_bal = decompress_chunk(c_apex_bal.data, c_apex_bal.pipeline_id)
        t_decomp = (time.perf_counter() - t0) * 1000
        results.append(BenchmarkEntry(
            engine_name=f"ApexCompress (Balanced: {c_apex_bal.name})",
            original_size=orig_len,
            compressed_size=c_apex_bal.compressed_len,
            compression_ratio=orig_len / c_apex_bal.compressed_len if c_apex_bal.compressed_len > 0 else 1.0,
            space_saved_pct=(1.0 - c_apex_bal.compressed_len / orig_len) * 100.0 if orig_len > 0 else 0.0,
            compression_time_ms=t_comp,
            decompression_time_ms=t_decomp,
            verified=(d_apex_bal == data),
        ))
    except Exception:
        pass

    # 8. ApexCompress ULTRA
    try:
        t0 = time.perf_counter()
        c_apex_ultra = compress_chunk(data, mode=Mode.ULTRA)
        t_comp = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        d_apex_ultra = decompress_chunk(c_apex_ultra.data, c_apex_ultra.pipeline_id)
        t_decomp = (time.perf_counter() - t0) * 1000
        results.append(BenchmarkEntry(
            engine_name=f"ApexCompress (Ultra: {c_apex_ultra.name})",
            original_size=orig_len,
            compressed_size=c_apex_ultra.compressed_len,
            compression_ratio=orig_len / c_apex_ultra.compressed_len if c_apex_ultra.compressed_len > 0 else 1.0,
            space_saved_pct=(1.0 - c_apex_ultra.compressed_len / orig_len) * 100.0 if orig_len > 0 else 0.0,
            compression_time_ms=t_comp,
            decompression_time_ms=t_decomp,
            verified=(d_apex_ultra == data),
        ))
    except Exception:
        pass

    # Sort results by compressed size ascending (smallest output first)
    results.sort(key=lambda r: r.compressed_size)
    return results
