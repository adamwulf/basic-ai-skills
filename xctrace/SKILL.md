---
name: xctrace
description: Profile macOS/Catalyst/iOS apps with Instruments via the xctrace CLI — record cold launches, attach to running processes, export tables to XML, symbolicate stacks. Use for launch time, frame hitches, CPU hotspots, memory. Also handles the LaunchServices gotcha where `xctrace --launch` profiles the wrong binary when multiple `.app`s share a bundle ID (worktrees, stale DerivedData).
allowed-tools: Bash, Read, Write
---

End-to-end recipe for capturing and analyzing Instruments traces using `xctrace` (the headless Instruments CLI). No GUI required.

## When to use

- Cold-launch profiling (time-to-first-frame, time-to-foreground)
- Steady-state CPU profiling of a running app
- Profiling a specific user flow (manual or automated)
- Finding which framework's static initializer is heavy
- Tracking down main-thread work that causes frame hitches
- Comparing two builds (record both, diff phase tables / sample distributions)
- Investigating memory allocations, file activity, network activity
- **Confirming `xctrace --launch` actually ran your build** — when you have multiple `.app`s with the same bundle ID across git worktrees, `~/Library/Developer/Xcode/DerivedData/`, `/Applications/`, etc. (see "LaunchServices gotcha" under Mode A)

## High-level flow

1. **Pick a template** that matches the question you're asking
2. **Pick a recording mode** — launch fresh, attach to a running process, or wrap a scripted flow
3. **Record** with `xctrace record`
4. **Inspect the table of contents** to see what schemas the trace contains
5. **Export** the relevant tables to XML
6. **Symbolicate** stacks using `atos` against the symbol archives in the trace bundle (or just open the trace in Instruments GUI)

## 1. Choose a template

`xctrace list templates` shows what's available. Most useful:

| Template | Use case |
|---|---|
| **App Launch** | Cold launch — adds life-cycle phase markers (process creation, static init, willFinishLaunching, sceneWillConnectTo, Initial Frame Rendering, Foreground) |
| **Time Profiler** | Generic CPU sampling. Best for steady-state and post-launch flows |
| **Allocations** | Memory allocations + leaks |
| **Leaks** | Just leaks |
| **System Trace** | Kernel + dyld + scheduling. Heavy, use sparingly |
| **Animation Hitches** | Dropped frames / scroll jank |
| **File Activity** | Disk I/O |
| **Network** | URLSession / socket activity |
| **Swift Concurrency** | Tasks, actors, await points |
| **Logging** | os_log / signposts only — very lightweight |
| **Activity Monitor** | High-level CPU/memory/disk/network rollup |

**Rule of thumb:** "App Launch" for launch, "Time Profiler" for everything else, "Allocations" when memory is the question.

## 2. Choose a recording mode

xctrace can attach to a process in three ways:

### Mode A — `--launch`: cold start

Launches the app fresh. Best for launch profiling.

```bash
# Kill by bundle ID, not process name — see "Killing the right app" below.
PID=$(lsappinfo info -only pid -app com.example.MyApp | awk -F'=' '{print $2}')
[ -n "$PID" ] && kill -9 "$PID"

xctrace record \
  --template "App Launch" \
  --launch /path/to/MyApp.app \
  --time-limit 15s \
  --output ~/launch.trace
```

#### Killing the right app (bundle ID, not process name)

`pkill -x MyApp` matches by **process name**, not bundle ID. If multiple builds of the app are installed (App Store + dev build, Setapp + worktree builds, TestFlight + Xcode build), they all share the same process name and `pkill` will kill all of them. That's almost never what you want during profiling.

Use bundle ID instead:

```bash
# Get the PID for a specific bundle ID (empty if not running)
PID=$(lsappinfo info -only pid -app com.example.MyApp | awk -F'=' '{print $2}')
[ -n "$PID" ] && kill -9 "$PID"
```

This is one shell invocation — no chaining issue with single-command rules. Alternatives:

- **Graceful quit:** `osascript -e 'tell application id "com.example.MyApp" to quit'`
- **Path-based pkill:** `pkill -f "DerivedData/Build/Products/Debug/MyApp.app"` (matches the full command line, useful when the binary is in a known location)

`pkill -x` is fine when you're certain only one build is installed, but bundle-ID targeting has no downside and works in every case.

#### LaunchServices gotcha (Mac/Catalyst `.app` bundles)

