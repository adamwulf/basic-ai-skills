#!/usr/bin/env python3
"""Print top hotspots from an xctrace .trace bundle.

Usage:
    hotspots.py TRACE.trace
    hotspots.py TRACE.trace --window willFinishLaunching..Foreground
    hotspots.py TRACE.trace --thread main --top 50

Streams the time-sample table, filters by window + thread, dedupes addresses
per-sample (so deep recursion doesn't dominate), maps each address to its
binary using a load-address map built from EVERY <binary> element in the
trace export (not just the dyld-library-load table — that one is often
empty), and symbolicates via batched `atos`.

Anything atos can't resolve is shown as the raw address rather than
silently misattributed. The misattribution bug (an unmapped address falling
into the gap between two known load addresses) is avoided because the image
map is built from observed binaries only — not assumed ranges.
"""

import argparse
import collections
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Sample-table xpath. We pull text-addresses (full backtrace) and text-address
# (leaf PC) for each row. Default sample interval is 5 ms; the row's `time-sample-kind`
# tells us whether the sample was a timer fire, LPET, etc., but we treat all
# kinds equally.
SAMPLES_XPATH = '/trace-toc/run/data/table[@schema="time-sample"]'
PHASES_XPATH = '/trace-toc/run/data/table[@schema="life-cycle-period"]'

# `dyld-activity-interval` table. Its rows have embedded backtraces with
# <binary> elements, which is the most reliable place to harvest load
# addresses for system frameworks (the dyld-library-load table is often empty).
DYLD_ACTIVITY_XPATH = '/trace-toc/run/data/table[@schema="dyld-activity-interval"]'


def run_xctrace_export(trace: Path, xpath: str) -> str:
    """Export one table to XML and return the raw text."""
    cmd = ["xctrace", "export", "--input", str(trace), "--xpath", xpath]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        sys.exit(f"xctrace export failed for xpath {xpath}:\n{out.stderr}")
    return out.stdout


# --- Image map ------------------------------------------------------------

# A binary's frame in the export looks like:
#   <binary id="..." name="Foo" UUID="..." arch="arm64e" load-addr="0x123..." path="/.../Foo"/>
# We harvest these from any table that has them. The xctrace export uses
# id/ref deduplication, so a single <binary id="N" .../> may be referenced
# many times via <binary ref="N"/>. We only care about the ones with
# load-addr (the originals).
BINARY_PAT = re.compile(
    r'<binary\b[^/]*?'
    r'name="(?P<name>[^"]*)"[^/]*?'
    r'UUID="(?P<uuid>[^"]*)"[^/]*?'
    r'arch="(?P<arch>[^"]*)"[^/]*?'
    r'load-addr="(?P<load>0x[0-9a-fA-F]+)"[^/]*?'
    r'path="(?P<path>[^"]*)"',
    re.DOTALL,
)


def build_image_map(trace: Path):
    """Return list of dicts {load_addr, name, uuid, path, arch}, sorted by load_addr.

    Sources, in order: dyld-activity-interval (most reliable for shared-cache
    libraries) and time-sample (catches anything dyld-activity missed). Dedupe
    by UUID.
    """
    by_uuid = {}

    for xpath in (DYLD_ACTIVITY_XPATH, SAMPLES_XPATH):
        try:
            raw = run_xctrace_export(trace, xpath)
        except SystemExit:
            # Some traces don't have one of these tables; skip silently.
            continue
        for m in BINARY_PAT.finditer(raw):
            uuid = m.group("uuid")
            if uuid in by_uuid:
                continue
            by_uuid[uuid] = {
                "load_addr": int(m.group("load"), 16),
                "name": m.group("name"),
                "uuid": uuid,
                "path": m.group("path"),
                "arch": m.group("arch"),
            }

    images = sorted(by_uuid.values(), key=lambda b: b["load_addr"])
    return images


