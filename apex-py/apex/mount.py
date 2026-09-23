"""
Read-Only FUSE Mount Interface for Apex Archives (.apx).
Exposes an archive transparently as a virtual filesystem with an LRU block cache (~64 MB).
"""

import collections
import errno
import os
import stat
import sys
import threading
import time
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from apex.archive import (
    DEFAULT_BLOCK_SIZE,
    FLAG_ENCRYPTED,
    PIPELINE_DEDUP_REF,
    BlockMeta,
    FileEntry,
    read_archive_header,
    scan_block_index,
)
from apex.engine import decompress_chunk
from apex.security import decrypt_payload


class BlockLRUCache:
    """Thread-safe LRU block cache capped at max_bytes (~64 MB)."""

    def __init__(self, max_bytes: int = 64 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.current_bytes = 0
        self.cache: collections.OrderedDict[int, bytes] = collections.OrderedDict()
        self.lock = threading.Lock()

    def get(self, block_id: int) -> Optional[bytes]:
        with self.lock:
            if block_id in self.cache:
                self.cache.move_to_end(block_id)
                return self.cache[block_id]
            return None

    def put(self, block_id: int, data: bytes):
        with self.lock:
            if block_id in self.cache:
                self.cache.move_to_end(block_id)
                return
            data_len = len(data)
            while self.current_bytes + data_len > self.max_bytes and self.cache:
                _, evicted = self.cache.popitem(last=False)
                self.current_bytes -= len(evicted)
            self.cache[block_id] = data
            self.current_bytes += data_len

    def clear(self):
        with self.lock:
            self.cache.clear()
            self.current_bytes = 0


class ApexArchiveFS:
    """
    Virtual filesystem representation of an Apex archive.
    Provides standard POSIX read operations with index-based selective block decompression.
    """

    def __init__(self, archive_path: str, password: Optional[str] = None, cache_size_mb: int = 64):
        self.archive_path = str(Path(archive_path).resolve())
        self.password = password
        self.lru_cache = BlockLRUCache(max_bytes=cache_size_mb * 1024 * 1024)
        self.lock = threading.Lock()

        with open(self.archive_path, "rb") as f:
            self.flags, self.block_size, self.manifest, self.enc_key, self.mac_key = read_archive_header(
                f, password=password
            )
            self.blocks_info: List[BlockMeta] = scan_block_index(f, f.tell())

        self.files_by_path: Dict[str, FileEntry] = {}
        self.dir_children: Dict[str, List[str]] = {"": []}

        for f_entry in self.manifest.files:
            norm_p = f_entry.rel_path.replace("\\", "/").strip("/")
            self.files_by_path[norm_p] = f_entry

            parts = norm_p.split("/")
            for i in range(len(parts)):
                parent = "/".join(parts[:i])
                child = parts[i]
                if parent not in self.dir_children:
                    self.dir_children[parent] = []
                if child not in self.dir_children[parent]:
                    self.dir_children[parent].append(child)

    def decode_block(self, block_id: int) -> bytes:
        """Decodes an individual block on demand, checking LRU cache first."""
        cached = self.lru_cache.get(block_id)
        if cached is not None:
            return cached

        with self.lock:
            cached = self.lru_cache.get(block_id)
            if cached is not None:
                return cached

            if block_id >= len(self.blocks_info):
                raise IndexError(f"Block ID {block_id} out of range")

            b_meta = self.blocks_info[block_id]
            with open(self.archive_path, "rb") as f:
                if b_meta.pipeline_id == PIPELINE_DEDUP_REF:
                    ref_idx = b_meta.ref_idx if b_meta.ref_idx is not None else 0
                    ref_data = self.decode_block(ref_idx)
                    self.lru_cache.put(block_id, ref_data)
                    return ref_data
                else:
                    f.seek(b_meta.payload_offset)
                    payload = f.read(b_meta.comp_len)
                    if self.flags & FLAG_ENCRYPTED:
                        payload = decrypt_payload(payload, self.enc_key, self.mac_key)
                    raw = decompress_chunk(payload, b_meta.pipeline_id)
                    if zlib.crc32(raw) != b_meta.crc:
                        raise ValueError(f"CRC-32 mismatch on block {block_id}")
                    self.lru_cache.put(block_id, raw)
                    return raw

    def getattr(self, path: str) -> Dict[str, Any]:
        norm = path.strip("/")
        now = time.time()
        if not norm or norm in self.dir_children:
            return {
                "st_mode": stat.S_IFDIR | 0o755,
                "st_nlink": 2,
                "st_size": 4096,
                "st_mtime": now,
                "st_ctime": now,
                "st_atime": now,
            }
        if norm in self.files_by_path:
            f = self.files_by_path[norm]
            if f.is_symlink:
                return {
                    "st_mode": stat.S_IFLNK | 0o777,
                    "st_nlink": 1,
                    "st_size": len(f.link_target.encode("utf-8")),
                    "st_mtime": f.mtime,
                    "st_ctime": f.mtime,
                    "st_atime": f.mtime,
                }
            elif f.is_dir:
                return {
                    "st_mode": stat.S_IFDIR | (f.mode or 0o755),
                    "st_nlink": 2,
                    "st_size": 4096,
                    "st_mtime": f.mtime,
                    "st_ctime": f.mtime,
                    "st_atime": f.mtime,
                }
            else:
                return {
                    "st_mode": stat.S_IFREG | (f.mode or 0o644),
                    "st_nlink": 1,
                    "st_size": f.size,
                    "st_mtime": f.mtime,
                    "st_ctime": f.mtime,
                    "st_atime": f.mtime,
                }
        raise OSError(errno.ENOENT, f"No such file or directory: {path}")

    def readdir(self, path: str) -> List[str]:
        norm = path.strip("/")
        if norm not in self.dir_children:
            raise OSError(errno.ENOENT, f"No such directory: {path}")
        return [".", ".."] + self.dir_children[norm]

    def readlink(self, path: str) -> str:
        norm = path.strip("/")
        if norm in self.files_by_path and self.files_by_path[norm].is_symlink:
            return self.files_by_path[norm].link_target
        raise OSError(errno.EINVAL, f"Not a symlink: {path}")

    def read(self, path: str, size: int, offset: int) -> bytes:
        norm = path.strip("/")
        if norm not in self.files_by_path:
            raise OSError(errno.ENOENT, f"No such file: {path}")
        entry = self.files_by_path[norm]
        if entry.is_dir or entry.is_symlink or entry.size == 0:
            return b""
        if offset >= entry.size:
            return b""

        to_read = min(size, entry.size - offset)
        global_start = entry.solid_offset + offset
        global_end = global_start + to_read

        chunks = []
        for b in self.blocks_info:
            if b.solid_end <= global_start or b.solid_start >= global_end:
                continue
            block_data = self.decode_block(b.block_id)
            slc_start = max(0, global_start - b.solid_start)
            slc_end = min(len(block_data), global_end - b.solid_start)
            chunks.append(block_data[slc_start:slc_end])

        return b"".join(chunks)

    # Read-only enforcement
    def write(self, *args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    def create(self, *args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    def mkdir(self, *args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    def unlink(self, *args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    def rmdir(self, *args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    def rename(self, *args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    def truncate(self, *args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    def chmod(self, *args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    def chown(self, *args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system")


def mount_archive(
    archive_path: str,
    mountpoint: str,
    password: Optional[str] = None,
    cache_size_mb: int = 64,
    foreground: bool = True,
):
    """
    Mounts an Apex archive at mountpoint using FUSE.
    Requires fusepy and a system FUSE driver (macFUSE, libfuse, or WinFsp).
    """
    try:
        from fuse import FUSE, Operations
    except ImportError:
        try:
            import fuse
            FUSE = getattr(fuse, "FUSE", None)
            Operations = getattr(fuse, "Operations", object)
            if FUSE is None:
                raise ImportError("No FUSE class in fuse module")
        except Exception as e:
            raise RuntimeError(
                "FUSE library not available. To use 'apex mount', install macFUSE (macOS), "
                "libfuse (Linux), or WinFsp (Windows), and ensure fusepy is installed."
            ) from e

    fs = ApexArchiveFS(archive_path, password=password, cache_size_mb=cache_size_mb)

    class ApexFuseBridge(Operations):
        def getattr(self, path, fh=None):
            return fs.getattr(path)

        def readdir(self, path, fh):
            return fs.readdir(path)

        def readlink(self, path):
            return fs.readlink(path)

        def read(self, path, size, offset, fh):
            return fs.read(path, size, offset)

        def open(self, path, flags):
            # Check read-only
            if (flags & os.O_ACCMODE) != os.O_RDONLY:
                raise OSError(errno.EROFS, "Read-only file system")
            return 0

        def write(self, path, data, offset, fh):
            raise OSError(errno.EROFS, "Read-only file system")

        def create(self, path, mode, fi=None):
            raise OSError(errno.EROFS, "Read-only file system")

        def mkdir(self, path, mode):
            raise OSError(errno.EROFS, "Read-only file system")

        def unlink(self, path):
            raise OSError(errno.EROFS, "Read-only file system")

        def rmdir(self, path):
            raise OSError(errno.EROFS, "Read-only file system")

        def rename(self, old, new):
            raise OSError(errno.EROFS, "Read-only file system")

    Path(mountpoint).mkdir(parents=True, exist_ok=True)
    FUSE(ApexFuseBridge(), mountpoint, foreground=foreground, ro=True, allow_other=False)