For `.app` bundles, `--launch <path>` (and `open <path>`) routes through LaunchServices, not `posix_spawn`. LS reads `CFBundleIdentifier` from the `.app`'s Info.plist, then **launches the highest-ranked registered `.app` for that bundle ID system-wide** — which can be a stale build in another `DerivedData/`, a `/Applications/` copy, or a TestFlight install. The path you passed becomes a hint, not a guarantee. CLI binaries (no `.app` wrapper) `posix_spawn` directly and aren't affected.

**Run the prune+force-register pair before _every_ `xctrace --launch`, not just once per session.** `lsregister -f` only puts your path at the front of the list temporarily. Xcode indexing, Spotlight, Setapp, an LS rescan, or another `xcodebuild` finishing in a sibling worktree can all reshuffle the order between traces. If you re-trace and skip the prune, LS may pick a different `.app` than the previous run — and you won't notice until you compare phase numbers and they look wrong, or you `ps` mid-run and see the wrong path. The cheap, reliable habit: prune → `-f` → `xctrace --launch` → verify with `ps`. Every time.

Verify after `--launch` with the actual launched path:

```bash
ps -ax -o pid,command | grep -i MyApp.app/Contents/MacOS/MyApp | grep -v grep
```

If the path doesn't match what you passed, LS substituted. Force LS to prefer your build:

```bash
lsregister -f /path/to/your/MyApp.app
```

> **Note:** `lsregister` is invokable as a bare command on recent macOS — it's on `$PATH` (resolved via the LaunchServices framework's Support directory). The fully-qualified path `/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister` still works, but is rarely needed. Examples below use the bare form.

`-f` adds your path and bumps it to the front for that bundle ID; it does **not** remove old candidates. If many `.app`s with the same ID accumulate (common with git worktrees + Xcode incremental builds), `-f` alone may not be enough — LS still picks a higher-ranked stale one. Inspect the pile with:

```bash
lsregister -dump | grep -E "path:.*MyApp\.app"
```

To bulk-prune stale registrations, use the helper script that ships with this skill:

```bash
# Dry-run: list every registered MyApp.app under any DerivedData/* dir.
python3 ~/.claude/skills/xctrace/prune-lsregister.py com.example.MyApp

# Unregister them, keeping only the build you want.
python3 ~/.claude/skills/xctrace/prune-lsregister.py com.example.MyApp \
    --keep /path/to/keep/MyApp.app --apply
```

The script is segment-aware: only paths whose components include a literal `DerivedData` (or `DerivedData2`/`DerivedData3` — Xcode auto-numbers) directory match. Substrings like `MyDerivedData` are ignored. Installed copies in `/Applications/`, Setapp wrappers under `/Library/Application Support/Setapp/`, and TestFlight installs are never touched. Use `--all` to widen the filter, `--keep PATH` (repeatable) to spare specific paths.

Other useful `lsregister` forms: `-u <path>` unregisters one path; `-R -f -domain user -domain local -domain system` rebuilds the whole DB (heavy — only when LS is genuinely confused).

Don't be tempted to change your debug build's `CFBundleIdentifier` to dodge the issue. App-group, keychain, iCloud, push-token, and entitlement lookups are all keyed on team-id+bundle-id; a different ID makes the trace measure something other than real launch behavior.

### Mode B — `--attach`: existing process

Attaches to a running PID or process name. Use for steady-state profiling, or when you want to start recording right before triggering some action.

```bash
xctrace record \
  --template "Time Profiler" \
  --attach MyApp \
  --time-limit 30s \
  --output ~/steady.trace
```

You can attach by PID (`--attach 12345`) or name (`--attach MyApp`). For ambiguous names, use PID.

### Mode C — wrap a scripted flow

For profiling a specific automated flow (e.g. an in-app self-test, AppleScript-driven UI, XCUITest-style automation):

```bash
# Start recording attached to the app (in background)
xctrace record \
  --template "Time Profiler" \
  --attach MyApp \
  --time-limit 60s \
  --output ~/flow.trace &
RECORD_PID=$!

# Trigger the in-app automation. Examples:
#   - osascript flow.scpt                        (AppleScript)
#   - curl http://localhost:9999/run-flow        (in-app HTTP debug endpoint)
#   - open "myapp://debug/run-benchmark"         (URL scheme)
#   - your own debug menu item triggered via accessibility
osascript /path/to/flow.scpt

# Optionally stop recording early when the flow is done
kill -INT $RECORD_PID
wait $RECORD_PID
```

The combination of an in-app debug trigger + xctrace attach is a powerful pattern for repeatable benchmarks. If your app exposes a debug endpoint (URL scheme, AppleScript handler, or HTTP server), you can build deterministic traces of any user flow.

