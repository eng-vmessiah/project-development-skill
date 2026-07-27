"""E4 tests for the supervisor's read-only event-diagnostics facade."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.event_diagnostics import EventDiagnosticsReport, diagnose_event_log  # noqa: E402
from pd_fleet.events import EventError, EventLog, FleetEvent, MAX_QUERY  # noqa: E402
from pd_fleet.supervisor import FleetSupervisor  # noqa: E402


STAMP = "2026-01-01T00:00:00+00:00"


def event(sequence: int, *, epoch: int = 3) -> FleetEvent:
    return FleetEvent(
        event_id=f"event-{sequence}",
        run_id="run-1",
        task_id="task-1",
        kind="lifecycle.transition",
        ordering_key="task-1",
        sequence=sequence,
        owner_epoch=epoch,
        payload={"from": "pending", "to": "ready"},
        created_at=STAMP,
    )


def populated_log(tmp_path: Path) -> EventLog:
    log = EventLog(tmp_path, "run-1", owner_epoch=3)
    log.append(event(1))
    return log


def test_facade_returns_same_report_content_and_does_not_dispatch(tmp_path: Path) -> None:
    log = populated_log(tmp_path)
    supervisor = FleetSupervisor()
    before_dispatch = supervisor.dispatch_count

    report = supervisor.diagnose_events(log, active_owner_epoch=3)
    direct = diagnose_event_log(log, active_owner_epoch=3)

    assert isinstance(report, EventDiagnosticsReport)
    assert report == direct
    assert report.to_dict() == {
        "checkpoint_count": 0,
        "event_count": 1,
        "first_sequence": 1,
        "last_sequence": 1,
        "reasons": [],
        "sequence_gaps": [],
        "status": "healthy",
        "task_states": {"task-1": "ready"},
        "transition_count": 1,
    }
    assert supervisor.dispatch_count == before_dispatch


def test_missing_log_is_read_only_and_does_not_create_directory(tmp_path: Path) -> None:
    log = EventLog(tmp_path, "missing", owner_epoch=3)
    supervisor = FleetSupervisor()
    assert not (tmp_path / "missing").exists()

    report = supervisor.diagnose_events(log)

    assert report.status == "unknown"
    assert not (tmp_path / "missing").exists()


def test_owner_and_limit_validation_fail_closed(tmp_path: Path) -> None:
    log = EventLog(tmp_path, "run-1", owner_epoch=3)
    supervisor = FleetSupervisor()
    for owner in (2, -1, True, "3"):
        with pytest.raises((EventError, ValueError)):
            supervisor.diagnose_events(log, active_owner_epoch=owner)
    for limit in (0, MAX_QUERY + 1, True, 1.0, "1"):
        with pytest.raises((EventError, ValueError)):
            supervisor.diagnose_events(log, limit=limit)
    with pytest.raises(TypeError):
        supervisor.diagnose_events(object())  # type: ignore[arg-type]
    assert not (tmp_path / "run-1").exists()


def test_event_bytes_and_mtime_are_unchanged(tmp_path: Path) -> None:
    log = populated_log(tmp_path)
    path = tmp_path / "run-1" / "events.jsonl"
    before_bytes = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns

    log_result = FleetSupervisor().diagnose_events(log)

    assert log_result.event_count == 1
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_mtime


def test_report_is_immutable_and_detached(tmp_path: Path) -> None:
    log = populated_log(tmp_path)
    report = FleetSupervisor().diagnose_events(log)

    with pytest.raises((AttributeError, TypeError)):
        report.status = "blocked"  # type: ignore[misc]
    with pytest.raises(TypeError):
        report.task_states["task-2"] = "ready"  # type: ignore[index]
    exported = report.to_dict()
    exported["task_states"]["task-1"] = "pending"
    exported["reasons"].append("sequence_gap")
    assert report.task_states["task-1"] == "ready"
    assert report.reasons == ()


def test_facade_has_no_forbidden_integration() -> None:
    source = Path(__file__).parents[2].joinpath("scripts/pd_fleet/supervisor.py").read_text()
    assert "subprocess" not in source
    assert "requests" not in source
    assert "urllib" not in source
    assert "dispatch(" not in source
    assert "EventLog.append" not in source
    assert "TaskLifecycle" not in source
    assert "Checkpoint" not in source
