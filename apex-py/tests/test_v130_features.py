"""
Unit and Integration Tests for Apex 1.3.0 Features:
- Indexed member storage & selective block decoding
- Clustered Tar flags (-cvf, -xvf, -tvf, -c0f) & Unix pipes (-cf -, -xf -)
- Foreign archive support (ZIP, TAR.GZ) & repair rejection
- Standalone incremental compression (--base) & reuse telemetry
- FUSE virtual filesystem (ApexArchiveFS & BlockLRUCache)
- Atomic write protection & exclusion filtering
- Machine-readable JSON listing with block indices
"""

import gzip
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

import apex
from apex.archive import (
    DEFAULT_BLOCK_SIZE,
    FLAG_ENCRYPTED,
    compress_archive,
    decompress_archive,
    read_archive_header,
    repair_archive,
    scan_block_index,
    test_archive,
)
from apex.foreign import (
    extract_foreign,
    is_foreign_archive,
    list_foreign,
    test_foreign,
)
from apex.mount import ApexArchiveFS, BlockLRUCache

APEX_CMD = [sys.executable, "-m", "apex.cli"]


class TestV130Features(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src_dir = Path(self.tmpdir) / "source_tree"
        self.src_dir.mkdir(parents=True, exist_ok=True)

        # Create multiple distinct files
        for i in range(10):
            p = self.src_dir / f"file_{i:02d}.txt"
            p.write_text(f"File {i} unique content payload block data.\n" * 500)

        # Create a nested directory with data
        nested = self.src_dir / "nested" / "sub"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "deep.json").write_text('{"nested": true, "key": "value"}')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_block_indexing_and_selective_extraction(self):
        """Single-file extraction decodes ONLY intersecting blocks, skipping unused blocks."""
        archive_p = Path(self.tmpdir) / "indexed.apx"
        # Use small 64 KB block size to ensure multiple blocks are created
        compress_archive(
            str(self.src_dir),
            str(archive_p),
            block_size=64 * 1024,
            mode=apex.Mode.FAST,
        )
        self.assertTrue(archive_p.exists())

        # Inspect block index
        with open(archive_p, "rb") as f:
            flags, bsize, manifest, _, _ = read_archive_header(f)
            blocks_meta = scan_block_index(f, f.tell())

        self.assertGreater(len(blocks_meta), 3, "Expected multiple blocks in test archive")

        # Verify manifest files store block_id, offset, length, solid_offset
        for fe in manifest.files:
            if not fe.is_dir and not fe.is_symlink:
                self.assertIsNotNone(fe.block_id)
                self.assertGreaterEqual(fe.solid_offset, 0)
                self.assertEqual(fe.length, fe.size)

        # Extract only file_00.txt
        out_single = Path(self.tmpdir) / "out_single"
        res = decompress_archive(
            str(archive_p),
            output_dir=str(out_single),
            include_patterns=["file_00.txt"],
        )

        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res.get("selective"))
        self.assertLess(res["blocks_decoded"], res["total_blocks"])
        self.assertTrue((out_single / "file_00.txt").exists())
        self.assertEqual(
            (out_single / "file_00.txt").read_text(),
            (self.src_dir / "file_00.txt").read_text(),
        )
        # Verify unselected files were not extracted
        self.assertFalse((out_single / "file_09.txt").exists())

    def test_pipe_round_trip(self):
        """apex -cf - | apex -xf - streams archive correctly through pipes without seeking."""
        # 1. Compress to stdout pipe
        comp_proc = subprocess.Popen(
            APEX_CMD + ["-cf", "-", str(self.src_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 2. Decompress from stdin pipe
        out_pipe = Path(self.tmpdir) / "out_pipe"
        decomp_proc = subprocess.Popen(
            APEX_CMD + ["-xf", "-", "-d", str(out_pipe)],
            stdin=comp_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        comp_proc.stdout.close()
        decomp_out, decomp_err = decomp_proc.communicate()
        comp_out, comp_err = comp_proc.communicate()

        self.assertEqual(comp_proc.returncode, 0, f"Compression pipe failed: {comp_err.decode()}")
        self.assertEqual(decomp_proc.returncode, 0, f"Decompression pipe failed: {decomp_err.decode()}")

        # Verify extracted contents bit-for-bit
        rest_base = out_pipe / self.src_dir.name if (out_pipe / self.src_dir.name).exists() else out_pipe
        for i in range(10):
            orig = (self.src_dir / f"file_{i:02d}.txt").read_text()
            rest = (rest_base / f"file_{i:02d}.txt").read_text()
            self.assertEqual(orig, rest)

    def test_foreign_archive_zip(self):
        """Transparent inspection and extraction for ZIP format."""
        zip_path = Path(self.tmpdir) / "test_foreign.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("hello.txt", "Hello from ZIP container!")
            z.writestr("sub/config.json", '{"zip": true}')

        self.assertEqual(is_foreign_archive(zip_path), "zip")

        # Test listing
        listing = list_foreign(str(zip_path), quiet=True)
        self.assertEqual(listing["total_files"], 2)
        paths = [f["path"] for f in listing["files"]]
        self.assertIn("hello.txt", paths)

        # Test integrity
        t_res = test_foreign(str(zip_path))
        self.assertEqual(t_res["status"], "PASSED")

        # Test extraction
        out_zip = Path(self.tmpdir) / "out_zip"
        x_res = extract_foreign(str(zip_path), output_dir=str(out_zip))
        self.assertEqual(x_res["status"], "SUCCESS")
        self.assertTrue((out_zip / "hello.txt").exists())
        self.assertEqual((out_zip / "hello.txt").read_text(), "Hello from ZIP container!")

        # Test CLI dispatch on foreign zip
        res_cli_l = subprocess.run(
            APEX_CMD + ["l", str(zip_path)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_cli_l.returncode, 0)
        self.assertIn("hello.txt", res_cli_l.stdout)

        # Test repair rejection on foreign archive
        with self.assertRaises(ValueError):
            repair_archive(str(zip_path))

    def test_foreign_archive_targz(self):
        """Transparent inspection and extraction for TAR.GZ format."""
        targz_path = Path(self.tmpdir) / "test_foreign.tar.gz"
        with tarfile.open(targz_path, "w:gz") as t:
            data = b"Tarball payload sample"
            ti = tarfile.TarInfo("docs/readme.txt")
            ti.size = len(data)
            ti.mtime = 1700000000
            t.addfile(ti, io.BytesIO(data))

        self.assertEqual(is_foreign_archive(targz_path), "tar_gz")

        # Test listing
        listing = list_foreign(str(targz_path), quiet=True)
        self.assertEqual(listing["total_files"], 1)

        # Test extraction
        out_tar = Path(self.tmpdir) / "out_tar"
        x_res = extract_foreign(str(targz_path), output_dir=str(out_tar))
        self.assertEqual(x_res["status"], "SUCCESS")
        self.assertTrue((out_tar / "docs/readme.txt").exists())
        self.assertEqual((out_tar / "docs/readme.txt").read_bytes(), b"Tarball payload sample")

        # Test repair rejection
        with self.assertRaises(ValueError):
            repair_archive(str(targz_path))

    def test_incremental_base_compression_and_standalone_extract(self):
        """Incremental compression with --base reuses compressed blocks and extracts standalone."""
        # 1. Day 1 Archive
        day1_dir = Path(self.tmpdir) / "day1"
        day1_dir.mkdir()
        (day1_dir / "unchanged_large.bin").write_bytes(b"A" * (256 * 1024))
        (day1_dir / "mod.txt").write_text("Day 1 version of file.")

        day1_apx = Path(self.tmpdir) / "day1.apx"
        compress_archive(str(day1_dir), str(day1_apx), block_size=64 * 1024, mode=apex.Mode.FAST)

        # 2. Day 2 Archive with --base day1.apx
        day2_dir = Path(self.tmpdir) / "day2"
        day2_dir.mkdir()
        (day2_dir / "unchanged_large.bin").write_bytes(b"A" * (256 * 1024))  # identical
        (day2_dir / "mod.txt").write_text("Day 2 modified contents!")       # changed
        (day2_dir / "brand_new.txt").write_text("Brand new file on day 2")  # new

        day2_apx = Path(self.tmpdir) / "day2.apx"
        res = compress_archive(
            str(day2_dir),
            str(day2_apx),
            block_size=64 * 1024,
            mode=apex.Mode.FAST,
            base_archive_path=str(day1_apx),
        )

        self.assertGreater(res["reused_chunks"], 0, "Expected reused chunks from base archive")

        # 3. Permanently remove day1.apx to verify day2 is 100% standalone
        day1_apx.unlink()
        self.assertFalse(day1_apx.exists())

        # 4. Decompress day2.apx without day1 present
        out_day2 = Path(self.tmpdir) / "out_day2"
        dec_res = decompress_archive(str(day2_apx), output_dir=str(out_day2))
        self.assertEqual(dec_res["status"], "SUCCESS")
        day2_base = out_day2 / "day2" if (out_day2 / "day2").exists() else out_day2
        self.assertEqual(
            (day2_base / "unchanged_large.bin").read_bytes(),
            b"A" * (256 * 1024),
        )
        self.assertEqual((day2_base / "mod.txt").read_text(), "Day 2 modified contents!")
        self.assertEqual((day2_base / "brand_new.txt").read_text(), "Brand new file on day 2")

        # 5. Verify apex info prints reuse count
        info_res = subprocess.run(
            APEX_CMD + ["info", str(day2_apx)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(info_res.returncode, 0)
        self.assertIn("Base Archive:", info_res.stdout)
        self.assertIn("Reused Chunks:", info_res.stdout)

    def test_tar_flags_and_find_print0(self):
        """Tar flag syntax: -cvf, -xvf, -tvf, and -c0f from find -print0."""
        archive_tar = Path(self.tmpdir) / "tar_flags.apx"

        # 1. -cvf out.apx src/
        c_res = subprocess.run(
            APEX_CMD + ["-cvf", str(archive_tar), str(self.src_dir)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(c_res.returncode, 0, f"-cvf failed: {c_res.stderr}")
        self.assertTrue(archive_tar.exists())

        # 2. -tvf out.apx
        t_res = subprocess.run(
            APEX_CMD + ["-tvf", str(archive_tar)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(t_res.returncode, 0)
        self.assertIn("file_00.txt", t_res.stdout)

        # 3. -xvf out.apx -C dest/
        out_xvf = Path(self.tmpdir) / "out_xvf"
        x_res = subprocess.run(
            APEX_CMD + ["-xvf", str(archive_tar), "-C", str(out_xvf)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(x_res.returncode, 0, f"-xvf failed: {x_res.stderr}")
        self.assertTrue((out_xvf / self.src_dir.name / "file_00.txt").exists() or (out_xvf / "file_00.txt").exists())

        # 4. -c0f from find -print0 (null-delimited input paths)
        archive_null = Path(self.tmpdir) / "null_stream.apx"
        files_to_pack = [
            str(self.src_dir / "file_01.txt"),
            str(self.src_dir / "file_02.txt"),
        ]
        stdin_null_bytes = "\x00".join(files_to_pack).encode("utf-8") + b"\x00"

        null_proc = subprocess.run(
            APEX_CMD + ["-c0f", str(archive_null)],
            input=stdin_null_bytes,
            capture_output=True,
        )
        self.assertEqual(null_proc.returncode, 0, f"-c0f failed: {null_proc.stderr.decode()}")
        self.assertTrue(archive_null.exists())

        # Test listing null archive
        null_l = subprocess.run(
            APEX_CMD + ["l", str(archive_null)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(null_l.returncode, 0)
        self.assertIn("file_01.txt", null_l.stdout)
        self.assertIn("file_02.txt", null_l.stdout)

    def test_list_json_schema(self):
        """apex list --json outputs complete manifest and block index schema."""
        archive_p = Path(self.tmpdir) / "json_test.apx"
        compress_archive(str(self.src_dir), str(archive_p), block_size=64 * 1024, mode=apex.Mode.FAST)

        res = subprocess.run(
            APEX_CMD + ["list", str(archive_p), "--json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)

        self.assertEqual(data["archive"], archive_p.name)
        self.assertIn("blocks", data)
        self.assertIn("files", data)
        self.assertGreater(len(data["blocks"]), 0)
        self.assertGreater(len(data["files"]), 0)

        # Verify block fields
        b0 = data["blocks"][0]
        self.assertIn("block_id", b0)
        self.assertIn("pipeline_id", b0)
        self.assertIn("uncompressed_length", b0)
        self.assertIn("compressed_length", b0)
        self.assertIn("crc32", b0)
        self.assertIn("solid_start", b0)
        self.assertIn("solid_end", b0)

        # Verify file fields
        f0 = data["files"][0]
        self.assertIn("path", f0)
        self.assertIn("size", f0)
        self.assertIn("block_id", f0)
        self.assertIn("solid_offset", f0)

    def test_fuse_mount_virtual_fs(self):
        """Direct unit testing of ApexArchiveFS and BlockLRUCache (read-only virtual filesystem)."""
        archive_p = Path(self.tmpdir) / "fuse_test.apx"
        compress_archive(str(self.src_dir), str(archive_p), block_size=64 * 1024, mode=apex.Mode.FAST)

        # 1. Test BlockLRUCache
        cache = BlockLRUCache(max_bytes=128 * 1024)
        cache.put(0, b"X" * (64 * 1024))
        self.assertEqual(cache.get(0), b"X" * (64 * 1024))
        cache.put(1, b"Y" * (64 * 1024))
        # Adding a 3rd should evict block 0
        cache.put(2, b"Z" * (64 * 1024))
        self.assertIsNone(cache.get(0))
        self.assertEqual(cache.get(2), b"Z" * (64 * 1024))

        # 2. Test ApexArchiveFS operations
        fs = ApexArchiveFS(str(archive_p))

        # getattr root directory
        root_stat = fs.getattr("/")
        self.assertTrue(root_stat["st_mode"] & 0o040000)  # S_IFDIR

        # readdir
        entries = fs.readdir("/")
        self.assertIn(".", entries)
        self.assertIn("..", entries)
        self.assertIn("file_00.txt", entries)

        # getattr regular file
        f_stat = fs.getattr("/file_00.txt")
        self.assertTrue(f_stat["st_mode"] & 0o100000)  # S_IFREG
        orig_content = (self.src_dir / "file_00.txt").read_bytes()
        self.assertEqual(f_stat["st_size"], len(orig_content))

        # read file slices
        read_all = fs.read("/file_00.txt", len(orig_content), 0)
        self.assertEqual(read_all, orig_content)

        read_slice = fs.read("/file_00.txt", 20, 10)
        self.assertEqual(read_slice, orig_content[10:30])

        # Read-only enforcement
        with self.assertRaises(OSError):
            fs.write("/file_00.txt", b"new", 0)
        with self.assertRaises(OSError):
            fs.unlink("/file_00.txt")
        with self.assertRaises(OSError):
            fs.mkdir("/new_dir")

    def test_atomic_write_leaves_dest_intact_on_failure(self):
        """If compression fails or is aborted before completion, destination is untouched."""
        dest_p = Path(self.tmpdir) / "safe_destination.apx"
        original_bytes = b"PRE-EXISTING VALUABLE DATA"
        dest_p.write_bytes(original_bytes)

        # Attempt to compress non-existent source
        with self.assertRaises(Exception):
            compress_archive(
                source_path=str(Path(self.tmpdir) / "does_not_exist"),
                output_archive_path=str(dest_p),
            )

        # Verify pre-existing destination was NOT overwritten or damaged
        self.assertTrue(dest_p.exists())
        self.assertEqual(dest_p.read_bytes(), original_bytes)

    def test_exclude_directory_and_patterns(self):
        """--exclude skips directories and files as expected."""
        git_dir = self.src_dir / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main")
        (self.src_dir / "ignore_me.tmp").write_text("temporary")

        archive_p = Path(self.tmpdir) / "excluded.apx"
        compress_archive(
            str(self.src_dir),
            str(archive_p),
            exclude_patterns=[".git", "*.tmp"],
            mode=apex.Mode.FAST,
        )

        with open(archive_p, "rb") as f:
            _, _, manifest, _, _ = read_archive_header(f)

        paths = [f.rel_path for f in manifest.files]
        self.assertFalse(any(".git" in p for p in paths), f".git was not excluded: {paths}")
        self.assertFalse(any("ignore_me.tmp" in p for p in paths), f"*.tmp was not excluded: {paths}")
        self.assertTrue(any("file_00.txt" in p for p in paths))


if __name__ == "__main__":
    unittest.main()
