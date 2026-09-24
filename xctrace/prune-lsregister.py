#!/usr/bin/env python3
"""
Prune LaunchServices registrations for a given CFBundleIdentifier.

By default, dry-run lists every registered .app whose bundle id matches the
target and whose path lives inside a "DerivedData" directory. With --apply,
unregisters each one. Optionally keep a single path with --keep <path>.

Why this exists: when many git worktrees + Xcode incremental builds produce
.app bundles with the same CFBundleIdentifier, LaunchServices substitutes
one of them for `xctrace --launch <path>` (the path you pass is hint-only
for .app bundles). Leftover DerivedData copies from old worktrees outrank
your fresh build, so the trace ends up profiling the wrong binary.
This script trims the candidate list to whatever you actually want.

Usage:
  python3 prune-lsregister.py com.example.MyApp                 # dry-run
  python3 prune-lsregister.py com.example.MyApp --apply         # unregister
  python3 prune-lsregister.py com.example.MyApp --keep PATH ... # keep PATH(s)

Bundle path matching is segment-aware: a directory named exactly
"DerivedData" anywhere in the path counts. Substrings like "MyDerivedData"
are ignored.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

LSREGISTER_DEFAULT = (
    "/System/Library/Frameworks/CoreServices.framework"
    "/Frameworks/LaunchServices.framework/Support/lsregister"
)


def find_lsregister() -> str:
    """Prefer lsregister on PATH (e.g. user-created /usr/local/bin symlink),
    fall back to the system path."""
    found = shutil.which("lsregister")
    if found:
        return found
    if os.path.exists(LSREGISTER_DEFAULT):
        return LSREGISTER_DEFAULT
    sys.exit("error: cannot find lsregister on PATH or at the default system path")


def dump_lsregister(lsregister: str) -> str:
    proc = subprocess.run(
        [lsregister, "-dump"], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0 and not proc.stdout:
        sys.exit(f"error: lsregister -dump failed: {proc.stderr.strip()}")
    return proc.stdout


# Records in `lsregister -dump` are separated by lines of dashes.
RECORD_SEPARATOR = re.compile(r"^-{30,}\s*$", re.MULTILINE)
PATH_LINE = re.compile(r"^path:\s+(.*?)(?:\s+\(0x[0-9a-f]+\))?\s*$", re.MULTILINE)
IDENT_LINE = re.compile(r"^identifier:\s+(\S+)\s*$", re.MULTILINE)


def parse_records(dump: str, bundle_id: str) -> list[str]:
    """Return all registered paths for the given bundle identifier."""
    paths: list[str] = []
    for record in RECORD_SEPARATOR.split(dump):
        ident_m = IDENT_LINE.search(record)
        if not ident_m or ident_m.group(1) != bundle_id:
            continue
        for path_m in PATH_LINE.finditer(record):
            paths.append(path_m.group(1))
    # de-dup, preserve order
    seen: set[str] = set()
    unique: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def is_in_derived_data(path: str) -> bool:
    """True if any path segment is exactly 'DerivedData' (or DerivedData2,
    DerivedData3 — Xcode auto-numbers when colliding)."""
    parts = Path(path).parts
    return any(re.fullmatch(r"DerivedData\d*", segment) for segment in parts)


def normalize(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prune LaunchServices registrations under DerivedData/* for a bundle id."
    )
    parser.add_argument("bundle_id", help="CFBundleIdentifier to prune")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually run lsregister -u (default: dry-run).",
    )
    parser.add_argument(
        "--keep",
        action="append",
        default=[],
        help="Path(s) to keep registered. Repeat for multiple.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Prune every candidate, not just paths under DerivedData.",
    )
    parser.add_argument(
        "--lsregister",
        default=None,
        help="Override lsregister binary path (default: PATH lookup, then system).",
    )
    args = parser.parse_args()

    lsregister = args.lsregister or find_lsregister()
    dump = dump_lsregister(lsregister)
    paths = parse_records(dump, args.bundle_id)
    if not paths:
        print(f"no registrations found for {args.bundle_id}")
        return 0

    keep_set = {normalize(k) for k in args.keep}

    candidates: list[str] = []
    for p in paths:
        if normalize(p) in keep_set:
            continue
        if not args.all and not is_in_derived_data(p):
            continue
        candidates.append(p)

    print(f"Bundle: {args.bundle_id}")
    print(f"Total registrations: {len(paths)}")
    print(f"Kept (--keep): {len(keep_set)} paths")
    print(f"Candidates to unregister: {len(candidates)}")
    print()

    if not candidates:
        print("nothing to do.")
        return 0

    width = len(str(len(candidates)))
    for i, p in enumerate(candidates, 1):
        prefix = f"  [{i:>{width}}/{len(candidates)}]"
        if not args.apply:
            print(f"{prefix} would unregister: {p}")
            continue
        print(f"{prefix} unregistering: {p}")
        proc = subprocess.run(
            [lsregister, "-u", p], capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            print(f"      ! lsregister -u failed ({proc.returncode}): {err}")

    if not args.apply:
        print()
        print("dry-run only. re-run with --apply to actually unregister.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
