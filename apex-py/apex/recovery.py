"""
ApexCompress Self-Healing Recovery Suite.
Provides Reed-Solomon / Cauchy Erasure Coding over GF(2^8) to reconstruct
corrupted or missing blocks damaged by bit rot, bad disk sectors, or transfer glitches.
"""

import struct
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

# GF(2^8) tables using primitive polynomial 0x11D (AES polynomial)
gf_exp = [0] * 512
gf_log = [0] * 256
_x = 1
for _i in range(255):
    gf_exp[_i] = _x
    gf_exp[_i + 255] = _x
    gf_log[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return gf_exp[gf_log[a] + gf_log[b]]


def gf_div(a: int, b: int) -> int:
    if a == 0:
        return 0
    if b == 0:
        raise ZeroDivisionError("GF(2^8) division by zero")
    return gf_exp[(gf_log[a] + 255 - gf_log[b]) % 255]


def gf_vec_mul(scalar: int, vec: bytes) -> bytes:
    """Multiplies a byte vector by a GF(2^8) scalar using vector LUT."""
    if scalar == 0:
        return bytes(len(vec))
    if scalar == 1:
        return vec
    if HAVE_NUMPY:
        lut = np.array([gf_mul(scalar, i) for i in range(256)], dtype=np.uint8)
        arr = np.frombuffer(vec, dtype=np.uint8)
        return lut[arr].tobytes()
    else:
        lut = [gf_mul(scalar, i) for i in range(256)]
        out = bytearray(len(vec))
        for i, b in enumerate(vec):
            out[i] = lut[b]
        return bytes(out)


def get_cauchy_coeff(i: int, total_blocks: int, parity_idx: int = 0) -> int:
    """Returns Cauchy generator matrix coefficient G[i, parity_idx] = 1 / (x_i ^ y_j)."""
    x_i = i
    y_j = (total_blocks + parity_idx + 1) & 0xFF
    denom = x_i ^ y_j
    if denom == 0:
        denom = 1
    return gf_div(1, denom)


def generate_recovery_parity(blocks: List[bytes]) -> Tuple[bytes, int]:
    """
    Generates a Reed-Solomon parity block over a set of uncompressed/compressed blocks.
    Returns (parity_bytes, max_block_length).
    """
    if not blocks:
        return b"", 0

    max_len = max(len(b) for b in blocks)
    total_blocks = len(blocks)

    if HAVE_NUMPY:
        parity = np.zeros(max_len, dtype=np.uint8)
        for i, b in enumerate(blocks):
            coeff = get_cauchy_coeff(i, total_blocks, 0)
            padded = np.zeros(max_len, dtype=np.uint8)
            padded[:len(b)] = np.frombuffer(b, dtype=np.uint8)
            if coeff == 1:
                parity ^= padded
            else:
                lut = np.array([gf_mul(coeff, v) for v in range(256)], dtype=np.uint8)
                parity ^= lut[padded]
        return parity.tobytes(), max_len
    else:
        parity = bytearray(max_len)
        for i, b in enumerate(blocks):
            coeff = get_cauchy_coeff(i, total_blocks, 0)
            scaled = gf_vec_mul(coeff, b)
            for j in range(len(scaled)):
                parity[j] ^= scaled[j]
        return bytes(parity), max_len


def heal_damaged_block(
    available_blocks: Dict[int, bytes],
    damaged_block_idx: int,
    total_blocks: int,
    parity_data: bytes,
    original_len: int,
) -> bytes:
    """
    Reconstructs a damaged block using the available blocks and recovery parity.
    """
    max_len = len(parity_data)
    coeff_damaged = get_cauchy_coeff(damaged_block_idx, total_blocks, 0)

    if HAVE_NUMPY:
        known_sum = np.zeros(max_len, dtype=np.uint8)
        for i in range(total_blocks):
            if i != damaged_block_idx:
                b = available_blocks.get(i, b"")
                coeff = get_cauchy_coeff(i, total_blocks, 0)
                padded = np.zeros(max_len, dtype=np.uint8)
                padded[:len(b)] = np.frombuffer(b, dtype=np.uint8)
                if coeff == 1:
                    known_sum ^= padded
                else:
                    lut = np.array([gf_mul(coeff, v) for v in range(256)], dtype=np.uint8)
                    known_sum ^= lut[padded]

        parity_arr = np.frombuffer(parity_data, dtype=np.uint8)
        diff = parity_arr ^ known_sum
        inv_coeff = gf_div(1, coeff_damaged)
        lut_inv = np.array([gf_mul(inv_coeff, v) for v in range(256)], dtype=np.uint8)
        healed_padded = lut_inv[diff].tobytes()
        return healed_padded[:original_len]
    else:
        known_sum = bytearray(max_len)
        for i in range(total_blocks):
            if i != damaged_block_idx:
                b = available_blocks.get(i, b"")
                coeff = get_cauchy_coeff(i, total_blocks, 0)
                scaled = gf_vec_mul(coeff, b)
                for j in range(len(scaled)):
                    known_sum[j] ^= scaled[j]

        diff = bytearray(max_len)
        for j in range(max_len):
            diff[j] = parity_data[j] ^ known_sum[j]

        inv_coeff = gf_div(1, coeff_damaged)
        healed = gf_vec_mul(inv_coeff, bytes(diff))
        return healed[:original_len]
