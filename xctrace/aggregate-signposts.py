#!/usr/bin/env python3
"""
Aggregate os_signpost intervals from an xctrace bundle.

Pairs Begin/End events per (thread, signpost-name) using a stack so reentrant
intervals (e.g. recursive lock acquisition) are handled correctly. Prints
count / total / mean / stdev / max / min per signpost name.

Usage:
    python3 aggregate-signposts.py <trace-bundle.trace> [--name <pattern>]
                                                        [--per-test]
                                                        [--keep-xml <path>]

Flags:
    --name <substr>   Filter signpost names (case-insensitive substring match)
    --per-test        Bucket signpost intervals by enclosing XCTestCase
    --keep-xml <path> Preserve the exported os-signpost XML at the given path
                      (otherwise it goes to a tempdir that's cleaned up)

The trace's os-signpost table is exported via xctrace, then parsed locally.
"""

import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict


def export_signposts(trace_path: str, dest_xml: str) -> None:
    """Run xctrace export to dump the os-signpost table to XML.

    Requires `xcrun` on PATH (which gives access to the Xcode toolchain's
    xctrace). On a Mac with Xcode installed and command-line tools selected,
    this is the case. If not, install Xcode or run `xcode-select --install`.
    """
    if shutil.which("xcrun") is None:
        sys.stderr.write(
            "error: `xcrun` not found on PATH. Install Xcode or run "
            "`xcode-select --install`.\n"
        )
        sys.exit(2)
    cmd = [
        "xcrun", "xctrace", "export",
        "--input", trace_path,
        "--xpath", '/trace-toc/run/data/table[@schema="os-signpost"]',
        "--output", dest_xml,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def parse_signposts(xml_path: str):
    """Yield (timestamp_ns, thread_id, event_type, signpost_name, subsystem) per row.

    The XML uses id/ref backreferences (id="N" on first occurrence, ref="N"
    on subsequent occurrences). We resolve them as we stream by remembering
    the most recent value for each id we've seen.
    """
    # We do streaming parse so we don't blow up on 1M-line files.
    seen = {}  # id -> (kind, value)

    def remember(kind, elem):
        eid = elem.get("id")
        if eid is not None:
            value = _value_for(kind, elem)
            seen[eid] = value
            return value
        ref = elem.get("ref")
        if ref is not None:
            return seen.get(ref)
        return _value_for(kind, elem)

    def _value_for(kind, elem):
        # event-time: nanoseconds since trace start (text)
        # event-type: "Begin" or "End" (text)
        # signpost-name: text
        # tid: hex string for thread id (text)
        # subsystem: text
        if kind == "tid":
            return elem.text or ""
        return elem.text or ""

    # Stream rows.
    context = ET.iterparse(xml_path, events=("end",))
    for _, elem in context:
        if elem.tag != "row":
            continue
        try:
            row = _decode_row(elem, seen)
            if row is not None:
                yield row
        finally:
            elem.clear()


def _decode_row(row_elem, seen):
    ts_ns = None
    tid = None
    event_type = None
    name = None
    subsystem = None
    metadata = None  # os-log-metadata text (XCTest carries the test name here)

    for child in row_elem:
        tag = child.tag
        # Resolve id/ref. Apply child-elements that bake in a value.
        if tag == "event-time":
            v = _resolve(child, seen)
            if v is not None:
                ts_ns = int(v)
        elif tag == "thread":
            # The thread element wraps tid + process + device-session. We want tid.
            for grand in child:
                if grand.tag == "tid":
                    tv = _resolve(grand, seen)
                    if tv is not None:
                        tid = tv
                    break
            # Or, if `<thread ref="..."/>`, look up.
            ref = child.get("ref")
            if ref is not None and tid is None:
                # We can't resolve through the thread ref alone (it points to
                # a previous <thread> element which itself contains a tid).
                # We stored <tid> separately when first seen. But because
                # `<thread ref="2"/>` reuses the whole element, fish the tid
                # out by remembering thread-id->tid.
                tid = seen.get("__thread_tid_" + ref)
            elif tid is not None and child.get("id"):
                # Remember this thread element's tid for later refs.
                seen["__thread_tid_" + child.get("id")] = tid
        elif tag == "event-type":
            v = _resolve(child, seen)
            if v is not None:
                event_type = v
        elif tag == "signpost-name":
            v = _resolve(child, seen)
            if v is not None:
                name = v
        elif tag == "subsystem":
            v = _resolve(child, seen)
            if v is not None:
                subsystem = v
        elif tag == "os-log-metadata":
            # The metadata may have an inline `fmt` attr that summarises it
            # cleanly; xctrace formats the test name into that.
            md = child.get("fmt")
            if md is None:
                ref = child.get("ref")
                if ref is not None:
                    md = seen.get("__metadata_fmt_" + ref)
            elif child.get("id"):
                seen["__metadata_fmt_" + child.get("id")] = md
            metadata = md

    if ts_ns is None or tid is None or event_type is None or name is None:
        return None
    return (ts_ns, tid, event_type, name, subsystem, metadata)


def _resolve(elem, seen):
    eid = elem.get("id")
    if eid is not None:
        v = elem.text or ""
        seen[eid] = v
        return v
    ref = elem.get("ref")
    if ref is not None:
        return seen.get(ref)
    return elem.text


def aggregate(rows, name_filter=None, per_test=False):
    """Pair Begin/End per (thread, name) using a stack.

    Returns a dict: bucket -> {name -> [duration_ns, ...]}.
    `bucket` is "ALL" by default. With per_test=True, buckets are XCTestCase
    names extracted from the os-log-metadata of XCTestCase signposts.

    Note: the bucketing is by interval *end time* — an interval that begins
    inside a test but ends after `measure {}` returns (rare) gets attributed
    to the test it ended in. Good enough for our use.
    """
    stacks = defaultdict(list)  # (tid, name) -> [start_ns, ...]

    # XCTestCase intervals: list of (start_ns, end_ns, test_name).
    # We need end-time, so we accumulate as we see Ends.
    test_intervals = []  # filled in pass 1

    rows_list = list(rows)  # we need 2 passes if per_test

    if per_test:
        # First pass: build test_intervals from XCTestCase Begin/End pairs.
        # These are emitted by XCTest itself (subsystem com.apple.dt.XCTest).
        starts = {}  # tid -> (start_ns, test_name)
        for ts_ns, tid, etype, name, subsystem, metadata in rows_list:
            if name != "XCTestCase":
                continue
            if etype == "Begin":
                starts[tid] = (ts_ns, metadata or "(unknown test)")
            elif etype == "End":
                if tid in starts:
                    s, tname = starts.pop(tid)
                    test_intervals.append((s, ts_ns, tname))
        test_intervals.sort()

    def find_bucket(end_ns):
        if not per_test:
            return "ALL"
        # Find the test interval whose [start, end] contains end_ns.
        # test_intervals is sorted by start_ns; linear scan is fine since N is
        # tiny (one per test method).
        for s, e, tname in test_intervals:
            if s <= end_ns <= e:
                return tname
        return "(outside any test)"

    durations = defaultdict(lambda: defaultdict(list))  # bucket -> name -> [dur]

    for ts_ns, tid, etype, name, subsystem, metadata in rows_list:
        if name_filter and name_filter.lower() not in name.lower():
            continue
        if etype == "Begin":
            stacks[(tid, name)].append(ts_ns)
        elif etype == "End":
            stack = stacks.get((tid, name))
            if not stack:
                continue
            start = stack.pop()
            duration = ts_ns - start
            bucket = find_bucket(ts_ns)
            durations[bucket][name].append(duration)

    return durations


def fmt_ns(ns: float) -> str:
    if ns < 1_000:
        return f"{ns:.0f} ns"
    if ns < 1_000_000:
        return f"{ns/1_000:.2f} μs"
    if ns < 1_000_000_000:
        return f"{ns/1_000_000:.2f} ms"
    return f"{ns/1_000_000_000:.3f} s"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("trace", help=".trace bundle path")
    p.add_argument("--name", default=None,
                   help="Substring filter on signpost name (case-insensitive)")
    p.add_argument("--per-test", action="store_true",
                   help="Bucket signpost durations per XCTestCase")
    p.add_argument("--keep-xml", default=None,
                   help="Optional path: keep the exported os-signpost XML at this location")
    args = p.parse_args()

    if not os.path.isdir(args.trace):
        sys.stderr.write(f"Trace bundle not found: {args.trace}\n")
        sys.exit(1)

    tmpdir = None
    try:
        if args.keep_xml:
            xml_path = args.keep_xml
        else:
            tmpdir = tempfile.mkdtemp(prefix="aggsig-")
            xml_path = os.path.join(tmpdir, "signposts.xml")
        sys.stderr.write(f"Exporting os-signpost table from {args.trace}...\n")
        export_signposts(args.trace, xml_path)

        rows = parse_signposts(xml_path)
        durations_by_bucket = aggregate(rows, name_filter=args.name, per_test=args.per_test)
    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)

    if not durations_by_bucket:
        sys.stderr.write("No matching signposts found.\n")
        sys.exit(2)

    for bucket in sorted(durations_by_bucket.keys()):
        durations = durations_by_bucket[bucket]
        if not durations:
            continue
        rows_out = []
        for name, ds in durations.items():
            n = len(ds)
            total = sum(ds)
            mean = total / n
            mx = max(ds)
            mn = min(ds)
            if n > 1:
                var = sum((d - mean) ** 2 for d in ds) / (n - 1)
                stdev = math.sqrt(var)
            else:
                stdev = 0.0
            rows_out.append((name, n, total, mean, stdev, mx, mn))

        rows_out.sort(key=lambda r: -r[2])  # by total desc

        name_w = max(len(r[0]) for r in rows_out)
        header_fmt = f"{{:<{name_w}}}  {{:>8}}  {{:>11}}  {{:>10}}  {{:>10}}  {{:>10}}  {{:>10}}"

        if args.per_test:
            sys.stdout.write("\n")
            sys.stdout.write(f"=== {bucket} ===\n")
        sys.stdout.write(header_fmt.format("name", "count", "total", "mean", "stdev", "max", "min") + "\n")
        sys.stdout.write("-" * (name_w + 70) + "\n")
        for name, n, total, mean, stdev, mx, mn in rows_out:
            sys.stdout.write(header_fmt.format(name, n, fmt_ns(total), fmt_ns(mean), fmt_ns(stdev), fmt_ns(mx), fmt_ns(mn)) + "\n")


if __name__ == "__main__":
    main()
