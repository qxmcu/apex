"""
ApexCompress - The Adaptive Tournament Multi-Engine Compression System.
"""

from typing import Any, Dict, List, Optional, Union

from apex.archive import (
    DEFAULT_BLOCK_SIZE,
    FLAG_ENCRYPTED,
    FLAG_RECOVERY,
    ArchiveManifest,
    compress_archive,
    decompress_archive,
    read_archive_header,
    repair_archive,
    test_archive,
)
from apex.analyzer import analyze_file
from apex.benchmark import run_benchmark
from apex.diff import diff_archives
from apex.engine import Mode, compress_chunk, decompress_chunk

__version__ = "1.2.0"
__author__ = "Apex Compression Lab"


def compress(
    source: str,
    destination: Optional[str] = None,
    mode: Union[str, Mode] = "balanced",
    block_size: Optional[int] = None,
    password: Optional[str] = None,
    recovery: bool = False,
    cdc: bool = False,
    progress_callback: Optional[Any] = None,
    exclude: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compress a file or folder into an .apx archive."""
    if isinstance(mode, str):
        mode = Mode(mode.lower())
    if destination is None:
        destination = str(source) + ".apx"
    return compress_archive(
        source_path=str(source),
        output_archive_path=str(destination),
        mode=mode,
        block_size=block_size,
        password=password,
        recovery=recovery,
        cdc=cdc,
        progress_callback=progress_callback,
        exclude_patterns=exclude,
    )


def extract(
    archive: str,
    destination: Optional[str] = None,
    password: Optional[str] = None,
    include: Optional[List[str]] = None,
    progress_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """Extract an .apx archive with optional selective extraction patterns."""
    return decompress_archive(
        archive_path=str(archive),
        output_dir=str(destination) if destination else None,
        password=password,
        progress_callback=progress_callback,
        include_patterns=include,
    )


def test(archive: str, password: Optional[str] = None) -> Dict[str, Any]:
    """Verify archive integrity, CRC-32 checksums, and stream SHA-256."""
    return test_archive(archive_path=str(archive), password=password)


def repair(
    archive: str,
    destination: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """Self-heal a damaged .apx archive using Reed-Solomon parity records."""
    return repair_archive(
        archive_path=str(archive),
        output_repaired_path=str(destination) if destination else None,
        password=password,
    )


def diff(
    archive1: str,
    archive2: str,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare two archives by manifest metadata and file lists without decompressing."""
    return diff_archives(str(archive1), str(archive2), password=password)


def info(file_path: str):
    """Analyze file entropy, compressibility score, and theoretical Shannon limit."""
    return analyze_file(str(file_path))


def benchmark(data_or_path: Union[bytes, str], max_sample_mb: Optional[float] = 16.0):
    """Run tournament benchmark shootout against standard archivers."""
    if isinstance(data_or_path, str):
        if max_sample_mb is not None:
            limit = int(max_sample_mb * 1024 * 1024)
            with open(data_or_path, "rb") as f:
                data = f.read(limit)
        else:
            with open(data_or_path, "rb") as f:
                data = f.read()
    else:
        data = data_or_path
    return run_benchmark(data)


def compress_bytes(data: bytes, mode: Union[str, Mode] = "balanced") -> bytes:
    """In-memory tournament compression of raw byte buffer."""
    if not data:
        return bytes([0])
    if isinstance(mode, str):
        mode = Mode(mode.lower())
    res = compress_chunk(data, mode)
    return bytes([res.pipeline_id]) + res.data


def decompress_bytes(data: bytes) -> bytes:
    """In-memory decompression of byte buffer created with compress_bytes."""
    if not data:
        return b""
    pipeline_id = data[0]
    payload = data[1:]
    return decompress_chunk(payload, pipeline_id)


__all__ = [
    "__version__",
    "compress",
    "extract",
    "test",
    "repair",
    "diff",
    "info",
    "benchmark",
    "compress_bytes",
    "decompress_bytes",
    "Mode",
    "ArchiveManifest",
]