#### Adding a flow trigger to your app

Common patterns to make flows scriptable:

- **URL scheme** — register `myapp://debug/<flow>` and handle in `application(_:open:)`. Trigger with `open myapp://debug/...`.
- **AppleScript handler** — implement an `NSApplication` script command. Trigger with `osascript`.
- **Local HTTP debug server** (debug builds only) — listen on `127.0.0.1:N`, accept `GET /run/<flow>`. Trigger with `curl`.
- **Accessibility / XCUITest** — drive the real UI via `osascript -e 'tell application "System Events" ...'` or a UI test target.

Wrap each flow in `os_signpost(.begin/.end, ...)` so the trace shows exactly where each step ran (see "Tips" below).

### Common record flags

- `--time-limit 15s` — auto-stops after duration. Omit to record until you `kill -INT` it.
- `--output <path>` — `.trace` is a *bundle directory*, not a file. Without this, output lands in the current working directory.
- `--launch -- <app> <arg1> <arg2>` — pass arguments to the launched app (separator is `--`).
- `--env KEY=VALUE` — env vars for the launched process (e.g. `DYLD_PRINT_STATISTICS=1`, `OS_ACTIVITY_MODE=disable`).
- `--device <udid|name>` — target an iOS simulator or device. List with `xctrace list devices`.
- `--package <path>` — load a custom Instruments package.

**Note:** older docs reference a `--mode immediate` flag for continuous-write recording. That flag has been removed from the modern `xctrace record` CLI (Xcode 26+ rejects it as "unrecognized option"). Recording is always deferred-write today; if a long trace serializes too slowly at the end, shorten the time-limit or pick a lighter template, don't add `--mode`.

### Exit codes

xctrace may exit **54** even on success ("Reached specified time limit, ending recording..."). Don't trust the exit code alone — check that the output bundle exists:

```bash
test -d ~/x.trace && echo "trace saved"
```

### iOS simulators and devices

```bash
xcrun xctrace list devices          # find UDID or name

xctrace record \
  --device "iPhone 15 Pro Simulator" \
  --template "App Launch" \
  --launch com.example.MyApp \
  --time-limit 15s \
  --output ~/x.trace
```

For real devices, the bundle ID is launched on-device and the trace is pulled back automatically.

## 3. Inspect the table of contents

The trace bundle contains many tables. Listing them tells you what's available:

```bash
xctrace export --input ~/x.trace --toc | head -80
```

Key tables, by template:

| Schema | Available in | What it gives you |
|---|---|---|
| `life-cycle-period` | App Launch | Phase timeline: process creation → foreground |
| `dyld-activity-interval` | App Launch, System Trace | dyld events: Map Image, Apply Fixups, Static Initializer, dlopen |
| `dyld-library-load` | App Launch, System Trace | Every dylib loaded with base address + UUID + path (needed for symbolication) |
| `time-sample` | Time Profiler, App Launch | Sampled callstacks (~5ms / 200 Hz default). Stacks are address arrays referencing the symbol archive |
| `time-profile` | Time Profiler | Aggregated time-profile with weights |
| `os-signpost` | Most templates | Your `os_signpost()` events with begin/end pairs and metadata |
| `thread-state` | Most | Thread blocked/running over time |
| `virtual-memory` | App Launch, System Trace | VM activity |
| `allocation` | Allocations | Per-allocation events with stacks |
| `vm-allocation` | Allocations | Virtual memory regions |
| `leaks` | Leaks | Leaked allocations |
| `process-info` | All | Process metadata |
| `cpu-narrative` | All | Per-CPU activity ribbons |
| `frame-lifetime` | Animation Hitches | Per-frame render time + hitch reasons |

## 4. Export tables to XML

`xctrace export` outputs XML. Direct it to a file — these can get large.

### Phase timeline (launch traces only)

```bash
xctrace export \
  --input ~/x.trace \
  --xpath '/trace-toc/run/data/table[@schema="life-cycle-period"]' \
  --output /tmp/phases.xml
```

Small XML file with one `<row>` per phase and a `fmt="..."` attribute showing human-readable durations (`860.67 ms`). Read directly. Typical phases observed (in order):

