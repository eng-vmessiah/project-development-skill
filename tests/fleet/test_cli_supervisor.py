import contextlib
import json
import os
import sys
from io import StringIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd import PD  # noqa: E402
from pd_fleet.handoff import HandoffStore, create_handoff  # noqa: E402


def _run(tmp_path, *args):
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        out = StringIO()
        with contextlib.redirect_stdout(out):
            PD().run(list(args))
        return out.getvalue()
    finally:
        os.chdir(old)


def _feature(tmp_path, fleet_state=None):
    feature = tmp_path / ".spec" / "demo"
    feature.mkdir(parents=True)
    payload = {
        "feature": "demo", "phase": 0, "status": "initialized", "tasks": [],
        "checkpoints": [], "created_at": "t", "updated_at": "t",
        "fleet_state": fleet_state or {},
    }
    (feature / "STATE.json").write_text(json.dumps(payload), encoding="utf-8")
    (feature / "STATE.md").write_text("# state\n", encoding="utf-8")
    return feature


def _plan(feature):
    (feature / "fleet.yaml").write_text("""schema_version: '1'
waves:
  - id: wave-1
    tasks: [T-1]
tasks:
  - id: T-1
    wave: 1
    role: coder
    objective: first
    outputs: [first]
    acceptance_criteria: [done]
    validation_commands: ['true']
gates: []
""", encoding="utf-8")


def _handoff(store, run_id="run-1"):
    artifact = create_handoff(
        mission_id="mission-1", mission_run_id=run_id, task_id="T-1",
        source_lane_id="lane-1", attempt_id="attempt-1", session_id="session-1",
        target_role="coder", owner_epoch=1, reason="handoff",
        summary="bounded summary", completed=["T-0"], remaining=["T-1"],
        decisions=["continue"], risks=["unknown"], evidence_refs=["ref-1"],
        next_action="resume",
    )
    return HandoffStore(store, run_id=run_id, owner_epoch=1).save(
        artifact, status="ready", evidence_refs=["ref-1"]
    )


def test_parser_has_s6_commands():
    parser = PD().parser
    assert parser.parse_args(["fleet-supervisor-status"]).command == "fleet-supervisor-status"
    parsed = parser.parse_args(["fleet-handoff-preview", "--run-id", "run-1", "--handoff-id", "h-1"])
    assert parsed.command == "fleet-handoff-preview"
    assert parsed.store_root == ".pd-fleet-handoffs"


def test_supervisor_status_json_is_deterministic_and_read_only(tmp_path):
    feature = _feature(tmp_path, {"tasks": [{"id": "T-0", "status": "completed"}]})
    _plan(feature)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in feature.glob("STATE.*")}
    first = _run(tmp_path, "fleet-supervisor-status", "--feature", "demo", "--plan", str(feature / "fleet.yaml"), "--json")
    second = _run(tmp_path, "fleet-supervisor-status", "--feature", "demo", "--plan", str(feature / "fleet.yaml"), "--json")
    assert first == second
    result = json.loads(first)
    assert result["read_only"] is True
    assert result["fleet_available"] is True
    assert result["ready_tasks"] == ["T-1"]
    assert result["supervisor"]["diagnosis"]["status"] == "unknown"
    assert result["supervisor"]["live_workers"] == "unavailable"
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in feature.glob("STATE.*")} == before


def test_supervisor_status_text_is_read_only(tmp_path):
    _feature(tmp_path)
    output = _run(tmp_path, "fleet-supervisor-status", "--feature", "demo", "--no-color")
    assert "read-only" in output.lower()
    assert "supervisor" in output.lower()
    assert "unavailable" in output.lower() or "unknown" in output.lower()


def test_supervisor_projection_hides_absolute_plan_and_hostile_fleet_state(tmp_path):
    hostile = {
        "tasks": [{"id": "T-0", "status": "completed", "debug": "dump", "password": "hunter2",
                   "note": "pid=4242 /home/private https://secret.example"}],
        "unknown_debug": "do not emit", "pid": 4242, "path": "/home/private",
    }
    feature = _feature(tmp_path, hostile)
    _plan(feature)
    output = _run(tmp_path, "fleet-supervisor-status", "--feature", "demo",
                  "--plan", str(feature / "fleet.yaml"), "--json")
    result = json.loads(output)
    assert result["plan_path"] == "fleet.yaml"
    assert "/" not in result["plan_path"]
    assert "unknown_debug" not in output and "hunter2" not in output
    assert "4242" not in output and "/home/private" not in output
    assert "secret.example" not in output


def test_handoff_preview_json_and_text(tmp_path):
    store = tmp_path / ".pd-fleet-handoffs"
    envelope = _handoff(store)
    output = _run(tmp_path, "fleet-handoff-preview", "--store", str(store), "--run-id", "run-1", "--handoff-id", envelope.handoff_id, "--owner-epoch", "1", "--json")
    result = json.loads(output)
    assert result["read_only"] is True
    assert result["envelope"]["handoff_id"] == envelope.handoff_id
    assert result["artifact"]["next_action"] == "resume"
    text = _run(tmp_path, "fleet-handoff-preview", "--store", str(store), "--run-id", "run-1", "--handoff-id", envelope.handoff_id, "--owner-epoch", "1", "--no-color")
    assert "read-only" in text.lower()
    assert envelope.handoff_id in text


def test_missing_handoff_fails_closed_without_creating_store(tmp_path):
    store = tmp_path / "missing-store"
    with pytest.raises(SystemExit):
        _run(tmp_path, "fleet-handoff-preview", "--store", str(store), "--run-id", "run-1", "--handoff-id", "missing", "--json")
    assert not store.exists()
