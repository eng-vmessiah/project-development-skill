"""Pure, bounded projection of fleet source health into readiness."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .event_diagnostics import EventDiagnosticsReport
    from .run_event_reconciliation import RunEventReconciliationReport
    from .supervisor import SupervisorReport

_STATUSES = frozenset({"ready", "unknown", "degraded", "blocked"})

_REASONS = frozenset({
    "supervisor_blocked", "source_degraded", "missing_or_unknown_source",
})
_COMPONENTS = frozenset({"supervisor", "event", "reconciliation"})
_MAX_ITEMS = 3
_SUPERVISOR_STATUSES = frozenset({"healthy", "slow", "suspected", "blocked", "degraded", "failed", "needs_human_intervention"})
_EVENT_STATUSES = frozenset({"healthy", "degraded", "unknown"})
_RECONCILIATION_STATUSES = frozenset({"consistent", "degraded", "unknown"})


def _status(value: Any, allowed: frozenset[str], name: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or value not in allowed:
        raise ValueError(f"invalid {name}")
    return value


def _fixed_tuple(value: Any, allowed: frozenset[str], name: str, *, dedupe: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise TypeError(f"{name} must be an exact tuple")
    if len(value) > _MAX_ITEMS:
        raise ValueError(f"{name} exceeds bounds")
    result: list[str] = []
    for item in value:
        if type(item) is not str or item not in allowed:
            raise ValueError(f"invalid {name}")
        if item in result:
            if not dedupe:
                raise ValueError(f"invalid {name}")
            continue
        result.append(item)
    return tuple(result)


@dataclass(frozen=True)
class ReadinessView:
    """Detached, JSON-safe readiness data with no source-specific details."""

    status: str
    supervisor_status: str | None
    event_status: str | None
    reconciliation_status: str | None
    reasons: tuple[str, ...]
    present_components: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.status) is not str or self.status not in _STATUSES:
            raise ValueError("invalid readiness status")
        supervisor = _status(self.supervisor_status, _SUPERVISOR_STATUSES, "supervisor status")
        event = _status(self.event_status, _EVENT_STATUSES, "event status")
        reconciliation = _status(self.reconciliation_status, _RECONCILIATION_STATUSES, "reconciliation status")
        reasons = _fixed_tuple(self.reasons, _REASONS, "reasons", dedupe=True)
        components = _fixed_tuple(self.present_components, _COMPONENTS, "present components")
        expected = tuple(name for name, value in (("supervisor", supervisor), ("event", event), ("reconciliation", reconciliation)) if value is not None)
        if components != expected:
            raise ValueError("present components do not match component statuses")
        if self.status == "ready":
            if reasons or supervisor not in (None, "healthy") or event not in (None, "healthy") or reconciliation not in (None, "consistent"):
                raise ValueError("ready readiness is inconsistent")
        elif self.status == "blocked":
            if reasons != ("supervisor_blocked",) or supervisor not in {"blocked", "failed", "needs_human_intervention"}:
                raise ValueError("blocked readiness is inconsistent")
        elif self.status == "degraded":
            if reasons != ("source_degraded",) or not ({supervisor, event, reconciliation} & {"slow", "degraded"}):
                raise ValueError("degraded readiness is inconsistent")
        elif reasons != ("missing_or_unknown_source",) or (components and not ({supervisor, event, reconciliation} & {"suspected", "unknown"})):
            raise ValueError("unknown readiness is inconsistent")
        object.__setattr__(self, "supervisor_status", supervisor)
        object.__setattr__(self, "event_status", event)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "reconciliation_status", reconciliation)
        object.__setattr__(self, "present_components", components)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_status": self.event_status,
            "present_components": list(self.present_components),
            "reasons": list(self.reasons),
            "reconciliation_status": self.reconciliation_status,
            "status": self.status,
            "supervisor_status": self.supervisor_status,
        }


def compose_readiness(
    *,
    supervisor_report: SupervisorReport | None = None,
    event_report: EventDiagnosticsReport | None = None,
    reconciliation_report: RunEventReconciliationReport | None = None,
) -> ReadinessView:
    """Compose readiness solely from already-materialized immutable reports."""
    from .event_diagnostics import EventDiagnosticsReport
    from .run_event_reconciliation import RunEventReconciliationReport
    from .supervision import SupervisorDiagnosis
    from .supervisor import SupervisorReport
    for value, expected, name in (
        (supervisor_report, SupervisorReport, "supervisor report"),
        (event_report, EventDiagnosticsReport, "event report"),
        (reconciliation_report, RunEventReconciliationReport, "reconciliation report"),
    ):
        if value is not None and type(value) is not expected:
            raise TypeError(f"{name} has an invalid type")

    supervisor_status = None
    if supervisor_report is not None:
        if type(supervisor_report.diagnosis) is not SupervisorDiagnosis:
            raise TypeError("supervisor diagnosis has an invalid type")
        supervisor_status = supervisor_report.diagnosis.status
    event_status = event_report.status if event_report is not None else None
    reconciliation_status = reconciliation_report.status if reconciliation_report is not None else None

    components = tuple(
        name for name, value in (
            ("supervisor", supervisor_report),
            ("event", event_report),
            ("reconciliation", reconciliation_report),
        ) if value is not None
    )
    reasons: list[str] = []
    if supervisor_status in {"blocked", "failed", "needs_human_intervention"}:
        status = "blocked"
        reasons.append("supervisor_blocked")
    elif supervisor_status in {"degraded", "slow"} or "degraded" in (event_status, reconciliation_status):
        status = "degraded"
        reasons.append("source_degraded")
    elif not components or supervisor_status == "suspected" or "unknown" in (event_status, reconciliation_status):
        status = "unknown"
        reasons.append("missing_or_unknown_source")
    else:
        status = "ready"
    return ReadinessView(status, supervisor_status, event_status, reconciliation_status, tuple(reasons), components)


__all__ = ["ReadinessView", "compose_readiness"]
