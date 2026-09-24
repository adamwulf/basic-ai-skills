---
name: battlecard-research
description: "Orchestrate a research → battlecard → comparison workflow for choosing between N candidates (products, vehicles, vendors, frameworks, etc). Each candidate gets its own research phase, cited battlecard, and review cycle. Cross-candidate comparison only happens at the end, after all battlecards are approved. Use when the user wants a decision-grade, cited comparison across multiple options."
---

# Battlecard Research

A structured workflow for turning "help me choose between these N options" into a defensible, cited, reviewed comparison. Per-candidate research is isolated so new questions discovered mid-research can trigger focused re-research without polluting other candidates.

Installed at `~/.claude/skills/battlecard-research/`; worker prompts reference it via `<skill-root>` (manager substitutes the absolute path before spawning — worktrees don't carry `~/.claude` and `~` expansion isn't guaranteed). All workflow *outputs* land in the user's target repo.

**Referenced skills** (load these when invoked): `citation` (inline citation format, Phase 3), `citation-review` (pre-merge lint, Phases 4 & 7), `review-cycle` (two-reviewer iteration, Phases 4 & 7), `parallel-agents` (worker orchestration, Phases 2–4).

## Glossary

- **Subject / subject-slug** — the stable real-world thing (a car model, SaaS product) and its directory name in the shared library. Persists across runs.
- **Candidate / candidate-slug** — the role a subject plays in one run, and its battlecard filename. Often equals subject-slug; diverges only when one run treats the same subject as two candidates (variants).
- **Domain** — the broad category (`used-ev`, `saas-pm-tool`). Set in Phase 1, reused across runs; new domains require user sign-off.

## When to Use

For ≥4 candidates needing a rigorous, cited, auditable comparison (major purchases, vendor selection, tech stack, hiring frameworks). Works for 2-3 but overhead is disproportionate. **Don't use for** quick Q&A, single-candidate deep dives, or work where citations aren't needed.

## Core Principles

- **Goal before research.** Nail down what the user is deciding before collecting a single source.
- **Raw research is a first-class shared library.** Every fetched source is its own `.md` with frontmatter in a repo-wide directory; battlecards cite these files, not the live web. Frontmatter (subjects, topics, domain) drives reuse across runs.
- **One candidate = one isolated battlecard pipeline** — each candidate runs its own research → cite → review loop; shared *raw research* is fine and expected.
- **Compare last, review everything.** No cross-candidate synthesis until every battlecard is reviewed and approved. Every battlecard *and* the final comparison get a review cycle. Re-research is expected — the first round rarely knows every question.

---

## Directory Layout

`<repo>/` is the user's **target repo** — nothing here is written inside the skill folder.

```
<repo>/
  research/                              # SHARED across all battlecard runs
    _index.md                            # manager-maintained lookup table
    <domain>/                            # e.g. "used-ev", "saas-pm-tool"
      <subject-slug>/                    # e.g. "kia-ev6", "linear"
        001-<short-source-name>.md       # one file per fetched source, immutable
        _gaps.md                         # append-only unresolved questions
        _failed.md                       # append-only failed-fetch log
        _archive/                        # optional: superseded files for clutter control
      _shared/                           # cross-subject research (regulatory, market data)
        001-<topic>.md
  <run-folder>/                          # one folder per run (e.g. "cars", "pm-tools")
    goal.md                              # Phase 1 output
    preference-questions.md              # Phase 4-late artifact
    battlecards/<candidate-slug>.md      # cites ../../research/<domain>/<subject-slug>/
    comparison.md                        # Phase 6 output, cites battlecards/
    universal-guide.md                   # optional domain-wide guidance
    reviews/                             # Phase 7 reviewer output
```

Re-research adds new files (`011-`, `012-`, …) — never overwrite. Older files stay so prior battlecards' citations keep working. `_archive/` moves require updating `_index.md`.

---

## Raw Research File Format

Every fetched source gets its own file. Schema in `<skill-root>/templates/research-file-template.md`. Required frontmatter: `source_url`, `source_title`, `date_fetched`, `subjects` (list — one source can speak to multiple candidates, e.g., a Hyundai/Kia E-GMP recall covers EV6 and Ioniq 5), `topics`, `domain`, `research_round`, `source_type`, `access`.

**Rules.** One file per source URL (multiple sections → subheadings in one file). Preserve original numbers, quotes, dates — paraphrasing is the battlecard's job. Paywalled? `access: paywalled` and capture what you read. Failed fetch? no file — log in `_failed.md`. `research_round` is immutable, set on write, and records the round *within this run*, not across future runs.

