#!/usr/bin/env python3
"""Print the launch phase timeline from an xctrace .trace bundle.

Usage:
    phases.py TRACE.trace                         # single-trace report
    phases.py TRACE.trace --baseline OLD.trace    # side-by-side diff

Reads the `life-cycle-period` table via `xctrace export` and prints a markdown
table of phases, durations, and the all-important gap from "Initial Frame
Rendering" to "Foreground" — the number you usually care about when measuring
launch.

The table only exists in App Launch traces. For Time Profiler traces the
table is also populated when the launched process is the target. If the
trace was attached (not launched), there are no phases and we exit non-zero.
"""

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# `xctrace export --xpath '.../table[@schema="life-cycle-period"]'` returns one
# <row> per phase with duration in nanoseconds. The narrative `fmt` attribute
# carries the human label ("Launching - sceneWillConnectTo()" etc.).
PHASE_XPATH = '/trace-toc/run/data/table[@schema="life-cycle-period"]'


def export_phases(trace_path: Path) -> list[tuple[int, int, str]]:
    """Return [(start_ns, duration_ns, phase_name), ...] in trace order."""
    cmd = ["xctrace", "export", "--input", str(trace_path), "--xpath", PHASE_XPATH]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        sys.exit(f"xctrace export failed:\n{out.stderr}")

    # xctrace's export uses id/ref deduplication for repeated values. We need
    # to resolve refs to read every row's phase name + duration.
    root = ET.fromstring(out.stdout)
    id_map = {el.get("id"): el for el in root.iter() if el.get("id")}

    def resolve(el):
        return id_map[el.get("ref")] if el.get("ref") else el

    phases = []
    for row in root.iter("row"):
        start_ns = None
        dur_ns = None
        name = None
        for child in row:
            actual = resolve(child)
            if actual.tag == "start-time":
                try:
                    start_ns = int(actual.text)
                except (TypeError, ValueError):
                    pass
            elif actual.tag == "duration":
                try:
                    dur_ns = int(actual.text)
                except (TypeError, ValueError):
                    pass
            elif actual.tag == "app-period":
                # The fmt attribute is the human-readable name; if missing,
                # fall back to the element text.
                name = actual.get("fmt") or (actual.text or "").strip()
        if start_ns is not None and dur_ns is not None and name:
            phases.append((start_ns, dur_ns, name))

    return phases


def fmt_dur(ns: int) -> str:
    """Format a duration in ns to a short human-readable string."""
    if ns < 1_000:
        return f"{ns} ns"
    if ns < 1_000_000:
        return f"{ns / 1_000:.2f} µs"
    if ns < 1_000_000_000:
        return f"{ns / 1_000_000:.2f} ms"
    return f"{ns / 1_000_000_000:.2f} s"


def fmt_signed_dur(ns: int) -> str:
    sign = "+" if ns >= 0 else "-"
    return sign + fmt_dur(abs(ns))


def find_phase_exact(phases, name: str):
    """Return the first phase whose name equals `name`, else None.

    Use exact match because phase names overlap as substrings — e.g.
    "Launching - sceneWillEnterForeground()" contains "Foreground" but is
    not the Foreground phase.
    """
    for p in phases:
        if p[2] == name:
            return p
    return None


def find_phase_endswith(phases, suffix: str):
    """Return the first phase whose name ends with `suffix`, else None.

    Useful for matching e.g. "Launching - Initial Frame Rendering" without
    hardcoding the "Launching - " prefix.
    """
    for p in phases:
        if p[2].endswith(suffix):
            return p
    return None


def gap_to_foreground(phases) -> int | None:
    """Compute the gap from end of 'Initial Frame Rendering' to start of 'Foreground'.

    This is usually the most actionable number — the user has seen the first
    frame, and we're measuring the time until the app accepts input. Work in
    this gap is post-first-frame setup that delays interactivity.

    Returns ns or None if either phase is missing (e.g. trace ended before
    Foreground fired — common with too-short --time-limit).
    """
    ifr = find_phase_endswith(phases, "Initial Frame Rendering")
    fg = find_phase_exact(phases, "Foreground")
    if ifr is None or fg is None:
        return None
    ifr_end = ifr[0] + ifr[1]
    return fg[0] - ifr_end


def total_to_foreground(phases) -> int | None:
    """Time from process creation start (always at t=0) to Foreground start."""
    fg = find_phase_exact(phases, "Foreground")
    if fg is None:
        return None
    return fg[0]


