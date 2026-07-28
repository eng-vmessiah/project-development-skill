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


_EXPECTED_RUN = "run-123"
_EXPECTED_SCOPE = {
    "schema_version": "pd-fleet-gate-scope:v1",
    "plan_hash": _DIGEST,
    "tasks": ["task-a", "task-b"],
    "waves": ["wave-1", "wave-2"],
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
    payload = _human_payload()
    payload["scope"] = {**_EXPECTED_SCOPE, "tasks": ["task-b", "task-a"], "waves": ["wave-2", "wave-1"]}
    gate = HumanVerificationGate.from_dict(payload)
    assert FleetOrchestrator._gate_passed(gate, expected_run=_EXPECTED_RUN, expected_scope=_EXPECTED_SCOPE)
    assert FleetOrchestrator._gate_passed(payload, expected_run=_EXPECTED_RUN, expected_scope=_EXPECTED_SCOPE)


def test_malformed_human_mapping_is_denied():
    payload = _human_payload()
    del payload["evidence_digest"]
    assert not FleetOrchestrator._gate_passed(payload, expected_run=_EXPECTED_RUN, expected_scope=_EXPECTED_SCOPE)


def test_human_gate_wrong_run_is_denied():
    payload = _human_payload()
    payload["scope"] = _EXPECTED_SCOPE
    assert not FleetOrchestrator._gate_passed(payload, expected_run="run-other", expected_scope=_EXPECTED_SCOPE)


def test_human_gate_wrong_scope_is_denied():
    payload = _human_payload()
    payload["scope"] = {**_EXPECTED_SCOPE, "plan_hash": "b" * 64}
    assert not FleetOrchestrator._gate_passed(payload, expected_run=_EXPECTED_RUN, expected_scope=_EXPECTED_SCOPE)


def test_human_gate_without_current_context_is_denied():
    payload = _human_payload()
    payload["scope"] = _EXPECTED_SCOPE
    assert not FleetOrchestrator._gate_passed(payload)
    assert not FleetOrchestrator._gate_passed(payload, expected_run=None, expected_scope=_EXPECTED_SCOPE)
    assert not FleetOrchestrator._gate_passed(payload, expected_run=_EXPECTED_RUN, expected_scope=None)


def test_automatic_gate_results_remain_policy_evaluated():
    assert FleetOrchestrator._gate_passed(_passed_result("smoke_test"))
    assert FleetOrchestrator._gate_passed(_passed_result("evidence"))
    assert FleetOrchestrator._gate_passed(_passed_result("smoke_test").to_dict())