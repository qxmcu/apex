## ApexCompress v1.2.0: Atomic Resilience, FastCDC & Security Hardening

ApexCompress v1.2.0 delivers major architectural improvements across data safety, chunking stability, deduplication verification, portable security, and tooling integration.

### 🛡️ Atomic Operations & Zero-Corruption Guarantees
- **Atomic Archive Writing**: Container writes now stream to a sibling temporary file (`.${dest}.tmp.${pid}.${uuid}.apx`) and perform an OS-level `fsync` before being atomically promoted (`os.replace`). If compression is interrupted, existing files are never replaced with partial archives.
- **Staged Extraction & Rollback**: Extraction stages uncompressed streams in a sibling staging folder (`.${dest}.staging.${pid}.${uuid}`). Promotion to destination occurs only after 100% verification of every block CRC-32 and stream SHA-256. Corrupt archives are rejected cleanly without leaving partial or corrupted files in the target directory.
- **Atomic Self-Healing Repair**: Repaired archives are created via sibling temporary files, guaranteeing no half-repaired files exist on disk.

### ⚡ True FastCDC & Cryptographic Deduplication
- **Gear-Hash FastCDC Chunking**: Implemented true Fast Content-Defined Chunking with normalized dual-mask Gear hashing (`--cdc`) based on the USENIX ATC '16 specification, providing stable chunk boundaries across byte shifts, patch updates, and DLC delta distributions.
- **BLAKE2b Collision-Proof Dedup**: Deduplication candidates are verified bit-for-bit against 256-bit cryptographic BLAKE2b hashes before emitting `PIPELINE_DEDUP_REF` (0xFE), permanently eliminating deduplication collision risk.

### 🔒 Portable Authenticated Encryption
- **Pure Python In-Process Authenticated Encryption**: Eliminates runtime dependencies on external OpenSSL CLI binaries by introducing portable ChaCha20-HMAC-SHA256 (`0x01`) and AES-256-CTR-HMAC (`0x02`) with PBKDF2 (100,000 rounds) and tamper-proof HMAC verification before decryption.

### 🚀 CLI & Tooling Enhancements
- **Skip Pipeline (--exclude / -e)**: Exclude subdirectories (`.git`, `node_modules`, build artifacts) and custom globs during compression directly from the CLI or via the Python SDK.
- **Full Dataset Benchmarking (--full)**: `apex benchmark` now supports benchmarking entire files without the 16 MB sample limit, accurately reporting sampled vs total file sizes.
- **HOL Guard Command Extension**: Integrated `codex_plugin_scanner.guard.runtime.command_apex_extensions`, recognizing `apex` and `apexcompress` commands and enforcing safe `REVIEW` classification on mutating operations and `ALLOW` on read-only inspection.
- **Production Specification Synchronized**: `docs/FORMAT.md` updated to v1.2.0 production specification.

---
**Checksums & Standalone Assets**:
Standalone binaries for macOS, Linux, and Windows are attached below with corresponding SHA-256 checksums.