```
Initializing - Process Creation
Initializing - System Interface Initialization
Initializing - Static Runtime Init           ← +load, dyld, framework binding
Launching - UIKit Initialization
Launching - UIKit Scene Creation
Launching - willFinishLaunchingWithOptions()
Launching - didFinishLaunchingWithOptions()
Launching - AppKit Initialization            (Mac Catalyst only)
Launching - AppKit Scene Creation            (Mac Catalyst only)
Launching - applicationWillFinishLaunching()
Launching - applicationDidFinishLaunching()
Launching - sceneWillConnectTo()
Launching - sceneWillEnterForeground()
Launching - Initial Frame Rendering
Foreground                                   ← user can see and interact
Background
```

The gap between "Initial Frame Rendering" end and "Foreground" start is often the largest unexplained chunk — typically synchronous work in your scene delegate's startup observer, first VC layout, or first data fetch. Note: if `--time-limit` is too short, the trace can end before "Foreground" fires (you'll see phases up through "Initial Frame Rendering" only). Bump `--time-limit` if you need to capture user-visible interactivity.

### Signposts (use these everywhere)

```bash
xctrace export \
  --input ~/x.trace \
  --xpath '/trace-toc/run/data/table[@schema="os-signpost"]' \
  --output /tmp/signposts.xml
```

Signposts give you human-named phase markers. If you've wrapped a flow with `os_signpost(.begin/.end, ...)`, this table shows each region with start time, duration, and any metadata you passed.

**Caveat — `--template "App Launch" --instrument "os_signpost"` may not capture early launch signposts.** Observed once: an App Launch trace recorded with `--instrument "os_signpost"` produced an `os-signpost` table that included later-firing signposts from the app's subsystem (periodic background work) but was missing signposts the same app emits during launch. Whether the cause is instrument warmup, a code path that didn't run in that particular launch, a binary mismatch, or something else hasn't been pinned down. If launch-time signposts seem to be missing, verify they actually fire at runtime first (e.g. `log stream --predicate 'subsystem == "MyApp"'` while launching) before assuming the trace pipeline is dropping them.

### Time-sample stacks

```bash
xctrace export \
  --input ~/x.trace \
  --xpath '/trace-toc/run/data/table[@schema="time-sample"]' \
  --output /tmp/samples.xml
```

Each `<row>` references a callstack by `frag <id>` with raw addresses. Symbolication is a separate step (next section). Default sampling rate is 5 ms.

### Allocations

```bash
xctrace export \
  --input ~/x.trace \
  --xpath '/trace-toc/run/data/table[@schema="allocation"]' \
  --output /tmp/allocations.xml
```

### dyld activity (framework load times)

```bash
xctrace export \
  --input ~/x.trace \
  --xpath '/trace-toc/run/data/table[@schema="dyld-activity-interval"]' \
  --output /tmp/dyld.xml
```

**Caveat:** in many traces, `dyld-activity-interval` collapses Map Image / Apply Fixups / Objc Image Init / Objc Map into a single summary row each — not per-library. The per-library breakdown lives in kdebug events and is hard to extract via XML alone. For per-framework load cost:

```bash
xctrace record --env DYLD_PRINT_STATISTICS=1 ...
```

`DYLD_PRINT_STATISTICS=1` causes dyld to print per-library load and init times to stderr — capture them by also redirecting stderr from the launched process (see "Capture stderr" below).

### Filter by time window

XPath supports predicates. To get only samples within a specific window (in nanoseconds since trace start):

```bash
xctrace export \
  --input ~/x.trace \
  --xpath '/trace-toc/run/data/table[@schema="time-sample"]/row[sample-time >= 1420000000 and sample-time <= 2600000000]'
```

Pair this with signposts: read the signposts table to find the start/end ns of a flow region, then narrow the time-sample query to that window.

## 5. Symbolicate callstacks

The trace bundle ships with everything needed for offline symbolication — but for one-off questions, opening the trace in the Instruments GUI is faster than building a symbolicator.

### The trace bundle layout

```
~/x.trace/
├── form.template
├── instrument_data
├── corespace/
├── shared_data
└── symbols/
    ├── MANIFEST.plist
    └── stores/
        ├── 02960C1F-...-symbolsarchive
        └── ...
```

Symbol archives are opaque, but `atos` resolves addresses if you know:

1. The owning binary's load address (from `dyld-library-load` table)
2. The binary's UUID (also in `dyld-library-load`)
3. A symbol-rich copy of the binary (the .app for your code; system libraries are in `~/Library/Developer/Xcode/iOS DeviceSupport` for devices, or `/System/Library` and the dyld shared cache for macOS)

### Resolve a single address

```bash
atos -o /path/to/MyApp.app/Contents/MacOS/MyApp \
     -l 0x104000000 \                # binary's load address from the trace
     -arch arm64e \                  # arm64e on Apple Silicon, x86_64 on Intel; verify with `lipo -info`
     0x1045c49c0
```

