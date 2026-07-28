import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.checkpoint import (
    Checkpoint, CheckpointError, DurableCheckpointStore, CheckpointV2Store,
    save_checkpoint_v2, load_checkpoint_v2, resume_checkpoint_v2,
)


class _HostileRepr(str):
    def __repr__(self):
        raise AssertionError("repr must not be called")


def cp(status="pending"):
    return Checkpoint.create("demo", 1, tasks={"done":{"id":"done"}, "run":{"id":"run"}}, lifecycle={
        "done":{"task_id":"done", "status":"completed"},
        "run":{"task_id":"run", "status":status, "heartbeat":0, "attempt":1, "max_attempts":3},
    })


def test_v2_save_load_has_sealed_metadata_and_deep_copy(tmp_path):
    store = DurableCheckpointStore(tmp_path)
    value = cp(); saved = store.save("run-1", value, plan_hash="a"*64, generation=2)
    assert saved["schema_version"] == "pd-fleet-checkpoint:v2"
    assert saved["generation"] == 2 and len(saved["checksum"]) == 64
    loaded = store.load("run-1", expected_plan_hash="a"*64, expected_generation=2)
    loaded["checkpoint"]["tasks"]["done"]["x"] = 1
    assert "x" not in value.tasks["done"]


def test_resume_rejects_plan_drift_and_recovers_orphans_without_replay(tmp_path):
    store = DurableCheckpointStore(tmp_path)
    store.save("r", cp("running"), plan_hash="a"*64, generation=1)
    with pytest.raises(CheckpointError, match="plan"):
        store.resume("r", expected_plan_hash="b"*64, now=400, timeout_seconds=300)
    resumed = store.resume("r", expected_plan_hash="a"*64, expected_generation=1, now=400, timeout_seconds=300)
    assert "done" not in resumed["resume_tasks"]
    assert "run" in resumed["resume_tasks"]
    assert resumed["orphaned"] == ["run"]


def test_checksum_schema_and_backup_recovery(tmp_path):
    store = DurableCheckpointStore(tmp_path)
    store.save("r", cp(), plan_hash="a"*64, generation=1)
    store.save("r", cp(), plan_hash="a"*64, generation=2)
    path = tmp_path / "r" / "checkpoint.json"
    data = json.loads(path.read_text()); data["generation"] = 99; path.write_text(json.dumps(data))
    assert store.load("r")["generation"] == 1
    data = json.loads(path.read_text()); assert data["generation"] == 99
    with pytest.raises(CheckpointError):
        store.load("r", expected_generation=2)


def test_faulty_write_is_atomic_and_paths_are_safe(tmp_path):
    store = DurableCheckpointStore(tmp_path)
    store.save("r", cp(), plan_hash="a"*64, generation=1)
    with pytest.raises(OSError):
        store.save("r", cp(), plan_hash="a"*64, generation=2, fault_injector=lambda stage: (_ for _ in ()).throw(OSError("boom")) if stage == "replace" else None)
    assert store.load("r")["generation"] == 1
    with pytest.raises(CheckpointError): store.save("../escape", cp(), plan_hash="a"*64, generation=1)
    (tmp_path / "link").symlink_to(tmp_path / "r", target_is_directory=True)
    with pytest.raises(CheckpointError): store.save("link", cp(), plan_hash="a"*64, generation=1)


def test_concurrent_instances_have_single_generation_winner(tmp_path):
    DurableCheckpointStore(tmp_path).save("r", cp(), plan_hash="a"*64, generation=0)
    def write():
        try:
            return DurableCheckpointStore(tmp_path).save("r", cp(), plan_hash="a"*64, generation=1)
        except CheckpointError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: write(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert DurableCheckpointStore(tmp_path).load("r")["generation"] == 1


def test_generation_cas_and_directory_fsync_fault_are_safe(tmp_path):
    store = DurableCheckpointStore(tmp_path)
    store.save("r", cp(), plan_hash="a"*64, generation=0)
    with pytest.raises(CheckpointError, match="generation"):
        store.save("r", cp(), plan_hash="a"*64, generation=0)
    with pytest.raises(CheckpointError, match="fsync"):
        store.save("r", cp(), plan_hash="a"*64, generation=1,
                   fault_injector=lambda stage: (_ for _ in ()).throw(OSError("dir"))
                   if stage == "directory_fsync" else None)
    assert store.load("r")["generation"] == 1


def test_invalid_plan_hash_and_symlink_candidate_do_not_poison_valid_backup(tmp_path):
    store = DurableCheckpointStore(tmp_path)
    with pytest.raises(CheckpointError):
        store.save("r", cp(), plan_hash="A"*64, generation=0)
    store.save("r", cp(), plan_hash="a"*64, generation=0)
    target = tmp_path / "r" / "checkpoint.json"
    backup = tmp_path / "r" / "checkpoint.json.bak"
    backup.write_text(target.read_text())
    target.unlink(); target.symlink_to(backup)
    assert store.load("r")["generation"] == 0


def test_functional_api_aliases(tmp_path):
    value = cp(); save_checkpoint_v2(tmp_path, "x", value, plan_hash="a"*64, generation=0)
    assert load_checkpoint_v2(tmp_path, "x")["generation"] == 0
    assert isinstance(CheckpointV2Store, type)
    assert "done" not in resume_checkpoint_v2(tmp_path, "x")["resume_tasks"]


@pytest.mark.parametrize("path", [r"\\server\alice\secret.txt", "~/alice/secret"])
def test_v2_checkpoint_redacts_unc_and_tilde_paths_as_a_whole(tmp_path, path):
    value = Checkpoint.create("demo", 1, tasks={"task": {"id": "task", "path": path}})
    saved = DurableCheckpointStore(tmp_path).save("run", value, plan_hash="a" * 64, generation=0)
    redacted = saved["checkpoint"]["tasks"]["task"]["path"]
    assert redacted == "[PATH REDACTED]"
    assert "alice" not in json.dumps(saved, ensure_ascii=False)


def test_checkpoint_invalid_values_never_call_repr():
    cases = [
        {"schema_version": object()},
        {"lifecycle": {"run": {"task_id": "run", "status": _HostileRepr("secret\x1bstatus")}}},
    ]
    for kwargs in cases:
        with pytest.raises(CheckpointError) as exc:
            Checkpoint(feature="demo", wave=1, tasks={"run": {"id": "run"}}, **kwargs)
        assert "repr must not be called" not in str(exc.value)
        assert "secret" not in str(exc.value)


def test_checkpoint_diagnostic_escapes_controls_in_valid_string_boundary():
    with pytest.raises(CheckpointError) as exc:
        Checkpoint(feature="demo", wave=1, tasks={"run": {"id": "run"}},
                   lifecycle={"run": {"task_id": "run", "status": "bad\x1bstatus"}})
    assert "\\x1b" in str(exc.value)
    assert "\x1b" not in str(exc.value)
