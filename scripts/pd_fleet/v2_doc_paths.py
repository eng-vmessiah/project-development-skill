#!/usr/bin/env python3
"""Offline, read-only checker for the V2 documentation path contract.

The command deliberately accepts the repository root explicitly.  It performs no
network or subprocess operations and emits stable JSON suitable for CI evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable

SCHEMA_VERSION = "pd-fleet-doc-paths:v1"
V2_DOCS = ".spec/pd-fleet-orchestration-v2"
V1_PREFIX = ".spec/pd-fleet-orchestration/"
FIELD_RE = re.compile(r"\*\*(Create|Exact files|Allowed paths):?\*\*\s*:?\s*(.*)")
TASK_RE = re.compile(r"^\s*#{1,6}\s+(T2-\d+)\b", re.IGNORECASE)
CODE_RE = re.compile(r"`([^`]+)`")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def _violation(code: str, path: str, task: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "task": task, "detail": detail}


def _slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value).strip().lower()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    return re.sub(r"[-\s]+", "-", value).strip("-")


def _docs(root: Path) -> Iterable[Path]:
    base = root / V2_DOCS
    if not base.is_dir():
        return ()
    return sorted((p for p in base.rglob("*.md") if p.is_file()), key=lambda p: p.relative_to(root).as_posix())


def _inline_create(rest: str, start: int, end: int, code_spans: list[tuple[int, int]]) -> bool:
    """Return whether the Create marker belongs to this individual path."""
    previous_end = 0
    for span_start, span_end in code_spans:
        if span_start == start:
            break
        previous_end = span_end
    next_start = len(rest)
    for span_start, _ in code_spans:
        if span_start > start:
            next_start = span_start
            break
    clause_start = max(rest.rfind(",", 0, start), rest.rfind(";", 0, start), previous_end) + 1
    clause_end_candidates = [p for p in (rest.find(",", end), rest.find(";", end)) if p >= 0]
    clause_end = min(clause_end_candidates) if clause_end_candidates else next_start
    clause = rest[clause_start:clause_end]
    return bool(re.search(r"\bCreate\b", clause, re.IGNORECASE))


def _relative_path(raw: str) -> str:
    value = raw.strip().replace("\\", "/")
    return value[2:] if value.startswith("./") else value


def check_repo(repo_root: str | Path) -> dict[str, object]:
    root = Path(repo_root).expanduser()
    violations: list[dict[str, str]] = []
    if root.is_symlink():
        violations.append(_violation("SYMLINK_ROOT", ".", "", "repo_root must not be a symlink"))
        return _result(root, violations)
    if not root.is_dir() or not (root / ".git").exists():
        violations.append(_violation("INVALID_ROOT", ".", "", "repo_root must be an existing repository root"))
        return _result(root, violations)
    base = root / V2_DOCS
    if base.is_symlink():
        violations.append(_violation("SYMLINK_DOCS", V2_DOCS, "", "V2 documentation directory must not be a symlink"))
        return _result(root, violations)
    docs = list(_docs(root))
    if not docs:
        violations.append(_violation("MISSING_DOCS", V2_DOCS, "", "V2 documentation directory has no markdown files"))
        return _result(root, violations)

    owners: dict[str, set[str]] = {}
    declarations: list[tuple[str, str, str, str]] = []
    inline_creates: set[tuple[str, str]] = set()
    for doc in docs:
        rel_doc = doc.relative_to(root).as_posix()
        if doc.is_symlink():
            violations.append(_violation("SYMLINK_DOC", rel_doc, "", "scanned documentation file must not be a symlink"))
            continue
        try:
            doc.resolve().relative_to(root.resolve())
        except ValueError:
            violations.append(_violation("PATH_ESCAPE", rel_doc, "", "scanned documentation file escapes repository root"))
            continue
        text = doc.read_text(encoding="utf-8")
        task = ""
        for line in text.splitlines():
            match_task = TASK_RE.match(line)
            if match_task:
                task = match_task.group(1).upper()
            field = FIELD_RE.search(line)
            if field and task:
                kind, rest = field.groups()
                code_matches = list(CODE_RE.finditer(rest))
                code_spans = [match.span(1) for match in code_matches]
                for code_match in code_matches:
                    raw = code_match.group(1)
                    path = _relative_path(raw)
                    if not path or " " in path or path.startswith("#"):
                        continue
                    declarations.append((kind, path, task, rel_doc))
                    if kind == "Create":
                        owners.setdefault(path, set()).add(task)
                    elif _inline_create(rest, code_match.start(1), code_match.end(1), code_spans):
                        inline_creates.add((path, task))

        headings = {_slug(m.group(1)) for m in HEADING_RE.finditer(text) if _slug(m.group(1))}
        for link in LINK_RE.findall(text):
            target = link.strip().split()[0].strip("<>")
            if not target or target.startswith("mailto:"):
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
                violations.append(_violation("EXTERNAL_LINK", rel_doc, task, "external links are not checked offline"))
                continue
            target_path, _, fragment = target.partition("#")
            if not target_path:
                destination = doc
            else:
                if target_path.startswith("/"):
                    violations.append(_violation("PATH_ESCAPE", rel_doc, task, "absolute link escapes repository root"))
                    continue
                if ".." in PurePosixPath(target_path).parts:
                    violations.append(_violation("TRAVERSAL", rel_doc, task, "parent traversal is not allowed in links"))
                    continue
                candidate = (doc.parent / target_path).resolve()
                try:
                    candidate.relative_to(root.resolve())
                except ValueError:
                    violations.append(_violation("TRAVERSAL", rel_doc, task, "link escapes repository root"))
                    continue
                destination = candidate
            if not destination.is_file():
                violations.append(_violation("BROKEN_LINK", rel_doc, task, f"link destination does not exist: {target_path or rel_doc}"))
            if fragment and destination == doc and _slug(fragment) not in headings:
                violations.append(_violation("BROKEN_ANCHOR", rel_doc, task, f"anchor does not exist: #{fragment}"))
            elif fragment and destination.is_file():
                dest_text = destination.read_text(encoding="utf-8")
                dest_headings = {_slug(m.group(1)) for m in HEADING_RE.finditer(dest_text) if _slug(m.group(1))}
                if _slug(fragment) not in dest_headings:
                    violations.append(_violation("BROKEN_ANCHOR", rel_doc, task, f"anchor does not exist: #{fragment}"))

    for kind, path, task, doc in declarations:
        if path.startswith(V1_PREFIX) or path == ".spec/pd-fleet-orchestration":
            if path.endswith("/*"):
                continue
            violations.append(_violation("V1_FORBIDDEN", doc, task, f"V1 path is forbidden: {path}"))
            continue
        if path.startswith("/") or ".." in PurePosixPath(path).parts:
            violations.append(_violation("PATH_ESCAPE", doc, task, f"path is outside repository: {path}"))
            continue
        candidate = (root / path).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            violations.append(_violation("PATH_ESCAPE", doc, task, f"path escapes repository: {path}"))
            continue
        if kind in {"Exact files", "Allowed paths"} and not candidate.exists():
            if not ((path in owners and task in owners[path]) or (path, task) in inline_creates):
                violations.append(_violation("MISSING_PATH", doc, task, f"declared path does not exist or is not Create-owned: {path}"))
            if any(k == "Create" and p == path and t != task for k, p, t, _ in declarations):
                violations.append(_violation("CREATE_OWNERSHIP", doc, task, f"Create belongs to another task: {path}"))
        if len(owners.get(path, set())) > 1:
            violations.append(_violation("CREATE_OWNERSHIP", doc, task, f"path has multiple task owners: {path}"))
    return _result(root, violations)


def _result(root: Path, violations: list[dict[str, str]]) -> dict[str, object]:
    violations.sort(key=lambda item: (item["code"], item["path"], item["task"], item["detail"]))
    return {"schema_version": SCHEMA_VERSION, "repo_root": ".", "violations": violations, "summary": {"documents": 0 if not root.is_dir() else len(list(_docs(root))), "violation_count": len(violations), "status": "valid" if not violations else "invalid"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root")
    args = parser.parse_args(argv)
    result = check_repo(args.repo_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    violations = result["violations"]
    assert isinstance(violations, list)
    return 2 if any(v["code"] in {"INVALID_ROOT", "SYMLINK_ROOT"} for v in violations) else (1 if violations else 0)


if __name__ == "__main__":
    raise SystemExit(main())
