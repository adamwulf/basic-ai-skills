---
name: md
description: Block-level editing of markdown files via the `md` CLI — insert/replace/remove by block index, read/write frontmatter, generate a TOC, normalize formatting, or list the frontmatter of every `.md` file in a directory as a folder index. Use instead of Read+Edit/Write when the file is long, edits target structural blocks (headings, paragraphs, code blocks, lists, tables), or you only need frontmatter or a section.
allowed-tools: Bash, Read
---

# md — Block-Aware Markdown CLI

`md` addresses markdown by **1-based block index** (headings, paragraphs, code blocks, lists, blockquotes, tables, thematic breaks, raw HTML). Prefer `md` over Read+Edit when the file is long, you're editing a whole block/section, or you only need frontmatter. For word-level tweaks inside a paragraph, `Edit` is simpler.

Every command takes exactly one of `--file <path>` or `--stdin`. Add `-i/--in-place` to mutating commands to write back to the file; otherwise output goes to stdout. Requires `md` on PATH (fall back to Read+Edit if missing); errors exit non-zero with a message on stderr.

## Workflow

1. `md toc --blocks --file doc.md` — map headings to block indices.
2. (Optional) `md blocks --file doc.md` — list every block with type + line range.
3. Mutate with `insert-after`, `insert-before`, `replace`, or `remove` using `-i`.

**Gotcha:** block indices shift after every insert/remove. Re-run `md toc --blocks` between mutations; don't reuse stale indices.

## Subcommands

- **`md toc --blocks|--lines --file <f>`** — TOC of headings. One of `--blocks` or `--lines` is required. Frontmatter is skipped — only real headings appear.
- **`md blocks [--count] [<start> [<end>]] --file <f>`** — no args lists all blocks with type + line range; `--count` prints total; `<start> [<end>]` prints raw content of that range (END defaults to START). Frontmatter is skipped, so block 1 is the first real markdown element after any `---`/`+++`/`;;;` block.
- **`md lines [--count] [<start> [<end>]] --file <f>`** — same three modes, by raw line number.
- **`md insert-after <idx> <content> --file <f> [-i]`** / **`md insert-before <idx> <content> --file <f> [-i]`** — insert markdown after/before a block. Content is re-parsed and re-formatted.
- **`md replace <start> [<end>] <content> --file <f> [-i]`** — replace a block or range. `<content>` is always required. Arg-parsing trap: if the second arg is entirely digits (e.g., `9`, not `9 lives`), it's treated as END and content goes in position 3; otherwise the second arg *is* the content. Contrast: `md replace 7 9 "new content"` replaces blocks 7–9; `md replace 7 "9 lives"` replaces block 7 with the string `9 lives`.
- **`md remove <start> [<end>] --file <f> [-i]`** — remove a block or inclusive range.
- **`md frontmatter --file <f> [flags] [-i]`** — supports YAML (`---`), TOML (`+++`), JSON (`;;;`). No flags prints the frontmatter body; `--key K` gets a value (dot syntax for nested: `author.name`); `--set K=V` sets (creates frontmatter if absent, defaults to YAML); `--remove-key K` deletes; `--format yaml|toml|json` converts (YAML date values are emitted as ISO-8601 strings in JSON). Read-mode output is bare data — no delimiters, no body — so `md frontmatter --format json --file f.md | jq .` works directly.
- **`md format --file <f> [--frontmatter yaml|toml|json] [-i]`** — normalize formatting via cmark-gfm. Preserves non-empty frontmatter verbatim; strips empty frontmatter. `--frontmatter X` converts non-empty frontmatter to format X while normalizing the body (no-ops if the source has no frontmatter or already matches X). Add `-i/--in-place` to write back to the file (rejected with `--stdin`); otherwise output goes to stdout.
- **`md list <dir>... [-r] [--format yaml|json|toml] [--output plain|json|ndjson] [--key K | --keys K1,K2] [--missing include|skip|only] [--sort path|mtime|name]`** — dump frontmatter of every `.md` file in one or more directories as a folder-level index. Default output is `plain` (a `== <path> ==` block per file, body in YAML); use `--output ndjson` for machine parsing. `--keys` projects a subset; `--missing skip` drops files without frontmatter, `--missing only` keeps just them. Symlinked directories are not followed. Uses only the `.md` extension.

## Examples

**Replace a section of a README** (replace `## Install` and everything through the block before the next heading):
```
md toc --blocks --file README.md
# "## Install" is block 7; next heading is block 12 — replace 7..11.
md replace 7 11 "## Install

Run \`brew install foo\`." --file README.md -i
```

**Read just one section without loading the whole file:**
```
md toc --blocks --file docs/guide.md
md blocks 14 18 --file docs/guide.md
```

**Frontmatter updates:**
```
md frontmatter --set "updated=2026-04-18" --file post.md -i
md frontmatter --remove-key draft --file post.md -i
md frontmatter --key author.name --file post.md
```

**Normalize formatting in place:**
```
md format --file README.md -i
```

**Convert frontmatter format and normalize the body in one pass:**
```
md format --frontmatter json --file post.md -i
```

**Compose with other tools via `--stdin`:**
```
curl -s https://example.com/doc.md | md toc --lines --stdin
```

**Index a folder of notes with `md list`** — scan a directory as an at-a-glance table of contents:
```
md list ./notes              # top-level, plain output, all frontmatter
md list -r ./notes           # recurse
md list ./notes --keys title,tags,updated   # narrow to an index-style view
md list -r . --output ndjson --missing skip # machine-readable, skip bare files
```
Files without frontmatter print `(no frontmatter)` in plain mode; use `--missing only` to find them, `--missing skip` to hide them.
