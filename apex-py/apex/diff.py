"""
Apex Archive Diff Tool - Compare manifests, file lists, sizes, and metadata between two Apex archives.
"""

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from apex.archive import read_archive_header
from apex.benchmark import format_bytes


def format_delta_bytes(n: int) -> str:
    """Format positive or negative byte delta."""
    if n > 0:
        return f"+{format_bytes(n)}"
    elif n < 0:
        return f"-{format_bytes(abs(n))}"
    else:
        return "0 B"


def diff_archives(
    archive1_path: str,
    archive2_path: str,
    password: Optional[str] = None,
    password2: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compares two Apex archives by reading their embedded manifests.
    Fast metadata-only comparison without decompressing payload blocks.
    """
    p1 = Path(archive1_path).resolve()
    p2 = Path(archive2_path).resolve()

    if not p1.exists():
        raise FileNotFoundError(f"Archive '{archive1_path}' not found.")
    if not p2.exists():
        raise FileNotFoundError(f"Archive '{archive2_path}' not found.")

    with open(p1, "rb") as f1:
        flags1, block_size1, manifest1, _, _ = read_archive_header(f1, password=password)

    pwd2 = password2 if password2 is not None else password
    with open(p2, "rb") as f2:
        flags2, block_size2, manifest2, _, _ = read_archive_header(f2, password=pwd2)

    files1 = {f.rel_path: f for f in manifest1.files}
    files2 = {f.rel_path: f for f in manifest2.files}

    all_paths = sorted(set(files1.keys()) | set(files2.keys()))

    added: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    modified: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []

    for path in all_paths:
        if path in files2 and path not in files1:
            f2 = files2[path]
            added.append({
                "path": path,
                "size": f2.size,
                "is_dir": f2.is_dir,
                "is_symlink": f2.is_symlink,
                "mode": f2.mode,
                "mtime": f2.mtime,
            })
        elif path in files1 and path not in files2:
            f1 = files1[path]
            removed.append({
                "path": path,
                "size": f1.size,
                "is_dir": f1.is_dir,
                "is_symlink": f1.is_symlink,
                "mode": f1.mode,
                "mtime": f1.mtime,
            })
        else:
            f1 = files1[path]
            f2 = files2[path]
            size_diff = f2.size - f1.size
            is_mod = (
                f1.size != f2.size
                or f1.is_symlink != f2.is_symlink
                or f1.link_target != f2.link_target
                or f1.mode != f2.mode
                or abs(f1.mtime - f2.mtime) > 0.001
            )
            entry = {
                "path": path,
                "old_size": f1.size,
                "new_size": f2.size,
                "size_diff": size_diff,
                "old_mtime": f1.mtime,
                "new_mtime": f2.mtime,
                "is_dir": f2.is_dir,
            }
            if is_mod:
                modified.append(entry)
            else:
                unchanged.append(entry)

    size_delta = manifest2.total_uncompressed_size - manifest1.total_uncompressed_size

    return {
        "archive1": str(p1),
        "archive2": str(p2),
        "archive1_size": p1.stat().st_size,
        "archive2_size": p2.stat().st_size,
        "uncompressed_size1": manifest1.total_uncompressed_size,
        "uncompressed_size2": manifest2.total_uncompressed_size,
        "size_delta": size_delta,
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
        "identical": len(added) == 0 and len(removed) == 0 and len(modified) == 0,
    }


def format_diff_report(diff_res: Dict[str, Any], color: bool = True) -> str:
    """Formats diff results for terminal output."""
    BOLD = "\033[1m" if color else ""
    DIM = "\033[2m" if color else ""
    GREEN = "\033[32m" if color else ""
    RED = "\033[31m" if color else ""
    YELLOW = "\033[33m" if color else ""
    CYAN = "\033[36m" if color else ""
    RESET = "\033[0m" if color else ""

    lines = []
    lines.append(f"{BOLD}Apex Archive Comparison:{RESET}")
    lines.append(f"  {BOLD}Old (-):{RESET} {Path(diff_res['archive1']).name} ({format_bytes(diff_res['archive1_size'])}, uncompressed: {format_bytes(diff_res['uncompressed_size1'])})")
    lines.append(f"  {BOLD}New (+):{RESET} {Path(diff_res['archive2']).name} ({format_bytes(diff_res['archive2_size'])}, uncompressed: {format_bytes(diff_res['uncompressed_size2'])})")
    lines.append("")

    if diff_res["identical"]:
        lines.append(f"{GREEN}✓ Archives contain identical files and metadata.{RESET}")
        return "\n".join(lines)

    if diff_res["added"]:
        lines.append(f"{GREEN}{BOLD}+ Added ({len(diff_res['added'])}):{RESET}")
        for item in diff_res["added"]:
            kind = "[dir]" if item["is_dir"] else format_bytes(item["size"])
            lines.append(f"  {GREEN}+ {item['path']} ({kind}){RESET}")
        lines.append("")

    if diff_res["removed"]:
        lines.append(f"{RED}{BOLD}- Removed ({len(diff_res['removed'])}):{RESET}")
        for item in diff_res["removed"]:
            kind = "[dir]" if item["is_dir"] else format_bytes(item["size"])
            lines.append(f"  {RED}- {item['path']} ({kind}){RESET}")
        lines.append("")

    if diff_res["modified"]:
        lines.append(f"{YELLOW}{BOLD}~ Modified ({len(diff_res['modified'])}):{RESET}")
        for item in diff_res["modified"]:
            delta = format_delta_bytes(item["size_diff"])
            lines.append(f"  {YELLOW}~ {item['path']} ({delta}, {format_bytes(item['old_size'])} → {format_bytes(item['new_size'])}){RESET}")
        lines.append("")

    lines.append("=" * 60)
    lines.append(
        f"  {BOLD}Summary:{RESET} "
        f"{GREEN}+{len(diff_res['added'])}{RESET} added, "
        f"{RED}-{len(diff_res['removed'])}{RESET} removed, "
        f"{YELLOW}~{len(diff_res['modified'])}{RESET} modified, "
        f"{len(diff_res['unchanged'])} unchanged"
    )
    lines.append(
        f"  {BOLD}Net Size Delta:{RESET} {format_delta_bytes(diff_res['size_delta'])} uncompressed"
    )
    lines.append("=" * 60)

    return "\n".join(lines)
