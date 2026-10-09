#!/usr/bin/env python3
"""Live contract guard for the swarm surface — mission pd-fleet-control-plane-v1 (T-103).

Read-only: builds the REAL snapshot and asserts the never-fabricate invariants.
Run: /usr/bin/python3 -m pytest .spec/pd-fleet-control-plane-v1/tests -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import plan_cockpit_sync as pc

ROW_KEYS = {"agente", "fonte", "fidelity", "status", "heartbeat", "acao", "arquivos", "nota"}


def test_swarm_rows_are_typed_and_explicit() -> None:
    sw = pc.swarm(REPO / ".pd-fleet-runs")
    assert sw["schema"] == "activity-swarm:v1"
    assert sw["rows"], "superfície exige ao menos as linhas explícitas"
    for r in sw["rows"]:
        assert set(r) == ROW_KEYS
        assert isinstance(r["status"], str)
        if r["status"] == "sem fonte":
            assert r["heartbeat"] == "—" and r["acao"] == "—", "linha sem fonte não inventa dados"


def test_swarm_files_reproducible() -> None:
    snap = pc.build(REPO / ".pd-fleet-runs")
    a = pc.swarm_files(snap)
    b = pc.swarm_files(snap)
    assert a == b
    data = json.loads(a["agents.json"])
    assert data["rows"] == snap["swarm"]["rows"]
    assert "nunca fabricar telemetria" in a["agents.md"]
