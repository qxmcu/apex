<div align="center">
  <img src="logo.svg" width="100" height="100" alt="ApexCompress Logo" />
  <h1>ApexCompress (apex)</h1>
  <p><strong>Adaptive multi-engine archival system with FastCDC deduplication and Cauchy Reed-Solomon self-healing</strong></p>

  <p>
    <a href="https://github.com/qxmcu/apex/releases"><img src="https://img.shields.io/badge/release-v1.2.0-brightgreen?style=flat-square" alt="Release" /></a>
    <a href="https://github.com/qxmcu/apex/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue?style=flat-square" alt="License" /></a>
    <a href="https://github.com/qxmcu/homebrew-tap"><img src="https://img.shields.io/badge/homebrew-tap-orange?style=flat-square" alt="Homebrew" /></a>
    <a href="https://github.com/qxmcu/apex/actions"><img src="https://img.shields.io/badge/tests-53%20passed-success?style=flat-square" alt="Tests" /></a>
    <a href="https://qxmcu.github.io/apex/"><img src="https://img.shields.io/badge/docs-interactive%20portal-darkgreen?style=flat-square" alt="Documentation" /></a>
  </p>
</div>

---

ApexCompress is an archival tool and container format engineered for modern multi-core processors. Rather than forcing all data through a single fixed compression algorithm, Apex analyzes incoming data blocks, runs an adaptive tournament across multiple compression engines, and applies reversible domain preconditioning filters to maximize compression density and throughput.

Complete interactive documentation, technical specifications, benchmark logs, and the full CLI reference are available on the project website: **[https://qxmcu.github.io/apex/](https://qxmcu.github.io/apex/)**

---

## Key Highlights

- **Multi-Engine Tournament**: Automatically races Zstandard, LZMA2, Deflate, Brotli, and Bzip2 across dynamic block partitions to select the highest-density compressor per data segment.
- **Domain Preconditioning Filters**: Dedicated byte-level preconditioning transforms for structured formats, including Delta-1/2/4, Planar-4 (float/int), BCJ branch filters (x86 and ARM64), BC1/BC7 GPU textures, and 3D coordinate transposition.
- **FastCDC Block Deduplication**: Content-Defined Chunking with Gear hashing detects identical and shifted blocks across directories, DLCs, and patch sets without decompressing identical data twice.
- **Self-Healing Reed-Solomon Parity**: Optional Cauchy Reed-Solomon erasure coding attached at EOF can mathematically reconstruct corrupt or erased blocks bit-for-bit.
- **Zero-Bloat Pass-Through**: Automatic Shannon entropy classification bypasses compression on already compressed or encrypted files (media, zip files, binaries) with zero expansion overhead.
- **Authenticated Encryption**: Full container encryption using ChaCha20-Poly1305 or hardware-accelerated AES-256-CTR with HMAC-SHA256 and PBKDF2 key derivation.
- **Selective Extraction & Microsecond Diffing**: Inspect and extract individual files by pattern without full container extraction; compare two archives instantaneously using metadata headers.

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

### Homebrew (macOS & Linux)

```bash
brew install qxmcu/tap/apex
```

### Standalone Pre-Compiled Native Binaries

Pre-compiled, zero-dependency standalone executables are available on the [GitHub Releases](https://github.com/qxmcu/apex/releases) page.

```bash
# macOS (Darwin x86_64 / Apple Silicon via Rosetta)
curl -LO https://github.com/qxmcu/apex/releases/download/v1.2.0/apex-v1.2.0-darwin-x86_64.tar.gz
tar -xzf apex-v1.2.0-darwin-x86_64.tar.gz
sudo mv apex /usr/local/bin/

# Linux (GLIBC 2.28+)
curl -LO https://github.com/qxmcu/apex/releases/download/v1.2.0/apex-v1.2.0-linux-x86_64.tar.gz
tar -xzf apex-v1.2.0-linux-x86_64.tar.gz
sudo mv apex /usr/local/bin/

# Windows 10 / 11 (PowerShell)
curl -LO https://github.com/qxmcu/apex/releases/download/v1.2.0/apex-v1.2.0-windows-x86_64.zip
tar -xf apex-v1.2.0-windows-x86_64.zip
.\apex.exe --help
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
# Compress a directory or file
apex compress path/to/data -o backup.apx -m balanced

# Compress with self-healing Reed-Solomon parity records (~5% overhead)
apex compress large_project/ -o archive.apx -r

# Compress excluding specific directories or patterns
apex compress . -o repo.apx --exclude .git --exclude node_modules

# Decompress an archive
apex decompress backup.apx -d output/

# Selective extraction (extract only matching files without decompressing the rest)
apex decompress backup.apx -d output/ -e "*.json"

# Verify archive integrity (non-destructive SHA-256 and CRC32 check)
apex test backup.apx

# Inspect archive contents and manifest
apex list backup.apx

# Instant archive diffing (compares two archives without extracting)
apex diff v1.apx v2.apx

# Repair a corrupted or damaged archive using Reed-Solomon parity
apex repair damaged.apx -o healed.apx

# Run an automated tournament benchmark against Gzip, Bzip2, XZ, Zstd, and Brotli
apex benchmark sample.bin

# Inspect file compressibility and Shannon entropy
apex info dataset.bin
```

---

## Python Library SDK

Apex provides a native Python SDK for direct in-memory and file-based compression workflows:

```python
import apex

# Compress and decompress files/directories
apex.compress_file("my_project/", "archive.apx", mode="balanced", recovery=True)
apex.decompress_file("archive.apx", "extracted/", extract_patterns=["*.py"])

# Verify archive integrity
is_valid = apex.test_archive("archive.apx")

# Instant archive diffing
diff = apex.diff_archives("v1.apx", "v2.apx")
print(f"Added: {len(diff.added_files)}, Modified: {len(diff.modified_files)}")

# In-memory buffer tournament compression (zero disk I/O)
compressed_bytes = apex.compress_buffer(b"Raw payload data...")
original_bytes = apex.decompress_buffer(compressed_bytes)
```

---

## Documentation & Deep Dive

For the complete documentation suite, visit **[https://qxmcu.github.io/apex/](https://qxmcu.github.io/apex/)**:

- **[CLI Command Manual](https://qxmcu.github.io/apex/#commands)**: Detailed parameter breakdown for all 9 CLI subcommands.
- **[Python SDK Reference](https://qxmcu.github.io/apex/#sdk)**: Full API signatures, options, and streaming examples.
- **[Container Specification (.apx)](https://qxmcu.github.io/apex/#spec)**: Byte-level layout, header flags, block formats, and cryptographic envelopes.
- **[Verification Data & Shootouts](https://qxmcu.github.io/apex/#benchmarks)**: Canterbury Corpus, repeated data deduplication, and 12.3 GB Xcode toolchain benchmarks.
- **[Architectural Comparison](https://qxmcu.github.io/apex/#audit)**: Comparison matrix against WinRAR (.rar), 7-Zip (.7z), and WinZip (.zip).

---

## Products using Apex

- **[ezaudioconverter.com](https://ezaudioconverter.com)**: Online high-speed audio conversion and media processing pipeline utilizing Apex's domain preconditioning filters for asset archiving.

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for architecture guidelines, code standards, and the local test suite workflow.

---

## License

ApexCompress is free software licensed under the **Apache License, Version 2.0**. See [LICENSE](LICENSE) for details.