For system libraries, point `-o` at the actual dylib path from `dyld-library-load`. On recent macOS the dyld shared cache is in `/System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld/dyld_shared_cache_*` — atos handles this transparently if given the right path.

### Bulk symbolication

For ranking heaviest functions over a window:

1. Parse `dyld-library-load` → list of `(load_addr, length, UUID, path)`
2. Parse `time-sample` → for each sample, walk the address array
3. Group addresses per binary by load-address range
4. Batch `atos -o <binary> -l <load_addr> -arch <arch> <addrs...>`
5. Build a frequency table: `symbol → sample count`

```python
# Skeleton — write to a file, run with python3
import re, subprocess
from collections import Counter

TRACE = "~/x.trace"

# 1. Parse dyld-library-load → image map
# 2. Parse time-sample stacks → list of address arrays
# 3. Group addresses per binary
# 4. Run atos in batch:
#    atos -arch arm64e -o <binary> -l <load_addr> < addrs.txt
# 5. Counter → top N
```

### When to skip the script and open the GUI

If headless analysis isn't pinning down the answer, open the trace in Instruments — it resolves symbols automatically and gives you flame graphs, call tree pivots, weight sorting, etc.:

```bash
open ~/x.trace
```

Open in GUI is often the fastest path for a one-off question. Reserve the headless symbolication pipeline for: automation (CI), aggregating across many traces, or when the GUI is unavailable.

## 6. Headless report scripts

Three helper scripts ship with this skill for the most common questions. All produce text reports — pipe to a file or render in a chat.

### `phases.py` — phase timeline

```bash
python3 ~/.claude/skills/xctrace/phases.py ~/x.trace                    # single trace
python3 ~/.claude/skills/xctrace/phases.py ~/new.trace --baseline ~/old.trace   # diff
```

Reads the `life-cycle-period` table and prints every phase with its duration. Computes the two numbers you usually want from a launch trace:

- **Process start → Foreground**: total cold-launch wall clock to interactivity.
- **Initial Frame → Foreground**: post-first-frame setup. The user sees the first frame, but this work delays input acceptance — usually the most actionable number.

The `--baseline` form prints a side-by-side delta. Repeated phase names (e.g. "Launching - UIKit Scene Creation" appears multiple times in a real launch) are disambiguated with `(#2)`, `(#3)` suffixes so the diff matches them in order.

Requires the trace to have phases — i.e. captured with `--launch` against an App Launch or Time Profiler template. `--attach` traces have no phases; the script exits with a clear error.

### `hotspots.py` — symbolicated sample histogram

```bash
python3 ~/.claude/skills/xctrace/hotspots.py ~/x.trace
python3 ~/.claude/skills/xctrace/hotspots.py ~/x.trace \
    --window 'willFinishLaunchingWithOptions()..Foreground' \
    --thread main \
    --top 30
```

