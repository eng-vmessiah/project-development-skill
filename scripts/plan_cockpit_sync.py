#!/usr/bin/env python3
"""plan-cockpit snapshot — read-only aggregate of real PD state (never fabricated).

Sources (all real; missing data yields explicit empties, never invented values):
- `.spec/*/STATE.json`            phase/status/tasks/checkpoints/fleet_state
- `.spec/*/plan.yaml`             FleetPlan v1 (agents/waves/tasks/gates) when present
- `.spec/*/PLAN.md`               checkbox counts (fallback when no plan.yaml)
- `.spec/*/CHECKPOINT-*.md`       timeline events (timestamp from filename)
- `.pd-fleet-runs/*/snapshot.json` fleet runs persisted by FleetRunStore
- `pd list --json`                optional enrichment (tasks/checkpoints counters)

Usage:
  python3 scripts/plan_cockpit_sync.py            # print snapshot JSON
  python3 scripts/plan_cockpit_sync.py --write    # also save .spec/pd-studio/plan-cockpit.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:  # plan.yaml parsing is optional; absence degrades gracefully (labeled in meta)
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

REPO = Path(__file__).resolve().parents[1]
SPEC_DIR = REPO / ".spec"
DEFAULT_RUNS_ROOT = REPO / ".pd-fleet-runs"

CHECKPOINT_RE = re.compile(r"^CHECKPOINT-(\d{8})-(\d{4})\.md$")
CHECKBOX_RE = re.compile(r"^- \[(x| )\]", re.MULTILINE)
HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(REPO), *args],
                             capture_output=True, text=True, timeout=15, check=True)
        return out.stdout.strip()
    except Exception:
        return ""


def _checkpoint_ts(name: str) -> str | None:
    m = CHECKPOINT_RE.match(name)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
        return dt.replace(tzinfo=timezone.utc).isoformat(timespec="minutes")
    except ValueError:
        return None


def _checkpoints(feature_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(feature_dir.glob("CHECKPOINT-*.md")):
        ts = _checkpoint_ts(path.name)
        heading = ""
        try:
            m = HEADING_RE.search(path.read_text(encoding="utf-8", errors="replace"))
            heading = m.group(1).strip()[:110] if m else ""
        except Exception:
            pass
        rows.append({"name": path.name, "ts": ts, "heading": heading})
    return rows


def _plan_yaml(feature_dir: Path) -> dict | None:
    path = feature_dir / "plan.yaml"
    if not path.exists() or yaml is None:
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _plan_md_counts(feature_dir: Path) -> tuple[int, int] | None:
    path = feature_dir / "PLAN.md"
    if not path.exists():
        return None
    try:
        marks = CHECKBOX_RE.findall(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    return (sum(1 for m in marks if m == "x"), len(marks))


def _fleet_state_summary(state: dict) -> dict:
    fs = state.get("fleet_state") or {}
    def _n(key: str) -> int:
        v = fs.get(key)
        return len(v) if isinstance(v, list) else 0
    return {
        "agents": _n("agents"), "waves": _n("waves"), "tasks": _n("tasks"),
        "gates": _n("gates"), "reports": _n("reports"), "attempts": _n("attempts"),
        "blockers": _n("blockers"), "evidence": _n("evidence"),
    }


def features() -> list[dict]:
    rows = []
    for state_path in sorted(SPEC_DIR.glob("*/STATE.json")):
        fdir = state_path.parent
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(state, dict):
            continue

        plan = _plan_yaml(fdir)
        source = "state-md"
        tasks_done = tasks_total = 0
        waves: list[dict] = []
        gates: list[dict] = []
        if plan:
            source = "plan-yaml"
            tasks = [t for t in (plan.get("tasks") or []) if isinstance(t, dict)]
            tasks_total = len(tasks)
            tasks_done = sum(1 for t in tasks if t.get("status") == "done")
            waves = [{"id": w.get("id"), "status": w.get("status"),
                      "tasks": len(w.get("tasks") or [])}
                     for w in (plan.get("waves") or []) if isinstance(w, dict)]
            gates = [{"id": g.get("id"), "kind": g.get("kind"),
                      "status": g.get("status"), "owner": g.get("owner")}
                     for g in (plan.get("gates") or []) if isinstance(g, dict)]
        else:
            counts = _plan_md_counts(fdir)
            if counts is not None:
                source = "plan-md"
                tasks_done, tasks_total = counts

        cps = _checkpoints(fdir)
        last = _git("log", "-1", "--format=%h %cs %s", "--", f".spec/{fdir.name}/")
        rows.append({
            "feature": state.get("feature", fdir.name),
            "phase": state.get("phase"),
            "status": state.get("status"),
            "source": source,
            "tasks_done": tasks_done,
            "tasks_total": tasks_total,
            "checkpoints": len(cps),
            "checkpoints_log": [c for c in cps[-3:]],
            "waves": waves,
            "gates": gates,
            "fleet_state": _fleet_state_summary(state),
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at"),
            "last_commit": last or None,
        })
    rows.sort(key=lambda r: (r.get("updated_at") or "", r["feature"]), reverse=True)
    return rows


def pd_cli_view() -> dict[str, dict]:
    """Optional enrichment from `pd list --json` (same underlying files, computed view)."""
    try:
        out = subprocess.run(["pd", "list", "--json"], capture_output=True,
                             text=True, timeout=20, check=True)
        data = json.loads(out.stdout)
    except Exception:
        return {}
    view: dict[str, dict] = {}
    for item in data.get("features", []):
        if isinstance(item, dict) and item.get("name"):
            view[item["name"]] = {
                "phase_name": item.get("phase_name"),
                "tasks_done": item.get("tasks_done"),
                "tasks_total": item.get("tasks_total"),
                "checkpoints": item.get("checkpoints"),
            }
    return view


def timeline(feature_rows: list[dict]) -> list[dict]:
    events = []
    for f in feature_rows:
        for c in f["checkpoints_log"]:
            if c.get("ts"):
                events.append({"ts": c["ts"], "kind": "checkpoint",
                               "feature": f["feature"], "detail": c["heading"] or c["name"]})
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events[:100]


def fleet_runs(runs_root: Path) -> list[dict]:
    rows = []
    if not runs_root.exists():
        return rows
    for snap in sorted(runs_root.glob("*/snapshot.json")):
        try:
            data = json.loads(snap.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        rows.append({
            "run_id": data.get("run_id", snap.parent.name),
            "status": data.get("status"),
            "updated_at": data.get("updated_at"),
            "owner": data.get("owner"),
            "dir": str(snap.parent.relative_to(REPO)) if str(snap.parent).startswith(str(REPO)) else str(snap.parent),
        })
    rows.sort(key=lambda r: (r.get("updated_at") or "", r["run_id"]), reverse=True)
    return rows


def build(runs_root: Path) -> dict:
    feature_rows = features()
    pd_view = pd_cli_view()
    for f in feature_rows:
        f["pd_view"] = pd_view.get(f["feature"])
    warnings = []
    if yaml is None:
        warnings.append("PyYAML unavailable — plan.yaml parsing disabled (sources labeled state-md/plan-md)")
    if not pd_view:
        warnings.append("`pd list --json` unavailable — pd_view omitted")
    return {
        "schema": "plan-cockpit:v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": str(REPO),
        "runs_root": str(runs_root),
        "features": feature_rows,
        "timeline": timeline(feature_rows),
        "fleet_runs": fleet_runs(runs_root),
        "meta": {
            "feature_count": len(feature_rows),
            "checkpoint_events": sum(f["checkpoints"] for f in feature_rows),
            "fleet_run_count": len(fleet_runs(runs_root)),
            "warnings": warnings,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="save .spec/pd-studio/plan-cockpit.json")
    ap.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT),
                    help="root directory of FleetRunStore runs")
    args = ap.parse_args()

    snapshot = build(Path(args.runs_root).expanduser())
    if args.write:
        out = REPO / ".spec/pd-studio/plan-cockpit.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"wrote {out}")
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
