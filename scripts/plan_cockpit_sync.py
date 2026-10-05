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
    except (subprocess.SubprocessError, OSError):
        return ""


def _checkpoint_ts(name: str) -> str | None:
    m = CHECKPOINT_RE.match(name)
    if not m:
        return None
    try:
        raw = m.group(1) + m.group(2)
        dt = datetime(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]),
                      int(raw[8:10]), int(raw[10:12]), tzinfo=timezone.utc)
        return dt.isoformat(timespec="minutes")
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
        except OSError:
            heading = ""
        rows.append({"name": path.name, "ts": ts, "heading": heading})
    return rows


def _plan_yaml(feature_dir: Path) -> dict | None:
    path = feature_dir / "plan.yaml"
    if not path.exists() or yaml is None:
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, yaml.YAMLError):
        return None


def _plan_md_counts(feature_dir: Path) -> tuple[int, int] | None:
    path = feature_dir / "PLAN.md"
    if not path.exists():
        return None
    try:
        marks = CHECKBOX_RE.findall(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
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
        state: dict | None = None
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            state = loaded if isinstance(loaded, dict) else None
        except (OSError, json.JSONDecodeError):
            state = None
        if state is None:
            continue

        plan = _plan_yaml(fdir)
        source = "state-md"
        tasks_done = tasks_total = 0
        waves: list[dict] = []
        gates: list[dict] = []
        task_rows: list[dict] = []
        if plan:
            source = "plan-yaml"
            tasks = [t for t in (plan.get("tasks") or []) if isinstance(t, dict)]
            tasks_total = len(tasks)
            tasks_done = sum(1 for t in tasks if t.get("status") == "done")
            task_rows = [{"id": t.get("id"), "wave": t.get("wave"),
                          "role": t.get("role"), "status": t.get("status")}
                         for t in tasks]
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
            "tasks": task_rows,
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
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
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
    if runs_root.exists():
        for snap in sorted(runs_root.glob("*/snapshot.json")):
            data: dict | None = None
            try:
                loaded = json.loads(snap.read_text(encoding="utf-8"))
                data = loaded if isinstance(loaded, dict) else None
            except (OSError, json.JSONDecodeError):
                data = None
            if data is None:
                continue
            rows.append({
                "run_id": data.get("run_id", snap.parent.name),
                "status": data.get("status"),
                "updated_at": data.get("updated_at"),
                "owner": data.get("owner"),
                "dir": str(snap.parent.relative_to(REPO)) if str(snap.parent).startswith(str(REPO)) else str(snap.parent),
            })
    pilot_root = REPO / ".spec" / "pilot-runs"
    if pilot_root.exists():
        for summary in sorted(pilot_root.glob("*/summary.json")):
            data = None
            updated = None
            try:
                loaded = json.loads(summary.read_text(encoding="utf-8"))
                data = loaded if isinstance(loaded, dict) else None
                updated = datetime.fromtimestamp(summary.stat().st_mtime,
                                                 tz=timezone.utc).isoformat(timespec="seconds")
            except (OSError, json.JSONDecodeError):
                data = None
            if data is None:
                continue
            statuses = data.get("statuses") or {}
            completed = sum(1 for value in statuses.values() if value == "completed")
            rows.append({
                "run_id": str(data.get("run_id") or summary.parent.name),
                "source": "pilot",
                "status": f"{completed}/{len(statuses)} completed" if statuses else None,
                "updated_at": updated,
                "owner": "hermes-pilot",
                "dir": str(summary.parent.relative_to(REPO)) if str(summary.parent).startswith(str(REPO)) else str(summary.parent),
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


def widget_payloads(snapshot: dict) -> list[dict]:
    """Mission Control tab payloads — reproducible re-apply after app workspace resets."""
    feats = snapshot["features"]

    def _gates_txt(gates: list[dict]) -> str:
        txt = " ".join(f"{g['id']}{'✅' if g['status'] == 'approved' else '·'}" for g in gates)
        return txt or "—"

    def _feat_row(f: dict) -> dict:
        return {"feature": f["feature"], "fase": str(f["phase"]), "status": f["status"],
                "fonte": f["source"], "tasks": f"{f['tasks_done']}/{f['tasks_total']}",
                "cps": str(f["checkpoints"]), "gates": _gates_txt(f["gates"])}

    pc = next((f for f in feats if f["feature"] == "plan-cockpit-v1"), None)
    pc_tasks = pc["tasks"] if pc else []
    pc_done = sum(1 for t in pc_tasks if t.get("status") == "done")
    ts = snapshot.get("generated_at", "")[:16].replace("T", " ")
    meta = snapshot["meta"]
    overview = (
        "# Mission Control — PD (plan-cockpit v1)\n\n"
        "Visão única do PD **derivada só de fontes reais** (nunca fabricar telemetria).\n\n"
        f"- **Features:** {len(feats)} · **plan-cockpit-v1:** {pc_done}/{len(pc_tasks)} tasks · "
        f"**Checkpoints:** {meta['checkpoint_events']} · **Runs:** {meta['fleet_run_count']}\n"
        f"- Snapshot: **{ts}**\n"
        "- Fonte: `scripts/plan_cockpit_sync.py` → `.spec/pd-studio/plan-cockpit.json`"
    )
    timeline_rows = [{"quando": e["ts"][:16].replace("T", " "),
                      "feature": e["feature"], "detalhe": "Checkpoint"}
                     for e in snapshot["timeline"]]
    pilot_runs = [row for row in snapshot.get("fleet_runs", []) if row.get("source") == "pilot"]
    run_lines = "\n".join(
        f"- `{row['run_id']}` — {row.get('status') or '?'} · `{row.get('dir')}`"
        for row in pilot_runs[:3]
    )
    fleet_md = (
        "## Fleet runs\n\n"
        f"**{meta['fleet_run_count']} runs** (`.pd-fleet-runs/` + `.spec/pilot-runs/`). "
        "Wave 4: T-401→T-404; G2 = autorização de dispatch live.\n\n"
        + (f"**Piloto hermes:**\n{run_lines}\n" if run_lines else
           "Nenhum run do piloto registrado ainda — `--live --authorized` auto-registra.\n")
    )
    return [
        {"tab": "mc", "kind": "builtin:markdown", "id": "mc-overview", "title": "Overview",
         "grid": {"x": 0, "y": 0, "w": 12, "h": 3},
         "bindings": {"content": {"source": "static", "value": overview}}},
        {"tab": "mc", "kind": "builtin:table", "id": "mc-features", "title": "Features (estado real)",
         "grid": {"x": 0, "y": 3, "w": 12, "h": 5},
         "bindings": {"rows": {"source": "static", "value": [_feat_row(f) for f in feats]}},
         "props": {"columns": ["feature", "fase", "status", "fonte", "tasks", "cps", "gates"]}},
        {"tab": "mc", "kind": "builtin:table", "id": "mc-tasks", "title": "Tasks — plan-cockpit-v1",
         "grid": {"x": 0, "y": 8, "w": 6, "h": 6},
         "bindings": {"rows": {"source": "static", "value": [
             {"id": t["id"], "wave": str(t["wave"]), "role": t["role"],
              "status": "✅ done" if t.get("status") == "done" else "⏳ pending"}
             for t in pc_tasks]}},
         "props": {"columns": ["id", "wave", "role", "status"]}},
        {"tab": "mc", "kind": "builtin:table", "id": "mc-timeline", "title": "Timeline — checkpoints (reais)",
         "grid": {"x": 6, "y": 8, "w": 6, "h": 6},
         "bindings": {"rows": {"source": "static", "value": timeline_rows}},
         "props": {"columns": ["quando", "feature", "detalhe"]}},
        {"tab": "mc", "kind": "builtin:markdown", "id": "mc-fleet", "title": "Fleet runs",
         "grid": {"x": 0, "y": 14, "w": 12, "h": 3},
         "bindings": {"content": {"source": "static", "value": fleet_md}}},
        {"tab": "mc", "kind": "builtin:action-form", "id": "mc-selector",
         "title": "Escolher missão", "grid": {"x": 0, "y": 17, "w": 6, "h": 3},
         "props": {
             "template": "Mission Control — seletor: publique o plano da missão {{missao}} na aba mc. "
                         "Rode: cd ~/project/project-development-skill && /usr/bin/python3 "
                         "scripts/plan_cockpit_sync.py --publish --mission '{{missao}}' e confirme.",
             "fields": [{"name": "missao", "label": "Missão", "type": "select",
                         "options": [f["feature"] for f in feats]}],
             "buttonLabel": "Mostrar plano",
         }},
        {"tab": "mc", "kind": "builtin:markdown", "id": "mc-mission-info",
         "title": "Plano da missão (selecionada)", "grid": {"x": 6, "y": 17, "w": 6, "h": 3},
         "bindings": {"content": {"source": "file", "path": "mc/mission.md"}}},
        {"tab": "mc", "kind": "builtin:table", "id": "mc-mission-tasks",
         "title": "Tasks da missão (selecionada)", "grid": {"x": 0, "y": 20, "w": 12, "h": 6},
         "bindings": {"rows": {"source": "file", "path": "mc/mission.json", "pointer": "/tasks"}},
         "props": {"columns": ["id", "wave", "role", "status"]}},
    ]


def publish_files(snapshot: dict) -> dict[str, str]:
    """Live-binding files for the dashboard data dir (file bindings, no cache on read)."""
    payloads = {p["id"]: p for p in widget_payloads(snapshot)}
    tables = {
        "features": payloads["mc-features"]["bindings"]["rows"]["value"],
        "tasks": payloads["mc-tasks"]["bindings"]["rows"]["value"],
        "timeline": payloads["mc-timeline"]["bindings"]["rows"]["value"],
    }
    return {
        "overview.md": payloads["mc-overview"]["bindings"]["content"]["value"] + "\n",
        "fleet.md": payloads["mc-fleet"]["bindings"]["content"]["value"] + "\n",
        "tables.json": json.dumps(tables, indent=2, ensure_ascii=False) + "\n",
    }


def mission_files(snapshot: dict, mission: str) -> dict[str, str]:
    """Selected-mission detail files for the mc tab (live file bindings)."""
    feat = next((f for f in snapshot["features"] if f["feature"] == mission), None)
    if feat is None:
        raise SystemExit(f"mission not found in snapshot: {mission}")
    gates_txt = " · ".join(
        f"{g['id']} ({g.get('kind')}) {g['status']}" for g in feat["gates"]) or "—"
    waves_txt = " · ".join(
        f"{w['id']}: {w['status']} ({w['tasks']})" for w in feat["waves"]) or "—"
    info = (
        f"## Plano da missão — `{feat['feature']}`\n\n"
        f"- **Fase:** {feat['phase']} · **Status:** {feat['status']} · **Fonte do plano:** {feat['source']}\n"
        f"- **Tasks:** {feat['tasks_done']}/{feat['tasks_total']} · **Checkpoints:** {feat['checkpoints']}\n"
        f"- **Gates:** {gates_txt}\n"
        f"- **Waves:** {waves_txt}\n"
    )
    if feat["source"] != "plan-yaml":
        info += "\n*Missão legada (sem `plan.yaml`) — o detalhe reflete só o que está registrado.*\n"
    detail = {
        "mission": feat["feature"],
        "phase": feat["phase"],
        "status": feat["status"],
        "source": feat["source"],
        "tasks_done": feat["tasks_done"],
        "tasks_total": feat["tasks_total"],
        "gates": feat["gates"],
        "waves": feat["waves"],
        "tasks": [
            {"id": t["id"], "wave": str(t["wave"]), "role": t["role"],
             "status": "✅ done" if t.get("status") == "done" else "⏳ pending"}
            for t in feat["tasks"]
        ],
    }
    return {
        "mission.md": info + "\n",
        "mission.json": json.dumps(detail, indent=2, ensure_ascii=False) + "\n",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="save .spec/pd-studio/plan-cockpit.json")
    ap.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT),
                    help="root directory of FleetRunStore runs")
    ap.add_argument("--widgets", action="store_true",
                    help="also write .spec/pd-studio/mc-widgets.json (Mission Control re-apply payloads)")
    ap.add_argument("--publish", action="store_true",
                    help="write live-binding files to ~/.hermes/boardstate-state/dashboard/data/mc/")
    ap.add_argument("--mission", default=None,
                    help="mission whose detail is published (default: keep current selection, else first plan-yaml mission)")
    args = ap.parse_args()

    snapshot = build(Path(args.runs_root).expanduser())
    if args.write:
        out = REPO / ".spec/pd-studio/plan-cockpit.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"wrote {out}")
    if args.widgets:
        wout = REPO / ".spec/pd-studio/mc-widgets.json"
        wout.write_text(json.dumps(widget_payloads(snapshot), indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        print(f"wrote {wout}")
    if args.publish:
        pdir = Path.home() / ".hermes/boardstate-state/dashboard/data/mc"
        pdir.mkdir(parents=True, exist_ok=True)
        for name, content in publish_files(snapshot).items():
            (pdir / name).write_text(content, encoding="utf-8")
            print(f"wrote {pdir / name}")
        mission = args.mission
        if mission is None:
            cur = pdir / "mission.json"
            if cur.exists():
                try:
                    loaded = json.loads(cur.read_text(encoding="utf-8"))
                    mission = loaded.get("mission") if isinstance(loaded, dict) else None
                except (OSError, json.JSONDecodeError):
                    mission = None
        if mission is None:
            plan_feats = [f["feature"] for f in snapshot["features"] if f["source"] == "plan-yaml"]
            mission = plan_feats[0] if plan_feats else (
                snapshot["features"][0]["feature"] if snapshot["features"] else None)
        if mission:
            for name, content in mission_files(snapshot, mission).items():
                (pdir / name).write_text(content, encoding="utf-8")
                print(f"wrote {pdir / name}")
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