def find_image(images, addr: int):
    """Return the image whose load-addr range contains `addr`, or None.

    We use the *next* image's load-addr as the upper bound, which assumes
    dyld lays binaries out contiguously in address order. This is the same
    heuristic Instruments uses; it's not perfect (an address in a gap could
    be misattributed), but with a complete-as-possible image map the gaps
    are tiny.

    For the LAST image we have no upper bound, so we cap at +256 MB which
    is bigger than any reasonable single binary.
    """
    if not images:
        return None
    lo, hi = 0, len(images) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        load = images[mid]["load_addr"]
        end = images[mid + 1]["load_addr"] if mid + 1 < len(images) else load + 0x10_000_000
        if addr < load:
            hi = mid - 1
        elif addr >= end:
            lo = mid + 1
        else:
            return images[mid]
    return None


# --- Phase windows --------------------------------------------------------


def parse_phases(trace: Path):
    """Return [(start_ns, dur_ns, name), ...] from the life-cycle-period table."""
    raw = run_xctrace_export(trace, PHASES_XPATH)
    root = ET.fromstring(raw)
    id_map = {el.get("id"): el for el in root.iter() if el.get("id")}

    def resolve(el):
        return id_map[el.get("ref")] if el.get("ref") else el

    out = []
    for row in root.iter("row"):
        st = dur = None
        name = None
        for child in row:
            actual = resolve(child)
            if actual.tag == "start-time":
                try: st = int(actual.text)
                except (TypeError, ValueError): pass
            elif actual.tag == "duration":
                try: dur = int(actual.text)
                except (TypeError, ValueError): pass
            elif actual.tag == "app-period":
                name = actual.get("fmt") or (actual.text or "").strip()
        if st is not None and dur is not None and name:
            out.append((st, dur, name))
    return out


def resolve_window(trace: Path, window_arg: str | None):
    """Return (start_ns, end_ns) for the window.

    Accepts either:
        START..END   — phase names; matched as suffixes against phase names
                       (e.g. "willFinishLaunching..Foreground" finds
                       "Launching - willFinishLaunchingWithOptions()" and
                       "Foreground")
        None         — entire trace, no filter

    The window covers START.start_ns through END.start_ns (so anything that
    happens during END itself is excluded — for "...Foreground" that's
    typically what you want, since you're measuring time *up to* foreground).
    """
    if not window_arg:
        return (0, 10**18)

    if ".." not in window_arg:
        sys.exit(f"--window must be of the form START..END, got {window_arg!r}")

    start_name, end_name = window_arg.split("..", 1)
    phases = parse_phases(trace)

    def match(needle):
        for p in phases:
            if p[2] == needle or p[2].endswith(needle):
                return p
        return None

    start = match(start_name)
    end = match(end_name)
    if start is None:
        sys.exit(f"Window start phase not found: {start_name!r}\nAvailable phases:\n  " +
                 "\n  ".join(p[2] for p in phases))
    if end is None:
        sys.exit(f"Window end phase not found: {end_name!r}\nAvailable phases:\n  " +
                 "\n  ".join(p[2] for p in phases))
    return (start[0], end[0])


# --- Sample parsing -------------------------------------------------------


def parse_samples(trace: Path, window_start: int, window_end: int, thread_filter: str | None):
    """Yield (thread_name, [addr, addr, ...]) for each sample in the window matching thread_filter.

    `thread_filter` is matched as a substring against the thread `fmt`
    attribute. Pass "main" to match "Main Thread 0x... (Muse, pid: ...)";
    pass None to include every thread.
    """
    raw = run_xctrace_export(trace, SAMPLES_XPATH)
    root = ET.fromstring(raw)
    id_map = {el.get("id"): el for el in root.iter() if el.get("id")}

    def resolve(el):
        return id_map[el.get("ref")] if el.get("ref") else el

    for row in root.iter("row"):
        st = None
        thread_fmt = None
        addrs = []
        for child in row:
            actual = resolve(child)
            if actual.tag == "sample-time":
                try: st = int(actual.text)
                except (TypeError, ValueError): pass
            elif actual.tag == "thread":
                thread_fmt = actual.get("fmt")
            elif actual.tag == "kperf-bt":
                for sub in actual:
                    sub_actual = resolve(sub)
                    if sub_actual.tag == "text-addresses" and sub_actual.text:
                        for a in sub_actual.text.split():
                            try:
                                v = int(a)
                                if v > 0: addrs.append(v)
                            except ValueError: pass
                    elif sub_actual.tag == "text-address":
                        try:
                            v = int(sub_actual.text)
                            if v > 0: addrs.append(v)
                        except (TypeError, ValueError): pass

        if st is None or not (window_start <= st < window_end):
            continue
        if thread_filter is not None:
            if thread_fmt is None or thread_filter.lower() not in thread_fmt.lower():
                continue
        yield (thread_fmt or "(unknown)", addrs)