Streams `time-sample`, filters by phase window and thread name, dedupes addresses per-sample (so deep recursion doesn't dominate), maps each address to its binary, and symbolicates via batched `atos`.

Key defaults:
- `--window START..END` is **suffix-matched** against phase names. `'Foreground'` matches the `Foreground` phase exactly; `'willFinishLaunchingWithOptions()'` matches `'Launching - willFinishLaunchingWithOptions()'`. With no `--window`, the entire trace is included.
- `--thread name` is a case-insensitive substring filter against the thread label. `--thread main` matches the main thread; omit it to see all threads (with a top-threads-by-sample-count summary).
- `--top N` caps the table at N rows (default 30).

The image map is built by harvesting **every** `<binary>` element across the trace's `dyld-activity-interval` and `time-sample` exports — not just the `dyld-library-load` table, which is often empty for shared-cache frameworks. This avoids the silent-misattribution bug where addresses in the gap between two known load addresses get assigned to the wrong binary.

Anything `atos` can't resolve (binary missing, UUID mismatch, address inside the dyld shared cache without a standalone path) shows as raw hex rather than a guessed symbol. A trailing "Symbolication failures" section lists the binaries that couldn't be resolved with one-line reasons — most often "binary not at trace-recorded path" (system shared cache, expected) or "binary UUID mismatch" (your own build was rebuilt or a different worktree was used).

When most of your own code shows as raw hex: the build whose UUID is in the trace no longer exists on disk. Capture a fresh trace, or save a copy of the matching `.app` next to each trace.

### `aggregate-signposts.py` — count + duration stats per signpost name

```bash
python3 ~/.claude/skills/xctrace/aggregate-signposts.py ~/x.trace
python3 ~/.claude/skills/xctrace/aggregate-signposts.py ~/x.trace --name lock
python3 ~/.claude/skills/xctrace/aggregate-signposts.py ~/x.trace --per-test
python3 ~/.claude/skills/xctrace/aggregate-signposts.py ~/x.trace --keep-xml /tmp/signposts.xml
```

Streams the `os-signpost` table, pairs Begin/End events per `(thread, signpost-name)` using a per-thread stack so reentrant intervals (e.g. recursive lock acquisition) are handled correctly, and prints one row per signpost name with `count` / `total` / `mean` / `stdev` / `max` / `min`.

Key flags:
- `--name <substr>` — case-insensitive substring filter on signpost name. Use to focus on a single subsystem (`--name lock`, `--name txn`).
- `--per-test` — bucket signpost intervals by enclosing `XCTestCase`. Reads XCTest's own signposts (subsystem `com.apple.dt.XCTest`) to build test-name intervals, then attributes each LogDriver-side interval to whichever test it ended in. Use when one trace covers multiple tests; otherwise the default `ALL` bucket is fine. Note: the multi-test signpost-drop quirk in xctrace 26.0 (see "Pitfalls" below) means `--per-test` should usually be paired with one-test-per-trace recordings, where `--per-test` is redundant.
- `--keep-xml <path>` — preserve the exported os-signpost XML at the given path (default: ephemeral tempdir). Useful for debugging the parser or for downstream re-analysis.

Output is plain text, sorted by total duration descending. Sample row format:

```
name                count        total        mean       stdev         max         min
--------------------------------------------------------------------------------
sql_lock          103960     2.054 s    19.76 μs   339.62 μs    27.42 ms     5.92 μs
```

The pairing logic uses a per-thread stack rather than a flat counter, so a `RecursiveMutex` that re-acquires itself N times still produces N independent intervals (each with its own duration). Re-entry counts are visible as a higher `count` than would otherwise be expected for the equivalent non-recursive lock.

**Use cases:**
- **Records-per-window throughput** for wall-clock-bounded contention tests: count of `sql_txn_write` = records written, count of `sql_txn_read` = records read. The `count` column is the metric.
- **Lock-hold time distributions**: total / mean / max for each lock signpost. A regression that holds a lock longer per acquire shows up as a rise in `mean` even when `count` is unchanged.
- **Cache pressure**: count of `queries_cache_clear` or similar invalidation signposts per N writes tells you how often invalidation fires.

If your trace was recorded with custom-subsystem signposts and the script reports "No matching signposts found," the multi-test quirk likely dropped them — re-record one test per trace (see "xctrace 26.0 quirks" pitfall below).

### When these scripts aren't enough

For exploratory questions ("what's that AppKit frame doing?", "where exactly is the main thread blocked?"), open the trace in Instruments — the GUI handles dyld shared cache symbolication natively, supports flame graphs and call-tree pivots, and is much faster for one-off digging. The scripts are for repeatable headless runs where you know what you're looking for.

## Tips

### Add os_signpost to mark interesting regions

```swift
import os.signpost
let log = OSLog(subsystem: "com.example.MyApp", category: .pointsOfInterest)

let id = OSSignpostID(log: log)
os_signpost(.begin, log: log, name: "load_database", signpostID: id)
// ... work ...
os_signpost(.end, log: log, name: "load_database", signpostID: id)
```

These appear in the `os-signpost` table. Especially useful for:
- The gap between "Initial Frame Rendering" and "Foreground"
- Wrapping each step of a scripted flow
- Marking individual frames in animation profiling
- Tagging API request/response boundaries

For high-throughput events, use a category of `.pointsOfInterest` — it has lower overhead than custom categories.

### Capture stderr from the launched app

`xctrace record` doesn't pipe the launched process's stdout/stderr by default. Two workarounds:

1. **Shell wrapper:** write a script that `exec`s your binary with stdout/stderr redirected, then point `--launch` at the script.
2. **Use `log stream`** in another terminal during recording:
   ```bash
   log stream --process MyApp --level debug > /tmp/myapp.log
   ```

Stream capture matters when using `DYLD_PRINT_STATISTICS=1` or any debug printf-style instrumentation.

### Recording is deferred-write

xctrace records to memory and serializes the bundle at the end. Older docs mention `--mode immediate` for continuous-write; that flag has been removed from the modern CLI (Xcode 26+ rejects it as "unrecognized option").

A finished trace bundle has these top-level entries: `corespace/`, `form.template`, `instrument_data/` (non-empty), `open.creq`, `shared_data/`, `symbols/`, `Trace1.run/`, and `UI_state_metadata.bin`. If `open.creq`, `shared_data/`, or `UI_state_metadata.bin` are missing, or `instrument_data/` is empty, the bundle is still being finalized (or finalization failed). Quick check after a record:

```bash
ls ~/x.trace/UI_state_metadata.bin && echo "trace finalized"
```

Observed once in this session: an `xctrace record --template "App Launch" --time-limit 90s` printed `Reached specified time limit, ending recording... Recording completed. Saving output file...` and then sat in that state for 5+ minutes without finalizing the bundle. A `--time-limit 45s` App Launch trace immediately after finalized normally. A `--time-limit 180s` App Launch trace earlier in the same session also finalized normally. So the failure mode exists but isn't deterministic — n=1 stall, n≥3 successful finalizes including a longer one. If you hit a stall, kill xctrace and try a shorter time-limit or a lighter template.

### Two-build comparison

```bash
xctrace record --template "Time Profiler" --launch ./before.app --time-limit 15s --output ~/before.trace
xctrace record --template "Time Profiler" --launch ./after.app  --time-limit 15s --output ~/after.trace
```

For launch comparisons, do at least 3 cold runs per build and take the median — the first run after reboot is unrepresentative due to warm caches.

### Common pitfalls

- **"Cold" launch isn't cold the second time.** Disk caches warm up. For true cold measurement, reboot or `purge` (requires sudo) between runs.
- **Debug builds are slower.** Optimization-disabled binaries skew absolute times. Profile Release-config builds for representative numbers; Debug is fine for finding *where* time is spent (relative ordering preserved).
- **On Mac Catalyst, the App Launch `Foreground` phase may not fire until the window is brought forward.** Observed with one Mac Catalyst app: `xctrace --launch` traces of 30s, 60s, and 180s all completed without the `Foreground` phase ever appearing. When the user clicked the app window, `Foreground` fired immediately — at ~30s on a 180s trace and ~18s on a 90s trace, matching click time. The mechanism wasn't pinned down (xctrace's terminal possibly retaining key focus, app/scene activation behavior, or something else). Practical takeaways: (1) if a Catalyst trace is missing `Foreground`, click the app window and it should appear; (2) the gap "Initial Frame Rendering → Foreground" includes user reaction time on Catalyst, so it's not a clean "post-first-frame work" measurement — back it up with an in-app signpost if you want a real TTI number.
- **First sample is at ~300 ms.** xctrace's sampling doesn't start until process creation completes — earliest phase ("Process Creation") has no callstack data.
- **Sampling cadence is statistical.** A 5 ms sample rate misses any function that runs in less than 5 ms. For sub-millisecond hotspots, use signposts or kdebug instead of sampling.
- **`--attach <name>` is ambiguous if multiple processes match.** Use PID for safety.
- **`--launch <path>` for `.app` bundles can launch the wrong binary.** LaunchServices substitutes by bundle ID, so a stale or installed `.app` with the same `CFBundleIdentifier` may run instead of the one you passed. After launch, verify with `ps`/`lsappinfo`; force LS to prefer your build with `lsregister -f <path>` (see Mode A — LaunchServices gotcha). **Re-run prune+`-f` before every trace** — the LS DB drifts between runs (Xcode indexing, sibling-worktree builds, Setapp), so a successful trace today does not mean the next one will hit the same `.app`.
- **Trace bundles are big.** 15 s of App Launch can be 50–200 MB. Clean up old traces.
- **xctrace 26.0 — `--output /tmp/foo.trace` fails.** Recording with the trace bundle under `/tmp` (or `/private/tmp`) exits 134 with abort trap. Internal failure: CoreData cannot open the trace's `RunIssues.storedata` (SQLite I/O error 6922), then `NSInvalidArgumentException` in `-[XRTrace saveDocument:saveCopy:error:]`. xctrace deletes the partial bundle on failure, so you get nothing. Same command with `--output ~/foo.trace` (or any non-`/tmp` path) succeeds. Verified 2026-05-03 on xctrace 26.0 (17C519). Workaround: write to your home dir, project worktree, or any other location.
- **xctrace 26.0 — multi-test traces drop custom-subsystem signposts.** A single `xctrace record` invocation that spans multiple `XCTestCase` test methods (e.g. `-XCTest <Suite>` instead of `-XCTest <Suite>/<singleTestName>`) drops signposts emitted from non-Apple subsystems (your app's `os_signpost` calls, but not XCTest's own). Apple-subsystem signposts (`com.apple.dt.XCTest` etc.) are preserved. Workaround: record one test per trace using `-XCTest <Suite>/<testName>`. Single-test traces also let `aggregate-signposts.py --per-test` skip the bucketing pass — the entire trace IS the test.

