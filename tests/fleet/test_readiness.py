"""E9 readiness composition contract tests."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import inspect
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.event_diagnostics import EventDiagnosticsReport
from pd_fleet.readiness import ReadinessView, compose_readiness
from pd_fleet.run_event_reconciliation import RunEventReconciliationReport
from pd_fleet.supervision import SupervisorDiagnosis
from pd_fleet.supervisor import SupervisorReport


def supervisor(status: str) -> SupervisorReport:
    return SupervisorReport(SupervisorDiagnosis(status))


def event(status: str, reasons: tuple[str, ...] = ()) -> EventDiagnosticsReport:
    return EventDiagnosticsReport(status, 0, 0, 0, None, None, (), {}, reasons)


def reconciliation(status: str, reasons: tuple[str, ...] = ()) -> RunEventReconciliationReport:
    return RunEventReconciliationReport(status, "run-1", None, None, None, 0, None, reasons)


@pytest.mark.parametrize(
    ("kwargs", "status", "reasons", "components"),
    [
        ({"supervisor_report": supervisor("healthy")}, "ready", (), ("supervisor",)),
        ({"event_report": event("healthy")}, "ready", (), ("event",)),
        ({"reconciliation_report": reconciliation("consistent")}, "ready", (), ("reconciliation",)),
        ({}, "unknown", ("missing_or_unknown_source",), ()),
        ({"supervisor_report": supervisor("suspected")}, "unknown", ("missing_or_unknown_source",), ("supervisor",)),
        ({"supervisor_report": supervisor("slow")}, "degraded", ("source_degraded",), ("supervisor",)),
        ({"supervisor_report": supervisor("degraded")}, "degraded", ("source_degraded",), ("supervisor",)),
        ({"supervisor_report": supervisor("blocked")}, "blocked", ("supervisor_blocked",), ("supervisor",)),
        ({"supervisor_report": supervisor("failed")}, "blocked", ("supervisor_blocked",), ("supervisor",)),
        ({"supervisor_report": supervisor("needs_human_intervention")}, "blocked", ("supervisor_blocked",), ("supervisor",)),
        ({"event_report": event("degraded")}, "degraded", ("source_degraded",), ("event",)),
        ({"reconciliation_report": reconciliation("degraded")}, "degraded", ("source_degraded",), ("reconciliation",)),
        ({"supervisor_report": supervisor("blocked"), "event_report": event("degraded")}, "blocked", ("supervisor_blocked",), ("supervisor", "event")),
        ({"supervisor_report": supervisor("healthy"), "event_report": event("degraded"), "reconciliation_report": reconciliation("degraded")}, "degraded", ("source_degraded",), ("supervisor", "event", "reconciliation")),
        ({"supervisor_report": supervisor("healthy"), "event_report": event("unknown")}, "unknown", ("missing_or_unknown_source",), ("supervisor", "event")),
        ({"event_report": event("healthy"), "reconciliation_report": reconciliation("unknown")}, "unknown", ("missing_or_unknown_source",), ("event", "reconciliation")),
    ],
)
def test_precedence_and_component_projection(kwargs, status, reasons, components):
    view = compose_readiness(**kwargs)
    assert view.status == status
    assert view.reasons == reasons
    assert view.present_components == components
    assert view.supervisor_status == (kwargs["supervisor_report"].diagnosis.status if "supervisor_report" in kwargs else None)
    assert view.event_status == (kwargs["event_report"].status if "event_report" in kwargs else None)
    assert view.reconciliation_status == (kwargs["reconciliation_report"].status if "reconciliation_report" in kwargs else None)


def test_view_is_frozen_bounded_and_serialization_detached():
    view = ReadinessView("ready", "healthy", "healthy", "consistent", (), ("supervisor", "event", "reconciliation"))
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        view.status = "blocked"
    payload = view.to_dict()
    assert list(payload) == sorted(payload)
    assert payload == {
        "event_status": "healthy", "present_components": ["supervisor", "event", "reconciliation"],
        "reasons": [], "reconciliation_status": "consistent", "status": "ready", "supervisor_status": "healthy",
    }
    payload["present_components"].append("tampered")
    payload["reasons"].append("tampered")
    assert view.present_components == ("supervisor", "event", "reconciliation") and view.reasons == ()


class HostileIterable:
    def __iter__(self):
        raise RuntimeError("SECRET")


@pytest.mark.parametrize("field", ["reasons", "present_components"])
def test_view_rejects_hostile_or_non_exact_collections(field):
    values = {"status": "ready", "supervisor_status": None, "event_status": None, "reconciliation_status": None,
              "reasons": (), "present_components": ("supervisor",)}
    values[field] = HostileIterable()
    with pytest.raises((TypeError, ValueError)):
        ReadinessView(**values)
    values[field] = ["supervisor"]
    with pytest.raises((TypeError, ValueError)):
        ReadinessView(**values)


@pytest.mark.parametrize("bad", [True, 1, "supervisor", HostileIterable()])
def test_compose_requires_exact_report_types(bad):
    with pytest.raises((TypeError, ValueError)):
        compose_readiness(supervisor_report=bad)


@pytest.mark.parametrize("field", ["reasons", "present_components"])
def test_view_rejects_unknown_duplicate_or_oversized_values(field):
    base = {"status": "ready", "supervisor_status": None, "event_status": None, "reconciliation_status": None,
            "reasons": (), "present_components": ()}
    base[field] = ("not_safe",)
    with pytest.raises(ValueError):
        ReadinessView(**base)
    base[field] = (("supervisor", "supervisor") if field == "present_components" else ("supervisor_blocked", "supervisor_blocked"))
    if field == "present_components":
        with pytest.raises(ValueError):
            ReadinessView(**base)
    else:
        with pytest.raises(ValueError):
            ReadinessView(**base)
    base[field] = (("supervisor",) * 4 if field == "present_components" else ("supervisor_blocked",) * 4)
    with pytest.raises(ValueError):
        ReadinessView(**base)


@pytest.mark.parametrize("field, value", [
    ("supervisor_status", "unknown"),
    ("event_status", "consistent"),
    ("reconciliation_status", "healthy"),
])
def test_view_validates_component_status_domains(field, value):
    values = {"status": "unknown", "supervisor_status": None, "event_status": None,
              "reconciliation_status": None, "reasons": ("missing_or_unknown_source",),
              "present_components": (field.removesuffix("_status"),)}
    values[field] = value
    with pytest.raises(ValueError):
        ReadinessView(**values)


@pytest.mark.parametrize("values", [
    {"status": "ready", "supervisor_status": "healthy", "event_status": None,
     "reconciliation_status": None, "reasons": ("source_degraded",), "present_components": ("supervisor",)},
    {"status": "blocked", "supervisor_status": "healthy", "event_status": None,
     "reconciliation_status": None, "reasons": ("supervisor_blocked",), "present_components": ("supervisor",)},
    {"status": "degraded", "supervisor_status": "slow", "event_status": None,
     "reconciliation_status": None, "reasons": (), "present_components": ("supervisor",)},
    {"status": "unknown", "supervisor_status": "suspected", "event_status": None,
     "reconciliation_status": None, "reasons": ("source_degraded",), "present_components": ("supervisor",)},
    {"status": "ready", "supervisor_status": None, "event_status": None,
     "reconciliation_status": None, "reasons": (), "present_components": ("event",)},
    {"status": "ready", "supervisor_status": "healthy", "event_status": None,
     "reconciliation_status": None, "reasons": (), "present_components": ()},
])
def test_view_rejects_incoherent_status_reason_or_component_projection(values):
    with pytest.raises(ValueError):
        ReadinessView(**values)


def test_projection_does_not_leak_report_details_or_integrations():
    source = inspect.getsource(sys.modules["pd_fleet.readiness"])
    for forbidden in ("payload", "proposals", "interventions", "owner", "task_id", "filesystem", "subprocess", "socket", "requests"):
        assert forbidden not in source
    report = SupervisorReport(SupervisorDiagnosis("blocked", ("SECRET_RAW_REASON",)))
    view = compose_readiness(supervisor_report=report)
    assert view.to_dict() == {"event_status": None, "present_components": ["supervisor"], "reasons": ["supervisor_blocked"], "reconciliation_status": None, "status": "blocked", "supervisor_status": "blocked"}
    assert "SECRET_RAW_REASON" not in repr(view.to_dict())
