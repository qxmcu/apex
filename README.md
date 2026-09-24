<div align="center">
  <img src="logo.svg" width="100" height="100" alt="ApexCompress Logo" />
  <h1>ApexCompress (apex)</h1>
  <p><strong>Adaptive multi-engine archival system with FastCDC deduplication, granular block indexing, and Cauchy Reed-Solomon self-healing</strong></p>

  <p>
    <a href="https://github.com/qxmcu/apex/releases"><img src="https://img.shields.io/badge/release-v1.3.0-brightgreen?style=flat-square" alt="Release" /></a>
    <a href="https://github.com/qxmcu/apex/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue?style=flat-square" alt="License" /></a>
    <a href="https://github.com/qxmcu/homebrew-tap"><img src="https://img.shields.io/badge/homebrew-tap-orange?style=flat-square" alt="Homebrew" /></a>
    <a href="https://github.com/qxmcu/apex/actions"><img src="https://img.shields.io/badge/tests-63%20passed-success?style=flat-square" alt="Tests" /></a>
    <a href="https://qxmcu.github.io/apex/"><img src="https://img.shields.io/badge/docs-interactive%20portal-darkgreen?style=flat-square" alt="Documentation" /></a>
  </p>
</div>

---

ApexCompress is an archival tool and container format engineered for modern multi-core processors. Rather than forcing all data through a single fixed compression algorithm, Apex analyzes incoming data blocks, runs an adaptive tournament across multiple compression engines, and applies reversible domain preconditioning filters to maximize compression density and throughput.

