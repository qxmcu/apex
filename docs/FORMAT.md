# Apex Binary Container Specification (.apx)

Status: **Experimental / Draft v1.0**

This document specifies the byte-for-byte structure of an `.apx` file. Apex was designed to be easily parseable, streaming-friendly, and mathematically robust against bit-rot.

## 1. File Layout Overview

An `.apx` archive consists of four main sections, placed linearly in the file:

1.  **Global Header** (Magic Bytes + Stream Configuration)
2.  **Metadata Manifest** (Zstd-compressed JSON of directory trees and file metadata)
3.  **Stream Payload Blocks** (Sequential compressed data chunks with inline CRC-32)
4.  **Global Footer** (Stream SHA-256 + Optional Reed-Solomon Parity Records)

## 2. Global Header

The file begins with a 38-byte global header (or 22 bytes if unencrypted).

| Offset | Field | Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x00` | Magic Signature | `bytes` | 8 bytes | `b'APEX\x01\x00\x00\x00'` |
| `0x08` | Container Flags | `uint16` | 2 bytes | Bitmask of stream features |
| `0x0A` | Stream Block Size | `uint32` | 4 bytes | Dynamic chunk size (e.g. 2097152 = 2MB) |
| `0x0E` | Manifest Raw Len | `uint32` | 4 bytes | Uncompressed size of the JSON manifest |
| `0x12` | Manifest Comp Len | `uint32` | 4 bytes | Zstd-compressed size of the JSON manifest |
| `0x16` | Encryption Salt | `bytes` | 16 bytes | `os.urandom(16)` (Only present if `FLAG_ENCRYPTED`) |

### Container Flags Bitmask
*   `0x0001` (`FLAG_DIR`): Archive contains a directory tree.
*   `0x0002` (`FLAG_SOLID`): Archive is solid (all files concatenated before block chunking).
*   `0x0004` (`FLAG_ENCRYPTED`): Archive is encrypted via AES-256-CTR + HMAC-SHA256.
*   `0x0008` (`FLAG_RECOVERY`): Archive contains Cauchy Reed-Solomon parity at EOF.

## 3. Metadata Manifest

Immediately following the header is the Metadata Manifest.
*   **Length**: Dictated by the `Manifest Comp Len` field in the header.
*   **Format**: A Zstd-compressed JSON string.

If `FLAG_ENCRYPTED` is set, the manifest is encrypted *before* compression to mask directory structures and filenames.

### Manifest JSON Structure
```json
{
  "version": 1,
  "files": [
    {
      "path": "src/main.py",
      "size": 14205,
      "mode": 33188,
      "mtime": 1694200000.0,
      "offset": 0
    }
  ]
}
```

## 4. Stream Payload Blocks

Following the manifest are sequentially written blocks. Each block corresponds to a chunk of the original stream (dictated by `Stream Block Size`).

### Block Header (13 bytes)
| Offset | Field | Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x00` | Pipeline ID | `uint8` | 1 byte | Transform + Engine ID (e.g. `0x0A` = Stride + Zstd) |
| `0x01` | Uncomp Size | `uint32` | 4 bytes | Uncompressed chunk size (usually equals Block Size, except EOF) |
| `0x05` | Comp Size | `uint32` | 4 bytes | Compressed payload length |
| `0x09` | CRC-32 | `uint32` | 4 bytes | Checksum of the *uncompressed* payload |

### Block Payload
*   **Length**: Dictated by `Comp Size`.
*   **Content**: The compressed bytes. If `FLAG_ENCRYPTED` is active, the bytes are AES-256-CTR encrypted and MAC'd.

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
*   **Parity Payload Length**: 4 bytes
*   **Max Block Length**: 4 bytes
*   **Parity Data**: Galois Field $(2^8)$ Cauchy Generator Matrix output.

## 7. Compatibility, Determinism & Robustness Invariants

### Format Versioning
The `.apx` container format is independently versioned:
- Magic signature byte 4 (`0x01`) represents Container Format Version 1 (`b'APEX\x01\x00\x00\x00'`).
- Backward Compatibility: All APEX 1.x point releases are guaranteed to decompress archives created by any earlier 1.x version.
- Forward Compatibility: When an older decompressor encounters an unknown major format version (magic mismatch), it halts with an explicit version upgrade message.

### Cross-Platform Portability
- **Path Normalization**: All relative file paths inside the metadata manifest are stored using standard POSIX forward slashes (`/`), regardless of whether created on Windows (`\`) or UNIX.
- **Endianness**: All integer fields in headers, footers, and block structures are strictly serialized in standard Little-Endian format (`<`).
- **Permissions**: File modes and mtimes are preserved using standard POSIX representations; Windows platforms map appropriate read-only flags cleanly.

### Determinism Guarantee
Given identical input bytes, the same APEX release, and identical CLI arguments (mode, chunk size, threads), APEX produces byte-for-byte identical `.apx` container files across separate runs. Directory traversal sorts file manifest entries alphabetically to prevent filesystem non-determinism.

### Unknown Transform & Engine Handling
Each payload block specifies a 1-byte `Pipeline ID`. If an archive contains a Pipeline ID unknown to the running decompressor, the extraction process immediately raises an explicit error (`ValueError: Unrecognized pipeline ID 0xXX: please upgrade APEX to read this block`) and aborts, ensuring data corruption is never silently emitted to disk.
