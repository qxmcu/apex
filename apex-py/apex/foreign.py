"""
Foreign Archive Support for ApexCompress.
Provides magic-based auto-detection, listing, and extraction for ZIP and TAR.GZ archives.
Write operations and self-healing repair are strictly restricted to native .apx containers.
"""

import fnmatch
import json
import os
import stat
import sys
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from apex.benchmark import format_bytes

BOLD = "\033[1m"
RESET = "\033[0m"
GREEN = "\033[32m"
CYAN = "\033[36m"
RED = "\033[31m"


def is_foreign_archive(path_or_file: Union[str, Path]) -> Optional[str]:
    """
    Detects if the file at path is a supported foreign archive (zip, tar.gz, tar).
    Returns 'zip', 'tar_gz', 'tar', or None if it is an Apex archive or unknown.
    """
    p = Path(path_or_file)
    if not p.is_file():
        return None

    try:
        with open(p, "rb") as f:
            magic = f.read(512)
    except OSError:
        return None

    if len(magic) < 4:
        return None

    # Native APEX archive
    if magic.startswith(b"APEX\x01\x00\x00\x00"):
        return None

    # ZIP format
    if magic.startswith(b"PK\x03\x04") or magic.startswith(b"PK\x05\x06") or magic.startswith(b"PK\x07\x08"):
        if zipfile.is_zipfile(p):
            return "zip"

    # GZIP (often tar.gz)
    if magic.startswith(b"\x1f\x8b"):
        if tarfile.is_tarfile(p):
            return "tar_gz"

    # Uncompressed TAR or other tarfile format
    if len(magic) >= 262 and magic[257:262] == b"ustar":
        return "tar"

    if tarfile.is_tarfile(p):
        return "tar"

    return None


def should_extract(rel_path: str, include_patterns: Optional[List[str]]) -> bool:
    """Matches relative path against include patterns."""
    if not include_patterns:
        return True
    norm = rel_path.replace("\\", "/").rstrip("/")
    basename = norm.split("/")[-1] if norm else ""
    for pat in include_patterns:
        pat_norm = pat.replace("\\", "/").rstrip("/")
        if norm == pat_norm or norm.startswith(pat_norm + "/"):
            return True
        if fnmatch.fnmatch(norm, pat_norm) or fnmatch.fnmatch(basename, pat_norm):
            return True
    return False


def list_foreign(archive_path: str, as_json: bool = False, quiet: bool = False) -> Dict:
    """Lists files in a foreign archive (zip or tar.gz) to stdout or JSON."""
    fmt = is_foreign_archive(archive_path)
    if not fmt:
        raise ValueError(f"Not a recognized foreign archive format: {archive_path}")

    p = Path(archive_path).resolve()
    file_records = []
    total_uncompressed = 0

    if fmt == "zip":
        with zipfile.ZipFile(p, "r") as z:
            for info in z.infolist():
                # Extract mode and mtime
                is_dir = info.is_dir()
                mode = (info.external_attr >> 16) & 0o7777 if info.external_attr else (0o755 if is_dir else 0o644)
                dt = info.date_time
                try:
                    mtime = time.mktime(dt + (0, 0, -1))
                except Exception:
                    mtime = time.time()
                file_records.append({
                    "path": info.filename,
                    "size": info.file_size,
                    "mode": mode,
                    "mtime": mtime,
                    "is_dir": is_dir,
                })
                total_uncompressed += info.file_size
    else:
        with tarfile.open(p, "r:*") as t:
            for member in t.getmembers():
                is_dir = member.isdir()
                file_records.append({
                    "path": member.name,
                    "size": member.size,
                    "mode": member.mode,
                    "mtime": member.mtime,
                    "is_dir": is_dir,
                })
                total_uncompressed += member.size

    result = {
        "archive": str(p.name),
        "format": fmt,
        "is_foreign": True,
        "total_files": len(file_records),
        "total_uncompressed_size": total_uncompressed,
        "files": file_records,
    }

    if as_json:
        print(json.dumps(result, indent=2))
        return result

    if not quiet:
        type_desc = "ZIP Archive" if fmt == "zip" else "TAR.GZ Archive" if fmt == "tar_gz" else "TAR Archive"
        print(f"{BOLD}Archive:{RESET}     {p.name}")
        print(f"{BOLD}Type:{RESET}        {type_desc} (Foreign Format)")
        print(f"{BOLD}Total Files:{RESET} {len(file_records)}")
        print(f"{BOLD}Total Size:{RESET}  {format_bytes(total_uncompressed)}\n")
        print(f"{'Mode':<10} | {'Size':<12} | {'Modified':<20} | {'Filename':<35}")
        print("-" * 82)
        for f in file_records:
            mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f["mtime"]))
            mode_str = oct(f["mode"])[-4:]
            print(f"{mode_str:<10} | {format_bytes(f['size']):<12} | {mtime_str:<20} | {f['path']}")

    return result


