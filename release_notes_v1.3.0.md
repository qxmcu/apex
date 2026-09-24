## ApexCompress v1.3.0: Index-Accelerated Extraction, Tar Pipes, Foreign Formats & FUSE Mount

ApexCompress v1.3.0 brings indexed random access, full tar-compatible syntax and Unix pipes, foreign archive transparency (ZIP and TAR.GZ), incremental standalone archiving, and a read-only FUSE virtual filesystem interface.

### Indexed Member Storage & Instant Selective Extraction
- **Granular Block Indexing**: Every member file entry now persists exact container mapping metadata (`block_id`, `offset`, `length`, `solid_offset`).
- **Selective Block Decoding**: When extracting individual files or glob patterns (`apex x archive.apx path/to/file -d out`), Apex selectively decodes only the blocks containing the requested data. Unreferenced blocks are skipped entirely, turning extraction of a small file from a multi-gigabyte archive into a near-instantaneous operation.
- **Fast Block Index Scanner**: Sub-millisecond container block header inspection (`<0.5ms` for 1,000 blocks) without parsing compressed block payloads.

### Tar Compatibility & Unix Pipeline Streaming
- **Clustered Tar Flags**: Full support for standard tar invocation styles:
  - `apex -cvf out.apx src/` (create archive with verbose output)
  - `apex -xvf out.apx` (extract archive)
  - `apex -tvf out.apx` (list archive contents)
  - `apex -c0f out.apx` (stream null-delimited file lists from `find -print0`)
- **Pipes & Non-Seekable Streams**: Full standard stream interoperability without seeking on stdout:
  - `apex -cf - src/ > out.apx`
  - `cat out.apx | apex -xf -`
  - `apex -cf - src/ | ssh remote "apex -xf -"`

### Transparent Foreign Archive Inspection & Extraction
- **Magic-Based Format Detection**: Apex automatically identifies ZIP and TAR.GZ / TAR archives by magic signature rather than file extension.
- **Unified Interface**: List (`apex list archive.zip`) and extract (`apex extract archive.tar.gz`) foreign archives seamlessly using familiar Apex commands.
- **Safety Boundary**: Self-healing Reed-Solomon repair and archive creation remain strictly scoped to native `.apx` containers.

### Standalone Incremental Compression
- **Zero-Dependency Incremental Archives**: `apex compress src -o day2.apx --base day1.apx` indexes base archive chunks by 256-bit BLAKE2b hash and copies matching compressed chunks directly into the new container without recompression.
- **Standalone Portability**: The resulting archive (`day2.apx`) has zero runtime dependency on `day1.apx` and extracts completely standalone on any machine.
- **Reuse Tracking**: `apex info day2.apx` and `apex list --json` report the base archive and reused chunk count.

### Read-Only FUSE Virtual Filesystem
- **Virtual Mount**: `apex mount archive.apx /mnt/point` exposes the archive transparently as a read-only virtual filesystem.
- **LRU Block Cache**: Configurable 64 MB LRU block cache ensures high-performance random read access and minimal memory overhead.

### Security Hardening: Cryptographic Key Independence (RFC 5869 HKDF-Expand)
- **Elimination of Key Dependency**: Fixed high-severity structural flaw where a single 64-byte PBKDF2 output was directly split into encryption ($K_{enc}$) and authentication ($K_{mac}$) keys.
- **Two-Step KDF Expansion**: Apex now derives a 256-bit master key via PBKDF2-HMAC-SHA256 (100,000 iterations) and applies RFC 5869 HKDF-Expand with domain-separated info strings (`apex-encryption-key-v1` and `apex-authentication-key-v1`), guaranteeing complete cryptographic independence and permanently eliminating key-reuse, structural leakage, and dependency attack vectors between stream ciphers (ChaCha20 / AES-CTR) and HMAC-SHA256.

### Packaging & Ecosystem Integrations
- **Scoop Manifest**: Automated Windows package installation via Scoop (`packaging/scoop/apex.json`).
- **Winget Manifest**: Windows Package Manager manifest (`packaging/winget/apex.yaml`).
- **GitHub Action**: Reusable composite action (`.github/actions/apex-pack`) for CI/CD artifact compression.
- **File(1) Magic Definitions**: MIME type and container signature definitions (`packaging/magic`).

---
### Pre-Compiled Standalone Binaries (v1.3.0)
- **macOS (Darwin x86_64 / Apple Silicon)**: `apex-v1.3.0-darwin-x86_64.tar.gz`
- **Linux (GLIBC 2.28+ x86_64)**: `apex-v1.3.0-linux-x86_64.tar.gz`
- **Windows (10 / 11 x86_64)**: `apex-v1.3.0-windows-x86_64.zip`
