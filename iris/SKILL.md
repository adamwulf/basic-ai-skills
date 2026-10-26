---
name: iris
description: Read email over IMAP from the terminal with the `iris` CLI. Use it to list and search a mailbox, show a message or a whole thread as Markdown or JSON, download an attachment, mark a message read or unread, and save new messages, replies, and edited drafts as drafts. Works with Gmail, iCloud Mail, and Zoho Mail. iris never sends mail.
---

# iris — email from the terminal

`iris` reads email over IMAP. It lists a mailbox, shows a message or a whole
thread as Markdown or JSON, and downloads one attachment. It can also mark a
message read or unread and save drafts. It never sends mail: the user reviews
and sends each draft in their mail app.

This skill explains how to get started and how the commands are shaped. It
does not list every option. For those, run `iris --help`,
`iris <command> --help`, or `iris draft <command> --help`.

## Get started

1. **Accounts.** Each account is a group of keys with its name in the middle:
   `IRIS_<NAME>_IMAP_HOST`, `IRIS_<NAME>_IMAP_USERNAME`,
   `IRIS_<NAME>_IMAP_PASSWORD` (an app-specific password), and the optional
   `IRIS_<NAME>_IMAP_PORT` and `IRIS_<NAME>_FROM` (the From line of drafts).
   `IRIS_DEFAULT_ACCOUNT` names the account to use without `--account`. iris
   reads the environment and every `.env` from the working directory up to
   `/`; the nearer file wins, and the environment wins over all of them.
   Provider settings and the Gmail OAuth setup are in the project `README.md`.
2. **Check.** `iris accounts` lists the accounts and any missing keys.
   `iris check --account <name>` logs in once to test the settings.
3. **Gmail with OAuth.** An account with `IRIS_<NAME>_GOOGLE_CLIENT_ID` signs
   in with Google instead of a password. `iris auth status` shows whether it
   is still signed in. `iris auth login --account <name>` signs in again; it
   opens a browser, so ask the user to run it.

Gotcha: Google ends the sign-in after 7 days (the app is in Testing mode).
When a command says the Google sign-in has expired, the user must run
`iris auth login` again.

## Read-only first

`iris ro <command>` runs only the commands that change nothing: `accounts`,
`check`, `mailboxes`, `list`, `show`, `thread`, `auth status`, and `download`
without `-o`. Use it for reading; the user may allow only `Bash(iris ro:*)`.
The commands that change mail (`read`, `unread`, and `draft`), `download -o`
(it writes a file), and `auth login` exist only outside `ro`.

## How commands are shaped

- A message is named by its **iris ID**, `<account>/<mailbox>/<UID>`, such as
  `work/INBOX/4821` or `personal/[Gmail]/All Mail/77`. `iris list` prints it,
  and every command about one message takes it. Always put it in single
  quotes: a mailbox name can have spaces and `[ ]`. Never use a UID alone;
  each mailbox has its own UIDs. A message that moves gets a new iris ID.
- A command that takes an iris ID has no `--account`: the ID names the
  account. The other commands take `--account <name>` (`-a`), or use the
  default account.
- An **attachment ID** is the part's MIME section, such as `2` or `1.2`.
  `iris show` lists it first on each attachment line (`attachmentID` in
  JSON).
- The list commands (`accounts`, `mailboxes`, `list`, `auth status`) take
  `--format table|json|jsonl|id`. `id` prints one iris ID per line.
- stdout holds only data. Hints (such as the next-page command) and errors go
  to stderr. Errors say what to do next.
- Reading never marks a message as read. Only `iris read` and `iris unread`
  change that; each sets the state, so running one twice is safe.

## Finding mail

```bash
iris mailboxes                                  # names and roles (\Drafts, \Sent, \All, ...)
iris list                                       # the newest 25 in INBOX
iris list --mailbox '[Gmail]/Sent Mail' --page 2 --limit 50
iris list --unread --from jane@example.com --since 2026-10-01
iris list --search invoice --format json        # the text in any header or the body
```

The filters combine: a message must match all of them. The server does the
matching (IMAP SEARCH), and many servers, Zoho among them, match whole words,
not parts of words: "Champ" does not find "Champion". `--since` and
`--before` compare the day the server received the message.

## Reading

- `iris show '<iris-id>'`: one message as Markdown, with its attachments and
  their attachment IDs. The quoted history and the signature at the end are
  hidden; `--full` shows them. `--body text` shows the plain-text part,
  `--format json` the same message as JSON, and `--format raw` the exact
  `.eml` source.
- `iris thread '<iris-id>'`: every message of the thread, oldest first, from
  INBOX, Sent, Drafts, Archive, All Mail, and the message's own mailbox.
  `--format id` lists their iris IDs and downloads no message.
- `iris download '<iris-id>' <attachment-id> > report.pdf`: one attachment's
  bytes on stdout (it refuses to write to a terminal). `-o <path>` saves a
  new file at exactly that path instead, and never overwrites one.

## Writing drafts

`iris draft new`, `iris draft reply '<iris-id>'`, and
`iris draft update '<iris-id>'` save a draft in the `\Drafts` mailbox and
print its iris ID. The body is Markdown from exactly one source: the
argument, `-F <path>` (`-F -` is stdin), or stdin. A body that starts with
`-` needs `--` before it. `--attach <path>` attaches one file; repeat it for
each file.

- `draft new` needs `--to` (one address each; repeat it) and `--subject`.
  `--cc` and `--bcc` are optional.
- `draft reply` quotes the original under the reply and sets the threading
  headers. `--all` replies to all; `--no-quote` leaves out the quote.
- `draft update` replaces a saved draft's body, and keeps its recipients,
  subject, threading, and attachments. It adds no quote. It saves a new copy
  and deletes the old one, so use the new iris ID it prints from then on.

When saving or updating a draft does not finish, the server may still have
saved it, and the error names the mailbox to look in. Look there (and tell
the user) before trying again: a second try can save a second draft.

## Typical flow

1. `iris ro accounts`, and `iris ro auth status` for a Google account.
2. `iris ro list` with filters, and copy an iris ID.
3. `iris ro show '<iris-id>'` or `iris ro thread '<iris-id>'`.
4. To answer, `iris draft reply '<iris-id>' -F reply.md`. Give the user the
   draft's iris ID to review and send in their mail app.