**`_gaps.md` and `_failed.md`** are append-only per-subject checklists. Workers add `- [ ] <question>` entries. **The battlecard author ticks resolved entries** with `- [x] → see NNN-*.md` during Phase 3 and Phase 5 re-drafts — re-research workers only add files (the battlecard author judges whether a new file actually closed the gap). **No agent ever deletes entries** — the audit trail must persist.

**Independent sources.** "≥2 independent sources per dimension" requires **different publishers that do not cite each other**. Acceptable: two primaries (manufacturer spec + EPA); primary + secondary that doesn't cite the primary; two reviewers independently testing the same model (even at the same conclusion). Two aggregators repeating one press release are **not** independent. `_shared/` files count toward the threshold for genuinely cross-subject claims.

**Supersedes.** When a newer source updates/contradicts an older one, add the new file and set `supersedes: [<full relative path from research/>]` — e.g., `supersedes: [used-ev/kia-ev6/_archive/sc302-early.md]`. Full relative paths, not bare slugs (slugs collide across domains).

---

## The Seven Phases

### Phase 1: Define the Goal

**Output:** `goal.md` (candidate list in frontmatter + body).

**First, pick and create `<run-folder>`** — short slug (`cars`, `pm-tools`). If it already exists, reuse (continuation) or pick fresh. `mkdir <run-folder>/` at the target repo root.

Then interview until you can write down: (1) **Decision** — one sentence; (2) **Domain** — single slug (**`ls research/` and reuse if matches**; new domains fork the library and require user sign-off); (3) **Candidates in scope** — which N? Why each? Declare each candidate's `subject-slug` (reuse existing); (4) **Hard constraints** — eliminators; (5) **Scoring criteria** — 5-9 dimensions (1-10), specific to *this* user; (6) **Tie-breakers**; (7) **Out-of-scope**; (8) **Source-staleness window** — `staleness_days` (default 60 for recall-sensitive, 180 for stable).

You may jot candidate question *topics* in a `goal.md` scratch section to seed Phase 4-late preference-questions; **do not create `preference-questions.md` yet and do not assign tiers** — tier assignment requires battlecard data.

`goal.md` frontmatter must declare `domain`, `subject_slugs`, `candidates`, `hard_constraints`, `scoring_criteria`, `tie_breakers`, `out_of_scope`, `staleness_days`. The frontmatter `candidates:` list is the canonical structured record (per-candidate `candidate_slug`, `subject_slug`, display); the body's "Candidates in scope" section carries narrative rationale only. Start from `<skill-root>/templates/goal-template.md`.

**Checkpoint:** Get user confirmation on `goal.md` before moving on. A bad goal costs the most.

### Phase 2: Research

**Output:** new files under `research/<domain>/<subject-slug>/NNN-*.md`.

**Pre-flight (manager).** Before spawning workers, scan `research/<domain>/` for matching `subject-slug` folders. For each hit, list existing files and their `topics`/`date_fetched`/`date_published`; judge freshness against `goal.md`'s `staleness_days` and coverage against current criteria; mark each candidate "reusable with gaps" (list what's missing) or "needs fresh research". The per-candidate worker prompt names the specific gaps to fill and files to reuse.

**Worker steps.** Spawn one worker per candidate via `parallel-agents`; the pre-flight scan is authoritative for scope. Each worker:

1. Reads `goal.md` and the canonical schema; uses `out_of_scope` to skip what the user declared irrelevant.
2. Reads existing files in `research/<domain>/<subject-slug>/` to verify reuse — **do not duplicate sources, do not expand beyond named gaps**.
3. Uses `WebSearch` + `WebFetch` to fill gaps per scoring dimension; writes one `.md` per new source with required frontmatter. Numbers continue from highest existing (e.g., `011-` if `010-*.md` exists).
4. Stops when every dimension has ≥2 independent sources (reused + new), or appends unresolved questions to `_gaps.md`.

Good targets: 10-25 source files per candidate (reused + new). **Source quality:** prefer primary (manufacturer specs, government data, standards bodies) over aggregators; prefer recent for fast-moving domains; for subjective dimensions, pull multiple independents and note disagreement; forums/Reddit valid for lived-experience but flag with `source_type: forum`.

