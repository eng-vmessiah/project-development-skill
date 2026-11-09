#!/usr/bin/env python3
"""Check tracked Markdown relative links without network access."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

LINK_RE = re.compile(r"!?\[[^]]*\]\(([^)\n]+)\)")
HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value).strip().lower()
    value = re.sub(r"[^\w\s-]", "", value)
    return re.sub(r"[-\s]+", "-", value).strip("-")


def check(root: Path, files: Sequence[Path]) -> list[str]:
    """Return one message per broken relative link or missing heading anchor."""
    root = root.resolve()
    failures: list[str] = []
    for relative in sorted(files, key=lambda path: path.as_posix()):
        source = root / relative
        text = source.read_text(encoding="utf-8")
        for raw in LINK_RE.findall(text):
            target = raw.strip().split()[0].strip("<>")
            if (not target or target.startswith(("#", "/", "mailto:", "//")) or
                    re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", target)):
                continue
            target_path, _, fragment = target.partition("#")
            destination = source if not target_path else source.parent / target_path
            try:
                destination = destination.resolve()
                destination.relative_to(root)
            except ValueError:
                failures.append(f"{relative}: escapes repository: {target}")
                continue
            if not destination.exists():
                failures.append(f"{relative}: missing target: {target}")
                continue
            if fragment and destination.is_file() and destination.suffix.lower() == ".md":
                headings = {
                    slug(match.group(1))
                    for match in HEADING_RE.finditer(destination.read_text(encoding="utf-8"))
                }
                if slug(fragment) not in headings:
                    failures.append(f"{relative}: missing anchor: {target}")
    return failures


def tracked_markdown(root: Path) -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.md"], cwd=root
    ).decode()
    return [Path(item) for item in output.split("\0") if item]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check tracked Markdown relative links.")
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="repository root (default: current directory)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        files = tracked_markdown(root)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"markdown link check: cannot list tracked files: {exc}", file=sys.stderr)
        return 2
    failures = check(root, files)
    if failures:
        print("\n".join(sorted(failures)))
        return 1
    print(f"Markdown relative-link check: PASS ({len(files)} tracked files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
