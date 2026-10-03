#!/usr/bin/env python3
"""
strip-line-prefixes.py — Recover Hermes source files corrupted by read_file line prefixes.

When read_file output (containing display-only "N|" prefixes) is mistakenly
written back into a source file via write_file, the file accumulates leading
digit-pipe tokens on every line.  This script strips all such prefixes
iteratively until stable, then normalizes trailing whitespace.

Usage:
    python3 scripts/strip-line-prefixes.py path/to/file.ts
    python3 scripts/strip-line-prefixes.py path/to/project/  # all .ts, .tsx, .js, .py files

Safe to run repeatedly — idempotent after the first pass.
"""
import re
import sys
from pathlib import Path

LINE_PREFIX = re.compile(r'^[ \t]*\d+\|[ \t]?', re.MULTILINE)


def strip_prefixes(text: str) -> str:
    """Remove all leading N| line-number prefixes from text."""
    prev = None
    while prev != text:
        prev = text
        text = LINE_PREFIX.sub('', text)
    return text


def fix_file(path: Path) -> bool:
    """Fix one file. Returns True if modified."""
    raw = path.read_text(encoding='utf-8')
    fixed = strip_prefixes(raw)
    # Normalize: exactly one trailing newline
    fixed = fixed.rstrip('\n') + '\n'
    if fixed == raw:
        return False
    path.write_text(fixed, encoding='utf-8')
    return True


def main():
    root = Path(sys.argv[1])

    if root.is_file():
        files = [root]
    elif root.is_dir():
        files = list(root.rglob('*.ts')) + list(root.rglob('*.tsx')) \
                + list(root.rglob('*.js')) + list(root.rglob('.py')) \
                + list(root.rglob('.jsx'))
    else:
        print(f'Not found: {root}')
        sys.exit(1)

    count = 0
    for p in files:
        if fix_file(p):
            print(f'  FIXED {p}')
            count += 1

    if count:
        print(f'\n{count} file(s) repaired.')
    else:
        print('No files needed repair.')


if __name__ == '__main__':
    main()
