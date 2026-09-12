# Contributing to ApexCompress ⚡📦

Thank you for your interest in contributing to **ApexCompress**! ApexCompress is designed to push the theoretical boundaries of lossless data compression through adaptive multi-engine tournaments, domain-specific preconditioning, self-healing parity, and military-grade security.

Whether you are fixing a bug, adding a new compression algorithm, implementing a domain preconditioning transform, or improving documentation, we welcome your contributions.

---

## 🧭 Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free experience for everyone. Please be respectful, constructive, and collaborative in all issues, pull requests, and discussions.

---

## 🛠️ Development Setup

### 1. Prerequisites
- **Python 3.9+** (Python 3.10 – 3.14 fully supported)
- **C Compiler** (Clang, GCC, or MSVC) for Nuitka standalone builds
- **Git**

### 2. Fork & Clone
```bash
git clone https://github.com/<your-username>/apex.git
cd apex
```

### 3. Create a Virtual Environment & Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode with fast recovery and testing dependencies
python3 -m pip install -e ".[fast-recovery,test]"
```

### 4. Verify Installation & Test Suite
```bash
python3 -m unittest discover -s apex-py/tests -v
```
All **32 tests** should pass.

---

## 🏗️ Architecture Tour

ApexCompress is cleanly decoupled into modular, high-cohesion subsystems:

```
apex/
├── apex-py/
│   ├── apex/
│   │   ├── analyzer.py     # Stage 1: Microsecond Shannon entropy & structural classification
│   │   ├── transforms.py   # Stage 1.5: Reversible preconditioning filters (Delta, Planar, RLE, BCJ)
│   │   ├── engine.py       # Stages 2 & 3: Adaptive tournament qualifier heats and finals
│   │   ├── archive.py      # Solid archive container serialization, FastCDC deduplication
│   │   ├── recovery.py     # Galois Field GF(2^8) Cauchy MDS Reed-Solomon parity & auto-repair
│   │   ├── security.py     # PBKDF2-HMAC-SHA256, AES-256-CTR / ChaCha20, HMAC-SHA256 Encrypt-then-MAC
│   │   ├── benchmark.py    # Head-to-head tournament shootout engine
│   │   └── cli.py          # Unified CLI subcommands and interactive progress UI
│   ├── tests/              # 32 exhaustive unit & integration tests
│   ├── build_standalone.py # One-click cross-platform standalone compiler (via Nuitka)
│   └── pyproject.toml      # Packaging & metadata
├── apex-rs/                # High-performance Rust native engine (reference core)
├── LICENSE                 # Apache License 2.0
├── NOTICE                  # Attribution notice
├── CONTRIBUTING.md         # This document
└── README.md               # World-class documentation
```

### Key Subsystems:

1. **Entropy & Structural Analyzer (`apex.analyzer`)**:
   - Computes Shannon entropy ($H = -\sum p_i \log_2 p_i$) and byte frequencies in under 0.05 ms.
   - Detects runs, byte-pair correlations, executable jump patterns, texture strides, and uncompressible high-entropy streams (JPEG, MP4, encrypted archives).

2. **Reversible Preconditioning Transforms (`apex.transforms`)**:
   - `Delta 1, 2, 4`: Preconditions smooth sensor or numerical gradients.
   - `Planar 4`: Separates interleaved 32-bit channels (RGBA textures, 3D vertices, audio PCM).
   - `RLE`: Run-length encodes sparse dumps and sparse binaries.
   - `x86 BCJ / ARM64 BCJ`: Normalizes relative jump and call targets to absolute addresses.
   - `BC1 / BC7 Swizzle`: Optimizes GPU compressed texture blocks for stream compression.

3. **Tournament Optimization Engine (`apex.engine`)**:
   - **Stage 1 (Feature Pruning)**: Uses entropy scores to eliminate 10–14 unpromising pipelines.
   - **Stage 2 (Qualifier Heat)**: Races the surviving contenders on a 32 KB probe slice in <2 ms to choose the top 2 finalists.
   - **Stage 3 (The Finals)**: Runs only the top 2 finalists on the full block, guaranteeing maximum compression ratio with minimal CPU overhead.
   - **Sticky Champion Momentum**: Re-evaluates prior block winners first, skipping qualifier heats on continuous homogeneous streams.

4. **Self-Healing Parity Engine (`apex.recovery`)**:
   - Implements Cauchy generator matrix Reed-Solomon Maximum Distance Separable (MDS) erasure coding over Galois Field $GF(2^8)$.
   - Automatically heals corrupt blocks detected by CRC-32 and stream SHA-256 bit-for-bit.

5. **Military-Grade Security Suite (`apex.security`)**:
   - PBKDF2-HMAC-SHA256 key derivation with 100,000 iterations and 128-bit cryptographic salt.
   - AES-256-CTR encryption with hardware AES-NI acceleration via OpenSSL (and pure-Python ChaCha20 fallback).
   - Encrypt-then-MAC using HMAC-SHA256 protecting the archive manifest, headers, and payload blocks against bit-flipping attacks.

---

## 🧩 How to Add a New Compression Engine

1. Open `apex-py/apex/engine.py`.
2. Define the engine ID constant (e.g. `ENGINE_NEW = 0x06`).
3. Add the compressor and decompressor functions with clean error handling.
4. Register the pipeline in `TOURNAMENT_PIPELINES` with its preset modes (`fast`, `balanced`, `ultra`).
5. Add roundtrip test cases to `tests/test_advanced.py`.

---

## 🔬 How to Add a New Preconditioning Transform

1. Open `apex-py/apex/transforms.py`.
2. Define the transform ID constant (e.g. `TRANSFORM_MY_FILTER = 0x09`).
3. Implement `forward(data: bytes) -> bytes` and `backward(data: bytes) -> bytes`.
4. Guarantee **100% bit-exact reversibility**:
   ```python
   assert backward(forward(raw_data)) == raw_data
   ```
5. Register the transform in `APPLY_TRANSFORM` and `REVERSE_TRANSFORM` dispatch tables.
6. Add unit tests in `tests/test_transforms.py`.

---

## 🧪 Testing Guidelines

Before submitting any PR, ensure all tests pass:

```bash
# Run all unit and integration tests
python3 -m unittest discover -s apex-py/tests -v

