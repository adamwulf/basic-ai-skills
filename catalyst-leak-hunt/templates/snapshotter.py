#!/usr/bin/env python3
"""External snapshotter for the catalyst-leak-hunt skill.

Polls the in-app harness's sandbox dir for checkpoint-<label>.request
sentinels, runs `heap` and `vmmap` against the harness's PID, and
publishes results atomically. Exits when the `done` sentinel appears or
on hard timeout.

USAGE:
    Edit the two // CONFIGURE markers below for your app, then:
        python3 snapshotter.py

The harness writes:
    <SANDBOX>/getpid.txt                       (PID of the harness)
    <SANDBOX>/checkpoint-<label>.request       (ask for a snapshot)

This script writes:
    <SANDBOX>/heap-<label>.txt
    <SANDBOX>/vmmap-<label>.txt
    <SANDBOX>/checkpoint-<label>.done          (atomic via .tmp + rename)
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# ============================================================================
# CONFIGURE these two for your app:
# ----------------------------------------------------------------------------
APP_BUNDLE_ID = "com.example.YourApp"            # DEBUG bundle ID
SUBDIR_NAME = "leak-repro"                       # name of the dir inside Documents/
# ============================================================================
# Optional: comma-separated list of bundle IDs the snapshotter MUST NOT attach
# to. Helps prevent profiling the user's daily-driver release build by mistake.
FORBIDDEN_BUNDLE_IDS = {
    # "com.example.YourApp-appstore",
}

DIR = Path.home() / f"Library/Containers/{APP_BUNDLE_ID}/Data/Documents/{SUBDIR_NAME}"
POLL_SEC = 2.0
HARD_TIMEOUT_SEC = 15 * 60


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def app_path_for_pid(pid: int) -> str | None:
    try:
        out = subprocess.check_output(
            ["lsappinfo", "info", "-only", "bundlepath", "-pid", str(pid)],
            text=True, timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    for line in out.splitlines():
        if "=" in line:
            _, val = line.split("=", 1)
            return val.strip().strip('"')
    return None


def handle_request(req_path: Path) -> None:
    label = req_path.name.removeprefix("checkpoint-").removesuffix(".request")

    pid: int | None = None
    pidfile = DIR / "getpid.txt"
    if pidfile.is_file():
        try:
            pid = int(pidfile.read_text().strip())
        except ValueError:
            pass
    if pid is None:
        try:
            for line in req_path.read_text().splitlines():
                if line.startswith("pid="):
                    pid = int(line.split("=", 1)[1].strip())
        except (OSError, ValueError):
            pass
    if pid is None:
        log(f"WARN: no PID for {req_path.name}")
        return

    app_path = app_path_for_pid(pid)
    if app_path:
        for forbidden in FORBIDDEN_BUNDLE_IDS:
            if forbidden in app_path:
                log(f"ABORT: PID {pid} is forbidden ({forbidden}) at {app_path}.")
                return

    log(f"checkpoint {label}: snapshotting PID {pid} ({app_path or '<unknown path>'})")

    heap_final = DIR / f"heap-{label}.txt"
    heap_partial = DIR / f"heap-{label}.partial"
    vmmap_final = DIR / f"vmmap-{label}.txt"
    vmmap_partial = DIR / f"vmmap-{label}.partial"
    heap_ok = 0
    vmmap_ok = 0

    try:
        with heap_partial.open("wb") as f:
            proc = subprocess.run(["heap", str(pid)], stdout=f, stderr=subprocess.STDOUT, timeout=300)
        if proc.returncode == 0:
            heap_partial.replace(heap_final)
            heap_ok = 1
            size_mb = heap_final.stat().st_size / (1024 * 1024)
            log(f"  heap -> {heap_final.name} ({size_mb:.1f} MiB)")
        else:
            log(f"  heap exited {proc.returncode}; partial left at {heap_partial.name}")
    except subprocess.TimeoutExpired:
        log(f"  heap TIMEOUT (>300s); partial left at {heap_partial.name}")
    except Exception as e:
        log(f"  heap FAILED: {e}")

    try:
        with vmmap_partial.open("wb") as f:
            proc = subprocess.run(["vmmap", "-summary", str(pid)], stdout=f, stderr=subprocess.STDOUT, timeout=120)
        if proc.returncode == 0:
            vmmap_partial.replace(vmmap_final)
            vmmap_ok = 1
            log(f"  vmmap -> {vmmap_final.name}")
        else:
            log(f"  vmmap exited {proc.returncode}; partial left at {vmmap_partial.name}")
    except subprocess.TimeoutExpired:
        log(f"  vmmap TIMEOUT (>120s); partial left at {vmmap_partial.name}")
    except Exception as e:
        log(f"  vmmap FAILED: {e}")

    req_path.unlink(missing_ok=True)
    done_tmp = DIR / f"checkpoint-{label}.done.tmp"
    done_final = DIR / f"checkpoint-{label}.done"
    done_tmp.write_text(
        f"completed_at={int(time.time())}\nheap_ok={heap_ok}\nvmmap_ok={vmmap_ok}\n"
    )
    done_tmp.replace(done_final)
    log(f"checkpoint {label}: done (heap_ok={heap_ok} vmmap_ok={vmmap_ok})")


def main() -> int:
    if not DIR.is_dir():
        log(f"Watch dir does not exist yet: {DIR}")
        log(f"Make sure the app launched with the harness activated.")
        return 1

    log(f"Watching {DIR} for checkpoint requests...")
    start = time.monotonic()

    while True:
        if (DIR / "done").is_file():
            log("Harness signaled done. Exiting.")
            return 0
        if time.monotonic() - start > HARD_TIMEOUT_SEC:
            log(f"Hard timeout after {HARD_TIMEOUT_SEC}s. Exiting.")
            return 2

        requests = sorted(DIR.glob("checkpoint-*.request"))
        for req in requests:
            handle_request(req)

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    sys.exit(main())
