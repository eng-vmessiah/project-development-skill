"""Read-only supervisor facade composed from supervision and handoff contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .handoff import HandoffArtifact, _freeze, _thaw, create_handoff
from .supervision import HealthSnapshot, InterventionProposal, SupervisorDiagnosis, _bounded_id, reconcile_snapshot


@dataclass(frozen=True)
class SupervisorReport:
    diagnosis: SupervisorDiagnosis
    interventions: tuple[InterventionProposal, ...] = ()
    lineage: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.diagnosis, SupervisorDiagnosis):
            raise ValueError("diagnosis must be SupervisorDiagnosis")
        if isinstance(self.interventions, (str, bytes)):
            raise ValueError("interventions must be bounded")
        try:
            intervention_items = tuple(self.interventions)
        except TypeError as exc:
            raise ValueError("interventions must be bounded") from exc
        if len(intervention_items) > 32:
            raise ValueError("interventions must be bounded")
        proposals = tuple(item if isinstance(item, InterventionProposal) else InterventionProposal(**dict(item))
                          if isinstance(item, dict) else (_ for _ in ()).throw(ValueError("invalid intervention"))
                          for item in intervention_items)
        object.__setattr__(self, "interventions", proposals)
        if self.lineage is not None:
            if not isinstance(self.lineage, Mapping) or set(self.lineage) != {"mission_id", "mission_run_id", "task_id", "lane_id", "attempt_id", "session_id", "owner_epoch"}:
                raise ValueError("invalid report lineage")
            for name in ("mission_id", "mission_run_id", "task_id", "lane_id", "attempt_id", "session_id"):
                _bounded_id(name, self.lineage[name])
            if type(self.lineage["owner_epoch"]) is not int or self.lineage["owner_epoch"] < 0:
                raise ValueError("invalid report lineage")
            object.__setattr__(self, "lineage", _freeze(dict(self.lineage)))

    def to_dict(self) -> dict[str, Any]:
        result = {"diagnosis": self.diagnosis.to_dict(),
                  "interventions": [item.to_dict() for item in self.interventions]}
        if self.lineage is not None:
            result["lineage"] = {key: _thaw(self.lineage[key]) for key in
                                  ("mission_id", "mission_run_id", "task_id", "lane_id", "attempt_id", "session_id", "owner_epoch")}
        return result


class FleetSupervisor:
    """Observe and propose; never dispatch or mutate workers in this slice."""

    def __init__(self) -> None:
        self.dispatch_count = 0

    def observe(
        self,
        snapshot: HealthSnapshot,
        *,
        desired_state: str,
        active_owner_epoch: int | None = None,
    ) -> SupervisorReport:
        diagnosis = reconcile_snapshot(
            snapshot,
            desired_state=desired_state,
            active_owner_epoch=active_owner_epoch,
        )
        return SupervisorReport(diagnosis=diagnosis, interventions=diagnosis.proposals,
                                lineage=snapshot.lineage_to_dict())

    def preview_handoff(
        self,
        *,
        mission_id: str = "legacy-mission",
        mission_run_id: str,
        task_id: str,
        source_lane_id: str,
        attempt_id: str = "legacy-attempt",
        session_id: str = "legacy-session",
        target_role: str,
        owner_epoch: int,
        reason: str,
        summary: str,
        completed: Iterable[str],
        remaining: Iterable[str],
        decisions: Iterable[str],
        risks: Iterable[str],
        evidence_refs: Iterable[str],
        next_action: str,
    ) -> HandoffArtifact:
        return create_handoff(
            mission_id=mission_id,
            mission_run_id=mission_run_id,
            task_id=task_id,
            source_lane_id=source_lane_id,
            attempt_id=attempt_id,
            session_id=session_id,
            target_role=target_role,
            owner_epoch=owner_epoch,
            reason=reason,
            summary=summary,
            completed=completed,
            remaining=remaining,
            decisions=decisions,
            risks=risks,
            evidence_refs=evidence_refs,
            next_action=next_action,
        )


__all__ = ["FleetSupervisor", "SupervisorReport"]
