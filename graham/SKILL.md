---
name: graham
description: Read and write Google Drive, Docs, Sheets, and Slides from the terminal with the `graham` CLI. Use it to find, create, export, and organize files; read and write Sheet values; and read and edit the content and formatting of Docs and Slides. Talks to the Google Workspace REST APIs over OAuth.
---

# graham — Google Workspace from the terminal

`graham` is a CLI for Google Drive, Docs, Sheets, and Slides. It talks to the
Google REST APIs over OAuth. Use it to find and organize files, create and
export documents, read and write Sheet values, and read and edit the content
and formatting of Docs and Slides.

This skill explains how to get started and how the commands are shaped. It
does not list every command. For the flags of anything, run `graham --help`,
`graham <service> --help`, or `graham <service> <command> --help`.

## Get started

1. **Credentials.** `graham` reads `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   and `GOOGLE_REFRESH_TOKEN` from the environment or from the nearest `.env`
   file, walking up from the working directory. The environment wins over
   `.env`. The client id and secret come from a Google Cloud OAuth client; that
   one-time setup is in the project `README.md`.
2. **Log in once.** `graham auth login` opens a browser for consent and writes
   the refresh token to `.env`.
3. **Check.** `graham auth status` shows which credentials are set and tests a
   token refresh. Run it first. If a command fails with an auth error, run
   `graham auth login` again.

Gotcha: an *External* OAuth app in *Testing* mode issues refresh tokens that
expire after 7 days, so `auth login` is needed about weekly. An *Internal* or
*Published* app has no such expiry.

## How commands are shaped

- `graham <service> <command> [<id>] [flags]`. The service is `drive`, `docs`,
  `sheets`, or `slides`. Related commands nest in groups, for example
  `docs table add-row` or `sheets chart add`.
- Almost every command takes a file id. Get one from `graham drive list` or
  from the file's URL: `https://docs.google.com/document/d/<id>/edit`.
- Commands that list things take `--format table|json|jsonl|id`. `table` is
  the default, `json` carries the full detail, and `id` prints bare ids for
  scripts.
- Formatting nouns are `get`/`set` pairs that take the same range options:
  `docs paragraph get|set`, `docs style get|set`, `slides notes get|set`.
  `get` prints values in the units `set` takes, so a value read can be
  written straight back.
- Write commands print the id of what they made or changed.
- Positions are one-based: slide positions, table rows and columns, tab
  positions. Docs and Slides text indices are zero-based UTF-16 code units, as
  the APIs define them. Read the current indices with `graham docs structure`
  before a text edit; every edit shifts the indices after it.

## Finding files

`graham drive list` spans My Drive and every shared drive.

```bash
graham drive list                                   # the roots
graham drive list <folder-or-drive-id>              # a folder's contents
graham drive list --query "name contains 'budget'" --type sheets --limit 20
graham drive get <file-id> --format json            # one file's metadata
```

`--type` is `docs|sheets|slides|folders|all`. `--query` is a raw Drive `q`
string.

## What each service does

- **drive** — list and search; get metadata; create Docs, Sheets, Slides,
  folders, shortcuts, and copies (`drive create` is the only way to make a
  document); export a Workspace file (`--type pdf|docx|csv|...`) or download a
  binary file; rename, move, star, trash, untrash, and delete.
- **docs** — read as text, Markdown, or JSON (`cat`); list blocks with their
  index ranges (`structure`); insert, delete, and replace text; get and set
  paragraph and text style; lists, tables, images, page and section breaks,
  headers, footers, footnotes, named ranges, page setup, tabs, and smart
  chips.
- **sheets** — spreadsheet metadata (`get`); read values (`values`); write,
  append, and clear values; tabs, freeze, resize, merge, and sort; cell format
  and borders; named ranges, conditional format, validation, filters, and
  protection; charts.
- **slides** — all text (`cat`); every element with its geometry and ids
  (`list`); layouts and images; add, move, and delete slides; create, move,
  style, and group elements; tables; text insert, delete, style, paragraphs,
  and bullets; speaker notes; alt text; chart refresh.

Each service has a live smoke test (`graham docs test`, and the same for
`drive`, `sheets`, and `slides`). It creates a file in a "graham test" folder,
exercises the API, and trashes the file.

## Typical flow

1. `graham auth status`.
2. `graham drive list --query "name contains '...'"` and copy the id, or
   `graham drive create doc "Name"` for a new file. Both print the id.
3. For a Docs or Slides edit, read first: `graham docs structure <id>` or
   `graham slides list <id> --format json`. Then write with the indices or
   object ids it printed.
4. Re-read after a write when a later edit depends on the new indices.
