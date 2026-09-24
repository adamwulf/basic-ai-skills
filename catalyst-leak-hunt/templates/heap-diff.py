#!/usr/bin/env python3
"""Diff three `heap` snapshots from the catalyst-leak-hunt harness.

Usage: python3 heap-diff.py <heap-A> <heap-B> <heap-C> [--watch CLASS,...]

Prints:
  - Classes of interest table — A/B/C counts + bytes + delta (C-A)
  - Leak fingerprint — every class where count went UP A->B and did NOT
    come back DOWN B->C. That's the canonical leak set.

The --watch argument extends the built-in "classes of interest" list
with app-specific class names. Without it, only the generic UIKit /
PDFKit / Foundation classes are shown by name (everything still goes
through the fingerprint detector).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

LINE_RE = re.compile(
    r"^\s*([\d,]+)\s+([\d,]+)\s+([\d.]+)\s+(\S(?:.*?\S)?)\s+(ObjC|Swift|C|C\+\+|CFType)\s+(\S+)\s*$"
)


def parse_heap(path: Path) -> dict[str, tuple[int, int]]:
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for line in path.read_text(errors="replace").splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        totals[m.group(4).strip()][0] += int(m.group(1).replace(",", ""))
        totals[m.group(4).strip()][1] += int(m.group(2).replace(",", ""))
    return {k: (v[0], v[1]) for k, v in totals.items()}


def fmt_count(n: int) -> str:
    return f"{n:>8,}"


def fmt_size(n: int) -> str:
    if n >= 1024 * 1024 * 1024:
        return f"{n / 1024 / 1024 / 1024:7.2f} GiB"
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:7.2f} MiB"
    if n >= 1024:
        return f"{n / 1024:7.2f} KiB"
    return f"{n:>11} B"


# Generic UIKit / PDFKit / CoreAnimation / Foundation classes worth watching
# on most iOS/Catalyst leak hunts.
DEFAULT_INTEREST = [
    # UIKit scene infrastructure
    "UIWindow", "UIWindowScene", "UIScene", "UISceneSession",
    "FBSScene", "FBSSceneClient", "FBSSceneClientIdentity",
    "FUApplicationSceneComponent",
    "UIApplication",
    # Common VC types
    "UIViewController", "UINavigationController",
    # PDFKit
    "PDFDocument", "PDFPage", "PDFView",
    # Common framework objects
    "UndoManager", "NSUndoManager",
    "UIGestureRecognizer", "UITapGestureRecognizer", "UIPanGestureRecognizer",
    "UIPinchGestureRecognizer", "UILongPressGestureRecognizer", "UISwipeGestureRecognizer",
    "UICommand", "UIKeyCommand",
    # CoreAnimation / CoreGraphics raster
    "CALayer", "CAShapeLayer", "CGImage", "IOSurface",
]


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("a", type=Path)
    p.add_argument("b", type=Path)
    p.add_argument("c", type=Path)
    p.add_argument(
        "--watch", default="",
        help="Comma-separated extra class names to include in the 'of interest' table"
    )
    args = p.parse_args(argv[1:])

    a = parse_heap(args.a)
    b = parse_heap(args.b)
    c = parse_heap(args.c)
    all_classes = set(a) | set(b) | set(c)

    watch_extra = [s.strip() for s in args.watch.split(",") if s.strip()]
    interest = DEFAULT_INTEREST + watch_extra

    print("\n=== Classes of interest ===")
    hdr = f"{'class':<48}  {'A count':>8} {'A bytes':>14}    {'B count':>8} {'B bytes':>14}    {'C count':>8} {'C bytes':>14}    {'delta':>9}"
    print(hdr)
    for name in interest:
        matches = sorted(k for k in all_classes if name in k or k == name)
        if not matches:
            print(f"{name:<48}  (no matches)")
            continue
        for k in matches:
            (a_c, a_b) = a.get(k, (0, 0))
            (b_c, b_b) = b.get(k, (0, 0))
            (c_c, c_b) = c.get(k, (0, 0))
            delta = c_c - a_c
            print(f"{k:<48}  {fmt_count(a_c)} {fmt_size(a_b)}    {fmt_count(b_c)} {fmt_size(b_b)}    {fmt_count(c_c)} {fmt_size(c_b)}    {delta:>+9}")

    leaks: list[tuple[str, int, int, int, int]] = []
    for k in all_classes:
        ac = a.get(k, (0, 0))[0]
        bc = b.get(k, (0, 0))[0]
        cc = c.get(k, (0, 0))[0]
        if bc - ac >= 1 and bc - cc <= 0 and cc > ac:
            leaks.append((k, ac, bc, cc, cc - ac))
    leaks.sort(key=lambda x: (-x[4], x[0]))

    print(f"\n=== Leak fingerprint: classes that went UP A->B but did NOT come DOWN B->C ===")
    print(f"{'class':<60} {'A':>6} {'B':>6} {'C':>6} {'C-A':>6}")
    for k, ac, bc, cc, da in leaks:
        print(f"{k:<60} {ac:>6} {bc:>6} {cc:>6} {da:>+6}")
    print(f"\nTotal leaked classes: {len(leaks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
