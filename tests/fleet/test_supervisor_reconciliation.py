"""E7A tests for the read-only supervisor reconciliation facade."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.events import EventError, EventLog, FleetEvent, MAX_QUERY  # noqa: E402
from pd_fleet.run_event_reconciliation import (  # noqa: E402
    RunEventReconciliationReport,
    reconcile_run_events,
)
from pd_fleet.run_store import CorruptSnapshotError, FleetRunStore  # noqa: E402
from pd_fleet.supervisor import FleetSupervisor  # noqa: E402


STAMP = "2026-01-01T00:00:00+00:00"


def event(sequence: int, *, run_id: str = "run-1", epoch: int = 7) -> FleetEvent:
    return FleetEvent(
        event_id=f"event-{sequence}", run_id=run_id, kind="test.event",
        ordering_key=f"event-{sequence}", sequence=sequence,
        owner_epoch=epoch, payload={}, created_at=STAMP,
    )


def sources(tmp_path: Path, *, snapshot: bool = True, log: bool = True):
    store = FleetRunStore(tmp_path / "store")
    event_log = EventLog(tmp_path / "events", "run-1", owner_epoch=7)
    if snapshot:
        store.create("run-1", {"schema_version": "pd-fleet-plan:v2", "tasks": []}, "owner-1")
    if log:
        if snapshot:
            store.append_event("run-1", {"event_id": "event-1", "ordering_key": "event-1"}, "owner-1")
        event_log.append(event(1))
    return store, event_log


def assert_facade_matches_direct(store, event_log, *, run_id="run-1", limit=MAX_QUERY):
    supervisor = FleetSupervisor()
    try:
        expected = reconcile_run_events(store, event_log, run_id=run_id, limit=limit)
    except Exception as direct_error:
        with pytest.raises(type(direct_error)) as facade_error:
            supervisor.reconcile_events(store, event_log, run_id=run_id, limit=limit)
        assert str(facade_error.value) == str(direct_error)
    else:
        actual = supervisor.reconcile_events(store, event_log, run_id=run_id, limit=limit)
        assert isinstance(actual, RunEventReconciliationReport)
        assert actual == expected
        assert actual.to_dict() == expected.to_dict()


@pytest.mark.parametrize("kind", ["consistent", "divergent", "missing"])
def test_facade_is_exact_direct_equivalent(tmp_path: Path, kind: str) -> None:
    if kind == "consistent":
        store, event_log = sources(tmp_path)
    elif kind == "divergent":
        store, event_log = sources(tmp_path)
        store.append_event("run-1", {"event_id": "event-2", "ordering_key": "event-2"}, "owner-1")
    else:
        store, event_log = sources(tmp_path, snapshot=False, log=False)
    assert_facade_matches_direct(store, event_log)


def test_facade_propagates_corrupt_source_errors_exactly(tmp_path: Path) -> None:
    store, event_log = sources(tmp_path)
    snapshot = tmp_path / "store" / "run-1" / "snapshot.json"
    original_snapshot = snapshot.read_bytes()
    backup = snapshot.with_name("snapshot.json.bak")
    original_backup = backup.read_bytes()
    snapshot.write_text("not-json", encoding="utf-8")
    backup.write_text("not-json", encoding="utf-8")
    with pytest.raises(CorruptSnapshotError):
        reconcile_run_events(store, event_log, run_id="run-1")
    assert_facade_matches_direct(store, event_log)

    snapshot.write_bytes(original_snapshot)
    backup.write_bytes(original_backup)
    event_path = tmp_path / "events" / "run-1" / "events.jsonl"
    event_path.write_bytes(event_path.read_bytes().replace(b"event-1", b"broken-1", 1))
    with pytest.raises(EventError):
        reconcile_run_events(store, event_log, run_id="run-1")
    assert_facade_matches_direct(store, event_log)


def test_facade_is_frozen_detached_and_preserves_sources(tmp_path: Path) -> None:
    store, event_log = sources(tmp_path)
    event_path = tmp_path / "events" / "run-1" / "events.jsonl"
    snapshot_path = tmp_path / "store" / "run-1" / "snapshot.json"
    before = {
        "event": (event_path.read_bytes(), event_path.stat().st_mtime_ns),
        "snapshot": (snapshot_path.read_bytes(), snapshot_path.stat().st_mtime_ns),
    }
    supervisor = FleetSupervisor()
    report = supervisor.reconcile_events(store, event_log, run_id="run-1")
    assert supervisor.dispatch_count == 0
    with pytest.raises((AttributeError, TypeError)):
        report.status = "degraded"  # type: ignore[misc]
    exported = report.to_dict()
    exported["reasons"].append("event_count_mismatch")
    assert report.reasons == ()
    assert (event_path.read_bytes(), event_path.stat().st_mtime_ns) == before["event"]
    assert (snapshot_path.read_bytes(), snapshot_path.stat().st_mtime_ns) == before["snapshot"]
    assert not (tmp_path / "STATE").exists()


def test_invalid_inputs_propagate_and_missing_inputs_create_nothing(tmp_path: Path) -> None:
    store, event_log = sources(tmp_path, snapshot=False, log=False)
    before = {path: (path.exists(), path.stat().st_mtime_ns if path.exists() else None)
              for path in (tmp_path / "store", tmp_path / "events", tmp_path / "STATE")}
    supervisor = FleetSupervisor()
    for args, kwargs in [
        ((object(), event_log), {"run_id": "run-1"}),
        ((store, object()), {"run_id": "run-1"}),
    ]:
        with pytest.raises(TypeError):
            supervisor.reconcile_events(*args, **kwargs)
    for run_id, limit in [("../bad", MAX_QUERY), ("run-1", 0), ("run-1", MAX_QUERY + 1)]:
        with pytest.raises((TypeError, ValueError)):
            supervisor.reconcile_events(store, event_log, run_id=run_id, limit=limit)
    assert {path: (path.exists(), path.stat().st_mtime_ns if path.exists() else None)
            for path in before} == before
