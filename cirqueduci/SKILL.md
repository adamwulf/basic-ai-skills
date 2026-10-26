---
name: cirqueduci
description: "Drive CircleCI from the terminal with the cirqueduci CLI: find pipelines, trigger builds, approve gates, wait for a job to finish, and read logs, artifacts, and test results. Use when asked to start, approve, check, or wait on a CircleCI build, or to investigate a CircleCI failure."
---

# CircleCI with `cirqueduci`

`cirqueduci` drives the CircleCI v2 API. Run `cirqueduci --help` and `cirqueduci help <subcommand>` for commands and flags.

## Basics

- Drill down with `recent` or `pipelines`, then `workflows <pipeline-id>`, then `jobs <workflow-id>`. Job commands (`job`, `steps`, `logs`, `artifacts`, `tests`, `watch`) take the JOB_NUMBER plus `--project gh/<org>/<repo>`.
- Triggering a pipeline or approving a gate starts real, billable CI work. Do it only when asked, and approve only the gate requested.
- For a failure, run `steps` to find the failed step, then `logs --step "<name>"` to read only that step.
- Download a job's build artifacts with `artifacts <job-number> --project gh/<org>/<repo> --download <dir>`.

## Get notified when a job finishes

Run `watch` in the background, then wait for the notification that it exited. Do not poll or sleep. In Claude Code, use the Bash tool with `run_in_background: true`.

```bash
cirqueduci watch <job-number> --project gh/<org>/<repo> --timeout 3600
```

Exit `0` means success, `1` means failed, and `2` means timed out (the job is still running, so watch again). Watch one job, not a pipeline: a pipeline with unapproved gates never finishes.
