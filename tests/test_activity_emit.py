#!/usr/bin/env python3
"""Activity emitter tests (T-201) — local bus, redaction, idempotency, collector consumption."""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pd_fleet.activity_emit as ae
import plan_cockpit_sync as pc

ROW_KEYS = {"agente", "fonte", "fidelity", "status", "heartbeat", "acao", "arquivos", "nota"}


def _db(path: Path, now: float) -> None:
    con = sqlite3.connect(path)
    con.executescript("""
        create table sessions (id text primary key, source text, user_id text, model text,
            started_at real, ended_at real, message_count integer, tool_call_count integer);
        create table messages (id integer primary key, session_id text, role text, content text,
            tool_name text, timestamp real);
        create table gateway_heartbeats (backend_id text primary key, pid integer, profile text,
            host text, last_heartbeat real);
    """)
    con.execute("insert into sessions values ('s1','desktop','vitor-id','m',?,NULL,7,3)", (now - 600,))
    con.execute("insert into sessions values ('s2','cron','vitor-id','m',?,?,4,2)", (now - 7200, now - 7000))
    con.execute("insert into messages values (1,'s1','user','SEGREDO XYZ nao pode vazar',NULL,?)", (now - 300,))
    con.execute("insert into messages values (2,'s1','tool',NULL,'terminal',?)", (now - 240,))
    con.execute("insert into messages values (3,'s2','tool',NULL,'patch',?)", (now - 7000,))
    con.execute("insert into gateway_heartbeats values ('default@HOST:123:ab',123,'default','HOST',?)", (now - 30,))
    con.commit()
    con.close()


def test_activity_emit_redacts_and_writes(tmp_path: Path) -> None:
    now = time.time()
    db = tmp_path / "state.db"
    _db(db, now)
    out = tmp_path / "activity"
    res = ae.emit(db, out)
    assert res["emitted"] == 3  # 2 sessões + 1 gateway
    bus = (out / "events.jsonl").read_text(encoding="utf-8")
    assert "SEGREDO" not in bus and "vitor-id" not in bus
    evs = [json.loads(l) for l in bus.splitlines()]
    s1 = next(e for e in evs if e["run_id"] == "s1")
    assert s1["status"] == "running" and s1["action"] == "terminal"
    assert s1["meta"]["msgs"] == 7
    assert s1["source"] == "hermes" and s1["fidelity"] == "high"
    gw = next(e for e in evs if e["agent_id"] == "gateway:default")
    assert gw["kind"] == "heartbeat" and gw["status"] is None


def test_activity_emit_idempotent(tmp_path: Path) -> None:
    now = time.time()
    db = tmp_path / "state.db"
    _db(db, now)
    out = tmp_path / "activity"
    ae.emit(db, out)
    n1 = len((out / "events.jsonl").read_text(encoding="utf-8").splitlines())
    res = ae.emit(db, out)
    assert res["emitted"] == 0 and res["skipped"] == 3
    n2 = len((out / "events.jsonl").read_text(encoding="utf-8").splitlines())
    assert n1 == n2


def test_activity_emit_dry_run_writes_nothing(tmp_path: Path) -> None:
    now = time.time()
    db = tmp_path / "state.db"
    _db(db, now)
    out = tmp_path / "activity"
    res = ae.emit(db, out, dry_run=True)
    assert res["emitted"] == 3
    assert not (out / "events.jsonl").exists()


def test_collector_reads_bus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert pc._hermes_agents_from_events() == []
    bus = tmp_path / ".hermes/activity/events.jsonl"
    bus.parent.mkdir(parents=True)
    fresh = datetime.now(UTC).isoformat(timespec="seconds")
    bus.write_text(json.dumps({
        "v": 1, "event_id": "e1", "ts": fresh, "agent_id": "hermes:desktop",
        "run_id": "s1", "source": "hermes", "fidelity": "high", "kind": "status",
        "action": "terminal", "status": "running", "meta": {"model": "m", "msgs": 7},
    }) + "\n", encoding="utf-8")
    rows = pc._hermes_agents_from_events()
    assert len(rows) == 1 and rows[0]["agente"] == "hermes:desktop"
    assert rows[0]["status"] == "running" and rows[0]["acao"] == "terminal"
    assert set(rows[0]) == ROW_KEYS


