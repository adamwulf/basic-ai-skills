#!/usr/bin/env python3
"""find_bangs.py — Locate Swift force-unwrap sites.

Classifies up to four kinds:
  unwrap : postfix `!` after identifier/)/]/?  (not `!=` `!==` `!!`)
  try!   : the `try!` keyword
  as!    : the `as!` keyword
  iuo    : implicitly-unwrapped optional type declarations (`var x: Foo!`)

By default writes a markdown report to the current directory and prints a
one-line summary. Pass --tsv to also emit a machine-readable detail file,
or --stdout to instead dump `file:line:kind:snippet` lines for piping.

Test files are always skipped (path contains Tests/ or Test/, or filename
ends with Tests.swift).
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
TRIPLE_STRING_DELIM = '"""'
LINE_COMMENT_RE = re.compile(r'//.*$')
BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)

TRY_RE = re.compile(r'\btry!')
AS_RE = re.compile(r'\bas!')
POSTFIX_RE = re.compile(r'(?<=[A-Za-z0-9_\)\]\?])!(?!=)(?!!)')

# Implicitly-unwrapped optional TYPE declaration (e.g. `var x: Foo!`).
IUO_TYPE_RE = re.compile(
    r'(?:[:\s]|->|\b(?:var|let)\b\s+\w+\s*:\s*)'
    r'\[?[A-Z]\w*(?:\.[A-Z]\w*)*(?:<[^>]*>)?\??\]?'
    r'!(?=\s*(?:$|=|\{|\(|\)|,|\n))'
)

KIND_ORDER = ['unwrap', 'try!', 'as!', 'iuo']


def strip_comments_and_strings(text: str) -> str:
    """Replace comments and string literals with spaces of equal length."""
    def replace_block(m):
        return ''.join('\n' if c == '\n' else ' ' for c in m.group(0))
    text = BLOCK_COMMENT_RE.sub(replace_block, text)

    # Triple-quoted multi-line strings.
    result = []
    i = 0
    n = len(text)
    in_triple = False
    while i < n:
        if text[i:i + 3] == TRIPLE_STRING_DELIM:
            in_triple = not in_triple
            result.append('   ')
            i += 3
            continue
        if in_triple:
            result.append('\n' if text[i] == '\n' else ' ')
            i += 1
            continue
        result.append(text[i])
        i += 1
    text = ''.join(result)

    out_lines = []
    for line in text.split('\n'):
        line = STRING_RE.sub(lambda m: ' ' * len(m.group(0)), line)
        line = LINE_COMMENT_RE.sub(lambda m: ' ' * len(m.group(0)), line)
        out_lines.append(line)
    return '\n'.join(out_lines)


def classify(file_path: Path, exclude_iuo: bool):
    """Yield (line_no, kind, snippet) tuples for hits in this file.

    IUO type declarations are reported as kind 'iuo' unless exclude_iuo is set,
    in which case they are dropped entirely.
    """
    try:
        raw = file_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"skip {file_path}: {e}", file=sys.stderr)
        return
    clean = strip_comments_and_strings(raw)
    raw_lines = raw.split('\n')
    clean_lines = clean.split('\n')

    for idx, (raw_line, clean_line) in enumerate(zip(raw_lines, clean_lines), start=1):
        iuo_spans = [(m.start(), m.end()) for m in IUO_TYPE_RE.finditer(clean_line)]

        def in_iuo(pos, spans=iuo_spans):
            return any(s <= pos < e for s, e in spans)

        for _ in TRY_RE.finditer(clean_line):
            yield (idx, 'try!', raw_line.rstrip())
        for _ in AS_RE.finditer(clean_line):
            yield (idx, 'as!', raw_line.rstrip())
        for m in POSTFIX_RE.finditer(clean_line):
            pos = m.start()
            # The `!` of try!/as! is already counted above; skip it here.
            if re.search(r'\b(try|as)$', clean_line[:pos]):
                continue
            if in_iuo(pos):
                if exclude_iuo:
                    continue
                yield (idx, 'iuo', raw_line.rstrip())
            else:
                yield (idx, 'unwrap', raw_line.rstrip())


TEST_PATH_MARKERS = ('Tests/', 'Test/')


def is_test_file(path: Path) -> bool:
    s = str(path)
    if any(marker in s for marker in TEST_PATH_MARKERS):
        return True
    if path.name.endswith('Tests.swift'):
        return True
    return False


def collect_swift_files(roots):
    seen = set()
    files = []
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            print(f"warn: {root} does not exist, skipping", file=sys.stderr)
            continue
        if root_path.is_file() and root_path.suffix == '.swift':
            candidates = [root_path]
        else:
            candidates = sorted(root_path.rglob('*.swift'))
        for fp in candidates:
            if fp in seen:
                continue
            if is_test_file(fp):
                continue
            seen.add(fp)
            files.append(fp)
    return files


def scan(files, exclude_iuo: bool):
    bucket = defaultdict(list)
    counts = defaultdict(lambda: defaultdict(int))
    for fp in files:
        for line_no, kind, snip in classify(fp, exclude_iuo):
            key = str(fp)
            bucket[key].append((line_no, kind, snip))
            counts[key][kind] += 1
    return bucket, counts


def totals_from_counts(counts):
    return {kind: sum(c.get(kind, 0) for c in counts.values()) for kind in KIND_ORDER}


def top_level_area(file_str: str) -> str:
    parts = Path(file_str).parts
    return parts[0] if parts else file_str


