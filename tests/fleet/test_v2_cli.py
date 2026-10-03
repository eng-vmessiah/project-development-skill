"""T2-15: V2 CLI adapter contract and safety tests."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd import PD
from pd_fleet.run_store import FleetRunStore, RunStoreError


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


def test_run_local_uses_store_and_returns_completed_simulated_fleet(tmp_path, capsys):
    path = write_plan(tmp_path)
    store_root = tmp_path / "store"
    output = run_cli(tmp_path, ["v2", "run-local", "--plan", str(path),
                                "--store", str(store_root), "--run-id", "r", "--owner", "cli"], capsys)
    parsed = json.loads(output)
    assert parsed["status"] == "completed"
    assert parsed["result"]["reports"][0]["status"] == "completed"
    assert parsed["result"]["reports"][0]["evidence"]["adapter"] == "simulated"
    assert output == json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    assert FleetRunStore(store_root).load("r")["status"] == "completed"
    assert str(tmp_path) not in output


def test_run_local_max_parallel_bounds_fail_before_store_mutation(tmp_path, capsys):
    path = write_plan(tmp_path)
    store_root = tmp_path / "store"
    for value in ("0", "9"):
        with pytest.raises(SystemExit):
            run_cli(tmp_path, ["v2", "run-local", "--plan", str(path), "--store", str(store_root),
                               "--max-parallel", value], capsys)
        assert not store_root.exists()


def test_run_local_accepts_bounded_max_parallel(tmp_path, capsys):
    output = run_cli(tmp_path, ["v2", "run-local", "--plan", str(write_plan(tmp_path)),
                                "--store", str(tmp_path / "store"), "--max-parallel", "2"], capsys)
    assert json.loads(output)["status"] == "completed"


def test_run_local_recovers_expired_lease_with_injected_wall_clock(tmp_path, capsys, monkeypatch):
    path = write_plan(tmp_path)
    store_root = tmp_path / "store"
    now = ["2026-01-01T00:00:00Z"]
    clock = lambda: now[0]
    with FleetRunStore(store_root, clock=clock) as store:
        store.create("r", plan(), "cli")
        store.claim("r", "a", "cli", lease_seconds=1)
    now[0] = "2026-01-01T00:00:02Z"
    monkeypatch.setattr(PD, "_v2_wall_clock", staticmethod(clock))
    output = run_cli(tmp_path, ["v2", "run-local", "--plan", str(path), "--store", str(store_root), "--run-id", "r"], capsys)
    assert json.loads(output)["status"] == "completed"
    assert FleetRunStore(store_root, clock=clock).load("r")["attempts"]["a"] == 2




def test_run_local_retry_once_persists_audit_event_and_completes(tmp_path, capsys):
    data = plan()
    data["tasks"][0]["retry_policy"] = {"max_attempts": 2, "backoff_seconds": 3, "retryable_errors": ["simulated_transient"]}
    path = tmp_path / "retry.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    root = tmp_path / "store"
    payload = json.loads(run_cli(tmp_path, ["v2", "run-local", "--plan", str(path), "--store", str(root), "--simulated-fixture", "retry-once"], capsys))
    snapshot = FleetRunStore(root).load("r")
    assert payload["status"] == "completed"
    assert snapshot["attempts"]["a"] == 2
    assert [event["event_id"] for event in snapshot["events"]] == ["retry-a-1", "a"]




def test_run_local_fail_always_exhausts_retry_and_is_not_ready(tmp_path, capsys):
    data = plan(); data["tasks"][0]["retry_policy"] = {"max_attempts": 2, "retryable_errors": ["simulated_transient"]}
    path = tmp_path / "fail.json"; path.write_text(json.dumps(data)); root = tmp_path / "store"
    payload = json.loads(run_cli(tmp_path, ["v2", "run-local", "--plan", str(path), "--store", str(root), "--simulated-fixture", "fail-always"], capsys))
    snapshot = FleetRunStore(root).load("r")
    readiness = json.loads(run_cli(tmp_path, ["v2", "readiness", "--store", str(root), "--run-id", "r"], capsys))
    assert payload["status"] == "failed" and snapshot["attempts"]["a"] == 2
    assert [event["event_id"] for event in snapshot["events"]] == ["retry-a-1", "a"]
    assert readiness["ready"] is False and readiness["reason"] == "run_failed"


def test_run_local_retry_allowlist_rejects_nonmatching_failure(tmp_path, capsys):
    data = plan(); data["tasks"][0]["retry_policy"] = {"max_attempts": 2, "retryable_errors": ["other"]}
    path = tmp_path / "deny.json"; path.write_text(json.dumps(data)); root = tmp_path / "store"
    payload = json.loads(run_cli(tmp_path, ["v2", "run-local", "--plan", str(path), "--store", str(root), "--simulated-fixture", "fail-always"], capsys))
    snapshot = FleetRunStore(root).load("r")
    assert payload["status"] == "failed" and snapshot["attempts"]["a"] == 1
    assert [event["event_id"] for event in snapshot["events"]] == ["a"]


def test_run_local_resume_after_retry_success_does_not_replay_completed_task(tmp_path, capsys):
    data = plan(); data["tasks"][0]["retry_policy"] = {"max_attempts": 2, "retryable_errors": ["simulated_transient"]}
    path = tmp_path / "resume.json"; path.write_text(json.dumps(data)); root = tmp_path / "store"
    first = json.loads(run_cli(tmp_path, ["v2", "run-local", "--plan", str(path), "--store", str(root), "--simulated-fixture", "retry-once"], capsys))
    before = FleetRunStore(root).load("r")
    resumed = json.loads(run_cli(tmp_path, ["v2", "run-local", "--plan", str(path), "--store", str(root), "--simulated-fixture", "fail-always"], capsys))
    assert first["status"] == resumed["status"] == "completed"
    assert FleetRunStore(root).load("r") == before


def test_external_provider_is_denied_before_execution(tmp_path, capsys):
    with pytest.raises(SystemExit):
        run_cli(tmp_path, ["v2", "run-local", "--plan", str(write_plan(tmp_path)),
                           "--provider", "remote"], capsys)
    assert "remote" not in capsys.readouterr().out


def test_run_local_persists_simulated_validation_and_evidence(tmp_path, capsys):
    path = write_plan(tmp_path)
    store_root = tmp_path / "store"
    run_cli(tmp_path, ["v2", "run-local", "--plan", str(path),
                       "--store", str(store_root), "--run-id", "r"], capsys)

    report = FleetRunStore(store_root).load("r")["reports"]["a"]["report"]
    assert report["status"] == "completed"
    assert report["evidence"]["adapter"] == "simulated"
    assert report["validation"]["status"] == "passed"
    assert report["tests"] == [{"name": "local", "status": "passed"}]
    assert report["decision"]["decision"] == "accept"


def test_run_local_resume_returns_persisted_completed_run(tmp_path, capsys):
    value = plan()
    path = tmp_path / "retry.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    store_root = tmp_path / "store"

    first = json.loads(run_cli(tmp_path, ["v2", "run-local", "--plan", str(path),
                                          "--store", str(store_root), "--run-id", "r"], capsys))
    assert first["status"] == "completed"
    persisted = FleetRunStore(store_root).load("r")
    assert persisted["attempts"]["a"] == 1

    resumed = json.loads(run_cli(tmp_path, ["v2", "run-local", "--plan", str(path),
                                            "--store", str(store_root), "--run-id", "r"], capsys))
    assert resumed["status"] == "completed"
    assert resumed["result"]["reports"][0]["status"] == "completed"


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


def test_v2_inspect_projects_persisted_run_readiness_and_events(tmp_path, capsys):
    path = write_plan(tmp_path)
    store_root = tmp_path / "store"
    run_cli(tmp_path, ["v2", "run-local", "--plan", str(path),
                       "--store", str(store_root), "--run-id", "r"], capsys)

    output = run_cli(tmp_path, ["v2", "inspect", "--store", str(store_root),
                                "--run-id", "r"], capsys)
    parsed = json.loads(output)
    assert parsed["status"] == "ok"
    assert parsed["run_id"] == "r"
    assert parsed["readiness"] == "ready"
    assert parsed["task_statuses"] == {"a": "completed"}
    assert parsed["report_statuses"] == {"a": "completed"}
    assert parsed["event_sequence"] == 1
    assert parsed["event_count"] == 1
    assert "updated_at" not in output
    assert "expires_at" not in output


def test_v2_readiness_reports_ready_and_not_ready_states(tmp_path, capsys):
    path = write_plan(tmp_path)
    store_root = tmp_path / "store"
    run_cli(tmp_path, ["v2", "run-local", "--plan", str(path), "--store", str(store_root), "--run-id", "r"], capsys)
    ready = json.loads(run_cli(tmp_path, ["v2", "readiness", "--store", str(store_root), "--run-id", "r"], capsys))
    assert ready == {"ready": True, "readiness": "ready", "reason": "completed", "run_id": "r", "status": "ok"}
    assert PD._v2_readiness({"run_id": "r", "readiness": "in_progress"})["reason"] == "run_in_progress"
    assert PD._v2_readiness({"run_id": "r", "readiness": "failed"})["reason"] == "run_failed"


def test_v2_readiness_requires_existing_run(tmp_path, capsys):
    with pytest.raises(SystemExit):
        run_cli(tmp_path, ["v2", "readiness", "--store", str(tmp_path / "store"), "--run-id", "missing"], capsys)
    assert "V2 run unavailable" in capsys.readouterr().out

    with pytest.raises(ValueError, match="snapshot_shape"):
        PD._v2_inspection({"tasks": [], "reports": {}})
    with pytest.raises(ValueError, match="snapshot_bounds"):
        PD._v2_inspection({"tasks": {}, "reports": {}, "waves": [["x" * 129]]})
    with pytest.raises(ValueError, match="snapshot_bounds"):
        PD._v2_inspection({"tasks": {str(i): {"status": "completed"} for i in range(257)}, "reports": {}})
    with pytest.raises(ValueError, match="snapshot_shape"):
        PD._v2_inspection({"tasks": {"a": []}, "reports": {}})
    with pytest.raises(ValueError, match="snapshot_shape"):
        PD._v2_inspection({"tasks": {}, "reports": {"a": {"status": "completed", "report": {"status": []}}}})


def test_v2_inspect_rejects_oversized_backup_candidate(tmp_path):
    store_root = tmp_path / "store"
    with FleetRunStore(store_root) as store:
        store.create("r", plan(), "cli")
    run_dir = store_root / "r"
    (run_dir / "snapshot.json").write_text("{", encoding="utf-8")
    (run_dir / "snapshot.json.bak").write_bytes(b"x" * (512 * 1024 + 1))
    with pytest.raises(RunStoreError):
        PD._v2_read_snapshot(str(store_root), "r")


def test_v2_inspect_rejects_broken_backup_symlink(tmp_path):
    store_root = tmp_path / "store"
    with FleetRunStore(store_root) as store:
        store.create("r", plan(), "cli")
    run_dir = store_root / "r"
    (run_dir / "snapshot.json.bak").symlink_to(run_dir / "missing.json")
    with pytest.raises(RunStoreError):
        PD._v2_read_snapshot(str(store_root), "r")
