"""
ApexCompress CLI - The Adaptive Tournament Multi-Engine Compression Tool.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

from apex.analyzer import analyze_file
from apex.archive import (
    DEFAULT_BLOCK_SIZE,
    FLAG_ENCRYPTED,
    FLAG_RECOVERY,
    compress_archive,
    decompress_archive,
    read_archive_header,
    repair_archive,
    test_archive,
)
from apex.benchmark import format_bytes, run_benchmark
from apex.engine import Mode

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
{RESET}{DIM}  Adaptive Multi-Engine Tournament Compression System v1.0.0{RESET}
"""
    print(banner)


def cmd_compress(args):
    source = Path(args.target).resolve()
    if not source.exists():
        print(f"{RED}Error: Source target '{args.target}' does not exist.{RESET}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        out_path = Path(args.output).resolve()
    else:
        downloads_dir = Path.home() / "Downloads"
        if downloads_dir.exists():
            out_path = downloads_dir / (source.name + ".apx")
        else:
            out_path = source.with_name(source.name + ".apx")

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

    print(f"{BOLD}Compressing:{RESET}  {source}")
    print(f"{BOLD}Destination:{RESET}  {out_path}")
    print(f"{BOLD}Preset Mode:{RESET}  {CYAN}{mode.value.upper()}{RESET} (Block size: {display_block_mb:g} MB)")
    print(f"{DIM}Running tournament optimization across CPU cores...{RESET}\n")

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
        sys.stdout.write(
            f"\r{CYAN}[{bar}]{RESET} {pct:5.1f}% | {format_bytes(done_bytes):<9} | Winner: {GREEN}{winner:<32}{RESET} ({ratio:5.2f}x)"
        )
        sys.stdout.flush()

    try:
        res = compress_archive(
            str(source),
            str(out_path),
            mode=mode,
            block_size=block_size,
            password=args.password,
            recovery=args.recovery,
            cdc=getattr(args, "cdc", False),
            progress_callback=on_progress if not args.quiet else None,
        )
    except Exception as e:
        print(f"\n{RED}Compression failed: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print("\n")

    # Print summary card
    speed_mb = (res["uncompressed_bytes"] / (1024 * 1024)) / res["elapsed"] if res["elapsed"] > 0 else 0.0
    print(f"{BOLD}{GREEN}✓ Compression Complete!{RESET}")
    print("=" * 60)
    print(f"  {BOLD}Original Size:{RESET}    {format_bytes(res['uncompressed_bytes'])}")
    print(f"  {BOLD}Apex Size:{RESET}        {format_bytes(res['compressed_bytes'])}")
    print(f"  {BOLD}Space Saved:{RESET}      {GREEN}{res['space_saved_pct']:.2f}%{RESET}")
    print(f"  {BOLD}Compression Ratio:{RESET}{CYAN}{BOLD} {res['ratio']:.2f}x{RESET}")
    print(f"  {BOLD}Total Blocks:{RESET}     {res['blocks']}")
    print(f"  {BOLD}Time Elapsed:{RESET}     {res['elapsed']:.2f}s ({speed_mb:.1f} MB/s)")
    print(f"  {BOLD}Stream SHA-256:{RESET}   {DIM}{res['sha256']}{RESET}")
    if res.get("encrypted"):
        print(f"  {BOLD}Security:{RESET}        {GREEN}Authenticated Encryption (AES-256-CTR + HMAC-SHA256){RESET}")
    if res.get("recovery"):
        print(f"  {BOLD}Self-Healing:{RESET}    {GREEN}Reed-Solomon Parity Records Attached{RESET}")
    print("=" * 60)

    if args.verbose and res["block_records"]:
        print(f"\n{BOLD}Block Tournament Breakdown:{RESET}")
        print(f"  {'Block':<6} | {'Winner Pipeline':<36} | {'Uncompressed':<12} | {'Compressed':<12} | {'Ratio':<8}")
        print("  " + "-" * 82)
        for b in res["block_records"]:
            print(f"  #{b['block']:<5} | {b['winner']:<36} | {format_bytes(b['uncompressed']):<12} | {format_bytes(b['compressed']):<12} | {b['ratio']:6.2f}x")


def cmd_decompress(args):
    archive_path = Path(args.archive).resolve()
    if not archive_path.exists():
        print(f"{RED}Error: Archive '{args.archive}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"{BOLD}Decompressing:{RESET} {archive_path}")
    if args.dest:
        print(f"{BOLD}Destination:{RESET}   {args.dest}")

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
            str(archive_path),
            output_dir=args.dest,
            password=args.password,
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
    print(f"  {BOLD}Time Elapsed:{RESET}     {res['elapsed']:.2f}s")
    print(f"  {BOLD}Integrity:{RESET}        {GREEN}100% Bit-Exact SHA-256 Verified{RESET}")
    print("=" * 60)


def cmd_test(args):
    archive_path = Path(args.archive).resolve()
    if not archive_path.exists():
        print(f"{RED}Error: Archive '{args.archive}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)

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

    with open(archive_path, "rb") as f:
        flags, block_size, manifest, enc_key, mac_key = read_archive_header(f, password=args.password)

    print(f"{BOLD}Archive:{RESET}     {archive_path.name}")
    print(f"{BOLD}Type:{RESET}        {'Directory / Solid Archive' if manifest.is_dir else 'Single File'}")
    print(f"{BOLD}Block Size:{RESET}  {block_size // (1024*1024)} MB")
    print(f"{BOLD}Encrypted:{RESET}   {'Yes (AES-256-CTR + HMAC-SHA256)' if (flags & FLAG_ENCRYPTED) else 'No'}")
    print(f"{BOLD}Self-Healing:{RESET}{'Yes (Reed-Solomon Parity)' if (flags & FLAG_RECOVERY) else 'No'}")
    print(f"{BOLD}Total Files:{RESET} {len(manifest.files)}")
    print(f"{BOLD}Total Size:{RESET}  {format_bytes(manifest.total_uncompressed_size)}\n")

    print(f"{'Mode':<10} | {'Size':<12} | {'Modified':<20} | {'Filename':<35}")
    print("-" * 82)
    for f in manifest.files:
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.mtime))
        mode_str = oct(f.mode)[-4:]
        print(f"{mode_str:<10} | {format_bytes(f.size):<12} | {mtime_str:<20} | {f.rel_path}")


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
    print(f"{BOLD}Reading sample from:{RESET} {file_path} ({format_bytes(size)})")

    # Read up to sample limit (default 16MB)
    sample_limit = int(args.max_sample_mb * 1024 * 1024)
    with open(file_path, "rb") as f:
        data = f.read(sample_limit)

    print(f"{DIM}Running tournament shootout against Gzip, Bzip2, XZ, Zstandard, Brotli...{RESET}\n")
    results = run_benchmark(data)

    print(f"{BOLD}TOURNAMENT BENCHMARK SHOOTOUT{RESET} (Input: {format_bytes(len(data))})")
    print("=" * 96)
    print(f"{'Rank':<5} | {'Engine / Tool':<42} | {'Compressed':<11} | {'Ratio':<9} | {'Saved%':<8} | {'Comp (ms)':<10}")
    print("-" * 96)

    for i, r in enumerate(results, 1):
        if i == 1:
            rank_str = f"{YELLOW}🥇 1{RESET}"
            name_str = f"{BOLD}{GREEN}{r.engine_name:<42}{RESET}"
        elif i == 2:
            rank_str = f"{CYAN}🥈 2{RESET}"
            name_str = f"{CYAN}{r.engine_name:<42}{RESET}"
        elif i == 3:
            rank_str = f"{MAGENTA}🥉 3{RESET}"
            name_str = f"{r.engine_name:<42}"
        else:
            rank_str = f"#{i:<3}"
            name_str = f"{r.engine_name:<42}"

        print(f"{rank_str:<5} | {name_str} | {format_bytes(r.compressed_size):<11} | {r.compression_ratio:6.2f}x  | {r.space_saved_pct:6.2f}% | {r.compression_time_ms:8.2f} ms")

    print("=" * 96)


def cmd_info(args):
    file_path = Path(args.file).resolve()
    if not file_path.exists() or not file_path.is_file():
        print(f"{RED}Error: File '{args.file}' not found.{RESET}", file=sys.stderr)
        sys.exit(1)

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


def main():
    parser = argparse.ArgumentParser(
        prog="apex",
        description="ApexCompress: The Adaptive Tournament Multi-Engine Compression Tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Compress
    p_comp = subparsers.add_parser("compress", aliases=["c"], help="Compress a file or folder into an .apx archive (saved to ~/Downloads by default)")
    p_comp.add_argument("target", help="File or folder to compress")
    p_comp.add_argument("-o", "--output", help="Output .apx file path (default: ~/Downloads/<name>.apx)")
    p_comp.add_argument("-m", "--mode", choices=["fast", "balanced", "ultra", "brute"], default="balanced", help="Compression preset")
    p_comp.add_argument("-b", "--block-size", type=float, default=None, help="Block size in megabytes (default: 4 MB for fast, 2 MB for balanced/ultra)")
    p_comp.add_argument("-p", "--password", help="Encrypt archive with AES-256-CTR & HMAC-SHA256")
    p_comp.add_argument("-r", "--recovery", action="store_true", help="Embed Reed-Solomon self-healing parity records")
    p_comp.add_argument("--cdc", action="store_true", help="Enable Content-Defined Chunking for game patches and delta updates")
    p_comp.add_argument("-v", "--verbose", action="store_true", help="Print block-level tournament winners")
    p_comp.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")
    p_comp.set_defaults(func=cmd_compress)

    # Decompress
    p_decomp = subparsers.add_parser("decompress", aliases=["x", "extract"], help="Decompress an .apx archive")
    p_decomp.add_argument("archive", help="Path to .apx archive")
    p_decomp.add_argument("-d", "--dest", help="Destination folder or file path")
    p_decomp.add_argument("-p", "--password", help="Password for encrypted archive")
    p_decomp.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")
    p_decomp.set_defaults(func=cmd_decompress)

    # Test
    p_test = subparsers.add_parser("test", aliases=["t"], help="Test archive integrity without writing to disk")
    p_test.add_argument("archive", help="Path to .apx archive")
    p_test.add_argument("-p", "--password", help="Password for encrypted archive")
    p_test.set_defaults(func=cmd_test)

    # List
    p_list = subparsers.add_parser("list", aliases=["l"], help="List contents of an .apx archive")
    p_list.add_argument("archive", help="Path to .apx archive")
    p_list.add_argument("-p", "--password", help="Password for encrypted archive")
    p_list.set_defaults(func=cmd_list)

    # Repair / Self-Healing
    p_repair = subparsers.add_parser("repair", aliases=["fix", "heal"], help="Self-heal a damaged .apx archive using recovery parity")
    p_repair.add_argument("archive", help="Path to damaged .apx archive")
    p_repair.add_argument("-o", "--output", help="Output repaired .apx path (default: <name>.repaired.apx)")
    p_repair.add_argument("-p", "--password", help="Password if archive is encrypted")
    p_repair.set_defaults(func=cmd_repair)

    # Benchmark
    p_bench = subparsers.add_parser("benchmark", aliases=["b"], help="Shootout benchmark against Gzip, Bzip2, XZ, Zstd, Brotli")
    p_bench.add_argument("file", help="File to benchmark")
    p_bench.add_argument("--max-sample-mb", type=float, default=16.0, help="Max sample size to benchmark in MB")
    p_bench.set_defaults(func=cmd_benchmark)

    # Info
    p_info = subparsers.add_parser("info", aliases=["i"], help="Analyze Shannon entropy and file compressibility")
    p_info.add_argument("file", help="File to analyze")
    p_info.set_defaults(func=cmd_info)

    if len(sys.argv) == 1:
        print_banner()
        parser.print_help()
        sys.exit(0)

    # Smart auto-detection if user passed a path without specifying a subcommand
    subcommands = {
        "compress", "c", "decompress", "x", "extract",
        "test", "t", "list", "l", "benchmark", "b", "info", "i",
        "repair", "fix", "heal",
        "-h", "--help", "-v", "--version"
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
