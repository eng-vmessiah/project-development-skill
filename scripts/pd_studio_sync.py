#!/usr/bin/env python3
"""pd-studio snapshot — read-only sync of real PD state into board widget payloads.

Sources (all real, nothing fabricated):
- PD repo git log (recent commits)
- Hermes B15a.2 worktree git log (configurable range)
- `.spec/*/STATE.json` feature states
- `STATE.md` gate table (pd-fleet-hermes-gateway-fleet-v1)
- Obsidian `b15a2-caminho.md` slice lines (S0–S6)

Usage:
  python3 scripts/pd_studio_sync.py            # print snapshot JSON
  python3 scripts/pd_studio_sync.py --write    # also save .spec/pd-studio/snapshot.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_HERMES_WT = Path.home() / "project/hermes-agent-b15a2-integration"
CAMINHO = Path.home() / "isis-obsidian/Projects/project-development-skill/b15a2-caminho.md"

GATES_RE = re.compile(r"^\|\s*(G\d)\s*\|\s*`?([^`|]+)`?\s*\|\s*(.+?)\s*\|\s*$")
SLICE_RE = re.compile(r"^- \*\*S(\d) (✅|⏳|🔄|❌)")


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args],
                             capture_output=True, text=True, timeout=15, check=True)
        return out.stdout.strip()
    except Exception:
        return ""


def pd_features() -> list[dict]:
    feats = []
    for state in sorted((REPO / ".spec").glob("*/STATE.json")):
        try:
            data = json.loads(state.read_text())
            feats.append({
                "feature": data.get("feature", state.parent.name),
                "phase": data.get("phase"),
                "status": data.get("status"),
                "tasks": len(data.get("tasks", [])),
            })
        except Exception:
            continue
    return feats


def gates() -> list[dict]:
    md = (REPO / ".spec/pd-fleet-hermes-gateway-fleet-v1/STATE.md").read_text()
    rows = []
    for line in md.splitlines():
        m = GATES_RE.match(line)
        if m:
            rows.append({"gate": m.group(1), "status": m.group(2).strip(),
                         "note": m.group(3).strip()[:120]})
    return rows


def slices() -> list[dict]:
    rows = []
    if CAMINHO.exists():
        for line in CAMINHO.read_text().splitlines():
            m = SLICE_RE.match(line)
            if m:
                title = line.split("**", 2)[-1].lstrip(": ").strip()
                rows.append({"slice": f"S{m.group(1)}", "state": m.group(2), "title": title[:110]})
    return rows


def commits(repo: Path, n: int = 8, rng: str | None = None) -> list[dict]:
    args = ["log", "--oneline", rng] if rng else ["log", "--oneline", "-n", str(n)]
    rows = []
    for line in _git(repo, *args).splitlines():
        h, _, msg = line.partition(" ")
        rows.append({"commit": h, "summary": msg.strip()})
    return rows


def build_snapshot(hermes_wt: Path, hermes_range: str) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {"repo": str(REPO), "hermes_worktree": str(hermes_wt)},
        "features": pd_features(),
        "gates": gates(),
        "slices": slices(),
        "commits": {"pd": commits(REPO), "hermes_b15a2": commits(hermes_wt, rng=hermes_range)},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="save .spec/pd-studio/snapshot.json")
    ap.add_argument("--hermes-worktree", default=str(DEFAULT_HERMES_WT))
    ap.add_argument("--hermes-range", default="63301027cc..HEAD")
    args = ap.parse_args()

    snapshot = build_snapshot(Path(args.hermes_worktree), args.hermes_range)
    if args.write:
        out = REPO / ".spec/pd-studio/snapshot.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {out}")
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