Complete interactive documentation, technical specifications, benchmark logs, and the full CLI reference are available on the project website: **[https://qxmcu.github.io/apex/](https://qxmcu.github.io/apex/)**

---

## Key Highlights

- **Multi-Engine Tournament**: Automatically races Zstandard, LZMA2, Deflate, Brotli, and Bzip2 across dynamic block partitions to select the highest-density compressor per data segment.
- **Granular Block Indexing & Instant Selective Extraction**: Every file entry records exact container mapping metadata (`block_id`, `offset`, `length`). Extracting individual files or patterns (`apex x archive.apx path -d out`) decodes only the blocks containing target data, skipping unreferenced blocks entirely.
- **Tar Compatibility & Unix Pipeline Streaming**: Full support for clustered tar flags (`-cvf`, `-xvf`, `-tvf`, `-c0f`), non-seekable streaming over standard streams (`apex -cf - src/ > out.apx`, `cat out.apx | apex -xf -`), and null-delimited file list ingestion from `find -print0`.
- **Transparent Foreign Archive Engine**: Magic-byte signature detection seamlessly inspects (`apex list archive.zip`) and extracts (`apex extract archive.tar.gz`) foreign formats without third-party dependencies.
- **Standalone Incremental Archiving**: Fast chunk deduplication via BLAKE2b hashes against a base container (`apex compress src -o day2.apx --base day1.apx`). Matching chunks are copied directly without recompression, and resulting archives extract completely standalone with zero dependency on the base.
- **Read-Only FUSE Virtual Filesystem**: Mount containers transparently as read-only directories (`apex mount archive.apx /mnt`) backed by an integrated 64 MB LRU block cache for instant, low-overhead random reads.
- **Domain Preconditioning Filters**: Dedicated byte-level preconditioning transforms for structured formats, including Delta-1/2/4, Planar-4 (float/int), BCJ branch filters (x86 and ARM64), BC1/BC7 GPU textures, and 3D coordinate transposition.
- **FastCDC Block Deduplication**: Content-Defined Chunking with Gear hashing detects identical and shifted blocks across directories, DLCs, and patch sets without decompressing identical data twice.
- **Self-Healing Reed-Solomon Parity**: Optional Cauchy Reed-Solomon erasure coding attached at EOF can mathematically reconstruct corrupt or erased blocks bit-for-bit.
- **Zero-Bloat Pass-Through**: Automatic Shannon entropy classification bypasses compression on already compressed or encrypted files (media, zip files, binaries) with zero expansion overhead.
- **Authenticated Encryption**: Full container encryption using ChaCha20-Poly1305 or hardware-accelerated AES-256-CTR with independent subkeys derived via PBKDF2-HMAC-SHA256 (100k rounds) and RFC 5869 HKDF-Expand domain separation.
- **Microsecond Metadata Diffing**: Inspect changes between two archives instantaneously using metadata headers without decompressing file contents.

---

## Benchmark Snapshot

Tested on AMD Ryzen 3 3250U (2 cores, 4 threads, 2.6 GHz), 8 GB DDR4, NVMe PCIe 3.0 SSD on the standard 282 MB Canterbury Corpus:

| Tool & Preset | Time | Throughput | Compressed Size | Space Saved | Ratio |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Apex FAST** | **2.44 s** | **115.6 MB/s** | 4.4 MB | 98.44% | 64.09x |
| **Apex BALANCED** | **6.70 s** | **42.1 MB/s** | 4.2 MB | 98.51% | 67.14x |
| **Apex ULTRA** | **53.20 s** | **5.3 MB/s** | **3.9 MB** | **98.62%** | **72.31x** |
| Gzip -9 | 16.58 s | 17.0 MB/s | 10.2 MB | 96.38% | 27.65x |
| Bzip2 -9 | 28.12 s | 10.0 MB/s | 6.8 MB | 97.59% | 41.47x |
| Zstandard -19 | 49.30 s | 5.7 MB/s | 4.1 MB | 98.55% | 68.78x |
| XZ -9e (LZMA2) | 648.10 s | 0.4 MB/s | 3.9 MB | 98.62% | 72.31x |

Apex ULTRA matches XZ -9e extreme density while completing substantially faster through parallel multi-core execution.

---

## Installation

### Package Managers

#### Homebrew (macOS & Linux)

```bash
brew install qxmcu/tap/apex
```

#### Windows Package Manager (WinGet)

```powershell
winget install qxmcu.apex
```

#### Scoop (Windows)

```powershell
scoop install https://raw.githubusercontent.com/qxmcu/apex/main/packaging/scoop/apex.json
```

### Standalone Pre-Compiled Native Binaries

Pre-compiled, zero-dependency standalone executables are available on the [GitHub Releases](https://github.com/qxmcu/apex/releases/tag/v1.3.0) page:

```bash
# macOS (Darwin x86_64 / Apple Silicon via Rosetta)
curl -LO https://github.com/qxmcu/apex/releases/download/v1.3.0/apex-v1.3.0-darwin-x86_64.tar.gz
tar -xzf apex-v1.3.0-darwin-x86_64.tar.gz
sudo mv apex /usr/local/bin/

# Linux (GLIBC 2.28+ x86_64)
curl -LO https://github.com/qxmcu/apex/releases/download/v1.3.0/apex-v1.3.0-linux-x86_64.tar.gz
tar -xzf apex-v1.3.0-linux-x86_64.tar.gz
sudo mv apex /usr/local/bin/

# Windows 10 / 11 (PowerShell)
curl -LO https://github.com/qxmcu/apex/releases/download/v1.3.0/apex-v1.3.0-windows-x86_64.zip
tar -xf apex-v1.3.0-windows-x86_64.zip
.\apex.exe --help
```

#### Binary Checksums (SHA-256)

| Platform / Architecture | Archive | SHA-256 Checksum |
| :--- | :--- | :--- |
| **macOS** (Darwin x86_64) | `apex-v1.3.0-darwin-x86_64.tar.gz` | `5c930feae2633f4acaa326423ff2c120fd3c73aa53b6599836661e68b3f4b89b` |
| **Linux** (GLIBC 2.28+ x86_64) | `apex-v1.3.0-linux-x86_64.tar.gz` | `360f76a52a27299b7083f35bdf4f78a0a406cd43606dd0d9b142a2417e904ffb` |
| **Windows** (x86_64) | `apex-v1.3.0-windows-x86_64.zip` | `46b63ba7ca108bab13c7e1c025d1313190ff08fbde873c5808c62684f31e12a8` |

### GitHub Action for CI/CD

Integrate high-speed archive compression directly into your GitHub Actions workflows:

```yaml
- name: Compress Build Artifacts
  uses: qxmcu/apex/.github/actions/apex-pack@v1.3.0
  with:
    path: 'build/dist'
    output: 'dist.apx'
    mode: 'balanced'
    recovery: true
```

### System File Type Magic

Register `.apx` container signatures with system `file(1)` utilities:

```bash
# Add to user magic file
cat packaging/magic >> ~/.magic
file archive.apx
# Output: archive.apx: Apex Compressed Archive (.apx), version 1
```

### Python Package (pip)

```bash
git clone https://github.com/qxmcu/apex.git
cd apex
pip install -e .
```

---

## CLI Quickstart

```bash
# Standard compression
apex compress path/to/data -o backup.apx -m balanced

# Tar-compatible syntax: create, extract, and list
apex -cvf archive.apx src/
apex -xvf archive.apx -d output/
apex -tvf archive.apx

# Unix pipelines without seeking on stdout
apex -cf - src/ > backup.apx
cat backup.apx | apex -xf -
apex -cf - src/ | ssh user@remote "apex -xf -"

# Ingest null-delimited file lists from find -print0
find . -name "*.log" -print0 | apex -c0f logs.apx

# Instant selective extraction (decodes only target blocks using container index)
apex x archive.apx path/to/file -d output/
apex decompress backup.apx -d output/ -e "*.json"

# Standalone incremental compression (zero-copy block reuse from base archive)
apex compress src/ -o day2.apx --base day1.apx

# Read-only virtual filesystem mount via FUSE (64 MB LRU block cache)
apex mount archive.apx /mnt/point

# Transparent foreign archive inspection and extraction
apex list bundle.zip
apex extract legacy.tar.gz -d output/

# Compress with self-healing Reed-Solomon parity records (~5% overhead)
apex compress large_project/ -o archive.apx -r

# Compress excluding specific directories or patterns
apex compress . -o repo.apx --exclude .git --exclude node_modules

# Verify archive integrity (non-destructive SHA-256 and CRC32 check)
apex test backup.apx

# Instant archive diffing (compares two archives without extracting)
apex diff v1.apx v2.apx

# Repair a corrupted or damaged archive using Reed-Solomon parity
apex repair damaged.apx -o healed.apx

# Run an automated tournament benchmark against Gzip, Bzip2, XZ, Zstd, and Brotli
apex benchmark sample.bin

# Inspect Shannon entropy and compressibility (or base archive reuse)
apex info dataset.bin
apex info day2.apx
```

---

## Python Library SDK

Apex provides a native Python SDK for direct in-memory and file-based compression workflows:

```python
import apex

# Compress and decompress files/directories
apex.compress_file("my_project/", "archive.apx", mode="balanced", recovery=True)
apex.decompress_file("archive.apx", "extracted/", extract_patterns=["*.py"])

# Standalone incremental compression
apex.compress_file("updated_project/", "day2.apx", base_archive="day1.apx")

# Transparent foreign archive inspection
foreign_entries = apex.read_foreign("bundle.zip")

# Verify archive integrity
is_valid = apex.test_archive("archive.apx")

# Instant archive diffing
diff = apex.diff_archives("v1.apx", "v2.apx")
print(f"Added: {len(diff.added_files)}, Modified: {len(diff.modified_files)}")

# In-memory buffer tournament compression (zero disk I/O)
compressed_bytes = apex.compress_buffer(b"Raw payload data...")
original_bytes = apex.decompress_buffer(compressed_bytes)

# Mount archive as virtual read-only FUSE filesystem
# apex.mount_archive("archive.apx", "/mnt/virtual", cache_size_mb=64)
```

---

## Documentation & Deep Dive

For the complete documentation suite, visit **[https://qxmcu.github.io/apex/](https://qxmcu.github.io/apex/)**:

- **[CLI Command Manual](https://qxmcu.github.io/apex/#commands)**: Detailed parameter breakdown for all subcommands and tar flags.
- **[Python SDK Reference](https://qxmcu.github.io/apex/#sdk)**: Full API signatures, options, and streaming examples.
- **[Container Specification (.apx)](https://qxmcu.github.io/apex/#spec)**: Byte-level layout, block indexing, header flags, and cryptographic envelopes.
- **[Verification Data & Shootouts](https://qxmcu.github.io/apex/#benchmarks)**: Canterbury Corpus, repeated data deduplication, and 12.3 GB Xcode toolchain benchmarks.
- **[Architectural Comparison](https://qxmcu.github.io/apex/#audit)**: Comparison matrix against WinRAR (.rar), 7-Zip (.7z), and WinZip (.zip).

---

## Products using Apex

- **[ezconvertsuite.com](https://ezconvertsuite.com/)**: Online high-speed audio conversion and media processing pipeline utilizing Apex's domain preconditioning filters for asset archiving.

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for architecture guidelines, code standards, and the local test suite workflow.

---

## License

ApexCompress is free software licensed under the **Apache License, Version 2.0**. See [LICENSE](LICENSE) for details.