**Acceptance / failure modes.** The manager checks each returned worker:
- **Acceptance:** every dimension has ≥2 independent sources OR an explicit `_gaps.md` entry; no duplicate URLs; frontmatter validates.
- **Crash / quota partial:** record partial work, append remaining dimensions to `_gaps.md`, re-spawn focused worker for the missing dimensions. Don't jump to Phase 5 (which is for battlecard-authoring gaps).
- **Contradictory interpretations from two workers:** keep both files (evidence); note disagreement in `_gaps.md`.
- **Hard-constraint gap signaled complete:** re-spawn before merging — eliminators cannot be deferred.
- **NNN-number race** (parallel runs, same subject): manager renumbers at merge — later-merged takes next free number.

Only proceed once every candidate has ≥2 sources per dimension or an accepted `_gaps.md` deferral.

**Manager: update the index** after workers merge — workers are scoped to their subject folder; concurrent `_index.md` edits would conflict.

**Pre-Phase-3 checkpoint.** The manager produces a one-page **research digest** (per-candidate findings + obvious dealbreakers). **Stop and let the user mark candidates as hard-pass before any battlecard is written.** Eliminating here saves a full battlecard + review cycle.

### Phase 3: Write Battlecard (per candidate)

**Output:** `battlecards/<candidate-slug>.md`. Each surviving candidate gets its own worker. Workers must:

1. Read the canonical schema (below) and follow section order exactly; read every file in `research/<domain>/<subject-slug>/` before drafting.
2. Follow the `citation` skill's inline format — cite as you write, `[^N]` inline, definitions point to `../../research/<domain>/<subject-slug>/NNN-*.md`.
3. Fill each section using **only** claims supported by the research folder. If a section can't be filled, mark `[^citation needed]` and list the gap in "Research Gaps" — triggers Phase 5.
4. Compute the Battle Score using `goal.md`'s rubric. Pull `scoring_criteria[].weight` directly from `goal.md` — do not invent or alter. One-line justification per criterion.
5. If `_gaps.md` exists, tick `- [x] → see NNN-*.md` for resolved gaps. Never delete entries.
6. Lightweight self-check before signaling complete (every `[^N]` resolves, schema order intact). **Formal review is Phase 4 — workers do not run their own review-cycle.**

See `<skill-root>/templates/battlecard-template.md`.

### Phase 4: Per-Battlecard Review Cycle

**Required for every battlecard.** Manager-run; must happen even if the worker signaled complete. For each battlecard, run `review-cycle` with two reviewers (both must have read `goal.md` and the `citation` skill):

- **Reviewer A — Citation accuracy:** Run `citation-review`. Every claim traces to a research file; every cited file exists; every quote is verbatim.
- **Reviewer B — Schema + scoring:** Canonical section order? Scores justified? Hard constraints addressed? Research gaps flagged?

Iterate until both approve. **Do not proceed to comparison until every battlecard passes review.**

**Phase 4 late: author `preference-questions.md`.** Once all battlecards are approved, the manager (or one dedicated worker) authors it using approved Battle Score data. Seed from `goal.md`'s "Preference-question topic scratch", expanding each into a real question grounded in battlecard data. The template (`<skill-root>/templates/preference-questions-template.md`) requires per-candidate tier assignments, only defensible after battlecards exist.

**Checkpoint:** After all battlecards pass and `preference-questions.md` is drafted, surface to the user — the "drop/add candidates based on battlecards" decision point before Phase 6.

### Phase 5: Re-Research (as needed)

Triggered in phases 3-4 by: unresolvable `[^citation needed]`, a reviewer question research didn't cover, a new user question, or Research Gaps the author can't tick off.

1. Write the new questions explicitly.
2. Spawn focused workers — one per candidate, scope = only new questions.
3. New files land with higher numbers and `research_round: 2` (or higher) — round is scoped to the current run (round 2 = first Phase 5). Do not inherit round numbers from prior runs.
4. Battlecard author ticks resolved `_gaps.md` entries on re-run of Phase 3; re-research workers only add files.
5. Re-run Phase 3 (affected sections) and Phase 4 (full review) on affected battlecards.

Re-research is **expected**, not a failure mode.

### Phase 6: Cross-Candidate Comparison

**Only start after every battlecard has passed Phase 4.** **Output:** `comparison.md` containing: executive summary (consider / hard-pass + why); master table (candidates × criteria + Battle Score, sorted desc); use-case recommendations ("best for X"); hard-pass list with reasons (including mid-run eliminations); links to every battlecard.

**Source-staleness check (Phase 6 start).** Before composing, scan all cited files (including reused from prior runs) for `date_fetched` older than `staleness_days`. Surface stale files; user decides refresh (focused Phase 5) or proceed with caveat.

**Citation rules:** Every claim cites the relevant battlecard, not raw research — battlecards are authoritative at this stage.

### Phase 7: Comparison Review Cycle