def test_collector_downgrades_old_running_to_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    bus = tmp_path / ".hermes/activity/events.jsonl"
    bus.parent.mkdir(parents=True)
    old = (datetime.now(UTC) - timedelta(days=3)).isoformat(timespec="seconds")
    bus.write_text(json.dumps({
        "v": 1, "event_id": "e-stale", "ts": old, "agent_id": "hermes:desktop",
        "run_id": "s1", "source": "hermes", "fidelity": "high", "kind": "status",
        "action": "terminal", "status": "running", "meta": {},
    }) + "\n", encoding="utf-8")
    rows = pc._hermes_agents_from_events()
    assert rows[0]["status"] == "stale"


def test_collector_newest_event_beats_older_rank(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    bus = tmp_path / ".hermes/activity/events.jsonl"
    bus.parent.mkdir(parents=True)
    now = datetime.now(UTC)
    running = {"v": 1, "event_id": "e-run", "ts": (now - timedelta(minutes=10)).isoformat(timespec="seconds"),
               "agent_id": "hermes:desktop", "run_id": "s1", "source": "hermes", "fidelity": "high",
               "kind": "status", "action": "terminal", "status": "running", "meta": {}}
    failed = {"v": 1, "event_id": "e-fail", "ts": (now - timedelta(minutes=2)).isoformat(timespec="seconds"),
              "agent_id": "hermes:desktop", "run_id": "s2", "source": "hermes", "fidelity": "high",
              "kind": "status", "action": "terminal", "status": "failed", "meta": {}}
    bus.write_text(json.dumps(running) + "\n" + json.dumps(failed) + "\n", encoding="utf-8")
    rows = pc._hermes_agents_from_events()
    assert rows[0]["status"] == "failed"


def test_activity_emit_window_uses_activity_not_ended_at(tmp_path: Path) -> None:
    now = time.time()
    db = tmp_path / "state.db"
    con = sqlite3.connect(db)
    con.executescript("""
        create table sessions (id text primary key, source text, user_id text, model text,
            started_at real, ended_at real, message_count integer, tool_call_count integer);
        create table messages (id integer primary key, session_id text, role text, content text,
            tool_name text, timestamp real);
        create table gateway_heartbeats (backend_id text primary key, pid integer, profile text,
            host text, last_heartbeat real);
    """)
    # Session closed in bulk yesterday, but its last real activity is 60 days old.
    con.execute("insert into sessions values ('old','desktop','u','m',?,?,2,1)",
                (now - 60 * 86400, now - 86400))
    con.execute("insert into messages values (1,'old','user','x',NULL,?)", (now - 60 * 86400,))
    con.commit()
    con.close()
    out = tmp_path / "activity"
    res = ae.emit(db, out)
    assert res["emitted"] == 0
    assert not (out / "events.jsonl").exists()


def test_swarm_uses_bus_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "REPO", tmp_path)
    monkeypatch.setattr(pc, "SPEC_DIR", tmp_path / ".spec")
    monkeypatch.setenv("HOME", str(tmp_path))
    bus = tmp_path / ".hermes/activity/events.jsonl"
    bus.parent.mkdir(parents=True)
    bus.write_text(json.dumps({
        "v": 1, "event_id": "e2", "ts": "2026-10-09T19:50:00+00:00", "agent_id": "hermes:cli",
        "run_id": "s3", "source": "hermes", "fidelity": "high", "kind": "status",
        "action": "bash", "status": "waiting", "meta": {},
    }) + "\n", encoding="utf-8")
    sw = pc.swarm(tmp_path / ".pd-fleet-runs")
    names = [r["agente"] for r in sw["rows"]]
    assert "hermes:cli" in names
    assert "sessões Hermes" not in names
