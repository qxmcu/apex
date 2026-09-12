"""
ApexCompress Transforms & Preconditioners.
Provides high-performance SIMD/NumPy accelerated and fallback pure-Python
preconditioning filters to dramatically boost compression ratios.
"""

import struct
from typing import Tuple

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

# Transform IDs
TRANSFORM_NONE = 0
TRANSFORM_DELTA1 = 1
TRANSFORM_DELTA2 = 2
TRANSFORM_DELTA4 = 3
TRANSFORM_PLANAR4 = 4
TRANSFORM_PLANAR4_DELTA = 5
TRANSFORM_RLE = 6
TRANSFORM_ARM64_BCJ = 7
TRANSFORM_X86_BCJ = 8
TRANSFORM_STRIDE12_PLANAR = 9
TRANSFORM_STRIDE16_PLANAR = 10
TRANSFORM_BC1_TEXTURE = 11
TRANSFORM_BC7_TEXTURE = 12

TRANSFORM_NAMES = {
    TRANSFORM_NONE: "Identity (None)",
    TRANSFORM_DELTA1: "Delta-1 (Byte Differential)",
    TRANSFORM_DELTA2: "Delta-2 (16-bit Stride)",
    TRANSFORM_DELTA4: "Delta-4 (32-bit Word Stride)",
    TRANSFORM_PLANAR4: "Planar-4 (32-bit Byte Split)",
    TRANSFORM_PLANAR4_DELTA: "Planar-4 + Intra-Plane Delta",
    TRANSFORM_RLE: "Run-Length Encoding (Zero/Run Reducer)",
    TRANSFORM_ARM64_BCJ: "ARM64 BCJ (Branch Call Target Translation)",
    TRANSFORM_X86_BCJ: "x86 BCJ (Branch Call Target Translation)",
    TRANSFORM_STRIDE12_PLANAR: "Stride-12 3D Mesh / Coordinate Delta",
    TRANSFORM_STRIDE16_PLANAR: "Stride-16 4D Float / SIMD Vector Delta",
    TRANSFORM_BC1_TEXTURE: "BC1 / DXT1 GPU Texture Plane Separation",
    TRANSFORM_BC7_TEXTURE: "BC7 Direct3D Texture Block Separation",
}


def delta_encode(data: bytes, stride: int = 1) -> bytes:
    """Computes byte-wise running difference with given stride."""
    n = len(data)
    if n <= stride:
        return data

    if HAVE_NUMPY:
        arr = np.frombuffer(data, dtype=np.uint8)
        diff = arr.copy()
        k = n // stride
        for s in range(stride):
            diff[s:k*stride:stride][1:] = arr[s:k*stride:stride][1:] - arr[s:k*stride:stride][:-1]
        return diff.tobytes()
    else:
        out = bytearray(data)
        for i in range(n - 1, stride - 1, -1):
            out[i] = (out[i] - out[i - stride]) & 0xFF
        return bytes(out)


def delta_decode(data: bytes, stride: int = 1) -> bytes:
    """Inverts delta encoding with given stride."""
    n = len(data)
    if n <= stride:
        return data

    if HAVE_NUMPY:
        diff = np.frombuffer(data, dtype=np.uint8)
        dec = diff.copy()
        k = n // stride
        for s in range(stride):
            dec[s:k*stride:stride] = np.cumsum(diff[s:k*stride:stride], dtype=np.uint8)
        return dec.tobytes()
    else:
        out = bytearray(data)
        for i in range(stride, n):
            out[i] = (out[i] + out[i - stride]) & 0xFF
        return bytes(out)


def planar4_encode(data: bytes) -> bytes:
    """Transposes interleaved 4-byte sequences into 4 contiguous byte planes."""
    n = len(data)
    k = n // 4
    if k == 0:
        return data

    if HAVE_NUMPY:
        arr = np.frombuffer(data, dtype=np.uint8)
        planar_core = arr[:4*k].reshape(-1, 4).T.flatten()
        if n % 4 != 0:
            return planar_core.tobytes() + data[4*k:]
        return planar_core.tobytes()
    else:
        out = bytearray(n)
        for p in range(4):
            out[p*k:(p+1)*k] = data[p:4*k:4]
        if n % 4 != 0:
            out[4*k:] = data[4*k:]
        return bytes(out)


