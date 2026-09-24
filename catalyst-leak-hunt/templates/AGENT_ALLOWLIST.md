# Agent allowlist for catalyst-leak-hunt

The minimal set of commands an agent needs to run this flow end-to-end. Group by purpose for the user's approval message.

## Build & launch

| Command | Why |
|---|---|
| `xcodebuild` | Compile the DEBUG configuration. The user can run this themselves instead if they prefer. |
| `open` (with `--env`) | LaunchServices-route launch of the .app. `--env` is unreliable on sandboxed Catalyst (see SKILL.md gotchas) — use the sentinel-file fallback too. |
| `lsregister` | Pin the freshly built .app to its bundle ID. Run prune+`-f` before EVERY launch (Xcode indexing, sibling worktrees, and other LS clients reshuffle the DB between runs). |
| `pgrep`, `lsappinfo` | Find PIDs by bundle ID. Required to scope all profiling and kills correctly. |
| `kill` | Terminate the previous DEBUG instance between runs. Only `kill <pid>`, never `pkill -x <name>` (would kill App Store / TestFlight / Setapp copies that share the process name). |

## Memory tools

| Command | Why |
|---|---|
| `heap` | Per-class allocation counts. Primary tool. |
| `vmmap` | Labeled VM regions (`IOSurface`, `CG image`). Complements `heap` for renderer-side memory. |
| `leaks` | Cycle detector. Note: most app-level leaks are reachable-from-singleton, NOT cycles — `leaks` will report 0. Use as a complement, not a primary signal. |
| `malloc_history` | Walk back retainer trees for specific addresses. Rarely needed; use `xctrace` Allocations + Instruments GUI for retainer trees instead. |
| `xctrace` | Instruments traces (App Launch, Allocations, Leaks). For retainer trees that the class-count diff can't provide. |
| `xcrun`, `swift-demangle`, `atos` | Demangling and address-to-symbol resolution. `heap` already demangles Swift on Sequoia+, but useful for raw addresses. |

## Disk & file management

| Command | Why |
|---|---|
| `df` | Sanity-check free space before snapshotting (each `heap` output can be 1-10 MB on a multi-GB process). |
| `chmod` | Make helper scripts executable. Optional — agents can usually invoke via `bash script.sh` or `python3 script.py` instead. |
| `python3` | Run the snapshotter and diff scripts. |

## Copy-pasteable approval request

> I need these in the allowlist for the catalyst-leak-hunt flow:
>
> **Build & launch:** `xcodebuild`, `open`, `lsregister`, `pgrep`, `lsappinfo`, `kill`
> **Memory:** `heap`, `vmmap`, `leaks`, `malloc_history`, `xctrace`, `xcrun`, `swift-demangle`, `atos`
> **Files:** `df`, `chmod`, `python3`
>
> All are read-only diagnostics except `kill` (terminates the DEBUG build by PID after `lsappinfo` lookup — never `pkill`) and `lsregister -f` (LaunchServices registration). None of these touch shared system state. The snapshotter has a bundle-ID guard that aborts if it sees the user's daily-driver release build.
