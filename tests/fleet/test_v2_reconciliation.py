import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.checkpoint import Checkpoint, DurableCheckpointStore
from pd_fleet.contracts import plan_hash
from pd_fleet.orchestrator import FleetOrchestrator
from pd_fleet.models import FleetPlan


def task(task_id="a"):
    return {"id": task_id, "wave": 1, "role": "coder", "objective": task_id,
            "allowed_paths": [f"x/{task_id}"], "outputs": ["out"],
            "acceptance_criteria": ["ok"], "validation_commands": ["check"]}


class CountingDispatcher:
    def __init__(self):
        self.calls = 0

    def dispatch(self, task, context):
        self.calls += 1
        raise AssertionError("blocked reconciliation must dispatch zero adapters")


class SuccessDispatcher:
    def __init__(self):
        self.calls = 0

    def dispatch(self, task, context):
        self.calls += 1
        return {"status": "completed", "result": {"out": "ok"}, "evidence": {"ok": True, "acceptance": True}}


def make_context(plan, **extra):
    runtime = FleetPlan.from_dict(plan).to_dict()
    runtime["schema_version"] = "pd-fleet-plan:v2"
    checkpoint = Checkpoint.create(
        feature="demo", wave=1, tasks={"a": {"id": "a"}}, lifecycle={}
    ).to_dict()
    value = {"plan_hash": plan_hash(runtime),
             "run_id": "run-demo", "generation": 2, "expected_generation": 2,
             "owner": "owner", "schema_version": "1", "leases": {}, "events": [],
             "checkpoint": checkpoint}
    value.update(extra)
    return value


def test_reconciliation_blocks_dispatch_before_any_adapter_call():
    dispatcher = CountingDispatcher()
    plan = {"tasks": [task()]}
    context = make_context(plan, plan_hash="0" * 64)
    result = FleetOrchestrator(plan, dispatcher=dispatcher, reconciliation_context=context).run()
    assert dispatcher.calls == 0
    assert result.blocked == ("a",)
    assert result.reports[0]["status"] == "blocked"


def test_reconciliation_detects_drift_lease_orphan_events_and_checkpoint():
    plan = {"tasks": [task()]}
    context = make_context(plan, generation=3, expected_generation=2,
        leases={"a": {"generation": 1}}, snapshots={"a": {"status": "running"}},
        events=[{"sequence": 1}, {"sequence": 1}], checkpoint={"schema_version": "pd-fleet-checkpoint:v2"})
    result = FleetOrchestrator(plan, reconciliation_context=context).reconcile(context)
    codes = {issue["code"] for issue in result.issues}
    assert not result.valid
    assert {"stale_generation", "stale_lease", "orphan_running_task",
            "event_sequence_invalid", "checkpoint_invalid"} <= codes


def test_reconciliation_accepts_v1_and_valid_v2_checkpoint_with_one_dispatch(tmp_path):
    plan = {"tasks": [task()]}
    context = make_context(plan)
    v1 = context["checkpoint"]
    v2 = DurableCheckpointStore(tmp_path).save(
        context["run_id"], Checkpoint.from_dict(v1),
        plan_hash=context["plan_hash"], generation=context["generation"],
    )
    for checkpoint in (v1, v2):
        dispatcher = SuccessDispatcher()
        context = make_context(plan, checkpoint=checkpoint)
        result = FleetOrchestrator(plan, dispatcher=dispatcher, reconciliation_context=context).run()
        assert result.completed == ("a",)
        assert dispatcher.calls == 1


def test_reconciliation_blocks_minimal_or_forged_checkpoint():
    plan = {"tasks": [task()]}
    context = make_context(plan)
    minimal = {"schema_version": 1, "lifecycle": {}}
    forged = {
        "schema_version": "pd-fleet-checkpoint:v2", "run_id": context["run_id"],
        "plan_hash": context["plan_hash"], "generation": context["generation"],
        "checkpoint": context["checkpoint"], "checksum": "0" * 64,
    }
    for checkpoint in (minimal, forged):
        dispatcher = CountingDispatcher()
        result = FleetOrchestrator(
            plan, dispatcher=dispatcher,
            reconciliation_context=make_context(plan, checkpoint=checkpoint),
        ).run()
        assert dispatcher.calls == 0
        assert result.blocked == ("a",)
        assert result.reports[0]["status"] == "blocked"
        assert result.reports[0]["reconciliation"]["valid"] is False