def write_markdown_report(out_path: Path, bucket, counts, totals, args, kinds):
    grand = sum(totals[k] for k in kinds)

    area_counts = defaultdict(lambda: defaultdict(int))
    for fp_str, c in counts.items():
        area = top_level_area(fp_str)
        for kind in kinds:
            area_counts[area][kind] += c.get(kind, 0)
        area_counts[area]['files'] += 1

    file_totals = []
    for fp_str, c in counts.items():
        total = sum(c.get(k, 0) for k in kinds)
        if total == 0:
            continue
        file_totals.append((total, fp_str, c))
    file_totals.sort(key=lambda x: (-x[0], x[1]))

    try_hits = []
    for fp_str, items in sorted(bucket.items()):
        for line_no, kind, snip in items:
            if kind == 'try!':
                try_hits.append((fp_str, line_no, snip))

    lines = []
    lines.append('# Force-unwrap inventory')
    lines.append('')
    lines.append(f'**Roots scanned:** {", ".join(args.paths)}')
    lines.append(f'**Exclude IUO type decls:** {args.exclude_iuo}')
    lines.append('')
    lines.append('## Totals')
    lines.append('')
    lines.append(f'- **{grand}** sites across **{len(file_totals)}** files')
    for kind in kinds:
        label = {
            'unwrap': 'postfix `!` (unwrap)',
            'try!': '`try!`',
            'as!': '`as!`',
            'iuo': 'IUO type declarations',
        }[kind]
        lines.append(f'- {totals[kind]} {label}')
    lines.append('')

    lines.append('## By area')
    lines.append('')
    header = ['Area', 'Files'] + kinds + ['Total']
    sep = ['---', '---:'] + ['---:'] * len(kinds) + ['---:']
    lines.append('| ' + ' | '.join(header) + ' |')
    lines.append('|' + '|'.join(sep) + '|')
    for area in sorted(area_counts.keys()):
        a = area_counts[area]
        total = sum(a[k] for k in kinds)
        row = [area, str(a['files'])] + [str(a[k]) for k in kinds] + [str(total)]
        lines.append('| ' + ' | '.join(row) + ' |')
    lines.append('')

    lines.append('## Top 25 files')
    lines.append('')
    header = ['File'] + kinds + ['Total']
    sep = ['---'] + ['---:'] * len(kinds) + ['---:']
    lines.append('| ' + ' | '.join(header) + ' |')
    lines.append('|' + '|'.join(sep) + '|')
    for total, fp_str, c in file_totals[:25]:
        row = [fp_str] + [str(c.get(k, 0)) for k in kinds] + [str(total)]
        lines.append('| ' + ' | '.join(row) + ' |')
    lines.append('')

    lines.append('## All `try!` sites')
    lines.append('')
    if not try_hits:
        lines.append('_None._')
    else:
        for fp_str, line_no, snip in try_hits:
            snippet = snip.strip().replace('|', '\\|')
            if len(snippet) > 160:
                snippet = snippet[:157] + '...'
            lines.append(f'- `{fp_str}:{line_no}` — `{snippet}`')
    lines.append('')

    out_path.write_text('\n'.join(lines), encoding='utf-8')


def write_tsv_details(out_path: Path, bucket):
    with out_path.open('w', encoding='utf-8') as f:
        f.write('kind\tfile\tline\tsnippet\n')
        for fp_str, items in sorted(bucket.items()):
            for line_no, kind, snip in items:
                snippet = snip.replace('\t', '    ')[:200]
                f.write(f'{kind}\t{fp_str}\t{line_no}\t{snippet}\n')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Find Swift force-unwrap sites (!, try!, as!, IUO type decls). '
                    'Test files are always skipped.'
    )
    parser.add_argument(
        'paths', nargs='*', default=['.'],
        help='Directories or .swift files to scan (default: current directory).'
    )
    parser.add_argument(
        '--exclude-iuo', action='store_true',
        help='Drop implicitly-unwrapped optional type declarations from the report.'
    )
    parser.add_argument(
        '--tsv', action='store_true',
        help='Also write a TSV detail file (find-all-bangs-details.tsv).'
    )
    parser.add_argument(
        '--stdout', action='store_true',
        help='Skip file output, dump file:line:kind:snippet to stdout.'
    )
    parser.add_argument(
        '--report', default='find-all-bangs-report.md',
        help='Markdown report path (default: find-all-bangs-report.md).'
    )
    parser.add_argument(
        '--details', default='find-all-bangs-details.tsv',
        help='TSV detail path when --tsv is set (default: find-all-bangs-details.tsv).'
    )
    args = parser.parse_args(argv)

    files = collect_swift_files(args.paths)
    bucket, counts = scan(files, args.exclude_iuo)
    totals = totals_from_counts(counts)
    kinds = [k for k in KIND_ORDER if not (args.exclude_iuo and k == 'iuo')]
    grand = sum(totals[k] for k in kinds)
    files_with_hits = sum(
        1 for c in counts.values() if sum(c.get(k, 0) for k in kinds) > 0
    )

    if args.stdout:
        for fp_str, items in sorted(bucket.items()):
            for line_no, kind, snip in items:
                snippet = snip.replace('\t', '    ')
                print(f'{fp_str}:{line_no}:{kind}:{snippet}')
    else:
        write_markdown_report(Path(args.report), bucket, counts, totals, args, kinds)
        if args.tsv:
            write_tsv_details(Path(args.details), bucket)

    parts = [f'{totals[k]} {k}' for k in kinds]
    print(f'{grand} sites in {files_with_hits} files ({", ".join(parts)})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
