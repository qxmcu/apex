"""
Unit tests for ApexCompress transforms and filters.
"""

import os
import unittest
from apex.transforms import (
    TRANSFORM_NONE,
    TRANSFORM_DELTA1,
    TRANSFORM_DELTA2,
    TRANSFORM_DELTA4,
    TRANSFORM_PLANAR4,
    TRANSFORM_PLANAR4_DELTA,
    TRANSFORM_RLE,
    TRANSFORM_ARM64_BCJ,
    TRANSFORM_X86_BCJ,
    TRANSFORM_STRIDE12_PLANAR,
    TRANSFORM_STRIDE16_PLANAR,
    TRANSFORM_BC1_TEXTURE,
    TRANSFORM_BC7_TEXTURE,
    apply_transform,
    invert_transform,
    delta_encode,
    delta_decode,
    planar4_encode,
    planar4_decode,
    planar4_delta_encode,
    planar4_delta_decode,
    rle_encode,
    rle_decode,
    arm64_bcj_encode,
    arm64_bcj_decode,
    x86_bcj_encode,
    x86_bcj_decode,
    stride12_planar_encode,
    stride12_planar_decode,
    stride16_planar_encode,
    stride16_planar_decode,
    bc1_texture_encode,
    bc1_texture_decode,
    bc7_texture_encode,
    bc7_texture_decode,
)


class TestTransforms(unittest.TestCase):

    def test_delta_roundtrips(self):
        for stride in [1, 2, 4]:
            for size in [0, 1, 2, 3, 4, 5, 17, 256, 1024, 65537]:
                data = os.urandom(size)
                enc = delta_encode(data, stride)
                dec = delta_decode(enc, stride)
                self.assertEqual(data, dec, f"Delta stride={stride} failed for size={size}")

    def test_planar4_roundtrips(self):
        for size in [0, 1, 2, 3, 4, 5, 7, 8, 9, 100, 1024, 65537]:
            data = os.urandom(size)
            enc = planar4_encode(data)
            dec = planar4_decode(enc)
            self.assertEqual(data, dec, f"Planar4 failed for size={size}")

    def test_planar4_delta_roundtrips(self):
        for size in [0, 1, 2, 3, 4, 7, 8, 15, 100, 1024, 65537]:
            data = os.urandom(size)
            enc = planar4_delta_encode(data)
            dec = planar4_delta_decode(enc)
            self.assertEqual(data, dec, f"Planar4+Delta failed for size={size}")

    def test_rle_roundtrips(self):
        # Repetitive sequences
        test_cases = [
            b"",
            b"A",
            b"AAAA",
            b"AAAAABBBBBCCCCCDDDDD",
            b"\xAA" * 10, # Escape character collision test
            b"Prefix" + b"\x00" * 500 + b"\xAA" * 50 + b"Suffix",
            os.urandom(2048),
        ]
        for data in test_cases:
            enc = rle_encode(data)
            dec = rle_decode(enc)
            self.assertEqual(data, dec)

    def test_arm64_bcj_roundtrip(self):
        # Synthetic instructions: bl (0x94...) and b (0x14...)
        code = bytearray()
        for i in range(100):
            # bl with imm26
            instr1 = 0x94000000 | (i * 13 & 0x03FFFFFF)
            code.extend(instr1.to_bytes(4, "little"))
            # b with imm26
            instr2 = 0x14000000 | ((i * 37 + 5) & 0x03FFFFFF)
            code.extend(instr2.to_bytes(4, "little"))
            # non-branch instruction
            instr3 = 0xD503201F # nop
            code.extend(instr3.to_bytes(4, "little"))

        enc = arm64_bcj_encode(bytes(code))
        dec = arm64_bcj_decode(enc)
        self.assertEqual(bytes(code), dec)

    def test_x86_bcj_roundtrip(self):
        # Synthetic instructions: call (0xE8) and jmp (0xE9)
        code = bytearray()
        for i in range(100):
            code.append(0xE8) # CALL
            code.extend((i * 1024 - 500).to_bytes(4, "little", signed=True))
            code.append(0x90) # NOP
            code.append(0xE9) # JMP
            code.extend((-i * 256).to_bytes(4, "little", signed=True))

        enc = x86_bcj_encode(bytes(code))
        dec = x86_bcj_decode(enc)
        self.assertEqual(bytes(code), dec)

    def test_stride12_mesh_roundtrip(self):
        for size in [0, 1, 5, 11, 12, 13, 24, 36, 1200, 65431]:
            data = os.urandom(size)
            enc = stride12_planar_encode(data)
            dec = stride12_planar_decode(enc)
            self.assertEqual(data, dec, f"Stride12 failed for size={size}")

    def test_stride16_mesh_roundtrip(self):
        for size in [0, 1, 5, 15, 16, 17, 32, 48, 1600, 65431]:
            data = os.urandom(size)
            enc = stride16_planar_encode(data)
            dec = stride16_planar_decode(enc)
            self.assertEqual(data, dec, f"Stride16 failed for size={size}")

    def test_bc1_texture_roundtrip(self):
        for size in [0, 1, 7, 8, 9, 16, 800, 65431]:
            data = os.urandom(size)
            enc = bc1_texture_encode(data)
            dec = bc1_texture_decode(enc)
            self.assertEqual(data, dec, f"BC1 failed for size={size}")

    def test_bc7_texture_roundtrip(self):
        for size in [0, 1, 7, 15, 16, 17, 32, 1600, 65431]:
            data = os.urandom(size)
            enc = bc7_texture_encode(data)
            dec = bc7_texture_decode(enc)
            self.assertEqual(data, dec, f"BC7 failed for size={size}")

    def test_all_transform_ids(self):
        sample = b"Testing generic transform pipeline with random: " + os.urandom(512)
        for tid in [
            TRANSFORM_NONE,
            TRANSFORM_DELTA1,
            TRANSFORM_DELTA2,
            TRANSFORM_DELTA4,
            TRANSFORM_PLANAR4,
            TRANSFORM_PLANAR4_DELTA,
            TRANSFORM_RLE,
            TRANSFORM_ARM64_BCJ,
            TRANSFORM_X86_BCJ,
            TRANSFORM_STRIDE12_PLANAR,
            TRANSFORM_STRIDE16_PLANAR,
            TRANSFORM_BC1_TEXTURE,
            TRANSFORM_BC7_TEXTURE,
        ]:
            enc = apply_transform(sample, tid)
            dec = invert_transform(enc, tid)
            self.assertEqual(sample, dec, f"Generic pipeline failed for transform_id={tid}")


if __name__ == "__main__":
    unittest.main()
