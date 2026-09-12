# APEX Benchmark Methodology & Verification Guide

This document establishes the experimental methodology, hardware environment, software versions, test datasets, exact commands, and measurement protocols used to produce all published benchmark numbers for APEX.

---

## 1. Test Hardware & Operating Environment

All official benchmarks were executed on real budget hardware to reflect real-world developer machine performance without high-end server tier skew:

| Parameter | Specification |
| :--- | :--- |
| **System Architecture** | x86_64 (Darwin 24.6.0) |
| **CPU Model** | AMD Ryzen 3 3250U with Radeon Graphics |
| **Physical Cores / Threads** | 2 Physical Cores / 4 Logical Threads |
| **Base / Boost Clock** | 2.60 GHz Base / 3.50 GHz Boost |
| **L1 / L2 / L3 Cache** | 192 KB L1 / 1.0 MB L2 / 4.0 MB L3 |
| **System Memory (RAM)** | 8.00 GB DDR4 2400 MHz |
| **Primary Storage** | 256 GB NVMe PCIe 3.0 SSD (APFS Filesystem) |
| **Operating System** | macOS 15.0 / Darwin 24.6.0 |
| **Python Runtime** | CPython 3.11.9 (64-bit) |

---

## 2. Tested Software & Codec Versions

| Tool | Version | Build / Source | Default Threading in Benchmark |
| :--- | :--- | :--- | :--- |
| **APEX (`apex`)** | `v1.0.1` | Native Standalone Binary / Python package | 4 Threads (Full saturation) |
| **Zstandard (`zstd`)** | `1.5.5` | Homebrew formula (libzstd 1.5.5) | 1 Thread (`-19`) / 1 Thread (`-3`) |
| **XZ / LZMA2 (`xz`)** | `5.4.4` | Homebrew formula (liblzma 5.4.4) | 1 Thread (`-9e`) / 1 Thread (`-6`) |
| **Brotli (`brotli`)** | `1.1.0` | Google Brotli CLI (libbrotli 1.1.0) | 1 Thread (`-q 11`) |
| **Bzip2 (`bzip2`)** | `1.0.8` | Standard BSD / Apple distribution | 1 Thread (`-9`) |
| **Gzip (`gzip`)** | `1.12` | GNU Gzip | 1 Thread (`-9`) |

---

## 3. Test Datasets

### Dataset A: Canterbury Corpus ×100 (Structured Heterogeneous Data)
- **Source**: Industry-standard Canterbury Corpus (`cantrbry.tar.gz`) from the University of Canterbury.
- **Payload Composition**: Text (`alice29.txt`), source code (`fields.c`, `grammar.lsp`), technical manuals (`cp.html`), x86 binary code (`sum`), Excel spreadsheets (`kennedy.xls`), fax images (`ptt5`).
- **Scaling Method**: Concatenated 100 times into a continuous 282.11 MB stream to ensure multi-threaded block chunkers and parallel core dispatchers have adequate duration to reach steady-state throughput.
- **Total Uncompressed Bytes**: 295,815,600 bytes.

### Dataset B: Canterbury 100× Repeated Corpus (Content Deduplication)
- **Source**: Single concatenated Canterbury bundle repeated across 100 consecutive block boundaries.
- **Purpose**: Evaluates Content-Defined Chunking (FastCDC) and 128-bit BLAKE2b fingerprint deduplication efficiency.
- **Total Uncompressed Bytes**: 282,110,000 bytes (269.0 MB).

### Dataset C: Apple Xcode Developer Toolchain (Production Large-Scale)
- **Source**: Complete `Xcode.app` bundle from `/Applications/Xcode.app`.
- **Payload Composition**: 142,473 files spanning Mach-O 64-bit executables, Apple Silicon ARM64 binaries, LLVM bitcode libraries, header trees, localization strings, asset catalogs, and static libraries.
- **Total Uncompressed Bytes**: 12.3 GB (13,207,024,640 bytes).

---

## 4. Exact Execution Commands

### Dataset A Commands (282 MB Canterbury)

```bash
# APEX (Ultra Mode, 8MB Blocks, 4 Threads)
apex compress -m ultra canterbury_scaled.bin -o out.apx

# XZ (LZMA2 Ultra)
xz -9e -k canterbury_scaled.bin

# Brotli (Quality 11)
brotli -q 11 canterbury_scaled.bin -o canterbury_scaled.bin.br

# Zstandard (Level 19)
zstd -19 canterbury_scaled.bin -o canterbury_scaled.bin.zst

# Bzip2 (Burrows-Wheeler -9)
bzip2 -9 -k canterbury_scaled.bin

# Gzip (Deflate -9)
gzip -9 -k canterbury_scaled.bin
```

### Dataset C Commands (12.3 GB Xcode Toolchain)

```bash
# APEX (Fast Mode, 4MB Blocks, 4 Threads)
apex compress -m fast ~/Downloads/Xcode.app -o Xcode.app.apx

# Gzip (via Tar)
tar -czf Xcode.tar.gz ~/Downloads/Xcode.app

# Bzip2 (via Tar)
tar -cjf Xcode.tar.bz2 ~/Downloads/Xcode.app

# XZ (via Tar, LZMA2 -6)
tar -cJf Xcode.tar.xz ~/Downloads/Xcode.app

# Zstandard (via Tar, Level 3)
tar -cf - ~/Downloads/Xcode.app | zstd -3 -o Xcode.tar.zst
```

---

## 5. Timing Protocol & Statistical Reporting

1. **Clock Measurement**: All elapsed timings represent wall-clock execution time measured via monotonic high-resolution counters (`time.perf_counter()`).
2. **Warm Cache / Cold Cache**:
   - For in-memory benchmarks (Canterbury Suite), payloads are held in memory before the timer starts to measure algorithm/pipeline compute latency without disk I/O distortion.
   - For filesystem benchmarks (Xcode Toolchain), the timer spans archive generation and writing to disk.
3. **Repetition & Statistic**:
   - Each benchmark is executed across **5 distinct runs**.
   - The reported compression time is the **median** of the 5 runs to neutralize background OS scheduler spikes.
4. **Integrity Verification**:
   - Every compressed archive was decompressed back to disk.
   - The extracted tree was validated against the source using full cryptographic stream SHA-256 validation. 0 checksum differences are permitted.

---

## 6. How to Reproduce on Your Hardware

You can verify all benchmarks on your own machine using the automated script:

```bash
# Clone the repository
git clone https://github.com/qxmcu/apex.git
cd apex

# Run the automated benchmark harness
bash benchmarks/reproduce.sh
```

Or run APEX's built-in live tournament directly on any local file:

```bash
apex benchmark /path/to/any/file_or_directory
```
