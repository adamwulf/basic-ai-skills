---
name: catalyst-leak-hunt
description: "Diagnose memory leaks in iOS/iPadOS/Mac Catalyst apps using an in-app DEBUG harness that drives a repro scenario, captures heap+vmmap snapshots via an external snapshotter (sandbox-safe sentinel-file IPC), and diffs class counts across before/after checkpoints. Use when a user reports RSS staying elevated after a teardown event (window close, scene discard, document close, sheet dismiss), monotonic memory growth over a known user flow, or a specific class suspected of leaking. Produces a leak fingerprint naming the retained classes and a reusable harness for future hunts."
---

# Catalyst memory-leak hunt

Class-count diff with a yes/no answer per class. Works on iOS, iPadOS, and Mac Catalyst.

The expensive lessons in this skill — Catalyst forbids `Process`, `requestSceneSessionDestruction` does NOT fire `sceneDidDisconnect`, `currentSceneDelegate` requires `.foregroundActive`, gesture-target retain cycles can't be fixed with `weak` — were learned chasing a 14 GB leak in Muse. They generalize.

## When to use

- RSS / `phys_footprint` stays elevated after a user-visible teardown (window close, document close, scene dismiss).
- Memory grows monotonically over a known repeatable user flow.
- A specific class is suspected of leaking and you want a count-over-time confirmation.
- The question is "where is the leak in code," not "is there a leak." (For the latter, just watch Activity Monitor.)

If the user's question is "fix this leak," follow this flow end-to-end. Don't skip to static analysis — Swift retain trees are sparse in Instruments and reading them is slow; class-count diff is faster and definitive.

## The shape of the approach

Five pieces, all in this skill's `templates/`:

1. **In-app DEBUG harness** (Swift, `~500` lines) that activates on env var or sandbox sentinel file, drives a scenario in `Task.detached` hopping to `@MainActor` for UIKit work, and writes checkpoint sentinels to the sandbox container.
2. **External snapshotter** (Python, `~150` lines) that polls the sandbox dir, runs `heap` and `vmmap` from outside the sandbox, writes results atomically.
3. **Heap diff tool** (Python, `~120` lines) that parses three snapshots (A/B/C) and prints classes that went up A→B and didn't come back down B→C — the "leak fingerprint."
4. **Two app hooks** (one line each): `AppDelegate.didFinishLaunchingWithOptions` → `LeakRepro.shared.startIfRequested()`; `UIWindowSceneDelegate.scene(_:willConnectTo:)` → `LeakRepro.shared.sceneDidConnect(scene)`.
5. **Allowlist request** for the agent doing the hunt (see `templates/AGENT_ALLOWLIST.md`).

Each scenario is one `runScenario_*` method on the harness. Adding new scenarios is cheap. Leak diagnosis is one-shot; the *harness* is reusable.

## Plan-first, then execute

Before writing the harness or building, write a **`LEAK_DIAGNOSIS_PLAN.md`** in the worktree root covering:

- **Hypotheses (ranked).** Read scene-delegate teardown, the relevant view controller, any singletons that subscribe to scene/session events, any per-scene/document caches. List every place a closed scene's content could be pinned.
- **For each hypothesis: what signal in the diff confirms or refutes it.** A specific class name plus expected count direction.
- **Repro strategy.** Programmatic via the in-app harness is the goal. If parts of the flow can't be driven programmatically (touch input, modal dismissal that needs a tap), describe the manual step and how the harness pauses for it.
- **Profiling strategy.** Which scenarios, what waits, how many checkpoints, what to capture at each.
- **Analysis strategy.** Which classes you'll grep for first based on hypotheses, what counts mean go vs no-go.

Then run a **review cycle**: spawn two independent reviewer agents to critique the plan. The Muse hunt found three load-bearing issues in the plan this way — including an early hypothesis about `appKitPlugin?.addWindowObserver` that turned out to be wrong (its impl ignored the `object:` parameter). Catching a wrong hypothesis costs minutes in plan review; catching it after a 5-minute rebuild costs hours.

## Building the harness

Copy `templates/LeakRepro.swift.template` into the app's `<Module>/Debug/LeakRepro.swift`. Wrap the whole file in `#if DEBUG`. Adapt:

