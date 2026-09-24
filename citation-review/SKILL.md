---
name: citation-review
description: "Universal pre-merge quality gate for cited documents. Tiered lint rules (error/warning/info) with structured reporting. Use when auditing citations, checking citation format, or linting citations before merge."
---

# Citation Review

Lint citations for format errors, accuracy problems, broken links, and density gaps. Use as a pre-merge quality gate for any document with `[^` footnotes.

## When to Use

- Before merging any document that contains citations
- After completing verification with `/citation`
- When asked to "audit citations", "lint citations", or "check citation format"
- When reviewing citation quality in any document

---

## Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| **ERROR** | Broken, inaccurate, or violates core policy | Must fix before merge |
| **WARNING** | Exists but has quality issues | Should fix; may defer |
| **INFO** | Stylistic or density suggestion | Author's discretion |

---

## Error Rules (Must Fix)

**E1: `format/footnote-syntax`**
Every `[^N]` reference has a matching definition, and every definition is referenced. See How to Check below for automated commands.

**E2: `source/no-cite-derivative`**
No citation points to a summary, synthesis, or analysis file. Only original sources. The automated check may produce false positives from display text — manually verify flagged lines.

**E3: `link/file-exists`**
Every local file path in a footnote resolves to an actual file. Extract paths from footnote definitions, then confirm each exists relative to the citing document's directory.

**E4: `content/citation-needed-markers`**
Zero `[^citation needed]` or `[^citation-needed]` markers remain (including numbered variants like `[^citation-needed-1]`).

**E5: `content/claim-accuracy`**
Every claim accurately reflects what its cited source says. No distortion, overstatement, or fabrication. Applies to paraphrases and quotes alike.

**E6: `content/multi-source-validation`**
When a claim cites multiple sources `[^1][^2][^3]`, ALL cited sources support that specific claim. Remove any that don't.

---

## Warning Rules (Should Fix)

**W1: `format/link-in-definition`**
Every `[^N]:` definition contains a markdown link `[text](path)`, not bare text.

**W2: `density/minimum-citations`**
Document meets minimum citation density for its type. **SKIP if no per-repo density target is configured.**

**W3: `density/orphaned-sources`**
Every raw source file in the source directory is cited at least once. No orphaned sources. **SKIP if no per-repo source directory is configured.**

**W4: `content/frequency-accuracy`**
Claims like "mentioned in X/Y sources" match actual counts when verified.

---

## Info Rules (Optional)

**I1: `format/footnote-numbering`**
Footnotes are sequential (1, 2, 3...) with no gaps or duplicates.

**I2: `content/quote-accuracy`**
Direct quotes (blockquotes with citations) appear verbatim in the cited source. Note: E5 covers substantive distortion of meaning. I2 covers minor verbatim deviations (punctuation, capitalization, ellipsis) that don't change meaning.

**I3: `content/anchored-references`**
Citations to source code use `:FunctionName` or `:TypeName.MethodName` (not line numbers). Citations to long non-code files include line numbers (`:START-END`).

**I4: `format/context-in-definition`**
Definitions include descriptive display text, not just a bare file path.

---

## How to Check

**Automated (run first):**

```bash
# E1: Dangling references or orphaned definitions
# Note: assumes definitions are on dedicated lines. If a line has both
# a definition and an inline reference, the inline ref will be missed.
grep -Ev '\[\^[0-9]+\]:' <file> | grep -Eo '\[\^[0-9]+\]' | grep -Eo '[0-9]+' | sort -un > /tmp/refs.txt
grep -Eo '\[\^[0-9]+\]:' <file> | grep -Eo '[0-9]+' | sort -un > /tmp/defs.txt
diff /tmp/refs.txt /tmp/defs.txt

# E2: Citations pointing to derivative files (triage false positives manually)
grep -Ern '\[\^[0-9]+\]:.*(synthesis|analysis|summary)' <path>

# E3: Extract footnote paths — manually verify each exists
# (no single portable command; read each definition and check the path)

# E4: Unresolved markers (second pattern catches numbered variants)
grep -rn '\[\^citation needed\]' <path>
grep -rn '\[\^citation-needed' <path>

# W1: Definitions without links
grep -E '\[\^[0-9]+\]:' <file> | grep -v '\[.*\](.*)'

# W2: Citation count (skip if no density target configured)
grep -Ec '\[\^[0-9]+\]:' <file>

# I1: Footnote numbering gaps
grep -Eo '\[\^[0-9]+\]:' <file> | grep -Eo '[0-9]+' | sort -n
```

**Manual (required for accuracy rules):**

For E5, E6, W4: Read cited source files and compare against claims. No shortcut — this is the core review task. Verify in batches of ~10 source files.

Long files: load the `md` skill and use `md toc` + `md blocks` to read only the flagged sections instead of the whole document. Grep stays primary for detection.

---

## Report Format

```
== Citation Review: <file> ==
DATE: YYYY-MM-DD
REVIEWER: [agent-id]

ERRORS (must fix):
  [E1] PASS/FAIL — [details]
  [E2] PASS/FAIL — [details]
  [E3] PASS/FAIL — [details]
  [E4] PASS/FAIL — [details]
  [E5] PASS/FAIL — [details]
  [E6] PASS/FAIL — [details]

WARNINGS (should fix):
  [W1] PASS/FAIL — [details]
  [W2] PASS/FAIL/SKIP — [details]
  [W3] PASS/FAIL/SKIP — [details]
  [W4] PASS/FAIL — [details]

INFO:
  [I1] PASS/FAIL — [details]
  [I2] PASS/FAIL — [details]
  [I3] PASS/FAIL — [details]
  [I4] PASS/FAIL — [details]

VERDICT: PASS | PASS WITH NOTES | FAIL
NOTES: [justification for any deferred warnings]
```

---

## Verdict Criteria

| Result | Criteria |
|--------|----------|
| **PASS** | Zero errors, warnings fixed or documented |
| **PASS WITH NOTES** | Zero errors, warnings acknowledged with justification |
| **FAIL** | Any error rule fails |

---

## Per-Repo Configuration

This review skill applies universal rules. Your repo may define additional context:

- **Source locations** for E2 checks (what paths count as "derivative" vs. "original")
- **Density targets** for W2 (minimum citation counts by document type)
- **Source directories** for W3 (where to look for orphaned sources)
- **Verification scripts** for automated first-pass checking

Without per-repo configuration, W2 and W3 are skipped. All other rules apply universally.

---

## References

- **Citation workflow:** `muse-skills/citation/SKILL.md`
