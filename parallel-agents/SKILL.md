---
name: parallel-agents
description: Orchestrate large tasks by decomposing them into parallel subtasks using ib agents. Use when a task can be split into independent pieces that different agents can work on simultaneously.
---

# Parallel Agent Orchestration

You are a manager orchestrating a large task by breaking it into parallel subtasks using `ib` agents. Your job is to plan, decompose, spawn workers, monitor progress, and merge results.

## Core Principles

1. **Analyze before spawning** — understand the full scope before creating any agents
2. **Decompose into independent pieces** — workers should not edit the same files
3. **Workers own their quality** — each worker self-reviews before signaling completion (see `the review-cycle skill`)
4. **Merge one at a time** — review each worker's diff and merge sequentially to avoid conflicts

## Step 1: Analyze and Decompose

Before spawning any agents:
1. Read relevant code and docs to understand the full scope
2. Identify independent subtasks that won't conflict (different files/areas)
3. Define clear boundaries and acceptance criteria for each subtask
4. Identify ordering dependencies (what must complete before what)

### Good Decomposition (Independent)
- Different files or modules
- Different features with no shared state
- Tests for different components
- Documentation for different areas
- Translations for different languages

### Bad Decomposition (Will Conflict)
- Multiple agents editing the same file
- Changes that depend on each other's output
- Shared state modifications without coordination
- Sequential operations split across agents

### When Tasks Depend on Each Other

If subtask B depends on subtask A:
1. Spawn A first
2. Wait for A to complete and merge
3. Then spawn B (it will get A's changes in its worktree base)

Or spawn both but tell B explicitly:
```
"Note: Another agent is working on [A's task]. Your work should be independent of those changes.
If you find you need changes from that work, use `ib ask` to notify the manager."
```

## Step 2: Spawn Workers

Each worker prompt must include:
- **Context**: What overall goal this is part of
- **Scope**: Exactly which files/areas to modify (and what NOT to touch)
- **Acceptance criteria**: Specific, verifiable requirements
- **Review instructions**: Tell the worker to follow the self-review pattern

```bash
ib new-agent "SUBTASK DESCRIPTION

Context: [what this is part of, what the overall goal is]
Scope: [exactly which files/areas to modify]
Manager agent ID: YOUR_AGENT_ID
Acceptance criteria:
- [specific criterion 1]
- [specific criterion 2]
Do NOT modify files outside your scope.

When your implementation is complete, follow the self-review process in the review-cycle skill — spawn review agents, integrate their feedback, and only signal completion once all reviewers approve."
```

## Step 3: Monitor Progress

```bash
# Check all agent statuses
ib list

# Look at a specific agent's output
ib look AGENT_ID

# Check for questions from agents
ib questions

# Acknowledge a question
ib acknowledge QUESTION_ID

# Review an agent's code changes
ib diff AGENT_ID
```

## Step 4: Merge Results

Once workers report complete (after their own review cycles):

```bash
# Review the final diff
ib diff AGENT_ID

# If satisfied, merge
ib merge AGENT_ID --force

# If issues remain, send feedback
ib send AGENT_ID "Issue found: [description]. Please fix and re-review."
```

Merge workers one at a time. After each merge, check for conflicts before merging the next.

### Optional: Manager-Level Review Before Merge

For critical changes, spawn a final reviewer before merging:

```bash
ib new-agent "Final review before merge of agent WORKER_AGENT_ID.

Run: ib diff WORKER_AGENT_ID
Review the complete diff for:
- Conflicts with other recently merged work
- Cross-cutting concerns the worker might have missed
- Overall coherence with the project goals

Write your verdict. If approved, the manager will merge."
```

## Agent Communication

### Worker → Manager
Workers are automatically monitored — the manager is notified when a worker completes or stops. If a worker is blocked by something it can't resolve on its own, it can use `ib ask` to escalate to the user.

### Manager → Worker
Managers use `ib send` to communicate:
```bash
ib send AGENT_ID "Scope clarification: Yes, include that module in your scope."
ib send AGENT_ID "Another worker merged changes that affect your files. Pull latest and resolve any issues."
```

## Example: Large Feature Implementation

Goal: "Add notifications support to the settings, list view, and detail view"

```bash
# Worker 1: Settings UI
ib new-agent "Add notification preferences to the Settings screen.

Context: We're adding notifications across the app. You own the settings UI only.
Scope: Files in src/settings/ and related views
Acceptance criteria:
- Notification toggle in settings
- Preferences persist correctly
- Follows existing settings patterns

When complete, follow the self-review process in the review-cycle skill"

# Worker 2: List view
ib new-agent "Update List view to show notification badges.

Context: We're adding notifications across the app. Settings are handled separately.
Scope: Files in src/views/list/ and related components
Acceptance criteria:
- Badge indicators on unread items
- Badge clears when item is viewed
- Consistent with existing list item patterns

When complete, follow the self-review process in the review-cycle skill"

# Worker 3: Detail view
ib new-agent "Update Detail view to show notification content.

Context: We're adding notifications across the app. Settings are handled separately.
Scope: Files in src/views/detail/ and related components
Acceptance criteria:
- Notification content displays inline
- Dismiss/mark-read action works
- Follows existing detail view patterns

When complete, follow the self-review process in the review-cycle skill"
```

## Quick Reference

```bash
ib new-agent "TASK"     # Spawn a worker
ib list                  # Check all agents
ib look AGENT_ID         # View agent output
ib diff AGENT_ID         # Review agent's changes
ib send AGENT_ID "msg"   # Send message to agent
ib questions             # Check agent questions
ib acknowledge QID       # Acknowledge a question
ib merge AGENT_ID --force  # Merge agent's work
ib kill AGENT_ID --force   # Kill without merging
```