# --- Symbolication --------------------------------------------------------


def symbolicate(addrs_by_image):
    """Run atos per binary, return ({addr: "symbol (Binary)"}, [(image_path, reason), ...]).

    addrs_by_image: {image_dict_key: list_of_addrs}, where the key is a
    tuple (path, load_addr, arch) so we batch one atos call per binary.

    The second return value is a list of (path, reason) for binaries we
    couldn't symbolicate, so the caller can surface a "missing binaries"
    section in the report.
    """
    syms = {}
    failures = []
    for (path, load_addr, arch), addrs in addrs_by_image.items():
        if not addrs:
            continue
        if not Path(path).exists():
            # Two cases land here:
            # 1. Shared-cache system frameworks: the path is a hint, the
            #    binary lives inside the dyld shared cache. atos *can*
            #    sometimes resolve these via the cache, but not by path.
            # 2. Our own binary was deleted between trace capture and now
            #    (e.g. clean build, switched worktrees, .debug.dylib
            #    rebuilt with a different UUID).
            failures.append((path, "binary not at trace-recorded path"))
            for a in addrs:
                syms[a] = None
            continue

        cmd = ["atos", "-arch", arch, "-o", path, "-l", hex(load_addr)] + [hex(a) for a in addrs]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            failures.append((path, "atos timed out"))
            for a in addrs:
                syms[a] = None
            continue

        # atos may write a useful error to stderr (e.g. UUID mismatch). If
        # it returned non-zero, treat all addresses as unresolved AND
        # surface the reason — UUID mismatch is the most common cause and
        # the user needs to know to use the matching build / dSYM.
        if out.returncode != 0:
            err_one_line = (out.stderr or "").strip().splitlines()
            reason = err_one_line[0] if err_one_line else f"atos exit {out.returncode}"
            failures.append((path, reason))
            for a in addrs:
                syms[a] = None
            continue

        lines = out.stdout.strip().split("\n")
        if len(lines) != len(addrs):
            # atos returned an unexpected number of lines (rare). Don't
            # pair-mismatch them; mark all as unresolved.
            failures.append((path, f"atos returned {len(lines)} lines for {len(addrs)} addresses"))
            for a in addrs:
                syms[a] = None
            continue

        for a, line in zip(addrs, lines):
            # atos echoes the input address back when it can't resolve it
            # (no "(in <Binary>)" portion). Treat those as unresolved.
            if line.startswith("0x") and "(in " not in line:
                syms[a] = None
            else:
                syms[a] = line
    return syms, failures


