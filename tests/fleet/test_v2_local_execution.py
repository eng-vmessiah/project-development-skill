import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.orchestrator import FleetOrchestrator
from pd_fleet.dispatch import Dispatcher, DispatchResult, AdapterDeniedError, UnknownAdapterError


def task(i="a"):
    return {"id": i, "role": "coder", "objective": i, "allowed_paths": [f"x/{i}"],
            "outputs": ["out"], "acceptance_criteria": ["ok"], "validation_commands": ["check"]}


def v2_plan():
    return {"schema_version": "pd-fleet-plan:v2", "run_id": "r", "tasks": [task() | {"wave": 1}]}


def test_local_v2_execution_has_no_external_side_effect_and_commits_once():
    commits = []
    hooks = type("Hooks", (), {"commit_report": lambda self, report: commits.append(report)})()
    result = FleetOrchestrator(v2_plan(), hooks=hooks).run()
    assert result.completed == ("a",)
    assert len(commits) == 1
    assert commits[0]["schema_version"] == "pd-fleet-report:v2"
    assert commits[0]["status"] == "completed"
    assert commits[0]["task_id"] == "a"


def test_v1_calls_both_lifecycle_hook_names_when_both_are_present():
    calls = []

    class Hooks:
        def lifecycle(self, life):
            calls.append(("lifecycle", life.status))

        def on_lifecycle(self, life):
            calls.append(("on_lifecycle", life.status))

    result = FleetOrchestrator({"tasks": [task() | {"wave": 1}]}, hooks=Hooks()).run()

    assert result.completed == ("a",)
    names = [name for name, _status in calls]
    assert names[::2] == ["lifecycle"] * (len(calls) // 2)
    assert names[1::2] == ["on_lifecycle"] * (len(calls) // 2)
    assert [status for _name, status in calls[::2]] == [
        status for _name, status in calls[1::2]
    ]


def test_v2_uses_one_canonical_lifecycle_hook_when_both_are_present():
    lifecycle_calls = []
    alias_calls = []
    commits = []

    class Hooks:
        def lifecycle(self, life):
            lifecycle_calls.append(life.status)

        def on_lifecycle(self, life):
            alias_calls.append(life.status)

        def commit_report(self, report):
            commits.append(report)

    result = FleetOrchestrator(v2_plan(), hooks=Hooks()).run()

    assert result.completed == ("a",)
    assert lifecycle_calls
    assert alias_calls == []
    assert len(commits) == 1


def test_v2_incomplete_report_is_rejected_and_never_committed():
    commits = []
    class Incomplete:
        def dispatch(self, task, context):
            return DispatchResult(task.id, "simulated", "completed", context["attempt"],
                                  {"report": {"status": "completed"}}, {"local": True})
    hooks = type("Hooks", (), {"commit_report": lambda self, report: commits.append(report)})()
    result = FleetOrchestrator(v2_plan(), dispatcher=Incomplete(), hooks=hooks).run()
    assert result.failed == ("a",)
    assert commits == []


def test_dispatcher_remains_default_deny_for_external_adapter():
    dispatcher = Dispatcher(routes={"coder": "provider"})
    try:
        dispatcher.dispatch(task())
    except (AdapterDeniedError, UnknownAdapterError):
        pass
    else:
        raise AssertionError("external adapter was not denied")


def test_v2_invalid_first_attempt_retries_only_when_policy_allows():
    calls = []
    class Retry:
        def dispatch(self, task, context):
            calls.append(context["attempt"])
            if len(calls) == 1:
                return DispatchResult(task.id, "simulated", "completed", context["attempt"],
                                      {"report": {}}, {"local": True})
            return Dispatcher().dispatch(task, {"attempt": context["attempt"], "report_v2": True})
    plan = v2_plan()
    plan["tasks"][0]["retry_policy"] = {"max_attempts": 2, "backoff_seconds": 0}
    result = FleetOrchestrator(plan, dispatcher=Retry(),
                               hooks=type("Hooks", (), {
                                   "commit_report": lambda self, report: None,
                               })()).run()
    assert result.completed == ("a",)
    assert calls == [1, 2]