def print_single(phases, label: str = ""):
    if not phases:
        sys.exit("No life-cycle phases found in trace. Was this an App Launch trace, with --launch (not --attach)?")

    if label:
        print(f"# Launch phases — {label}\n")
    else:
        print("# Launch phases\n")

    print("| Start | Duration | Phase |")
    print("|-------|----------|-------|")
    for start_ns, dur_ns, name in phases:
        # Show start as "MM:SS.mmm" relative to t=0
        ms = start_ns // 1_000_000
        mm, sec_ms = divmod(ms, 60_000)
        ss, mss = divmod(sec_ms, 1_000)
        print(f"| {mm:02d}:{ss:02d}.{mss:03d} | {fmt_dur(dur_ns):>10s} | {name} |")

    gap = gap_to_foreground(phases)
    total = total_to_foreground(phases)
    print()
    if total is not None:
        print(f"**Process start → Foreground:** {fmt_dur(total)}")
    if gap is not None:
        print(f"**Initial Frame → Foreground (post-first-frame work):** {fmt_dur(gap)}")
    if total is None and gap is None:
        # Trace likely ended before Foreground fired.
        last_start, last_dur, last_name = phases[-1]
        print(f"_Trace ended before Foreground phase. Last phase: {last_name}._")


def numbered_phase_keys(phases):
    """Yield (name_with_occurrence_suffix, dur_ns) for each phase, in order.

    Names that repeat get a "(#2)", "(#3)" suffix so the diff can match them
    independently. Without this, repeated phases like "Launching - UIKit
    Scene Creation" all collapse into one row and the diff is meaningless.
    """
    counts = {}
    for _, dur_ns, name in phases:
        counts[name] = counts.get(name, 0) + 1
        n = counts[name]
        key = name if n == 1 else f"{name} (#{n})"
        yield (key, dur_ns)


def print_diff(new_phases, baseline_phases, new_label: str, base_label: str):
    """Print a side-by-side diff matched by phase name + occurrence index.

    Multiple appearances of the same phase name are disambiguated with
    "(#2)", "(#3)", etc.; the Nth occurrence in `new` is matched against
    the Nth occurrence in `baseline`. Phases that appear only in one trace
    show as "_new_" or "_removed_".
    """
    if not new_phases:
        sys.exit(f"No phases in {new_label}.")
    if not baseline_phases:
        sys.exit(f"No phases in baseline {base_label}.")

    print(f"# Launch phases — {new_label} vs {base_label}\n")
    print(f"| Phase | {base_label} | {new_label} | Δ |")
    print("|-------|--------------|-------------|---|")

    base_by_key = dict(numbered_phase_keys(baseline_phases))
    seen = set()
    for key, dur_ns in numbered_phase_keys(new_phases):
        seen.add(key)
        if key in base_by_key:
            base_dur = base_by_key[key]
            delta = dur_ns - base_dur
            delta_pct = (delta / base_dur * 100) if base_dur else 0
            print(f"| {key} | {fmt_dur(base_dur)} | {fmt_dur(dur_ns)} | {fmt_signed_dur(delta)} ({delta_pct:+.1f}%) |")
        else:
            print(f"| {key} | _(absent)_ | {fmt_dur(dur_ns)} | _new_ |")
    for key, dur in numbered_phase_keys(baseline_phases):
        if key not in seen:
            print(f"| {key} | {fmt_dur(dur)} | _(absent)_ | _removed_ |")

    # Headline numbers
    print()
    new_total = total_to_foreground(new_phases)
    base_total = total_to_foreground(baseline_phases)
    if new_total is not None and base_total is not None:
        d = new_total - base_total
        print(f"**Process start → Foreground:** {fmt_dur(base_total)} → {fmt_dur(new_total)} ({fmt_signed_dur(d)})")

    new_gap = gap_to_foreground(new_phases)
    base_gap = gap_to_foreground(baseline_phases)
    if new_gap is not None and base_gap is not None:
        d = new_gap - base_gap
        print(f"**Initial Frame → Foreground:** {fmt_dur(base_gap)} → {fmt_dur(new_gap)} ({fmt_signed_dur(d)})")

    new_gap = gap_to_foreground(new_phases)
    base_gap = gap_to_foreground(baseline_phases)
    if new_gap is not None and base_gap is not None:
        d = new_gap - base_gap
        print(f"**Initial Frame → Foreground:** {fmt_dur(base_gap)} → {fmt_dur(new_gap)} ({fmt_signed_dur(d)})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("trace", type=Path, help="Path to .trace bundle")
    ap.add_argument("--baseline", type=Path, help="Optional baseline trace for side-by-side diff")
    args = ap.parse_args()

    if not args.trace.is_dir():
        sys.exit(f"Not a .trace bundle: {args.trace}")
    phases = export_phases(args.trace)

    if args.baseline:
        if not args.baseline.is_dir():
            sys.exit(f"Not a .trace bundle: {args.baseline}")
        base = export_phases(args.baseline)
        print_diff(phases, base, args.trace.name, args.baseline.name)
    else:
        print_single(phases)


if __name__ == "__main__":
    main()
