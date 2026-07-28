import sys
import os
import subprocess
from pathlib import Path

import pytest

try:
    from scripts.pd_fleet.models import FleetPlan
    from scripts.pd_fleet.validation import (
        FleetValidationError,
        compute_ready_tasks,
        validate_dag,
        validate_ownership,
        validate_plan,
        validate_wave_gates,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).parents[2]))
    from scripts.pd_fleet.models import FleetPlan  # noqa: E402
    from scripts.pd_fleet.validation import (  # noqa: E402
        FleetValidationError,
        compute_ready_tasks,
        validate_dag,
        validate_ownership,
        validate_plan,
        validate_wave_gates,
    )


def task(task_id, *, wave=1, depends_on=(), paths=(), group=None, **extra):
    return {
        "id": task_id, "wave": wave, "role": "coder", "objective": "do work",
        "depends_on": list(depends_on), "allowed_paths": list(paths),
        "parallel_group": group, "outputs": ["result"],
        "acceptance_criteria": ["works"], "validation_commands": ["pytest -q"], **extra,
    }


def plan(*tasks):
    return FleetPlan.from_dict({"tasks": list(tasks)})


def test_valid_dag_is_deterministic_and_readiness_is_sorted():
    value = plan(task("T-2", depends_on=("T-1",), paths=("b.py",)), task("T-1", paths=("a.py",)))
    assert validate_plan(value).task_ids == ("T-1", "T-2")
    assert compute_ready_tasks(value) == ("T-1",)
    assert compute_ready_tasks(value, completed=("T-1",)) == ("T-1", "T-2")


def test_missing_dependency_is_actionable():
    errors = validate_dag(plan(task("T-1", depends_on=("NOPE",))))
    assert "dependência inexistente" in errors[0]
    with pytest.raises(FleetValidationError, match="NOPE"):
        validate_plan(plan(task("T-1", depends_on=("NOPE",))))


def test_cycle_is_rejected_with_stable_path():
    errors = validate_dag(plan(task("A", depends_on=("B",)), task("B", depends_on=("A",))))
    assert errors == ("ciclo no DAG: A -> B -> A",)


def test_parallel_write_overlap_is_rejected_but_dependency_serializes():
    conflicting = plan(task("A", paths=("src",)), task("B", paths=("src/file.py",)))
    assert any("ownership conflitante" in error for error in validate_ownership(conflicting))
    serialized = plan(task("A", paths=("src",)), task("B", depends_on=("A",), paths=("src/file.py",)))
    assert validate_ownership(serialized) == ()


def test_parallel_group_does_not_hide_conflict_and_different_waves_are_safe():
    value = plan(task("A", paths=("x.py",), group="g"), task("B", paths=("x.py",), group="g"))
    assert validate_ownership(value)
    assert validate_ownership(plan(task("A", paths=("x.py",), wave=1), task("B", paths=("x.py",), wave=2))) == ()


def test_allowed_and_forbidden_paths_cannot_overlap():
    errors = validate_ownership(plan(task("A", paths=("src",), forbidden_paths=["src/private.py"])))
    assert any("forbidden_path" in error for error in errors)


@pytest.mark.parametrize("field", ["outputs", "acceptance_criteria", "validation_commands"])
def test_readiness_minimum_contract_is_required(field):
    value = task("A")
    value[field] = []
    with pytest.raises(FleetValidationError, match="contrato incompleto"):
        validate_plan(plan(value))


def test_readiness_respects_sequential_waves_and_terminal_statuses():
    value = FleetPlan.from_dict({"waves": [{"id": "wave-1"}, {"id": "wave-2"}], "tasks": [
        task("late", wave=2), task("first", wave=1), task("already-done", wave=1, status="completed"),
    ]})
    assert compute_ready_tasks(value) == ("first",)
    assert compute_ready_tasks(value, completed=("first",)) == ("first", "late")
    blocked = FleetPlan.from_dict({"tasks": [task("A", status="blocked"), task("B", status="running"), task("C", status="completed")]})
    assert compute_ready_tasks(blocked) == ()


