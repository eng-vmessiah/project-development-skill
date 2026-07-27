from __future__ import annotations

import inspect
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.checkpoint import Checkpoint
from pd_fleet.events import EventError, EventLog, FleetEvent
from pd_fleet.lifecycle import LifecycleState, TaskLifecycle
from pd_fleet.lifecycle_events import LifecycleEventRecorder
from pd_fleet.event_diagnostics import EventDiagnosticsReport, diagnose_event_log

STAMP = "2026-01-01T00:00:00+00:00"


def make_log(tmp_path, epoch=3):
    return EventLog(tmp_path, "run-1", owner_epoch=epoch)


def test_missing_log_is_unknown_and_read_only(tmp_path):
    log = make_log(tmp_path)
    before = list(tmp_path.iterdir()) if tmp_path.exists() else []
    report = diagnose_event_log(log)
    assert report.status == "unknown"
    assert report.event_count == report.transition_count == report.checkpoint_count == 0
    assert report.first_sequence is report.last_sequence is None
    assert report.sequence_gaps == () and report.task_states == {} and report.reasons == ()
    assert list(tmp_path.iterdir()) == before if tmp_path.exists() else True


def test_valid_transition_and_checkpoint_are_healthy_and_detached(tmp_path):
    log = make_log(tmp_path)
    recorder = LifecycleEventRecorder(log)
    recorder.record_transition(TaskLifecycle("task-1"), LifecycleState.PENDING, LifecycleState.READY, 1, created_at=STAMP)
    recorder.record_checkpoint(Checkpoint.create("feature-x", 1, created_at=STAMP), 2, created_at=STAMP)
    report = diagnose_event_log(log, active_owner_epoch=3)
    assert report.status == "healthy"
    assert (report.event_count, report.transition_count, report.checkpoint_count) == (2, 1, 1)
    assert (report.first_sequence, report.last_sequence, report.task_states["task-1"]) == (1, 2, "ready")
    assert report.task_states is not log.replay()[0].payload
    exported = report.to_dict()
    assert list(exported) == sorted(exported)
    exported["task_states"]["task-1"] = "tampered"
    assert report.task_states["task-1"] == "ready"
    with pytest.raises(TypeError):
        report.task_states["task-1"] = "x"


def test_owner_mismatch_fails_closed_and_does_not_create_log(tmp_path):
    log = make_log(tmp_path, epoch=8)
    with pytest.raises(EventError):
        diagnose_event_log(log, active_owner_epoch=7)
    assert not (tmp_path / "run-1").exists()


def test_diagnosis_does_not_modify_log_bytes_or_mtime(tmp_path):
    log = make_log(tmp_path)
    LifecycleEventRecorder(log).record_transition(
        TaskLifecycle("task-1"), "pending", "ready", 1, created_at=STAMP
    )
    path = tmp_path / "run-1" / "events.jsonl"
    before_bytes, before_mtime = path.read_bytes(), path.stat().st_mtime_ns
    diagnose_event_log(log)
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_mtime


def test_tampered_event_fails_closed_without_exporting_payload(tmp_path):
    log = make_log(tmp_path)
    LifecycleEventRecorder(log).record_transition(
        TaskLifecycle("task-1"), "pending", "ready", 1, created_at=STAMP
    )
    path = tmp_path / "run-1" / "events.jsonl"
    path.write_bytes(path.read_bytes().replace(b'\"ready\"', b'\"bogus\"', 1))
    with pytest.raises(EventError):
        diagnose_event_log(log)


def test_sequence_gaps_are_bounded_and_sorted(tmp_path):
    log = make_log(tmp_path)
    recorder = LifecycleEventRecorder(log)
    recorder.record_transition(TaskLifecycle("a"), "pending", "ready", 1, created_at=STAMP)
    recorder.record_checkpoint(Checkpoint.create("f", 1, created_at=STAMP), 40, created_at=STAMP)
    report = diagnose_event_log(log)
    assert report.status == "degraded"
    assert report.sequence_gaps == tuple(range(2, 34))
    assert "sequence_gap" in report.reasons


