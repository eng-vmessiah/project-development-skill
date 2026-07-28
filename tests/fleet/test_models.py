import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.models import (  # noqa: E402
    FleetPlan,
    FleetPlanError,
    RetryPolicy,
    TaskSpec,
)


MIN_TASK = {"id": "T-1", "wave": 1, "role": "coder", "objective": "build it"}


class _HostileRepr:
    def __repr__(self):
        raise AssertionError("repr must not be called")


def test_invalid_schema_version_does_not_render_untrusted_value():
    with pytest.raises(FleetPlanError, match="schema_version não suportada") as exc:
        FleetPlan.from_dict({"schema_version": _HostileRepr()})
    assert "repr must not be called" not in str(exc.value)


def test_defaults_and_contract_fields_are_normalized():
    task = TaskSpec.from_dict({**MIN_TASK, "retry_policy": {"max_attempts": 2}, "outputs": ["artifact"]})
    assert task.status == "pending"
    assert task.capabilities == []
    assert task.depends_on == []
    assert task.retry_policy == RetryPolicy(max_attempts=2)
    assert task.outputs[0].name == "artifact"
    assert FleetPlan.from_dict({"tasks": [MIN_TASK]}).schema_version == "1"


def test_round_trip_normalizes_nested_dicts():
    source = {
        "schema_version": "1",
        "agents": [{"id": "a1", "role": "coder", "capabilities": ["python"]}],
        "waves": [{"id": "w1", "tasks": ["T-1"]}],
        "tasks": [{**MIN_TASK, "owner": "a1", "inputs": ["src"], "outputs": [{"name": "result"}]}],
        "gates": [{"id": "G1", "kind": "review"}],
    }
    plan = FleetPlan.from_dict(source)
    assert FleetPlan.from_json(plan.to_json()).to_dict() == plan.to_dict()
    assert plan.to_dict()["tasks"][0]["retry_policy"] == {"max_attempts": 1, "backoff_seconds": 0, "retryable_errors": []}


@pytest.mark.parametrize("missing", ["id", "wave", "role", "objective"])
def test_task_required_fields(missing):
    value = dict(MIN_TASK)
    del value[missing]
    with pytest.raises(FleetPlanError, match="obrigatório"):
        TaskSpec.from_dict(value)


def test_duplicate_ids_are_rejected():
    with pytest.raises(FleetPlanError, match="IDs duplicados"):
        FleetPlan.from_dict({"tasks": [MIN_TASK, {**MIN_TASK, "objective": "other"}]})


def test_json_is_deterministic_and_sorted():
    plan_a = FleetPlan.from_dict({"tasks": [MIN_TASK], "gates": [], "agents": [], "waves": []})
    plan_b = FleetPlan.from_dict({"waves": [], "agents": [], "gates": [], "tasks": [MIN_TASK]})
    assert plan_a.to_json() == plan_b.to_json()
    assert plan_a.to_json() == json.dumps(plan_a.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert plan_a.to_json().startswith('{"agents"')


@pytest.mark.parametrize("attempts", [True, False, 1.5, "2"])
def test_retry_attempts_are_strict_integers(attempts):
    with pytest.raises(FleetPlanError, match="max_attempts"):
        RetryPolicy.from_dict({"max_attempts": attempts})


@pytest.mark.parametrize("backoff", [math.inf, -math.inf, math.nan])
def test_retry_backoff_must_be_finite(backoff):
    with pytest.raises(FleetPlanError, match="backoff_seconds"):
        RetryPolicy.from_dict({"backoff_seconds": backoff})


def test_schema_version_and_typed_fields_are_strict():
    with pytest.raises(FleetPlanError, match="schema_version"):
        FleetPlan.from_dict({"schema_version": "2"})
    with pytest.raises(FleetPlanError, match="strings"):
        FleetPlan.from_dict({"tasks": [{**MIN_TASK, "capabilities": [1]}]})
    with pytest.raises(FleetPlanError, match="role"):
        TaskSpec.from_dict({**MIN_TASK, "role": 7})
    with pytest.raises(FleetPlanError, match="required"):
        TaskSpec.from_dict({**MIN_TASK, "outputs": [{"name": "x", "required": 1}]})


@pytest.mark.parametrize("owner", [1, "", " \t"])
def test_task_owner_must_be_a_non_empty_string_when_provided(owner):
    with pytest.raises(FleetPlanError, match="owner"):
        TaskSpec.from_dict({**MIN_TASK, "owner": owner})


@pytest.mark.parametrize("items", [[""], [" \t"]])
def test_string_lists_reject_empty_items_after_strip(items):
    with pytest.raises(FleetPlanError, match="não vazias"):
        TaskSpec.from_dict({**MIN_TASK, "capabilities": items})


def test_json_semantic_errors_are_fleet_plan_errors():
    with pytest.raises(FleetPlanError):
        FleetPlan.from_json("[]")
    with pytest.raises(FleetPlanError):
        FleetPlan.from_json('{"schema_version": "2"}')
    plan = FleetPlan.from_dict({"tasks": [MIN_TASK]})
    plan.tasks[0].inputs = {"not_json": math.nan}
    with pytest.raises(FleetPlanError, match="JSON válido"):
        plan.to_json()
