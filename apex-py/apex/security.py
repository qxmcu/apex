"""
ApexCompress Security & Authenticated Encryption Suite.
Provides zero-knowledge PBKDF2 key derivation (100,000 rounds of SHA-256)
and authenticated encryption (Encrypt-then-HMAC-SHA256) with AES-256-CTR
hardware acceleration and ChaCha20 pure-Python fallback.
"""

import hashlib
import hmac
import os
import struct
import subprocess
from typing import Tuple

PBKDF2_ITERATIONS = 100_000
SALT_LEN = 16
IV_LEN = 16
TAG_LEN = 32


def derive_keys(password: str, salt: bytes) -> Tuple[bytes, bytes]:
    """Derives a 256-bit encryption key and 256-bit HMAC key from password + salt."""
    stretched = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations=PBKDF2_ITERATIONS,
        dklen=64,
    )
    enc_key = stretched[:32]
    mac_key = stretched[32:]
    return enc_key, mac_key


def _chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    state = [
        0x61707865, 0x33322d62, 0x79746520, 0x6b657920,
        *struct.unpack("<8I", key),
        counter,
        *struct.unpack("<3I", nonce),
    ]

    def qround(a, b, c, d):
        def rot(v, n):
            return ((v << n) & 0xFFFFFFFF) | (v >> (32 - n))
        state[a] = (state[a] + state[b]) & 0xFFFFFFFF
        state[d] = rot(state[d] ^ state[a], 16)
        state[c] = (state[c] + state[d]) & 0xFFFFFFFF
        state[b] = rot(state[b] ^ state[c], 12)
        state[a] = (state[a] + state[b]) & 0xFFFFFFFF
        state[d] = rot(state[d] ^ state[a], 8)
        state[c] = (state[c] + state[d]) & 0xFFFFFFFF
        state[b] = rot(state[b] ^ state[c], 7)

    orig = list(state)
    for _ in range(10):
        qround(0, 4, 8, 12)
        qround(1, 5, 9, 13)
        qround(2, 6, 10, 14)
        qround(3, 7, 11, 15)
        qround(0, 5, 10, 15)
        qround(1, 6, 11, 12)
        qround(2, 7, 8, 13)
        qround(3, 4, 9, 14)

    out = [((state[i] + orig[i]) & 0xFFFFFFFF) for i in range(16)]
    return struct.pack("<16I", *out)


def _chacha20_crypt(data: bytes, key: bytes, nonce: bytes, counter: int = 1) -> bytes:
    out = bytearray(len(data))
    for i in range(0, len(data), 64):
        block = _chacha20_block(key, counter + (i // 64), nonce)
        chunk = data[i:i + 64]
        for j in range(len(chunk)):
            out[i + j] = chunk[j] ^ block[j]
    return bytes(out)


def _aes256_crypt(data: bytes, key: bytes, iv: bytes, decrypt: bool = False) -> bytes:
    """Uses native /usr/bin/openssl AES-256-CTR with hardware AES-NI if present."""
    if len(data) == 0:
        return b""
    cmd = ["/usr/bin/openssl", "enc", "-aes-256-ctr", "-K", key.hex(), "-iv", iv.hex()]
    if decrypt:
        cmd.insert(2, "-d")
    try:
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = p.communicate(data)
        if p.returncode == 0:
            return out
    except Exception:
        pass
    # Fallback to ChaCha20
    nonce = iv[:12]
    return _chacha20_crypt(data, key, nonce)


def encrypt_payload(data: bytes, enc_key: bytes, mac_key: bytes) -> bytes:
    """
    Encrypts data using AES-256-CTR / ChaCha20 and appends HMAC-SHA256 tag.
    Output: [16 bytes IV] + [32 bytes HMAC-SHA256] + [Ciphertext]
    """
    iv = os.urandom(IV_LEN)
    ciphertext = _aes256_crypt(data, enc_key, iv, decrypt=False)
    mac = hmac.new(mac_key, iv + ciphertext, digestmod=hashlib.sha256).digest()
    return iv + mac + ciphertext


def decrypt_payload(payload: bytes, enc_key: bytes, mac_key: bytes) -> bytes:
    """
    Verifies HMAC-SHA256 authentication tag and decrypts ciphertext.
    Raises ValueError if password is wrong or ciphertext has been tampered with.
    """
    if len(payload) < IV_LEN + TAG_LEN:
        raise ValueError("Corrupted encrypted payload: truncated data.")

    iv = payload[:IV_LEN]
    tag = payload[IV_LEN:IV_LEN + TAG_LEN]
    ciphertext = payload[IV_LEN + TAG_LEN:]

    expected_mac = hmac.new(mac_key, iv + ciphertext, digestmod=hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_mac):
        raise ValueError("Decryption failed: Incorrect password or corrupted archive!")

    plaintext = _aes256_crypt(ciphertext, enc_key, iv, decrypt=True)
    return plaintext
