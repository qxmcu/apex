"""
Unit & Integration tests for ApexCompress archive container, manifests, and integrity.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from apex.archive import compress_archive, test_archive, decompress_archive
from apex.engine import Mode


class TestArchive(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_single_file_compression(self):
        p = Path(self.tmpdir) / "single.txt"
        content = "The quick brown fox jumps over the lazy dog.\n" * 1000
        p.write_text(content)

        apx = Path(self.tmpdir) / "single.txt.apx"
        comp_res = compress_archive(str(p), str(apx), mode=Mode.BALANCED)
        self.assertTrue(apx.exists())
        self.assertLess(comp_res["compressed_bytes"], len(content))

        # Test verification
        t_res = test_archive(str(apx))
        self.assertEqual(t_res["status"], "PASSED")

        # Extract
        out_file = Path(self.tmpdir) / "restored.txt"
        dec_res = decompress_archive(str(apx), output_dir=str(out_file))
        self.assertEqual(dec_res["status"], "SUCCESS")
        self.assertEqual(out_file.read_text(), content)

    def test_directory_solid_compression(self):
        root = Path(self.tmpdir) / "my_project"
        root.mkdir()
        (root / "readme.md").write_text("# Project\n" * 200)
        (root / "data.bin").write_bytes(bytes(range(256)) * 50)
        sub = root / "src"
        sub.mkdir()
        (sub / "app.py").write_text("import sys\nprint('hello')\n" * 50)

        apx = Path(self.tmpdir) / "my_project.apx"
        comp_res = compress_archive(str(root), str(apx), mode=Mode.ULTRA)
        self.assertTrue(apx.exists())

        # Verify
        t_res = test_archive(str(apx))
        self.assertEqual(t_res["status"], "PASSED")

        # Decompress into a new directory
        dest = Path(self.tmpdir) / "extracted_project"
        dec_res = decompress_archive(str(apx), output_dir=str(dest))
        self.assertEqual(dec_res["status"], "SUCCESS")

        # Check every file bit-for-bit
        dest_app = dest / "my_project" if (dest / "my_project").exists() else dest
        for orig in root.rglob("*"):
            if orig.is_file():
                rel = orig.relative_to(root)
                restored = dest_app / rel
                self.assertTrue(restored.exists(), f"Missing file: {rel}")
                self.assertEqual(orig.read_bytes(), restored.read_bytes(), f"Mismatch: {rel}")

    def test_corrupted_archive_detection(self):
        p = Path(self.tmpdir) / "important.txt"
        p.write_text("Mission critical secret data that must not be corrupted!" * 100)

        apx = Path(self.tmpdir) / "important.apx"
        compress_archive(str(p), str(apx), mode=Mode.FAST)

        # Intentionally tamper with a byte in the payload
        with open(apx, "r+b") as f:
            f.seek(60) # inside payload
            b = f.read(1)
            f.seek(60)
            f.write(bytes([b[0] ^ 0xFF])) # flip bits

        # Integrity test must raise ValueError
        with self.assertRaises(ValueError):
            test_archive(str(apx))

    def test_readonly_and_overwrite_decompression(self):
        root = Path(self.tmpdir) / "bundle_with_readonly"
        sub = root / "SubDir" / "Nested"
        sub.mkdir(parents=True)

        ro_file = sub / "SystemVersion.plist"
        ro_file.write_text("<plist>version 1.0</plist>")
        os.chmod(ro_file, 0o444)

        normal_file = root / "regular.txt"
        normal_file.write_text("Regular writable file content")

        apx = Path(self.tmpdir) / "bundle.apx"
        compress_archive(str(root), str(apx), mode=Mode.FAST)

        dest = Path(self.tmpdir) / "extracted_bundle"

        # First extraction: extracts read-only file and creates directory structure
        dec1 = decompress_archive(str(apx), output_dir=str(dest))
        self.assertEqual(dec1["status"], "SUCCESS")

        restored_ro = dest / "bundle_with_readonly" / "SubDir" / "Nested" / "SystemVersion.plist"
        self.assertTrue(restored_ro.exists())
        self.assertEqual(restored_ro.read_text(), "<plist>version 1.0</plist>")

        # Second extraction: dest already contains the read-only 0444 file!
        # Must not crash with [Errno 13] Permission denied
        dec2 = decompress_archive(str(apx), output_dir=str(dest))
        self.assertEqual(dec2["status"], "SUCCESS")
        self.assertTrue(restored_ro.exists())
        self.assertEqual(restored_ro.read_text(), "<plist>version 1.0</plist>")


if __name__ == "__main__":
    unittest.main()
