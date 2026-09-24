---
name: websnap
description: Take a screenshot of a web page, extract it as Markdown, or run JavaScript against it. Use when checking page layout, verifying styling changes, inspecting rendered content, reading a page as text, or querying page properties like dimensions.
argument-hint: <url> [-w width] [-h height] [-y scroll] [-f] [-r js] [--format png|md] [--no-js]
allowed-tools: Bash, Read
---

Take a screenshot of the specified URL using `websnap` and display the result.

## Steps

1. Run: `websnap $ARGUMENTS`
2. For screenshots: the command outputs the path to the saved PNG (in `/tmp/`), then use the Read tool to display the image
3. For `--format md`: the command outputs the path to the saved Markdown file (in `/tmp/`), then use the Read tool to display its contents
4. For `-r` (run JS): the command outputs the JavaScript result directly (no screenshot)

## Options

- `-w, --width <px>` — Viewport width (default: 1280)
- `-h, --height <px>` — Viewport height (default: 1080)
- `-x, --xoffset <px>` — Horizontal scroll offset (png only)
- `-y, --yoffset <px>` — Vertical scroll offset (png only)
- `-f, --full` — Capture full page height (ignores -h; png only)
- `-r, --run <js>` — Run JavaScript and output result (no screenshot)
- `--format <fmt>` — Output format: `png` (screenshot) or `md` (Markdown). Default: `png`
- `--no-js` — Disable the page's JavaScript (capture server-rendered HTML; helps with SPA/archived pages where JS rewrites the content). Readability still runs.

## Examples

```
/websnap http://localhost:1313/guide/
/websnap http://localhost:1313/ -w 1920 -h 1080
/websnap http://localhost:1313/guide/ -y 500
/websnap http://localhost:1313/ -f
/websnap http://example.com -r 'document.title'
/websnap http://example.com -r 'document.documentElement.scrollHeight'
/websnap http://example.com --format md
/websnap https://web.archive.org/web/.../https://medium.com/... --format md --no-js
```

If no URL is provided, ask the user what page they want to screenshot.

## Notes

Each call to `websnap` spawns a fresh browser instance. State does not persist between calls (no cookies, localStorage, or session data).

`--format md` extracts the main content (Mozilla Readability) and converts it to GitHub-flavored Markdown, saved as `/tmp/{filename}.md`. Each file begins with a YAML frontmatter block (`title`, `url`, `date` = fetch time, and `author` when a byline is found).

Use `--no-js` when a `--format md` result comes back wrong on a single-page app or an archived (Wayback) snapshot — those are server-rendered with the article, but their client JavaScript can rewrite the DOM (often into a "404") before capture. Disabling page JS keeps the server-rendered content; Readability still runs. Do not use `--no-js` on genuinely client-rendered sites, which need their scripts to build the content at all.
