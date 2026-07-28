from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.run_store import FleetRunStore, LeaseError
from pd_fleet.scheduler import CapacityExceeded, LeaseScheduler, OwnershipConflict, SchedulerError

PLAN = {"schema_version": "pd-fleet-plan:v2", "tasks": [
    {"id": "b", "depends_on": [], "allowed_paths": ["src/b.py"]},
    {"id": "a", "depends_on": [], "allowed_paths": ["src/a.py"]},
    {"id": "child", "depends_on": ["a"], "allowed_paths": ["src/c.py"]},
]}


def test_ready_ids_are_sorted_and_dependencies_are_barriers(tmp_path: Path):
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner", initial={"tasks": {"a": {"status": "completed"}}})
    scheduler = LeaseScheduler(store, "run", "owner", max_parallel=2)
    assert scheduler.ready_ids() == ["b", "child"]


@pytest.mark.parametrize("status", ["completed", "failed", "blocked", "orphaned"])
def test_malformed_terminal_dependency_blocks_valid_sibling_before_claim(tmp_path: Path, status: str):
    plan = {"schema_version": "pd-fleet-plan:v2", "tasks": [
        {"id": "valid", "depends_on": [], "allowed_paths": ["src/valid.py"]},
        {"id": "terminal", "status": status, "depends_on": {"malformed": True},
         "allowed_paths": ["src/terminal.py"]},
    ]}
    store = FleetRunStore(tmp_path)
    store.create("run", plan, "owner")
    scheduler = LeaseScheduler(store, "run", "owner")

    with pytest.raises(SchedulerError, match="task dependencies must be a list"):
        scheduler.claim("worker", limit=1)

    assert store.load("run")["leases"] == {}


@pytest.mark.parametrize("dependency", [["nested"], {"nested": True}, 42, None])
def test_non_string_dependency_elements_fail_closed_before_claim(tmp_path: Path, dependency):
    plan = {"schema_version": "pd-fleet-plan:v2", "tasks": [
        {"id": "blocked", "depends_on": [dependency], "allowed_paths": ["src/blocked.py"]},
    ]}
    store = FleetRunStore(tmp_path)
    store.create("run", plan, "owner")
    scheduler = LeaseScheduler(store, "run", "owner")

    with pytest.raises(SchedulerError, match="dependency elements must be exact strings"):
        scheduler.claim("worker", limit=1)

    assert store.load("run")["leases"] == {}


def test_claim_rechecks_dependency_barrier_when_ready_ids_is_stale(tmp_path: Path, monkeypatch):
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")
    scheduler = LeaseScheduler(store, "run", "owner", max_parallel=1)
    monkeypatch.setattr(scheduler, "ready_ids", lambda: ["child"])

    assert scheduler.claim("worker", limit=1) == []
    assert store.load("run")["leases"] == {}


def test_claim_can_select_dependency_ready_in_locked_snapshot(tmp_path: Path, monkeypatch):
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")
    scheduler = LeaseScheduler(store, "run", "owner", max_parallel=1)
    monkeypatch.setattr(scheduler, "ready_ids", lambda: ["child"])

    original_claim_many = store.claim_many

    def complete_dependency_then_claim(*args, **kwargs):
        store._mutate("run", "owner", None, lambda state: state["tasks"].update({"a": {"status": "completed"}}))
        return original_claim_many(*args, **kwargs)

    monkeypatch.setattr(store, "claim_many", complete_dependency_then_claim)
    claimed = scheduler.claim("worker", limit=1)

    assert [token["task_id"] for token in claimed] == ["child"]


def test_claims_are_bounded_and_release_allows_reuse(tmp_path: Path):
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")
    scheduler = LeaseScheduler(store, "run", "owner", max_parallel=2)
    tokens = scheduler.claim("worker", limit=2)
    assert [token["task_id"] for token in tokens] == ["a", "b"]
    with pytest.raises(CapacityExceeded):
        scheduler.claim("worker", limit=1)
    scheduler.release(tokens[1])
    assert scheduler.claim("worker", limit=1)[0]["task_id"] == "b"


def test_claim_limit_above_max_parallel_is_stable_capacity_error(tmp_path: Path):
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")
    scheduler = LeaseScheduler(store, "run", "owner", max_parallel=2)
    before = store.load("run")

    with pytest.raises(CapacityExceeded, match="bounded capacity exceeded"):
        scheduler.claim("worker", limit=3)

    assert store.load("run") == before


