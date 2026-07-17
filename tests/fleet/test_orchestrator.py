import sys
import math
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.dispatch import (  # noqa: E402
    AdapterDeniedError,
    Dispatcher,
    UnknownAdapterError,
)
from pd_fleet.orchestrator import FleetOrchestrator, OrchestratorError  # noqa: E402
from pd_fleet.checkpoint import Checkpoint  # noqa: E402
from pd_fleet.validation import FleetValidationError  # noqa: E402


def task(i, wave=1, deps=(), path=None):
    return {"id": i, "wave": wave, "role": "coder", "objective": i,
            "depends_on": list(deps), "allowed_paths": [path or f"x/{i}"],
            "outputs": ["out"], "acceptance_criteria": ["ok"],
            "validation_commands": ["check"]}


def test_simulated_dag_and_idempotent_resume():
    plan = {"tasks": [task("b", 2, ["a"]), task("a")]}
    first = FleetOrchestrator(plan).run()
    assert first.completed == ("a", "b")
    checkpoint = {"feature": "x", "wave": 1, "tasks": {"a": {"id": "a"}},
                  "lifecycle": {"a": {"task_id": "a", "status": "completed", "attempt": 1}},
                  "reports": [], "evidence": [], "blockers": []}
    resumed = FleetOrchestrator(plan, checkpoint=checkpoint).run()
    assert resumed.completed == ("a", "b")


def test_hook_snapshot_is_checkpoint_roundtrippable_and_resumable():
    snapshots = []
    hooks = type("Hooks", (), {"checkpoint": lambda self, value: snapshots.append(value)})()
    plan = {"tasks": [task("a"), task("b", 2, ["a"])]}

    result = FleetOrchestrator(plan, hooks=hooks, feature="feature/snapshot",
                               created_at="2026-01-01T00:00:00+00:00").run()
    assert result.completed == ("a", "b")
    snapshot = snapshots[-1]
    restored = Checkpoint.from_dict(snapshot)
    assert restored.feature == "feature/snapshot"
    assert restored.wave == restored.to_dict()["wave"] == 2
    assert restored.created_at == "2026-01-01T00:00:00+00:00"
    assert snapshot["schema_version"] == 1
    assert {"tasks", "lifecycle", "reports", "evidence", "blockers"} <= set(snapshot)
    assert {"attempts", "gates", "agents"} <= set(snapshot)
    assert FleetOrchestrator(plan, checkpoint=restored).run().completed == ("a", "b")


def test_parallel_batches_are_deterministic_and_bounded():
    plan = {"tasks": [task("c"), task("a"), task("b")]}
    result = FleetOrchestrator(plan, max_parallel=2).run()
    assert result.waves == [("a", "b"), ("c",)]


def test_gate_blocks_and_dry_run_does_not_change_lifecycle():
    plan = {"waves": [{"id": "wave-1", "gates": ["review"]}],
            "gates": [{"id": "review", "status": "pending"}], "tasks": [task("a")]}
    blocked = FleetOrchestrator(plan).run()
    assert blocked.blocked == ("a",)
    dry = FleetOrchestrator({"tasks": [task("a")]}, dry_run=True)
    result = dry.run()
    assert dry.lifecycles["a"].status == "pending"
    assert result.reports[0]["reason"] == "dry_run"


def test_timeout_and_checkpoint_hook_and_blocked_dependency():
    from pd_fleet.dispatch import DispatchResult

    class Slow:
        def dispatch(self, task, context):
            return DispatchResult(task.id, "simulated", "completed", context["attempt"], {"ok": 1}, {"ok": 1})

    ticks = iter([0.0, 2.0, 2.0])
    snapshots = []
    plan = {"tasks": [task("a"), task("b", deps=["a"])]}
    result = FleetOrchestrator(plan, dispatcher=Slow(), timeout_seconds=1,
                               clock=lambda: next(ticks), hooks=type("H", (), {"checkpoint": lambda self, x: snapshots.append(x)})()).run()
    assert result.failed == ("a",)
    assert result.blocked == ("b",)
    assert snapshots


