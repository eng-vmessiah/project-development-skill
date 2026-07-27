from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.events import EventError, EventLog, FleetEvent, MAX_QUERY
from pd_fleet.run_event_reconciliation import (
    RunEventReconciliationReport,
    reconcile_run_events,
)
from pd_fleet.run_store import CorruptSnapshotError, FleetRunStore, RunNotFoundError


def make_sources(tmp_path):
    store = FleetRunStore(tmp_path / "store")
    store.create("run-1", {"schema_version": "pd-fleet-plan:v2", "tasks": []}, "owner-1")
    log = EventLog(tmp_path / "events", "run-1", owner_epoch=7)
    return store, log


def event(sequence: int, *, run_id: str = "run-1", epoch: int = 7):
    return FleetEvent(
        event_id=f"event-{sequence}", run_id=run_id, kind="test.event",
        ordering_key=f"event-{sequence}", sequence=sequence,
        owner_epoch=epoch, payload={}, created_at="2026-01-01T00:00:00+00:00",
    )


def test_matching_sources_are_consistent_and_detached(tmp_path):
    store, log = make_sources(tmp_path)
    store.append_event("run-1", {"event_id": "event-1", "ordering_key": "event-1"}, "owner-1")
    log.append(event(1))
    report = reconcile_run_events(store, log, run_id="run-1")
    assert report.status == "consistent"
    assert (report.snapshot_status, report.snapshot_generation) == ("created", 1)
    assert (report.store_event_sequence, report.event_log_count, report.event_log_last_sequence) == (1, 1, 1)
    assert report.reasons == ()
    exported = report.to_dict()
    assert list(exported) == sorted(exported)
    exported["reasons"].append("event_count_mismatch")
    assert report.reasons == ()


def test_divergence_has_fixed_bounded_reasons(tmp_path):
    store, log = make_sources(tmp_path)
    store.append_event("run-1", {"event_id": "event-1", "ordering_key": "event-1"}, "owner-1")
    store.append_event("run-1", {"event_id": "event-2", "ordering_key": "event-2"}, "owner-1")
    log.append(event(3))
    report = reconcile_run_events(store, log, run_id="run-1")
    assert report.status == "degraded"
    assert report.reasons == ("event_sequence_mismatch", "event_count_mismatch")


def test_missing_sources_are_unknown_without_creating_anything(tmp_path):
    store = FleetRunStore(tmp_path / "store")
    log = EventLog(tmp_path / "events", "run-1", owner_epoch=7)
    report = reconcile_run_events(store, log, run_id="run-1")
    assert report.status == "unknown" and report.reasons == ()
    assert not (tmp_path / "events" / "run-1").exists()
    with pytest.raises(RunNotFoundError):
        store.load("run-1")


def test_missing_store_with_existing_log_is_degraded_without_mkdir(tmp_path):
    store = FleetRunStore(tmp_path / "store")
    log = EventLog(tmp_path / "events", "run-1", owner_epoch=7)
    log.append(event(1))
    report = reconcile_run_events(store, log, run_id="run-1")
    assert report.status == "degraded" and report.reasons == ("missing_store_snapshot",)
    assert not (tmp_path / "store" / "run-1").exists()


def test_missing_log_with_existing_store_is_degraded(tmp_path):
    store, log = make_sources(tmp_path)
    report = reconcile_run_events(store, log, run_id="run-1")
    assert report.status == "degraded" and report.reasons == ("missing_event_log",)


@pytest.mark.parametrize(
    "store_exists,log_exists,expected_status,expected_reasons",
    [
        (False, False, "unknown", ()),
        (True, False, "degraded", ("missing_event_log",)),
        (False, True, "degraded", ("missing_store_snapshot",)),
        (True, True, "consistent", ()),
    ],
)
def test_reconciliation_distinguishes_empty_existing_sources(
    tmp_path, store_exists, log_exists, expected_status, expected_reasons
):
    store = FleetRunStore(tmp_path / "store")
    log = EventLog(tmp_path / "events", "run-1", owner_epoch=7)
    if store_exists:
        store.create("run-1", {"schema_version": "pd-fleet-plan:v2", "tasks": []}, "owner-1")
    if log_exists:
        log._directory.mkdir(parents=True)
        log._path.write_bytes(b"")

    report = reconcile_run_events(store, log, run_id="run-1")

    assert report.status == expected_status
    assert report.reasons == expected_reasons
    assert report.event_log_count == 0
    assert report.event_log_last_sequence == (0 if log_exists else None)
    assert report.store_event_sequence == (0 if store_exists else None)


def test_existing_empty_log_is_read_only_and_preserves_bounds_and_report_contract(tmp_path):
    store = FleetRunStore(tmp_path / "store")
    log = EventLog(tmp_path / "events", "run-1", owner_epoch=7)
    log._directory.mkdir(parents=True)
    log._path.write_bytes(b"")
    before = (log._path.read_bytes(), log._path.stat().st_mtime_ns, log._path.stat().st_size)

    report = reconcile_run_events(store, log, run_id="run-1", limit=MAX_QUERY)

    assert report == RunEventReconciliationReport(
        "degraded", "run-1", None, None, None, 0, 0, ("missing_store_snapshot",)
    )
    assert (log._path.read_bytes(), log._path.stat().st_mtime_ns, log._path.stat().st_size) == before


@pytest.mark.parametrize("store,log,run_id,limit", [
    (None, EventLog, "run-1", MAX_QUERY),
])
def test_invalid_inputs_fail_closed(store, log, run_id, limit, tmp_path):
    real_store, real_log = make_sources(tmp_path)
    with pytest.raises(TypeError):
        reconcile_run_events(store, real_log, run_id=run_id, limit=limit)
    with pytest.raises(TypeError):
        reconcile_run_events(real_store, object(), run_id=run_id)
    with pytest.raises((TypeError, ValueError)):
        reconcile_run_events(real_store, real_log, run_id=run_id, limit=0)
    with pytest.raises((TypeError, ValueError)):
        reconcile_run_events(real_store, real_log, run_id="../bad")


def test_corruption_raises_and_report_is_frozen_bounded(tmp_path):
    store, log = make_sources(tmp_path)
    snapshot = tmp_path / "store" / "run-1" / "snapshot.json"
    snapshot.write_text("not-json", encoding="utf-8")
    with pytest.raises(CorruptSnapshotError):
        reconcile_run_events(store, log, run_id="run-1")

    report = RunEventReconciliationReport("unknown", "run-1", None, None, None, 0, None, ())
    with pytest.raises((AttributeError, TypeError)):
        report.status = "degraded"
    assert len(report.reasons) <= 6
    assert report.to_dict() == report.to_dict()


def test_corrupt_event_log_fails_closed(tmp_path):
    store, log = make_sources(tmp_path)
    log.append(event(1))
    path = tmp_path / "events" / "run-1" / "events.jsonl"
    path.write_bytes(path.read_bytes().replace(b"event-1", b"broken-1", 1))
    with pytest.raises(EventError):
        reconcile_run_events(store, log, run_id="run-1")
