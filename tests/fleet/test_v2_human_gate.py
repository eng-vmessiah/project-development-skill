import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.gates import (  # noqa: E402
    GateError,
    GateStatus,
    HumanDecision,
    HumanVerificationGate,
)

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
DIGEST = "a" * 64


def approved(**overrides):
    data = dict(
        owner="release-owner",
        identity="alice@example.test",
        decision=HumanDecision.APPROVED,
        scope="release",
        run="run-42",
        evidence_digest=DIGEST,
        artifact_digest="b" * 64,
        created_at=NOW,
        updated_at=NOW,
        freshness_window=timedelta(hours=1),
        blockers=(),
    )
    data.update(overrides)
    return HumanVerificationGate(**data)


def test_identity_decision_digest_and_freshness_are_required():
    for field, value in (("owner", ""), ("identity", ""), ("evidence_digest", "bad"), ("scope", ""), ("run", "")):
        with pytest.raises(GateError):
            approved(**{field: value})
    with pytest.raises(GateError):
        approved(freshness_window=timedelta(0))
    assert approved().allows(now=NOW, expected_run="run-42", expected_scope="release")


def test_only_explicit_approved_allows_and_rejected_pending_fail_closed():
    assert approved(decision="APPROVED").decision is HumanDecision.APPROVED
    context = {"now": NOW, "expected_run": "run-42", "expected_scope": "release"}
    assert not approved(decision=HumanDecision.PENDING).allows(**context)
    assert not approved(decision=HumanDecision.REJECTED).allows(**context)
    with pytest.raises(GateError):
        approved(decision="approve")


def test_stale_evidence_and_changed_artifact_reopen_gate():
    gate = approved()
    context = {"expected_run": "run-42", "expected_scope": "release"}
    assert gate.evaluate(now=NOW + timedelta(hours=1, seconds=1), **context) is GateStatus.PENDING
    assert gate.evaluate(now=NOW, artifact_digest="c" * 64, **context) is GateStatus.PENDING
    assert not gate.allows(now=NOW, artifact_digest="c" * 64, **context)


def test_allows_does_not_replace_explicit_falsey_digests_with_stored_values():
    gate = approved()
    context = {"now": NOW, "expected_run": "run-42", "expected_scope": "release"}
    assert gate.allows(**context)
    assert not gate.allows(artifact_digest="", **context)
    assert not gate.allows(evidence_digest="", **context)


def test_blocker_metadata_is_trimmed_casefolded_and_unknown_fails_closed():
    context = {"now": NOW, "expected_run": "run-42", "expected_scope": "release"}
    assert approved(blockers=({"severity": "  HIGH ", "status": " pending "},)).evaluate(**context) is GateStatus.BLOCKED
    assert approved(blockers=({"severity": " high ", "status": " RESOLVED "},)).allows(**context)
    assert approved(blockers=({"severity": "mystery", "status": "open"},)).evaluate(**context) is GateStatus.BLOCKED
    assert approved(blockers=({"severity": "high", "status": "mystery"},)).evaluate(**context) is GateStatus.BLOCKED


def test_blocker_or_high_severity_blocks_even_with_approval():
    context = {"now": NOW, "expected_run": "run-42", "expected_scope": "release"}
    for severity in ("BLOCKER", "HIGH"):
        gate = approved(blockers=({"severity": severity, "status": "OPEN"},))
        assert gate.evaluate(**context) is GateStatus.BLOCKED
        assert not gate.allows(**context)
    assert approved(blockers=({"severity": "HIGH", "status": "RESOLVED"},)).allows(**context)


def test_expected_run_and_scope_are_required_and_must_match():
    gate = approved(scope={"tasks": ["task-a", "task-b"]})
    assert gate.allows(now=NOW, expected_run="run-42", expected_scope={"tasks": ["task-b", "task-a"]})
    assert gate.evaluate(now=NOW, expected_run="another-run", expected_scope={"tasks": ["task-a", "task-b"]}) is GateStatus.PENDING
    assert gate.evaluate(now=NOW, expected_run="run-42", expected_scope={"tasks": ["task-a", "other"]}) is GateStatus.PENDING


def test_missing_expected_context_fails_closed_without_auto_approval():
    gate = approved()
    assert gate.evaluate(now=NOW) is GateStatus.PENDING
    assert gate.evaluate(now=NOW, expected_run="run-42") is GateStatus.PENDING
    assert not gate.allows(now=NOW, expected_scope="release")


def test_stale_digest_and_freshness_mismatch_fail_closed_with_matching_context():
    context = {"now": NOW, "expected_run": "run-42", "expected_scope": "release"}
    gate = approved()
    assert gate.evaluate(evidence_digest="c" * 64, **context) is GateStatus.PENDING
    assert gate.evaluate(artifact_digest="c" * 64, **context) is GateStatus.PENDING
    assert gate.evaluate(now=NOW + timedelta(hours=1, seconds=1), expected_run="run-42", expected_scope="release") is GateStatus.PENDING


def test_gate_is_deeply_immutable_and_serialization_deterministic():
    scope = {"tasks": ["T1"]}
    gate = approved(scope=scope)
    scope["tasks"].append("T2")
    assert gate.scope["tasks"] == ("T1",)
    with pytest.raises(TypeError):
        gate.scope["tasks"] += ("T2",)
    assert gate.to_json() == gate.to_json()
    assert HumanVerificationGate.from_json(gate.to_json()) == gate


def test_timestamps_must_be_utc_and_updated_not_before_created():
    with pytest.raises(GateError):
        approved(created_at=NOW.replace(tzinfo=None))
    with pytest.raises(GateError):
        approved(updated_at=NOW - timedelta(seconds=1))


def test_from_dict_rejects_unknown_and_conflicting_alias_fields():
    payload = approved().to_dict()
    assert HumanVerificationGate.from_dict({**payload, "run_id": payload["run"]}) == approved()
    with pytest.raises(GateError):
        HumanVerificationGate.from_dict({**payload, "unexpected": True})
    with pytest.raises(GateError):
        HumanVerificationGate.from_dict({**payload, "run_id": "different"})


def test_from_dict_rejects_hostile_mapping_at_the_boundary():
    class Hostile(dict):
        def __iter__(self):
            raise RuntimeError("hostile iteration")

    with pytest.raises(GateError):
        HumanVerificationGate.from_dict(Hostile(approved().to_dict()))


def test_from_dict_rejects_hostile_nested_scope_mapping():
    class Hostile(dict):
        def items(self):
            raise RuntimeError("hostile items")

    payload = approved().to_dict()
    payload["scope"] = Hostile({"plan_hash": "safe"})
    with pytest.raises(GateError):
        HumanVerificationGate.from_dict(payload)


def test_from_dict_rejects_hostile_nested_blocker_mapping():
    class Hostile(dict):
        def items(self):
            raise RuntimeError("hostile items")

    payload = approved().to_dict()
    payload["blockers"] = [Hostile({"severity": "low", "status": "resolved"})]
    with pytest.raises(GateError):
        HumanVerificationGate.from_dict(payload)


def test_human_gate_injected_clock_is_used_once_only_when_now_is_omitted():
    calls = []

    def clock():
        calls.append(1)
        return NOW

    gate = approved(clock=clock)
    assert gate.allows(expected_run="run-42", expected_scope="release")
    assert calls == [1]
    assert gate.allows(now=NOW, expected_run="run-42", expected_scope="release")
    assert calls == [1]
