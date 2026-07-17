import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

import pd_fleet.checkpoint as checkpoint_module  # noqa: E402
from pd_fleet.checkpoint import (  # noqa: E402
    Checkpoint,
    CheckpointError,
    completed_tasks,
    load_checkpoint,
    recover_orphans,
    resume_tasks,
    retry_task,
    save_checkpoint,
)
from pd_fleet.lifecycle import LifecycleState, RetryExhausted, TaskLifecycle  # noqa: E402


def lifecycle(task_id, status, **values):
    return {"task_id": task_id, "status": status, **values}


def checkpoint_fixture():
    return Checkpoint.create(
        "feature/resume",
        3,
        tasks={"done": {"id": "done"}, "failed": {"id": "failed"}, "blocked": {"id": "blocked"}, "pending": {"id": "pending"}},
        lifecycle={
            "done": lifecycle("done", "completed", attempt=1, outputs=["artifact"], evidence=["report"]),
            "failed": lifecycle("failed", "failed", attempt=1, max_attempts=2, error="transient", retryable=True),
            "blocked": lifecycle("blocked", "blocked", reason="gate G1"),
            "pending": lifecycle("pending", "pending"),
        },
        reports=[{"task": "done", "path": "reports/done.json"}],
        evidence=[{"kind": "pytest", "command": "pytest -q"}],
        blockers=[{"task": "blocked", "reason": "gate G1"}],
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_checkpoint_schema_and_round_trip_preserve_contract():
    original = checkpoint_fixture()
    payload = original.to_dict()

    assert payload["schema_version"] == 1
    assert set(payload) == {"schema_version", "feature", "wave", "tasks", "lifecycle", "reports", "evidence", "blockers", "created_at"}
    restored = Checkpoint.from_dict(payload)
    assert restored.to_dict() == payload
    assert restored.feature == "feature/resume"
    assert restored.wave == 3


def test_save_and_load_checkpoint_atomically(tmp_path):
    path = tmp_path / "state" / "checkpoint.json"
    checkpoint = checkpoint_fixture()
    save_checkpoint(checkpoint, path)

    assert path.exists()
    assert load_checkpoint(path).to_dict() == checkpoint.to_dict()
    assert json.loads(path.read_text(encoding="utf-8")) == checkpoint.to_dict()
    assert not list(path.parent.glob(f".{path.name}.*"))


def test_load_rejects_corrupt_json_and_schema_errors(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(CheckpointError, match="inválido ou ilegível"):
        load_checkpoint(path)

    path.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")
    with pytest.raises(CheckpointError, match="schema_version"):
        load_checkpoint(path)

    path.write_text(json.dumps({"schema_version": 1, "feature": "x", "created_at": "now", "lifecycle": {"a": {"status": "unknown"}}}), encoding="utf-8")
    with pytest.raises(CheckpointError, match="estado inválido"):
        load_checkpoint(path)

    path.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(CheckpointError, match="objeto JSON"):
        load_checkpoint(path)


def test_completed_tasks_and_resume_never_replay_completed():
    checkpoint = checkpoint_fixture()

    assert completed_tasks(checkpoint) == ["done"]
    assert checkpoint.completed() == ["done"]
    assert resume_tasks(checkpoint) == ["failed", "pending"]
    assert "done" not in checkpoint.resume_tasks()
    assert "blocked" not in checkpoint.resume_tasks()


def test_running_orphan_recovery_uses_task_lifecycle_and_preserves_history():
    running = TaskLifecycle("running", max_attempts=3)
    running.mark_ready().start("agent-a", now=100)
    running.evidence = {"partial": "log"}
    checkpoint = Checkpoint.create("f", 1, tasks={"running": {"id": "running"}}, lifecycle={"running": running})

    assert recover_orphans(checkpoint, now=401, timeout_seconds=300) == ["running"]
    recovered = checkpoint.lifecycle["running"]
    assert recovered["status"] == LifecycleState.FAILED.value
    assert recovered["error"] == "orphaned_run"
    assert recovered["retryable"] is True
    assert recovered["attempt"] == 1
    assert recovered["history"][-1]["to"] == "failed"


def test_explicit_retry_transitions_failed_task_to_ready():
    checkpoint = Checkpoint.create(
        "f", 1,
        tasks={"t1": {"id": "t1"}},
        lifecycle={"t1": lifecycle("t1", "failed", attempt=1, max_attempts=2, error="boom", retryable=True)},
    )

    result = retry_task(checkpoint, "t1", now=20)
    assert result["status"] == "ready"
    assert result["attempt"] == 2
    assert result["error"] is None
    assert result["history"][-1]["reason"] == "explicit_retry"


def test_reports_evidence_and_blockers_survive_save_load(tmp_path):
    checkpoint = checkpoint_fixture()
    path = tmp_path / "checkpoint.json"
    checkpoint.save(path)
    restored = Checkpoint.load(path)

    assert restored.reports == checkpoint.reports
    assert restored.evidence == checkpoint.evidence
    assert restored.blockers == checkpoint.blockers
    assert restored.lifecycle["done"]["evidence"] == ["report"]


def test_atomic_write_failure_keeps_previous_checkpoint(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    previous = checkpoint_fixture()
    previous.save(path)
    old_bytes = path.read_bytes()
    replacement = Checkpoint.create("new-feature", 99, tasks={"new": {"id": "new"}})

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(checkpoint_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        replacement.save(path)
    assert path.read_bytes() == old_bytes
    assert load_checkpoint(path).to_dict() == previous.to_dict()
    assert not list(path.parent.glob(f".{path.name}.*"))


@pytest.mark.parametrize("field, value", [("feature", 3), ("wave", "one"), ("tasks", "wrong"), ("lifecycle", "wrong"), ("reports", {}), ("evidence", {}), ("blockers", {})])
def test_payload_top_level_types_are_checkpoint_errors(field, value):
    payload = checkpoint_fixture().to_dict(); payload[field] = value
    with pytest.raises(CheckpointError): Checkpoint.from_dict(payload)


@pytest.mark.parametrize("field, value", [("attempt", True), ("attempt", -1), ("attempt", 1.5), ("max_attempts", False), ("max_attempts", 0), ("max_attempts", 1.5), ("retryable", "yes"), ("heartbeat", "now"), ("started_at", {}), ("finished_at", [])])
def test_lifecycle_payload_types_are_checkpoint_errors(field, value):
    payload = checkpoint_fixture().to_dict(); payload["lifecycle"]["pending"][field] = value
    with pytest.raises(CheckpointError): Checkpoint.from_dict(payload)


@pytest.mark.parametrize("where", [("wave",), ("tasks", "pending"), ("lifecycle", "pending"), ("reports",), ("evidence",), ("blockers",)])
def test_nan_is_rejected_anywhere_in_payload(where):
    payload = checkpoint_fixture().to_dict(); cursor = payload
    for part in where[:-1]: cursor = cursor[part]
    cursor[where[-1]] = math.nan
    with pytest.raises(CheckpointError): Checkpoint.from_dict(payload)


@pytest.mark.parametrize("bad_id", [1, ""])
def test_non_string_or_empty_ids_are_rejected(bad_id):
    payload = checkpoint_fixture().to_dict(); payload["tasks"] = {bad_id: {"id": bad_id}}
    with pytest.raises(CheckpointError): Checkpoint.from_dict(payload)


def test_task_record_id_must_match_task_mapping_key():
    payload = checkpoint_fixture().to_dict()
    payload["tasks"]["pending"]["id"] = "other"

    with pytest.raises(CheckpointError, match=r"^tasks\.pending\.id inconsistente$"):
        Checkpoint.from_dict(payload)


def test_skipped_tasks_are_not_resumed():
    checkpoint = Checkpoint.create("f", 1, tasks={"skip": {"id": "skip"}}, lifecycle={"skip": lifecycle("skip", "skipped", reason="not needed")})
    assert checkpoint.resume_tasks() == []


def test_retry_api_honors_retryable_flag():
    checkpoint = Checkpoint.create("f", 1, tasks={"t": {"id": "t"}}, lifecycle={"t": lifecycle("t", "failed", attempt=1, max_attempts=2, retryable=False)})
    with pytest.raises(RetryExhausted, match="não é retryable"):
        checkpoint.retry_task("t")
