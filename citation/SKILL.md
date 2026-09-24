---
name: citation
description: "Write, verify, and fix citations in research-to-summary workflows. Cite sources accurately, verify claims against originals, resolve gaps. Use when adding, auditing, or fixing citations in any repo. Load this skill before citing code — line-number citations rot fast, and this skill defines the symbol-based format that doesn't."
---

# Citation Workflow

Every factual claim in a synthesis document must trace to an original source. This skill defines how.

## When to Use

- Writing synthesis from raw research with inline citations
- Adding citations or citing sources in any document
- Verifying or auditing citations in existing documents
- Fixing citations that don't support their claims
- Resolving `[^citation needed]` markers
- Following citation guidelines or citation format rules
- Before finalizing any document that cites sources (then use `/citation-review` or read `muse-skills/citation-review/SKILL.md` directly as the quality gate)

---

## Core Principles

1. **Always cite the most original source available.** Never cite a summary, synthesis, or analysis file when the raw source exists.
2. **Fix, don't flag.** Every inaccuracy found must be corrected, not just noted.
3. **No spot-checking.** Read the full source file before judging any citation to it.
4. **Cite as you write.** Add `[^N]` references inline while drafting — never defer.
5. **When in doubt, be conservative.** If the source doesn't clearly support the claim, fix it.

### What Doesn't Need a Citation

Your own analysis or recommendations (though they should reference cited findings), general knowledge, or insights clearly derived from cited evidence in the same section.

---

## Citation Format

One format, everywhere:

```markdown
Factual claim about the product[^1]. Another claim[^2][^3].

[^1]: [Display text with context](path/to/original-source.md)
[^2]: [Author or source label, date](path/to/file.swift:MyClass.fetchData)
[^3]: [Author, date](https://example.com/external-source)
```

**Rules:**
- Inline reference: `[^N]` where N is sequential
- Definition: `[^N]: [Text](path)` — always use markdown link syntax
- Display text: Include context (author, date, source label, or type)
- Paths: Relative from the citing file; full URLs for external sources
- Source code: For code files, append `:FunctionName` or `:TypeName.MethodName` to the path (not line numbers — they shift too easily)
- Line numbers: For long non-code files, append `:START-END` to the path

**The test:** If a more original version of this source exists, cite that instead.

**HTML files:** Use HTML comments for citations. Place references inline and definitions at the end of the file:
```html
<p>Factual claim about the product<!-- [^1] -->.</p>

<!-- [^1]: [Display text](path/to/source.md) -->
```

**Source code files:** Use the language's comment syntax for citations:
```swift
// Data is stored locally [^1]
// [^1]: [Privacy docs](docs/privacy.md)
```

---

## The Hierarchy Principle

| Cite This (Original) | NOT This (Derivative) |
|---|---|
| Raw research files | Synthesis or summary files |
| Raw transcripts | Analysis files derived from transcripts |
| Original messages (URLs) | Digests or rollups of messages |
| Primary data exports | Reports generated from exports |

If a derivative file references original sources by name or number, trace back and cite those originals instead.

---

## Three-Phase Workflow

### Phase 1: Write with Citations

1. Gather all raw source files. Organize by category or theme.
2. Read sources thoroughly. Note which file contains each piece of evidence.
3. Write thematic sections, adding `[^N]` citations inline as you write.
4. For every factual claim, add a citation immediately. For direct quotes, use blockquote formatting.

```markdown
The product stores all data locally[^1], with no telemetry[^2].

> "No company has access to your data" — Privacy docs[^3]

[^1]: [Source 001](../research/001-homepage.md)
[^2]: [Source 047](../research/047-privacy-controls.md)
[^3]: [Source 047](../research/047-privacy-controls.md)
```

### Phase 2: Verify Accuracy

**Step 1 — Determine your mode:**

Check for prior verification work: `git log --oneline --grep="citation"` to find commits mentioning citation verification. Use the result to determine which mode applies.

| Situation | Mode | Action |
|-----------|------|--------|
| No prior verification | **Net-new** | Full verification from scratch |
| Prior report, incomplete | **Resume** | Continue from last verified batch |
| Sources newer than report | **Refresh** | Re-verify changed/new files only |
| Report complete, sources current | **Verify** | Quick pass to confirm |

**Step 2 — Run automated checks:**

```bash
# Find all citations in a file or directory
grep -Ern '\[\^[0-9]+\]' <path>

# Find unresolved markers (second pattern catches numbered variants)
grep -rn '\[\^citation needed\]' <path>
grep -rn '\[\^citation-needed' <path>

# Count unique citation definitions
grep -Ec '\[\^[0-9]+\]:' <file>
```

Run any repo-specific verification tooling (see Per-Repo Configuration below).

**Step 3 — Manual verification (batches of ~10 source files):**

For each source file:
1. Read the FULL source file
2. Find all citations to it across synthesis files
3. For each citation, read the claiming passage
4. Verify: Does the claim accurately reflect what the source says?

### Phase 3: Resolve and Finalize

**Fix inaccuracies using this decision tree:**

