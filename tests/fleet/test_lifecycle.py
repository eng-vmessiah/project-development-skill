import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.lifecycle import (  # noqa: E402
    CompletionError,
    GatePolicy,
    InvalidTransition,
    LifecycleState,
    RetryExhausted,
    TaskLifecycle,
)


def running(max_attempts=2):
    task = TaskLifecycle("T3", max_attempts=max_attempts)
    task.mark_ready().start("agent-a", now=100)
    return task


def test_all_happy_path_transitions():
    task = TaskLifecycle("T1")
    assert task.state is LifecycleState.PENDING
    task.mark_ready().start("a", now=10)
    task.complete(["out"], ["report"], now=11)
    assert task.state is LifecycleState.COMPLETED
    assert task.attempt == 1


@pytest.mark.parametrize("operation", ["mark_ready", "start", "retry", "block", "skip"])
def test_invalid_terminal_transition(operation):
    task = running()
    task.complete(["out"], ["evidence"])
    with pytest.raises(InvalidTransition):
        if operation == "start":
            task.start("a")
        elif operation == "complete":
            task.complete(["out"], ["evidence"])
        elif operation == "retry":
            task.retry()
        elif operation == "block":
            task.block("x")
        elif operation == "skip":
            task.skip("x")
        else:
            getattr(task, operation)()


def test_completion_requires_outputs_and_evidence_and_is_idempotent():
    task = running()
    with pytest.raises(CompletionError):
        task.complete([], ["evidence"])
    task.complete({"artifact": "x"}, {"path": "report"})
    task.complete([], [])
    assert task.outputs == {"artifact": "x"}


def test_retry_is_explicit_and_bounded():
    task = running(max_attempts=2)
    task.fail("temporary")
    assert task.state is LifecycleState.FAILED
    assert task.retryable is True
    with pytest.raises(InvalidTransition):
        task.start("a")
    task.retry().start("a")
    assert task.attempt == 2
    task.fail("again")
    with pytest.raises(RetryExhausted):
        task.retry()


def test_non_retryable_failure_is_persisted_and_cannot_retry():
    task = running(max_attempts=3)
    task.fail("permanent", retryable=False)
    assert task.retryable is False
    with pytest.raises(RetryExhausted, match="não é retryable"):
        task.retry()


def test_blocked_has_no_retry_exit():
    task = TaskLifecycle("T1")
    task.block("G1 not passed")
    with pytest.raises(InvalidTransition):
        task.retry()


def test_orphan_recovery_uses_heartbeat_timeout():
    task = running()
    task.final_report = {"status": "in-progress"}
    assert task.recover_orphan(now=399, timeout_seconds=300) is False
    assert task.recover_orphan(now=400, timeout_seconds=300) is True
    assert task.state is LifecycleState.FAILED
    assert task.reason == "orphaned_run"


def test_orphan_recovery_covers_missing_final_report_even_with_recent_heartbeat():
    task = running()
    task.beat(now=399)
    assert task.recover_orphan(now=400, timeout_seconds=300) is True
    assert task.error == "orphaned_run"


def test_gate_policy_blocks_until_all_required_gates_pass():
    policy = GatePolicy.from_gates([{"id": "G1", "status": "pending"}, {"id": "G2", "status": "passed"}])
    gates = {"G1": {"status": "pending"}, "G2": {"status": "passed"}}
    assert policy.allows(gates) is False
    assert policy.blocked_by(gates) == ("G1",)
    gates["G1"] = {"status": "passed"}
    assert policy.allows(gates) is True


def test_gate_policy_can_block_pending_task():
    task = TaskLifecycle("T1")
    GatePolicy(("G1",)).require_ready(task, {"G1": {"status": "failed"}})
    assert task.state is LifecycleState.BLOCKED
    assert task.reason is not None and "G1" in task.reason


def test_gate_policy_validates_contract_fields_and_requires_exact_passed():
    policy = GatePolicy(("G1",))
    contract = {"status": "passed", "evidence": ["log"], "owner": "a", "decision": "go", "blockers": []}
    assert policy.allows({"G1": contract}) is True
    for key, value in (("evidence", []), ("owner", ""), ("decision", None), ("blockers", ["issue"])):
        invalid = dict(contract, **{key: value})
        assert policy.allows({"G1": invalid}) is False
    assert policy.allows({"G1": dict(contract, status="PASS")}) is False


def test_gate_policy_promotes_pending_task_when_gates_pass():
    task = TaskLifecycle("T1")
    GatePolicy(("G1",)).require_ready(task, {"G1": {"status": "passed"}})
    assert task.state is LifecycleState.READY