def test_default_deny_external_dispatch():
    dispatcher = Dispatcher(routes={"coder": "external"})
    try:
        dispatcher.dispatch(task("a"))
    except (AdapterDeniedError, UnknownAdapterError):
        pass
    else:
        raise AssertionError("external adapter must be denied")


def test_invalid_plan_is_validated_before_resume_or_lifecycle_mutation():
    invalid = {"tasks": [task("a")], "waves": [{"id": "wave-1", "gates": ["missing"]}]}
    try:
        FleetOrchestrator(invalid, checkpoint={"feature": "x", "wave": 1,
            "tasks": {"a": {"id": "a"}}, "lifecycle": {}, "reports": [],
            "evidence": [], "blockers": []})
    except FleetValidationError:
        pass
    else:
        raise AssertionError("invalid plan must be rejected during construction")


def test_status_only_declared_plan_gate_does_not_authorize():
    plan = {"waves": [{"id": "wave-1", "gates": ["review"]}],
            "gates": [{"id": "review", "status": "passed"}], "tasks": [task("a")]}
    result = FleetOrchestrator(plan).run()
    assert result.blocked == ("a",)
    assert result.to_dict()["validation"] is not None


def test_dispatch_error_is_sanitized_everywhere():
    from pd_fleet.dispatch import DispatchResult

    class Leaky:
        def dispatch(self, task, context):
            return DispatchResult(task.id, "x", "failed", context["attempt"],
                                  error="token=TOPSECRET https://secret.example/x")

    result = FleetOrchestrator({"tasks": [task("a")]}, dispatcher=Leaky()).run()
    text = repr(result.reports)
    assert "TOPSECRET" not in text
    assert "secret.example" not in text
    assert "[redacted-secret]" in text and "[redacted-url]" in text


def test_timeout_seconds_requires_finite_nonnegative_number():
    for value in (-1, math.nan, math.inf, "1", True):
        try:
            FleetOrchestrator({"tasks": [task("a")]}, timeout_seconds=value)
        except OrchestratorError:
            pass
        else:
            raise AssertionError(f"invalid timeout accepted: {value!r}")


def test_declared_agent_matching_role_and_capabilities_dispatches():
    plan = {"agents": [{"id": "a1", "role": "coder", "capabilities": ["python", "tests"]}],
            "tasks": [task("a") | {"capabilities": ["python"], "owner": "a1"}]}
    assert FleetOrchestrator(plan).run().completed == ("a",)


def test_declared_agents_unknown_role_blocks_before_dispatch():
    calls = []
    class NeverDispatch:
        def dispatch(self, task, context):
            calls.append(task.id)
            raise AssertionError("incompatible task must not dispatch")
    result = FleetOrchestrator(
        {"agents": [{"id": "a1", "role": "coder"}], "tasks": [task("a") | {"role": "reviewer"}]},
        dispatcher=NeverDispatch()).run()
    assert result.blocked == ("a",) and calls == []
    assert "nenhum agente compatível" in result.reports[0]["reason"]
    assert result.reports[0]["evidence"]["agent_matching"]["role"] == "reviewer"


def test_declared_agents_incompatible_capability_blocks():
    result = FleetOrchestrator(
        {"agents": [{"id": "a1", "role": "coder", "capabilities": ["python"]}],
         "tasks": [task("a") | {"capabilities": ["rust"]}]}).run()
    assert result.blocked == ("a",)
    assert "capabilities" in result.reports[0]["reason"]


def test_declared_agents_incompatible_owner_blocks_even_when_other_agent_matches():
    result = FleetOrchestrator(
        {"agents": [{"id": "a1", "role": "coder", "capabilities": ["python"]},
                    {"id": "a2", "role": "coder", "capabilities": ["python"]}],
         "tasks": [task("a") | {"capabilities": ["python"], "owner": "missing"}]}).run()
    assert result.blocked == ("a",)
    assert "owner incompatível" in result.reports[0]["reason"]


def test_empty_or_absent_agents_preserve_simulated_dispatch():
    for plan in ({"tasks": [task("a")]}, {"agents": [], "tasks": [task("a")]}):
        assert FleetOrchestrator(plan).run().completed == ("a",)
