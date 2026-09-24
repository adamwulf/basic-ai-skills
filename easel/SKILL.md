---
name: easel
description: Manage Canvas LMS courses from the terminal with the `easel` CLI — list courses and people, read and update wiki pages and assignments (title, body, publish state, due/availability dates, points), and create/update assignment rubrics. Use when asked to read, verify, or update Canvas course content (any Canvas API instance).
---

# easel — Canvas LMS CLI

`easel` reads and updates Canvas course content. Output is JSON on stdout; logs go to `~/Library/Logs/easel/`, so stdout stays clean for parsing.

## Setup

Install: `mint install adamwulf/easel@main --force`

Config comes from a `.env` file (found by walking up parent directories from the working directory) or environment variables. Env vars beat `.env`; `--host` beats both.

```
CANVAS_API_KEY=<access token>     # never print or read this value
CANVAS_HOST=<your.canvas.host>
```

If a command fails with a missing key/host error, the `.env` is absent or incomplete — ask the user rather than guessing a host (a wrong host would receive the token).

## Commands

Every command accepts `--format json|jsonl|smalljsonl|md|id` (default `json`) and `--host <domain>`. `smalljsonl` is one slim JSON object per line (id/title + a few key meta fields, no nested bloat); `md` is human-readable Markdown (heading + field list per record, with bodies and rubric/enrollment/criteria tables). Run `easel help <subcommand>` for all flags.

```bash
# Find course ids first — everything else needs one
easel courses                        # all courses, JSON
easel courses --format id            # ids only
easel courses --enrollment-type teacher

# Pages (identified by url slug, or page_id:<id>)
easel pages <course-id>              # list (no bodies)
easel page <course-id> <slug>        # one page with HTML body
easel update-page <course-id> <slug> --title "..." --body-file f.html --published true

# Assignments (identified by numeric id)
easel assignments <course-id>
easel assignment <course-id> <id>    # includes description + rubric
easel update-assignment <course-id> <id> --name "..." --description-file f.html \
  --published true --points 100 --due-at "2026-09-05T23:59:00-05:00" \
  --unlock-at "2026-08-24T00:00:00-05:00" --lock-at "2026-09-13T23:59:00-05:00"

# People
easel users <course-id> [--enrollment-type student] [--search name]

# Rubrics
easel rubrics <course-id>
easel rubric <course-id> <rubric-id>
easel create-rubric <course-id> --assignment <id> --file rubric.json
easel update-rubric <course-id> <rubric-id> --file rubric.json
```

Notes:
- `--body`/`--body-file` (and `--description`/`--description-file`) are mutually exclusive; `-` means stdin. Content is HTML.
- Update commands send only the flags you give; everything else stays untouched.
- Dates must be full ISO 8601 **with a time zone** (`2026-09-05T23:59:00-05:00` or `...Z`); zone-less values are rejected. Canvas stores and returns UTC (`Z`).

Rubric JSON (`create-rubric`/`update-rubric` replace title + criteria):

```json
{
  "title": "Essay Rubric",
  "criteria": [
    { "description": "Thesis", "points": 5,
      "ratings": [ { "description": "Excellent", "points": 5 },
                   { "description": "Missing", "points": 0 } ] }
  ]
}
```

## Typical workflow

1. `easel courses --format json` → find the course id.
2. `easel pages <id>` / `easel assignments <id>` → see what exists (ids, titles, publish state).
3. `easel page <id> <slug>` / `easel assignment <id> <aid>` → read current content to compare against planning material.
4. `update-page` / `update-assignment` / rubric commands → apply changes; the command prints the updated object, which confirms the write.

## Can and can't

**Can:** list courses; list/read/update pages and assignments (titles, HTML bodies/descriptions, publish/unpublish, due + unlock/lock dates, points, scheduled page publication); list people with roles/emails; list/read/create/update rubrics and attach them to assignments.

**Can't (not implemented):** create or delete pages/assignments; grades, submissions, or feedback; modules, quizzes, files, announcements, or discussions; enrollment changes. Pages have no unlock/lock dates (Canvas limitation) — only `--publish-at`.

Errors are one-line messages on stderr (401 = bad token, 404 = wrong id/slug). Transient 429/5xx are retried automatically.