- Class names of the scene delegate / view controllers
- Workspace/document discovery (whatever the app's notion of "a thing you open" is)
- Scenario body (the actual user flow being tested)

Add the two one-line hooks. Both `#if DEBUG`-gated.

Add the snapshotter and diff scripts to `scripts/`. They're nearly app-agnostic — only the sandbox container path and the bundle ID for the safety guard need to change.

The total app delta is one Swift file (`LeakRepro.swift`) plus two one-liners in `AppDelegate` and the scene delegate. Easy to delete pre-merge if desired; clean diff to merge if kept.

### Review the harness too

After the harness builds, run a second review cycle on the harness code before trusting any data it produces. Focus reviewers on:

- **Thread safety.** UIKit work must hop to `@MainActor`. Background timer firing on the main thread is a footgun.
- **Activation gating.** When the env var/sentinel is unset, the harness must be truly zero-cost. No timer, no observer, nothing.
- **Subprocess from inside the same process.** `heap`/`vmmap` invoked via `Process` from the harness will fail on Catalyst — that's why this skill uses an external snapshotter. Reviewer should sanity-check that the harness doesn't try to spawn subprocesses.
- **TASK_VM_INFO revision.** `task_info` requires `REV1_COUNT` validation for `phys_footprint` to be trustworthy. Check.
- **`requestSceneSessionDestruction` semantics.** It does NOT fire `sceneDidDisconnect` — see "Hard-won gotchas" below.
- **Workspace/document picker.** The harness should pick the largest existing one (signal-to-noise). It must not synthesize new ones (won't match the real symptom).

The Muse hunt's review pass caught: a `corpusGraph.isInitialized` poll that should have been bounded; a missing `layoutIfNeeded()` after `setContentOffset` (without it, cards don't instantiate and the snapshot misses them); a missing nil-guard on W2; a missing REV1_COUNT validation. All would have produced bad data silently.

## Running it end-to-end

```bash
# 1. Build the DEBUG configuration.
xcodebuild -workspace App.xcworkspace -scheme "<DEBUG-scheme-name>" \
    -destination "platform=macOS" -derivedDataPath DerivedData build 2>&1 \
    | grep -E "BUILD SUCCEEDED|BUILD FAILED|error: " | tail -5

# 2. Kill any prior instance of the DEBUG build. Scope by bundle ID — DO NOT pkill by name.
PID=$(lsappinfo info -only pid -app <debug-bundle-id> | awk -F'=' '{print $2}')
[ -n "$PID" ] && kill "$PID"

# 3. LaunchServices: pin THIS .app for the bundle ID so `open` doesn't pick a stale build.
python3 ~/.claude/skills/xctrace/prune-lsregister.py <debug-bundle-id> \
    --keep "$PWD/DerivedData/Build/Products/<config>-<platform>/App.app" --apply
lsregister -f "$PWD/DerivedData/Build/Products/<config>-<platform>/App.app"

# 4. Clean prior run output.
rm -rf ~/Library/Containers/<debug-bundle-id>/Data/Documents/leak-repro

# 5. Drop the sentinel file (works whether or not --env propagates).
mkdir -p ~/Library/Containers/<debug-bundle-id>/Data/Documents
echo "<scenario-name>" > \
    ~/Library/Containers/<debug-bundle-id>/Data/Documents/.debug-scenario

# 6. Launch. Pass the env var too in case Catalyst happens to honor it on this OS version.
open --env DEBUG_SCENARIO=<scenario-name> \
    "$PWD/DerivedData/Build/Products/<config>-<platform>/App.app"

# 7. Run the external snapshotter. Blocks until `done` sentinel appears.
python3 scripts/leak-repro-snapshotter.py

# 8. Diff the three snapshots.
python3 scripts/leak-heap-diff.py \
    ~/Library/Containers/<debug-bundle-id>/Data/Documents/leak-repro/heap-A.txt \
    ~/Library/Containers/<debug-bundle-id>/Data/Documents/leak-repro/heap-B.txt \
    ~/Library/Containers/<debug-bundle-id>/Data/Documents/leak-repro/heap-C.txt
```

Total wall time per run: ~5–8 minutes for a typical scenario (most of it is steady-state waits to let natural releases happen).

## Reading the output

### `timeline.csv`

```
timestamp,checkpoint,rss_bytes,phys_footprint_bytes
2026-05-18T21:08:52Z,A,609189888,191647872
2026-05-18T21:09:32Z,B,258998272,177917952
2026-05-18T21:11:42Z,C,272056320,165056576
```

- **A** = loaded state of the "thing being torn down"
- **B** = with the second thing also open (control)
- **C** = post-teardown, after the natural-release wait

**Trust `phys_footprint`, not RSS.** RSS includes file-backed pages the kernel can drop for free; `phys_footprint` is dirty/unswappable bytes the process is actually consuming.

### `heap-X.txt`

`heap` on modern macOS already demangles Swift class names. Columns: `<count> <bytes> <avg> <classname> <lang> <module>`.

The diff tool sums per-class counts across malloc zones and prints:

1. **Classes of interest** — user-specified watch list with A/B/C counts and deltas.
2. **Leak fingerprint** — every class where count went UP A→B AND did NOT come back DOWN B→C. That's the canonical leak set.

### Generic patterns to recognize in the fingerprint

| Pattern | What it usually means |
|---|---|
| Top-of-tree class (e.g. `SceneDelegate`, `RootViewController`) in fingerprint | The scene/window itself isn't releasing — every other leak below it is downstream. Investigate this first. |
| Top-of-tree class NOT in fingerprint, but a child VC is | Scene delegate deinit-s correctly; child has its own retainer (delegate, observer, gesture cycle). |
| A `*NavigationController` in fingerprint | Suspect gesture-target retain cycles on the nav controller's view; suspect a transition animator held by UIKit. |
| Model objects (your `Card`, `Document`, etc.) in fingerprint | Pinned by an object cache somewhere — singleton, context, or service. Find the cache and add an eviction path. |
| `UndoManager` count drifts upward over many runs | Per-document undo managers held by a singleton without an eviction policy. |
| `PDFDocument` / `PDFPage` / `IOSurface` in fingerprint | PDFKit rasters held alive via a leaked CardView-equivalent. |
| `FBSScene*`, `FBSSceneClient*`, `FUApplicationSceneComponent` in fingerprint | UIKit-internal scene infrastructure isn't fully torn down. Suspect a long-lived observer that bridges to the scene. |
| `UICommand` / `UIKeyCommand` in fingerprint | Menu commands accumulating per scene (rebuilt and old set kept alive). |

### `vmmap-X.txt`

- `IOSurface`, `CG image`, `CG raster data` are *labeled* regions. If they shrink A→C, the renderer-side memory released. If they don't, suspect retained PDFKit or image-backed views.
- `MALLOC_LARGE` / `MALLOC_SMALL` / `MALLOC_TINY` are NOT semantically labeled. A Swift-object-cache leak lives here without telling you which class. Use `heap` for class-level localization, `vmmap` for renderer/CoreGraphics localization. They complement.

## Hard-won gotchas (Catalyst / iOS)

These are the things that cost the most time in the Muse hunt. Skim this section before writing the harness.

### Sandbox & process

- **Catalyst forbids `Process`.** `Process.run()`, `Process.launchPath`, the whole class — sandbox blocks fork+exec. That's why this skill uses an external snapshotter and sandbox-readable sentinel files.
- **`FileManager.default.homeDirectoryForCurrentUser` is unavailable on Catalyst.** Use `URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)`. On a sandboxed Catalyst app, that resolves to the per-app container, which is exactly what you want for shared-with-external-tools data.
- **Sandbox container path:** `~/Library/Containers/<bundle-id>/Data/Documents/`. Readable from outside the sandbox without entitlements. Use it for the sentinel files.

### Activation

- **`open --env FOO=BAR Path.app` does NOT reliably pass env vars to Catalyst sandboxed apps.** LaunchServices strips them. Always implement a sentinel-file fallback. The env var is a no-op nice-to-have for unsandboxed cases.

### Scene lifecycle

- **`requestSceneSessionDestruction` does NOT fire `sceneDidDisconnect`.** Only `sceneWillResignActive` and `sceneDidEnterBackground` fire. Your teardown belongs in `UIApplicationDelegate.application(_:didDiscardSceneSessions:)`, not in the scene delegate's `sceneDidDisconnect`. The Muse hunt initially put teardown in `sceneDidDisconnect` and it never ran.
- **`UIApplication.shared.currentSceneDelegate` (or your custom equivalent) requires `.foregroundActive` AND a key window.** When the app is launched programmatically via `open` without explicit focus, neither holds — the scenario's "find the scene delegate" code returns nil. Use a fallback that iterates `UIApplication.shared.connectedScenes` looking for *any* scene matching your criteria.
- **`UIApplication.shared.requestSceneSessionActivation(_:userActivity:options:errorHandler:)` returns immediately, before the new scene's delegate has been connected.** Hook the scene delegate's `willConnectTo` and signal back to the harness with a continuation; don't `sleep`.

### Async teardown

- **`requestSceneSessionDestruction` returns immediately**, but the actual VC/delegate deinits happen asynchronously over the next ~3 s. Before snapshotting C, spin the runloop and an autoreleasepool to drain pending teardown:

  ```swift
  for _ in 0..<30 {
      autoreleasepool { _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.1)) }
  }
  ```

  Then wait the natural-release time (60–120 s) before snapshot C. Many objects release on a delay even after their owner dies (`URLSession` background queue, `CADisplayLink` next-frame, animation completion blocks).

### Gesture-target cycles can NOT be fixed with `weak`

`UIGestureRecognizer.init(target:action:)` retains the target. There is no public `weak target:` API. If a handler stores a `UIGestureRecognizer` in a strong property AND that recognizer's target is the handler itself, you have a self↔gesture retain cycle that is *intrinsic* and cannot be broken by making any property weak.

The fix is `removeTarget(self, action: nil)` from a teardown hook. Cache the gestures on the handler so teardown can find them. Call teardown from `application(_:didDiscardSceneSessions:)` (or wherever the scene-ownership chain hits zero) before any view-side cleanup.

This pattern is also true of `NSTimer.scheduledTimer(target:)` — for timers, the standard fix is a proxy weak-target wrapper. For gestures, explicit `removeTarget` is the established Cocoa idiom.

### `task_info`

- **`TASK_VM_INFO` returns ambiguous data unless you check `TASK_VM_INFO_REV1_COUNT`.** Without that validation, `phys_footprint` can be a kernel-zeroed field. Validate before logging.

### Build / launch

- **`com.apple.FinderInfo` xattr on the .app dir blocks codesign** with `error: resource fork, Finder information, or similar detritus not allowed`. Strip with `xattr -d com.apple.FinderInfo path/to/App.app` and rebuild. If repeated builds keep adding it back, nuke `DerivedData/` and rebuild.
- **First build of a fresh `DerivedData/` may hit Info.plist Template ordering bugs**. Try `clean build` first; if that fails, full nuke + rebuild.
- **Run LaunchServices `prune` + `lsregister -f` before EVERY launch**, not just once per session. Xcode indexing, sibling worktrees, Setapp, and other LS clients can reshuffle the DB between launches. See the `xctrace` skill's "LaunchServices gotcha" section for the prune script.
- **`pkill -x AppName` matches by process name and can kill the wrong build** if multiple versions are installed (App Store + dev, TestFlight + Xcode build, Setapp + worktree). Always scope by bundle ID via `lsappinfo info -only pid -app <bundle-id>` then `kill <pid>`.

### `heap` and `vmmap` timing

- **`heap` on a multi-GB process can take 30–120 s per snapshot.** Don't budget 5 seconds. The harness needs an "infinite" wait on the `.done` sentinel.
- Each snapshot can produce 1–10 MB of text. Disk-budget for it.

## Verifying the fix

Diagnosis is not done until the fix is verified:

1. **Apply the fix.** Commit separately so you can bisect.
2. **Optional one-pass review** of the fix diff. One reviewer worker, single round. Focus: does the new teardown call site match where the lifecycle event actually fires (`didDiscardSceneSessions` is the usual answer on Catalyst, not `sceneDidDisconnect`)? Are removed strong refs safe? Does breaking a gesture cycle break the gesture's functionality during normal operation?
3. **Rebuild and re-run the same scenario.**
4. **Diff the new snapshots against the pre-fix baseline.** Class counts that were in the fingerprint must now show count B→C dropping correctly. Deinits that previously never fired must now fire.
5. **If the leak persists, you were wrong.** Don't merge a fix that doesn't reduce the signal. Go back to the suspect list, pick the next-most-likely retainer based on the new evidence, and iterate. Hard stop at 3 cycles — beyond that, escalate to the user.

Always keep pre-fix and post-fix snapshots in `agent-reports/leak-repro-evidence/{,post-fix/}` so before/after lives in git.

## Trimming the fix to minimum load-bearing

After verification, look at the fix and ask "is every piece of this necessary?" A typical iteration produces:

- Load-bearing changes that visibly closed the leak.
- Defense-in-depth changes added "for safety" that the verification doesn't actually require.

Remove the defense-in-depth — but verify the trim doesn't regress. If a "defense-in-depth" change turns out to be load-bearing after all, you've learned something important and should keep it AND document why.

The Muse hunt's v1 fix included nilling four strong properties on the scene delegate. The commit message itself noted these weren't load-bearing — the scene delegate's `deinit` was already firing correctly. After trim verification, those nillings were removed; the fix held.

## What this skill cannot do

- **Drive Apple Pencil / touch input.** Real touches require a human or XCUITest. The scenario can drive scroll views, gestures with synthetic events via `UIControl.sendActions`, and the in-process state machine, but it can't simulate a pencil stroke.
- **Reproduce a leak that's data-dependent.** If the bug only shows with a specific workspace/document containing 10k items, the harness has to be run against a DB that contains such a workspace — it cannot synthesize one.
- **Distinguish "cycle leak" from "reachable-from-singleton leak."** The Apple `leaks` tool reports only cycles. Most app-level leaks are reachable-but-unwanted and `leaks` calls them 0 leaks. The class-count diff is the right tool.
- **Capture allocation retainer trees.** For "this class is leaking, but I can't find who holds it," use `xctrace` Allocations + Instruments GUI (see the `xctrace` skill). The class-count diff localizes WHICH class; Instruments shows WHO.
- **Detect leaks that only manifest after N iterations.** The default scenario runs once. For "memory grows over N opens" patterns, loop inside the scenario or relaunch between runs.

## Agent allowlist

Future agents asking to run this flow should request these in their tool allowlist (the minimal set from the Muse hunt):

```
xcodebuild lsappinfo lsregister kill pgrep open
heap vmmap leaks malloc_history xcrun swift-demangle atos xctrace
df chmod python3
```

Plus `open` with `--env` for env-var passthrough (still implement the sentinel-file fallback even with this — it's not reliable).

Detail in `templates/AGENT_ALLOWLIST.md`.

---

## Muse-specific quick reference

When working in the Muse codebase, the harness and tooling already exist on disk:

### Existing artifacts (do not re-create)

| Where | What |
|---|---|
| `Muse/Debug/LeakRepro.swift` | The harness. Wraps the whole file in `#if DEBUG`. |
| `Muse/AppDelegate.swift:didFinishLaunchingWithOptions` | `LeakRepro.shared.startIfRequested()` hook. |
| `Muse/MuseSceneDelegate.swift:scene(_:willConnectTo:options:)` | `LeakRepro.shared.sceneDidConnect(scene)` hook. |
| `scripts/leak-repro-snapshotter.py` | External snapshotter (Python). `scripts/leak-repro-snapshotter.sh` is a Bash twin. |
| `scripts/leak-heap-diff.py` | Diff tool. `scripts/leak-heap-diff.sh` is a Bash twin. |
| `scripts/leak-capture-snapshot.sh` | One-off heap+vmmap helper (rarely needed; the snapshotter usually handles this). |
| `docs/memory-leak-diagnosis.md` | The Muse-specific runbook. Detailed phase timings, the full `leak-workspace-close` flow, and Muse-specific patterns in the fingerprint. |
| `MEMORY_LEAK_FINDINGS.md` (most recent incident) | The findings report for the workspace-close leak — root cause: three standalone gesture-target retain cycles in `UndoHandler`, `SelectionHandler`, `CSAnimatingNavigationController`. |
| `agent-reports/leak-repro-evidence/` | Pre-fix and post-fix snapshots, scenario.log, timeline.csv. Reference baseline. |

### Scheme and bundle IDs

| Scheme | Bundle ID | Use |
|---|---|---|
| **Muse Setapp Debug** | `com.musesoftware.museios-setapp` | **The ONLY scheme for leak hunts.** All tooling targets this bundle ID. |
| Muse | `com.musesoftware.museios-dev` | iOS dev. Separate bundle ID — no LS collision with the Setapp Debug build. |
| Muse AppStore | `com.musesoftware.museios-appstore` | **The user's daily-driver Muse.** Off-limits — must not be killed, attached to, or profiled. The snapshotter has a bundle-ID guard that aborts if it sees this PID. |
| Muse Setapp | `com.musesoftware.museios-setapp` | Setapp release. Same bundle ID as Setapp Debug. LaunchServices prune+`lsregister -f` is critical. |

### Sandbox container path

```
~/Library/Containers/com.musesoftware.museios-setapp/Data/Documents/muse-leak-repro/
```

The `LogDriver` SQLite DB lives in the same `Documents` dir (`db.sqlite3`). On a real user account, this DB is often 2–5 GB, plenty large for the leak to reproduce.

### Available scenarios

| Scenario | What it does |
|---|---|
| `leak-workspace-close` | Picks the largest initialized workspace as W1 and a small one as W2. Switches to W1. setContentOffset sweep + layoutIfNeeded for 30 s on the active BoardScrollView. Wait 60 s. Snapshot A. Open W2 in a second window. Wait 30 s. Snapshot B. `requestSceneSessionDestruction` on W1's scene. Drain runloop. Wait 120 s. Snapshot C. Total ~6–8 min. |

Add a new scenario in `Muse/Debug/LeakRepro.swift` — see "Adding a new scenario" in `docs/memory-leak-diagnosis.md` for the dispatch pattern.

### Muse-specific patterns in the fingerprint

| Class | Cause |
|---|---|
| `CSAnimatingNavigationController` in fingerprint | Self↔gesture-target cycle on its tap/double-tap/pinch/swipe recognizers (fixed; if it re-appears, a new recognizer was added without a `removeTarget` in the teardown helper). |
| `BoardViewController` in fingerprint | Usually cascading from a leaked `MainAppViewController` / `CSAnimatingNavigationController`. Investigate parent first. |
| `MuseStroke` / `MuseBoard` / `MuseCard` in fingerprint | Pinned by `MuseContext.uiContext` or `rootContext` object cache. Never purged on workspace switch. |
| `UndoManager` count drifts upward | `PersistenceService.shared.undoManagers` (`PersistenceService.swift:41`) is never evicted. Per-board entries accumulate. |
| `UndoHandler` / `SelectionHandler` in fingerprint | Self↔gesture-target cycle on their stored recognizer properties (fixed; same pattern as `CSAnimatingNavigationController`). |
| `PDFDocument` / `IOSurface` / `CG image` in `vmmap` | PDFKit raster held alive via a leaked CardView. Look up the chain — if a CardView leaks, PDFKit raster bytes follow. |
| `FBSScene*` in fingerprint | UIKit-internal scene infrastructure not fully torn down. Was bait-and-switch in the workspace-close hunt: `appKitPlugin?.addWindowObserver(object: self)` at `MuseSceneDelegate.swift:1314` *looks* like a leak source but its impl in `MuseAppKitBridge.addWindowObserver(object:)` ignores the `object:` parameter. Don't chase it without confirming the impl actually retains. |

### Don'ts (Muse-specific)

- **Do NOT touch `com.musesoftware.museios-appstore`.** That's the user's daily driver. Every tool in this skill is bundle-ID-scoped to `museios-setapp`. The snapshotter aborts if it sees the App Store build's PID.
- **Do NOT synthesize workspaces.** The user has multiple workspaces of varying sizes already; pick from them. Synthetic workspaces won't have the realistic content (PDFs, images, strokes) that produces the leak signal.
- **Do NOT remove the harness or scripts when the hunt is done.** They are retained for future hunts. The diagnostic-only `log.info(.sceneLifecycle, ...)` instrumentation IS removed after each hunt; the harness itself stays.

### Scheme + path quick reference (copy-paste)

```bash
SCHEME="Muse Setapp Debug"
BUNDLE_ID="com.musesoftware.museios-setapp"
APP_PATH="$PWD/DerivedData/Build/Products/SetappDebug-maccatalyst/Muse.app"
SANDBOX="$HOME/Library/Containers/$BUNDLE_ID/Data/Documents"
OUTPUT="$SANDBOX/muse-leak-repro"
```
