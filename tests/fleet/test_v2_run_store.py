from __future__ import annotations

import hashlib
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from test_run_store import PLAN, _complete_report
from pd_fleet.run_store import FleetRunStore, LeaseError
from pd_fleet.run_store import RunStoreError


def test_claim_use_commit_rejects_stale_generation_or_lease_without_corruption(
    tmp_path: Path,
):
    """M-04 evidence: renewing fences the old claim before commit, atomically."""
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")

    old_token = store.claim("run", "a", "owner")
    store.use("run", "a", old_token, "owner")
    renewed_token = store.renew("run", "a", old_token, "owner")
    state_before_stale_commit = store.load("run")
    snapshot_before_stale_commit = (tmp_path / "run" / "snapshot.json").read_bytes()
    snapshot_digest = hashlib.sha256(snapshot_before_stale_commit).hexdigest()

    with pytest.raises(LeaseError, match="stale or expired lease"):
        store.commit("run", "a", old_token, "owner", _complete_report())

    assert store.load("run") == state_before_stale_commit
    assert (tmp_path / "run" / "snapshot.json").read_bytes() == snapshot_before_stale_commit
    assert hashlib.sha256(
        (tmp_path / "run" / "snapshot.json").read_bytes()
    ).hexdigest() == snapshot_digest
    assert store.query("run", "events") == state_before_stale_commit["events"]
    assert store.query("run", "reports") == state_before_stale_commit["reports"]
    assert store.load("run")["leases"]["a"]["lease_id"] == renewed_token["lease_id"]


@pytest.mark.parametrize("event", [{1: "bad"}, {"nested": {1: "bad"}}])
def test_append_event_rejects_non_string_keys_without_mutation(tmp_path: Path, event):
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")
    before = store.load("run")
    with pytest.raises(RunStoreError, match="mapping keys must be strings"):
        store.append_event("run", event, "owner")
    assert store.load("run") == before


def test_append_event_rejects_cycles_with_stable_error(tmp_path: Path):
    event = {}
    event["self"] = event
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")
    with pytest.raises(RunStoreError, match="payload contains a cycle"):
        store.append_event("run", event, "owner")


def test_claim_rejects_unknown_task_and_nan_lease(tmp_path: Path):
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")
    with pytest.raises(RunStoreError, match="unknown task id"):
        store.claim("run", "unknown", "owner")
    with pytest.raises(LeaseError, match="lease duration must be positive"):
        store.claim("run", "a", "owner", lease_seconds=float("nan"))


def test_claim_expiry_is_based_on_time_sampled_under_store_lock(tmp_path: Path, monkeypatch):
    now = ["2026-01-01T00:00:00.000000Z"]
    store = FleetRunStore(tmp_path, clock=lambda: now[0])
    store.create("run", PLAN, "owner")
    original_guard = store._guard

    @contextmanager
    def advancing_guard():
        with original_guard():
            # Simulate waiting for another writer after claim() starts but
            # before its mutation callback gets the lock.
            now[0] = "2026-01-01T00:00:10.000000Z"
            yield

    monkeypatch.setattr(store, "_guard", advancing_guard)
    token = store.claim("run", "a", "owner", lease_seconds=5)

    assert token["expires_at"] == "2026-01-01T00:00:15.000000Z"
    assert store.load("run")["leases"]["a"]["expires_at"] == token["expires_at"]


def test_claim_many_refuses_task_committed_terminal_under_store_lock(tmp_path: Path):
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")
    token = store.claim("run", "a", "owner")
    store.commit("run", "a", token, "owner", _complete_report())
    before = store.load("run")

    with pytest.raises(RunStoreError, match="terminal task"):
        store.claim_many("run", ["a"], "owner", max_parallel=1)

    assert store.load("run") == before


@pytest.mark.parametrize("selector_kind", ["positional", "keyword", "legacy"])
def test_claim_many_selector_supports_now_signatures(tmp_path: Path, selector_kind: str):
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")
    seen = []

    if selector_kind == "positional":
        def select(state, available, capacity, now, /):
            seen.append(now)
            return available[:capacity]
    elif selector_kind == "keyword":
        def select(state, available, capacity, *, now):
            seen.append(now)
            return available[:capacity]
    else:
        def select(state, available, capacity):
            return available[:capacity]

    claimed = store.claim_many(
        "run", ["a"], "owner", max_parallel=1, select=select,
    )

    assert [token["task_id"] for token in claimed] == ["a"]
    if selector_kind != "legacy":
        assert len(seen) == 1
        assert seen[0] < claimed[0]["expires_at"]


def test_claim_many_isolates_selector_mutations_from_persisted_state(tmp_path: Path):
    store = FleetRunStore(tmp_path)
    store.create("run", PLAN, "owner")

    def hostile_select(state, available, capacity):
        state["metrics"]["hostile"] = {"persist": True}
        state["leases"]["injected"] = {
            "owner": "attacker", "lease_id": "fake", "expires_at": "2999-01-01T00:00:00Z",
            "generation": 999,
        }
        state["tasks"][available[0]] = {"status": "failed"}
        available.append("injected")
        return [available[0]]

    claimed = store.claim_many(
        "run", ["a"], "owner", max_parallel=1, select=hostile_select,
    )

    state = store.load("run")
    assert [token["task_id"] for token in claimed] == ["a"]
    assert "hostile" not in state["metrics"]
    assert set(state["leases"]) == {"a"}
    assert state["tasks"] == {}


def test_claim_many_persists_expired_reclaim_when_selector_returns_empty(
    tmp_path: Path,
):
    now = ["2026-01-01T00:00:00Z"]
    store = FleetRunStore(tmp_path, clock=lambda: now[0])
    store.create("run", PLAN, "owner")
    expired = store.claim("run", "a", "owner", lease_seconds=1)
    before = store.load("run")
    now[0] = "2026-01-01T00:00:02Z"

    assert store.claim_many(
        "run", ["a"], "owner", max_parallel=1,
        select=lambda state, available, capacity: [],
    ) == []

    state = store.load("run")
    assert state["leases"] == {}
    assert state["generation"] == before["generation"] + 1
    assert state["updated_at"] == now[0]
    assert expired["lease_id"] not in {
        lease.get("lease_id") for lease in state["leases"].values()
    }


def test_unrelated_event_does_not_fence_surviving_lease(tmp_path: Path):
    plan = {"schema_version": "pd-fleet-plan:v2", "tasks": [{"id": "a"}, {"id": "b"}]}
    store = FleetRunStore(tmp_path)
    store.create("run", plan, "owner")
    token_a = store.claim("run", "a", "owner")
    token_b = store.claim("run", "b", "owner")
    store.append_event("run", {"event_id": "note"}, "owner")
    store.use("run", "a", token_a, "owner")
    renewed_b = store.renew("run", "b", token_b, "owner")
    with pytest.raises(LeaseError):
        store.use("run", "b", token_b, "owner")
    store.use("run", "a", token_a, "owner")
    assert renewed_b["lease_id"] != token_b["lease_id"]
