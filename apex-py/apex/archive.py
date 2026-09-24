"""
ApexCompress Container & Archive Manager.
Handles solid stream serialization, file/directory manifests, metadata preservation,
block-level CRC32 verification, content-aware deduplication, authenticated encryption,
self-healing recovery records, and cryptographic SHA-256 validation.
"""

import concurrent.futures
import fnmatch
import getpass
import hashlib
import json
import mmap
import os
import queue
import shutil
import struct
import sys
import threading
import time
import uuid
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Callable, Dict, Generator, List, Optional, Tuple

# Cross-platform O_BINARY for safe binary os.open()
O_BINARY = getattr(os, "O_BINARY", 0)

from apex.engine import (
    CompressedBlockResult,
    Mode,
    compress_chunk,
    decompress_chunk,
)
from apex.fastcdc import fastcdc_chunk_stream
from apex.security import derive_keys, encrypt_payload, decrypt_payload
from apex.recovery import generate_recovery_parity, heal_damaged_block

MAGIC_HEADER = b"APEX\x01\x00\x00\x00"
MAGIC_FOOTER = b"XPED"
FLAG_IS_DIR = 1 << 0
FLAG_SOLID = 1 << 1
FLAG_SHA256 = 1 << 2
FLAG_ENCRYPTED = 1 << 3
FLAG_RECOVERY = 1 << 4
PIPELINE_DEDUP_REF = 0xFE
EOF_PIPELINE_ID = 0xFF

DEFAULT_BLOCK_SIZE = 2 * 1024 * 1024       # 2MB chunks for balanced/ultra
DEFAULT_FAST_BLOCK_SIZE = 4 * 1024 * 1024  # 4MB chunks for fast mode (wider match window)


@dataclass
class FileEntry:
    rel_path: str
    size: int
    mode: int
    mtime: float
    offset: int = 0  # Offset within block (or uncompressed solid stream)
    is_symlink: bool = False
    link_target: str = ""
    is_dir: bool = False
    block_id: int = 0  # 0-indexed block ID where file starts
    length: int = 0  # Length in bytes
    solid_offset: int = 0  # Offset in uncompressed solid stream


@dataclass
class BlockMeta:
    block_id: int
    file_offset: int  # Byte position where 13-byte block header starts
    payload_offset: int  # Byte position where payload starts
    pipeline_id: int
    uncomp_len: int
    comp_len: int
    crc: int
    ref_idx: Optional[int] = None
    solid_start: int = 0
    solid_end: int = 0


@dataclass
class ArchiveManifest:
    is_dir: bool
    root_name: str
    total_uncompressed_size: int
    files: List[FileEntry] = field(default_factory=list)
    base_archive: str = ""
    reused_chunks: int = 0

    def to_json(self) -> str:
        payload = {
            "is_dir": self.is_dir,
            "root_name": self.root_name,
            "total_uncompressed_size": self.total_uncompressed_size,
            "files": [
                {
                    "path": f.rel_path,
                    "size": f.size,
                    "mode": f.mode,
                    "mtime": f.mtime,
                    "block_id": f.block_id,
                    "offset": f.offset,
                    "length": f.length if f.length or f.size == 0 else f.size,
                    "solid_offset": f.solid_offset,
                    "is_symlink": f.is_symlink,
                    "link_target": f.link_target,
                    "is_dir": f.is_dir,
                }
                for f in self.files
            ],
        }
        if self.base_archive:
            payload["base_archive"] = self.base_archive
        if self.reused_chunks:
            payload["reused_chunks"] = self.reused_chunks
        return json.dumps(payload)

    @classmethod
    def from_json(cls, json_str: str) -> "ArchiveManifest":
        data = json.loads(json_str)
        files = []
        for f in data.get("files", []):
            rel_path = f["path"]
            if rel_path.startswith("/") or rel_path.startswith("\\"):
                raise ValueError(f"Absolute path detected in archive manifest: {rel_path}")
            parts = rel_path.replace("\\", "/").split("/")
            if ".." in parts:
                raise ValueError(f"Path traversal detected in archive manifest: {rel_path}")
            
            size = f["size"]
            block_id = f.get("block_id", 0)
            offset = f.get("offset", 0)
            length = f.get("length", size)
            solid_offset = f.get("solid_offset", offset)

            files.append(FileEntry(
                rel_path=rel_path,
                size=size,
                mode=f.get("mode", 0o644),
                mtime=f.get("mtime", time.time()),
                offset=offset,
                is_symlink=f.get("is_symlink", False),
                link_target=f.get("link_target", ""),
                is_dir=f.get("is_dir", False),
                block_id=block_id,
                length=length,
                solid_offset=solid_offset,
            ))
            
        return cls(
            is_dir=data.get("is_dir", False),
            root_name=data.get("root_name", "archive"),
            total_uncompressed_size=data.get("total_uncompressed_size", 0),
            files=files,
            base_archive=data.get("base_archive", ""),
            reused_chunks=data.get("reused_chunks", 0),
        )


def should_exclude(rel_path: str, name: str, is_dir: bool, patterns: Optional[List[str]]) -> bool:
    """Checks if a file or directory matches any exclusion glob patterns."""
    if not patterns:
        return False
    norm_rel = rel_path.replace("\\", "/").strip("/")
    parts = norm_rel.split("/") if norm_rel else []
    for pat in patterns:
        pat_norm = pat.replace("\\", "/").strip("/")
        # Check against entry name directly (e.g. pat=".git", name=".git" or pat="*.log")
        if fnmatch.fnmatch(name, pat_norm):
            return True
        # Check if any path component matches (e.g. pat=".git", parts=["sub", ".git", "file"])
        if any(fnmatch.fnmatch(part, pat_norm) for part in parts):
            return True
        # Check against full relative path
        if fnmatch.fnmatch(norm_rel, pat_norm):
            return True
        # Check prefix match for directory exclusion
        if fnmatch.fnmatch(norm_rel, f"{pat_norm}/*") or fnmatch.fnmatch(norm_rel, f"*/{pat_norm}/*"):
            return True
    return False


