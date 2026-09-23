"""
ApexCompress CLI - The Adaptive Tournament Multi-Engine Compression Tool.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

# Force UTF-8 encoding on Windows to prevent UnicodeEncodeError with UI characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from apex.analyzer import analyze_file
from apex.archive import (
    DEFAULT_BLOCK_SIZE,
    DEFAULT_FAST_BLOCK_SIZE,
    FLAG_ENCRYPTED,
    FLAG_RECOVERY,
    MAGIC_HEADER,
    compress_archive,
    decompress_archive,
    read_archive_header,
    repair_archive,
    scan_block_index,
    test_archive,
)
from apex.benchmark import format_bytes, run_benchmark
from apex.completions import generate_completions
from apex.diff import diff_archives, format_diff_report
from apex.engine import Mode
from apex.foreign import (
    extract_foreign,
    is_foreign_archive,
    list_foreign,
    test_foreign,
)

# ANSI Colors
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RED = "\033[31m"
BLUE = "\033[34m"


def print_banner():
    banner = f"""{CYAN}{BOLD}
   ___       ___ ___   ___                          ___  
  / _ \\ ___ / _ \\ \\ \\ / / _ \\ ___  _ __ ___  _ __  / _ \\ 
 / /_\\// _ \\  __/  \\ V / /_\\// _ \\| '_ ` _ \\| '_ \\ \\___/ 
