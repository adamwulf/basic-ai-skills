---
name: find-all-bangs
description: "Inventory Swift force-unwrap sites: postfix !, try!, as!, and IUO type declarations. Use when the user asks to find force unwraps, audit ! usage, find all the bangs, or scan a Swift codebase for unsafe unwrap patterns. Writes a markdown report (and optional TSV) and prints a one-line summary. Tests are always skipped."
---

# find-all-bangs

Scans a Swift codebase for force-unwrap patterns and writes a categorized inventory. Counts four kinds of sites:

| Kind     | What it catches                                       |
|----------|-------------------------------------------------------|
| `unwrap` | Postfix `!` after an identifier/`)`/`]`/`?`           |
| `try!`   | `try!` keyword                                        |
| `as!`    | `as!` keyword                                         |
| `iuo`    | Implicitly-unwrapped optional type declarations       |

The scanner strips comments and string literals (single-line, multi-line, and triple-quoted) before matching, replacing them with whitespace of equal length so line numbers stay accurate. It avoids `!=`, `!==`, and `!!` false positives, and de-duplicates the `!` that belongs to `try!`/`as!`.

**Test files are always skipped.** A file is considered a test file when its path contains `Tests/` or `Test/`, or its filename ends with `Tests.swift`.

## Invoking

```bash
python3 find_bangs.py [path ...] [--exclude-iuo] [--tsv] [--stdout]
```

- `path ...` — one or more directories (or individual `.swift` files). Defaults to `.`.
- `--exclude-iuo` — drop implicitly-unwrapped optional type declarations from the report (default: include them as kind `iuo`).
- `--tsv` — also write a machine-readable `find-all-bangs-details.tsv` alongside the markdown report.
- `--stdout` — skip file output; print `file:line:kind:snippet` lines for piping.
- `--report PATH` / `--details PATH` — override the default output paths.

Exit code is always `0` — this is a reporting tool, not a linter.

## Example

```bash
# Default: write markdown report with all four kinds for the whole repo.
python3 find_bangs.py Muse muse-mcp-server SharedMCP MuseShare

# Just the "true" force unwraps, without IUO declarations.
python3 find_bangs.py Muse --exclude-iuo

# Pipe individual hits into another tool.
python3 find_bangs.py Muse --stdout | grep ' try!:'
```

## Outputs

### Stdout summary

A single line, always:

```
712 sites in 198 files (222 unwrap, 5 try!, 98 as!, 387 iuo)
```

With `--exclude-iuo`:

```
325 sites in 125 files (222 unwrap, 5 try!, 98 as!)
```

### `find-all-bangs-report.md`

Human-readable markdown with:

```
# Force-unwrap inventory

**Roots scanned:** Muse, muse-mcp-server, SharedMCP, MuseShare
**Exclude IUO type decls:** False

## Totals
- **712** sites across **198** files
- 222 postfix `!` (unwrap)
- 5 `try!`
- 98 `as!`
- 387 IUO type declarations

## By area
| Area | Files | unwrap | try! | as! | iuo | Total |
|---|---:|---:|---:|---:|---:|---:|
| Muse | 180 | … |

## Top 25 files
| File | unwrap | try! | as! | iuo | Total |
|---|---:|---:|---:|---:|---:|

## All `try!` sites
- `Muse/.../Foo.swift:42` — `try! ctx.commitToAncestors()`
```

### `find-all-bangs-details.tsv` (only with `--tsv`)

```
kind	file	line	snippet
unwrap	Muse/Foo.swift	42	    return cache[key]!
try!	Muse/Bar.swift	18	        try! db.write { … }
```

## Caveats

- Regex-based — does not understand Swift syntax. It will miss custom operators that happen to end in `!` and could in principle false-positive on exotic macro expansions, though no false positives were found in spot-checks across ~900 files.
- IUO detection requires the type to start with an uppercase identifier (Swift convention). A typealias to a lowercase-named type used as IUO would be missed.
- The script is stdlib-only (Python 3, no external deps). Tested on Python 3.11+.