# --- Main report ----------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("trace", type=Path, help="Path to .trace bundle")
    ap.add_argument("--window", default=None,
                    help='Phase window "START..END" (suffix-matched against phase names). '
                         'Default: entire trace.')
    ap.add_argument("--thread", default=None,
                    help='Thread name substring filter. Common: "main". Default: all threads.')
    ap.add_argument("--top", type=int, default=30, help="Max rows to print (default 30)")
    args = ap.parse_args()

    if not args.trace.is_dir():
        sys.exit(f"Not a .trace bundle: {args.trace}")

    print(f"Building image map from {args.trace.name}...", file=sys.stderr)
    images = build_image_map(args.trace)
    print(f"  {len(images)} unique binaries", file=sys.stderr)

    win_start, win_end = resolve_window(args.trace, args.window)
    if args.window:
        print(f"Window: {args.window}  ({win_start/1e9:.3f}s..{win_end/1e9:.3f}s)", file=sys.stderr)

    # Per-sample dedupe: count each unique address ONCE per sample. This
    # matters because addresses inside loops or recursion can appear many
    # times in a single backtrace; without dedupe the leaf inflates relative
    # to its actual sample-occurrence rate.
    addr_count = collections.Counter()
    samples_kept = 0
    threads = collections.Counter()
    for thread_name, addrs in parse_samples(args.trace, win_start, win_end, args.thread):
        samples_kept += 1
        threads[thread_name] += 1
        for a in set(addrs):
            addr_count[a] += 1

    if samples_kept == 0:
        sys.exit("No samples matched the window/thread filter.")

    print(f"Samples in window (matching thread filter): {samples_kept}", file=sys.stderr)

    # Group top-N addresses by binary for batched atos
    top = addr_count.most_common(args.top * 3)  # over-fetch; some may resolve to no symbol
    addrs_by_image = collections.defaultdict(list)
    addr_to_image = {}
    unmapped = []
    for addr, _ in top:
        img = find_image(images, addr)
        if img is None:
            unmapped.append(addr)
            continue
        key = (img["path"], img["load_addr"], img["arch"])
        addrs_by_image[key].append(addr)
        addr_to_image[addr] = img

    print("Symbolicating...", file=sys.stderr)
    syms, sym_failures = symbolicate(addrs_by_image)

    # Render
    print(f"\n# Hotspots — {args.trace.name}\n")
    if args.window:
        print(f"**Window:** `{args.window}` ({(win_end-win_start)/1e6:.1f} ms wall-clock)  ")
    if args.thread:
        print(f"**Thread filter:** `{args.thread}`  ")
    print(f"**Samples in window:** {samples_kept}  ")
    if not args.thread:
        # When unfiltered, show top threads so the user sees where time is going
        top_threads = ", ".join(
            f"{t.split(' (')[0] if t else '?'} ({c})" for t, c in threads.most_common(5)
        )
        print(f"**Top threads:** {top_threads}  ")
    print()
    print("| Samples | % | Symbol | Binary |")
    print("|---------|---|--------|--------|")

    rows_printed = 0
    for addr, count in addr_count.most_common():
        if rows_printed >= args.top:
            break
        pct = count / samples_kept * 100
        img = addr_to_image.get(addr)
        sym = syms.get(addr)
        if sym:
            # atos returns "Symbol (in Binary) (file:line)" — split out binary so
            # we can put it in its own column for sortability.
            m = re.match(r"^(.*?)\s*\(in (.+?)\)(\s*\(.+\))?\s*$", sym)
            if m:
                fn = (m.group(1) + (m.group(3) or "")).strip()
                binary = m.group(2)
            else:
                fn = sym
                binary = img["name"] if img else ""
        else:
            fn = f"`0x{addr:x}`"
            binary = img["name"] if img else "(unmapped)"
        # Escape pipe chars in symbol names so the markdown table doesn't break
        fn = fn.replace("|", "\\|")
        binary = binary.replace("|", "\\|")
        print(f"| {count} | {pct:.1f}% | {fn} | {binary} |")
        rows_printed += 1

    if unmapped:
        print()
        print(f"_{len(unmapped)} addresses had no binary mapping (skipped from table)._")

    if sym_failures:
        # Most rows showing as raw hex usually means the user's own binary
        # is missing or has a different UUID — worth surfacing distinctly
        # because the fix is "rebuild / point at the right .app", not "the
        # tool is broken".
        print()
        print("## Symbolication failures\n")
        print("These binaries had samples but couldn't be symbolicated:\n")
        for path, reason in sym_failures:
            print(f"- `{path}` — {reason}")
        print()
        print("_Hint: if these are your own binaries, the trace was captured "
              "against a build whose UUID no longer matches what's on disk. "
              "Rebuild against the same source (or point atos at the matching "
              ".dSYM) to recover symbols._")


if __name__ == "__main__":
    main()