def extract_foreign(
    archive_path: str,
    output_dir: Optional[str] = None,
    include_patterns: Optional[List[str]] = None,
    quiet: bool = False,
) -> Dict:
    """Safely extracts members from a foreign archive (zip or tar.gz)."""
    fmt = is_foreign_archive(archive_path)
    if not fmt:
        raise ValueError(f"Not a recognized foreign archive format: {archive_path}")

    p = Path(archive_path).resolve()
    out_base = Path(output_dir).resolve() if output_dir else Path.cwd()
    out_base.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    extracted_count = 0
    extracted_bytes = 0

    if fmt == "zip":
        with zipfile.ZipFile(p, "r") as z:
            for info in z.infolist():
                rel_path = info.filename.replace("\\", "/").strip("/")
                if not rel_path or rel_path.startswith("/") or ".." in rel_path.split("/"):
                    continue
                if not should_extract(rel_path, include_patterns):
                    continue

                dest_target = out_base / rel_path
                if info.is_dir():
                    dest_target.mkdir(parents=True, exist_ok=True)
                    continue

                dest_target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(dest_target, "wb") as dst:
                    while True:
                        buf = src.read(1024 * 1024)
                        if not buf:
                            break
                        dst.write(buf)
                        extracted_bytes += len(buf)

                # Set mtime and mode if present
                try:
                    dt = info.date_time
                    mtime = time.mktime(dt + (0, 0, -1))
                    os.utime(dest_target, (mtime, mtime))
                except Exception:
                    pass
                if info.external_attr:
                    mode = (info.external_attr >> 16) & 0o777
                    if mode:
                        try:
                            os.chmod(dest_target, mode)
                        except OSError:
                            pass
                extracted_count += 1
    else:
        with tarfile.open(p, "r:*") as t:
            for member in t.getmembers():
                rel_path = member.name.replace("\\", "/").strip("/")
                if not rel_path or rel_path.startswith("/") or ".." in rel_path.split("/"):
                    continue
                if not should_extract(rel_path, include_patterns):
                    continue

                dest_target = out_base / rel_path
                if member.isdir():
                    dest_target.mkdir(parents=True, exist_ok=True)
                    continue

                dest_target.parent.mkdir(parents=True, exist_ok=True)
                if member.issym():
                    try:
                        if dest_target.is_symlink() or dest_target.exists():
                            dest_target.unlink()
                        os.symlink(member.linkname, dest_target)
                    except OSError:
                        pass
                elif member.isreg():
                    src_f = t.extractfile(member)
                    if src_f:
                        with open(dest_target, "wb") as dst:
                            while True:
                                buf = src_f.read(1024 * 1024)
                                if not buf:
                                    break
                                dst.write(buf)
                                extracted_bytes += len(buf)
                    try:
                        os.utime(dest_target, (member.mtime, member.mtime))
                        os.chmod(dest_target, member.mode)
                    except OSError:
                        pass
                    extracted_count += 1

    elapsed = time.perf_counter() - t0
    return {
        "status": "SUCCESS",
        "format": fmt,
        "is_foreign": True,
        "files_extracted": extracted_count,
        "total_uncompressed_bytes": extracted_bytes,
        "elapsed": elapsed,
    }


def test_foreign(archive_path: str) -> Dict:
    """Verifies integrity of foreign archive."""
    fmt = is_foreign_archive(archive_path)
    if not fmt:
        raise ValueError(f"Not a recognized foreign archive format: {archive_path}")

    p = Path(archive_path).resolve()
    t0 = time.perf_counter()
    total_files = 0
    total_bytes = 0

    if fmt == "zip":
        with zipfile.ZipFile(p, "r") as z:
            corrupt = z.testzip()
            if corrupt is not None:
                raise ValueError(f"Corrupted ZIP entry detected: {corrupt}")
            for info in z.infolist():
                total_files += 1
                total_bytes += info.file_size
    else:
        with tarfile.open(p, "r:*") as t:
            for member in t.getmembers():
                total_files += 1
                total_bytes += member.size
                if member.isreg():
                    f = t.extractfile(member)
                    if f:
                        while f.read(1024 * 1024):
                            pass

    elapsed = time.perf_counter() - t0
    return {
        "status": "PASSED",
        "archive": str(p),
        "format": fmt,
        "is_foreign": True,
        "total_files": total_files,
        "total_uncompressed_bytes": total_bytes,
        "elapsed": elapsed,
    }


test_foreign.__test__ = False
