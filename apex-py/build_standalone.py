#!/usr/bin/env python3
"""
Apex Standalone Executable Builder
==================================
Compiles the Apex Python implementation into a single standalone,
zero-dependency native executable using Nuitka.

Supported Platforms: macOS (Mach-O), Linux (ELF), Windows (PE / .exe)
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    root_dir = Path(__file__).resolve().parent
    launcher = root_dir / "apex_launcher.py"
    dist_dir = root_dir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Apex Standalone Executable Builder")
    print(f"  Target OS:     {platform.system()} ({platform.machine()})")
    print(f"  Python:        {sys.version.split()[0]}")
    print("=" * 60)

    # Check Nuitka availability
    try:
        import nuitka  # noqa: F401
    except ImportError:
        print("\n[!] Nuitka is not installed in the current Python environment.")
        print("    Install it via: pip install nuitka zstandard brotli")
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--assume-yes-for-downloads",
        "--include-package=apex",
        "--include-package=zstandard",
        "--include-package=brotli",
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=unittest",
        "--no-deployment-flag=self-execution",
        f"--output-dir={dist_dir}",
        "--output-filename=apex",
        "--show-progress",
        str(launcher),
    ]

    print(f"\n[+] Executing build command:\n    {' '.join(cmd)}\n")
    res = subprocess.run(cmd)

    if res.returncode != 0:
        print(f"\n[X] Build failed with exit code {res.returncode}")
        sys.exit(res.returncode)

    binary_name = "apex.exe" if platform.system() == "Windows" else "apex"
    binary_path = dist_dir / binary_name

    if binary_path.exists():
        size_mb = binary_path.stat().st_size / (1024 * 1024)
        print("\n" + "=" * 60)
        print("  [OK] Standalone Executable Built Successfully!")
        print(f"  Output Path: {binary_path}")
        print(f"  Size:        {size_mb:.2f} MB")
        print("=" * 60)
        print("\nTest your binary with:")
        print(f"  {binary_path} --help\n")
    else:
        print(f"\n[!] Warning: Expected binary not found at {binary_path}")


if __name__ == "__main__":
    main()
