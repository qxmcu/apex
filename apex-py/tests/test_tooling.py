"""
Unit tests for Apex tooling additions:
- Selective extraction
- Archive diff
- Shell completions
- Python SDK API
- In-memory buffer compression/decompression
"""

import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import apex
from apex.archive import compress_archive, decompress_archive
from apex.completions import generate_completions
from apex.diff import diff_archives, format_diff_report
from apex.engine import Mode


class TestTooling(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="apex_test_tooling_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_selective_extraction_directory(self):
        # Create a directory with multiple files of different extensions
        src_dir = os.path.join(self.test_dir, "sample_dir")
        os.makedirs(os.path.join(src_dir, "subfolder"), exist_ok=True)

        with open(os.path.join(src_dir, "data.json"), "w") as f:
            f.write('{"key": "value", "count": 100}')
        with open(os.path.join(src_dir, "notes.txt"), "w") as f:
            f.write("Some human readable text notes here.")
        with open(os.path.join(src_dir, "subfolder", "config.json"), "w") as f:
            f.write('{"debug": true, "port": 8080}')
        with open(os.path.join(src_dir, "subfolder", "binary.dat"), "wb") as f:
            f.write(b"\x00\x01\x02\x03" * 500)

        apx_file = os.path.join(self.test_dir, "archive.apx")
        compress_archive(src_dir, apx_file, mode=Mode.FAST)

        # 1. Selective extract only *.json
        out_dir = os.path.join(self.test_dir, "out_json")
        res = decompress_archive(apx_file, output_dir=out_dir, include_patterns=["*.json"])
        self.assertEqual(res["status"], "SUCCESS")

        extracted_files = []
        for root, _, files in os.walk(out_dir):
            for file in files:
                extracted_files.append(os.path.relpath(os.path.join(root, file), out_dir))

        self.assertIn(os.path.join("sample_dir", "data.json"), extracted_files)
        self.assertIn(os.path.join("sample_dir", "subfolder", "config.json"), extracted_files)
        self.assertNotIn(os.path.join("sample_dir", "notes.txt"), extracted_files)
        self.assertNotIn(os.path.join("sample_dir", "subfolder", "binary.dat"), extracted_files)

        # Verify content of extracted file
        with open(os.path.join(out_dir, "sample_dir", "data.json"), "r") as f:
            self.assertEqual(f.read(), '{"key": "value", "count": 100}')

        # 2. Selective extract specific path
        out_single = os.path.join(self.test_dir, "out_single")
        res_single = decompress_archive(
            apx_file, output_dir=out_single, include_patterns=["notes.txt"]
        )
        self.assertEqual(res_single["status"], "SUCCESS")
        with open(os.path.join(out_single, "sample_dir", "notes.txt"), "r") as f:
            self.assertEqual(f.read(), "Some human readable text notes here.")
        self.assertFalse(os.path.exists(os.path.join(out_single, "sample_dir", "data.json")))

    def test_diff_archives(self):
        # Create dir 1
        d1 = os.path.join(self.test_dir, "d1")
        os.makedirs(d1, exist_ok=True)
        with open(os.path.join(d1, "file_a.txt"), "w") as f:
            f.write("Version 1 content")
        with open(os.path.join(d1, "file_b.txt"), "w") as f:
            f.write("Will be deleted")

        # Create dir 2
        d2 = os.path.join(self.test_dir, "d2")
        os.makedirs(d2, exist_ok=True)
        with open(os.path.join(d2, "file_a.txt"), "w") as f:
            f.write("Version 2 updated content that is longer")
        with open(os.path.join(d2, "file_c.txt"), "w") as f:
            f.write("Newly added file!")

        apx1 = os.path.join(self.test_dir, "v1.apx")
        apx2 = os.path.join(self.test_dir, "v2.apx")

        compress_archive(d1, apx1, mode=Mode.FAST)
        compress_archive(d2, apx2, mode=Mode.FAST)

        # Diff v1 with v1 -> identical
        same_diff = diff_archives(apx1, apx1)
        self.assertTrue(same_diff["identical"])
        self.assertEqual(len(same_diff["added"]), 0)
        self.assertEqual(len(same_diff["removed"]), 0)

        # Diff v1 with v2
        diff_res = diff_archives(apx1, apx2)
        self.assertFalse(diff_res["identical"])
        self.assertEqual(len(diff_res["added"]), 1)
        self.assertEqual(diff_res["added"][0]["path"], "file_c.txt")

        self.assertEqual(len(diff_res["removed"]), 1)
        self.assertEqual(diff_res["removed"][0]["path"], "file_b.txt")

        self.assertEqual(len(diff_res["modified"]), 1)
        self.assertEqual(diff_res["modified"][0]["path"], "file_a.txt")
        self.assertGreater(diff_res["modified"][0]["size_diff"], 0)

        report = format_diff_report(diff_res, color=False)
        self.assertIn("+ file_c.txt", report)
        self.assertIn("- file_b.txt", report)
        self.assertIn("~ file_a.txt", report)

    def test_completions(self):
        bash = generate_completions("bash")
        self.assertIn("_apex_completions()", bash)
        self.assertIn("complete -F _apex_completions apex", bash)

        zsh = generate_completions("zsh")
        self.assertIn("#compdef apex", zsh)
        self.assertIn("compress:Compress", zsh)

        fish = generate_completions("fish")
        self.assertIn("complete -f -c apex", fish)

        with self.assertRaises(ValueError):
            generate_completions("powershell_unsupported")

    def test_python_sdk_api(self):
        # 1. SDK version
        self.assertEqual(apex.__version__, "1.2.0")

        # 2. File compression & extraction via SDK
        txt_path = os.path.join(self.test_dir, "sdk_input.txt")
        with open(txt_path, "w") as f:
            f.write("Testing the high-level Python API for ApexCompress!")

        archive_path = os.path.join(self.test_dir, "sdk.apx")
        c_res = apex.compress(txt_path, archive_path, mode="fast")
        self.assertIn("sha256", c_res)

        # 3. Test integrity via SDK
        t_res = apex.test(archive_path)
        self.assertEqual(t_res["status"], "PASSED")

        # 4. Extract via SDK
        out_sdk = os.path.join(self.test_dir, "out_sdk")
        e_res = apex.extract(archive_path, out_sdk)
        self.assertEqual(e_res["status"], "SUCCESS")

        out_txt = os.path.join(out_sdk, "sdk_input.txt")
        with open(out_txt, "r") as f:
            self.assertEqual(f.read(), "Testing the high-level Python API for ApexCompress!")

        # 5. Info via SDK
        info_res = apex.info(txt_path)
        self.assertGreater(info_res.shannon_entropy, 0.0)

        # 6. In-memory buffer compression & decompression
        raw_payload = b"Hello ApexCompress in-memory buffers! " * 200
        compressed_buf = apex.compress_bytes(raw_payload, mode="fast")
        self.assertLess(len(compressed_buf), len(raw_payload))

        decompressed_buf = apex.decompress_bytes(compressed_buf)
        self.assertEqual(decompressed_buf, raw_payload)

        # Empty buffer
        self.assertEqual(apex.decompress_bytes(apex.compress_bytes(b"")), b"")


if __name__ == "__main__":
    unittest.main()
