"""
Advanced Feature Tests for ApexCompress:
Authenticated Encryption, Reed-Solomon Self-Healing Recovery,
Content-Aware Deduplication, and Corrupted Archive Repair.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from apex.archive import (
    DEFAULT_BLOCK_SIZE,
    FLAG_ENCRYPTED,
    FLAG_RECOVERY,
    PIPELINE_DEDUP_REF,
    compress_archive,
    decompress_archive,
    read_archive_header,
    repair_archive,
    test_archive,
)
from apex.engine import Mode, compress_chunk, decompress_chunk
from apex.recovery import generate_recovery_parity, heal_damaged_block
from apex.security import (
    _chacha20_crypt,
    decrypt_payload,
    derive_keys,
    encrypt_payload,
)


class TestSecurity(unittest.TestCase):

    def test_derive_keys(self):
        salt = os.urandom(16)
        k1, m1 = derive_keys("mypassword", salt)
        k2, m2 = derive_keys("mypassword", salt)
        self.assertEqual(k1, k2)
        self.assertEqual(m1, m2)
        self.assertEqual(len(k1), 32)
        self.assertEqual(len(m1), 32)
        # K_enc and K_mac must be cryptographically independent subkeys
        self.assertNotEqual(k1, m1)

        # Different salt gives different keys
        k3, m3 = derive_keys("mypassword", os.urandom(16))
        self.assertNotEqual(k1, k3)
        self.assertNotEqual(m1, m3)

    def test_payload_encryption_roundtrip(self):
        salt = os.urandom(16)
        enc_key, mac_key = derive_keys("super_secure_key", salt)
        sample = b"Secret payload that must remain confidential!" * 50

        enc = encrypt_payload(sample, enc_key, mac_key)
        self.assertNotEqual(sample, enc)

        dec = decrypt_payload(enc, enc_key, mac_key)
        self.assertEqual(sample, dec)

    def test_wrong_password_rejected(self):
        salt = os.urandom(16)
        enc_key1, mac_key1 = derive_keys("correct_pass", salt)
        enc_key2, mac_key2 = derive_keys("wrong_pass", salt)

        sample = b"Top secret data!"
        enc = encrypt_payload(sample, enc_key1, mac_key1)

        with self.assertRaises(ValueError):
            decrypt_payload(enc, enc_key2, mac_key2)

    def test_tampered_payload_rejected(self):
        salt = os.urandom(16)
        enc_key, mac_key = derive_keys("pass", salt)
        sample = b"Integrity verified data!"
        enc = bytearray(encrypt_payload(sample, enc_key, mac_key))

        # Tamper with a byte in ciphertext
        enc[-1] ^= 0x01
        with self.assertRaises(ValueError):
            decrypt_payload(bytes(enc), enc_key, mac_key)

    def test_chacha20_fallback(self):
        key = os.urandom(32)
        nonce = os.urandom(12)
        data = b"Pure Python ChaCha20 encryption test string!" * 10
        enc = _chacha20_crypt(data, key, nonce)
        dec = _chacha20_crypt(enc, key, nonce)
        self.assertEqual(data, dec)


class TestRecovery(unittest.TestCase):

    def test_reed_solomon_parity_and_healing(self):
        b0 = b"First block with some text data" * 10
        b1 = b"Second block with different binary" + os.urandom(100)
        b2 = b"Third block with repeating zero characters" + b"\x00" * 80
        b3 = b"Fourth block short"

        blocks = [b0, b1, b2, b3]
        parity, max_len = generate_recovery_parity(blocks)
        self.assertGreater(len(parity), 0)

        # Simulate damage / erasure to block 1
        available = {0: b0, 2: b2, 3: b3}
        healed = heal_damaged_block(available, 1, 4, parity, len(b1))
        self.assertEqual(b1, healed, "Reed-Solomon failed to reconstruct block 1")

        # Simulate damage / erasure to block 0
        available0 = {1: b1, 2: b2, 3: b3}
        healed0 = heal_damaged_block(available0, 0, 4, parity, len(b0))
        self.assertEqual(b0, healed0, "Reed-Solomon failed to reconstruct block 0")


class TestArchiveAdvanced(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_encrypted_archive(self):
        source = Path(self.tmpdir) / "classified.pdf"
        source.write_bytes(b"%PDF-1.4 Classified military research data...\n" * 500)
        archive = Path(self.tmpdir) / "classified.apx"

        # Compress with password
        res = compress_archive(str(source), str(archive), password="apex_ultra_pass")
        self.assertTrue(res["encrypted"])
        self.assertTrue(archive.exists())

        # Test archive with wrong password must fail
        with self.assertRaises(ValueError):
            test_archive(str(archive), password="wrong_pass")

        # Test archive with correct password must pass
        t_res = test_archive(str(archive), password="apex_ultra_pass")
        self.assertEqual(t_res["status"], "PASSED")
        self.assertTrue(t_res["encrypted"])

        # Decompress with correct password
        out_file = Path(self.tmpdir) / "restored.pdf"
        d_res = decompress_archive(str(archive), output_dir=str(out_file), password="apex_ultra_pass")
        self.assertEqual(d_res["status"], "SUCCESS")
        self.assertEqual(out_file.read_bytes(), source.read_bytes())

    def test_block_deduplication(self):
        # Create data with repeated 64KB blocks
        block_a = os.urandom(64 * 1024)
        block_b = os.urandom(64 * 1024)
        # Sequence: A, B, A, B, A
        full_data = block_a + block_b + block_a + block_b + block_a

        source = Path(self.tmpdir) / "dedup_source.bin"
        source.write_bytes(full_data)
        archive = Path(self.tmpdir) / "dedup_test.apx"

        # Use 64KB block size
        res = compress_archive(
            str(source),
            str(archive),
            mode=Mode.FAST,
            block_size=64 * 1024,
        )

        pids = [b["pipeline_id"] for b in res["block_records"]]
        self.assertIn(PIPELINE_DEDUP_REF, pids, "Expected deduplication pipeline references")

        # Verify integrity
        t_res = test_archive(str(archive))
        self.assertEqual(t_res["status"], "PASSED")

        # Extract and verify 100% bit-exact restoration
        out_file = Path(self.tmpdir) / "restored_dedup.bin"
        decompress_archive(str(archive), output_dir=str(out_file))
        self.assertEqual(out_file.read_bytes(), full_data)

    def test_self_healing_repair(self):
        source = Path(self.tmpdir) / "precious_family_photos.dat"
        # 3 blocks of 32KB
        chunk1 = os.urandom(32 * 1024)
        chunk2 = b"Hello world repeated block 2!\n" * 1000
        chunk3 = os.urandom(16 * 1024)
        original_data = chunk1 + chunk2 + chunk3
        source.write_bytes(original_data)

        archive = Path(self.tmpdir) / "photos.apx"
        repaired_archive = Path(self.tmpdir) / "photos_fixed.apx"

        # Compress with self-healing recovery enabled
        res = compress_archive(
            str(source),
            str(archive),
            mode=Mode.FAST,
            block_size=32 * 1024,
            recovery=True,
        )
        self.assertTrue(res["recovery"])

        # Archive is healthy initially
        self.assertEqual(test_archive(str(archive))["status"], "PASSED")

        # Intentionally corrupt block #1 (mutate payload)
        with open(archive, "r+b") as f:
            # Skip magic (8), header (18), manifest
            flags, bsize, manifest, _, _ = read_archive_header(f)
            # We are now at start of block 0
            pid, ulen, clen, crc = [f.read(1), f.read(4), f.read(4), f.read(4)]
            c_len0 = int.from_bytes(clen, "little")
            f.seek(c_len0, os.SEEK_CUR)

            # Now at block 1 header
            b1_hdr_pos = f.tell()
            f.seek(13, os.SEEK_CUR)
            # Mutate first 10 bytes of block 1 payload
            payload_pos = f.tell()
            f.write(b"\xFF\xFE\xFD\xFC\xFB\xFA\xF9\xF8\xF7\xF6")

        # Corrupted archive must fail validation
        with self.assertRaises(ValueError):
            test_archive(str(archive))

        # Perform self-healing repair
        repair_res = repair_archive(str(archive), output_repaired_path=str(repaired_archive))
        self.assertEqual(repair_res["status"], "SUCCESS_REPAIRED")
        self.assertEqual(repair_res["healed_block_index"], 1)

        # Repaired archive must pass test_archive
        repaired_test = test_archive(str(repaired_archive))
        self.assertEqual(repaired_test["status"], "PASSED")

        # Repaired archive must decompress bit-for-bit to the exact original data!
        out_file = Path(self.tmpdir) / "restored_repaired.dat"
        decompress_archive(str(repaired_archive), output_dir=str(out_file))
        self.assertEqual(out_file.read_bytes(), original_data)

    def test_encrypted_and_recovery_repair(self):
        source = Path(self.tmpdir) / "secret_vault.dat"
        orig_bytes = os.urandom(48 * 1024)
        source.write_bytes(orig_bytes)

        archive = Path(self.tmpdir) / "vault.apx"
        repaired_archive = Path(self.tmpdir) / "vault_fixed.apx"

        compress_archive(
            str(source),
            str(archive),
            mode=Mode.FAST,
            block_size=16 * 1024,
            password="apex_strong_pass",
            recovery=True,
        )

        # Corrupt block 0 payload
        with open(archive, "r+b") as f:
            flags, bsize, manifest, _, _ = read_archive_header(f, password="apex_strong_pass")
            # Seek past block 0 header (13 bytes)
            f.seek(13, os.SEEK_CUR)
            f.write(b"\x00\x00\x00\x00\x00\x00\x00\x00")

        # Repair with password
        repair_res = repair_archive(
            str(archive),
            output_repaired_path=str(repaired_archive),
            password="apex_strong_pass",
        )
        self.assertEqual(repair_res["status"], "SUCCESS_REPAIRED")
        self.assertEqual(repair_res["healed_block_index"], 0)

        # Decompress repaired archive
        out_file = Path(self.tmpdir) / "restored_vault.dat"
        decompress_archive(
            str(repaired_archive),
            output_dir=str(out_file),
            password="apex_strong_pass",
        )
        self.assertEqual(out_file.read_bytes(), orig_bytes)

    def test_fast_mode_3d_mesh_and_texture_steering(self):
        import struct, math

        # 1. Generate 3D vertex mesh
        mesh_data = bytearray()
        for i in range(1000):
            theta = i * 0.05
            x = math.sin(theta) * 10.0
            y = math.cos(theta) * 10.0
            z = i * 0.1
            mesh_data.extend(struct.pack("<fff", x, y, z))

        res_mesh = compress_chunk(bytes(mesh_data), mode=Mode.FAST)
        # Verify it chose specialized 3D mesh pipeline
        self.assertIn(res_mesh.pipeline_id, [90, 92])
        # Verify 100% bit-exact decompression
        dec_mesh = decompress_chunk(res_mesh.data, res_mesh.pipeline_id)
        self.assertEqual(bytes(mesh_data), dec_mesh)

        # 2. Generate BC1 GPU texture
        tex_data = bytearray(b"DDS ") # DirectDraw Surface signature
        for i in range(500):
            c0 = 0x5678 + (i % 50)
            c1 = 0x5670 + (i % 50)
            indices = 0xAA55AA55 ^ (i * 17)
            tex_data.extend(struct.pack("<HHI", c0, c1, indices))

        res_tex = compress_chunk(bytes(tex_data), mode=Mode.FAST)
        # Verify it chose specialized texture pipeline
        self.assertIn(res_tex.pipeline_id, [100, 102])
        # Verify 100% bit-exact decompression
        dec_tex = decompress_chunk(res_tex.data, res_tex.pipeline_id)
        self.assertEqual(bytes(tex_data), dec_tex)

    def test_fastcdc_chunking_and_deduplication(self):
        # Create a directory with shifted versions of large files
        proj = Path(self.tmpdir) / "game_patch_test"
        proj.mkdir(parents=True, exist_ok=True)

        base_data = os.urandom(3 * 1024 * 1024)
        (proj / "asset_v1.bin").write_bytes(base_data)
        # 53-byte shift (patch insertion)
        (proj / "asset_v2.bin").write_bytes(b"PATCH_HEADER_DATA_12345" + base_data)

        archive = Path(self.tmpdir) / "game_cdc.apx"
        res_comp = compress_archive(str(proj), str(archive), mode=Mode.FAST, block_size=1024*1024, cdc=True)
        self.assertEqual(res_comp["status"], "SUCCESS")

        # Decompress and verify bit-for-bit
        out_dir = Path(self.tmpdir) / "restored_game"
        res_dec = decompress_archive(str(archive), output_dir=str(out_dir))
        self.assertEqual(res_dec["status"], "SUCCESS")

        restored_v1 = out_dir / "game_patch_test" / "asset_v1.bin"
        restored_v2 = out_dir / "game_patch_test" / "asset_v2.bin"
        self.assertEqual(restored_v1.read_bytes(), base_data)
        self.assertEqual(restored_v2.read_bytes(), b"PATCH_HEADER_DATA_12345" + base_data)


if __name__ == "__main__":
    unittest.main()
