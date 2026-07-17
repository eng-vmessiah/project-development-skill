import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd import PD  # noqa: E402


def _run(tmp_path, *args):
    import contextlib
    from io import StringIO
    import os
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        out = StringIO()
        with contextlib.redirect_stdout(out):
            PD().run(list(args))
        return out.getvalue()
    finally:
        os.chdir(old)


def _feature(tmp_path, state=None):
    feature = tmp_path / ".spec" / "demo"
    feature.mkdir(parents=True)
    payload = {"feature": "demo", "phase": 0, "status": "initialized", "tasks": [], "checkpoints": [],
               "created_at": "t", "updated_at": "t", "fleet_state": state or {}}
    (feature / "STATE.json").write_text(json.dumps(payload))
    return feature


def _plan(feature):
    (feature / "fleet.yaml").write_text("""schema_version: '1'
waves:
  - id: wave-1
    tasks: [T-1]
  - id: wave-2
    tasks: [T-2]
    gates: [G-1]
tasks:
  - id: T-1
    wave: 1
    role: coder
    objective: first
    outputs: [first]
    acceptance_criteria: [done]
    validation_commands: ['true']
  - id: T-2
    wave: 2
    role: coder
    objective: second
    outputs: [second]
    acceptance_criteria: [done]
    validation_commands: ['true']
    depends_on: [T-1]
gates:
  - id: G-1
    status: pending
""")


def test_json_and_text_are_read_only(tmp_path):
    feature = _feature(tmp_path)
    _plan(feature)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in feature.glob("STATE.*")}
    result = json.loads(_run(tmp_path, "fleet-ready", "--feature", "demo", "--json"))
    assert result["ready_tasks"] == ["T-1"]
    assert "Fleet tasks ready" in _run(tmp_path, "fleet-ready", "--feature", "demo", "--no-color")
    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in feature.glob("STATE.*")}
    assert before == after


def test_dependencies_and_gates(tmp_path):
    feature = _feature(tmp_path, {"tasks": [{"id": "T-1", "status": "completed"}]})
    _plan(feature)
    assert json.loads(_run(tmp_path, "fleet-ready", "--feature", "demo", "--json"))["ready_tasks"] == []
    payload = json.loads(feature.joinpath("STATE.json").read_text())
    payload["fleet_state"]["gates"] = [{"id": "G-1", "status": "passed"}]
    feature.joinpath("STATE.json").write_text(json.dumps(payload))
    assert json.loads(_run(tmp_path, "fleet-ready", "--feature", "demo", "--json"))["ready_tasks"] == ["T-2"]


def test_missing_fleet_is_explicit(tmp_path):
    _feature(tmp_path)
    result = json.loads(_run(tmp_path, "fleet-status", "--feature", "demo", "--json"))
    assert result["fleet_available"] is False
    assert result["plan"] is None
