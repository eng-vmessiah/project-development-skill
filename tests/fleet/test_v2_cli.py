"""T2-15: V2 CLI adapter contract and safety tests."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd import PD
from pd_fleet.run_store import FleetRunStore


def task(task_id="a"):
    return {"id": task_id, "role": "coder", "objective": task_id,
            "allowed_paths": [f"src/{task_id}"], "outputs": ["out"],
            "acceptance_criteria": ["ok"], "validation_commands": ["check"]}


def plan():
    return {"schema_version": "pd-fleet-plan:v2", "run_id": "r",
            "tasks": [task() | {"wave": 1}]}


def write_plan(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(plan()), encoding="utf-8")
    return path


def run_cli(tmp_path, args, capsys):
    old = Path.cwd()
    try:
        os.chdir(tmp_path)
        PD().run(args)
    finally:
        os.chdir(old)
    return capsys.readouterr().out


def test_read_emits_one_canonical_json_without_absolute_paths(tmp_path, capsys):
    output = run_cli(tmp_path, ["v2", "read", "--plan", str(write_plan(tmp_path))], capsys)
    parsed = json.loads(output)
    assert output == json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    assert str(tmp_path) not in output
    assert parsed["plan"]["schema_version"] == "pd-fleet-plan:v2"


def test_inspect_and_dry_run_are_read_only(tmp_path, capsys):
    path = write_plan(tmp_path)
    store_root = tmp_path / "store"
    before = path.read_bytes()
    output = run_cli(tmp_path, ["v2", "run-local", "--plan", str(path), "--dry-run",
                                "--store", str(store_root)], capsys)
    assert json.loads(output)["status"] == "dry_run"
    assert path.read_bytes() == before
    assert not store_root.exists()


def test_run_local_uses_store_and_returns_canonical_json(tmp_path, capsys):
    path = write_plan(tmp_path)
    store_root = tmp_path / "store"
    output = run_cli(tmp_path, ["v2", "run-local", "--plan", str(path),
                                "--store", str(store_root), "--run-id", "r", "--owner", "cli"], capsys)
    parsed = json.loads(output)
    # The local dispatcher has no validator/evidence producer.  It must fail
    # closed rather than manufacture an accepted completion.
    assert parsed["status"] == "failed"
    assert output == json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    assert FleetRunStore(store_root).load("r")["run_id"] == "r"
    assert str(tmp_path) not in output


def test_external_provider_is_denied_before_execution(tmp_path, capsys):
    with pytest.raises(SystemExit):
        run_cli(tmp_path, ["v2", "run-local", "--plan", str(write_plan(tmp_path)),
                           "--provider", "remote"], capsys)
    assert "remote" not in capsys.readouterr().out


def test_run_local_does_not_fabricate_acceptance_or_validation(tmp_path, capsys):
    path = write_plan(tmp_path)
    store_root = tmp_path / "store"
    run_cli(tmp_path, ["v2", "run-local", "--plan", str(path),
                       "--store", str(store_root), "--run-id", "r"], capsys)

    report = FleetRunStore(store_root).load("r")["reports"]["a"]["report"]
    assert report["status"] == "failed"
    assert "local" not in json.dumps(report)
    assert "tests" not in report
    assert "validation" not in report
    assert "decision" not in report
    assert report["evidence"]["task_id"] == "a"
    assert report["reason"] == "RuntimeError"


def test_run_local_resume_preserves_persisted_attempt(tmp_path, capsys):
    value = plan()
    value["tasks"][0]["retry_policy"] = {"max_attempts": 2, "backoff_seconds": 0}
    path = tmp_path / "retry.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    store_root = tmp_path / "store"

    first = json.loads(run_cli(tmp_path, ["v2", "run-local", "--plan", str(path),
                                          "--store", str(store_root), "--run-id", "r"], capsys))
    assert first["status"] == "failed"
    persisted = FleetRunStore(store_root).load("r")
    assert persisted["attempts"]["a"] == 2
    assert persisted["reports"]["a"]["report"]["evidence"]["attempt"] == 2

    resumed = json.loads(run_cli(tmp_path, ["v2", "run-local", "--plan", str(path),
                                            "--store", str(store_root), "--run-id", "r"], capsys))
    assert resumed["status"] == "failed"
    assert resumed["result"]["reports"][0]["status"] == "failed"


def test_legacy_status_remains_feature_status(tmp_path, capsys):
    output = run_cli(tmp_path, ["init", "legacy"], capsys)
    status_output = run_cli(tmp_path, ["status"], capsys)
    assert "Initialized" in output
    assert "Phase" in status_output


def test_v2_rejects_manifest_symlink(tmp_path, capsys):
    target = write_plan(tmp_path)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(SystemExit):
        run_cli(tmp_path, ["v2", "read", "--plan", str(link)], capsys)
    assert "manifest_symlink" in capsys.readouterr().out


def test_v2_normalizes_aliases_and_rejects_conflicts(tmp_path, capsys):
    value = plan()
    value.pop("schema_version")
    value["schemaVersion"] = "pd-fleet-plan:v2"
    value["tasks"][0]["allowedPaths"] = value["tasks"][0].pop("allowed_paths")
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    parsed = json.loads(run_cli(tmp_path, ["v2", "read", "--plan", str(path)], capsys))
    assert parsed["plan"]["schema_version"] == "pd-fleet-plan:v2"
    value["schema_version"] = "other"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(SystemExit):
        run_cli(tmp_path, ["v2", "read", "--plan", str(path)], capsys)


def test_v2_status_projection_omits_volatile_nested_fields(tmp_path, capsys):
    path = write_plan(tmp_path)
    store_root = tmp_path / "store"
    run_cli(tmp_path, ["v2", "run-local", "--plan", str(path), "--store", str(store_root), "--run-id", "r"], capsys)
    output = run_cli(tmp_path, ["v2", "status", "--store", str(store_root), "--run-id", "r"], capsys)
    assert "updated_at" not in output
    assert "expires_at" not in output
