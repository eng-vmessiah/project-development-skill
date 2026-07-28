import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.gates import GateResult, GateStatus, HumanVerificationGate  # noqa: E402
from pd_fleet.orchestrator import FleetOrchestrator  # noqa: E402


_NOW = datetime.now(timezone.utc).replace(microsecond=0)
_DIGEST = "a" * 64


def _human_payload() -> dict:
    return {
        "owner": "release-owner",
        "identity": "human@example.test",
        "decision": "APPROVED",
        "scope": "release",
        "run": "run-123",
        "evidence_digest": _DIGEST,
        "artifact_digest": "b" * 64,
        "created_at": _NOW.isoformat().replace("+00:00", "Z"),
        "updated_at": _NOW.isoformat().replace("+00:00", "Z"),
        "freshness_window": 3600,
    }


def _passed_result(gate_type: str) -> GateResult:
    return GateResult(
        gate_id=f"gate-{gate_type}",
        gate_type=gate_type,
        status=GateStatus.PASSED,
        owner="automation",
        decision="approved",
        evidence=["evidence-1"],
        reports=["report-1"],
    )


def test_structural_passed_governance_results_are_denied():
    assert not FleetOrchestrator._gate_passed(_passed_result("review"))
    assert not FleetOrchestrator._gate_passed(_passed_result("grill"))
    assert not FleetOrchestrator._gate_passed(_passed_result("review").to_dict())


def test_valid_human_verification_gate_is_accepted():
    gate = HumanVerificationGate.from_dict(_human_payload())
    assert FleetOrchestrator._gate_passed(gate)
    assert FleetOrchestrator._gate_passed(_human_payload())


def test_malformed_human_mapping_is_denied():
    payload = _human_payload()
    del payload["evidence_digest"]
    assert not FleetOrchestrator._gate_passed(payload)


def test_automatic_gate_results_remain_policy_evaluated():
    assert FleetOrchestrator._gate_passed(_passed_result("smoke_test"))
    assert FleetOrchestrator._gate_passed(_passed_result("evidence"))
    assert FleetOrchestrator._gate_passed(_passed_result("smoke_test").to_dict())