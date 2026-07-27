"""RED tests for the read-only FleetSupervisor facade."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.supervision import HealthSignal, HealthSnapshot, SupervisorDiagnosis  # noqa: E402
from pd_fleet.supervisor import FleetSupervisor, SupervisorReport  # noqa: E402


def test_supervisor_observes_without_dispatching() -> None:
    supervisor = FleetSupervisor()
    snapshot = HealthSnapshot(
        mission_run_id="run-1",
        task_id="T-001",
        lane_id="lane-1",
        owner_epoch=1,
        signal=HealthSignal("alive", "ready", "advanced", "healthy"),
    )

    report = supervisor.observe(snapshot, desired_state="running", active_owner_epoch=1)

    assert isinstance(report, SupervisorReport)
    assert report.diagnosis.status == "healthy"
    assert report.interventions == ()
    assert supervisor.dispatch_count == 0


def test_supervisor_report_lineage_is_detached_and_immutable() -> None:
    source = {
        "mission_id": "mission-1",
        "mission_run_id": "run-1",
        "task_id": "T-001",
        "lane_id": "lane-1",
        "attempt_id": "attempt-1",
        "session_id": "session-1",
        "owner_epoch": 1,
    }
    report = SupervisorReport(diagnosis=SupervisorDiagnosis("healthy"), lineage=source)
    expected = report.to_dict()

    source["owner_epoch"] = 99
    assert report.to_dict() == expected

    try:
        report.lineage["owner_epoch"] = 99  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("report lineage must be immutable")
    assert report.to_dict() == expected


def test_supervisor_can_preview_handoff_without_dispatch() -> None:
    supervisor = FleetSupervisor()
    artifact = supervisor.preview_handoff(
        mission_run_id="run-1",
        task_id="T-001",
        source_lane_id="lane-1",
        target_role="verification",
        owner_epoch=1,
        reason="phase_boundary",
        summary="Implementation finished",
        completed=["implementation"],
        remaining=["verification"],
        decisions=[],
        risks=[],
        evidence_refs=["result.json"],
        next_action="Run verification",
    )

    assert artifact.lineage["target_role"] == "verification"
    assert supervisor.dispatch_count == 0
