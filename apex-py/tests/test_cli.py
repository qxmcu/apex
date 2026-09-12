"""
CLI End-to-End Tests for ApexCompress.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apex.archive import read_archive_header

APEX_CMD = [sys.executable, "-m", "apex.cli"]


class TestCLI(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_cli_compress_and_extract(self):
        sample = Path(self.tmpdir) / "test.txt"
        sample.write_text("Testing apex command line interface!\n" * 200)

        archive = Path(self.tmpdir) / "test.txt.apx"

        # Compress
        res = subprocess.run(
            APEX_CMD + ["c", str(sample), "-o", str(archive), "-m", "fast"],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, f"apex c failed: {res.stderr}")
        self.assertTrue(archive.exists())

        # List
        res = subprocess.run(
            APEX_CMD + ["l", str(archive)],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, f"apex l failed: {res.stderr}")
        self.assertIn("test.txt", res.stdout)

        # Test
        res = subprocess.run(
            APEX_CMD + ["t", str(archive)],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, f"apex t failed: {res.stderr}")
        self.assertIn("Archive Integrity PASSED", res.stdout)

        # Decompress
        out_dir = Path(self.tmpdir) / "out"
        res = subprocess.run(
            APEX_CMD + ["x", str(archive), "-d", str(out_dir)],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, f"apex x failed: {res.stderr}")
        restored = out_dir / "test.txt"
        self.assertTrue(restored.exists())
        self.assertEqual(restored.read_text(), sample.read_text())

    def test_cli_info(self):
        sample = Path(self.tmpdir) / "info_sample.txt"
        sample.write_text("Hello World\n" * 100)

        res = subprocess.run(
            APEX_CMD + ["i", str(sample)],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, f"apex i failed: {res.stderr}")
        self.assertIn("Shannon Entropy", res.stdout)
        self.assertIn("Theoretical Limit", res.stdout)

    def test_cli_benchmark(self):
        sample = Path(self.tmpdir) / "bench_sample.bin"
        sample.write_bytes(bytes(range(256)) * 10)

        res = subprocess.run(
            APEX_CMD + ["b", str(sample)],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, f"apex b failed: {res.stderr}")
        self.assertIn("TOURNAMENT BENCHMARK SHOOTOUT", res.stdout)

    def test_cli_encryption(self):
        sample = Path(self.tmpdir) / "classified.txt"
        sample.write_text("Top secret confidential payload data!\n" * 50)
        archive = Path(self.tmpdir) / "classified.apx"

        # Compress with -p
        res = subprocess.run(
            APEX_CMD + ["c", str(sample), "-o", str(archive), "-p", "secret123", "-m", "fast"],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, f"apex c -p failed: {res.stderr}")
        self.assertIn("Authenticated Encryption", res.stdout)

        # Test with wrong password -> must fail
        res_fail = subprocess.run(
            APEX_CMD + ["t", str(archive), "-p", "wrongpassword"],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertNotEqual(res_fail.returncode, 0)

        # Test with correct password -> succeeds
        res_test = subprocess.run(
            APEX_CMD + ["t", str(archive), "-p", "secret123"],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res_test.returncode, 0, f"apex t -p failed: {res_test.stderr}")
        self.assertIn("Archive Integrity PASSED", res_test.stdout)

        # Decompress with -p
        out_dir = Path(self.tmpdir) / "extracted_enc"
        res_dec = subprocess.run(
            APEX_CMD + ["x", str(archive), "-d", str(out_dir), "-p", "secret123"],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res_dec.returncode, 0, f"apex x -p failed: {res_dec.stderr}")
        restored = out_dir / "classified.txt"
        self.assertEqual(restored.read_text(), sample.read_text())

    def test_cli_recovery_and_repair(self):
        sample = Path(self.tmpdir) / "photos.dat"
        sample.write_bytes(bytes(range(256)) * 200)
        archive = Path(self.tmpdir) / "photos.apx"
        repaired = Path(self.tmpdir) / "photos_fixed.apx"

        # Compress with -r
        res = subprocess.run(
            APEX_CMD + ["c", str(sample), "-o", str(archive), "-r", "-m", "fast"],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, f"apex c -r failed: {res.stderr}")
        self.assertIn("Reed-Solomon", res.stdout)

        # Corrupt block 0 payload
        with open(archive, "r+b") as f:
            read_archive_header(f)
            # Seek past block 0 header (13 bytes) + 5 bytes into payload
            f.seek(18, os.SEEK_CUR)
            b = f.read(1)
            f.seek(-1, os.SEEK_CUR)
            f.write(bytes([b[0] ^ 0xFF]))

        # Test fails
        res_corrupt = subprocess.run(
            APEX_CMD + ["t", str(archive)],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertNotEqual(res_corrupt.returncode, 0)

        # Repair using apex repair
        res_repair = subprocess.run(
            APEX_CMD + ["repair", str(archive), "-o", str(repaired)],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res_repair.returncode, 0, f"apex repair failed: {res_repair.stderr}")
        self.assertIn("Archive Successfully Repaired", res_repair.stdout)

        # Test repaired archive
        res_fixed_test = subprocess.run(
            APEX_CMD + ["t", str(repaired)],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res_fixed_test.returncode, 0)

        # Decompress repaired archive
        out_dir = Path(self.tmpdir) / "extracted_fixed"
        res_fixed_dec = subprocess.run(
            APEX_CMD + ["x", str(repaired), "-d", str(out_dir)],
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(res_fixed_dec.returncode, 0)
        restored = out_dir / "photos.dat"
        self.assertEqual(restored.read_bytes(), sample.read_bytes())


if __name__ == "__main__":
    unittest.main()
