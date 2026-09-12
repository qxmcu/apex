# Security Policy

ApexCompress (`apex`) is built with production-grade cryptographic architecture designed to guarantee data confidentiality, bit-exact authenticity, and error correction.

---

## 🔒 Cryptographic Architecture & Guarantees

ApexCompress implements standard, vetted cryptographic primitives without proprietary roll-your-own crypto:

1. **Key Derivation**:
   - **Algorithm**: PBKDF2-HMAC-SHA256
   - **Work Factor**: 100,000 iterations
   - **Salt**: 128-bit cryptographically secure random salt (`os.urandom(16)`), uniquely generated per archive.

2. **Payload Encryption**:
   - **Cipher**: AES-256 in Counter (CTR) mode with native OpenSSL / AES-NI hardware acceleration.
   - **Fallback**: Pure-Python ChaCha20 stream cipher when native OpenSSL is unavailable.
   - **Granularity**: Encrypts the archive manifest (file tree, names, permissions, timestamps) and all block payloads.

3. **Integrity & Tamper-Proof Authentication**:
   - **Architecture**: **Encrypt-then-MAC** design.
   - **MAC**: HMAC-SHA256 calculated over the header, encrypted manifest, and all encrypted payload blocks.
   - **Protection**: Cryptographically prevents bit-flipping attacks, padding oracles, and chosen-ciphertext tampering. Any modified bit triggers immediate rejection before decompression.

4. **Integrity & Error Correction**:
   - **Per-Block**: CRC-32 checksum validated for every block.
   - **End-to-End**: 256-bit cryptographic SHA-256 stream hash verified upon decompression.
   - **Bit-Rot Defense**: Cauchy Reed-Solomon $GF(2^8)$ MDS parity records to mathematically heal corrupted blocks.

---

## 🚨 Reporting a Vulnerability or Security Issue

We believe in open, transparent security and rapid public fixes. If you discover a bug, cryptographic flaw, memory safety concern, or integrity issue:

### 👉 Open a Public Issue on GitHub:
Report it directly via the GitHub Issue Tracker:
**[https://github.com/qxmcu/apex/issues](https://github.com/qxmcu/apex/issues)**

Please include:
1. **Title**: Prefixed with `[SECURITY]` (e.g. `[SECURITY] HMAC verification edge case on truncated archive`).
2. **Environment**: OS (macOS, Linux, Windows), Python version, and installation method (Standalone binary or pip).
3. **Reproduction Steps**: Exact CLI commands used (e.g. `apex c -p ...`, `apex x ...`).
4. **Test Vector / Sample Data**: A minimal non-sensitive sample file or test script that reproduces the behavior.
5. **Expected vs. Observed Behavior**: Cryptographic error message, traceback, or unexpected output.

If you have already identified a fix or improvement, pull requests are warmly welcomed!

---

## 🛡️ Supported Versions

| Version | Supported |
| :--- | :---: |
| **v1.0.x** (Latest) | :white_check_mark: Active Production Support |