def test_invalid_or_inconsistent_transition_is_degraded_without_raw_reason(tmp_path):
    log = make_log(tmp_path)
    recorder = LifecycleEventRecorder(log)
    recorder.record_transition(TaskLifecycle("a"), "pending", "ready", 1, created_at=STAMP)
    # Build a valid envelope with a semantically inconsistent transition.
    log.append(FleetEvent(event_id="manual-2", run_id="run-1", task_id="a", kind="lifecycle.transition",
                          ordering_key="a", sequence=2, owner_epoch=3,
                          payload={"from": "pending", "to": "running"}, created_at=STAMP))
    report = diagnose_event_log(log)
    assert report.status == "degraded"
    assert report.task_states["a"] == "running"
    assert report.reasons == ("inconsistent_transition",)
    assert all("pending" not in reason for reason in report.reasons)


def test_unknown_kind_counted_but_ignored(tmp_path):
    log = make_log(tmp_path)
    log.append(FleetEvent(event_id="other-1", run_id="run-1", kind="other.kind", ordering_key="x",
                          sequence=1, owner_epoch=3, payload={}, created_at=STAMP))
    report = diagnose_event_log(log)
    assert report.status == "healthy" and report.event_count == 1
    assert report.transition_count == report.checkpoint_count == 0


def test_non_integer_sequence_is_degraded_without_inventing_gap(tmp_path):
    log = make_log(tmp_path)
    log.append(FleetEvent(event_id="other-1", run_id="run-1", kind="other.kind", ordering_key="x",
                          sequence=1.5, owner_epoch=3, payload={}, created_at=STAMP))
    report = diagnose_event_log(log)
    assert report.status == "degraded" and report.sequence_gaps == ()
    assert "non_integer_sequence" in report.reasons


def test_bounded_query_and_no_forbidden_integration():
    source = inspect.getsource(sys.modules["pd_fleet.event_diagnostics"])
    for forbidden in ("orchestrator", "subprocess", "requests", "socket", "pd.py"):
        assert forbidden not in source
    assert "replay(" in source


def test_report_is_frozen():
    report = EventDiagnosticsReport("unknown", 0, 0, 0, None, None, (), {}, ())
    with pytest.raises((AttributeError, TypeError)):
        report.status = "healthy"


def test_replay_order_anomalies_degrade_without_gaps(tmp_path, monkeypatch):
    log = make_log(tmp_path)
    events = tuple(FleetEvent(event_id=f"e-{index}", run_id="run-1", kind="other.kind", ordering_key="x",
                              sequence=sequence, owner_epoch=3, payload={}, created_at=STAMP)
                   for index, sequence in enumerate((3, 3, 1), 1))
    monkeypatch.setattr(log, "replay", lambda *, limit: events)
    report = diagnose_event_log(log)
    assert report.status == "degraded"
    assert "duplicate_sequence" in report.reasons
    assert "non_monotonic_sequence" in report.reasons
    assert report.sequence_gaps == ()


def test_hostile_transition_mapping_is_fixed_reason(tmp_path):
    class HostileMapping(dict):
        def get(self, key, default=None):
            raise RuntimeError("SECRET_PAYLOAD_TEXT")

    log = make_log(tmp_path)
    event = FleetEvent(event_id="e-1", run_id="run-1", task_id="task-1",
                       kind="lifecycle.transition", ordering_key="task-1", sequence=1,
                       owner_epoch=3, payload={}, created_at=STAMP)
    object.__setattr__(event, "payload", HostileMapping())
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(log, "replay", lambda *, limit: (event,))
    try:
        report = diagnose_event_log(log)
    finally:
        monkeypatch.undo()
    assert report.reasons == ("malformed_transition",)
    assert "SECRET_PAYLOAD_TEXT" not in repr(report.to_dict())


@pytest.mark.parametrize("kwargs", [
    {"status": "healthy", "event_count": True},
    {"status": "healthy", "event_count": 1001},
    {"status": "healthy", "event_count": 1, "transition_count": 2},
    {"status": "healthy", "event_count": 1, "first_sequence": float("nan")},
    {"status": "healthy", "event_count": 0, "sequence_gaps": (True,)},
    {"status": "healthy", "event_count": 0, "task_states": {"bad id": "ready"}},
    {"status": "healthy", "event_count": 0, "task_states": {"task-1": "SECRET"}},
    {"status": "healthy", "event_count": 0, "reasons": ("raw_secret",)},
])
def test_report_rejects_adversarial_fields(kwargs):
    values = dict(status="healthy", event_count=0, transition_count=0, checkpoint_count=0,
                  first_sequence=None, last_sequence=None, sequence_gaps=(), task_states={}, reasons=())
    values.update(kwargs)
    with pytest.raises(ValueError):
        EventDiagnosticsReport(**values)