def build_manifest(
    target_path: str,
    chunk_size: int = DEFAULT_FAST_BLOCK_SIZE,
    exclude_patterns: Optional[List[str]] = None,
) -> Tuple[ArchiveManifest, Generator[bytes, None, None]]:
    """
    Builds an ArchiveManifest and yields sequential uncompressed chunks
    as a continuous solid stream from a file or directory.
    Prunes files and directories matching exclude_patterns.
    """
    p = Path(target_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Source target not found: {target_path}")

    files: List[FileEntry] = []
    total_size = 0

    if p.is_file():
        if should_exclude(p.name, p.name, False, exclude_patterns):
            raise ValueError(f"Source file '{p.name}' matches exclusion patterns.")
        stat = p.stat()
        entry = FileEntry(
            rel_path=p.name,
            size=stat.st_size,
            mode=stat.st_mode,
            mtime=stat.st_mtime,
            offset=0,
            block_id=0,
            length=stat.st_size,
            solid_offset=0,
        )
        files.append(entry)
        total_size = stat.st_size
        manifest = ArchiveManifest(
            is_dir=False,
            root_name=p.name,
            total_uncompressed_size=total_size,
            files=files,
        )

        def file_stream():
            file_size = stat.st_size
            if file_size == 0:
                return
            buf = bytearray(chunk_size)
            mv = memoryview(buf)
            offset = 0
            try:
                with open(str(p), "rb", buffering=0) as f:
                    rem = file_size
                    while rem > 0:
                        to_read = min(rem, chunk_size - offset)
                        n = f.readinto(mv[offset:offset + to_read])
                        if not n:
                            break
                        offset += n
                        rem -= n
                        if offset == chunk_size:
                            yield bytes(buf)
                            offset = 0
            except OSError:
                pass
            if offset > 0:
                yield bytes(buf[:offset])

        return manifest, file_stream()

    elif p.is_dir():
        current_offset = 0
        root_path_str = str(p)
        root_len = len(root_path_str)
        if not root_path_str.endswith(os.sep):
            root_len += 1

        # High-Speed Recursive Directory Traversal with os.scandir
        # Cuts manifest scan time from 50s down to ~4s (10x faster)
        scanned_entries: List[Tuple[str, str, bool, bool, bool, int, int, float, str]] = []
        stack = [root_path_str]

        while stack:
            cur_dir = stack.pop()
            try:
                with os.scandir(cur_dir) as it:
                    for entry in it:
                        try:
                            full_p = entry.path
                            rel = full_p[root_len:]
                            is_dir_entry = entry.is_dir(follow_symlinks=False)
                            if should_exclude(rel, entry.name, is_dir_entry, exclude_patterns):
                                continue
                            is_link = entry.is_symlink()
                            if is_link:
                                target = os.readlink(full_p)
                                try:
                                    st = entry.stat(follow_symlinks=False)
                                    mode = st.st_mode
                                    mtime = st.st_mtime
                                except OSError:
                                    mode = 0o777
                                    mtime = time.time()
                                scanned_entries.append((rel, full_p, True, False, False, 0, mode, mtime, target))
                            elif is_dir_entry:
                                st = entry.stat(follow_symlinks=False)
                                scanned_entries.append((rel, full_p, False, True, False, 0, st.st_mode, st.st_mtime, ""))
                                stack.append(full_p)
                            else:
                                st = entry.stat(follow_symlinks=False)
                                scanned_entries.append((rel, full_p, False, False, True, st.st_size, st.st_mode, st.st_mtime, ""))
                        except OSError:
                            pass
            except OSError:
                pass


        # Sort entries so order is deterministic
        scanned_entries.sort(key=lambda x: x[0])

        file_records: List[Tuple[str, int]] = []
        for rel, full_p, is_link, is_dir, is_file, size, mode, mtime, target in scanned_entries:
            if is_link:
                files.append(FileEntry(
                    rel_path=rel,
                    size=0,
                    mode=mode,
                    mtime=mtime,
                    offset=current_offset % chunk_size,
                    block_id=current_offset // chunk_size,
                    length=0,
                    solid_offset=current_offset,
                    is_symlink=True,
                    link_target=target,
                ))
            elif is_dir:
                files.append(FileEntry(
                    rel_path=rel,
                    size=0,
                    mode=mode,
                    mtime=mtime,
                    offset=current_offset % chunk_size,
                    block_id=current_offset // chunk_size,
                    length=0,
                    solid_offset=current_offset,
                    is_dir=True,
                ))
            else:
                files.append(FileEntry(
                    rel_path=rel,
                    size=size,
                    mode=mode,
                    mtime=mtime,
                    offset=current_offset % chunk_size,
                    block_id=current_offset // chunk_size,
                    length=size,
                    solid_offset=current_offset,
                ))
                current_offset += size
                file_records.append((full_p, size))

        manifest = ArchiveManifest(
            is_dir=True,
            root_name=p.name,
            total_uncompressed_size=current_offset,
            files=files,
        )

        def dir_stream():
            buf = bytearray(chunk_size)
            mv = memoryview(buf)
            offset = 0
            for fp_str, f_size in file_records:
                if f_size == 0:
                    continue
                try:
                    with open(fp_str, "rb", buffering=0) as f:
                        rem = f_size
                        while rem > 0:
                            to_read = min(rem, chunk_size - offset)
                            n = f.readinto(mv[offset:offset + to_read])
                            if not n:
                                break
                            offset += n
                            rem -= n
                            if offset == chunk_size:
                                yield bytes(buf)
                                offset = 0
                except OSError:
                    pass
            if offset > 0:
                yield bytes(buf[:offset])

        return manifest, dir_stream()
    else:
        raise ValueError(f"Unsupported filesystem object: {target_path}")


def build_manifest_from_paths(
    paths: List[str],
    chunk_size: int = DEFAULT_FAST_BLOCK_SIZE,
    exclude_patterns: Optional[List[str]] = None,
    root_name: str = "archive",
) -> Tuple[ArchiveManifest, Generator[bytes, None, None]]:
    """
    Builds an ArchiveManifest from an explicit list of file/dir paths (e.g. from find -print0 or CLI args)
    and yields sequential uncompressed chunks as a continuous solid stream.
    """
    files: List[FileEntry] = []
    current_offset = 0
    file_records: List[Tuple[str, int]] = []

    norm_paths = []
    for raw_p in paths:
        s = str(raw_p).strip()
        if not s:
            continue
        p = Path(s)
        if not p.exists() and not p.is_symlink():
            continue
        norm_paths.append(s)

    for item in sorted(norm_paths):
        p = Path(item)
        rel = item.replace("\\", "/").lstrip("/")
        if rel.startswith("./"):
            rel = rel[2:]
        is_link = p.is_symlink()
        is_dir_entry = p.is_dir() if not is_link else False
        if should_exclude(rel, p.name, is_dir_entry, exclude_patterns):
            continue

        if is_link:
            target = os.readlink(str(p))
            try:
                st = p.lstat()
                mode = st.st_mode
                mtime = st.st_mtime
            except OSError:
                mode = 0o777
                mtime = time.time()
            files.append(FileEntry(
                rel_path=rel,
                size=0,
                mode=mode,
                mtime=mtime,
                offset=current_offset % chunk_size,
                block_id=current_offset // chunk_size,
                length=0,
                solid_offset=current_offset,
                is_symlink=True,
                link_target=target,
            ))
        elif is_dir_entry:
            st = p.stat()
            files.append(FileEntry(
                rel_path=rel,
                size=0,
                mode=st.st_mode,
                mtime=st.st_mtime,
                offset=current_offset % chunk_size,
                block_id=current_offset // chunk_size,
                length=0,
                solid_offset=current_offset,
                is_dir=True,
            ))
        elif p.is_file():
            st = p.stat()
            size = st.st_size
            files.append(FileEntry(
                rel_path=rel,
                size=size,
                mode=st.st_mode,
                mtime=st.st_mtime,
                offset=current_offset % chunk_size,
                block_id=current_offset // chunk_size,
                length=size,
                solid_offset=current_offset,
            ))
            current_offset += size
            file_records.append((str(p), size))

    manifest = ArchiveManifest(
        is_dir=True,
        root_name=root_name,
        total_uncompressed_size=current_offset,
        files=files,
    )

    def path_stream():
        buf = bytearray(chunk_size)
        mv = memoryview(buf)
        offset = 0
        for fp_str, f_size in file_records:
            if f_size == 0:
                continue
            try:
                with open(fp_str, "rb", buffering=0) as f:
                    rem = f_size
                    while rem > 0:
                        to_read = min(rem, chunk_size - offset)
                        n = f.readinto(mv[offset:offset + to_read])
                        if not n:
                            break
                        offset += n
                        rem -= n
                        if offset == chunk_size:
                            yield bytes(buf)
                            offset = 0
            except OSError:
                pass
        if offset > 0:
            yield bytes(buf[:offset])

    return manifest, path_stream()


def compress_archive(
    source_path: Optional[str] = None,
    output_archive_path: str = "-",
    mode: Mode = Mode.BALANCED,
    block_size: Optional[int] = None,
    password: Optional[str] = None,
    recovery: bool = False,
    cdc: bool = False,
    progress_callback: Optional[Callable[[int, int, str, float], None]] = None,
    exclude_patterns: Optional[List[str]] = None,
    base_archive_path: Optional[str] = None,
    paths: Optional[List[str]] = None,
) -> Dict:
    """
    Compresses a file or directory into a high-efficiency `.apx` archive.
    Supports authenticated encryption, self-healing recovery records, block deduplication,
    FastCDC content-defined chunking, incremental base deduplication, and multi-core pipelined block compression.
    Writes atomically via a sibling temp file or streams to stdout.
    """
    if block_size is None:
        block_size = DEFAULT_FAST_BLOCK_SIZE if mode == Mode.FAST else DEFAULT_BLOCK_SIZE

    if paths is not None:
        manifest, stream = build_manifest_from_paths(paths, chunk_size=block_size, exclude_patterns=exclude_patterns)
    elif source_path is not None:
        manifest, stream = build_manifest(source_path, chunk_size=block_size, exclude_patterns=exclude_patterns)
    else:
        raise ValueError("Either source_path or paths must be provided to compress_archive.")

    # Incremental Base Archive Indexing
    base_chunks: Dict[bytes, Tuple[int, int, bytes, int, str]] = {}
    reused_chunks_count = 0
    reused_bytes = 0

    if base_archive_path:
        base_p = Path(base_archive_path).resolve()
        if not base_p.exists():
            raise FileNotFoundError(f"Base archive not found: {base_archive_path}")
        with open(base_p, "rb") as base_f:
            b_flags, b_block_size, b_manifest, b_enc_key, b_mac_key = read_archive_header(base_f, password=password)
            base_blocks = scan_block_index(base_f, base_f.tell())
            base_uncomp_cache: Dict[int, bytes] = {}
            base_comp_cache: Dict[int, Tuple[int, int, bytes, int]] = {}
            for b in base_blocks:
                if b.pipeline_id == PIPELINE_DEDUP_REF:
                    if b.ref_idx is not None and b.ref_idx in base_comp_cache:
                        base_comp_cache[b.block_id] = base_comp_cache[b.ref_idx]
                        if b.ref_idx in base_uncomp_cache:
                            uncomp_data = base_uncomp_cache[b.ref_idx]
                            base_uncomp_cache[b.block_id] = uncomp_data
                            h = hashlib.blake2b(uncomp_data, digest_size=32).digest()
                            b_pid, b_ulen, b_pay, b_crc = base_comp_cache[b.ref_idx]
                            base_chunks[h] = (b_pid, b_ulen, b_pay, b_crc, f"Base ref #{b.ref_idx}")
                else:
                    base_f.seek(b.payload_offset)
                    payload = base_f.read(b.comp_len)
                    if b_flags & FLAG_ENCRYPTED:
                        payload = decrypt_payload(payload, b_enc_key, b_mac_key)
                    try:
                        uncomp_data = decompress_chunk(payload, b.pipeline_id)
                        if zlib.crc32(uncomp_data) == b.crc:
                            base_uncomp_cache[b.block_id] = uncomp_data
                            base_comp_cache[b.block_id] = (b.pipeline_id, b.uncomp_len, payload, b.crc)
                            h = hashlib.blake2b(uncomp_data, digest_size=32).digest()
                            base_chunks[h] = (b.pipeline_id, b.uncomp_len, payload, b.crc, f"Base #{b.block_id}")
                    except Exception:
                        pass
        manifest.base_archive = base_p.name

        # If base is provided and data size is manageable (< 128 MB), pre-count reuse for manifest accuracy
        if manifest.total_uncompressed_size < 128 * 1024 * 1024:
            buffered_stream_blocks = list(stream)
            stream = iter(buffered_stream_blocks)
            pre_count = 0
            for b_data in buffered_stream_blocks:
                h = hashlib.blake2b(b_data, digest_size=32).digest()
                if h in base_chunks:
                    pre_count += 1
            manifest.reused_chunks = pre_count

    manifest_bytes = manifest.to_json().encode("utf-8")
    comp_manifest = zlib.compress(manifest_bytes, level=9)

    flags = FLAG_SOLID | FLAG_SHA256
    if manifest.is_dir:
        flags |= FLAG_IS_DIR

    enc_key, mac_key = None, None
    salt = b""
    if password:
        flags |= FLAG_ENCRYPTED
        salt = os.urandom(16)
        enc_key, mac_key = derive_keys(password, salt)
        manifest_payload = encrypt_payload(comp_manifest, enc_key, mac_key)
    else:
        manifest_payload = comp_manifest

    if recovery:
        flags |= FLAG_RECOVERY

    overall_hasher = hashlib.sha256()
    total_uncompressed = 0
    total_compressed = 0
    total_blocks = 0
    block_records = []
    seen_crypto_hashes: Dict[bytes, int] = {}
    raw_blocks_for_recovery: List[bytes] = []

    start_time = time.perf_counter()

    is_stdout = (output_archive_path == "-")
    if is_stdout:
        dest_p = None
        temp_archive_path = None
    else:
        dest_p = Path(output_archive_path).resolve()
        dest_p.parent.mkdir(parents=True, exist_ok=True)
        temp_archive_path = dest_p.parent / f".{dest_p.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}.apx"
    write_success = False

    try:
        import contextlib
        def get_out_handle():
            if is_stdout:
                return contextlib.nullcontext(sys.stdout.buffer)
            return open(temp_archive_path, "wb", buffering=4 * 1024 * 1024)

        with get_out_handle() as out:
            # 1. Magic Header (8 bytes)
            out.write(MAGIC_HEADER)

            # 2. Container Header:
            out.write(struct.pack(
                "<HIII",
                flags,
                block_size,
                len(manifest_bytes),
                len(manifest_payload),
            ))

            # Encryption salt (16 bytes) if encrypted
            if flags & FLAG_ENCRYPTED:
                out.write(salt)

            # Manifest payload
            out.write(manifest_payload)

            # Multi-Core Block Worker Pool
            workers = min(os.cpu_count() or 4, 4)
            max_inflight = 32

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                inflight: Dict[int, Any] = {}
                next_write_idx = 0

                def _compress_worker(b_data: bytes, m: Mode, precomputed_crc: int) -> Tuple[int, bytes, str, int]:
                    c_res = compress_chunk(b_data, mode=m)
                    return (c_res.pipeline_id, c_res.data, c_res.name, precomputed_crc)

                def write_block(b_idx: int):
                    nonlocal total_compressed
                    item = inflight.pop(b_idx)
                    if len(item) == 5:
                        # Deduplicated or base-reused block: (pipeline_id, uncomp_len, payload, crc, winner_name)
                        pid, u_len, payload, b_crc, w_name = item
                    else:
                        fut, u_len = item
                        pid, payload, w_name, b_crc = fut.result()

                    if flags & FLAG_ENCRYPTED:
                        payload = encrypt_payload(payload, enc_key, mac_key)

                    c_len = len(payload)
                    total_compressed += c_len

                    out.write(struct.pack("<BIII", pid, u_len, c_len, b_crc))
                    out.write(payload)

                    ratio = (u_len / c_len) if c_len > 0 else 1.0
                    block_records.append({
                        "block": b_idx + 1,
                        "pipeline_id": pid,
                        "winner": w_name,
                        "uncompressed": u_len,
                        "compressed": c_len,
                        "ratio": ratio,
                    })

                    if progress_callback:
                        progress_callback(total_uncompressed, manifest.total_uncompressed_size, w_name, ratio)

                chunk_queue: queue.Queue = queue.Queue(maxsize=32)
                reader_exc: List[Exception] = []

                def reader_worker():
                    try:
                        if cdc:
                            min_chunk = max(512 * 1024, block_size // 2)
                            max_chunk = block_size * 2
                            avg_chunk = block_size
                            for block_data in fastcdc_chunk_stream(stream, min_chunk, avg_chunk, max_chunk):
                                overall_hasher.update(block_data)
                                b_crc = zlib.crc32(block_data)
                                chunk_queue.put((block_data, b_crc))
                        else:
                            for block_data in stream:
                                overall_hasher.update(block_data)
                                b_crc = zlib.crc32(block_data)
                                chunk_queue.put((block_data, b_crc))
                    except Exception as e:
                        reader_exc.append(e)
                    finally:
                        chunk_queue.put(None)

                reader_t = threading.Thread(target=reader_worker, daemon=True)
                reader_t.start()

                def dispatch_block(b_data: bytes, b_crc: int):
                    nonlocal total_blocks, total_uncompressed, next_write_idx, reused_chunks_count, reused_bytes
                    b_idx = total_blocks
                    total_blocks += 1

                    u_len = len(b_data)
                    total_uncompressed += u_len

                    if recovery:
                        raw_blocks_for_recovery.append(b_data)

                    crypto_key = hashlib.blake2b(b_data, digest_size=32).digest()
                    if crypto_key in seen_crypto_hashes:
                        prev_idx = seen_crypto_hashes[crypto_key]
                        payload = struct.pack("<I", prev_idx)
                        inflight[b_idx] = (PIPELINE_DEDUP_REF, u_len, payload, b_crc, f"Deduplicated (ref #{prev_idx})")
                    elif base_chunks and crypto_key in base_chunks:
                        b_pid, b_ulen, b_payload, b_crc_val, b_name = base_chunks[crypto_key]
                        reused_chunks_count += 1
                        reused_bytes += u_len
                        inflight[b_idx] = (b_pid, b_ulen, b_payload, b_crc_val, f"Reused from base ({b_name})")
                        seen_crypto_hashes[crypto_key] = b_idx
                    else:
                        seen_crypto_hashes[crypto_key] = b_idx
                        fut = executor.submit(_compress_worker, b_data, mode, b_crc)
                        inflight[b_idx] = (fut, u_len)

                    while len(inflight) >= max_inflight:
                        write_block(next_write_idx)
                        next_write_idx += 1

                while True:
                    item = chunk_queue.get()
                    if item is None:
                        if reader_exc:
                            raise reader_exc[0]
                        break
                    b_data, b_crc = item
                    dispatch_block(b_data, b_crc)

                while next_write_idx < total_blocks:
                    write_block(next_write_idx)
                    next_write_idx += 1

                reader_t.join()

            out.write(struct.pack("<BIII", EOF_PIPELINE_ID, 0, 0, 0))

            # sha256 (32 bytes), total_uncompressed_bytes (uint64), total_blocks (uint32), footer_magic (4 bytes)
            digest = overall_hasher.digest()
            out.write(digest)
            out.write(struct.pack("<QI", total_uncompressed, total_blocks))
            out.write(MAGIC_FOOTER)

            # Self-Healing Recovery Records (Parity)
            if flags & FLAG_RECOVERY and raw_blocks_for_recovery:
                parity_data, max_b_len = generate_recovery_parity(raw_blocks_for_recovery)
                out.write(struct.pack("<II", len(parity_data), max_b_len))
                out.write(parity_data)

            out.flush()
            if not is_stdout:
                try:
                    os.fsync(out.fileno())
                except OSError:
                    pass

        if not is_stdout:
            os.replace(temp_archive_path, dest_p)
        write_success = True
    finally:
        if not is_stdout and not write_success and temp_archive_path and temp_archive_path.exists():
            try:
                temp_archive_path.unlink()
            except OSError:
                pass

    elapsed = time.perf_counter() - start_time
    if is_stdout:
        archive_file_size = total_compressed
        archive_name = "<stdout>"
    else:
        archive_file_size = os.path.getsize(dest_p)
        archive_name = str(dest_p)

    overall_ratio = (total_uncompressed / archive_file_size) if archive_file_size > 0 else 1.0
    space_saved = (1.0 - (archive_file_size / total_uncompressed)) * 100.0 if total_uncompressed > 0 else 0.0

    return {
        "status": "SUCCESS",
        "source": source_path or (", ".join(str(p) for p in paths[:3]) if paths else ""),
        "archive": archive_name,
        "uncompressed_bytes": total_uncompressed,
        "compressed_bytes": archive_file_size,
        "ratio": overall_ratio,
        "space_saved_pct": space_saved,
        "blocks": total_blocks,
        "elapsed": elapsed,
        "sha256": overall_hasher.hexdigest(),
        "block_records": block_records,
        "encrypted": bool(flags & FLAG_ENCRYPTED),
        "recovery": bool(flags & FLAG_RECOVERY),
        "base_archive": manifest.base_archive,
        "reused_chunks": reused_chunks_count,
        "reused_bytes": reused_bytes,
    }


def read_archive_header(
    f: BinaryIO, password: Optional[str] = None
) -> Tuple[int, int, ArchiveManifest, Optional[bytes], Optional[bytes]]:
    """Reads and validates magic, container flags, manifest, and encryption keys."""
    magic = f.read(8)
    if magic != MAGIC_HEADER:
        raise ValueError(f"Invalid Apex archive header: magic '{magic}' mismatch.")

    header_bytes = f.read(struct.calcsize("<HIII"))
    flags, block_size, manifest_raw_len, manifest_comp_len = struct.unpack("<HIII", header_bytes)

    enc_key, mac_key = None, None
    if flags & FLAG_ENCRYPTED:
        salt = f.read(16)
        if len(salt) != 16:
            raise ValueError("Corrupted encrypted archive: missing encryption salt.")
        if not password:
            password = getpass.getpass("Enter archive password: ")
        enc_key, mac_key = derive_keys(password, salt)

    comp_manifest = f.read(manifest_comp_len)
    try:
        if flags & FLAG_ENCRYPTED:
            comp_manifest = decrypt_payload(comp_manifest, enc_key, mac_key)
        manifest_bytes = zlib.decompress(comp_manifest)
        manifest = ArchiveManifest.from_json(manifest_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Corrupted archive manifest: {e}") from e

    return flags, block_size, manifest, enc_key, mac_key


def scan_block_index(f: BinaryIO, start_pos: int) -> List[BlockMeta]:
    """
    Rapidly scans block headers to build a block index table mapping each block's
    location, sizes, pipeline ID, CRC, and uncompressed stream offsets in < 1ms.
    """
    cur_pos = f.tell()
    f.seek(start_pos)
    blocks: List[BlockMeta] = []
    header_struct = struct.Struct("<BIII")
    solid_curr = 0
    b_idx = 0

    while True:
        hdr_pos = f.tell()
        hdr_bytes = f.read(header_struct.size)
        if not hdr_bytes or len(hdr_bytes) < header_struct.size:
            break
        pid, u_len, c_len, crc = header_struct.unpack(hdr_bytes)
        if pid == EOF_PIPELINE_ID:
            break

        payload_pos = f.tell()
        ref_idx = None
        if pid == PIPELINE_DEDUP_REF:
            payload = f.read(c_len)
            if len(payload) >= 4:
                ref_idx = struct.unpack("<I", payload[:4])[0]
        else:
            try:
                f.seek(c_len, os.SEEK_CUR)
            except Exception:
                f.read(c_len)

        blocks.append(BlockMeta(
            block_id=b_idx,
            file_offset=hdr_pos,
            payload_offset=payload_pos,
            pipeline_id=pid,
            uncomp_len=u_len,
            comp_len=c_len,
            crc=crc,
            ref_idx=ref_idx,
            solid_start=solid_curr,
            solid_end=solid_curr + u_len,
        ))
        solid_curr += u_len
        b_idx += 1

    try:
        f.seek(cur_pos)
    except Exception:
        pass

    return blocks


def test_archive(archive_path: str, password: Optional[str] = None) -> Dict:
    """
    Verifies the complete bit-exact integrity of an archive:
    checks block CRCs, deduplication pointers, encryption, and stream SHA-256 without extracting to disk.
    """
    t0 = time.perf_counter()
    with open(archive_path, "rb") as f:
        flags, block_size, manifest, enc_key, mac_key = read_archive_header(f, password=password)

        # Fast 1st pass: scan block headers for referenced deduplication targets (<0.02s)
        f_start_pos = f.tell()
        needed_refs = set()
        header_struct = struct.Struct("<BIII")
        while True:
            hdr_bytes = f.read(header_struct.size)
            if not hdr_bytes:
                break
            p_id, _, c_len, _ = header_struct.unpack(hdr_bytes)
            if p_id == EOF_PIPELINE_ID:
                break
            if p_id == PIPELINE_DEDUP_REF:
                ref_payload = f.read(c_len)
                needed_refs.add(struct.unpack("<I", ref_payload)[0])
            else:
                f.seek(c_len, 1)
        f.seek(f_start_pos)

        overall_hasher = hashlib.sha256()
        total_uncompressed = 0
        total_blocks = 0
        dedup_cache = {}

        workers = min(os.cpu_count() or 4, 8)
        max_inflight = max(4, workers * 2)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            inflight_queue: List[Tuple[int, Any, int, int]] = []
            eof_reached = False

            while not eof_reached or inflight_queue:
                while not eof_reached and len(inflight_queue) < max_inflight:
                    hdr_bytes = f.read(header_struct.size)
                    if not hdr_bytes:
                        eof_reached = True
                        break
                    pipeline_id, uncomp_len, comp_len, crc = header_struct.unpack(hdr_bytes)
                    if pipeline_id == EOF_PIPELINE_ID:
                        eof_reached = True
                        break

                    payload = f.read(comp_len)
                    if len(payload) != comp_len:
                        raise ValueError(f"Truncated block {total_blocks + len(inflight_queue) + 1}: expected {comp_len} bytes.")

                    if flags & FLAG_ENCRYPTED:
                        payload = decrypt_payload(payload, enc_key, mac_key)

                    if pipeline_id == PIPELINE_DEDUP_REF:
                        ref_idx = struct.unpack("<I", payload)[0]
                        inflight_queue.append((PIPELINE_DEDUP_REF, ref_idx, uncomp_len, crc))
                    else:
                        fut = executor.submit(decompress_chunk, payload, pipeline_id)
                        inflight_queue.append((pipeline_id, fut, uncomp_len, crc))

                if not inflight_queue:
                    break

                cur_block_idx = total_blocks
                pid, task_or_ref, uncomp_len, crc = inflight_queue.pop(0)
                try:
                    if pid == PIPELINE_DEDUP_REF:
                        raw_chunk = dedup_cache[task_or_ref]
                    else:
                        raw_chunk = task_or_ref.result()
                    if cur_block_idx in needed_refs:
                        dedup_cache[cur_block_idx] = raw_chunk
                except Exception as e:
                    raise ValueError(f"Corrupted block {total_blocks + 1}: decompression failed ({e})") from e

                if len(raw_chunk) != uncomp_len:
                    raise ValueError(f"Block {total_blocks + 1} size mismatch: expected {uncomp_len}, got {len(raw_chunk)}.")

                actual_crc = zlib.crc32(raw_chunk)
                if actual_crc != crc:
                    raise ValueError(f"CRC-32 checksum mismatch in block {total_blocks + 1}!")

                overall_hasher.update(raw_chunk)
                total_uncompressed += uncomp_len
                total_blocks += 1

        stored_sha = f.read(32)
        stored_uncomp, stored_blocks = struct.unpack("<QI", f.read(12))
        footer_magic = f.read(4)

        if footer_magic != MAGIC_FOOTER:
            raise ValueError("Corrupted archive: Footer magic mismatch.")

        if total_blocks != stored_blocks:
            raise ValueError(f"Block count mismatch: header {stored_blocks}, verified {total_blocks}.")

        if total_uncompressed != stored_uncomp:
            raise ValueError(f"Size mismatch: expected {stored_uncomp} bytes, found {total_uncompressed}.")

        calculated_sha = overall_hasher.digest()
        if calculated_sha != stored_sha:
            raise ValueError("Cryptographic SHA-256 stream mismatch! Archive is corrupted.")

        has_recovery = bool(flags & FLAG_RECOVERY)

    elapsed = time.perf_counter() - t0
    return {
        "status": "PASSED",
        "archive": archive_path,
        "total_files": len(manifest.files),
        "total_uncompressed_bytes": total_uncompressed,
        "total_blocks": total_blocks,
        "sha256": overall_hasher.hexdigest(),
        "encrypted": bool(flags & FLAG_ENCRYPTED),
        "has_recovery": has_recovery,
        "elapsed": elapsed,
    }


test_archive.__test__ = False


def _safe_write_all(fd: int, data: Any):
    """Zero-copy complete buffer write to file descriptor."""
    if not data:
        return
    mv = memoryview(data) if not isinstance(data, memoryview) else data
    total = len(mv)
    offset = 0
    while offset < total:
        written = os.write(fd, mv[offset:])
        if written == 0:
            break
        offset += written


def _write_single_file_fast(target_path: str, data: Any, mode: int, mtime: float):
    """High-performance direct file creation using low-level OS syscalls."""
    try:
        fd = os.open(target_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | O_BINARY, mode)
    except OSError:
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        # Conflict: existing read-only file, directory, or permissions issue
        try:
            os.chmod(target_path, 0o777)
        except OSError:
            pass
        try:
            if os.path.isdir(target_path) and not os.path.islink(target_path):
                shutil.rmtree(target_path, ignore_errors=True)
            else:
                os.unlink(target_path)
        except OSError:
            pass
        fd = os.open(target_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | O_BINARY, mode)

    try:
        if data:
            _safe_write_all(fd, data)
        try:
            os.utime(fd, (mtime, mtime))
        except (OSError, NotImplementedError, TypeError):
            try:
                os.utime(target_path, (mtime, mtime))
            except OSError:
                pass
        if mode & 0o222 == 0:
            try:
                os.fchmod(fd, mode)
            except (OSError, NotImplementedError, AttributeError):
                try:
                    os.chmod(target_path, mode)
                except OSError:
                    pass
    finally:
        os.close(fd)


def _write_symlink_fast(target_path: str, link_target: str, mtime: float):
    """High-performance symlink creation with overwrite recovery."""
    try:
        os.symlink(link_target, target_path)
    except OSError:
        try:
            if os.path.isdir(target_path) and not os.path.islink(target_path):
                shutil.rmtree(target_path, ignore_errors=True)
            else:
                os.unlink(target_path)
        except OSError:
            pass
        os.symlink(link_target, target_path)

    try:
        os.utime(target_path, (mtime, mtime), follow_symlinks=False)
    except (OSError, NotImplementedError, TypeError):
        pass


def _promote_staging_to_dest(staging: Path, dest: Path):
    """Atomically promotes a staged directory to destination, merging if destination already exists."""
    if not dest.exists():
        try:
            os.replace(staging, dest)
            return
        except OSError:
            pass
    dest.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(staging, followlinks=False):
        rel = os.path.relpath(root, staging)
        target_dir = dest if rel == "." else dest / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for f_name in files:
            s_file = Path(root) / f_name
            d_file = target_dir / f_name
            try:
                if d_file.is_symlink() or d_file.exists():
                    try:
                        os.chmod(d_file, 0o777)
                    except OSError:
                        pass
                    if d_file.is_dir() and not d_file.is_symlink():
                        shutil.rmtree(d_file, ignore_errors=True)
                    else:
                        d_file.unlink(missing_ok=True)
            except OSError:
                pass
            os.replace(s_file, d_file)
    shutil.rmtree(staging, ignore_errors=True)


def decompress_archive(
    archive_path: str,
    output_dir: Optional[str] = None,
    password: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
    include_patterns: Optional[List[str]] = None,
) -> Dict:
    """
    Decompresses and reconstructs files/directories with exact permissions, symlinks, and mtimes.
    Blazing fast pipelined zero-copy NVMe extraction engine with parallel decompression and disk writes.
    """
    t0 = time.perf_counter()
    is_stdin = (archive_path == "-")
    if is_stdin:
        archive_p = None
        out_base = Path(output_dir).resolve() if output_dir else Path.cwd()
    else:
        archive_p = Path(archive_path).resolve()
        if not archive_p.exists():
            raise FileNotFoundError(f"Archive file not found: {archive_path}")
        out_base = Path(output_dir).resolve() if output_dir else (archive_p.parent if archive_p.is_file() else Path.cwd())

    old_umask = os.umask(0)
    stop_event = threading.Event()
    writer_stop_event = threading.Event()
    block_queue: queue.Queue = queue.Queue(maxsize=32)

    staging_file_to_cleanup: Optional[Path] = None
    staging_dir_to_cleanup: Optional[Path] = None
    decomp_success = False

    try:
        import contextlib
        f_context = contextlib.nullcontext(sys.stdin.buffer) if is_stdin else open(archive_p, "rb")
        with f_context as f:
            flags, block_size, manifest, enc_key, mac_key = read_archive_header(f, password=password)
            f_start_pos = 0 if is_stdin else f.tell()

            # Fast Selective Indexed Extraction if specific files/patterns were requested on a seekable file
            if include_patterns and not is_stdin:
                def _matches_pattern(rel_p: str) -> bool:
                    norm = rel_p.replace("\\", "/").rstrip("/")
                    bn = norm.split("/")[-1] if norm else ""
                    for pat in include_patterns:
                        pat_norm = pat.replace("\\", "/").rstrip("/")
                        if norm == pat_norm or norm.startswith(pat_norm + "/"):
                            return True
                        if fnmatch.fnmatch(norm, pat_norm) or fnmatch.fnmatch(bn, pat_norm):
                            return True
                    return False

                matched_files = [fe for fe in manifest.files if _matches_pattern(fe.rel_path)]
                if matched_files:
                    blocks_info = scan_block_index(f, f_start_pos)
                    needed_blocks = set()
                    for mf in matched_files:
                        if mf.is_symlink or mf.is_dir or mf.size == 0:
                            continue
                        f_start = mf.solid_offset
                        f_end = f_start + mf.size
                        for b in blocks_info:
                            if not (b.solid_end <= f_start or b.solid_start >= f_end):
                                needed_blocks.add(b.block_id)

                    # Add dedup refs recursively
                    changed = True
                    while changed:
                        changed = False
                        new_refs = set()
                        for b_id in needed_blocks:
                            b = blocks_info[b_id]
                            if b.pipeline_id == PIPELINE_DEDUP_REF and b.ref_idx is not None:
                                if b.ref_idx not in needed_blocks:
                                    new_refs.add(b.ref_idx)
                                    changed = True
                        needed_blocks.update(new_refs)

                    if len(needed_blocks) < len(blocks_info):
                        # Selective decoding: ONLY decode the needed blocks!
                        decoded_cache: Dict[int, bytes] = {}
                        for b_id in sorted(needed_blocks):
                            b = blocks_info[b_id]
                            if b.pipeline_id == PIPELINE_DEDUP_REF:
                                raw = decoded_cache[b.ref_idx]
                            else:
                                f.seek(b.payload_offset)
                                payload = f.read(b.comp_len)
                                if flags & FLAG_ENCRYPTED:
                                    payload = decrypt_payload(payload, enc_key, mac_key)
                                raw = decompress_chunk(payload, b.pipeline_id)
                                if zlib.crc32(raw) != b.crc:
                                    raise ValueError(f"CRC-32 checksum failed on block {b_id + 1}!")
                            decoded_cache[b_id] = raw

                        out_base.mkdir(parents=True, exist_ok=True)
                        extracted_paths = []
                        written_bytes = 0
                        for mf in matched_files:
                            norm_rel = mf.rel_path.replace("\\", "/").lstrip("/")
                            if not manifest.is_dir and len(manifest.files) == 1 and (out_base.suffix or not out_base.exists() or out_base.is_file()):
                                target_p = out_base
                            else:
                                target_p = out_base / norm_rel

                            target_p.parent.mkdir(parents=True, exist_ok=True)
                            if mf.is_symlink:
                                _write_symlink_fast(str(target_p), mf.link_target, mf.mtime)
                            elif mf.is_dir:
                                target_p.mkdir(parents=True, exist_ok=True)
                            else:
                                f_start = mf.solid_offset
                                f_end = f_start + mf.size
                                slices = []
                                for b in blocks_info:
                                    if b.solid_end <= f_start or b.solid_start >= f_end:
                                        continue
                                    b_raw = decoded_cache[b.block_id]
                                    slc_start = max(0, f_start - b.solid_start)
                                    slc_end = min(len(b_raw), f_end - b.solid_start)
                                    slices.append(b_raw[slc_start:slc_end])
                                file_bytes = b"".join(slices)
                                _write_single_file_fast(str(target_p), file_bytes, mf.mode, mf.mtime)
                                written_bytes += len(file_bytes)
                            extracted_paths.append(str(target_p))

                        elapsed = time.perf_counter() - t0
                        return {
                            "status": "SUCCESS",
                            "archive": str(archive_p) if not is_stdin else "<stdin>",
                            "files_extracted": len(extracted_paths),
                            "total_uncompressed_bytes": written_bytes,
                            "blocks_decoded": len(decoded_cache),
                            "total_blocks": len(blocks_info),
                            "elapsed": elapsed,
                            "selective": True,
                        }

            # Fast 1st pass: scan block headers for referenced deduplication targets (<0.02s)
            needed_refs = set()
            header_struct = struct.Struct("<BIII")
            if not is_stdin:
                while True:
                    hdr_bytes = f.read(header_struct.size)
                    if not hdr_bytes:
                        break
                    p_id, _, c_len, _ = header_struct.unpack(hdr_bytes)
                    if p_id == EOF_PIPELINE_ID:
                        break
                    if p_id == PIPELINE_DEDUP_REF:
                        ref_payload = f.read(c_len)
                        needed_refs.add(struct.unpack("<I", ref_payload)[0])
                    else:
                        f.seek(c_len, 1)
                f.seek(f_start_pos)

            overall_hasher = hashlib.sha256()
            feeder_stats = {
                "total_uncompressed": 0,
                "total_blocks": 0,
                "error": None,
            }

            def _worker_decompress(payload: bytes, pid: int, expected_crc: int) -> bytes:
                raw = decompress_chunk(payload, pid)
                if zlib.crc32(raw) != expected_crc:
                    raise ValueError("CRC-32 checksum verification failed on block!")
                return raw

            def decompress_feeder_worker():
                try:
                    workers = min(os.cpu_count() or 4, 4)
                    max_inflight = max(8, workers * 3)
                    dedup_cache = {}

                    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                        inflight_decomp: List[Tuple[int, Any, int, int]] = []
                        eof_reached = False

                        while not stop_event.is_set() and (not eof_reached or inflight_decomp):
                            while not stop_event.is_set() and not eof_reached and len(inflight_decomp) < max_inflight:
                                hdr_bytes = f.read(header_struct.size)
                                if not hdr_bytes:
                                    eof_reached = True
                                    break
                                pipeline_id, uncomp_len, comp_len, crc = header_struct.unpack(hdr_bytes)
                                if pipeline_id == EOF_PIPELINE_ID:
                                    eof_reached = True
                                    break

                                payload = f.read(comp_len)
                                if len(payload) != comp_len:
                                    raise ValueError(f"Truncated block in archive: expected {comp_len} bytes.")

                                if flags & FLAG_ENCRYPTED:
                                    payload = decrypt_payload(payload, enc_key, mac_key)

                                if pipeline_id == PIPELINE_DEDUP_REF:
                                    ref_idx = struct.unpack("<I", payload)[0]
                                    inflight_decomp.append((PIPELINE_DEDUP_REF, ref_idx, uncomp_len, crc))
                                else:
                                    fut = executor.submit(_worker_decompress, payload, pipeline_id, crc)
                                    inflight_decomp.append((pipeline_id, fut, uncomp_len, crc))

                            if not inflight_decomp:
                                break

                            cur_block_idx = feeder_stats["total_blocks"]
                            pid, task_or_ref, uncomp_len, crc = inflight_decomp.pop(0)

                            if pid == PIPELINE_DEDUP_REF:
                                raw_chunk = dedup_cache[task_or_ref]
                                if zlib.crc32(raw_chunk) != crc:
                                    raise ValueError(f"CRC-32 checksum failed on deduplicated block {cur_block_idx + 1}!")
                            else:
                                raw_chunk = task_or_ref.result()

                            if is_stdin or cur_block_idx in needed_refs:
                                dedup_cache[cur_block_idx] = raw_chunk

                            if len(raw_chunk) != uncomp_len:
                                raise ValueError(f"Block {cur_block_idx + 1} size mismatch: expected {uncomp_len}, got {len(raw_chunk)}.")

                            overall_hasher.update(raw_chunk)
                            feeder_stats["total_uncompressed"] += uncomp_len
                            feeder_stats["total_blocks"] += 1

                            while not stop_event.is_set():
                                try:
                                    block_queue.put(raw_chunk, timeout=0.1)
                                    break
                                except queue.Full:
                                    continue

                        if stop_event.is_set():
                            return

                        stored_sha = f.read(32)
                        stored_uncomp, stored_blocks = struct.unpack("<QI", f.read(12))
                        footer_magic = f.read(4)

                        if footer_magic != MAGIC_FOOTER:
                            raise ValueError("Corrupted archive: Footer magic mismatch.")
                        if feeder_stats["total_blocks"] != stored_blocks:
                            raise ValueError(f"Block count mismatch: header {stored_blocks}, verified {feeder_stats['total_blocks']}.")
                        if feeder_stats["total_uncompressed"] != stored_uncomp:
                            raise ValueError(f"Size mismatch: expected {stored_uncomp} bytes, found {feeder_stats['total_uncompressed']}.")
                        if overall_hasher.digest() != stored_sha:
                            raise ValueError("Cryptographic SHA-256 stream verification failed!")

                        while not stop_event.is_set():
                            try:
                                block_queue.put(None, timeout=0.1)
                                break
                            except queue.Full:
                                continue

                except Exception as exc:
                    feeder_stats["error"] = exc
                    try:
                        block_queue.put_nowait(None)
                    except Exception:
                        pass

            feeder_thread = threading.Thread(target=decompress_feeder_worker, daemon=True)
            feeder_thread.start()

            cur_block: Optional[bytes] = None
            cur_mv: Optional[memoryview] = None
            cur_offset = 0

            def get_bytes_slice(needed: int) -> memoryview:
                nonlocal cur_block, cur_mv, cur_offset
                if needed == 0:
                    return memoryview(b"")

                if cur_mv is None or cur_offset >= len(cur_mv):
                    chunk = block_queue.get()
                    if chunk is None:
                        if feeder_stats["error"]:
                            raise feeder_stats["error"]
                        raise EOFError("Unexpected end of compressed stream")
                    cur_block = chunk
                    cur_mv = memoryview(chunk)
                    cur_offset = 0

                avail = len(cur_mv) - cur_offset
                if avail >= needed:
                    slc = cur_mv[cur_offset : cur_offset + needed]
                    cur_offset += needed
                    return slc

                buf = bytearray(needed)
                buf_view = memoryview(buf)
                filled = 0
                while filled < needed:
                    if cur_mv is None or cur_offset >= len(cur_mv):
                        chunk = block_queue.get()
                        if chunk is None:
                            if feeder_stats["error"]:
                                raise feeder_stats["error"]
                            raise EOFError("Unexpected end of compressed stream")
                        cur_block = chunk
                        cur_mv = memoryview(chunk)
                        cur_offset = 0
                    avail = len(cur_mv) - cur_offset
                    take = min(needed - filled, avail)
                    buf_view[filled : filled + take] = cur_mv[cur_offset : cur_offset + take]
                    cur_offset += take
                    filled += take
                return buf_view

            def skip_bytes(needed: int) -> None:
                nonlocal cur_block, cur_mv, cur_offset
                rem = needed
                while rem > 0:
                    if cur_mv is None or cur_offset >= len(cur_mv):
                        chunk = block_queue.get()
                        if chunk is None:
                            if feeder_stats["error"]:
                                raise feeder_stats["error"]
                            raise EOFError("Unexpected end of compressed stream")
                        cur_block = chunk
                        cur_mv = memoryview(chunk)
                        cur_offset = 0
                    avail = len(cur_mv) - cur_offset
                    take = min(rem, avail)
                    cur_offset += take
                    rem -= take

            def should_extract(rel_path: str) -> bool:
                if not include_patterns:
                    return True
                norm = rel_path.replace("\\", "/")
                basename = norm.split("/")[-1]
                for pat in include_patterns:
                    pat_norm = pat.replace("\\", "/").rstrip("/")
                    if norm == pat_norm or norm.startswith(pat_norm + "/"):
                        return True
                    if fnmatch.fnmatch(norm, pat_norm) or fnmatch.fnmatch(basename, pat_norm):
                        return True
                return False

            extracted_paths: List[str] = []
            deferred_dir_perms: List[Tuple[str, Optional[int], Optional[float]]] = []
            written_bytes = 0
            last_progress_time = 0.0

            def maybe_report():
                nonlocal last_progress_time
                if not progress_callback:
                    return
                now = time.monotonic()
                if now - last_progress_time >= 0.1:
                    last_progress_time = now
                    progress_callback(written_bytes, manifest.total_uncompressed_size, len(extracted_paths))

            if not manifest.is_dir and len(manifest.files) == 1:
                file_entry = manifest.files[0]
                if not should_extract(file_entry.rel_path):
                    if not file_entry.is_symlink and file_entry.size > 0:
                        skip_bytes(file_entry.size)
                else:
                    if output_dir:
                        out_p = Path(output_dir).resolve()
                        if out_p.is_dir() or str(output_dir).endswith(("/", "\\")) or out_p.suffix == "":
                            target_file = out_p / file_entry.rel_path
                        else:
                            target_file = out_p
                    else:
                        target_file = out_base / file_entry.rel_path

                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    staging_file = target_file.parent / f".{target_file.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
                    staging_file_to_cleanup = staging_file
                    target_str = str(staging_file)

                    if file_entry.is_symlink:
                        _write_symlink_fast(target_str, file_entry.link_target, file_entry.mtime)
                    else:
                        try:
                            fd = os.open(target_str, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | O_BINARY, file_entry.mode)
                        except OSError:
                            try:
                                os.chmod(target_str, 0o777)
                            except OSError:
                                pass
                            try:
                                if os.path.isdir(target_str) and not os.path.islink(target_str):
                                    shutil.rmtree(target_str, ignore_errors=True)
                                else:
                                    os.unlink(target_str)
                            except OSError:
                                pass
                            fd = os.open(target_str, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | O_BINARY, file_entry.mode)

                        rem = file_entry.size
                        try:
                            while rem > 0:
                                if cur_mv is None or cur_offset >= len(cur_mv):
                                    chunk = block_queue.get()
                                    if chunk is None:
                                        if feeder_stats["error"]:
                                            raise feeder_stats["error"]
                                        raise EOFError("Unexpected EOF in archive")
                                    cur_block = chunk
                                    cur_mv = memoryview(chunk)
                                    cur_offset = 0

                                take = min(rem, len(cur_mv) - cur_offset)
                                _safe_write_all(fd, cur_mv[cur_offset : cur_offset + take])
                                cur_offset += take
                                rem -= take
                                written_bytes += take
                                maybe_report()
                            try:
                                os.utime(fd, (file_entry.mtime, file_entry.mtime))
                            except (OSError, NotImplementedError, TypeError):
                                try:
                                    os.utime(target_str, (file_entry.mtime, file_entry.mtime))
                                except OSError:
                                    pass
                            if file_entry.mode & 0o222 == 0:
                                try:
                                    os.fchmod(fd, file_entry.mode)
                                except (OSError, NotImplementedError, AttributeError):
                                    try:
                                        os.chmod(target_str, file_entry.mode)
                                    except OSError:
                                        pass
                        finally:
                            os.close(fd)

                    extracted_paths.append(str(target_file))

            else:
                if output_dir:
                    out_p = Path(output_dir).resolve()
                    if out_p.name == manifest.root_name:
                        dest_root = out_p
                    else:
                        dest_root = out_p / manifest.root_name
                else:
                    dest_root = out_base / manifest.root_name

                dest_root.parent.mkdir(parents=True, exist_ok=True)
                staging_root = dest_root.parent / f".{dest_root.name}.staging.{os.getpid()}.{uuid.uuid4().hex}"
                staging_dir_to_cleanup = staging_root
                staging_root.mkdir(parents=True, exist_ok=True)

                staging_root_str = str(staging_root)
                if not staging_root_str.endswith("/"):
                    staging_root_str += "/"
                dest_root_str = str(dest_root)
                if not dest_root_str.endswith("/"):
                    dest_root_str += "/"

                # Step 1: Upfront Directory Tree Materialization (Single Pass) in staging_root
                unique_dirs = set()
                for file_entry in manifest.files:
                    if not should_extract(file_entry.rel_path):
                        continue
                    rel_norm = file_entry.rel_path.replace("\\", "/")
                    if file_entry.is_dir:
                        parts = rel_norm.split("/")
                        curr = ""
                        for part in parts:
                            curr = (curr + "/" + part) if curr else part
                            unique_dirs.add(curr)
                    else:
                        p_idx = rel_norm.rfind("/")
                        if p_idx != -1:
                            parts = rel_norm[:p_idx].split("/")
                            curr = ""
                            for part in parts:
                                curr = (curr + "/" + part) if curr else part
                                unique_dirs.add(curr)

                sorted_dirs = sorted(unique_dirs, key=lambda d: (d.count("/"), len(d)))
                for d in sorted_dirs:
                    full_d = staging_root_str + d
                    try:
                        os.mkdir(full_d)
                    except FileExistsError:
                        pass
                    except OSError:
                        try:
                            os.makedirs(full_d, exist_ok=True)
                        except OSError:
                            pass

                # Step 2: Tuned Multi-threaded Writer Pool
                writer_threads_count = min(os.cpu_count() or 4, 4)
                file_queue: queue.Queue = queue.Queue(maxsize=64)
                worker_errors: List[Exception] = []

                def writer_worker():
                    while True:
                        batch = file_queue.get()
                        if batch is None:
                            file_queue.task_done()
                            break
                        if worker_errors:
                            file_queue.task_done()
                            continue
                        try:
                            for is_symlink, t_path, data, mode, mtime, extra in batch:
                                if not is_symlink:
                                    _write_single_file_fast(t_path, data, mode, mtime)
                                else:
                                    _write_symlink_fast(t_path, extra, mtime)
                        except Exception as e:
                            worker_errors.append(e)
                        finally:
                            file_queue.task_done()

                threads: List[threading.Thread] = []
                for _ in range(writer_threads_count):
                    t = threading.Thread(target=writer_worker, daemon=True)
                    t.start()
                    threads.append(t)

                current_batch: List[Tuple] = []
                batch_bytes = 0
                MAX_BATCH_FILES = 512
                MAX_BATCH_BYTES = 8 * 1024 * 1024

                def flush_batch():
                    nonlocal current_batch, batch_bytes
                    if current_batch:
                        file_queue.put(current_batch)
                        current_batch = []
                        batch_bytes = 0

                # Step 3: Stream and Pipeline File Writing to staging directory
                for file_entry in manifest.files:
                    if worker_errors:
                        raise worker_errors[0]
                    if feeder_stats["error"]:
                        raise feeder_stats["error"]

                    if not should_extract(file_entry.rel_path):
                        if not file_entry.is_dir and not file_entry.is_symlink and file_entry.size > 0:
                            skip_bytes(file_entry.size)
                        continue

                    rel_norm = file_entry.rel_path.replace("\\", "/")
                    staging_item_str = staging_root_str + rel_norm
                    final_item_str = dest_root_str + rel_norm

                    if file_entry.is_dir:
                        deferred_dir_perms.append((final_item_str, file_entry.mode, file_entry.mtime))
                        extracted_paths.append(final_item_str)
                        maybe_report()
                        continue

                    if file_entry.is_symlink:
                        current_batch.append((True, staging_item_str, None, 0, file_entry.mtime, file_entry.link_target))
                        extracted_paths.append(final_item_str)
                        if len(current_batch) >= MAX_BATCH_FILES:
                            flush_batch()
                        maybe_report()
                        continue

                    if file_entry.size == 0:
                        current_batch.append((False, staging_item_str, b"", file_entry.mode, file_entry.mtime, None))
                        extracted_paths.append(final_item_str)
                        if len(current_batch) >= MAX_BATCH_FILES:
                            flush_batch()
                        maybe_report()
                        continue

                    if file_entry.size <= 4 * 1024 * 1024:
                        data = get_bytes_slice(file_entry.size)
                        w_len = len(data)
                        written_bytes += w_len
                        current_batch.append((False, staging_item_str, data, file_entry.mode, file_entry.mtime, None))
                        batch_bytes += w_len
                        extracted_paths.append(final_item_str)
                        if len(current_batch) >= MAX_BATCH_FILES or batch_bytes >= MAX_BATCH_BYTES:
                            flush_batch()
                        maybe_report()
                        continue

                    # Large file (> 4MB): Stream directly with zero-copy NVMe I/O to staging_item_str
                    flush_batch()
                    try:
                        fd = os.open(staging_item_str, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | O_BINARY, file_entry.mode)
                    except OSError:
                        try:
                            os.chmod(staging_item_str, 0o777)
                        except OSError:
                            pass
                        try:
                            if os.path.isdir(staging_item_str) and not os.path.islink(staging_item_str):
                                shutil.rmtree(staging_item_str, ignore_errors=True)
                            else:
                                os.unlink(staging_item_str)
                        except OSError:
                            pass
                        fd = os.open(staging_item_str, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | O_BINARY, file_entry.mode)

                    rem = file_entry.size
                    try:
                        while rem > 0:
                            if cur_mv is None or cur_offset >= len(cur_mv):
                                chunk = block_queue.get()
                                if chunk is None:
                                    if feeder_stats["error"]:
                                        raise feeder_stats["error"]
                                    raise EOFError("Unexpected EOF in archive")
                                cur_block = chunk
                                cur_mv = memoryview(chunk)
                                cur_offset = 0

                            take = min(rem, len(cur_mv) - cur_offset)
                            _safe_write_all(fd, cur_mv[cur_offset : cur_offset + take])
                            cur_offset += take
                            rem -= take
                            written_bytes += take
                            maybe_report()
                        try:
                            os.utime(fd, (file_entry.mtime, file_entry.mtime))
                        except (OSError, NotImplementedError, TypeError):
                            try:
                                os.utime(staging_item_str, (file_entry.mtime, file_entry.mtime))
                            except OSError:
                                pass
                        if file_entry.mode & 0o222 == 0:
                            try:
                                os.fchmod(fd, file_entry.mode)
                            except (OSError, NotImplementedError, AttributeError):
                                try:
                                    os.chmod(staging_item_str, file_entry.mode)
                                except OSError:
                                    pass
                    finally:
                        os.close(fd)

                    extracted_paths.append(final_item_str)
                    maybe_report()

                # Flush remaining batches and wait for all writers
                flush_batch()
                file_queue.join()
                for _ in threads:
                    file_queue.put(None)
                for t in threads:
                    t.join()

                if worker_errors:
                    raise worker_errors[0]

            # Ensure feeder thread finishes and footer verification completes
            while True:
                if feeder_stats["error"]:
                    raise feeder_stats["error"]
                try:
                    item = block_queue.get(timeout=0.2)
                    if item is None:
                        break
                except queue.Empty:
                    if not feeder_thread.is_alive():
                        break

            feeder_thread.join()
            if feeder_stats["error"]:
                raise feeder_stats["error"]

            # Promote staged extractions atomically after 100% verified integrity
            if staging_file_to_cleanup and staging_file_to_cleanup.exists():
                os.replace(staging_file_to_cleanup, target_file)
                staging_file_to_cleanup = None

            if staging_dir_to_cleanup and staging_dir_to_cleanup.exists():
                _promote_staging_to_dest(staging_dir_to_cleanup, dest_root)
                staging_dir_to_cleanup = None
                # Restore directory timestamps & permissions on promoted directory
                deferred_dir_perms.sort(key=lambda item: (item[0].count("/"), len(item[0])), reverse=True)
                for d_str, d_mode, d_mtime in deferred_dir_perms:
                    try:
                        if d_mtime is not None:
                            os.utime(d_str, (d_mtime, d_mtime))
                    except OSError:
                        pass
                    try:
                        if d_mode is not None and (d_mode & 0o777) != 0o755:
                            os.chmod(d_str, d_mode)
                    except OSError:
                        pass

            decomp_success = True

            if progress_callback:
                progress_callback(written_bytes, manifest.total_uncompressed_size, len(extracted_paths))

        elapsed = time.perf_counter() - t0
        return {
            "status": "SUCCESS",
            "archive": str(archive_p),
            "files_extracted": len(extracted_paths),
            "total_uncompressed_bytes": feeder_stats["total_uncompressed"],
            "elapsed": elapsed,
            "extracted_paths": extracted_paths,
        }
    finally:
        writer_stop_event.set()
        stop_event.set()
        if not decomp_success:
            if staging_file_to_cleanup and staging_file_to_cleanup.exists():
                try:
                    staging_file_to_cleanup.unlink()
                except OSError:
                    pass
            if staging_dir_to_cleanup and staging_dir_to_cleanup.exists():
                shutil.rmtree(staging_dir_to_cleanup, ignore_errors=True)
        try:
            while not block_queue.empty():
                block_queue.get_nowait()
        except Exception:
            pass
        os.umask(old_umask)



def repair_archive(
    archive_path: str,
    output_repaired_path: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict:
    """
    Self-heals a corrupted archive using embedded Reed-Solomon parity records.
    Detects damaged blocks, reconstructs them mathematically, and writes a healthy archive.
    """
    t0 = time.perf_counter()
    from apex.foreign import is_foreign_archive
    if is_foreign_archive(archive_path):
        raise ValueError("Self-healing repair is only supported for Apex (.apx) archives.")

    archive_p = Path(archive_path).resolve()
    if not archive_p.exists():
        raise FileNotFoundError(f"Archive file not found: {archive_path}")

    if output_repaired_path:
        out_path = Path(output_repaired_path).resolve()
    else:
        out_path = archive_p.with_name(archive_p.stem + ".repaired.apx")

    with open(archive_p, "rb") as f:
        flags, block_size, manifest, enc_key, mac_key = read_archive_header(f, password=password)

        if not (flags & FLAG_RECOVERY):
            raise ValueError("This archive does not contain self-healing recovery records. Re-compress with '--recovery'.")

        header_struct = struct.Struct("<BIII")
        raw_blocks: Dict[int, bytes] = {}
        block_metas: List[Tuple[int, int, int, int, bytes]] = []
        damaged_block_idx: Optional[int] = None
        damaged_uncomp_len = 0
        damaged_crc = 0
        total_blocks = 0

        while True:
            hdr_bytes = f.read(header_struct.size)
            if not hdr_bytes:
                break
            pipeline_id, uncomp_len, comp_len, crc = header_struct.unpack(hdr_bytes)
            if pipeline_id == EOF_PIPELINE_ID:
                break

            payload = f.read(comp_len)
            block_metas.append((pipeline_id, uncomp_len, comp_len, crc, payload))

            try:
                dec_payload = payload
                if flags & FLAG_ENCRYPTED:
                    dec_payload = decrypt_payload(payload, enc_key, mac_key)

                if pipeline_id == PIPELINE_DEDUP_REF:
                    ref_idx = struct.unpack("<I", dec_payload)[0]
                    raw_chunk = raw_blocks[ref_idx]
                else:
                    raw_chunk = decompress_chunk(dec_payload, pipeline_id)

                if zlib.crc32(raw_chunk) == crc:
                    raw_blocks[total_blocks] = raw_chunk
                else:
                    damaged_block_idx = total_blocks
                    damaged_uncomp_len = uncomp_len
                    damaged_crc = crc
            except Exception:
                damaged_block_idx = total_blocks
                damaged_uncomp_len = uncomp_len
                damaged_crc = crc

            total_blocks += 1

        stored_sha = f.read(32)
        stored_uncomp, stored_blocks = struct.unpack("<QI", f.read(12))
        footer_magic = f.read(4)

        parity_hdr = f.read(8)
        if len(parity_hdr) != 8:
            raise ValueError("Corrupted archive: recovery record is truncated or missing.")
        parity_len, parity_max_block_len = struct.unpack("<II", parity_hdr)
        parity_data = f.read(parity_len)

        if damaged_block_idx is None:
            return {
                "status": "ALREADY_HEALTHY",
                "message": "Archive is 100% healthy, all CRC-32 and SHA-256 hashes matched.",
                "archive": str(archive_p),
                "elapsed": time.perf_counter() - t0,
            }

        healed_raw = heal_damaged_block(
            raw_blocks,
            damaged_block_idx,
            total_blocks,
            parity_data,
            damaged_uncomp_len,
        )

        if zlib.crc32(healed_raw) != damaged_crc:
            raise ValueError("Self-healing failed: too many blocks damaged beyond parity capacity.")

        raw_blocks[damaged_block_idx] = healed_raw

        healed_comp = compress_chunk(healed_raw, mode=Mode.BALANCED)
        healed_payload = healed_comp.data
        if flags & FLAG_ENCRYPTED:
            healed_payload = encrypt_payload(healed_payload, enc_key, mac_key)

        block_metas[damaged_block_idx] = (
            healed_comp.pipeline_id,
            damaged_uncomp_len,
            len(healed_payload),
            damaged_crc,
            healed_payload,
        )

    overall_hasher = hashlib.sha256()
    for idx in range(total_blocks):
        overall_hasher.update(raw_blocks[idx])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp_repaired_path = out_path.parent / f".{out_path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}.apx"
    repair_success = False

    try:
        with open(archive_p, "rb") as orig_f, open(temp_repaired_path, "wb") as out_f:
            orig_f.seek(0)
            out_f.write(orig_f.read(8))  # Magic
            hdr_b = orig_f.read(struct.calcsize("<HIII"))
            out_f.write(hdr_b)
            f_flags, b_size, m_raw_l, m_comp_l = struct.unpack("<HIII", hdr_b)
            if f_flags & FLAG_ENCRYPTED:
                out_f.write(orig_f.read(16))  # Salt
            out_f.write(orig_f.read(m_comp_l))  # Manifest

            for pid, u_len, c_len, crc, payload in block_metas:
                out_f.write(struct.pack("<BIII", pid, u_len, c_len, crc))
                out_f.write(payload)

            out_f.write(struct.pack("<BIII", EOF_PIPELINE_ID, 0, 0, 0))
            # Updated footer with verified SHA-256
            out_f.write(overall_hasher.digest())
            out_f.write(struct.pack("<QI", stored_uncomp, total_blocks))
            out_f.write(MAGIC_FOOTER)
            out_f.write(struct.pack("<II", len(parity_data), parity_max_block_len))
            out_f.write(parity_data)

            out_f.flush()
            try:
                os.fsync(out_f.fileno())
            except OSError:
                pass

        os.replace(temp_repaired_path, out_path)
        repair_success = True
    finally:
        if not repair_success and temp_repaired_path.exists():
            try:
                temp_repaired_path.unlink()
            except OSError:
                pass

    elapsed = time.perf_counter() - t0
    return {
        "status": "SUCCESS_REPAIRED",
        "original_archive": str(archive_p),
        "repaired_archive": str(out_path),
        "healed_block_index": damaged_block_idx,
        "blocks_verified": total_blocks,
        "elapsed": elapsed,
    }