def test_expired_lease_path_is_reusable_but_live_lease_still_blocks(tmp_path: Path):
    now = ["2026-01-01T00:00:00Z"]
    clock = lambda: now[0]
    plan = {"schema_version": "pd-fleet-plan:v2", "tasks": [
        {"id": "a", "allowed_paths": ["src/shared.py"]},
        {"id": "b", "allowed_paths": ["src/shared.py"]},
        {"id": "c", "allowed_paths": ["src/shared.py"]},
    ]}
    store = FleetRunStore(tmp_path, clock=clock)
    store.create("run", plan, "owner")
    scheduler = LeaseScheduler(store, "run", "owner", max_parallel=2, clock=clock)

    expired = scheduler.claim("w", limit=1, lease_seconds=1)[0]
    now[0] = "2026-01-01T00:00:02Z"
    replacement = scheduler.claim("w", limit=1, lease_seconds=10)[0]

    assert replacement["task_id"] == "b"
    assert store.load("run")["leases"] == {
        "b": {
            "owner": "owner",
            "lease_id": replacement["lease_id"],
            "expires_at": replacement["expires_at"],
            "generation": replacement["generation"],
        }
    }
    assert expired["lease_id"] != replacement["lease_id"]
    with pytest.raises(OwnershipConflict):
        scheduler.claim("w", limit=1)


def test_overlapping_paths_are_rejected(tmp_path: Path):
    plan = {"schema_version": "pd-fleet-plan:v2", "tasks": [
        {"id": "a", "allowed_paths": ["src"]},
        {"id": "b", "allowed_paths": ["src/file.py"]},
    ]}
    store = FleetRunStore(tmp_path)
    store.create("run", plan, "owner")
    scheduler = LeaseScheduler(store, "run", "owner", max_parallel=2)
    assert scheduler.claim("w", limit=1)[0]["task_id"] == "a"
    with pytest.raises(OwnershipConflict):
        scheduler.claim("w", limit=1)


def test_two_workers_cannot_claim_same_task(tmp_path: Path):
    store = FleetRunStore(tmp_path)
    store.create("run", {"schema_version": "pd-fleet-plan:v2", "tasks": [{"id": "only"}]}, "owner")
    schedulers = [LeaseScheduler(store, "run", "owner", max_parallel=1) for _ in range(2)]
    barrier = threading.Barrier(2)
    results: list[list[dict]] = []
    def worker(scheduler):
        barrier.wait()
        try:
            results.append(scheduler.claim("worker", limit=1))
        except CapacityExceeded:
            # The loser of the atomic claim race has no ready work left.
            results.append([])
    threads = [threading.Thread(target=worker, args=(s,)) for s in schedulers]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sum(bool(result) for result in results) == 1
    assert len(store.load("run")["leases"]) == 1


def test_renew_fences_old_token_and_stale_recovery_is_fail_closed(tmp_path: Path):
    now = ["2026-01-01T00:00:00Z"]
    clock = lambda: now[0]
    store = FleetRunStore(tmp_path, clock=clock)
    store.create("run", {"schema_version": "pd-fleet-plan:v2", "tasks": [{"id": "a"}]}, "owner")
    scheduler = LeaseScheduler(store, "run", "owner", clock=clock)
    old = scheduler.claim("w", lease_seconds=1)[0]
    now[0] = "2026-01-01T00:00:02Z"
    assert scheduler.recover_stale() == ["a"]
    with pytest.raises(LeaseError):
        scheduler.renew(old)
    fresh = scheduler.claim("w", lease_seconds=10)[0]
    renewed = scheduler.renew(fresh)
    assert renewed["lease_id"] != fresh["lease_id"]
    with pytest.raises(LeaseError):
        store.use("run", "a", fresh, "owner")


def test_release_and_event_preserve_unrelated_lease(tmp_path: Path):
    plan = {"schema_version": "pd-fleet-plan:v2", "tasks": [{"id": "a"}, {"id": "b"}]}
    store = FleetRunStore(tmp_path)
    store.create("run", plan, "owner")
    sched = LeaseScheduler(store, "run", "owner", max_parallel=2)
    token_a, token_b = sched.claim("worker", limit=2)
    sched.release(token_b)
    store.append_event("run", {"event_id": "after-release"}, "owner")
    store.use("run", "a", token_a, "owner")