### Combining with other tools

- **`sample <pid> <duration>`** — quick CPU sample without xctrace's setup. Output is plain text. Good for "is the app stuck?" checks during a long trace.
- **`spindump`** — system-wide hang dump. Complementary when an app hangs entirely.
- **`heap <pid>` / `leaks <pid>`** — quick memory snapshots without an Allocations trace.
- **`fs_usage -w -f filesys <pid>`** — live disk I/O. Faster than running a File Activity trace if you just want to see what's being read.
- **`log stream --predicate 'process == "MyApp"'`** — live os_log stream. Pair with a signpost-heavy build for richer traces.

### Open the trace in Instruments

```bash
open ~/x.trace
```

Always an option when the headless pipeline gets stuck.

## Quick reference

```bash
# Discovery
xctrace list templates
xctrace list devices

# Record — cold launch (Mac)
# IMPORTANT: prune+force-register before EVERY trace, not just once per session.
# LS rankings drift between runs (Xcode indexing, sibling builds, Setapp), so the
# previous trace hitting your build is no guarantee the next one will.
# Kill by bundle ID, not process name — pkill -x App would also kill App Store / Setapp / TestFlight builds with the same name.
PID=$(lsappinfo info -only pid -app com.example.App | awk -F'=' '{print $2}'); [ -n "$PID" ] && kill -9 "$PID"
python3 ~/.claude/skills/xctrace/prune-lsregister.py com.example.App --keep /path/to/App.app --apply
lsregister -f /path/to/App.app   # bare command — `lsregister` is on $PATH
xctrace record --template "App Launch" --launch /path/to/App.app --time-limit 15s --output ~/x.trace
# Verify it actually launched YOUR build:
ps -ax -o pid,command | grep -i App.app/Contents/MacOS/App | grep -v grep

# Record — cold launch (iOS sim)
xctrace record --device "iPhone 15 Pro Simulator" --template "App Launch" --launch com.example.App --time-limit 15s --output ~/x.trace

# Record — attach to running process
xctrace record --template "Time Profiler" --attach MyApp --time-limit 30s --output ~/x.trace

# Record — wrap a scripted flow
xctrace record --template "Time Profiler" --attach MyApp --time-limit 60s --output ~/flow.trace &
osascript /path/to/flow.scpt
kill -INT $!

# Inspect
xctrace export --input ~/x.trace --toc

# Export common tables
xctrace export --input ~/x.trace --xpath '/trace-toc/run/data/table[@schema="life-cycle-period"]' --output /tmp/phases.xml
xctrace export --input ~/x.trace --xpath '/trace-toc/run/data/table[@schema="os-signpost"]'       --output /tmp/signposts.xml
xctrace export --input ~/x.trace --xpath '/trace-toc/run/data/table[@schema="time-sample"]'       --output /tmp/samples.xml
xctrace export --input ~/x.trace --xpath '/trace-toc/run/data/table[@schema="dyld-library-load"]' --output /tmp/dyld-libs.xml

# Symbolicate one address
atos -o /path/to/App.app/Contents/MacOS/App -l <load_addr> -arch arm64e <addr>

# Verify --launch hit your build (Mac/Catalyst .app)
ps -ax -o pid,command | grep -i App.app/Contents/MacOS/App | grep -v grep

# Force LS to pick a specific build / bulk-prune stale registrations
lsregister -f /path/to/App.app   # bare command — `lsregister` is on $PATH
python3 ~/.claude/skills/xctrace/prune-lsregister.py com.example.App --keep /path/to/App.app --apply

# Headless reports (markdown output)
python3 ~/.claude/skills/xctrace/phases.py ~/x.trace
python3 ~/.claude/skills/xctrace/phases.py ~/new.trace --baseline ~/old.trace
python3 ~/.claude/skills/xctrace/hotspots.py ~/x.trace --window 'willFinishLaunchingWithOptions()..Foreground' --thread main --top 30
python3 ~/.claude/skills/xctrace/aggregate-signposts.py ~/x.trace
python3 ~/.claude/skills/xctrace/aggregate-signposts.py ~/x.trace --name lock --per-test

# Open in GUI
open ~/x.trace
```
