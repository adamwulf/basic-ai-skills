---
name: review-cycle
description: "Iterative review cycle: commit work, spawn 2 independent reviewer agents, fix every code issue and meaningful doc issue, repeat until a round finds none. Use after implementing a feature."
---

# Review Cycle

Get independent reviews before merging. Never review your own work — always spawn dedicated review agents.

Keep the result clear, concise, simple, and comprehensive. The goal is correct code, not a review with zero comments.

## What to fix

- **Fix every code issue** the reviewers find.
- **Fix meaningful documentation issues:** a doc or comment that is wrong, misleading, or missing something a reader needs.
- **Skip documentation nits:** wording, style, and phrasing preferences.
- **Skip super-edge cases:** a finding needs a realistic cause in normal use. Planted or adversarial filesystem states, deliberate races, and theoretical combinations do not count, unless CLAUDE.md or the plan says they do.
- **Stay in scope.** Review and fix only the change and its stated goal. Do not get pulled into cleaning up comments or code outside it. List anything out of scope in your final report instead.
- If you disagree with a finding, say why in your report. A design question goes to the user.

## Lifecycle

```
Rebase onto main if behind (git log --oneline HEAD..main); re-run tests
Commit all changes
  ├── Spawn 2 reviewer agents
  ├── Read both reports; check each finding against the code
  ├── Fix per "What to fix"; commit
  ├── Did the fixes change code? → start a new round that reviews the fixes
  └── Only docs or comments changed → done
Done when a round finds no code issues and no meaningful doc issues.
```

## Spawn Review Agents

Spawn 2 worker agents (`--type worker`), each with a different focus. Write each prompt to a file, then run:

```bash
ib new-agent --type worker -f <prompt-file>
```

Do not pass `--name`, even if other instructions tell you to name agents. Generic names like `review-correctness` collide with reviewers from other rounds and other agents. An unnamed agent gets a unique ID. Use the ID that `ib new-agent` prints.

Each prompt includes:
1. How to see the change: `ib diff YOUR_AGENT_ID` and `git log --oneline main..`
2. One focus area, and the stated goal of the change
3. "Read CLAUDE.md for project conventions"
4. Any decisions the user already made (do not re-litigate them)
5. The "What to fix" rules above, so reviewers do not report nits or super-edge cases
6. In a later round: the fixes to verify
7. "Do not edit files. Report only."
8. The output format:

```
## Review: [FOCUS AREA]
### Issues
- [file:line] Problem, realistic cause, fix
### Out of scope (optional)
- ...
### Verdict
APPROVED or CHANGES NEEDED

When done: ib send YOUR_AGENT_ID 'Review complete: [APPROVED or CHANGES NEEDED] — [one-line summary]'
```

Common focus areas: **Correctness**, **Architecture**, **Concurrency**, **Data safety**. Use more reviewers for higher-risk changes (data handling, sync, persistence).

## After Reviews Complete

1. Read each report: `ib look REVIEWER_ID --lines 200`
2. Retire each finished reviewer: `ib retire REVIEWER_ID`
3. Fix, commit, and follow the Lifecycle

## Done

Done when a round finds no code issues and no meaningful doc issues. Your final report lists what was fixed, what was skipped and why, and anything out of scope.
