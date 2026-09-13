# ApexCompress v1.1.0 — Ecosystem & Tooling Release ⚡📦

ApexCompress v1.1.0 expands the container format into a developer-first ecosystem with zero-copy selective extraction, archive diffing, native shell autocompletions, Windows Explorer context menus, and a high-performance Python Library SDK.

### 🌟 What's New in v1.1.0

#### 1. Selective Extraction (`apex x archive.apx -i "*.json"`)
- Extract specific files or glob patterns without extracting or decompressing the entire archive to disk.
- **Zero-Overhead Memoryview Skipping**: Solid `.apx` blocks advance slice pointers in memory without heap allocations or disk syscalls for unselected files.
- Full stream SHA-256 and block-level CRC-32 checksums remain 100% cryptographically verified throughout extraction.

```bash
# Extract only matching files
apex x archive.apx -i "*.json" -i "*.png"

# Extract a specific file path
apex x archive.apx path/to/file.txt -d ./out
```

#### 2. Archive Diff Tool (`apex diff`)
- Compare two `.apx` archives in milliseconds by reading embedded container manifests without decompressing block payloads.
- Reports added, removed, modified, and unchanged files alongside net uncompressed size deltas.
- Supports `--json` for automated CI/CD pipeline integration and build artifact tracking.

```bash
apex diff release_v1.apx release_v2.apx
apex diff release_v1.apx release_v2.apx --json
```

#### 3. Shell Autocompletions (`apex completions`)
- Native shell completion generator for **Bash**, **Zsh**, and **Fish**.
- Autocompletes all subcommands, shorthand aliases (`c`, `x`, `t`, `l`, `d`, `b`, `i`), preset modes, and flags.

```bash
source <(apex completions bash)
source <(apex completions zsh)
apex completions fish > ~/.config/fish/completions/apex.fish
```

#### 4. High-Level Python Library SDK (`import apex`)
- Direct Python API for embedding adaptive tournament compression in data processing pipelines and microservices:

```python
import apex

# Compress files and directories
apex.compress("dataset_folder", "dataset.apx", mode="balanced", recovery=True)

# Selective extraction
apex.extract("dataset.apx", destination="./output", include=["*.json"])

# Integrity verification
apex.test("dataset.apx")

# Fast metadata diff
diff = apex.diff("old.apx", "new.apx")

# In-memory buffer tournament compression (zero disk I/O)
compressed = apex.compress_bytes(b"Raw heterogeneous payload...", mode="fast")
restored = apex.decompress_bytes(compressed)
```

#### 5. Windows Explorer Context Menu Integration
- [`scripts/windows_context_menu.reg`](scripts/windows_context_menu.reg) adds native Explorer right-click options:
  - Right-click files/folders: "Compress with Apex" (Balanced, Ultra, Fast, Self-Healing Parity).
  - Right-click `.apx` files: "Extract with Apex", "Test Archive Integrity", "Repair Damaged Archive".

#### 6. Expanded Verification & Quality Assurance
- Test suite expanded to **40 comprehensive automated tests** covering all transforms, FastCDC deduplication, Reed-Solomon Cauchy self-healing, AES-256-CTR encryption, selective extraction, archive diffing, and shell completions.
- 100% bit-exact SHA-256 determinism verified across macOS, Linux, and Windows.

---

### 📦 Pre-Compiled Standalone Binaries (v1.1.0)
No Python runtime or external dependencies required:
- **macOS (Darwin x86_64 / Apple Silicon)**: `apex-v1.1.0-darwin-x86_64.tar.gz`
- **Linux (GLIBC 2.28+ x86_64)**: `apex-v1.1.0-linux-x86_64.tar.gz`
- **Windows (10 / 11 x86_64)**: `apex-v1.1.0-windows-x86_64.zip`
