---
name: ib-merge
description: Review and merge an ittybitty agent's work after verifying it passed a review cycle. Checks for reviewer approval, does a manager-level review, merges, and runs post-merge tests. Use when an agent signals completion and is ready to merge.
argument-hint: <agent-id>
allowed-tools: [Bash, Read, Grep, Glob]
---

Please thoroughly review agent `$ARGUMENTS` before merging. Be methodical — slow is smooth, smooth is fast.

## Step 1: Understand the Context
- Run `ib look $ARGUMENTS` to see recent agent output and understand what it did
- Run `ib status $ARGUMENTS` to see commit history and files changed

## Step 2: Verify Review Cycle
- Check the agent's output (`ib look $ARGUMENTS`) for evidence of a completed review cycle
- Look for: reviewer agents spawned, "APPROVED" verdicts, all issues fixed
- **If no review cycle evidence**: ask the user — "This agent doesn't appear to have run a review cycle. Merge anyway?"
- Do NOT proceed without either review cycle evidence or explicit user confirmation

## Step 3: Verify Tests Were Run
- Agents cannot run tests from their worktrees — tests must be run from the main repo
- Check the agent's output for evidence that the agent confirmed tests pass or noted which tests are relevant
- If the agent claims tests pass, note which tests to verify post-merge (Step 6)

## Step 4: Manager-Level Code Review
- Run `ib diff $ARGUMENTS` to see the full diff
- For each changed file, verify:
  - Does the change solve the stated goal?
  - Are there hardcoded values that should use variables/constants?
  - Edge cases handled? Error conditions?
  - Security concerns (command injection, path traversal)?
- Did the agent update documentation (CLAUDE.md) if needed?
- Run `ib merge-check $ARGUMENTS` to verify no merge conflicts

## Step 5: Send Feedback or Merge
- If ANY issues found: `ib send $ARGUMENTS "detailed feedback"` and wait for fixes
- Only merge when ALL concerns are addressed: `ib merge $ARGUMENTS --force`

## Step 6: Run Tests After Merge
- After merging, run project tests from the main repo to verify the merged code
- Check CLAUDE.md for the project's test commands
- If tests fail after merge, investigate and fix immediately (you're now on main)

## Important
- Never merge incomplete or questionable work
- When in doubt, send feedback and ask the agent to explain or fix
- Multiple rounds of feedback are fine — quality over speed
- Always run tests after merge to catch integration issues
