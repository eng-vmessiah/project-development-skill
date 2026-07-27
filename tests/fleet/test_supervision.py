"""RED contract tests for the first supervisor/observer slice."""
from __future__ import annotations

import math
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.supervision import (  # noqa: E402
    HealthSignal,
    HealthSnapshot,
    SupervisorDiagnosis,
    diagnose_snapshot,
    reconcile_snapshot,
    InterventionProposal,
)


def _snapshot(**overrides):
    values = dict(mission_run_id="run-1", task_id="T-001", lane_id="lane-1", owner_epoch=1,
                  signal=HealthSignal("alive", "ready", "advanced", "healthy"))
    values.update(overrides)
    return HealthSnapshot(**values)


def test_diagnosis_taxonomy_uses_finite_age_thresholds_without_false_failure():
    cases = [
        (_snapshot(), "healthy"),
        (_snapshot(signal=HealthSignal("alive", "ready", "stalled", "healthy"),
                   last_progress_age_seconds=600), "slow"),
        (_snapshot(signal=HealthSignal("alive", "ready", "stalled", "healthy"),
                   last_progress_age_seconds=30), "suspected"),
        (_snapshot(signal=HealthSignal("alive", "not_ready", "advanced", "healthy")), "blocked"),
        (_snapshot(signal=HealthSignal("alive", "ready", "advanced", "degraded")), "degraded"),
        (_snapshot(signal=HealthSignal("alive", "ready", "advanced", "failed")), "failed"),
        (_snapshot(signal=HealthSignal("missing", "ready", "advanced", "healthy"),
                   last_heartbeat_age_seconds=600), "needs_human_intervention"),
    ]
    for snapshot, expected in cases:
        diagnosis = diagnose_snapshot(snapshot)
        assert diagnosis.status == expected
    assert diagnose_snapshot(cases[-1][0]).status != "failed"


def test_intervention_proposal_is_immutable_bounded_and_used_by_diagnosis():
    proposal = InterventionProposal(
        action="inspect", reason="human_intervention", target="T-001",
        evidence_refs=("checkpoint.json",), human_gate_required=True,
    )
    assert proposal.to_dict()["human_gate_required"] is True
    with pytest.raises(FrozenInstanceError):
        proposal.evidence_refs += ("other.json",)
    diagnosis = diagnose_snapshot(_snapshot(
        signal=HealthSignal("alive", "ready", "stalled", "healthy"),
        last_progress_age_seconds=600,
    ))
    assert all(isinstance(item, InterventionProposal) for item in diagnosis.proposals)


def test_health_signal_separates_liveness_readiness_progress_and_health() -> None:
    signal = HealthSignal(
        liveness="alive",
        readiness="ready",
        progress="advanced",
        health="healthy",
    )

    assert signal.to_dict() == {
        "liveness": "alive",
        "readiness": "ready",
        "progress": "advanced",
        "health": "healthy",
    }


def test_live_worker_without_progress_is_suspected_not_failed() -> None:
    snapshot = HealthSnapshot(
        mission_run_id="run-1",
        task_id="T-001",
        lane_id="lane-1",
        owner_epoch=3,
        signal=HealthSignal(
            liveness="alive",
            readiness="ready",
            progress="stalled",
            health="healthy",
        ),
        last_heartbeat_age_seconds=30,
        last_progress_age_seconds=900,
    )

    diagnosis = diagnose_snapshot(snapshot)

    assert isinstance(diagnosis, SupervisorDiagnosis)
    assert diagnosis.status in {"suspected", "slow", "degraded"}
    assert diagnosis.status != "failed"
    assert diagnosis.proposals


def test_reconciliation_detects_stale_owner_without_mutating_snapshot() -> None:
    snapshot = HealthSnapshot(
        mission_run_id="run-1",
        task_id="T-001",
        lane_id="lane-old",
        owner_epoch=2,
        signal=HealthSignal("alive", "ready", "advanced", "healthy"),
    )

    diagnosis = reconcile_snapshot(snapshot, desired_state="running", active_owner_epoch=3)

    assert diagnosis.status == "blocked"
    assert diagnosis.reasons == ("stale_owner_epoch",)
    assert snapshot.owner_epoch == 2


@pytest.mark.parametrize("age", [math.nan, math.inf, -math.inf, 31 * 24 * 60 * 60, -1])
def test_snapshot_rejects_non_finite_and_unbounded_ages(age: float) -> None:
    with pytest.raises(ValueError):
        HealthSnapshot(
            mission_run_id="run-1", task_id="T-001", lane_id="lane-1", owner_epoch=1,
            signal=HealthSignal("alive", "ready", "advanced", "healthy"),
            last_heartbeat_age_seconds=age,
        )


def test_diagnosis_nested_proposals_are_immutable_and_serialization_is_detached() -> None:
    diagnosis = SupervisorDiagnosis(
        status="suspected", reasons=("check",),
        proposals=(InterventionProposal(
            action="inspect", reason="human_intervention", target="T-001",
            evidence_refs=("result.json",), human_gate_required=True,
        ),),
    )
    with pytest.raises(FrozenInstanceError):
        diagnosis.proposals[0].evidence_refs += ("other.json",)
    payload = diagnosis.to_dict()
    payload["proposals"][0]["target"] = "other"
    assert diagnosis.proposals[0].target == "T-001"