| Problem | Fix |
|---------|-----|
| Claim distorts source meaning | Rewrite claim to match source |
| Quote isn't verbatim | Correct quote or convert to paraphrase |
| Frequency count wrong | Recount and correct |
| Citation partially supports claim | Narrow claim to what source actually says |
| Citation doesn't support claim at all | Remove citation or find correct source |
| Claim is correct but cites wrong source | Find and cite the correct source |
| Sources conflict with each other | Acknowledge the conflict in the text; cite both with context |
| No source exists for claim | Remove claim entirely |

**Resolve all `[^citation needed]` markers:**

1. Understand the claim that needs a source
2. Search raw source files for evidence (grep with key phrases, synonyms)
3. Found? Replace marker with proper `[^N]` citation. Adjust claim text if needed to match what the source actually says.
4. Not found? Remove the unsupported claim
5. If the same claim appears in multiple files, resolve it consistently everywhere

**Final state: zero `[^citation needed]` markers remain.**

---

## Delegating to Sub-Agents

For large tasks (many source files), spawn parallel sub-agents with ~10 source files per batch. Each sub-agent reads this skill file — that's all they need.

### Delegation Flow

1. Manager reads this skill and the repo's Per-Repo Configuration (see below) to identify source and synthesis files
2. Manager divides source files into batches
3. For each batch, copy the quick-start block below into the sub-agent prompt — replace the `[PLACEHOLDERS]` with actual paths before sending
4. Collect sub-agent reports, fix all issues, run `/citation-review` (or read `muse-skills/citation-review/SKILL.md` directly) as final quality gate

### COPY THIS INTO SUB-AGENT PROMPTS

Replace all `[PLACEHOLDERS]` with actual values before sending:
- `[BATCH-FILES]` — list of source files this sub-agent should verify
- `[SYNTHESIS-DIR]` — path to the directory containing synthesis/summary files

```
--- CITATION VERIFICATION QUICK-START ---

YOUR JOB: Verify that citations accurately support their claims,
for source files in your assigned batch.

YOUR BATCH:
[BATCH-FILES]

GOLDEN RULE: Only cite original sources. Never cite synthesis, analysis,
or derivative files. When in doubt, be conservative — fix it.

WHAT "ACCURATE" MEANS:
- Quote: Must be verbatim (or nearly exact) in the source
- Paraphrase: Must capture substance, not distort meaning
- Frequency claim (X/Y sources): Must match actual count

HOW TO CHECK (for each source file in your batch):
1. Read the FULL source file
2. Find all citations to it (use the source filename or a unique substring):
   grep -rn "[SOURCE-FILENAME]" [SYNTHESIS-DIR]/
3. For each citation, read the claiming passage
4. Compare: Does the claim say what the source actually says?

REPORT FORMAT:
  FILE: <source-file>
  STATUS: VERIFIED | NEEDS FIXES
  Claims checked: N
  Issues:
  - Line NN in <synthesis-file>: [problem]
    Source says: "[what source says]"
    Claim says: "[what claim says]"

Do NOT spot-check. Read every source. Check every citation.
--- END QUICK-START ---
```

---

## Per-Repo Configuration

This skill defines universal citation rules. Your repo should define (in its CLAUDE.md or a linked doc):

- **Source locations:** Where raw/original source files live and their naming conventions
- **Original vs. derivative:** What counts as an "original" source vs. a "derivative" in your repo's data model
- **Verification tooling:** Any repo-specific scripts for automated citation checking
- **Density targets:** Expected citation counts by document type (if applicable)
- **Additional format conventions:** Any extensions beyond the standard markdown footnote format

Without per-repo configuration, the universal rules still apply — cite originals, use `[^N]: [Text](path)` format, verify accuracy.

---

## Long Files: Use the `md` Skill

When a source or synthesis file is long, load the `md` skill rather than Read-ing the whole file. The `md` skill is the source of truth for flags, examples, and the block-index-shift gotcha — this section names only which subcommands apply where.

- Phase 2 verification: `md toc` + `md blocks` to pull just the cited section of a long source.
- Phase 3 fixes: `md replace` to rewrite a whole block — a claim paragraph, a resolved `[^citation needed]` marker, a narrowed multi-source citation. For word-level tweaks inside a block, `Edit` is simpler.

---

## Definition of Done

### When writing a document with citations
- [ ] Every factual claim has at least one `[^N]` citation
- [ ] All citations point to original sources (not derivatives)
- [ ] Citation format is consistent: `[^N]: [text](path)`
- [ ] No `[^citation needed]` markers remain
- [ ] Direct quotes match source text verbatim

### When verifying citations
- [ ] Every cited file exists and is accessible
- [ ] Every citation read against its source — claim matches source
- [ ] All inaccuracies fixed (not just flagged)
- [ ] Zero `[^citation needed]` markers remain

### When resolving markers
- [ ] Each marker resolved: source found and cited, OR unsupported claim removed
- [ ] Claim text adjusted to match source where needed
- [ ] Zero markers remain in the final document

## References

- **Quality gate:** `muse-skills/citation-review/SKILL.md`
