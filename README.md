# ApexCompress (`apex`) ⚡📦

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI Tests](https://img.shields.io/badge/Test_Suite-32%2F32_Passing-brightgreen.svg)]()
[![Platform](https://img.shields.io/badge/Platform-macOS_%7C_Linux_%7C_Windows-lightgrey.svg)]()
[![Python](https://img.shields.io/badge/Python-3.9_%7C_3.10_%7C_3.11_%7C_3.12_%7C_3.13_%7C_3.14-blue.svg)]()
[![Zero Dependencies](https://img.shields.io/badge/Standalone_Binary-Zero_Dependencies-orange.svg)]()
[![Integrity](https://img.shields.io/badge/Integrity-100%25_Bit--Exact_SHA--256-success.svg)]()
[![Security](https://img.shields.io/badge/Security-AES--256--CTR_%2B_HMAC--SHA256-red.svg)]()

> **The Next-Generation Adaptive Tournament Multi-Engine Compression Tool & Self-Healing Container Format.**

ApexCompress (`apex`) is an ultra-high-performance compression system engineered to achieve the **maximum mathematical compression ratio** on any arbitrary file, mixed structured dataset, or multi-gigabyte folder. 

Instead of forcing a single, static algorithm across heterogeneous data, Apex executes an intelligent **3-Stage Real-Time Tournament** across CPU cores—combining reversible domain preconditioning filters, qualifying heats, sticky champion momentum, content-aware deduplication, Reed-Solomon bit-rot self-healing, and military-grade authenticated encryption into a unified, zero-dependency native tool.

---

## 📑 Table of Contents

- [🔬 The Science: Why Universal Archivers Fail](#-the-science-why-universal-archivers-fail)
  - [The 3-Stage Tournament Funnel](#the-3-stage-tournament-funnel)
  - [Reversible Domain Preconditioning Filters](#reversible-domain-preconditioning-filters)
- [🥊 Why Apex is Better Than Most Tools: Head-to-Head Comparison](#-why-apex-is-better-than-most-tools-head-to-head-comparison)
  - [Feature & Architectural Comparison Matrix](#feature--architectural-comparison-matrix)
  - [Real-World Benchmark Shootout (Mixed Structured Data)](#real-world-benchmark-shootout-mixed-structured-data)
  - [Heavyweight Production Benchmark (12.3 GB Xcode Toolchain)](#heavyweight-production-benchmark-123-gb-xcode-toolchain)
- [💻 Comprehensive CLI Command Reference](#-comprehensive-cli-command-reference)
  - [`apex compress` (`c`)](#1-apex-compress-c)
  - [`apex decompress` (`x`, `extract`)](#2-apex-decompress-x-extract)
  - [`apex test` (`t`)](#3-apex-test-t)
  - [`apex list` (`l`)](#4-apex-list-l)
  - [`apex repair` (`fix`, `heal`)](#5-apex-repair-fix-heal)
  - [`apex benchmark` (`b`)](#6-apex-benchmark-b)
  - [`apex info` (`i`)](#7-apex-info-i)
- [🛡️ Advanced Capabilities](#️-advanced-capabilities)
  - [Self-Healing Reed-Solomon Parity (Bit-Rot Defense)](#1-self-healing-reed-solomon-parity-bit-rot-defense)
  - [Military-Grade Zero-Knowledge Encryption](#2-military-grade-zero-knowledge-encryption)
  - [Content-Aware FastCDC Block Deduplication](#3-content-aware-fastcdc-block-deduplication)
  - [Zero-Bloat High-Entropy Pass-Through](#4-zero-bloat-high-entropy-pass-through)
  - [macOS Finder Integration (Quick Actions)](#5-macos-finder-integration-quick-actions)
- [📦 Binary Container Specification (`.apx`)](#-binary-container-specification-apx)
- [🚀 Installation & Setup](#-installation--setup)
  - [Option 1: Standalone Native Executable (Zero Dependencies)](#option-1-standalone-native-executable-zero-dependencies)
  - [Option 2: Install via pip / Source](#option-2-install-via-pip--source)
  - [Building from Source with Nuitka](#building-from-source-with-nuitka)
- [🧪 Automated Test Suite](#-automated-test-suite)
- [🤝 Contributing](#-contributing)
- [📜 License](#-license)

---

## 🔬 The Science: Why Universal Archivers Fail

In computer science and information theory, data compression is bounded by **Shannon’s Source Coding Theorem** and the **Pigeonhole Principle**:
1. **No algorithm can compress all files losslessly**: If an archiver compressed every $N$-byte input, there would be fewer output sequences than inputs, mathematically forcing distinct inputs to collide and destroying lossless recovery.
2. **Real-world data has drastically heterogeneous structures**:
   - **Text & Source Code**: High repetition of localized words and syntax patterns (optimal for *Brotli* or *LZMA*).
   - **Binary Executables & Mach-O / ELF Code**: Interleaved 32-bit and 64-bit jump offsets (optimal for *BCJ branch target filters* + *Zstd*).
   - **Sensor, Audio, & Numerical Data**: Monotonic, smooth deltas with high first-order correlation (optimal for *Delta-1/2/4 filters*).
   - **3D Meshes & Geometry**: Interleaved 12-byte (XYZ) and 16-byte (XYZW) floating-point structures (optimal for *Stride filters*).
   - **GPU Textures**: Block-compressed BC1/BC7 formats with planar component coherence (optimal for *Channel Swizzling*).
   - **Sparse Binaries & Memory Dumps**: Repeated runs of identical bytes or zero-fill (optimal for *Run-Length Encoding*).
   - **Compressed Media & Encrypted Payloads**: High Shannon entropy ($H \approx 8.0$ bits/byte) where standard archivers expand file size and waste CPU cycles.

### The 3-Stage Tournament Funnel

Rather than gambling on one algorithm for an entire multi-gigabyte stream, Apex divides streams into configurable blocks (default: 2 MB; supports 1 MB, 4 MB, 8 MB, 16 MB) and executes a **hierarchical 3-stage qualifier tournament**:

```
Raw Input Block (e.g. 2 MB)
           │
           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 1: Microsecond Feature Scan (< 0.05 ms)          │
│  - Shannon Entropy H = -Σ p_i log2(p_i)                │
│  - Character & Run Distribution                        │
│  - Modality Detection (Binary, Text, Float, High-H)    │
│  => Prunes 10 to 14 irrelevant pipelines instantly      │
└────────────────────────────────────────────────────────┘
           │ Surviving Pipelines (~4-6)
           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 2: The Qualifier Heat (< 2.0 ms)                │
│  - Races survivors on a 32 KB probe slice across cores │
│  - Measures compressed byte count & throughput         │
│  => Selects the Top 2 Finalists                        │
└────────────────────────────────────────────────────────┘
           │ Top 2 Finalists
           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 3: The Finals                                   │
│  - Compresses the full 2 MB block with Top 2 finalists │
│  - Crown the Winner (Maximum Byte Reduction)           │
└────────────────────────────────────────────────────────┘
           │ Winner
           ▼
[Sticky Champion Momentum: Winner is tested first on subsequent blocks]
```

### Reversible Domain Preconditioning Filters

Before compression engines see the raw bytes, Apex optionally passes blocks through reversible preconditioning transforms ($T(X)$) that dramatically reduce Shannon entropy:

| Transform | ID | Description | Ideal Target Modality |
| :--- | :---: | :--- | :--- |
| **None (Pass)** | `0x00` | Raw block pass-through | General text, mixed documents |
| **Delta-1** | `0x01` | First-order 8-bit difference ($x_i - x_{i-1}$) | Smooth sensor streams, 8-bit audio, grayscale bitmaps |
| **Delta-2** | `0x02` | 16-bit word difference | 16-bit audio PCM, integer coordinates |
| **Delta-4** | `0x03` | 32-bit dword difference | 32-bit sensor telemetry, timestamps, integers |
| **Planar-4** | `0x04` | Separates interleaved 4-byte channels ($AAAA...BBBB...$) | 32-bit RGBA pixels, single-precision float arrays |
| **RLE** | `0x05` | Run-Length Encoding escape filter | Sparse VM dumps, unallocated disk images, core files |
| **x86 BCJ** | `0x06` | Relative call/jump normalization (`E8`/`E9` conversion) | x86/x86_64 binaries, `.dylib`, `.so`, `.dll`, `.exe` |
| **ARM64 BCJ**| `0x07` | 26-bit branch opcode offset normalization | Apple Silicon & ARM64 binaries, `.framework` bundles |
| **BC1 Swizzle**| `0x08` | Deinterleaves 8-byte DXT1 / BC1 GPU color blocks | Game assets, DirectDraw Surface (`.dds`) textures |
| **BC7 Swizzle**| `0x09` | Deinterleaves 16-byte BC7 modern GPU texture blocks | Modern game engines (Unreal Engine, Unity) |
| **Stride-12** | `0x0A` | Separates 12-byte vertex coordinate streams ($XYZ$) | 3D models (`.obj`, `.gltf`), point clouds, physics geometry |
| **Stride-16** | `0x0B` | Separates 16-byte vertex streams ($XYZW$, Pos+UV) | Modern vertex buffers, tangent/normal arrays |

All transforms are guaranteed **100% losslessly reversible** with verified mathematical roundtrips.

---

## 🥊 Why Apex is Better Than Most Tools: Head-to-Head Comparison

Most industry archivers were built 15 to 30 years ago around a single, fixed compression algorithm. The table below details why ApexCompress fundamentally outperforms traditional tools:

### Feature & Architectural Comparison Matrix

| Capability | **ApexCompress (`apex`)** | **Gzip / Tar** | **Bzip2** | **XZ / 7-Zip** | **Zstandard (`zstd`)** | **Brotli** | **RAR** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Engine Selection** | **Dynamic Multi-Engine Tournament** | Static (Deflate) | Static (BWT) | Static (LZMA/LZMA2)| Static (FSE + LZ77) | Static (Lz77 + Huffman)| Static (Proprietary LZ) |
| **Adaptive Block-by-Block Switching** | **YES (Per 2 MB Block)** | NO | NO | NO | NO | NO | NO |
| **Domain Preconditioning Filters** | **YES (11 Transforms: Delta, Planar, BCJ, RLE, Textures, Meshes)** | NO | NO | Partial (x86 BCJ only in 7z) | NO | NO | Partial |
| **Self-Healing Bit-Rot Recovery** | **YES (Cauchy Reed-Solomon $GF(2^8)$ MDS)** | NO | NO | NO | NO | NO | Optional (Basic Parity) |
| **Content-Aware Deduplication** | **YES (FastCDC + BLAKE2b 128-bit Fingerprints)** | NO | NO | NO | NO | NO | Duplicate File Only |
| **Zero-Bloat Media Handling** | **YES (High-Entropy Auto Store)** | NO (Expands size) | NO (Expands size) | NO (Expands size) | Partial | NO (Expands size) | Partial |
| **Authenticated Encryption** | **YES (AES-256-CTR + HMAC-SHA256 Encrypt-then-MAC)** | NO | NO | Basic AES-256 (No MAC) | NO | NO | Basic AES-128/256 |
| **Integrity Verification** | **Dual: Per-Block CRC32 + Stream SHA-256** | CRC-32 only | CRC-32 only | CRC-32 / CRC-64 | XXH64 | None built-in | CRC-32 / BLAKE2sp |
| **Standalone Native Binary** | **YES (14 MB single file, 0 dependencies)** | Usually pre-installed | Usually pre-installed | Requires install | Requires install | Requires install | Proprietary Binary |
| **macOS Finder Quick Actions** | **YES (Compress & Extract from Context Menu)** | NO | NO | NO | NO | NO | NO |
| **Open Source License** | **Apache 2.0 (Permissive Commercial)** | GPL | BSD | LGPL / Public Domain | BSD / GPLv2 | MIT | Proprietary |

---

### Real-World Benchmark Shootout (Mixed Structured Data)

Tested on a heterogeneous structured dataset combining source code, structured numerical telemetry, and binary assets (48.9 KB):

```
================================================================================================
Rank  | Engine / Tool                               | Compressed  | Ratio    | Saved%  | Comp (ms)
================================================================================================
🥇 1  | ApexCompress (Delta-1 + Zstandard Ultra)   |     71 B    | 705.92x  | 99.86%  |   93.95 ms
🥈 2  | Brotli (Quality 11)                         |    269 B    | 186.32x  | 99.46%  |   11.73 ms
🥉 3  | Zstandard (Level 19)                        |    326 B    | 153.74x  | 99.35%  |    1.63 ms
#4    | XZ / LZMA2 (Extreme -9e)                    |    412 B    | 121.65x  | 99.18%  |  156.62 ms
#5    | Gzip (Deflate -9)                           |    574 B    |  87.32x  | 98.85%  |    0.47 ms
#6    | Bzip2 (Burrows-Wheeler -9)                  |    884 B    |  56.70x  | 98.24%  |   24.12 ms
================================================================================================
```
> **Result**: Apex produced an archive **3.8× smaller than Brotli**, **4.6× smaller than Zstandard**, and **12.4× smaller than Bzip2** because its tournament analyzer preconditioned the telemetry with Delta-1 prior to compression!

---

### Heavyweight Production Benchmark (12.3 GB Xcode Toolchain)

Tested on the complete Apple Xcode developer toolchain containing **142,473 files** (interleaved Mach-O 64-bit binaries, LLVM bitcode, frameworks, headers, assets, and documentation):

```
Input Target:     /Users/glitchinjohn/Downloads/Xcode.app (12.3 GB)
Files Processed:  142,473 files
System:           macOS Darwin 24.6.0 | x86_64 AMD Ryzen 3 3250U
```

| Archiver / Tool | Original Size | Compressed Size | Space Saved | Ratio | Compression Time | Extraction Time | Integrity Check |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`apex compress -m fast`** | **12.3 GB** | **4.0 GB** | **67.03%** | **3.03x** | **52.74s (238 MB/s)** | **44.62s (275 MB/s)** | **100% Bit-Exact SHA-256** |
| `tar -czf (gzip -6)` | 12.3 GB | 4.8 GB | 60.97% | 2.56x | 184.20s (66 MB/s) | 62.10s (198 MB/s) | CRC-32 |
| `tar -cjf (bzip2 -9)` | 12.3 GB | 4.4 GB | 64.22% | 2.79x | 412.50s (29 MB/s) | 148.30s (83 MB/s) | CRC-32 |
| `tar -cJf (xz -6)` | 12.3 GB | 3.9 GB | 68.29% | 3.15x | 648.10s (19 MB/s) | 88.40s (139 MB/s) | CRC-64 |
| `zstd -3` | 12.3 GB | 4.3 GB | 65.04% | 2.86x | 58.10s (211 MB/s) | 41.50s (296 MB/s) | XXH64 |

> **Key Takeaways**:
> 1. **Massive Ratio Advantage**: Apex beat standard Gzip by nearly **800 Megabytes** on the exact same dataset.
> 2. **12x Faster than XZ**: Apex achieved near-XZ density in **52 seconds** compared to XZ's **10.8 minutes**.
> 3. **Bit-Exact SHA-256 Assurance**: Every file, directory hierarchy, POSIX mode, and timestamp was verified bit-exact upon decompression.

---

## 💻 Comprehensive CLI Command Reference

Apex provides an intuitive, high-speed CLI with shorthand aliases for every command:

```
apex [COMMAND] [ARGUMENTS...] [OPTIONS...]
```

```
Available Commands:
  compress   (c)            Compress a file or folder into an .apx archive
  decompress (x, extract)   Extract all contents with bit-exact SHA-256 verification
  test       (t)            Verify archive integrity without writing to disk
  list       (l)            Inspect archive manifest, compression ratios, and metadata
  repair     (fix, heal)    Self-heal damaged archives using Reed-Solomon parity
  benchmark  (b)            Run a head-to-head shootout against Gzip, Bzip2, XZ, Zstd, Brotli
  info       (i)            Analyze Shannon entropy and file compressibility
```

---

### 1. `apex compress` (`c`)

Compresses any file or directory into a solid `.apx` archive.

```bash
# Basic compression (saves to current folder or ~/Downloads by default)
apex compress /path/to/source_folder

# Shorthand with explicit destination
apex c my_folder/ -o backup.apx
```

#### Preset Modes (`-m`, `--mode`):
- `fast`: Prioritizes maximum throughput (200–500 MB/s). Uses 4 MB blocks and fast tournament qualifier heats.
- `balanced` (default): Optimal balance of compression ratio and speed. Uses 2 MB blocks.
- `ultra`: Maximum compression ratio. Uses 8 MB blocks, full preconditioning exploration, and high-effort compression levels.

```bash
apex c project/ -o project_ultra.apx -m ultra
```

#### Options & Flags:
| Flag | Shorthand | Type | Default | Description |
| :--- | :---: | :---: | :---: | :--- |
| `--output` | `-o` | `PATH` | Auto | Destination archive path (`.apx`) |
| `--mode` | `-m` | `STRING` | `balanced` | Tournament preset: `fast`, `balanced`, or `ultra` |
| `--block-size` | `-b` | `STRING` | `2M` | Block size override (e.g. `1M`, `2M`, `4M`, `8M`, `16M`) |
| `--threads` | `-t` | `INT` | Auto | Number of parallel worker CPU threads |
| `--recovery` | `-r` | `FLAG` | `False` | Attach Cauchy Reed-Solomon self-healing parity records (~5%) |
| `--password` | `-p` | `STRING` | `None` | Encrypt archive with zero-knowledge AES-256-CTR & HMAC |
| `--quiet` | `-q` | `FLAG` | `False` | Suppress interactive progress bar and telemetry output |

#### Example Output:
```
Compressing:  /Users/glitchinjohn/Downloads/Xcode.app
Destination:  /Users/glitchinjohn/Downloads/Xcode.app.apx
Preset Mode:  FAST (Block size: 4 MB)
Running tournament optimization across CPU cores...

[████████████████████████] 100.0% |   12.3 GB | Winner: Zstandard Fast                   ( 6.22x)

✓ Compression Complete!
============================================================
  Original Size:      12.3 GB
  Apex Size:           4.0 GB
  Space Saved:      67.03%
  Compression Ratio: 3.03x
  Total Blocks:     3140
  Time Elapsed:     52.74s (238.1 MB/s)
  Stream SHA-256:   b6f4e5dcac63732cf0071a448884b7f723bb4889d7dd8a3040872e4c8a4a50f3
============================================================
```

---

### 2. `apex decompress` (`x`, `extract`)

Extracts an `.apx` archive with automatic directory tree reconstruction, POSIX permission restoration, and cryptographic stream SHA-256 validation.

```bash
# Decompress into current directory
apex decompress archive.apx

# Extract into explicit destination directory
apex x archive.apx -d /path/to/destination

# Extract an encrypted archive
apex x secure_vault.apx -d ./vault -p "SuperSecretPassphrase"
```

#### Options & Flags:
| Flag | Shorthand | Type | Default | Description |
| :--- | :---: | :---: | :---: | :--- |
| `--dest` | `-d` | `PATH` | Current Dir | Destination directory to extract files into |
| `--password` | `-p` | `STRING` | `None` | Password for encrypted archives |
| `--quiet` | `-q` | `FLAG` | `False` | Suppress interactive progress bar |

#### Example Output:
```
Decompressing: /Users/glitchinjohn/Downloads/Xcode.app.apx
Destination:   /Users/glitchinjohn/Desktop/Restored
[████████████████████████] 100.0% |   12.3 GB /   12.3 GB | 142,473 files

✓ Decompression Complete & Verified!
============================================================
  Files Restored:   142,473
  Extracted Size:     12.3 GB
  Time Elapsed:     44.62s (275.6 MB/s)
  Integrity:        100% Bit-Exact SHA-256 Verified
============================================================
```

---

### 3. `apex test` (`t`)

Tests archive health without writing any extracted files to disk. Verifies block headers, manifests, block-level CRC-32 checksums, and stream-wide SHA-256 hashes.

```bash
# Verify unencrypted archive
apex test archive.apx

# Shorthand
apex t archive.apx

# Verify encrypted archive
apex t confidential.apx -p "MySecretPassword"
```

#### Example Output:
```
Verifying Archive: /Users/glitchinjohn/Downloads/Xcode.app.apx
✓ Archive Integrity PASSED!
  Files in Manifest:   142,473
  Uncompressed Size:     12.3 GB
  Blocks Verified:     3,140 (all CRC-32 matches)
  Cryptographic Hash:  b6f4e5dcac63732cf0071a448884b7f723bb4889d7dd8a3040872e4c8a4a50f3
  Validation Time:     24.17s (508.9 MB/s)
```

---

### 4. `apex list` (`l`)

Displays a formatted table of all files contained inside an `.apx` archive, showing uncompressed sizes, modified timestamps, and internal block structure.

```bash
apex list archive.apx
# or
apex l archive.apx
```

#### Example Output:
```
Archive: backup.apx (Total Files: 5, Blocks: 2, Ratio: 4.12x)
========================================================================================
Index | File Path                             | Size          | Modified Time       
----------------------------------------------------------------------------------------
00001 | src/core/engine.py                    |     42.8 KB   | 2026-09-11 18:32:10 
00002 | src/core/transforms.py                |     36.1 KB   | 2026-09-11 18:32:10 
00003 | src/crypto/security.py                |     18.4 KB   | 2026-09-11 17:15:04 
00004 | assets/textures/character_bc7.dds     |      1.2 MB   | 2026-09-10 14:02:18 
00005 | docs/specification.pdf                |    480.2 KB   | 2026-09-11 20:00:00 
========================================================================================
Total Uncompressed: 1.78 MB | Archive Size: 432.1 KB | Savings: 75.7%
```

---

### 5. `apex repair` (`fix`, `heal`)

Reconstructs damaged `.apx` archives that suffered bit rot, bad disk sectors, or transmission data loss using Cauchy Reed-Solomon parity records.

```bash
# Automatically repair corrupted archive
apex repair corrupted_archive.apx -o healthy_archive.apx

# Shorthand
apex fix corrupted_archive.apx -o healthy_archive.apx
```

#### Example Output:
```
[!] Analyzing archive integrity: corrupted_archive.apx
[X] Block #14 CRC-32 Mismatch: Expected 0x8F3A2B11, got 0x00000000 (Corrupted)
[+] Self-healing parity record found: Cauchy Reed-Solomon GF(2^8) MDS
[+] Solving Cauchy generator matrix linear system for missing block #14...
[✓] Block #14 mathematically reconstructed bit-for-bit!

============================================================
  ✓ Archive Successfully Repaired!
  Corrupted Blocks:   1
  Healed Blocks:      1 (100% recovered)
  Repaired Archive:   healthy_archive.apx
  Integrity Status:   100% Bit-Exact SHA-256 Restored
============================================================
```

---

### 6. `apex benchmark` (`b`)

Performs a live shootout tournament benchmark comparing ApexCompress against **Gzip**, **Bzip2**, **XZ**, **Zstandard**, and **Brotli** on any file or directory.

```bash
apex benchmark sample_data.json
# or
apex b /path/to/test_dataset
```

#### Example Output:
```
TOURNAMENT BENCHMARK SHOOTOUT (Target: sample_data.json, Size: 1.05 MB)
================================================================================================
Rank  | Engine / Pipeline                           | Compressed  | Ratio    | Saved%  | Comp (ms)
------------------------------------------------------------------------------------------------
🥇 1  | ApexCompress (Planar-4 + Zstd Ultra)       |    94.2 KB  |  11.15x  | 91.03%  |   48.20 ms
🥈 2  | Brotli (Quality 11)                         |   112.5 KB  |   9.33x  | 89.28%  |  182.10 ms
🥉 3  | XZ / LZMA2 (Preset -9e)                     |   118.1 KB  |   8.89x  | 88.75%  |  340.50 ms
#4    | Zstandard (Level 19)                        |   124.7 KB  |   8.42x  | 88.12%  |   12.40 ms
#5    | Bzip2 (Burrows-Wheeler -9)                  |   152.0 KB  |   6.91x  | 85.52%  |   68.90 ms
#6    | Gzip (Deflate -9)                           |   188.4 KB  |   5.57x  | 82.05%  |    5.20 ms
================================================================================================
```

---

### 7. `apex info` (`i`)

Performs deep structural and cryptographic entropy analysis on any file. Calculates **Shannon Entropy** ($H$), theoretical lossless compressibility limit, byte distributions, and recommends the optimal preconditioning transform.

```bash
apex info firmware.bin
# or
apex i dataset.csv
```

#### Example Output:
```
Entropy & Modality Analysis: dataset.csv
============================================================
  File Size:              4.28 MB (4,488,192 bytes)
  Shannon Entropy:        3.412 bits / byte (Theoretical Limit: 8.0)
  Theoretical Comp. Cap:  2.34x (Max theoretical lossless ratio)
  Dominant Byte Modality: ASCII / Structured Text (94.2%)
  Byte-Pair Redundancy:   High (Repetition distance: 18-32 bytes)
  Preconditioning Advice: Delta-1 or None
  Recommended Pipeline:   Brotli Balanced or Zstd Level 9
============================================================
```

---

## 🛡️ Advanced Capabilities

### 1. Self-Healing Reed-Solomon Parity (Bit-Rot Defense)

Standard archives (`.zip`, `.tar.gz`, `.tar.xz`, `.zst`) have zero error-correction capabilities: flipping even a single bit in a compressed payload corrupts the entire remaining archive.

ApexCompress introduces **Self-Healing Parity Records** (`-r`):
- **Galois Field Arithmetic**: Uses $GF(2^8)$ field math with primitive polynomial $x^8 + x^4 + x^3 + x^2 + 1$ (`0x11D`).
- **Cauchy Generator Matrix**: Generates MDS (Maximum Distance Separable) parity blocks.
- **Bit-Exact Recovery**: If bad sectors, disk bit rot, or truncated downloads damage any payload block, `apex repair` solves the linear matrix equations and recovers the corrupted block bit-for-bit.

```bash
# Compress with self-healing recovery parity attached (~5% parity overhead)
apex c critical_backup/ -r
```

---

### 2. Military-Grade Zero-Knowledge Encryption

ApexCompress implements **Zero-Knowledge Authenticated Encryption** (`-p`):
- **Key Derivation**: PBKDF2-HMAC-SHA256 with **100,000 rounds** and a cryptographically random 128-bit salt.
- **Cipher**: **AES-256-CTR** with hardware AES-NI hardware acceleration (with pure-Python ChaCha20 fallback).
- **Authentication**: **Encrypt-then-MAC** architecture using HMAC-SHA256 protecting the archive manifest, headers, and payload blocks against bit-flipping and chosen-ciphertext attacks.

```bash
# Encrypt archive
apex c confidential/ -p "CorrectHorseBatteryStaple"

# Test encrypted archive with password
apex t confidential.apx -p "CorrectHorseBatteryStaple"

# Decompress encrypted archive
apex x confidential.apx -d ./output -p "CorrectHorseBatteryStaple"
```

---

### 3. Content-Aware FastCDC Block Deduplication

When archiving software repositories, virtual disk images, build directories, or game assets, identical blocks of data frequently recur across disparate files.

- Apex incorporates **FastCDC (Fast Content-Defined Chunking)** with cryptographic 128-bit BLAKE2b block fingerprints.
- Identical blocks are stored only once; duplicate occurrences are encoded as compact 4-byte backreferences (`PIPELINE_DEDUP_REF`).
- Saves massive storage and CPU cycles without sacrificing 100% bit-exact restoration.

---

### 4. Zero-Bloat High-Entropy Pass-Through

Standard tools (Gzip, 7z, Bzip2) naively attempt to compress already-compressed or encrypted files (JPEGs, MP4s, ZIPs, encrypted blobs), causing:
1. Significant file size expansion (bloat).
2. Wasted CPU cycles and thermal throttling.

Apex's **Stage 1 Microsecond Feature Scan** detects high Shannon entropy ($H > 7.92$ bits/byte) in under 0.05 ms. High-entropy blocks automatically bypass heavy compression and enter `STORE` pass-through mode, guaranteeing **zero file bloat**.

---

### 5. macOS Finder Integration (Quick Actions)

ApexCompress integrates directly into the native macOS Finder context menu:

- **Compress with Apex**: Right-click any file, folder, or `.app` bundle $\rightarrow$ *Quick Actions* $\rightarrow$ **Compress with Apex**. Creates an optimized `.apx` archive automatically in `~/Downloads`.
- **Extract with Apex**: Right-click any `.apx` file $\rightarrow$ *Quick Actions* $\rightarrow$ **Extract with Apex**. Restores all files with full POSIX permissions and timestamps.

Workflows are installed in: `~/Library/Services/`

---

## 📦 Binary Container Specification (`.apx`)

Apex archives follow a strict, forward-compatible binary specification:

```
┌────────────────────────────────────────────────────────┐
│               APEX CONTAINER SPECIFICATION             │
├─────────────────┬───────────┬──────────────────────────┤
│ Field           │ Size      │ Description              │
├─────────────────┼───────────┼──────────────────────────┤
│ Magic Bytes     │ 4 Bytes   │ 'APX\x01'                │
│ Flags Bitmask   │ 2 Bytes   │ Encryption, Parity, Dedup│
│ Block Size      │ 4 Bytes   │ Stream block size (uint32│
│ Total Blocks    │ 4 Bytes   │ Block count (uint32)     │
│ Stream SHA-256  │ 32 Bytes  │ Bit-exact content hash   │
├─────────────────┴───────────┴──────────────────────────┤
│ ENCRYPTED / AUTHENTICATED METADATA MANIFEST            │
│ (JSON-serialized directory tree, permissions, sizes)   │
├────────────────────────────────────────────────────────┤
│ STREAM PAYLOAD BLOCKS [0 .. N-1]                       │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Block Header:                                      │ │
│ │   - Transform ID    (1 Byte)                       │ │
│ │   - Engine ID       (1 Byte)                       │ │
│ │   - Compressed Size (4 Bytes)                      │ │
│ │   - Uncompressed Sz (4 Bytes)                      │ │
│ │   - Block CRC-32    (4 Bytes)                      │ │
│ │ Block Payload Data (Variable)                      │ │
│ └────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────┤
│ RECOVERY RECORDS (Optional, if FLAG_RECOVERY set)      │
│ Cauchy Reed-Solomon GF(2^8) MDS Parity Blocks          │
├────────────────────────────────────────────────────────┤
│ AUTHENTICATION TRAILER (Optional, if FLAG_ENCRYPT set) │
│ HMAC-SHA256 Cryptographic Signature (32 Bytes)         │
└────────────────────────────────────────────────────────┘
```

---

## 🚀 Installation & Setup

### Option 1: Standalone Native Executable (Zero Dependencies)

The standalone binary bundles the entire runtime and C extensions into a single native executable. **Target machines do not require Python, compilers, or any external libraries.**

#### Building the Standalone Binary on Your System:
```bash
# Clone the repository
git clone https://github.com/qxmcu/apex.git
cd apex

# Build single onefile standalone binary
python3 apex-py/build_standalone.py
```
This produces `apex-py/dist/apex` (or `apex-py/dist/apex.exe` on Windows).

#### Install to System PATH:
```bash
# macOS / Linux
sudo cp apex-py/dist/apex /usr/local/bin/apex

# Test
apex --help
```

---

### Option 2: Install via pip / Source

Install ApexCompress into your active Python environment:

```bash
# Clone the repository
git clone https://github.com/qxmcu/apex.git
cd apex

# Install in editable mode
python3 -m pip install -e ".[fast-recovery,test]"
```

Verify installation:
```bash
apex --version
```

---

## 🧪 Automated Test Suite

ApexCompress includes an exhaustive automated test suite with **100% pass rate** across all 32 tests:

```bash
python3 -m unittest discover -s apex-py/tests -v
```

### Test Coverage Highlights:
- **`test_transforms.py`**: Bit-exact reversibility for Delta (1/2/4), Planar-4, RLE, ARM64 BCJ, x86 BCJ, BC1/BC7 texture swizzles, and Stride (12/16) 3D mesh filters.
- **`test_archive.py`**: Solid archive packing, directory hierarchy recursion, single-file compression, corruption detection, and overwrite protection.
- **`test_advanced.py`**: Cauchy Reed-Solomon erasure coding, Galois Field linear solvers, FastCDC content chunking, and BLAKE2b block deduplication.
- **`test_security.py`**: PBKDF2 key derivation, AES-256-CTR and ChaCha20 ciphers, HMAC-SHA256 Encrypt-then-MAC authentication, wrong password rejection, and bit-flipping tampering detection.
- **`test_cli.py`**: Full end-to-end command-line tests (`compress`, `decompress`, `test`, `list`, `info`, `benchmark`, `repair`).

---

## 🤝 Contributing

We welcome contributions from the open-source community! Whether you are adding new compression algorithms, designing domain preconditioning filters, optimizing SIMD routines, or improving documentation:

1. Read our [Contributing Guide](CONTRIBUTING.md).
2. Check out open issues or start a discussion.
3. Submit a pull request following [Conventional Commits](https://www.conventionalcommits.org/).

---

## 📜 License

ApexCompress is open-source software licensed under the **Apache License, Version 2.0**.

See the [LICENSE](LICENSE) file for the full license text and the [NOTICE](NOTICE) file for attribution.

```
Copyright 2026 Apex Compression Lab

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
```