/ /_\\\\|  __/ /_     | |/ /_\\\\|  __/| | | | | | |_) | _   
\\____/ \\___|\\__|    |_|\\____/ \\___||_| |_| |_| .__/ (_)  
                                             |_|         
{RESET}{DIM}  Adaptive Multi-Engine Tournament Compression System v1.3.0{RESET}
"""
    print(banner)


def preprocess_tar_args(argv: List[str]) -> List[str]:
    """
    Translates standard tar-style cluster flags into apex CLI arguments.
    Supports -cvf out.apx src/, -xvf out.apx, -tvf out.apx, -cf - src/, -xf -, -c0f out.apx, etc.
    """
    if len(argv) < 2:
        return argv

    token = argv[1]
    is_dashed = token.startswith("-") and not token.startswith("--")
    raw = token[1:] if is_dashed else token

    # Check characters: must contain at least one of 'c', 'x', 't'
    # and all characters must be in 'cxvt0fzj'
    if not (
        ("c" in raw or "x" in raw or ("t" in raw and (is_dashed or "f" in raw)))
        and all(ch in "cxvt0fzj" for ch in raw)
        and len(raw) >= (1 if is_dashed else 2)
    ):
        return argv

    # Determine action
    if "c" in raw:
        action = "compress"
    elif "x" in raw:
        action = "decompress"
    elif "t" in raw:
        action = "list"
    else:
        return argv

    has_f = "f" in raw
    has_v = "v" in raw
    has_null = "0" in raw

    arg_idx = 2
    archive_arg = None
    if has_f:
        if arg_idx < len(argv):
            archive_arg = argv[arg_idx]
            arg_idx += 1
        else:
            print("Error: Option -f requires an argument.", file=sys.stderr)
            sys.exit(1)

    new_argv = [argv[0], action]

    if action == "compress":
        if archive_arg:
            new_argv.extend(["-o", archive_arg])
        if has_v:
            new_argv.append("-v")
        if has_null:
            new_argv.append("-0")
        new_argv.extend(argv[arg_idx:])
    elif action == "decompress":
        if archive_arg:
            new_argv.append(archive_arg)
        if has_v:
            new_argv.append("-v")
        new_argv.extend(argv[arg_idx:])
    elif action == "list":
        if archive_arg:
            new_argv.append(archive_arg)
        if has_v:
            new_argv.append("-v")
        new_argv.extend(argv[arg_idx:])

    return new_argv


def cmd_compress(args):
    is_null = getattr(args, "null", False)
    paths = None
    source = None

    if is_null:
        null_bytes = sys.stdin.buffer.read()
        path_strs = [p.decode("utf-8", errors="surrogateescape").strip() for p in null_bytes.split(b"\x00") if p.strip()]
        if not path_strs:
            print(f"{RED}Error: No input paths received via stdin null-stream.{RESET}", file=sys.stderr)
            sys.exit(1)
        paths = [str(Path(p).resolve()) for p in path_strs]
    else:
        if not args.target:
            print(f"{RED}Error: Source target or -0 (stdin) must be specified.{RESET}", file=sys.stderr)
            sys.exit(1)
        source = Path(args.target).resolve()
        additional = getattr(args, "additional_targets", [])
        if additional:
            paths = [str(source)] + [str(Path(p).resolve()) for p in additional]
            for p in paths:
                if not Path(p).exists():
                    print(f"{RED}Error: Source target '{p}' does not exist.{RESET}", file=sys.stderr)
                    sys.exit(1)
        else:
            if not source.exists():
                print(f"{RED}Error: Source target '{args.target}' does not exist.{RESET}", file=sys.stderr)
                sys.exit(1)

    if args.output:
        if args.output == "-":
            out_str = "-"
            is_stdout = True
        else:
            out_str = str(Path(args.output).resolve())
            is_stdout = False
    else:
        is_stdout = False
        downloads_dir = Path.home() / "Downloads"
        default_name = source.name if source else "archive"
        if downloads_dir.exists():
            out_str = str(downloads_dir / (default_name + ".apx"))
        else:
            out_str = str((source.parent if source else Path.cwd()) / (default_name + ".apx"))

    out_file = sys.stderr if is_stdout else sys.stdout

    mode_map = {
        "fast": Mode.FAST,
        "balanced": Mode.BALANCED,
        "ultra": Mode.ULTRA,
        "brute": Mode.BRUTE,
    }
    mode = mode_map[args.mode.lower()]

    if args.block_size is not None:
        block_size = int(args.block_size * 1024 * 1024)
        display_block_mb = args.block_size
    else:
        block_size = None
        display_block_mb = 4.0 if mode == Mode.FAST else 2.0

    if not is_stdout and not args.quiet:
        print(f"{BOLD}Compressing:{RESET}  {paths if paths else source}", file=out_file)
        print(f"{BOLD}Destination:{RESET}  {out_str}", file=out_file)
        print(f"{BOLD}Preset Mode:{RESET}  {CYAN}{mode.value.upper()}{RESET} (Block size: {display_block_mb:g} MB)", file=out_file)
        if getattr(args, "base", None):
            print(f"{BOLD}Base Archive:{RESET} {CYAN}{args.base}{RESET}", file=out_file)
        if getattr(args, "exclude", None):
            print(f"{BOLD}Exclusions:{RESET}   {YELLOW}{', '.join(args.exclude)}{RESET}", file=out_file)
        print(f"{DIM}Running tournament optimization across CPU cores...{RESET}\n", file=out_file)

    last_p_time = 0.0
    def on_progress(done_bytes, total_bytes, winner, ratio):
        nonlocal last_p_time
        now = time.monotonic()
        if now - last_p_time < 0.06 and done_bytes < total_bytes:
            return
        last_p_time = now
        pct = (done_bytes / total_bytes * 100.0) if total_bytes > 0 else 100.0
        bar_len = 24
        filled = int(bar_len * (pct / 100.0))
        bar = "█" * filled + "░" * (bar_len - filled)
        out_file.write(
            f"\r{CYAN}[{bar}]{RESET} {pct:5.1f}% | {format_bytes(done_bytes):<9} | Winner: {GREEN}{winner:<32}{RESET} ({ratio:5.2f}x)"
        )
        out_file.flush()

    try:
        res = compress_archive(
            source_path=str(source) if source and not paths else None,
            output_archive_path=out_str,
            mode=mode,
            block_size=block_size,
            password=args.password,
            recovery=args.recovery,
            cdc=getattr(args, "cdc", False),
            progress_callback=on_progress if (not args.quiet and not is_stdout) else None,
            exclude_patterns=getattr(args, "exclude", None),
            base_archive_path=getattr(args, "base", None),
            paths=paths,
        )
    except Exception as e:
        print(f"\n{RED}Compression failed: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet and not is_stdout:
        print("\n", file=out_file)

    if not is_stdout:
        speed_mb = (res["uncompressed_bytes"] / (1024 * 1024)) / res["elapsed"] if res["elapsed"] > 0 else 0.0
        print(f"{BOLD}{GREEN}✓ Compression Complete!{RESET}")
        print("=" * 60)
        print(f"  {BOLD}Original Size:{RESET}    {format_bytes(res['uncompressed_bytes'])}")
        print(f"  {BOLD}Apex Size:{RESET}        {format_bytes(res['compressed_bytes'])}")
        print(f"  {BOLD}Space Saved:{RESET}      {GREEN}{res['space_saved_pct']:.2f}%{RESET}")
        print(f"  {BOLD}Compression Ratio:{RESET}{CYAN}{BOLD} {res['ratio']:.2f}x{RESET}")
        print(f"  {BOLD}Total Blocks:{RESET}     {res['blocks']}")
        if res.get("reused_chunks"):
            print(f"  {BOLD}Reused Chunks:{RESET}    {GREEN}{res['reused_chunks']}{RESET} (incremental deduplication)")
        print(f"  {BOLD}Time Elapsed:{RESET}     {res['elapsed']:.2f}s ({speed_mb:.1f} MB/s)")
        print(f"  {BOLD}Stream SHA-256:{RESET}   {DIM}{res['sha256']}{RESET}")
        if res.get("encrypted"):
            print(f"  {BOLD}Security:{RESET}        {GREEN}Authenticated Encryption (PBKDF2 + ChaCha20/AES + HMAC-SHA256){RESET}")
        if res.get("recovery"):
            print(f"  {BOLD}Self-Healing:{RESET}    {GREEN}Reed-Solomon Parity Records Attached{RESET}")
        print("=" * 60)

        if args.verbose and res.get("block_records"):
            print(f"\n{BOLD}Block Tournament Breakdown:{RESET}")
            print(f"  {'Block':<6} | {'Winner Pipeline':<36} | {'Uncompressed':<12} | {'Compressed':<12} | {'Ratio':<8}")
            print("  " + "-" * 82)
            for b in res["block_records"]:
                print(f"  #{b['block']:<5} | {b['winner']:<36} | {format_bytes(b['uncompressed']):<12} | {format_bytes(b['compressed']):<12} | {b['ratio']:6.2f}x")


def cmd_decompress(args):
    archive_arg = args.archive
    is_stdin = archive_arg == "-"

    if not is_stdin:
        archive_path = Path(archive_arg).resolve()
        if not archive_path.exists():
            print(f"{RED}Error: Archive '{archive_arg}' not found.{RESET}", file=sys.stderr)
            sys.exit(1)
        archive_str = str(archive_path)
    else:
        archive_str = "-"

    patterns = []
    if getattr(args, "include", None):
        patterns.extend(args.include)
    if getattr(args, "files", None):
        patterns.extend(args.files)
    include_patterns = patterns if patterns else None

    dest_dir = getattr(args, "dest", None)

    # Foreign archive handling (zip, tar.gz, tar)
    if not is_stdin and is_foreign_archive(archive_str):
        print(f"{BOLD}Decompressing Foreign Archive:{RESET} {archive_str}")
        if dest_dir:
            print(f"{BOLD}Destination:{RESET}   {dest_dir}")
        if include_patterns:
            print(f"{BOLD}Selective Patterns:{RESET} {CYAN}{', '.join(include_patterns)}{RESET}")
        try:
            res = extract_foreign(
                archive_str,
                output_dir=dest_dir,
                include_patterns=include_patterns,
                quiet=getattr(args, "quiet", False),
            )
        except Exception as e:
            print(f"\n{RED}Foreign extraction error: {e}{RESET}", file=sys.stderr)
            sys.exit(1)
        print(f"\n{BOLD}{GREEN}✓ Decompression Complete!{RESET}")
        print("=" * 60)
        print(f"  {BOLD}Files Restored:{RESET}   {res['files_extracted']:,}")
        print(f"  {BOLD}Extracted Size:{RESET}   {format_bytes(res['total_uncompressed_bytes'])}")
        print(f"  {BOLD}Format:{RESET}           {res['format'].upper()}")
        print(f"  {BOLD}Time Elapsed:{RESET}     {res['elapsed']:.2f}s")
        print("=" * 60)
        return

    if not is_stdin:
        print(f"{BOLD}Decompressing:{RESET} {archive_str}")
    else:
        print(f"{BOLD}Decompressing:{RESET} <stdin>")
    if dest_dir:
        print(f"{BOLD}Destination:{RESET}   {dest_dir}")
    if include_patterns:
        print(f"{BOLD}Selective Patterns:{RESET} {CYAN}{', '.join(include_patterns)}{RESET}")

    def on_progress(done_bytes: int, total_bytes: int, files_done: int):
        pct = (done_bytes / total_bytes * 100.0) if total_bytes > 0 else 100.0
        bar_len = 24
        filled = int(bar_len * (pct / 100.0))
        bar = "█" * filled + "░" * (bar_len - filled)
        sys.stdout.write(
            f"\r{CYAN}[{bar}]{RESET} {pct:5.1f}% | {format_bytes(done_bytes):<9} / {format_bytes(total_bytes):<9} | {files_done:,} files"
        )
        sys.stdout.flush()

    quiet = getattr(args, "quiet", False)
    try:
        res = decompress_archive(
            archive_str,
            output_dir=dest_dir,
            password=args.password,
            include_patterns=include_patterns,
            progress_callback=on_progress if not quiet else None,
        )
    except Exception as e:
        print(f"\n{RED}Decompression error: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    if not quiet:
        print()

    print(f"\n{BOLD}{GREEN}✓ Decompression Complete & Verified!{RESET}")
    print("=" * 60)
    print(f"  {BOLD}Files Restored:{RESET}   {res['files_extracted']:,}")
    print(f"  {BOLD}Extracted Size:{RESET}   {format_bytes(res['total_uncompressed_bytes'])}")
    if res.get("selective"):
        print(f"  {BOLD}Index Selectivity:{RESET}{GREEN} {res['blocks_decoded']} of {res['total_blocks']} blocks decoded ({res['total_blocks'] - res['blocks_decoded']} skipped){RESET}")
    print(f"  {BOLD}Time Elapsed:{RESET}     {res['elapsed']:.2f}s")
    print(f"  {BOLD}Integrity:{RESET}        {GREEN}100% Bit-Exact SHA-256 Verified{RESET}")
    print("=" * 60)


def cmd_diff(args):
    archive1 = Path(args.archive1).resolve()
    archive2 = Path(args.archive2).resolve()
    if not archive1.exists():
        print(f"{RED}Error: First archive '{args.archive1}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)
    if not archive2.exists():
        print(f"{RED}Error: Second archive '{args.archive2}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)

    try:
        res = diff_archives(str(archive1), str(archive2), password=args.password)
    except Exception as e:
        print(f"{RED}Diff error: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
    else:
        print(format_diff_report(res))


def cmd_completions(args):
    try:
        script = generate_completions(args.shell)
        sys.stdout.write(script)
    except Exception as e:
        print(f"{RED}Error generating completions: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def cmd_test(args):
    archive_path = Path(args.archive).resolve()
    if not archive_path.exists():
        print(f"{RED}Error: Archive '{args.archive}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)

    if is_foreign_archive(str(archive_path)):
        print(f"{BOLD}Verifying Foreign Archive:{RESET} {archive_path}")
        try:
            res = test_foreign(str(archive_path))
        except Exception as e:
            print(f"{RED}FAILED: {e}{RESET}", file=sys.stderr)
            sys.exit(1)
        print(f"{BOLD}{GREEN}✓ Foreign Archive Integrity PASSED!{RESET}")
        print(f"  Format:              {res['format'].upper()}")
        print(f"  Files in Manifest:   {res['total_files']}")
        print(f"  Uncompressed Size:   {format_bytes(res['total_uncompressed_bytes'])}")
        print(f"  Validation Time:     {res['elapsed']:.3f}s")
        return

    print(f"{BOLD}Verifying Archive:{RESET} {archive_path}")
    try:
        res = test_archive(str(archive_path), password=args.password)
    except Exception as e:
        print(f"{RED}FAILED: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"{BOLD}{GREEN}✓ Archive Integrity PASSED!{RESET}")
    print(f"  Files in Manifest:   {res['total_files']}")
    print(f"  Uncompressed Size:   {format_bytes(res['total_uncompressed_bytes'])}")
    print(f"  Blocks Verified:     {res['total_blocks']} (all CRC-32 matches)")
    if res.get("encrypted"):
        print(f"  Security:            {GREEN}Authenticated Encryption Verified{RESET}")
    if res.get("has_recovery"):
        print(f"  Self-Healing:        {GREEN}Reed-Solomon Recovery Records Present & Ready{RESET}")
    print(f"  Cryptographic Hash:  {res['sha256']}")
    print(f"  Validation Time:     {res['elapsed']:.3f}s")


def cmd_list(args):
    archive_path = Path(args.archive).resolve()
    if not archive_path.exists():
        print(f"{RED}Error: Archive '{args.archive}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)

    # Check foreign format
    if is_foreign_archive(str(archive_path)):
        list_foreign(str(archive_path), as_json=getattr(args, "json", False), quiet=getattr(args, "quiet", False))
        return

    with open(archive_path, "rb") as f:
        flags, block_size, manifest, enc_key, mac_key = read_archive_header(f, password=args.password)
        blocks_meta = scan_block_index(f, f.tell())

    if getattr(args, "json", False):
        data = {
            "archive": archive_path.name,
            "type": "directory" if manifest.is_dir else "file",
            "block_size": block_size,
            "encrypted": bool(flags & FLAG_ENCRYPTED),
            "recovery": bool(flags & FLAG_RECOVERY),
            "base_archive": manifest.base_archive,
            "reused_chunks": manifest.reused_chunks,
            "total_files": len(manifest.files),
            "total_uncompressed_size": manifest.total_uncompressed_size,
            "files": [
                {
                    "path": fe.rel_path,
                    "size": fe.size,
                    "mode": fe.mode,
                    "mtime": fe.mtime,
                    "is_dir": fe.is_dir,
                    "is_symlink": fe.is_symlink,
                    "block_id": fe.block_id,
                    "offset": fe.offset,
                    "length": fe.length,
                    "solid_offset": fe.solid_offset,
                }
                for fe in manifest.files
            ],
            "blocks": [
                {
                    "block_id": b.block_id,
                    "pipeline_id": b.pipeline_id,
                    "uncompressed_length": b.uncomp_len,
                    "compressed_length": b.comp_len,
                    "crc32": b.crc,
                    "solid_start": b.solid_start,
                    "solid_end": b.solid_end,
                    "ref_idx": b.ref_idx,
                }
                for b in blocks_meta
            ],
        }
        print(json.dumps(data, indent=2))
        return

    print(f"{BOLD}Archive:{RESET}     {archive_path.name}")
    print(f"{BOLD}Type:{RESET}        {'Directory / Solid Archive' if manifest.is_dir else 'Single File'}")
    print(f"{BOLD}Block Size:{RESET}  {block_size // (1024*1024)} MB")
    print(f"{BOLD}Encrypted:{RESET}   {'Yes (Authenticated Encryption: ChaCha20/AES + HMAC-SHA256)' if (flags & FLAG_ENCRYPTED) else 'No'}")
    print(f"{BOLD}Self-Healing:{RESET}{'Yes (Reed-Solomon Parity)' if (flags & FLAG_RECOVERY) else 'No'}")
    if manifest.base_archive:
        print(f"{BOLD}Base Archive:{RESET}{CYAN}{manifest.base_archive}{RESET}")
        print(f"{BOLD}Reused Chunks:{RESET}{GREEN}{manifest.reused_chunks}{RESET}")
    print(f"{BOLD}Total Files:{RESET} {len(manifest.files)}")
    print(f"{BOLD}Total Size:{RESET}  {format_bytes(manifest.total_uncompressed_size)}\n")

    print(f"{'Mode':<10} | {'Size':<12} | {'Modified':<20} | {'Filename':<35}")
    print("-" * 82)
    for f in manifest.files:
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.mtime))
        mode_str = oct(f.mode)[-4:]
        print(f"{mode_str:<10} | {format_bytes(f.size):<12} | {mtime_str:<20} | {f.rel_path}")

    if getattr(args, "verbose", False) and blocks_meta:
        print(f"\n{BOLD}Block Index Breakdown ({len(blocks_meta)} blocks):{RESET}")
        print(f"  {'Block':<6} | {'Pipeline ID':<12} | {'Uncompressed':<14} | {'Compressed':<12} | {'CRC-32':<10}")
        print("  " + "-" * 62)
        for b in blocks_meta:
            print(f"  #{b.block_id:<5} | {b.pipeline_id:<12} | {format_bytes(b.uncomp_len):<14} | {format_bytes(b.comp_len):<12} | {b.crc:08x}")


def cmd_repair(args):
    archive_path = Path(args.archive).resolve()
    if not archive_path.exists():
        print(f"{RED}Error: Archive '{args.archive}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"{BOLD}Self-Healing Recovery Check:{RESET} {archive_path}")
    print(f"{DIM}Scanning blocks and evaluating Reed-Solomon Cauchy parity matrix...{RESET}\n")

    try:
        res = repair_archive(
            str(archive_path),
            output_repaired_path=args.output,
            password=args.password,
        )
    except Exception as e:
        print(f"{RED}Self-healing repair failed: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    if res["status"] == "ALREADY_HEALTHY":
        print(f"{BOLD}{GREEN}✓ Archive is 100% Healthy!{RESET}")
        print("  All CRC-32 checksums and SHA-256 hash matched. No repair needed.")
    elif res["status"] == "SUCCESS_REPAIRED":
        print(f"{BOLD}{GREEN}✓ Archive Successfully Repaired & Restored!{RESET}")
        print("=" * 60)
        print(f"  {BOLD}Original Archive:{RESET} {res['original_archive']}")
        print(f"  {BOLD}Repaired Archive:{RESET} {GREEN}{res['repaired_archive']}{RESET}")
        print(f"  {BOLD}Healed Block:{RESET}     Block #{res['healed_block_index'] + 1} reconstructed bit-for-bit")
        print(f"  {BOLD}Blocks Verified:{RESET}  {res['blocks_verified']}")
        print(f"  {BOLD}Elapsed Time:{RESET}     {res['elapsed']:.3f}s")
        print("=" * 60)


def cmd_benchmark(args):
    file_path = Path(args.file).resolve()
    if not file_path.exists() or not file_path.is_file():
        print(f"{RED}Error: File '{args.file}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)

    size = file_path.stat().st_size
    if getattr(args, "full", False):
        data = file_path.read_bytes()
        print(f"{BOLD}Reading sample from:{RESET} {file_path} ({format_bytes(len(data))}, 100% full dataset)")
    else:
        sample_limit = int(args.max_sample_mb * 1024 * 1024)
        with open(file_path, "rb") as f:
            data = f.read(sample_limit)
        print(f"{BOLD}Reading sample from:{RESET} {file_path} (Sample: {format_bytes(len(data))} / Total: {format_bytes(size)})")

    print(f"{DIM}Running tournament shootout against Gzip, Bzip2, XZ, Zstandard, Brotli...{RESET}\n")
    results = run_benchmark(data)

    print(f"{BOLD}TOURNAMENT BENCHMARK SHOOTOUT{RESET} (Input: {format_bytes(len(data))})")
    print("=" * 96)
    print(f"{'Rank':<5} | {'Engine / Tool':<42} | {'Compressed':<11} | {'Ratio':<9} | {'Saved%':<8} | {'Comp (ms)':<10}")
    print("-" * 96)

    for i, r in enumerate(results, 1):
        if i == 1:
            rank_str = f"{YELLOW}#1   {RESET}"
            name_str = f"{BOLD}{GREEN}{r.engine_name:<42}{RESET}"
        elif i == 2:
            rank_str = f"{CYAN}#2   {RESET}"
            name_str = f"{CYAN}{r.engine_name:<42}{RESET}"
        elif i == 3:
            rank_str = f"{MAGENTA}#3   {RESET}"
            name_str = f"{r.engine_name:<42}"
        else:
            rank_str = f"#{i:<4}"
            name_str = f"{r.engine_name:<42}"

        print(f"{rank_str:<5} | {name_str} | {format_bytes(r.compressed_size):<11} | {r.compression_ratio:6.2f}x  | {r.space_saved_pct:6.2f}% | {r.compression_time_ms:8.2f} ms")

    print("=" * 96)


def cmd_info(args):
    file_path = Path(args.file).resolve()
    if not file_path.exists() or not file_path.is_file():
        print(f"{RED}Error: File '{args.file}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)

    # Check if this is an Apex archive
    is_apx = False
    try:
        with open(file_path, "rb") as f:
            if f.read(8) == MAGIC_HEADER:
                is_apx = True
    except OSError:
        pass

    if is_apx:
        try:
            with open(file_path, "rb") as f:
                flags, block_size, manifest, _, _ = read_archive_header(f, password=getattr(args, "password", None))
                blocks_info = scan_block_index(f, f.tell())
            print(f"{BOLD}Apex Archive Info:{RESET} {file_path}")
            print("=" * 60)
            print(f"  {BOLD}Archive Type:{RESET}        {'Directory / Solid Archive' if manifest.is_dir else 'Single File'}")
            print(f"  {BOLD}Block Size:{RESET}          {block_size // (1024 * 1024)} MB")
            print(f"  {BOLD}Encrypted:{RESET}           {'Yes' if (flags & FLAG_ENCRYPTED) else 'No'}")
            print(f"  {BOLD}Self-Healing:{RESET}        {'Yes' if (flags & FLAG_RECOVERY) else 'No'}")
            print(f"  {BOLD}Total Files:{RESET}         {len(manifest.files)}")
            print(f"  {BOLD}Total Uncompressed:{RESET}  {format_bytes(manifest.total_uncompressed_size)}")
            print(f"  {BOLD}Total Blocks:{RESET}        {len(blocks_info)}")
            if manifest.base_archive:
                print(f"  {BOLD}Base Archive:{RESET}        {CYAN}{manifest.base_archive}{RESET}")
                print(f"  {BOLD}Reused Chunks:{RESET}       {GREEN}{manifest.reused_chunks}{RESET} chunks reused from base")
            print("=" * 60)
            return
        except Exception:
            pass

    print(f"{BOLD}Analyzing Entropy & Information Content:{RESET} {file_path}")
    report = analyze_file(str(file_path))

    print("\n" + "=" * 60)
    print(f"  {BOLD}File Size:{RESET}               {format_bytes(report.total_bytes)} ({report.total_bytes:,} bytes)")
    print(f"  {BOLD}Unique Symbols:{RESET}          {report.unique_bytes} / 256 bytes")
    print(f"  {BOLD}Shannon Entropy H(X):{RESET}    {CYAN}{BOLD}{report.shannon_entropy:.4f}{RESET} bits / byte (Max: 8.0)")
    print(f"  {BOLD}Theoretical Limit:{RESET}       {GREEN}{BOLD}{report.theoretical_max_ratio:.2f}x{RESET} (Min size: {format_bytes(report.theoretical_min_size)})")
    print(f"  {BOLD}Printable ASCII Ratio:{RESET}   {report.ascii_ratio * 100:.1f}%")
    print(f"  {BOLD}Zero / Null Ratio:{RESET}       {report.zero_ratio * 100:.1f}%")
    print(f"  {BOLD}High-Byte Ratio (>127):{RESET} {report.high_byte_ratio * 100:.1f}%")
    print(f"  {BOLD}Data Classification:{RESET}     {YELLOW}{report.classification}{RESET}")
    print(f"  {BOLD}Compressibility Score:{RESET}   {GREEN}{report.compressibility_pct:.1f}%{RESET}")
    print(f"  {BOLD}Recommended Mode:{RESET}        {BOLD}{report.recommended_mode}{RESET}")
    print("=" * 60)


def cmd_mount(args):
    archive_path = Path(args.archive).resolve()
    if not archive_path.exists():
        print(f"{RED}Error: Archive '{args.archive}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)

    from apex.mount import mount_archive

    print(f"{BOLD}Mounting Archive:{RESET} {archive_path}")
    print(f"{BOLD}Mountpoint:{RESET}       {args.mountpoint}")
    print(f"{BOLD}LRU Block Cache:{RESET}  {args.cache_size} MB")
    print(f"{DIM}Press Ctrl+C to unmount.{RESET}\n")

    try:
        mount_archive(
            str(archive_path),
            args.mountpoint,
            password=args.password,
            cache_size_mb=args.cache_size,
            foreground=args.foreground,
        )
    except Exception as e:
        print(f"{RED}Mount error: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def main():
    sys.argv = preprocess_tar_args(sys.argv)

    parser = argparse.ArgumentParser(
        prog="apex",
        description="ApexCompress: The Adaptive Tournament Multi-Engine Compression Tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="version", version="%(prog)s 1.3.0")
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    p_comp = subparsers.add_parser("compress", aliases=["c"], help="Compress a file or folder into an .apx archive (saved to ~/Downloads by default)")
    p_comp.add_argument("target", nargs="?", default=None, help="File or folder to compress")
    p_comp.add_argument("additional_targets", nargs="*", help=argparse.SUPPRESS)
    p_comp.add_argument("-o", "--output", help="Output .apx file path (default: ~/Downloads/<name>.apx, or '-' for stdout)")
    p_comp.add_argument("-m", "--mode", choices=["fast", "balanced", "ultra", "brute"], default="balanced", help="Compression preset")
    p_comp.add_argument("-b", "--block-size", type=float, default=None, help="Block size in megabytes (default: 4 MB for fast, 2 MB for balanced/ultra)")
    p_comp.add_argument("-p", "--password", help="Encrypt archive with AES-256-CTR & HMAC-SHA256")
    p_comp.add_argument("-r", "--recovery", action="store_true", help="Embed Reed-Solomon self-healing parity records")
    p_comp.add_argument("-e", "--exclude", action="append", help="Exclude pattern or folder (e.g. -e '.git' -e 'node_modules' -e '*.tmp')")
    p_comp.add_argument("--cdc", action="store_true", help="Enable Content-Defined Chunking for game patches and delta updates")
    p_comp.add_argument("--base", help="Base archive for incremental compression (reuses matching chunks)")
    p_comp.add_argument("-0", "--null", action="store_true", help="Read input file paths from standard input separated by null characters (from find -print0)")
    p_comp.add_argument("-v", "--verbose", action="store_true", help="Print block-level tournament winners")
    p_comp.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")
    p_comp.set_defaults(func=cmd_compress)

    p_decomp = subparsers.add_parser("decompress", aliases=["x", "extract"], help="Decompress an .apx archive")
    p_decomp.add_argument("archive", help="Path to .apx archive (or '-' for stdin)")
    p_decomp.add_argument("files", nargs="*", help="Specific files or paths to selectively extract")
    p_decomp.add_argument("-d", "-C", "--dest", help="Destination folder or file path")
    p_decomp.add_argument("-p", "--password", help="Password for encrypted archive")
    p_decomp.add_argument("-i", "--include", action="append", help="Include pattern/glob for selective extraction (e.g. -i '*.json')")
    p_decomp.add_argument("-v", "--verbose", action="store_true", help="Verbose extraction")
    p_decomp.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")
    p_decomp.set_defaults(func=cmd_decompress)

    p_diff = subparsers.add_parser("diff", aliases=["d"], help="Compare manifests and contents between two .apx archives")
    p_diff.add_argument("archive1", help="First .apx archive")
    p_diff.add_argument("archive2", help="Second .apx archive")
    p_diff.add_argument("-p", "--password", help="Password if archive is encrypted")
    p_diff.add_argument("--json", action="store_true", help="Output diff as JSON")
    p_diff.set_defaults(func=cmd_diff)

    p_comp_gen = subparsers.add_parser("completions", help="Generate shell completions script (bash, zsh, fish)")
    p_comp_gen.add_argument("shell", choices=["bash", "zsh", "fish"], help="Target shell")
    p_comp_gen.set_defaults(func=cmd_completions)

    p_test = subparsers.add_parser("test", aliases=["t"], help="Test archive integrity without writing to disk")
    p_test.add_argument("archive", help="Path to archive")
    p_test.add_argument("-p", "--password", help="Password for encrypted archive")
    p_test.set_defaults(func=cmd_test)

    p_list = subparsers.add_parser("list", aliases=["l"], help="List contents of an archive")
    p_list.add_argument("archive", help="Path to archive")
    p_list.add_argument("-p", "--password", help="Password for encrypted archive")
    p_list.add_argument("--json", action="store_true", help="Output listing with block and file indices as JSON")
    p_list.add_argument("-v", "--verbose", action="store_true", help="Verbose listing with block index")
    p_list.set_defaults(func=cmd_list)

    p_mount = subparsers.add_parser("mount", help="Mount an .apx archive read-only as a virtual FUSE filesystem")
    p_mount.add_argument("archive", help="Path to .apx archive")
    p_mount.add_argument("mountpoint", help="Target directory to mount archive")
    p_mount.add_argument("-p", "--password", help="Password for encrypted archive")
    p_mount.add_argument("--cache-size", type=int, default=64, help="Block LRU cache size in MB (default: 64 MB)")
    p_mount.add_argument("-f", "--foreground", action="store_true", default=True, help="Run FUSE mount in foreground")
    p_mount.set_defaults(func=cmd_mount)

    p_repair = subparsers.add_parser("repair", aliases=["fix", "heal"], help="Self-heal a damaged .apx archive using recovery parity")
    p_repair.add_argument("archive", help="Path to damaged .apx archive")
    p_repair.add_argument("-o", "--output", help="Output repaired .apx path (default: <name>.repaired.apx)")
    p_repair.add_argument("-p", "--password", help="Password if archive is encrypted")
    p_repair.set_defaults(func=cmd_repair)

    p_bench = subparsers.add_parser("benchmark", aliases=["b"], help="Shootout benchmark against Gzip, Bzip2, XZ, Zstd, Brotli")
    p_bench.add_argument("file", help="File to benchmark")
    p_bench.add_argument("--max-sample-mb", type=float, default=16.0, help="Max sample size to benchmark in MB")
    p_bench.add_argument("--full", action="store_true", help="Benchmark entire file without 16 MB sample limit")
    p_bench.set_defaults(func=cmd_benchmark)

    p_info = subparsers.add_parser("info", aliases=["i"], help="Analyze Shannon entropy and file compressibility (or archive reuse info)")
    p_info.add_argument("file", help="File or archive to analyze")
    p_info.add_argument("-p", "--password", help="Password if archive is encrypted")
    p_info.set_defaults(func=cmd_info)

    if len(sys.argv) == 1:
        print_banner()
        parser.print_help()
        sys.exit(0)

    # Smart auto-detection if user passed a path without specifying a subcommand
    subcommands = {
        "compress", "c", "decompress", "x", "extract",
        "diff", "d", "completions",
        "test", "t", "list", "l", "benchmark", "b", "info", "i",
        "repair", "fix", "heal", "mount",
        "-h", "--help", "-v", "-V", "--version"
    }
    first_arg = sys.argv[1]
    if first_arg not in subcommands and not first_arg.startswith("-"):
        p = Path(first_arg)
        if first_arg.endswith(".apx"):
            sys.argv.insert(1, "decompress")
        elif p.exists():
            sys.argv.insert(1, "compress")

    try:
        args = parser.parse_args()
        if hasattr(args, "func"):
            args.func(args)
        else:
            parser.print_help()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
    except KeyboardInterrupt:
        print(f"\n{RED}Operation cancelled by user.{RESET}", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
