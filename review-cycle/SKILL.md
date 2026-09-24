---
name: review-cycle
description: "Iterative review cycle: commit work, spawn 2 independent reviewer agents, fix all issues, repeat until both approve. Use after implementing a feature."
---

# Review Cycle

Run an iterative review cycle to ensure quality before merging. Never review your own work — always spawn dedicated review agents.

## Lifecycle

```
Rebase onto main (if behind)
  └── git merge-base --is-ancestor main HEAD → if not, rebase first, fix conflicts, re-run tests
Commit all changes
  ├── Spawn 2 reviewer agents as sub-agents (they inherit git state)
  ├── Wait for both reviewers to complete (`ib list`)
  ├── Read each reviewer's feedback (`ib look REVIEWER_ID`)
  ├── Fix ALL issues — including non-blocking ones
  │     └── If you disagree, document why — don't silently ignore
  ├── If ANY changes were made → commit and start a new review round
  └── Only done when both reviewers come back with no issues and give the all-clear
```

## Pre-flight: Rebase Check

Before spawning reviewers, verify the branch is current with main:

```bash
git log --oneline HEAD..main
```

- **No output** — main has no new commits; branch is up to date, proceed
- **Has output** — main has moved ahead; rebase first:
  ```bash
  git rebase main
  ```
  Resolve any conflicts, re-run `bun test` and `bunx tsc --noEmit`, commit, then start the review cycle.

## Spawn Review Agents

Spawn 2 `--worker` agents, each with a different focus area. Every reviewer prompt should include:
1. Your agent ID so they can run `ib diff YOUR_AGENT_ID`
2. A single clear focus area
3. Instructions to read CLAUDE.md for project-specific conventions
4. The structured output format below

### Reviewer Prompt Template

```bash
ib new-agent --worker "You are a code reviewer focusing on [FOCUS AREA].

Review the changes by running: ib diff AGENT_ID
Also run: git log --oneline main.. (to see commit history)

Read CLAUDE.md for project-specific conventions and code quality standards.

Focus exclusively on: [FOCUS AREA DESCRIPTION]

Format your review as:

## Review: [FOCUS AREA]
### Issues Found
- [file:line] Description of issue and suggested fix
### Approved Items
- Brief list of things that look good
### Verdict
APPROVED or CHANGES NEEDED

If CHANGES NEEDED, be specific about what must change.

When done, signal completion with: ib send YOUR_AGENT_ID 'Review complete: [APPROVED or CHANGES NEEDED] — [one-line summary]'"
```

Replace `YOUR_AGENT_ID` with your own agent ID so reviewers report back to you.

### Review Areas

Pick 2 focus areas appropriate to the changes. Common areas:

- **Correctness**: Logic errors, incorrect behavior, missing error handling, off-by-one errors
- **Architecture**: Correct layer placement, consistency with existing patterns, proper use of existing libraries, single responsibility, no unused code
- **Concurrency**: Thread safety, proper resource cleanup, consistent concurrency model (don't mix paradigms)
- **Edge Cases & Safety**: Empty/null inputs, error states, data corruption risk, backwards compatibility

Use more reviewers for higher-risk changes (data handling, sync, persistence).

## After Reviews Complete

1. Read all reviewer output: `ib look REVIEWER_ID`
2. Kill completed reviewers: `ib kill REVIEWER_ID --force`
3. Fix **every** issue — including non-blocking ones (or document why you're not fixing it)
4. **If you made ANY changes, commit and start a new review round** — no exceptions
5. Repeat until both reviewers return APPROVED with no issues

## Done

The cycle is complete only when both reviewers come back with zero issues and give the all-clear.
