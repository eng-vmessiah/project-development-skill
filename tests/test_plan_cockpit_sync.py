#!/usr/bin/env python3
"""Tests for scripts/plan_cockpit_sync.py — derived-only aggregate, determinism, no fabrication."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import plan_cockpit_sync as pc


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _feature(root: Path, name: str, **overrides: object) -> Path:
    fdir = root / ".spec" / name
    state: dict = {
        "feature": name,
        "phase": 0,
        "status": "initialized",
        "tasks": [],
        "checkpoints": [],
        "created_at": "2026-10-04T23:00:00",
        "updated_at": "2026-10-04T23:00:00",
        "fleet_state": {},
    }
    state.update(overrides)
    _write(fdir / "STATE.json", json.dumps(state))
    return fdir


@pytest.fixture()
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(pc, "REPO", tmp_path)
    monkeypatch.setattr(pc, "SPEC_DIR", tmp_path / ".spec")
    return tmp_path


def test_empty_repo_is_explicit_empty(fake_repo: Path) -> None:
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    assert snap["features"] == []
    assert snap["fleet_runs"] == []
    assert snap["timeline"] == []
    assert snap["meta"]["feature_count"] == 0


def test_state_only_feature_labels_state_md(fake_repo: Path) -> None:
    _feature(fake_repo, "feat-a")
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    row = snap["features"][0]
    assert row["source"] == "state-md"
    assert row["tasks_done"] == 0 and row["tasks_total"] == 0
    assert row["gates"] == [] and row["waves"] == []


def test_plan_yaml_counts_and_gates(fake_repo: Path) -> None:
    fdir = _feature(fake_repo, "feat-b")
    _write(fdir / "plan.yaml", (
        'schema_version: "1"\n'
        "agents: []\n"
        "waves:\n"
        "  - id: wave-1\n"
        "    tasks: [T-1, T-2]\n"
        "    status: pending\n"
        "tasks:\n"
        "  - id: T-1\n"
        "    wave: 1\n"
        "    role: coder\n"
        "    objective: x\n"
        "    status: done\n"
        "  - id: T-2\n"
        "    wave: 1\n"
        "    role: coder\n"
        "    objective: y\n"
        "    status: pending\n"
        "gates:\n"
        "  - id: G1\n"
        "    kind: review\n"
        "    scope: plan\n"
        "    owner: vitor\n"
        "    status: approved\n"
        "    required_evidence: [spec]\n"
    ))
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    row = snap["features"][0]
    assert row["source"] == "plan-yaml"
    assert (row["tasks_done"], row["tasks_total"]) == (1, 2)
    assert row["gates"] == [
        {"id": "G1", "kind": "review", "status": "approved", "owner": "vitor"}
    ]
    assert row["waves"] == [{"id": "wave-1", "status": "pending", "tasks": 2}]


def test_plan_md_fallback_counts(fake_repo: Path) -> None:
    fdir = _feature(fake_repo, "feat-c")
    _write(fdir / "PLAN.md", "# P\n- [x] a\n- [ ] b\n- [x] c\n")
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    row = snap["features"][0]
    assert row["source"] == "plan-md"
    assert (row["tasks_done"], row["tasks_total"]) == (2, 3)


def test_checkpoints_and_timeline_desc(fake_repo: Path) -> None:
    fdir = _feature(fake_repo, "feat-d")
    _write(fdir / "CHECKPOINT-20261004-2312.md", "# Checkpoint - 2026-10-04 23:12\n")
    _write(fdir / "CHECKPOINT-20260727-1458.md", "# Checkpoint - 2026-07-27 14:58\n")
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    row = snap["features"][0]
    assert row["checkpoints"] == 2
    assert [e["ts"] for e in snap["timeline"]] == [
        "2026-10-04T23:12+00:00",
        "2026-07-27T14:58+00:00",
    ]


def test_fleet_runs_scanned_and_corrupt_skipped(fake_repo: Path) -> None:
    runs = fake_repo / ".pd-fleet-runs"
    _write(runs / "run-1" / "snapshot.json", json.dumps({
        "run_id": "run-1", "status": "completed",
        "updated_at": "2026-10-04T23:30:00", "owner": "o",
    }))
    _write(runs / "run-2" / "snapshot.json", "{not json")
    snap = pc.build(runs)
    assert [r["run_id"] for r in snap["fleet_runs"]] == ["run-1"]
    assert snap["fleet_runs"][0]["status"] == "completed"


def test_fleet_runs_includes_pilot_summaries(fake_repo: Path) -> None:
    pilot = fake_repo / ".spec" / "pilot-runs" / "hermes"
    pilot.mkdir(parents=True)
    (pilot / "summary.json").write_text(json.dumps({
        "run_id": "pilot-hermes-pd-fleet",
        "adapter": "hermes/opencode-go",
        "statuses": {"T-001": "completed", "T-002": "failed", "T-003": "completed"},
    }), encoding="utf-8")
    rows = pc.fleet_runs(fake_repo / ".pd-fleet-runs")
    pilot_rows = [row for row in rows if row.get("source") == "pilot"]
    assert len(pilot_rows) == 1
    assert pilot_rows[0]["run_id"] == "pilot-hermes-pd-fleet"
    assert pilot_rows[0]["status"] == "2/3 completed"
    assert pilot_rows[0]["dir"] == ".spec/pilot-runs/hermes"


def test_determinism(fake_repo: Path) -> None:
    _feature(fake_repo, "feat-e")
    a = pc.build(fake_repo / ".pd-fleet-runs")
    b = pc.build(fake_repo / ".pd-fleet-runs")
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b


class _Out:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout


def test_pd_view_enrichment(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _feature(fake_repo, "feat-f")
    payload = json.dumps({"features": [{
        "name": "feat-f", "phase_name": "Setup",
        "tasks_done": 3, "tasks_total": 9, "checkpoints": 1,
    }]})

    def _fake_run(cmd, *a, **k):  # type: ignore[no-untyped-def]
        if cmd and cmd[0] == "git":
            return _Out("")
        return _Out(payload)

    monkeypatch.setattr(pc.subprocess, "run", _fake_run)
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    assert snap["features"][0]["pd_view"]["tasks_total"] == 9


def test_pd_view_absent_without_pd(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _feature(fake_repo, "feat-g")

    def _boom(*a, **k):  # type: ignore[no-untyped-def]
        raise FileNotFoundError("pd")

    monkeypatch.setattr(pc.subprocess, "run", _boom)
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    assert snap["features"][0]["pd_view"] is None
    assert any("pd list" in w for w in snap["meta"]["warnings"])


def test_widget_payloads_shapes(fake_repo: Path) -> None:
    _feature(fake_repo, "feat-w")
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    payloads = pc.widget_payloads(snap)
    assert [p["id"] for p in payloads] == [
        "mc-overview", "mc-features", "mc-tasks", "mc-timeline", "mc-fleet",
        "mc-selector", "mc-mission-info", "mc-mission-tasks",
    ]
    assert all(p["tab"] == "mc" for p in payloads)
    assert payloads[1]["bindings"]["rows"]["value"][0]["feature"] == "feat-w"
    assert payloads[0]["bindings"]["content"]["value"].startswith("# Mission Control")


def test_publish_files_shapes(fake_repo: Path) -> None:
    _feature(fake_repo, "feat-p")
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    files = pc.publish_files(snap)
    assert set(files) == {"overview.md", "fleet.md", "tables.json"}
    tables = json.loads(files["tables.json"])
    assert set(tables) == {"features", "tasks", "timeline"}
    assert tables["features"][0]["feature"] == "feat-p"


def test_mission_files_plan_yaml(fake_repo: Path) -> None:
    fdir = _feature(fake_repo, "feat-m")
    _write(fdir / "plan.yaml", (
        'schema_version: "1"\n'
        "agents: []\n"
        "waves:\n"
        "  - id: wave-1\n"
        "    tasks: [T-1]\n"
        "    status: pending\n"
        "tasks:\n"
        "  - id: T-1\n"
        "    wave: 1\n"
        "    role: coder\n"
        "    objective: x\n"
        "    status: done\n"
        "gates:\n"
        "  - id: G1\n"
        "    kind: review\n"
        "    scope: plan\n"
        "    owner: vitor\n"
        "    status: approved\n"
        "    required_evidence: [spec]\n"
    ))
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    files = pc.mission_files(snap, "feat-m")
    assert set(files) == {"mission.md", "mission.json"}
    detail = json.loads(files["mission.json"])
    assert detail["mission"] == "feat-m"
    assert detail["tasks"] == [{"id": "T-1", "wave": "1", "role": "coder", "status": "✅ done"}]
    assert detail["gates"][0]["id"] == "G1"
    assert "Plano da missão" in files["mission.md"]


def test_mission_files_legacy_mission(fake_repo: Path) -> None:
    _feature(fake_repo, "feat-legacy")
    snap = pc.build(fake_repo / ".pd-fleet-runs")
    files = pc.mission_files(snap, "feat-legacy")
    detail = json.loads(files["mission.json"])
    assert detail["tasks"] == []
    assert "legada" in files["mission.md"]
