from __future__ import annotations

import json
import os
import threading
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.run_store import (
    FleetRunStore, DuplicateCommitError, GenerationConflictError,
    LeaseError, OwnerMismatchError, PathContainmentError, RunStoreError, CorruptSnapshotError,
)

PLAN = {"schema_version": "pd-fleet-plan:v2", "tasks": [{"id": "a", "path": "/secret/project/a"}], "token": "secret-value"}

def _complete_report():
    return {"status": "completed", "outputs": {"result": "ok"}, "evidence": ["evidence"], "tests": ["pytest"], "validation": {"passed": True}, "decision": "APPROVED", "started_at": "2020-01-01T00:00:00.000000Z", "completed_at": "2020-01-01T00:00:01.000000Z"}


def test_create_load_hash_and_atomic_reload(tmp_path: Path):
    store = FleetRunStore(tmp_path)
    state = store.create("run-1", PLAN, "alice")
    assert state["run_id"] == "run-1" and len(state["plan_hash"]) == 64
    assert store.load("run-1") == state
    assert not list(tmp_path.joinpath("run-1").glob("*.tmp"))


def test_owner_and_generation_cas(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a")
    with pytest.raises(OwnerMismatchError): s.transition("r", "x", "b")
    with pytest.raises(GenerationConflictError): s.transition("r", "x", "a", expected_generation=99)


def test_claim_use_commit_and_duplicate(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a")
    token = s.claim("r", "a", "a")
    s.use("r", "a", token, "a")
    result = s.commit("r", "a", token, "a", _complete_report())
    assert result["reports"]["a"]["status"] == "completed"
    with pytest.raises(DuplicateCommitError): s.commit("r", "a", token, "a", {**_complete_report(), "evidence": ["different"]})


def test_events_are_append_only_and_redacted(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a")
    s.append_event("r", {"task_id": "b", "ordering_key": "002", "secret": "dont-store", "path": "/home/private"}, "a")
    s.append_event("r", {"task_id": "a", "ordering_key": "001"}, "a")
    events = s.query("r", "events")
    assert [e["sequence"] for e in events] == [2, 1]
    assert events[1]["secret"] == "[REDACTED]" and "/home" not in json.dumps(events)


def test_commit_rejects_non_terminal_status_without_mutation(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a"); token = s.claim("r", "a", "a")
    before = s.load("r")
    with pytest.raises(RunStoreError, match="terminal"):
        s.commit("r", "a", token, "a", {"status": "running", "reason": "not terminal"}, status="running")
    assert s.load("r") == before


def test_renew_fences_old_token_and_returns_refreshed_token(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a"); old = s.claim("r", "a", "a")
    fresh = s.renew("r", "a", old, "a")
    assert set(fresh) == {"run_id", "task_id", "lease_id", "generation", "expires_at"}
    assert fresh["lease_id"] != old["lease_id"] and fresh["generation"] != old["generation"]
    with pytest.raises(LeaseError): s.use("r", "a", old, "a")
    s.use("r", "a", fresh, "a")


@pytest.mark.parametrize("artifact", ["snapshot.json", "snapshot.json.bak"])
def test_create_rejects_any_existing_snapshot_artifact(tmp_path: Path, artifact: str):
    s = FleetRunStore(tmp_path)
    run_dir = tmp_path / "r"; run_dir.mkdir()
    (run_dir / artifact).write_text("corrupt", encoding="utf8")
    with pytest.raises(RunStoreError, match="artifact"):
        s.create("r", PLAN, "a")


def test_concurrent_event_query_is_canonical_not_scheduler_completion_order(tmp_path: Path):
    a, b = FleetRunStore(tmp_path), FleetRunStore(tmp_path)
    a.create("r", PLAN, "owner")
    barrier = threading.Barrier(2)
    def add(store, key):
        barrier.wait(); store.append_event("r", {"event_id": key, "ordering_key": key}, "owner")
    ts = [threading.Thread(target=add, args=(a, "b")), threading.Thread(target=add, args=(b, "a"))]
    [t.start() for t in ts]; [t.join() for t in ts]
    events = a.query("r", "events")
    assert [e["ordering_key"] for e in events] == ["a", "b"]
    assert sorted(e["sequence"] for e in events) == [1, 2]


def test_truncated_primary_recovers_backup_and_paths_rejected(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a"); s.transition("r", "running", "a")
    p = tmp_path / "r" / "snapshot.json"; p.write_text("{truncated", encoding="utf8")
    assert s.load("r")["status"] == "created"
    with pytest.raises(PathContainmentError): s.create("../escape", PLAN, "a")


def test_expired_lease_is_rejected_before_commit(tmp_path: Path):
    now = ["2020-01-01T00:00:00.000000Z"]
    def clock(): return now[0]
    s = FleetRunStore(tmp_path, clock=clock); s.create("r", PLAN, "a")
    token = s.claim("r", "a", "a", lease_seconds=1); before = s.load("r")
    now[0] = "2020-01-01T00:00:02.000000Z"
    with pytest.raises(LeaseError): s.commit("r", "a", token, "a", _complete_report())
    assert s.load("r") == before


def test_separate_instances_do_not_lose_updates(tmp_path: Path):
    a, b = FleetRunStore(tmp_path), FleetRunStore(tmp_path)
    a.create("r", PLAN, "owner")
    barrier = threading.Barrier(2)
    def add(store, task):
        barrier.wait(); store.append_event("r", {"task_id": task}, "owner")
    ts = [threading.Thread(target=add, args=(a, "a")), threading.Thread(target=add, args=(b, "b"))]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert [e["sequence"] for e in a.query("r", "events")] == [1, 2]


def test_symlink_lock_is_rejected(tmp_path: Path):
    outside = tmp_path / "outside"; outside.write_text("outside")
    (tmp_path / ".run_store.lock").symlink_to(outside)
    with pytest.raises(Exception): FleetRunStore(tmp_path)


def test_lock_is_regular_and_mode_0600(tmp_path: Path):
    FleetRunStore(tmp_path)
    assert (tmp_path / ".run_store.lock").is_file()
    assert os.stat(tmp_path / ".run_store.lock").st_mode & 0o777 == 0o600


def test_newer_valid_backup_is_selected_when_primary_is_invalid(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a"); s.transition("r", "running", "a")
    primary = tmp_path / "r" / "snapshot.json"; backup = tmp_path / "r" / "snapshot.json.bak"
    data = json.loads(primary.read_text()); data["generation"] = 99; data["event_sequence"] = 0; data["checksum"] = s._checksum(data)
    backup.write_text(json.dumps(data)); primary.write_text("{}")
    loaded = s.load("r")
    assert loaded["status"] == "running" and loaded["generation"] == 99


def test_strict_inputs_and_persistence_failure_has_no_memory_mutation(tmp_path: Path, monkeypatch):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a")
    before = s.load("r")
    monkeypatch.setattr(s, "_write", lambda *args: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError): s.transition("r", "running", "a")
    assert s.load("r") == before
    with pytest.raises(LeaseError): s.claim("r", "a", "a", lease_seconds=0)
    with pytest.raises(Exception): s.transition("r", "bogus", "a")


def test_terminal_report_is_strict_and_does_not_mutate(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a"); token = s.claim("r", "a", "a")
    before = s.load("r")
    with pytest.raises(RunStoreError): s.commit("r", "a", token, "a", {"status": "completed", "outputs": ["ok"]})
    assert s.load("r") == before


def test_checksum_corruption_is_recovered_or_reported(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a"); s.transition("r", "running", "a")
    primary = tmp_path / "r" / "snapshot.json"
    data = json.loads(primary.read_text()); data["status"] = "failed"; primary.write_text(json.dumps(data))
    assert s.load("r")["status"] == "created"
    (tmp_path / "r" / "snapshot.json.bak").write_text(json.dumps(data))
    with pytest.raises(CorruptSnapshotError): s.load("r")


def test_malformed_existing_candidates_are_corruption(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a")
    (tmp_path / "r" / "snapshot.json").write_text("not json")
    (tmp_path / "r" / "snapshot.json.bak").write_text("also not json")
    with pytest.raises(CorruptSnapshotError): s.load("r")


def test_close_and_context_manager_release_lock(tmp_path: Path):
    s = FleetRunStore(tmp_path); s.close(); s.close()
    with pytest.raises(RunStoreError, match="locking unavailable"):
        s.load("r")
    with FleetRunStore(tmp_path) as scoped:
        scoped.create("r", PLAN, "a")
    assert scoped._lock_fd == -1


def test_partial_writes_are_completed(tmp_path: Path, monkeypatch):
    s = FleetRunStore(tmp_path)
    original = os.write
    def partial(fd, data):
        return original(fd, data[: max(1, len(data) // 3)])
    monkeypatch.setattr(os, "write", partial)
    created = s.create("r", PLAN, "a")
    assert s.load("r") == created


def test_fsync_failure_is_normalized_and_temp_cleaned(tmp_path: Path, monkeypatch):
    s = FleetRunStore(tmp_path); s.create("r", PLAN, "a")
    calls = [0]
    original = os.fsync
    def fail_after_file(fd):
        calls[0] += 1
        if calls[0] == 3: raise OSError("directory fsync")
        return original(fd)
    monkeypatch.setattr(os, "fsync", fail_after_file)
    with pytest.raises(RunStoreError): s.transition("r", "running", "a")
    assert not list((tmp_path / "r").glob("snapshot.json.tmp-*"))
    # The replace happened before directory fsync; the failure is reported,
    # while the newly replaced primary remains a valid snapshot.
    assert s.load("r")["status"] == "running"
