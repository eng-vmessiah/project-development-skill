#!/usr/bin/env python3
"""Control-plane swarm surface tests (T-103) — real sources, explicit empties, determinism.

Covers the swarm() derivation added in T-102: monitor (host), kanban (read-only),
pilot runs, and the never-fabricate rule (empty source => explicit "sem fonte").
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import plan_cockpit_sync as pc

ROW_KEYS = {"agente", "fonte", "fidelity", "status", "heartbeat", "acao", "arquivos", "nota"}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def fake_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(pc, "REPO", tmp_path)
    monkeypatch.setattr(pc, "SPEC_DIR", tmp_path / ".spec")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path


def test_control_plane_empty_sources_are_explicit(fake_world: Path) -> None:
    sw = pc.swarm(fake_world / ".pd-fleet-runs")
    assert sw["schema"] == "activity-swarm:v1"
    rows = {r["agente"]: r for r in sw["rows"]}
    assert rows["host (Windows + WSL)"]["status"] == "sem fonte"
    assert rows["kanban"]["status"] == "sem fonte"
    assert rows["sessões Hermes"]["status"] == "sem fonte"
    for r in sw["rows"]:
        assert set(r) == ROW_KEYS
        if r["status"] == "sem fonte":
            assert r["heartbeat"] == "—" and r["acao"] == "—"
    assert any("kanban" in n for n in sw["notes"])


def test_control_plane_host_fresh_and_stale(fake_world: Path) -> None:
    home = Path.home()
    now = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)
    fresh = (now - timedelta(minutes=5)).isoformat()
    stale = (now - timedelta(hours=3)).isoformat()
    _write(home / ".hermes/monitor/machine.jsonl",
           json.dumps({"ts": fresh, "gpu_util": 7}) + "\n"
           + "GARBAGE\n"
           + json.dumps({"ts": fresh, "gpu_util": 9, "wsl_ram_pct": 20,
                         "win_cpu": 4, "win_ram_pct": 62}) + "\n")
    row = pc._host_agent(now)
    assert row["status"] == "ok"
    assert "gpu 9%" in row["acao"]  # última linha válida, não a primeira
    _write(home / ".hermes/monitor/machine.jsonl", json.dumps({"ts": stale}) + "\n")
    row = pc._host_agent(now)
    assert row["status"] == "stale"


def test_control_plane_kanban_rows_and_empty(fake_world: Path) -> None:
    db = Path.home() / ".hermes/kanban.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(
        "create table tasks (id text primary key, title text, assignee text, status text);"
        "create table task_runs (id integer primary key, task_id text, profile text,"
        " status text, last_heartbeat_at text, outcome text, summary text);"
    )
    con.execute("insert into tasks values ('t1','Fazer coisa','worker-a','in_progress')")
    con.execute("insert into task_runs values (1,'t1','worker-a','running','2026-10-09T19:00:00Z',null,null)")
    con.commit()
    con.close()
    rows, note = pc._kanban_agents()
    assert note is None and len(rows) == 1
    assert rows[0]["agente"] == "kanban:worker-a"
    assert rows[0]["status"] == "running"
    assert "t1" in rows[0]["acao"]
    con = sqlite3.connect(db)
    con.execute("delete from task_runs")
    con.execute("delete from tasks")
    con.commit()
    con.close()
    rows, note = pc._kanban_agents()
    assert rows == [] and "sem workers" in (note or "")


def test_control_plane_pilot_rows_counts(fake_world: Path) -> None:
    pilot = fake_world / ".spec" / "pilot-runs" / "hermes"
    _write(pilot / "summary.json", json.dumps({
        "run_id": "pilot-hermes-pd-fleet", "adapter": "hermes/opencode-go", "model": "m",
        "statuses": {"T-001": "completed", "T-002": "failed"},
    }))
    lines = [
        {"task_id": "T-001", "attempt": 1, "ok": False},
        {"task_id": "T-001", "attempt": 2, "ok": True},
        {"task_id": "T-002", "attempt": 1, "ok": False},
    ]
    _write(pilot / "dispatch-log.jsonl", "\n".join(json.dumps(l) for l in lines) + "\n")
    rows, note = pc._pilot_agents()
    assert note is None and len(rows) == 2
    by = {r["acao"].split(" ")[0]: r for r in rows}
    assert "dispatch ×2" in by["T-001"]["acao"] and "último ok" in by["T-001"]["acao"]
    assert "última falha" in by["T-002"]["acao"]
    assert by["T-001"]["status"] == "completed"
    (pilot / "summary.json").unlink()
    rows, note = pc._pilot_agents()
    assert rows == [] and note == "sem runs"


def test_control_plane_swarm_deterministic(fake_world: Path) -> None:
    a = pc.swarm(fake_world / ".pd-fleet-runs")
    b = pc.swarm(fake_world / ".pd-fleet-runs")
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b


def test_control_plane_swarm_files_shapes(fake_world: Path) -> None:
    sw = pc.swarm(fake_world / ".pd-fleet-runs")
    files = pc.swarm_files({"swarm": sw})
    assert set(files) == {"agents.md", "agents.json"}
    md, js = files["agents.md"], json.loads(files["agents.json"])
    assert "nunca fabricar telemetria" in md
    assert js["rows"] == sw["rows"]
    assert md.count("- **") == len(sw["rows"])
    empty = pc.swarm_files({"swarm": {"rows": [], "generated_at": "", "notes": []}})
    assert "0 linhas" in empty["agents.md"]
    assert json.loads(empty["agents.json"])["rows"] == []


def test_control_plane_build_includes_swarm(fake_world: Path) -> None:
    snap = pc.build(fake_world / ".pd-fleet-runs")
    assert snap["swarm"]["schema"] == "activity-swarm:v1"
    assert snap["swarm"]["rows"]