def test_reconciliation_invalid_types_are_sanitized_deterministic_and_no_mutation():
    plan = {"tasks": [task()]}
    context = make_context(plan, owner=object(), events=[{"sequence": object()}])
    before = copy.deepcopy(context)
    first = FleetOrchestrator(plan, reconciliation_context=context).reconcile(context).to_dict()
    second = FleetOrchestrator(plan, reconciliation_context=context).reconcile(context).to_dict()
    assert first == second
    assert context["owner"].__class__ is object and context["events"][0]["sequence"].__class__ is object
    assert context["owner"] is not before["owner"]
    assert not first["valid"] and all(set(issue) <= {"code", "reason", "task_id"} for issue in first["issues"])


def test_strict_v2_lease_owner_mismatch_blocks_without_dispatch():
    plan = {"tasks": [task()]}
    dispatcher = CountingDispatcher()
    context = make_context(plan, leases={"a": {"lease_id": "lease-a", "owner": "other", "generation": 2}})
    orchestrator = FleetOrchestrator(plan, dispatcher=dispatcher, reconciliation_context=context)

    result = orchestrator.reconcile(context)

    assert not result.valid
    assert [issue["code"] for issue in result.issues] == ["lease_owner_mismatch"]
    assert orchestrator.run().blocked == ("a",)
    assert dispatcher.calls == 0


def test_strict_v2_stale_lease_generation_blocks_without_dispatch():
    plan = {"tasks": [task()]}
    dispatcher = CountingDispatcher()
    context = make_context(plan, leases={"a": {"lease_id": "lease-a", "owner": "owner", "generation": 1}})
    orchestrator = FleetOrchestrator(plan, dispatcher=dispatcher, reconciliation_context=context)

    result = orchestrator.reconcile(context)

    assert not result.valid
    assert [issue["code"] for issue in result.issues] == ["stale_lease"]
    assert orchestrator.run().blocked == ("a",)
    assert dispatcher.calls == 0


def test_strict_v2_empty_and_matching_leases_are_valid_and_dispatch():
    plan = {"tasks": [task()]}
    for leases in ({}, {"a": {"lease_id": "lease-a", "owner": "owner", "generation": 2}}):
        dispatcher = SuccessDispatcher()
        context = make_context(plan, leases=leases)
        orchestrator = FleetOrchestrator(plan, dispatcher=dispatcher, reconciliation_context=context)

        result = orchestrator.reconcile(context)

        assert result.valid
        assert orchestrator.run().completed == ("a",)
        assert dispatcher.calls == 1


def test_reconciliation_owner_and_schema_mismatch_blocks():
    plan = {"tasks": [task()]}
    context = make_context(plan, owner="other", expected_owner="owner", schema_version="bad")
    result = FleetOrchestrator(plan, reconciliation_context=context).reconcile(context)
    assert {"owner_mismatch", "schema_mismatch"} <= {issue["code"] for issue in result.issues}


def test_strict_v2_requires_nonempty_top_level_owner_without_dispatch():
    plan = {"tasks": [task()]}
    dispatcher = CountingDispatcher()
    for owner in (None, ""):
        context = make_context(plan)
        if owner is None:
            del context["owner"]
        else:
            context["owner"] = owner
        orchestrator = FleetOrchestrator(plan, dispatcher=dispatcher, reconciliation_context=context)

        result = orchestrator.reconcile(context)

        assert not result.valid
        assert any(issue["code"] in {"missing_owner", "owner_invalid"} for issue in result.issues)
        assert orchestrator.run().blocked == ("a",)
    assert dispatcher.calls == 0


def test_strict_v2_rejects_lease_for_task_not_in_loaded_plan_without_dispatch():
    plan = {"tasks": [task()]}
    dispatcher = CountingDispatcher()
    context = make_context(plan, leases={"not-in-plan": {
        "lease_id": "lease-x", "owner": "owner", "generation": 2,
    }})
    orchestrator = FleetOrchestrator(plan, dispatcher=dispatcher, reconciliation_context=context)

    result = orchestrator.reconcile(context)

    assert not result.valid
    assert [issue["code"] for issue in result.issues] == ["lease_task_mismatch"]
    assert orchestrator.run().blocked == ("a",)
    assert dispatcher.calls == 0


def test_v1_context_with_ambiguous_reconciliation_keys_is_not_auto_promoted():
    plan = {"tasks": [task()]}
    dispatcher = SuccessDispatcher()
    context = {"checkpoint": "ordinary-v1-input", "persisted_run": {"status": "running"},
               "plan_hash": "ordinary-value"}

    result = FleetOrchestrator(plan, dispatcher=dispatcher, context=context).run()

    assert result.completed == ("a",)
    assert dispatcher.calls == 1
