# Contributing to ApexCompress ⚡📦

Thank you for your interest in contributing to **ApexCompress**! ApexCompress is an open-source project designed to push the boundaries of data compression science through adaptive multi-engine tournaments, domain-specific preconditioning, self-healing parity, and authenticated encryption.

Whether you are fixing a bug, adding a new compression engine, designing a specialized domain preconditioning filter, optimizing SIMD routines, or improving documentation, we welcome your contributions!

---

## 📑 Table of Contents

- [Code of Conduct](#-code-of-conduct)
- [How Can I Contribute?](#-how-can-i-contribute)
- [Setting Up Your Local Development Environment](#-setting-up-your-local-development-environment)
- [Codebase Architecture & Subsystems](#-codebase-architecture--subsystems)
- [Step-by-Step Contribution Guides](#-step-by-step-contribution-guides)
  - [Guide 1: Adding a New Compression Engine](#guide-1-adding-a-new-compression-engine)
  - [Guide 2: Implementing a New Preconditioning Transform](#guide-2-implementing-a-new-preconditioning-transform)
  - [Guide 3: Enhancing the Self-Healing Parity Engine](#guide-3-enhancing-the-self-healing-parity-engine)
- [Coding Standards & Best Practices](#-coding-standards--best-practices)
- [Testing & Quality Assurance](#-testing--quality-assurance)
- [Pull Request & Git Commit Guidelines](#-pull-request--git-commit-guidelines)
- [Building & Testing Standalone Binaries](#-building--testing-standalone-binaries)
- [Community & Getting Help](#-community--getting-help)

---

## 🧭 Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free community for everyone.
- **Be respectful and constructive**: Treat all contributors with empathy and patience.
- **Focus on technical merits**: Provide reasoned, evidence-based feedback on code and benchmarks.
- **Zero tolerance for harassment**: Harassment, derogatory comments, or abusive behavior will not be tolerated.

---

## 💡 How Can I Contribute?

There are many ways to contribute to ApexCompress:
1. **Reporting Bugs**: Found a file that compresses poorly, causes an error, or fails verification? Open an issue using our [Bug Report Template](.github/ISSUE_TEMPLATE/bug_report.md).
2. **Feature Requests**: Have ideas for new algorithms, GPU acceleration, or container features? Share them in our [Feature Request Template](.github/ISSUE_TEMPLATE/feature_request.md).
3. **Adding Preconditioning Transforms**: Implement filters for specialized data types (e.g. 64-bit floating point, audio FLAC-style LPC, geometric point clouds, DNA FASTA sequences).
4. **Benchmarking**: Benchmark Apex on novel datasets (genomics, deep learning checkpoints, video games) and submit your findings.
5. **Documentation & Translations**: Improve README explanations, tutorials, and CLI help messages.

---

## 🛠️ Setting Up Your Local Development Environment

### 1. Prerequisites
- **Python 3.9+** (Python 3.10 – 3.14 fully supported)
- **Git**
- **C Compiler** (Clang, GCC, or MSVC) — Required if building standalone binaries via Nuitka.

### 2. Fork & Clone the Repository
```bash
# Fork the repository on GitHub, then clone your fork:
git clone https://github.com/qxmcu/apex.git
cd apex
```

### 3. Create a Virtual Environment
```bash
python3 -m venv .venv

# Activate on macOS / Linux:
source .venv/bin/activate

# Activate on Windows:
.venv\Scripts\activate
```

### 4. Install in Editable Development Mode
Install Apex in editable mode with all optional testing and fast-recovery dependencies:
```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[fast-recovery,test]"
```

### 5. Run the Test Suite to Verify
```bash
python3 -m unittest discover -s apex-py/tests -v
```
All **32 tests** must pass before making any code modifications.

---

## 🏗️ Codebase Architecture & Subsystems

ApexCompress is structured as a cleanly decoupled pipeline where each module has a single, well-defined responsibility:

```
apex/
├── pyproject.toml              # Root build & dependency configuration
├── LICENSE                     # GNU General Public License v3.0
├── NOTICE                      # Attribution and legal notices
├── README.md                   # Primary project documentation
├── CONTRIBUTING.md             # This document
├── .github/
│   ├── workflows/ci.yml        # Multi-OS GitHub Actions CI matrix
│   ├── ISSUE_TEMPLATE/         # Bug & Feature templates
│   └── pull_request_template.md# PR review checklist
├── apex-py/                    # Core Python Reference Implementation
│   ├── apex/
│   │   ├── analyzer.py         # Stage 1: Microsecond Shannon entropy & structural classification
│   │   ├── transforms.py       # Stage 1.5: 11 Reversible domain preconditioning filters
│   │   ├── engine.py           # Stages 2 & 3: Adaptive tournament qualifier heats & finals
│   │   ├── archive.py          # Solid container serializer, FastCDC chunker & deduplication
│   │   ├── recovery.py         # Cauchy Reed-Solomon GF(2^8) self-healing parity & linear solver
│   │   ├── security.py         # PBKDF2, AES-256-CTR / ChaCha20, HMAC-SHA256 Encrypt-then-MAC
│   │   ├── benchmark.py        # Head-to-head shootout tournament benchmark runner
│   │   └── cli.py              # Subcommand routing, argument parsing & visual UI
│   ├── tests/
│   │   ├── test_transforms.py  # Bit-exact reversibility tests for all 11 filters
│   │   ├── test_archive.py     # Container packing, permissions, and directory structure tests
│   │   ├── test_advanced.py    # Deduplication, Reed-Solomon parity healing, and crypto tests
│   │   └── test_cli.py         # End-to-end command line interface tests
│   ├── build_standalone.py     # Automated standalone native executable compiler
│   └── apex_launcher.py       # Standalone binary entrypoint
└── apex-rs/                    # Preserved Rust native reference core (gitignored)
```

---

## 🛠️ Step-by-Step Contribution Guides

### Guide 1: Adding a New Compression Engine

To integrate a new compression engine (e.g. LZ4, Snappy, or a custom entropy coder):

1. **Define the Engine ID** in `apex-py/apex/engine.py`:
   ```python
   ENGINE_NEW = 0x06
   ```
2. **Implement Compressor & Decompressor**:
   ```python
   def compress_new(data: bytes, level: int = 1) -> bytes:
       ...

   def decompress_new(data: bytes) -> bytes:
       ...
   ```
3. **Register in Pipeline Tables**:
   Add your new engine configuration to `TOURNAMENT_PIPELINES` with appropriate preset levels (`fast`, `balanced`, `ultra`).
4. **Update Dispatch Tables**:
   Update `COMPRESS_DISPATCH` and `DECOMPRESS_DISPATCH`.
5. **Add Tests**:
   Add test cases to `apex-py/tests/test_advanced.py` ensuring roundtrip bit-exactness.

---

### Guide 2: Implementing a New Preconditioning Transform

Preconditioning filters reduce entropy by rearranging or differentiating bytes prior to compression.

1. **Define the Transform ID** in `apex-py/apex/transforms.py`:
   ```python
   TRANSFORM_MY_FILTER = 0x0C
   ```
2. **Implement Forward and Backward Functions**:
   ```python
   def my_filter_forward(data: bytes) -> bytes:
       """Applies domain preconditioning."""
       ...

   def my_filter_backward(data: bytes) -> bytes:
       """Exact inverse of my_filter_forward."""
       ...
   ```
3. **Mandatory Invariant — 100% Bit-Exact Invertibility**:
   ```python
   assert my_filter_backward(my_filter_forward(raw_data)) == raw_data
   ```
4. **Register in Dispatchers**:
   Add to `APPLY_TRANSFORM` and `REVERSE_TRANSFORM`.
5. **Add Unit Tests**:
   Add test methods to `apex-py/tests/test_transforms.py` testing random bytes, uniform bytes, empty buffers, and various block sizes.

---

### Guide 3: Enhancing the Self-Healing Parity Engine

The recovery engine in `apex-py/apex/recovery.py` uses Galois Field $GF(2^8)$ arithmetic with Cauchy generator matrices:
- Any proposed performance optimization (e.g. NumPy vectorization, SIMD XOR tables) must maintain exact equivalence with the mathematical Galois field definition.
- Always verify with `test_reed_solomon_parity_and_healing` in `apex-py/tests/test_advanced.py`.

---

## 📐 Coding Standards & Best Practices

1. **PEP 8 Compliance**: Code must adhere to PEP 8 standards. Use 4 spaces per indentation level.
2. **Type Annotations**: Use Python type hints for all function signatures:
   ```python
   def compress_block(data: bytes, mode: str = "balanced") -> Tuple[bytes, int, int]:
   ```
3. **Docstrings**: Provide concise, clear docstrings describing the algorithmic complexity, input parameters, and return values.
4. **Zero Silent Failures**: Never use bare `except:` clauses. Always raise descriptive exceptions or handle known errors gracefully.
5. **Performance Discipline**: Inner loops in preconditioning and analyzer modules process megabytes of data per second. Avoid unnecessary memory allocations or redundant copies.

---

## 🧪 Testing & Quality Assurance

Before submitting a Pull Request, run the full test suite locally:

```bash
# Run all unit and integration tests
python3 -m unittest discover -s apex-py/tests -v
```

### Running Specific Test Modules:
```bash
# Test transforms only:
python3 -m unittest apex-py/tests/test_transforms.py -v

# Test advanced features (Deduplication, Reed-Solomon, Crypto):
python3 -m unittest apex-py/tests/test_advanced.py -v

# Test CLI end-to-end:
python3 -m unittest apex-py/tests/test_cli.py -v
```

### Mandatory Testing Checklist:
- [ ] All 32 existing tests pass without warnings or failures.
- [ ] Any new feature has corresponding unit tests added.
- [ ] Edge cases tested: empty files, 1-byte files, incompressible random data ($H \approx 8.0$), repetitive data ($H \approx 0.0$), and boundary-straddling blocks.
- [ ] Decompressed output is verified to have an identical SHA-256 hash to original source data.

---

## 📦 Building & Testing Standalone Binaries

ApexCompress includes an automated build script using Nuitka to generate self-contained, zero-dependency native executables:

```bash
cd apex-py
python3 build_standalone.py
```

- **Output Location**: `apex-py/dist/apex` (or `apex.exe` on Windows).
- **Verification**:
  ```bash
  # Check dynamically linked libraries (should only link to OS system libs)
  otool -L apex-py/dist/apex  # On macOS
  ldd apex-py/dist/apex       # On Linux

  # Test execution
  ./apex-py/dist/apex --help
  ```

---

## 🚀 Pull Request & Git Commit Guidelines

### 1. Branch Naming
Create a descriptive branch for your work:
```bash
git checkout -b feat/add-fast-lz4-engine
git checkout -b fix/galois-division-by-zero
git checkout -b perf/vectorized-delta-filter
git checkout -b docs/clarify-benchmark-matrix
```

### 2. Commit Message Convention
We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

| Prefix | Description | Example |
| :--- | :--- | :--- |
| `feat:` | A new feature or capability | `feat: add ARM64 SIMD acceleration for Planar-4` |
| `fix:` | A bug fix | `fix: handle empty directory recursion in manifest` |
| `perf:` | A code change that improves performance | `perf: optimize qualifier heat probe from 64KB to 32KB` |
| `test:` | Adding or improving tests | `test: add edge-case tests for 1-byte archives` |
| `docs:` | Documentation updates | `docs: add detailed CLI usage examples to README` |
| `refactor:` | Code restructuring without behavior changes | `refactor: extract FastCDC rolling hash helper` |

### 3. Submitting the PR
1. Push your branch to your GitHub fork:
   ```bash
   git push origin feat/my-new-feature
   ```
2. Open a Pull Request against `main` on the primary repository.
3. Fill out the [Pull Request Template](.github/pull_request_template.md).
4. Verify that all automated GitHub Actions CI checks pass.

---

## 📜 License & Copyright

By contributing to ApexCompress, you agree that your contributions will be licensed under the **[GNU General Public License v3.0](LICENSE)**.
