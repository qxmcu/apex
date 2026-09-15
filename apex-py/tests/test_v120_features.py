"""
Unit tests for ApexCompress v1.2.0 features:
- Skip pipeline / directory exclusion (--exclude / -e)
- Atomic archive writing (sibling temp file + replace)
- Atomic extraction with clean rollback on corruption
- FastCDC Gear hash content-defined chunking
- BLAKE2b collision-proof deduplication
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from apex.archive import (
    compress_archive,
    decompress_archive,
    read_archive_header,
    test_archive,
    should_exclude,
)
from apex.engine import Mode
from apex.fastcdc import fastcdc_chunk_stream, GEAR_TABLE


class TestV120Features(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="apex_v120_test_")
        self.work_path = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_should_exclude(self):
        patterns = [".git", "node_modules", "*.tmp", "cache/*"]
        self.assertTrue(should_exclude(".git", ".git", True, patterns))
        self.assertTrue(should_exclude("project/.git/HEAD", "HEAD", False, patterns))
        self.assertTrue(should_exclude("node_modules/lib/pkg.json", "pkg.json", False, patterns))
        self.assertTrue(should_exclude("data/scratch.tmp", "scratch.tmp", False, patterns))
        self.assertTrue(should_exclude("cache/index.bin", "index.bin", False, patterns))
        self.assertFalse(should_exclude("src/main.py", "main.py", False, patterns))
        self.assertFalse(should_exclude("docs/README.md", "README.md", False, patterns))

    def test_exclude_compression_and_extraction(self):
        # Setup folder structure
        repo = self.work_path / "my_repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / ".git" / "config").write_text("git config here")
        (repo / "node_modules").mkdir()
        (repo / "node_modules" / "test.js").write_text("console.log('dep')")
        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("print('hello world')")
        (repo / "build.tmp").write_text("temp data")

        archive_path = self.work_path / "repo.apx"
        res = compress_archive(
            str(repo),
            str(archive_path),
            mode=Mode.FAST,
            exclude_patterns=[".git", "node_modules", "*.tmp"],
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(archive_path.exists())

        # Inspect manifest
        with open(archive_path, "rb") as f:
            _, _, manifest, _, _ = read_archive_header(f)

        manifest_paths = [f.rel_path.replace(os.sep, "/") for f in manifest.files]
        self.assertIn("src/app.py", manifest_paths)
        for p in manifest_paths:
            self.assertFalse(".git" in p, f"Excluded .git found in manifest: {p}")
            self.assertFalse("node_modules" in p, f"Excluded node_modules found in manifest: {p}")
            self.assertFalse(p.endswith(".tmp"), f"Excluded .tmp found in manifest: {p}")

        # Decompress to dest and verify
        dest_dir = self.work_path / "extracted"
        decomp_res = decompress_archive(str(archive_path), output_dir=str(dest_dir))
        self.assertEqual(decomp_res["status"], "SUCCESS")

        root_out = dest_dir / "my_repo"
        self.assertTrue((root_out / "src" / "app.py").exists())
        self.assertFalse((root_out / ".git").exists())
        self.assertFalse((root_out / "node_modules").exists())
        self.assertFalse((root_out / "build.tmp").exists())

    def test_atomic_archive_creation(self):
        data_file = self.work_path / "data.bin"
        data_file.write_bytes(b"A" * 100000)

        out_apx = self.work_path / "out.apx"
        out_apx.write_text("old archive content")

        res = compress_archive(str(data_file), str(out_apx), mode=Mode.FAST)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(out_apx.exists())
        self.assertEqual(out_apx.read_bytes()[:4], b"APEX")

    def test_atomic_decompression_rollback_on_corruption(self):
        src_dir = self.work_path / "atomic_src"
        src_dir.mkdir()
        (src_dir / "file1.txt").write_text("original valid content 1")
        (src_dir / "file2.txt").write_text("original valid content 2")

        arc = self.work_path / "corrupt_test.apx"
        compress_archive(str(src_dir), str(arc), mode=Mode.FAST)

        raw_arc = bytearray(arc.read_bytes())
        raw_arc[len(raw_arc) // 2] ^= 0xFF
        arc.write_bytes(raw_arc)

        dest_dir = self.work_path / "clean_dest"
        dest_dir.mkdir()
        canary_file = dest_dir / "canary.txt"
        canary_file.write_text("must survive")

        with self.assertRaises(Exception):
            decompress_archive(str(arc), output_dir=str(dest_dir))

        self.assertTrue(canary_file.exists())
        self.assertEqual(canary_file.read_text(), "must survive")
        staging_items = [p.name for p in dest_dir.parent.glob(".*staging*")]
        self.assertEqual(len(staging_items), 0)

    def test_fastcdc_chunking(self):
        self.assertEqual(len(GEAR_TABLE), 256)
        chunk_pattern = b"0123456789abcdef" * 65536
        stream = [chunk_pattern[:500000], chunk_pattern[500000:]]

        chunks = list(fastcdc_chunk_stream(stream, min_chunk=64 * 1024, avg_chunk=128 * 1024, max_chunk=256 * 1024))
        self.assertTrue(len(chunks) > 1)
        total_reconstructed = b"".join(chunks)
        self.assertEqual(total_reconstructed, chunk_pattern)

    def test_blake2b_deduplication(self):
        data_block = b"REPEAT_BLOCK_APEX_TEST_" * 50000
        combined = data_block + data_block + data_block
        test_file = self.work_path / "dedup_test.bin"
        test_file.write_bytes(combined)

        out_apx = self.work_path / "dedup.apx"
        res = compress_archive(str(test_file), str(out_apx), mode=Mode.FAST, block_size=len(data_block))

        winners = [b["winner"] for b in res["block_records"]]
        self.assertTrue(any("Deduplicated" in w for w in winners), f"Expected deduplication in winners: {winners}")

        decomp = self.work_path / "dedup_out"
        decompress_archive(str(out_apx), output_dir=str(decomp))
        restored = (decomp / "dedup_test.bin").read_bytes()
        self.assertEqual(restored, combined)

    def test_cli_exclude_flag(self):
        import subprocess
        # Create folder
        test_dir = self.work_path / "cli_exclude_src"
        test_dir.mkdir()
        (test_dir / "keep.txt").write_text("keep this")
        (test_dir / ".git").mkdir()
        (test_dir / ".git" / "index").write_text("git index")
        (test_dir / "ignore.tmp").write_text("ignore this")

        out_arc = self.work_path / "cli_exclude.apx"
        cmd = [
            sys.executable, "-m", "apex.cli", "compress",
            str(test_dir), "-o", str(out_arc),
            "-e", ".git", "-e", "*.tmp", "-q"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=f"src:apex-py:{os.environ.get('PYTHONPATH', '')}"))
        self.assertEqual(result.returncode, 0, f"CLI compress failed: {result.stderr}")
        self.assertTrue(out_arc.exists())

        # Verify manifest
        with open(out_arc, "rb") as f:
            _, _, manifest, _, _ = read_archive_header(f)
        paths = [f.rel_path.replace(os.sep, "/") for f in manifest.files]
        self.assertIn("keep.txt", paths)
        self.assertFalse(any(".git" in p or p.endswith(".tmp") for p in paths))

    def test_cli_benchmark_full(self):
        import subprocess
        sample = self.work_path / "bench_sample.bin"
        sample.write_bytes(b"HELLO_BENCHMARK_TEST_" * 1000)

        cmd = [
            sys.executable, "-m", "apex.cli", "benchmark",
            str(sample), "--full"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=f"src:apex-py:{os.environ.get('PYTHONPATH', '')}"))
        self.assertEqual(result.returncode, 0, f"CLI benchmark failed: {result.stderr}")
        self.assertIn("TOURNAMENT BENCHMARK SHOOTOUT", result.stdout)
        self.assertIn("100% full dataset", result.stdout)


if __name__ == '__main__':
    unittest.main()