def planar4_decode(data: bytes) -> bytes:
    """Inverts planar4 encoding back into interleaved byte sequences."""
    n = len(data)
    k = n // 4
    if k == 0:
        return data

    if HAVE_NUMPY:
        arr = np.frombuffer(data, dtype=np.uint8)
        planar_core = arr[:4*k].reshape(4, -1).T.flatten()
        if n % 4 != 0:
            return planar_core.tobytes() + data[4*k:]
        return planar_core.tobytes()
    else:
        out = bytearray(n)
        for p in range(4):
            out[p:4*k:4] = data[p*k:(p+1)*k]
        if n % 4 != 0:
            out[4*k:] = data[4*k:]
        return bytes(out)


def planar4_delta_encode(data: bytes) -> bytes:
    """Transposes into 4 planes, then applies Delta-1 within each plane."""
    n = len(data)
    k = n // 4
    if k <= 1:
        return delta_encode(data, 1)

    planar = planar4_encode(data)
    if HAVE_NUMPY:
        arr = np.frombuffer(planar, dtype=np.uint8).copy()
        for p in range(4):
            plane = arr[p*k:(p+1)*k]
            diff = np.empty_like(plane)
            diff[0] = plane[0]
            diff[1:] = plane[1:] - plane[:-1]
            arr[p*k:(p+1)*k] = diff
        return arr.tobytes()
    else:
        out = bytearray(planar)
        for p in range(4):
            start = p * k
            end = (p + 1) * k
            for i in range(end - 1, start, -1):
                out[i] = (out[i] - out[i - 1]) & 0xFF
        return bytes(out)


def planar4_delta_decode(data: bytes) -> bytes:
    """Inverts planar4 delta encoding."""
    n = len(data)
    k = n // 4
    if k <= 1:
        return delta_decode(data, 1)

    if HAVE_NUMPY:
        arr = np.frombuffer(data, dtype=np.uint8).copy()
        for p in range(4):
            arr[p*k:(p+1)*k] = np.cumsum(arr[p*k:(p+1)*k], dtype=np.uint8)
        return planar4_decode(arr.tobytes())
    else:
        out = bytearray(data)
        for p in range(4):
            start = p * k
            end = (p + 1) * k
            for i in range(start + 1, end):
                out[i] = (out[i] + out[i - 1]) & 0xFF
        return planar4_decode(bytes(out))


def rle_encode(data: bytes, escape: int = 0xAA) -> bytes:
    """Byte-stuffed run length encoding: collapses runs >= 4 identical bytes."""
    out = bytearray()
    n = len(data)
    i = 0
    while i < n:
        b = data[i]
        run_len = 1
        while i + run_len < n and data[i + run_len] == b and run_len < 255:
            run_len += 1

        if run_len >= 4:
            out.append(escape)
            out.append(run_len)
            out.append(b)
            i += run_len
        elif b == escape:
            out.append(escape)
            out.append(0)
            out.append(escape)
            i += 1
        else:
            out.append(b)
            i += 1
    return bytes(out)


def rle_decode(data: bytes, escape: int = 0xAA) -> bytes:
    """Inverts byte-stuffed run length encoding."""
    out = bytearray()
    n = len(data)
    i = 0
    while i < n:
        b = data[i]
        if b == escape:
            if i + 2 >= n:
                raise ValueError("Malformed RLE stream: truncated escape sequence")
            count = data[i + 1]
            val = data[i + 2]
            i += 3
            if count == 0:
                out.append(escape)
            else:
                out.extend([val] * count)
        else:
            out.append(b)
            i += 1
    return bytes(out)


