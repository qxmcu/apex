# Security Policy & Threat Model

**Status: Experimental / Unaudited**

ApexCompress (`apex`) is built with standard cryptographic architecture designed to guarantee data confidentiality, bit-exact authenticity, and error correction. However, the codebase has **not** undergone a formal third-party security audit. 

**Do not use ApexCompress as the sole protection for high-value classified data, state secrets, or critical PII/PHI at this time.**

---

## 🔒 Cryptographic Architecture & Guarantees

ApexCompress implements standard, vetted cryptographic primitives without proprietary roll-your-own crypto:

1. **Key Derivation**:
   - **Algorithm**: PBKDF2-HMAC-SHA256
   - **Work Factor**: 100,000 iterations (chosen for hashlib compatibility in zero-dependency environments)
   - **Salt**: 128-bit cryptographically secure random salt (`os.urandom(16)`), uniquely generated per archive.

2. **Payload Encryption**:
   - **Cipher**: AES-256 in Counter (CTR) mode with native OpenSSL / AES-NI hardware acceleration.
   - **Fallback**: Pure-Python ChaCha20 stream cipher when native OpenSSL is unavailable.
   - **Granularity**: Encrypts the archive manifest (file tree, names, permissions, timestamps) and all block payloads.

3. **Integrity & Tamper-Proof Authentication**:
   - **Architecture**: **Encrypt-then-MAC** design.
   - **MAC**: HMAC-SHA256 calculated over the header, encrypted manifest, and all encrypted payload blocks.
   - **Protection**: Designed to prevent bit-flipping attacks, padding oracles, and chosen-ciphertext tampering. Any modified bit triggers immediate rejection before decompression.

4. **Integrity & Error Correction**:
   - **Per-Block**: CRC-32 checksum validated for every block.
   - **End-to-End**: 256-bit cryptographic SHA-256 stream hash verified upon decompression.
   - **Bit-Rot Defense**: Cauchy Reed-Solomon $GF(2^8)$ MDS parity records to mathematically heal corrupted blocks.

---

## ⚠️ What is NOT Protected (Threat Model Exclusions)

When an archive is encrypted, be aware of these structural limitations:

- **Archive Size**: The total size of the `.apx` file is visible. An attacker can infer the rough aggregate size of the compressed contents.
- **Block Boundaries**: Apex uses adaptive chunk sizes (e.g., 2MB or 4MB). The block headers (which contain the *compressed* size of the block) are not encrypted. This could theoretically allow an attacker to perform traffic analysis or infer structural boundaries of the data based on compression density variance across blocks.
- **Side-Channel Attacks**: The Python implementation of the AES/ChaCha fallback and the FastCDC chunking algorithms are not explicitly designed to be constant-time. They may be vulnerable to timing or cache-timing side-channel attacks if an attacker has local execution access to the machine performing the compression.
- **Memory Security**: Passwords and derived keys are stored in process memory during execution and are not explicitly wiped or locked (e.g., via `mlock()`) to prevent swapping to disk.

---

## 🚨 Reporting a Vulnerability or Security Issue

We believe in open, transparent security and rapid public fixes. If you discover a bug, cryptographic flaw, memory safety concern, or integrity issue, **please do not open a public issue.**

### 👉 Private Disclosure:
Please email **security@qxmcu.github.io** or use GitHub's **Private Vulnerability Reporting** mechanism.

1. **Private Disclosure**: Send us the details and a PoC.
2. **Investigation & Patch**: We will investigate and develop a patch.
3. **Public Advisory**: We will issue a CVE/security advisory along with the public disclosure once a fix is released.