# Run standalone compilation test (optional)
python3 apex-py/build_standalone.py
```

### Testing Rules:
- **Bit-Exact Integrity**: Any change affecting compression or decompression MUST be 100% bit-exact verifiable.
- **Edge Cases**: Always test empty files, 1-byte files, incompressible random data (high entropy), uniform data (all zeroes), and files exceeding block boundaries.
- **Backward Compatibility**: Archives created with older versions of ApexCompress must always decompress correctly in newer versions.

---

## 📦 Building Standalone Zero-Dependency Binaries

ApexCompress includes a built-in builder script using Nuitka:

```bash
cd apex-py
python3 build_standalone.py
```

This compiles a single onefile executable into `dist/apex` (or `dist/apex.exe` on Windows) bundling all required C-extensions and runtimes with zero external dependencies.

---

## 🚀 Pull Request Workflow

1. **Create a branch**:
   ```bash
   git checkout -b feature/my-amazing-feature
   ```
2. **Commit changes**:
   Follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat: add LZ4 ultra-fast mode`
   - `fix: correct Galois field division edge case`
   - `perf: vectorize Delta-1 transform with SIMD`
   - `docs: update benchmark shootout tables`
   - `test: add BC7 texture transform edge cases`
3. **Push to your fork**:
   ```bash
   git push origin feature/my-amazing-feature
   ```
4. **Open a Pull Request**:
   - Provide a clear summary of the changes.
   - Reference any relevant issues (e.g., `Fixes #12`).
   - Include before/after benchmark numbers or test output if applicable.

---

## 📜 License

By contributing to ApexCompress, you agree that your contributions will be licensed under the [Apache License, Version 2.0](./LICENSE).
