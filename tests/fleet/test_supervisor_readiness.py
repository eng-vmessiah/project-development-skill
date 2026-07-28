"""E10A supervisor readiness facade contract tests."""
from __future__ import annotations

import inspect
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.event_diagnostics import EventDiagnosticsReport
from pd_fleet.readiness import ReadinessView, compose_readiness
from pd_fleet.run_event_reconciliation import RunEventReconciliationReport
from pd_fleet.supervision import SupervisorDiagnosis
from pd_fleet.supervisor import FleetSupervisor, SupervisorReport


def supervisor(status: str) -> SupervisorReport:
    return SupervisorReport(SupervisorDiagnosis(status))


def event(status: str) -> EventDiagnosticsReport:
    return EventDiagnosticsReport(status, 0, 0, 0, None, None, (), {}, ())


def reconciliation(status: str) -> RunEventReconciliationReport:
    return RunEventReconciliationReport(status, "run-1", None, None, None, 0, None, ())


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"supervisor_report": supervisor("healthy")},
        {"supervisor_report": supervisor("blocked"), "event_report": event("degraded")},
        {"supervisor_report": supervisor("healthy"), "event_report": event("degraded"), "reconciliation_report": reconciliation("unknown")},
        {"event_report": event("healthy"), "reconciliation_report": reconciliation("consistent")},
    ],
)
def test_readiness_view_is_exact_compositor_equivalence(kwargs):
    supervisor_facade = FleetSupervisor()
    assert supervisor_facade.readiness_view(**kwargs) == compose_readiness(**kwargs)
    assert isinstance(supervisor_facade.readiness_view(**kwargs), ReadinessView)


@pytest.mark.parametrize("field", ["supervisor_report", "event_report", "reconciliation_report"])
def test_readiness_view_preserves_compositor_type_errors(field):
    kwargs = {field: object()}
    with pytest.raises(TypeError, match="invalid type") as expected:
        compose_readiness(**kwargs)
    with pytest.raises(type(expected.value), match=str(expected.value)):
        FleetSupervisor().readiness_view(**kwargs)


def test_readiness_view_has_no_side_effects_or_detail_leakage(tmp_path):
    supervisor_facade = FleetSupervisor()
    before = dict(vars(supervisor_facade))
    before_files = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    report = SupervisorReport(SupervisorDiagnosis("blocked", ("SECRET_RAW_REASON",)))

    view = supervisor_facade.readiness_view(supervisor_report=report)

    assert dict(vars(supervisor_facade)) == before == {"dispatch_count": 0}
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before_files
    assert view.to_dict() == {
        "event_status": None,
        "present_components": ["supervisor"],
        "reasons": ["supervisor_blocked"],
        "reconciliation_status": None,
        "status": "blocked",
        "supervisor_status": "blocked",
    }
    assert "SECRET_RAW_REASON" not in repr(view.to_dict())


def test_readiness_view_source_is_thin_and_integration_free():
    source = inspect.getsource(FleetSupervisor.readiness_view)
    assert "compose_readiness" in source
    for forbidden in ("dispatch", "PDState", "provider", "network", "process", "open(", "Path("):
        assert forbidden not in source
