"""Read-only health signals, bounded interventions and deterministic diagnosis."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .handoff import HandoffReason, _ref, _sanitize_text, _unsafe_identifier


class SupervisionError(ValueError):
    """Invalid or unsafe supervision input."""

_ALLOWED = {
    "liveness": {"alive", "missing", "unknown"},
    "readiness": {"ready", "not_ready", "unknown"},
    "progress": {"advanced", "stalled", "unknown"},
    "health": {"healthy", "degraded", "failed", "unknown"},
}
MAX_AGE_SECONDS = 30 * 24 * 60 * 60
HEARTBEAT_SUSPECT_SECONDS = 60
HEARTBEAT_HUMAN_SECONDS = 300
PROGRESS_SUSPECT_SECONDS = 60
PROGRESS_SLOW_SECONDS = 300
_DIAGNOSIS_STATUSES = {"healthy", "slow", "suspected", "blocked", "degraded", "failed", "needs_human_intervention"}


def _signal(name: str, value: str) -> str:
    if type(value) is not str or value not in _ALLOWED[name]:
        raise SupervisionError(f"invalid {name} signal")
    return value


def _bounded_id(name: str, value: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 200 or any(ord(c) < 32 for c in value):
        raise SupervisionError(f"invalid {name}")
    value = value.strip()
    if _unsafe_identifier(value):
        raise SupervisionError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class HealthSignal:
    liveness: str
    readiness: str
    progress: str
    health: str

    def __post_init__(self) -> None:
        for name in _ALLOWED:
            object.__setattr__(self, name, _signal(name, getattr(self, name)))

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in _ALLOWED}


@dataclass(frozen=True)
class HealthSnapshot:
    mission_run_id: str
    task_id: str
    lane_id: str
    owner_epoch: int
    signal: HealthSignal
    mission_id: str = "legacy-mission"
    attempt_id: str = "legacy-attempt"
    session_id: str = "legacy-session"
    last_heartbeat_age_seconds: float | None = None
    last_progress_age_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in ("mission_run_id", "task_id", "lane_id", "mission_id", "attempt_id", "session_id"):
            object.__setattr__(self, name, _bounded_id(name, getattr(self, name)))
        if type(self.owner_epoch) is not int or self.owner_epoch < 0:
            raise SupervisionError("invalid owner_epoch")
        if not isinstance(self.signal, HealthSignal):
            raise SupervisionError("invalid signal")
        for name in ("last_heartbeat_age_seconds", "last_progress_age_seconds"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                                      not math.isfinite(value) or value < 0 or value > MAX_AGE_SECONDS):
                raise SupervisionError(f"invalid {name}")

    def lineage_to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in
                ("mission_id", "mission_run_id", "task_id", "lane_id", "attempt_id", "session_id", "owner_epoch")}

    def to_dict(self) -> dict[str, Any]:
        return {"lineage": self.lineage_to_dict(), "signal": self.signal.to_dict(),
                "last_heartbeat_age_seconds": self.last_heartbeat_age_seconds,
                "last_progress_age_seconds": self.last_progress_age_seconds}


@dataclass(frozen=True)
class InterventionProposal:
    action: str
    reason: str
    target: str
    evidence_refs: tuple[str, ...]
    human_gate_required: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", _sanitize_text("action", self.action))
        object.__setattr__(self, "target", _bounded_id("target", self.target))
        reason = self.reason.value if isinstance(self.reason, HandoffReason) else self.reason
        if reason not in {item.value for item in HandoffReason}:
            raise SupervisionError("invalid intervention reason")
        object.__setattr__(self, "reason", reason)
        if isinstance(self.evidence_refs, (str, bytes)):
            raise SupervisionError("evidence_refs must be a list")
        refs = tuple(_ref(ref) for ref in self.evidence_refs)
        if not refs or len(refs) > 32:
            raise SupervisionError("evidence_refs must be bounded and non-empty")
        object.__setattr__(self, "evidence_refs", refs)
        if type(self.human_gate_required) is not bool:
            raise SupervisionError("human_gate_required must be bool")

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "reason": self.reason, "target": self.target,
                "evidence_refs": list(self.evidence_refs), "human_gate_required": self.human_gate_required}


@dataclass(frozen=True)
class SupervisorDiagnosis:
    status: str
    reasons: tuple[str, ...] = ()
    proposals: tuple[InterventionProposal, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not str or self.status not in _DIAGNOSIS_STATUSES:
            raise SupervisionError("invalid diagnosis status")
        if isinstance(self.reasons, (str, bytes)):
            raise SupervisionError("reasons must be a list")
        try:
            reasons = tuple(_sanitize_text("reason", reason) for reason in self.reasons)
        except (TypeError, ValueError) as exc:
            raise SupervisionError("invalid diagnosis reasons") from exc
        if len(reasons) > 32 or sum(len(reason) for reason in reasons) > 16000:
            raise SupervisionError("reasons exceed bounds")
        object.__setattr__(self, "reasons", reasons)
        if isinstance(self.proposals, (str, bytes)):
            raise SupervisionError("proposals must be a list")
        if len(self.proposals) > 32:
            raise SupervisionError("proposals exceed bounds")
        converted = []
        for item in self.proposals:
            if isinstance(item, InterventionProposal):
                converted.append(item)
            elif isinstance(item, Mapping):
                converted.append(InterventionProposal(**dict(item)))
            else:
                raise SupervisionError("invalid intervention proposal")
        object.__setattr__(self, "proposals", tuple(converted))

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reasons": list(self.reasons),
                "proposals": [item.to_dict() for item in self.proposals]}


def _proposal(action: str, reason: str, snapshot: HealthSnapshot, why: str, human: bool = False) -> InterventionProposal:
    return InterventionProposal(action, reason, snapshot.task_id, (f"snapshot:{snapshot.mission_run_id}:{snapshot.task_id}",), human)


def diagnose_snapshot(snapshot: HealthSnapshot) -> SupervisorDiagnosis:
    if not isinstance(snapshot, HealthSnapshot):
        raise SupervisionError("snapshot must be HealthSnapshot")
    signal = snapshot.signal
    heartbeat = snapshot.last_heartbeat_age_seconds
    progress_age = snapshot.last_progress_age_seconds
    if signal.health == "failed":
        return SupervisorDiagnosis("failed", ("worker_reported_failed",), (_proposal("inspect", "human_intervention", snapshot, "reported_failure", True),))
    if signal.liveness == "missing":
        if heartbeat is not None and heartbeat >= HEARTBEAT_HUMAN_SECONDS:
            return SupervisorDiagnosis("needs_human_intervention", ("heartbeat_missing_too_long",), (_proposal("inspect", "human_intervention", snapshot, "heartbeat_missing", True),))
        return SupervisorDiagnosis("suspected", ("heartbeat_missing",))
    if signal.readiness == "not_ready":
        return SupervisorDiagnosis("blocked", ("worker_not_ready",), (_proposal("inspect", "fallback", snapshot, "not_ready"),))
    if signal.progress == "stalled":
        if progress_age is not None and progress_age >= PROGRESS_SLOW_SECONDS:
            return SupervisorDiagnosis("slow", ("progress_stalled", "progress_age_exceeded_slow_threshold"), (_proposal("inspect", "retry", snapshot, "slow_progress"),))
        return SupervisorDiagnosis("suspected", ("progress_stalled",))
    if signal.health == "degraded":
        return SupervisorDiagnosis("degraded", ("health_degraded",), (_proposal("inspect", "fallback", snapshot, "degraded_health"),))
    if "unknown" in (signal.liveness, signal.readiness, signal.progress, signal.health):
        return SupervisorDiagnosis("suspected", ("incomplete_health_signal",))
    if heartbeat is not None and heartbeat >= HEARTBEAT_SUSPECT_SECONDS:
        return SupervisorDiagnosis("suspected", ("heartbeat_age_exceeded_suspect_threshold",))
    return SupervisorDiagnosis("healthy")


def reconcile_snapshot(snapshot: HealthSnapshot, *, desired_state: str, active_owner_epoch: int | None = None) -> SupervisorDiagnosis:
    if desired_state not in {"running", "paused", "completed", "cancelled"}:
        raise SupervisionError("invalid desired_state")
    if active_owner_epoch is not None and (type(active_owner_epoch) is not int or active_owner_epoch < 0):
        raise SupervisionError("invalid active_owner_epoch")
    if active_owner_epoch is not None and snapshot.owner_epoch != active_owner_epoch:
        return SupervisorDiagnosis("blocked", ("stale_owner_epoch",))
    if desired_state == "running":
        return diagnose_snapshot(snapshot)
    if desired_state == "paused" and snapshot.signal.liveness == "alive":
        return SupervisorDiagnosis("degraded", ("pause_not_observed",))
    if desired_state in {"completed", "cancelled"} and snapshot.signal.progress != "advanced":
        return SupervisorDiagnosis("blocked", ("terminal_state_not_ready",))
    return SupervisorDiagnosis("healthy")


__all__ = ["HealthSignal", "HealthSnapshot", "InterventionProposal", "SupervisorDiagnosis", "SupervisionError", "diagnose_snapshot", "reconcile_snapshot"]