def arm64_bcj_encode(data: bytes) -> bytes:
    """Translates relative ARM64 branch/call target offsets to absolute offsets."""
    n = len(data)
    if n < 4:
        return data
    k = (n // 4) * 4
    out = bytearray(data)
    for i in range(0, k, 4):
        instr = struct.unpack_from("<I", out, i)[0]
        op = instr & 0xFC000000
        if op == 0x94000000 or op == 0x14000000:
            imm26 = instr & 0x03FFFFFF
            pc_word = i >> 2
            abs_word = (imm26 + pc_word) & 0x03FFFFFF
            struct.pack_into("<I", out, i, op | abs_word)
    return bytes(out)


def arm64_bcj_decode(data: bytes) -> bytes:
    """Inverts relative ARM64 branch/call target translation."""
    n = len(data)
    if n < 4:
        return data
    k = (n // 4) * 4
    out = bytearray(data)
    for i in range(0, k, 4):
        instr = struct.unpack_from("<I", out, i)[0]
        op = instr & 0xFC000000
        if op == 0x94000000 or op == 0x14000000:
            abs_word = instr & 0x03FFFFFF
            pc_word = i >> 2
            imm26 = (abs_word - pc_word) & 0x03FFFFFF
            struct.pack_into("<I", out, i, op | imm26)
    return bytes(out)


def x86_bcj_encode(data: bytes) -> bytes:
    """Translates relative x86/x64 CALL/JMP target addresses to absolute addresses."""
    n = len(data)
    if n < 5:
        return data
    out = bytearray(data)
    i = 0
    while i <= n - 5:
        b = out[i]
        if b == 0xE8 or b == 0xE9:
            rel = struct.unpack_from("<i", out, i + 1)[0]
            abs_addr = (rel + (i + 5)) & 0xFFFFFFFF
            if abs_addr & 0x80000000:
                abs_addr -= 0x100000000
            struct.pack_into("<i", out, i + 1, abs_addr)
            i += 5
        else:
            i += 1
    return bytes(out)


def x86_bcj_decode(data: bytes) -> bytes:
    """Inverts relative x86/x64 CALL/JMP target translation."""
    n = len(data)
    if n < 5:
        return data
    out = bytearray(data)
    i = 0
    while i <= n - 5:
        b = out[i]
        if b == 0xE8 or b == 0xE9:
            abs_addr = struct.unpack_from("<i", out, i + 1)[0]
            rel = (abs_addr - (i + 5)) & 0xFFFFFFFF
            if rel & 0x80000000:
                rel -= 0x100000000
            struct.pack_into("<i", out, i + 1, rel)
            i += 5
        else:
            i += 1
    return bytes(out)


def stride12_planar_encode(data: bytes) -> bytes:
    """Stride-12 3D mesh coordinate plane separation and delta differentiation."""
    stride = 12
    n = len(data)
    k = n // stride
    if k <= 1:
        return data
    if HAVE_NUMPY:
        arr = np.frombuffer(data[:k*stride], dtype=np.uint8).reshape(k, stride)
        diff = np.empty_like(arr)
        diff[0, :] = arr[0, :]
        diff[1:, :] = arr[1:, :] - arr[:-1, :]
        enc = diff.T.tobytes()
        if n % stride != 0:
            return enc + data[k*stride:]
        return enc
    else:
        out = bytearray(n)
        for s in range(stride):
            prev = 0
            for i in range(k):
                val = data[i * stride + s]
                out[s * k + i] = (val - prev) & 0xFF
                prev = val
        if n % stride != 0:
            out[k*stride:] = data[k*stride:]
        return bytes(out)


def stride12_planar_decode(data: bytes) -> bytes:
    """Inverts Stride-12 3D mesh coordinate plane separation."""
    stride = 12
    n = len(data)
    k = n // stride
    if k <= 1:
        return data
    if HAVE_NUMPY:
        arr_planes = np.frombuffer(data[:k*stride], dtype=np.uint8).reshape(stride, k).T
        dec = np.cumsum(arr_planes, axis=0, dtype=np.uint8).tobytes()
        if n % stride != 0:
            return dec + data[k*stride:]
        return dec
    else:
        out = bytearray(n)
        for s in range(stride):
            acc = 0
            for i in range(k):
                diff = data[s * k + i]
                acc = (acc + diff) & 0xFF
                out[i * stride + s] = acc
        if n % stride != 0:
            out[k*stride:] = data[k*stride:]
        return bytes(out)


def stride16_planar_encode(data: bytes) -> bytes:
    """Stride-16 4D float / SIMD vector plane separation and delta differentiation."""
    stride = 16
    n = len(data)
    k = n // stride
    if k <= 1:
        return data
    if HAVE_NUMPY:
        arr = np.frombuffer(data[:k*stride], dtype=np.uint8).reshape(k, stride)
        diff = np.empty_like(arr)
        diff[0, :] = arr[0, :]
        diff[1:, :] = arr[1:, :] - arr[:-1, :]
        enc = diff.T.tobytes()
        if n % stride != 0:
            return enc + data[k*stride:]
        return enc
    else:
        out = bytearray(n)
        for s in range(stride):
            prev = 0
            for i in range(k):
                val = data[i * stride + s]
                out[s * k + i] = (val - prev) & 0xFF
                prev = val
        if n % stride != 0:
            out[k*stride:] = data[k*stride:]
        return bytes(out)


def stride16_planar_decode(data: bytes) -> bytes:
    """Inverts Stride-16 4D float plane separation."""
    stride = 16
    n = len(data)
    k = n // stride
    if k <= 1:
        return data
    if HAVE_NUMPY:
        arr_planes = np.frombuffer(data[:k*stride], dtype=np.uint8).reshape(stride, k).T
        dec = np.cumsum(arr_planes, axis=0, dtype=np.uint8).tobytes()
        if n % stride != 0:
            return dec + data[k*stride:]
        return dec
    else:
        out = bytearray(n)
        for s in range(stride):
            acc = 0
            for i in range(k):
                diff = data[s * k + i]
                acc = (acc + diff) & 0xFF
                out[i * stride + s] = acc
        if n % stride != 0:
            out[k*stride:] = data[k*stride:]
        return bytes(out)


def bc1_texture_encode(data: bytes) -> bytes:
    """Separates BC1 4x4 texture blocks: color endpoints from interpolation indices."""
    stride = 8
    n = len(data)
    k = n // stride
    if k <= 1:
        return data
    if HAVE_NUMPY:
        arr = np.frombuffer(data[:k*stride], dtype=np.uint8).reshape(k, 8)
        colors = arr[:, :4]
        indices = arr[:, 4:]
        diff_colors = np.empty_like(colors)
        diff_colors[0, :] = colors[0, :]
        diff_colors[1:, :] = colors[1:, :] - colors[:-1, :]
        enc = diff_colors.T.tobytes() + indices.tobytes()
        if n % stride != 0:
            return enc + data[k*stride:]
        return enc
    else:
        colors_out = bytearray(k * 4)
        indices_out = bytearray(k * 4)
        for c in range(4):
            prev = 0
            for i in range(k):
                val = data[i * 8 + c]
                colors_out[c * k + i] = (val - prev) & 0xFF
                prev = val
        for i in range(k):
            indices_out[i*4 : (i+1)*4] = data[i*8 + 4 : i*8 + 8]
        res = bytes(colors_out) + bytes(indices_out)
        if n % stride != 0:
            res += data[k*stride:]
        return res


def bc1_texture_decode(data: bytes) -> bytes:
    """Inverts BC1 texture plane separation."""
    stride = 8
    n = len(data)
    k = n // stride
    if k <= 1:
        return data
    if HAVE_NUMPY:
        color_bytes = data[:k * 4]
        index_bytes = data[k * 4 : k * 8]
        colors_t = np.frombuffer(color_bytes, dtype=np.uint8).reshape(4, k).T
        colors = np.cumsum(colors_t, axis=0, dtype=np.uint8)
        indices = np.frombuffer(index_bytes, dtype=np.uint8).reshape(k, 4)
        reassembled = np.hstack([colors, indices]).tobytes()
        if n % stride != 0:
            return reassembled + data[k*stride:]
        return reassembled
    else:
        out = bytearray(n)
        for c in range(4):
            acc = 0
            for i in range(k):
                diff = data[c * k + i]
                acc = (acc + diff) & 0xFF
                out[i * 8 + c] = acc
        indices_start = k * 4
        for i in range(k):
            out[i * 8 + 4 : i * 8 + 8] = data[indices_start + i * 4 : indices_start + (i + 1) * 4]
        if n % stride != 0:
            out[k*stride:] = data[k*stride:]
        return bytes(out)


def bc7_texture_encode(data: bytes) -> bytes:
    """Separates BC7 Direct3D texture blocks: 8 bytes endpoints from 8 bytes weights."""
    stride = 16
    n = len(data)
    k = n // stride
    if k <= 1:
        return data
    if HAVE_NUMPY:
        arr = np.frombuffer(data[:k*stride], dtype=np.uint8).reshape(k, 16)
        endpoints = arr[:, :8]
        weights = arr[:, 8:]
        diff_ep = np.empty_like(endpoints)
        diff_ep[0, :] = endpoints[0, :]
        diff_ep[1:, :] = endpoints[1:, :] - endpoints[:-1, :]
        enc = diff_ep.T.tobytes() + weights.tobytes()
        if n % stride != 0:
            return enc + data[k*stride:]
        return enc
    else:
        ep_out = bytearray(k * 8)
        weights_out = bytearray(k * 8)
        for c in range(8):
            prev = 0
            for i in range(k):
                val = data[i * 16 + c]
                ep_out[c * k + i] = (val - prev) & 0xFF
                prev = val
        for i in range(k):
            weights_out[i*8 : (i+1)*8] = data[i*16 + 8 : i*16 + 16]
        res = bytes(ep_out) + bytes(weights_out)
        if n % stride != 0:
            res += data[k*stride:]
        return res


def bc7_texture_decode(data: bytes) -> bytes:
    """Inverts BC7 texture plane separation."""
    stride = 16
    n = len(data)
    k = n // stride
    if k <= 1:
        return data
    if HAVE_NUMPY:
        ep_bytes = data[:k * 8]
        weight_bytes = data[k * 8 : k * 16]
        ep_t = np.frombuffer(ep_bytes, dtype=np.uint8).reshape(8, k).T
        endpoints = np.cumsum(ep_t, axis=0, dtype=np.uint8)
        weights = np.frombuffer(weight_bytes, dtype=np.uint8).reshape(k, 8)
        reassembled = np.hstack([endpoints, weights]).tobytes()
        if n % stride != 0:
            return reassembled + data[k*stride:]
        return reassembled
    else:
        out = bytearray(n)
        for c in range(8):
            acc = 0
            for i in range(k):
                diff = data[c * k + i]
                acc = (acc + diff) & 0xFF
                out[i * 16 + c] = acc
        weights_start = k * 8
        for i in range(k):
            out[i * 16 + 8 : i * 16 + 16] = data[weights_start + i * 8 : weights_start + (i + 1) * 8]
        if n % stride != 0:
            out[k*stride:] = data[k*stride:]
        return bytes(out)


def apply_transform(data: bytes, transform_id: int) -> bytes:
    """Applies a forward preconditioning transform."""
    if transform_id == TRANSFORM_NONE:
        return data
    elif transform_id == TRANSFORM_DELTA1:
        return delta_encode(data, 1)
    elif transform_id == TRANSFORM_DELTA2:
        return delta_encode(data, 2)
    elif transform_id == TRANSFORM_DELTA4:
        return delta_encode(data, 4)
    elif transform_id == TRANSFORM_PLANAR4:
        return planar4_encode(data)
    elif transform_id == TRANSFORM_PLANAR4_DELTA:
        return planar4_delta_encode(data)
    elif transform_id == TRANSFORM_RLE:
        return rle_encode(data)
    elif transform_id == TRANSFORM_ARM64_BCJ:
        return arm64_bcj_encode(data)
    elif transform_id == TRANSFORM_X86_BCJ:
        return x86_bcj_encode(data)
    elif transform_id == TRANSFORM_STRIDE12_PLANAR:
        return stride12_planar_encode(data)
    elif transform_id == TRANSFORM_STRIDE16_PLANAR:
        return stride16_planar_encode(data)
    elif transform_id == TRANSFORM_BC1_TEXTURE:
        return bc1_texture_encode(data)
    elif transform_id == TRANSFORM_BC7_TEXTURE:
        return bc7_texture_encode(data)
    else:
        raise ValueError(f"Unknown transform ID: {transform_id}")


def invert_transform(data: bytes, transform_id: int) -> bytes:
    """Inverts a preconditioning transform."""
    if transform_id == TRANSFORM_NONE:
        return data
    elif transform_id == TRANSFORM_DELTA1:
        return delta_decode(data, 1)
    elif transform_id == TRANSFORM_DELTA2:
        return delta_decode(data, 2)
    elif transform_id == TRANSFORM_DELTA4:
        return delta_decode(data, 4)
    elif transform_id == TRANSFORM_PLANAR4:
        return planar4_decode(data)
    elif transform_id == TRANSFORM_PLANAR4_DELTA:
        return planar4_delta_decode(data)
    elif transform_id == TRANSFORM_RLE:
        return rle_decode(data)
    elif transform_id == TRANSFORM_ARM64_BCJ:
        return arm64_bcj_decode(data)
    elif transform_id == TRANSFORM_X86_BCJ:
        return x86_bcj_decode(data)
    elif transform_id == TRANSFORM_STRIDE12_PLANAR:
        return stride12_planar_decode(data)
    elif transform_id == TRANSFORM_STRIDE16_PLANAR:
        return stride16_planar_decode(data)
    elif transform_id == TRANSFORM_BC1_TEXTURE:
        return bc1_texture_decode(data)
    elif transform_id == TRANSFORM_BC7_TEXTURE:
        return bc7_texture_decode(data)
    else:
        raise ValueError(f"Unknown transform ID: {transform_id}")