def test_wave_gates_use_real_gate_ids_and_equivalent_wave_ids():
    value = FleetPlan.from_dict({"waves": [{"id": "wave-2", "gates": ["G-review", "G-tests"]}], "gates": [
        {"id": "G-review"}, {"id": "G-tests"}], "tasks": [task("T", wave=2)]})
    assert compute_ready_tasks(value) == ()
    assert compute_ready_tasks(value, gates_passed=("G-review",)) == ()
    assert compute_ready_tasks(value, gates_passed=("G-review", "G-tests")) == ("T",)


def test_missing_wave_gate_is_actionable_and_does_not_release_task():
    value = FleetPlan.from_dict({"waves": [{"id": "wave-1", "gates": ["NOPE"]}], "tasks": [task("T", wave=1)]})
    errors = validate_wave_gates(value)
    assert errors == ("wave wave-1: gate inexistente 'NOPE'; adicione-o a FleetPlan.gates ou remova-o de wave.gates",)
    with pytest.raises(FleetValidationError, match="NOPE"):
        compute_ready_tasks(value, gates_passed=("NOPE",))


def test_equivalent_wave_ids_are_one_sequential_wave_across_hash_seeds():
    code = """
from scripts.pd_fleet.models import FleetPlan
from scripts.pd_fleet.validation import compute_ready_tasks
def task(i, wave):
    return {'id': i, 'wave': wave, 'role': 'coder', 'objective': 'do',
            'outputs': ['result'], 'acceptance_criteria': ['works'],
            'validation_commands': ['true']}
plan = FleetPlan.from_dict({'tasks': [task('later', 'wave-2'), task('one-a', 1), task('one-b', 'wave-1')]})
print(compute_ready_tasks(plan))
"""
    outputs = []
    for seed in ("1", "7", "101"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": os.getcwd()}
        outputs.append(subprocess.check_output([sys.executable, "-c", code], env=env, text=True).strip())
    assert outputs == ["('one-a', 'one-b')"] * 3


def test_blocked_when_is_descriptive_and_blocked_status_is_not_ready():
    value = plan(task("blocked", blocked_when=("external approval",), status="blocked"), task("open", blocked_when=("external approval",)))
    assert compute_ready_tasks(value) == ("open",)


def test_transitive_dependencies_and_readiness_are_deterministic():
    value = plan(task("C", depends_on=("B",)), task("A"), task("B", depends_on=("A",)))
    assert compute_ready_tasks(value) == ("A",)
    assert compute_ready_tasks(value, completed=("A",)) == ("A", "B")
    assert compute_ready_tasks(value, completed=("A", "B")) == ("A", "B", "C")
    assert compute_ready_tasks(value, completed=("B", "A")) == compute_ready_tasks(value, completed=("A", "B"))


class _HostileRepr(str):
    def __repr__(self):
        raise AssertionError("repr must not be called")


def test_validation_diagnostics_never_call_repr_on_untrusted_values():
    missing = _HostileRepr("secret\x1bdep")
    value = plan(task("A", depends_on=("missing",), paths=("src",), forbidden_paths=["src/private"]))
    value.tasks[0].depends_on = [missing]
    errors = validate_dag(value) + validate_ownership(value)
    assert errors and all("repr must not be called" not in error for error in errors)
    assert all("secret" not in error for error in errors)


def test_validation_gate_and_parallel_diagnostics_never_call_repr():
    value = FleetPlan.from_dict({"waves": [{"id": "wave-1"}], "tasks": [
        task("A", paths=("src",)), task("B", paths=("src/file",))
    ]})
    value.waves[0].gates.append(_HostileRepr("secret\x1bgate"))
    errors = validate_wave_gates(value) + validate_ownership(value)
    assert errors and all("repr must not be called" not in error for error in errors)
    assert all("secret" not in error for error in errors)
