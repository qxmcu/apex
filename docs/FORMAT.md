# Apex Binary Container Specification (.apx)

Status: **Production Specification v1.2.0**

This document specifies the byte-for-byte structure of an `.apx` file. Apex was designed to be easily parseable, streaming-friendly, zero-copy NVMe optimized, and mathematically robust against bit-rot.

## 1. File Layout Overview

An `.apx` archive consists of four main sections, placed linearly in the file:

1.  **Global Header** (Magic Bytes + Stream Configuration)
2.  **Metadata Manifest** (Deflate-compressed JSON of directory trees, permissions, symlinks, and file offsets)
3.  **Stream Payload Blocks** (Sequential compressed data chunks with inline CRC-32)
4.  **Global Footer** (Stream SHA-256 + Optional Reed-Solomon Parity Records)

## 2. Global Header

The file begins with a 38-byte global header (or 22 bytes if unencrypted).

| Offset | Field | Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x00` | Magic Signature | `bytes` | 8 bytes | `b'APEX\x01\x00\x00\x00'` |
| `0x08` | Container Flags | `uint16` | 2 bytes | Bitmask of stream features |
| `0x0A` | Stream Block Size | `uint32` | 4 bytes | Dynamic chunk size (e.g. 2097152 = 2MB, 4194304 = 4MB) |
| `0x0E` | Manifest Raw Len | `uint32` | 4 bytes | Uncompressed size of the JSON manifest |
| `0x12` | Manifest Comp Len | `uint32` | 4 bytes | Deflate-compressed size of the JSON manifest (level 9) |
| `0x16` | Encryption Salt | `bytes` | 16 bytes | Cryptographic salt (Only present if `FLAG_ENCRYPTED`) |

### Container Flags Bitmask
*   `0x0001` (`FLAG_IS_DIR`): Archive contains a directory tree.
*   `0x0002` (`FLAG_SOLID`): Archive is solid (all files concatenated into a continuous stream before block chunking).
*   `0x0004` (`FLAG_SHA256`): Global 256-bit SHA stream digest present in footer.
*   `0x0008` (`FLAG_ENCRYPTED`): Manifest and all payload blocks are protected with authenticated encryption.
*   `0x0010` (`FLAG_RECOVERY`): Archive contains Cauchy Reed-Solomon parity records at EOF.

## 3. Metadata Manifest & Authenticated Encryption

Immediately following the header is the Metadata Manifest.
*   **Length**: Dictated by the `Manifest Comp Len` field in the header.
*   **Format**: Deflate-compressed JSON string (level 9).

If `FLAG_ENCRYPTED` is set, the manifest and block payloads are encrypted with PBKDF2-HMAC-SHA256 derived keys (100,000 rounds).

### Authenticated Encryption Payload Format
Encrypted payloads follow an explicit envelope:
```
+-------------------+----------------------+------------------------+----------------------+
| Cipher ID (1 byte)| Nonce / IV (12/16 B) | Ciphertext (N bytes)   | HMAC-SHA256 (32 B)   |
+-------------------+----------------------+------------------------+----------------------+
```
*   `0x01` (`CIPHER_CHACHA20_HMAC_SHA256`): Default portable cipher. In-process pure Python implementation immune to platform toolchain mismatches.
*   `0x02` (`CIPHER_AES256_CTR_HMAC`): Hardware-accelerated AES-256-CTR with HMAC-SHA256.

All authenticated encryption envelopes verify HMAC before decryption to prevent padding oracle or tampering attacks.

### Manifest JSON Structure
```json
{
  "is_dir": true,
  "root_name": "my_project",
  "total_uncompressed_size": 104857600,
  "files": [
    {
      "path": "src/main.py",
      "size": 14205,
      "mode": 33188,
      "mtime": 1726300000.0,
      "offset": 0,
      "is_symlink": false,
      "link_target": "",
      "is_dir": false
    }
  ]
}
```

## 4. Stream Payload Blocks

Following the manifest are sequentially written blocks. Each block corresponds to a chunk of the original stream (fixed block size or FastCDC).

### Block Header (13 bytes)
| Offset | Field | Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x00` | Pipeline ID | `uint8` | 1 byte | Transform + Engine ID (e.g. `0x0A` = Stride + Zstd, `0xFE` = Dedup Ref) |
| `0x01` | Uncomp Size | `uint32` | 4 bytes | Uncompressed chunk size |
| `0x05` | Comp Size | `uint32` | 4 bytes | Compressed payload length |
| `0x09` | CRC-32 | `uint32` | 4 bytes | Checksum of the *uncompressed* payload |

### Deduplication References (`0xFE`)
When a block is identical to an earlier block, `Pipeline ID = 0xFE` is emitted. Its payload contains a little-endian `uint32` pointing to the 0-indexed predecessor block. Candidates are cryptographically verified using 256-bit BLAKE2b hashes before referencing.

### Fast Content-Defined Chunking (FastCDC)
When `--cdc` is specified, blocks are sliced using normalized dual-mask Gear hash chunking (USENIX ATC '16) with a deterministic 256-entry gear table, guaranteeing stable boundaries across byte insertions, game patches, and delta distributions.

### End of Stream Marker
The payload section is terminated by an empty block with `Pipeline ID = 0xFF`:
*   `[0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]`

## 5. Global Footer

The 48-byte footer guarantees stream-wide integrity and allows reverse-seeking.

| Offset | Field | Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x00` | Stream SHA-256 | `bytes` | 32 bytes | Hash of the entire *uncompressed* concatenated stream |
| `0x20` | Total Uncomp Size | `uint64` | 8 bytes | Total uncompressed bytes across all blocks |
| `0x28` | Total Block Count | `uint32` | 4 bytes | Total number of blocks |
| `0x2C` | Footer Magic | `bytes` | 4 bytes | `b'XPED'` |

## 6. Self-Healing Parity (Optional)

If `FLAG_RECOVERY` is set, Reed-Solomon parity records are appended *after* the footer.
*   **Parity Payload Length**: 4 bytes (`uint32`)
*   **Max Block Length**: 4 bytes (`uint32`)
*   **Parity Data**: Galois Field $(2^8)$ Cauchy Generator Matrix output.

## 7. Compatibility, Determinism & Atomic Invariants

### Atomic Container Writing & Rollback
To prevent data loss or corrupted partial archives:
- **Archive Creation**: All `.apx` container writes stream to a sibling temporary file (`.<dest>.tmp.<pid>.<uuid>.apx`) on the exact same filesystem, followed by an OS-level `fsync`. The file is promoted to destination via an atomic rename (`os.replace`) only after the footer, SHA-256, and parity are flushed.
- **Decompression Staging**: Extractions stage files in a sibling temporary directory (`.<dest>.staging.<pid>.<uuid>`). Only upon 100% verification of every block CRC-32 and overall stream SHA-256 is the staged directory promoted to destination. If verification fails, the staging directory is completely purged, leaving destination files untainted.

### Cross-Platform Portability
- **Path Normalization**: All relative file paths inside the metadata manifest are stored using standard POSIX forward slashes (`/`), regardless of whether created on Windows (`\`) or UNIX.
- **Endianness**: All integer fields in headers, footers, and block structures are strictly serialized in standard Little-Endian format (`<`).
- **Permissions**: File modes and mtimes are preserved using standard POSIX representations; Windows platforms map appropriate read-only flags cleanly.

### Determinism Guarantee
Given identical input bytes, the same APEX release, and identical CLI arguments (mode, chunk size, threads), APEX produces byte-for-byte identical `.apx` container files across separate runs. Directory traversal sorts file manifest entries alphabetically to prevent filesystem non-determinism.