Run `review-cycle` on `comparison.md` with two reviewers:

- **Reviewer A — Independent ranker:** Read `goal.md` + every battlecard. Independently produce your own top-N ranking with reasoning; compare to the doc and surface disagreement with specific criteria weighting.
- **Reviewer B — Integrity:** Run `citation-review` on `comparison.md`. Claims match cited battlecards; master-table numbers match individual battlecards; no candidate silently dropped; hard constraints applied consistently.

Both outputs land in `<run-folder>/reviews/` (target repo, *not* the skill folder).

**Approval** means the reviewer agrees the comparison fairly represents the evidence — *not* that it matches their own ranking. Ranking disagreement is surfaced and recorded, not resolved; the user decides. The deliverable is `comparison.md` plus both reviewer files — ranking dissent is part of the deliverable.

**Checkpoint:** Before finalizing, surface reviewer disagreement (especially the ranker's top-N) to the user.

---

## Handling Run Changes

- **Candidate added mid-run.** Spawn one new research worker (single-candidate Phase 2); Phase 3-4 proceed as ready; Phase 6 waits for the full set.
- **Candidate eliminated mid-run.** Before Phase 3 (at pre-Phase-3 checkpoint): no battlecard, record in `comparison.md` with one-line reason citing the digest. After Phase 3: complete the battlecard, flag hard-pass.
- **Scoring criteria change after battlecards exist.** Targeted Battle Score re-compute + Phase 4 review of just the score table. Don't rewrite battlecards.
- **Source staleness during long runs.** Triggers a refresh check at Phase 6 start; applies to reused files from prior runs too.
- **Variant within a subject (Prius Gen 1 vs Gen 2).** One subject folder; battlecards narrow via `Variants in scope`. Fork only if variants are sourced separately enough that reuse would mislead.
- **Zero-source or near-zero-source candidate.** <2 sources on any dimension after focused re-research → surfaced to user for drop / keep-with-caveats. If kept, battlecard's Recommendation notes which dimensions fall short.
- **Unresolvable reviewer disagreement at Phase 7.** Recorded, not forced into resolution.

---

## Canonical Battlecard Schema

Every battlecard follows this section order. Omit only if genuinely not applicable — do not reorder.

1. **Overview** — what this candidate is, key identifiers (trims, versions, tiers)
2. **<Primary Dimension>** — #1 scoring criterion from `goal.md`
3. **<Secondary Dimensions>** — one per remaining criterion, in `goal.md`'s order
4. **Known Risks / Red Flags** — recalls, defects, lawsuits, outages
5. **Warranty / Support / SLA** — what the user gets when things go wrong
6. **Ownership / Total Cost** — ongoing cost over the user's timeline
7. **Battle Score** — criterion rows (1-10 + one-line justification) + weighted overall
8. **Recommendation** — BUY / BUY WITH CAVEATS / AVOID + 2-3 sentences
9. **Research Gaps** — open questions (feeds Phase 5)
10. **Sources & Citations** — all `[^N]` definitions

Battle Score criteria come from `goal.md` Phase 1. Section names 2-6 customize per domain but stay in this order.

---

## Research Library Index

The shared `research/` grows across runs. **After every research phase** (Phase 2 or Phase 5), the manager updates `research/_index.md` by scanning newly-added files' frontmatter:

```markdown
# Research Library Index

## Domain: used-ev

### Subject: kia-ev6
- `used-ev/kia-ev6/001-kbb-specs.md` — trims, HP, 2024 | topics: [specs, trims] | 2026-03-14
- `used-ev/kia-ev6/002-recharged-degradation.md` — battery degradation | topics: [battery, longevity] | 2026-03-15
- `used-ev/kia-ev6/003-nhtsa-sc327.md` — ICCU recall SC327 | topics: [recalls, reliability] | 2026-03-15
  - supersedes: `used-ev/kia-ev6/_archive/sc302-early.md`
```

The index is convenience — frontmatter in each file is authoritative; if they disagree, frontmatter wins and the index gets updated. `supersedes:` sub-bullets mirror source frontmatter. Never hand-edit only the index. Quick lookups: `ls research/<domain>/<subject-slug>/`, `grep -l "topics:.*reliability" research/<domain>/*/*.md`, `ls research/<domain>/`.

---

## Spawning Workers

Use `parallel-agents` for orchestration. Spawn with `ib new-agent --worker "<prompt>"` — `--worker` is intentional: prompts are tightly scoped, non-interactive, signal-only; the manager owns merging, `_index.md`, and downstream phases. The worker's internal pass is *not* a substitute for the manager-run Phase 4 review cycle.

**Substitute all `<angle-bracket>` placeholders before spawning; never pass literal `<placeholders>` to the worker:** `<skill-root>` (absolute path — worktrees don't reliably expand `~`), `<run-folder>` (per-run folder at target repo root), `<domain>`, `<subject-slug>` / `<candidate-slug>`, `<subject-display-name>`. (`<repo>/` is a diagram-only label — workers run with cwd = target repo root.)

### Research worker prompt (Phases 2 & 5)

One per candidate, isolated to that candidate's subject folder:

```
ib new-agent --worker "Research <subject-display-name> for the decision defined in <run-folder>/goal.md.

Read first:
- <run-folder>/goal.md (decision, constraints, scoring criteria)
- <skill-root>/SKILL.md (this skill — Phase 2 worker steps and source-quality guidance)
- <skill-root>/templates/research-file-template.md (frontmatter format)
- ALL existing files in research/<domain>/<subject-slug>/ — these are prior research you should REUSE where still accurate
- research/_index.md (read-only) to see what's already captured across the library

Your scope: research/<domain>/<subject-slug>/ only. Do NOT touch other subjects' folders or any <run-folder>/ content. Do NOT edit research/_index.md — the manager owns that file. Do NOT move existing files into _archive/ — only the manager does that.

For each scoring criterion in goal.md:
- If existing research covers it with current sources (check date_fetched / date_published against goal.md's staleness_days), leave those files alone and count them toward coverage
- If a gap exists, find ≥2 independent sources (different publishers that don't cite each other) and add new files

Numbering: start from the next unused NNN in research/<domain>/<subject-slug>/. Do not renumber existing files.

If a new source contradicts or updates an older one, add the new file and set supersedes: [<full path from research/>] in its frontmatter — never delete existing files.

Stop when every criterion has ≥2 independent sources (counting reused + new), or append unresolved questions to research/<domain>/<subject-slug>/_gaps.md (one '- [ ] <question>' line per gap; never delete existing entries). Then signal complete."
```

### Battlecard worker prompt (Phase 3)

One per candidate, writing into the per-run folder.

```
ib new-agent --worker "Write <run-folder>/battlecards/<candidate-slug>.md using the canonical schema.

Read first:
- <run-folder>/goal.md
- <skill-root>/SKILL.md (canonical schema section)
- <skill-root>/templates/battlecard-template.md
- The citation skill (inline-citation format)
- EVERY file in research/<domain>/<subject-slug>/

Follow the citation skill's inline-citation format: cite as you write, never paraphrase without [^N], definitions point to ../../research/<domain>/<subject-slug>/NNN-*.md files (relative paths from <run-folder>/battlecards/).

If _gaps.md exists, tick entries your draft now resolves — never delete entries.

If you can't support a claim from the research folder, either (a) drop the claim or (b) flag it in the Research Gaps section. Do NOT fabricate and do NOT fetch new sources — Phase 5 handles gaps.

When the battlecard is complete, do a lightweight self-check: every [^N] resolves, schema order intact. Then signal done. Do NOT run review-cycle yourself — Phase 4 is manager-run."
```

---

## Definition of Done

User checkpoints (anchored inline): end of Phase 1, after the Phase 2 research digest, after Phase 4, and before finalizing Phase 7. Between checkpoints, work autonomously.

- [ ] `goal.md` confirmed by user (frontmatter has `domain`, `subject_slugs`, `candidates`, `scoring_criteria`, `staleness_days`)
- [ ] Every in-scope candidate has ≥2 independent sources per criterion (or accepted `_gaps.md` deferral)
- [ ] `research/_index.md` reflects all files added this run (manager-updated)
- [ ] Every candidate's battlecard passed Phase 4; zero unresolved `[^citation needed]` (resolved by Phase 5 or accepted in Research Gaps)
- [ ] `preference-questions.md` authored after battlecards exist (Phase 4 late)
- [ ] `comparison.md` cites battlecards, passed Phase 7 review-cycle, with two reviewer outputs (A: ranker, B: integrity) in `<run-folder>/reviews/`
- [ ] All research gaps either resolved or documented as known-unknowns in the comparison
- [ ] Source-staleness check passed (or explicitly waived) at Phase 6 start

## References

- Skills: `citation` (inline format), `citation-review` (pre-merge lint), `review-cycle` (two-reviewer iteration), `parallel-agents` (worker orchestration via `ib`)
- Templates: `goal-template.md`, `battlecard-template.md`, `preference-questions-template.md`, `research-file-template.md`
