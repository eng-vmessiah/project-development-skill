"""End-to-end safety and determinism checks for the local example."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]


def _module():
    path = ROOT / "examples" / "pd-fleet" / "run_local.py"
    spec = importlib.util.spec_from_file_location("pd_fleet_run_local", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _files(directory: Path) -> dict[str, bytes]:
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in sorted(directory.rglob("*")) if path.is_file()}


def test_local_example_end_to_end_is_deterministic_and_has_no_external_calls(tmp_path, monkeypatch):
    module = _module()
    plan = ROOT / "examples" / "pd-fleet" / "plan.yaml"
    first, second = tmp_path / "first", tmp_path / "second"

    source = (ROOT / "examples" / "pd-fleet" / "run_local.py").read_text(encoding="utf-8")
    assert "subprocess" not in source and "socket" not in source and "requests" not in source
    assert "Dispatcher()" in source
    assert module.main(["--plan", str(plan), "--output", str(first)]) == 0
    assert module.main(["--plan", str(plan), "--output", str(second)]) == 0
    assert _files(first) == _files(second)

    summary = json.loads((first / "summary.json").read_text(encoding="utf-8"))
    assert set(summary["statuses"]["statuses"].values()) == {"completed"}
    assert set(summary["gate_statuses"].values()) == {"passed"}
    gates = json.loads((first / "gates.json").read_text(encoding="utf-8"))
    assert {gate["gate_type"] for gate in gates} == {"review", "grill", "smoke_test", "evidence"}
    reports = json.loads((first / "reports.json").read_text(encoding="utf-8"))
    assert {report["status"] for report in reports} == {"completed"}
    assert len(reports) == 3


def test_gate_contract_rejects_malformed_and_fake_references_without_writes(tmp_path):
    module = _module()
    ev = module._local_evidence("task", "fingerprint")
    report = module.AgentReport(
        task_id="task", agent_id="agent", status="completed",
        evidence=[ev.to_dict()], timestamps={"started_at": "2026-01-01T00:00:00Z"},
    )
    evidence = {"evidence:task": ev}
    reports = {"report:task": report}
    with pytest.raises(ValueError):
        module._validated_gate({"status": "passed"}, evidence, reports)
    fake = module.GateResult(
        "G1", "review", "passed", owner="owner", decision="approved",
        evidence=["evidence:fake"], reports=["report:task"],
    )
    with pytest.raises(ValueError):
        module._validated_gate(fake, evidence, reports)
    assert not list(tmp_path.iterdir())


def test_output_root_symlink_and_nested_task_id_fail_before_writes(tmp_path):
    module = _module()
    plan = ROOT / "examples" / "pd-fleet" / "plan.yaml"
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    assert module.main(["--plan", str(plan), "--output", str(link)]) == 1
    assert not list(target.iterdir())

    manifest = module._load_manifest(plan)
    manifest = dict(manifest)
    manifest["tasks"] = [dict(manifest["tasks"][0], id="nested/task")]
    bad_plan = tmp_path / "bad.json"
    bad_plan.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "output"
    assert module.main(["--plan", str(bad_plan), "--output", str(output)]) == 1
    assert not output.exists()
