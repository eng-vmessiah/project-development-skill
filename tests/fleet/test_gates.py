import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.gates import GateError, GatePolicy, GateResult, GateStatus  # noqa: E402


def complete(kind="review", **overrides):
    data = dict(gate_id="G1", gate_type=kind, status="passed", owner="alice",
                decision="approved", evidence=["evidence/report.json"], reports=["report.json"], blockers=[])
    data.update(overrides)
    return GateResult(**data)


class _HostileRepr:
    def __repr__(self):
        raise AssertionError("repr must not be called")


def test_invalid_status_does_not_render_untrusted_value():
    with pytest.raises(GateError, match="status inválido") as exc:
        GateResult("G1", "review", status=_HostileRepr())
    assert "repr must not be called" not in str(exc.value)


@pytest.mark.parametrize("kind", ["review", "grill", "smoke_test", "evidence"])
def test_gate_types_and_default_policy(kind):
    result = complete(kind)
    assert GatePolicy().allows(result)


def test_status_transitions_are_explicit():
    result = GateResult("G1", "review")
    # Final states require the contract fields, so populate them before passing.
    result.owner, result.decision, result.evidence, result.reports = "a", "approved", ["e"], ["r"]
    result.transition("running").transition("passed")
    assert result.status is GateStatus.PASSED
    with pytest.raises(GateError):
        result.transition("running")


def test_default_deny_missing_evidence_or_open_high_blocker():
    policy = GatePolicy()
    with pytest.raises(GateError):
        complete(evidence=[])
    blocked = complete()
    blocked.blockers = [{"severity": "high", "status": "open"}]
    assert policy.evaluate(blocked) is GateStatus.BLOCKED
    assert policy.allows(complete(blockers=[{"severity": "high", "status": "closed"}]))


def test_human_decision_remains_pending():
    result = complete(decision="human")
    assert GatePolicy().evaluate(result) is GateStatus.PENDING
    assert not GatePolicy().allows(result)


def test_requirements_are_configurable_per_gate():
    result = complete("smoke_test")
    result.reports = []
    policy = GatePolicy(requirements={"smoke_test": {"reports": False}})
    assert policy.allows(result)


def test_json_serialization_is_deterministic_and_safe():
    result = complete(details={"z": 1, "a": True})
    encoded = result.to_json()
    assert encoded == result.to_json()
    assert json.loads(encoded) == result.to_dict()
    assert GateResult.from_json(encoded).to_dict() == result.to_dict()


def test_invalid_references_and_non_json_values_fail_closed():
    with pytest.raises(GateError):
        complete(evidence=[""])
    with pytest.raises(GateError):
        complete(details={"bad": object()})


def test_references_are_deep_copied_and_nested_payloads_are_validated():
    evidence = [{"ref": "log", "metadata": {"nested": ["before"]}}]
    result = complete(evidence=evidence)
    evidence[0]["metadata"]["nested"].append("after")
    assert result.evidence == [{"ref": "log", "metadata": {"nested": ["before"]}}]
    with pytest.raises(GateError):
        complete(evidence=[{"ref": "log", "metadata": {"bad": object()}}])
    cyclic = {"ref": "log"}
    cyclic["metadata"] = cyclic
    with pytest.raises(GateError):
        complete(reports=[cyclic])


def test_policy_copies_input_and_freezes_nested_requirements():
    requirements = {"review": {"reports": False}}
    defaults = {"owner": True}
    policy = GatePolicy(requirements=requirements, default_requirements=defaults)
    requirements["review"]["reports"] = True
    defaults["owner"] = False
    assert policy.requirements["review"]["reports"] is False
    assert policy.default_requirements["owner"] is True
    with pytest.raises(TypeError):
        policy.requirements["review"]["reports"] = True


@pytest.mark.parametrize("kwargs", [
    {"evidence": []},
    {"reports": []},
    {"blockers": [{"severity": "high", "status": "open"}]},
])
def test_passed_requires_full_contract(kwargs):
    with pytest.raises(GateError):
        complete(**kwargs)


def test_transition_to_passed_requires_full_contract():
    result = GateResult("G1", "review", owner="alice", decision="approved")
    result.transition("running")
    with pytest.raises(GateError):
        result.transition("passed")


def test_details_must_be_mapping():
    with pytest.raises(GateError):
        GateResult("G1", "review", details=["not", "a", "mapping"])


def test_policy_rejects_unknown_top_level_keys_and_non_string_keys():
    with pytest.raises(GateError, match="campos desconhecidos"):
        GatePolicy.from_dict({"requirements": {}, "typo": {}})
    with pytest.raises(GateError, match="chave JSON inválida"):
        GatePolicy.from_dict({1: {}})


@pytest.mark.parametrize("payload", [
    {"requirements": {"review": {"typo": True}}},
    {"default_requirements": {"typo": True}},
])
def test_policy_rejects_unknown_nested_requirement_keys(payload):
    with pytest.raises(GateError, match="requirement desconhecido"):
        GatePolicy.from_dict(payload)


@pytest.mark.parametrize("payload", [
    {"requirements": {"review": {"reports": 1}}},
    {"default_requirements": {"reports": None}},
])
def test_policy_rejects_non_boolean_requirement_values(payload):
    with pytest.raises(GateError, match="booleano"):
        GatePolicy.from_dict(payload)


def test_policy_aliases_are_compatible_but_conflicts_are_rejected():
    expected = {"review": {"reports": False}}
    assert GatePolicy.from_dict({"gates": expected}).requirements["review"]["reports"] is False
    assert GatePolicy.from_dict({"requirements": expected, "gates": expected}).to_dict() == GatePolicy.from_dict({"requirements": expected}).to_dict()
    with pytest.raises(GateError, match="conflitantes"):
        GatePolicy.from_dict({"requirements": expected, "gates": {"review": {"reports": True}}})


def test_policy_alias_conflict_cannot_be_bypassed_by_mapping_equality():
    class LyingMapping(dict):
        def __eq__(self, other):
            return True

    requirements = {"review": {"reports": False}}
    hostile_gates = LyingMapping({"review": {"reports": True}})
    with pytest.raises(GateError, match="conflitantes"):
        GatePolicy.from_dict({"requirements": requirements, "gates": hostile_gates})


def test_policy_none_defaults_and_serialization_round_trip():
    assert GatePolicy.from_dict(None).to_dict() == GatePolicy().to_dict()
    policy = GatePolicy.from_dict({"gates": {"review": {"reports": False}}, "default_requirements": {"owner": True}})
    assert GatePolicy.from_json(policy.to_json()).to_dict() == policy.to_dict()
