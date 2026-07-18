"""Fleet V2 adapter seam tests using only injected fake runtimes."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.contracts import AgentReportV2
from pd_fleet.checkpoint import Checkpoint
from pd_fleet.models import TaskSpec
from pd_fleet.orchestrator import FleetOrchestrator
from pd_fleet.orchestrator_provider import ProviderDispatchAdapter
from pd_fleet.provider import CommandMetadata, RuntimePolicy, RuntimeProviderProfile
from pd_fleet.provider_dispatch import DispatchStatus, ProviderDispatchBoundary
from pd_fleet.provider_routing import ProviderRoutePolicy
from pd_fleet.runtime_adapter import RuntimeErrorCode, RuntimeResult, RuntimeStatus


def _profile(name: str = "fake") -> RuntimeProviderProfile:
    return RuntimeProviderProfile(
        name, "runtime", "env:TEST_KEY", ("read",), CommandMetadata("/tool"),
        policy=RuntimePolicy(enabled=True, allowed_capabilities=("read",)),
    )


class _Adapter:
    def __init__(self, profile, result):
        self.name = f"{profile.provider_name}/{profile.runtime_name}"
        self.profile = profile
        self.result = result
        self.calls = 0
        self.envelope = None

    def build_argv(self, envelope):
        return ("trusted", envelope.task_id)

    def execute(self, envelope, *, runner):
        self.calls += 1
        self.envelope = envelope
        return self.result


def _task() -> TaskSpec:
    return TaskSpec("task", 2, "builder", "build the artifact", capabilities=["read"],
                    allowed_paths=["workspace"])


def test_provider_dispatch_adapter_returns_validated_report_and_safe_request():
    profile = _profile()
    runtime = _Adapter(profile, RuntimeResult(RuntimeStatus.OK, output="done token=secret"))
    boundary = ProviderDispatchBoundary(catalog=(profile,), adapters={"fake/runtime": runtime},
                                        runners={"fake/runtime": object()})
    adapter = ProviderDispatchAdapter(boundary, ProviderRoutePolicy(
        preferred_ids=("fake/runtime",), required_capabilities=("read",)), "run", "worker")

    report = adapter.run(_task(), {"task_id": "task", "attempt": 3, "lease_id": "lease-1", "owner": "worker", "generation": 0, "expires_at": "2999-01-01T00:00:00Z"})

    assert isinstance(report, AgentReportV2)
    assert report.status == "completed"
    assert report.attempt == 3
    assert report.outputs["runtime_output"] == "done [SECRET REDACTED]"
    assert dict(report.evidence)["status"] == "ok"
    assert dict(runtime.envelope.metadata) == {"lease_attempt": 3, "role": "builder", "wave": "2"}


def test_provider_failure_is_terminal_failure_without_boundary_fallback():
    profile = _profile()
    runtime = _Adapter(profile, RuntimeResult(RuntimeStatus.FAILED, "sandbox_failed"))
    boundary = ProviderDispatchBoundary(catalog=(profile,), adapters={"fake/runtime": runtime},
                                        runners={"fake/runtime": object()})
    adapter = ProviderDispatchAdapter(boundary, ProviderRoutePolicy(
        preferred_ids=("fake/runtime",), fallback_ids=(), allow_fallback=False,
        required_capabilities=("read",)), "run", "worker")

    report = adapter.run(_task(), {"task_id": "task", "attempt": 1, "lease_id": "lease-1", "owner": "worker", "generation": 0, "expires_at": "2999-01-01T00:00:00Z"})

    assert report.status == "failed"
    assert report.reason == "provider execution failed"
    assert report.error == "provider_failed"
    assert runtime.calls == 1


def test_invalid_lease_is_rejected_before_dispatch():
    profile = _profile()
    runtime = _Adapter(profile, RuntimeResult(RuntimeStatus.OK, output="must-not-run"))
    boundary = ProviderDispatchBoundary(catalog=(profile,), adapters={"fake/runtime": runtime},
                                        runners={"fake/runtime": object()})
    adapter = ProviderDispatchAdapter(boundary, ProviderRoutePolicy(
        preferred_ids=("fake/runtime",), required_capabilities=("read",)), "run", "worker",
        clock=lambda: "2026-01-01T00:00:00Z")
    valid = {"task_id": "task", "attempt": 1, "lease_id": "lease-1", "owner": "worker",
             "generation": 0, "expires_at": "2026-01-01T00:00:01Z"}
    cases = (
        ("task_id", "other", "invalid lease task"),
        ("owner", "other", "invalid lease owner"),
        ("run_id", "other-run", "invalid lease run"),
        ("expires_at", "2025-01-01T00:00:00Z", "expired lease"),
        ("lease_id", "../escape", "invalid lease id"),
        ("generation", -1, "invalid lease generation"),
        ("expires_at", "tomorrow", "invalid lease expiry"),
    )
    for key, value, error in cases:
        lease = dict(valid, **{key: value})
        with pytest.raises(ValueError, match=error):
            adapter.run(_task(), lease)
    assert runtime.calls == 0


_ORCH_PLAN = {"schema_version": "1", "tasks": [{
    "id": "task", "wave": "1", "role": "builder", "objective": "build",
    "acceptance_criteria": ["ok"], "outputs": ["result"],
    "validation_commands": ["declared"],
}]}


class _V2Scheduler:
    def __init__(self): self.claimed = False
    def ready_ids(self): return [] if self.claimed else ["task"]
    def claim(self, owner, *, limit):
        self.claimed = True
        return [{"task_id": "task", "lease_id": "lease-1", "generation": 0,
                 "expires_at": "2999-01-01T00:00:00Z"}]
    def release(self, token): return None


class _V2Executor:
    def run(self, tasks, runner, **kwargs):
        return [{"task_id": task_id, "status": "completed", "value": runner(task_id)}
                for task_id in tasks]


class _V2Store:
    def __init__(self): self.commits = []
    def load(self, run_id): return {"attempts": {"task": 1}}
    def commit(self, run_id, task_id, token, owner, value, *, status):
        self.commits.append((task_id, value, status))
    def append_event(self, run_id, event, owner): return None


def _run_provider_status(runtime_status):
    profile = _profile()
    error_code = (RuntimeErrorCode.CAPABILITY_DENIED.value if runtime_status is RuntimeStatus.BLOCKED
                  else RuntimeErrorCode.SANDBOX_FAILED.value)
    runtime = _Adapter(profile, RuntimeResult(runtime_status, error_code))
    boundary = ProviderDispatchBoundary(catalog=(profile,), adapters={"fake/runtime": runtime},
                                        runners={"fake/runtime": object()})
    policy = ProviderRoutePolicy(
        preferred_ids=() if runtime_status is RuntimeStatus.BLOCKED else ("fake/runtime",),
        required_capabilities=("read",))
    adapter = ProviderDispatchAdapter(boundary, policy, "run", "worker")
    scheduler, store = _V2Scheduler(), _V2Store()
    base = FleetOrchestrator(_ORCH_PLAN)
    context = {"plan_hash": base._plan_digest(base), "run_id": "run", "generation": 0,
               "owner": "worker", "checkpoint": Checkpoint.create(feature="test", wave=0).to_dict(),
               "leases": {}, "events": []}
    result = FleetOrchestrator(_ORCH_PLAN, scheduler=scheduler, store=store,
        executor=_V2Executor(), adapter=adapter, run_id="run", run_owner="worker",
        reconciliation_context=context).run()
    return result, store


def test_provider_failed_report_never_commits_completed():
    result, store = _run_provider_status(RuntimeStatus.FAILED)
    assert result.statuses == {"task": "failed"}
    assert [(task_id, status) for task_id, _, status in store.commits] == [("task", "failed")]
    assert store.commits[0][1]["reason"] == "provider execution failed"


def test_provider_blocked_report_commits_blocked_with_blocker_evidence():
    result, store = _run_provider_status(RuntimeStatus.BLOCKED)
    assert result.statuses == {"task": "blocked"}
    assert [(task_id, status) for task_id, _, status in store.commits] == [("task", "blocked")]
    report = store.commits[0][1]
    assert report["blocker"]["dispatch_status"] in {"blocked", "no_provider"}
    assert report["evidence"]["status"] == "no_provider"
