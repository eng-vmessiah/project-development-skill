"""T2-14 integration contract: workers are pure, commits are canonical."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.orchestrator import FleetOrchestrator
from pd_fleet.checkpoint import Checkpoint


PLAN = {"schema_version": "1", "tasks": [
    {"id": "b", "wave": "1", "role": "worker", "objective": "b", "acceptance_criteria": ["ok"], "outputs": ["result"], "validation_commands": ["declared"]},
    {"id": "a", "wave": "1", "role": "worker", "objective": "a", "acceptance_criteria": ["ok"], "outputs": ["result"], "validation_commands": ["declared"]},
]}


def report(task_id):
    return {"schema_version": "pd-fleet-report:v2", "task_id": task_id,
            "attempt": 1, "agent_id": "agent", "role": "worker", "capabilities": [],
            "status": "completed", "outputs": {"result": task_id}, "evidence": {"proof": task_id},
            "tests": {"passed": True}, "validation": {"passed": True}, "decision": {"accepted": True},
            "started_at": "2026-01-01T00:00:00Z", "completed_at": "2026-01-01T00:00:01Z"}


class Scheduler:
    def __init__(self): self.claimed = False
    def ready_ids(self): return [] if self.claimed else ["a", "b"]
    def claim(self, owner, *, limit):
        self.claimed = True
        return [{"task_id": x, "lease_id": x, "generation": 1} for x in ("a", "b")]
    def release(self, token): pass


class Executor:
    def run(self, tasks, runner, **kwargs):
        # Deliberately return completion in reverse order.
        return [{"task_id": task_id, "status": "completed", "value": runner(task_id)}
                for task_id in reversed(list(tasks))]


class Store:
    def __init__(self, *, fail_events=False): self.commits = []; self.events = []; self.fail_events = fail_events
    def load(self, run_id): return {"attempts": {"a": 1, "b": 1}}
    def commit(self, run_id, task_id, token, owner, value, *, status):
        self.commits.append((task_id, value, status))
    def append_event(self, run_id, event, owner):
        if self.fail_events: raise RuntimeError("event token=super-secret /home/private")
        self.events.append(event)


def reconciliation_context():
    loaded = FleetOrchestrator(PLAN)
    return {"plan_hash": loaded._plan_digest(loaded), "run_id": "run", "generation": 0,
            "owner": "owner", "checkpoint": Checkpoint.create(feature="test", wave=0).to_dict(),
            "leases": {}, "events": []}


def run_once(*, fail_events=False):
    store = Store(fail_events=fail_events)
    result = FleetOrchestrator(PLAN, max_parallel=2, scheduler=Scheduler(), store=store,
        executor=Executor(), adapter=lambda task, token: report(task.id), run_id="run", run_owner="owner",
        reconciliation_context=reconciliation_context()).run()
    return result.to_dict(), store


def test_completion_order_is_not_persisted_order():
    output, store = run_once()
    assert [task_id for task_id, _, _ in store.commits] == ["a", "b"]
    assert [event["task_id"] for event in store.events] == ["a", "b"]
    assert output["statuses"] == {"a": "completed", "b": "completed"}


def test_workers_do_not_receive_store_capability():
    output, store = run_once()
    assert len(store.commits) == 2
    assert output["waves"] == [["a", "b"]]


def test_event_failure_does_not_reclassify_or_recommit_terminal_completion():
    output, store = run_once(fail_events=True)
    assert output["statuses"] == {"a": "completed", "b": "completed"}
    assert len(store.commits) == 2
    assert all(status == "completed" for _, _, status in store.commits)
    assert all("super-secret" not in str(report) and "/home/private" not in str(report)
               for report in output["reports"])
    assert all("event_persistence_warning" in report for report in output["reports"])


def test_injected_v2_run_requires_context_before_claim():
    scheduler = Scheduler()
    result = FleetOrchestrator(
        PLAN, scheduler=scheduler, store=Store(), executor=Executor(),
        adapter=lambda task, token: report(task.id), run_id="run", run_owner="owner",
    ).run()
    assert set(result.blocked) == {"a", "b"}
    assert scheduler.claimed is False


def test_run_v2_requires_context_before_claim():
    scheduler = Scheduler()
    orchestrator = FleetOrchestrator(
        PLAN, scheduler=scheduler, store=Store(), executor=Executor(),
        adapter=lambda task, token: report(task.id), run_id="run", run_owner="owner",
    )
    result = orchestrator.run_v2()
    assert set(result.blocked) == {"a", "b"}
    assert scheduler.claimed is False
