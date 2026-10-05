"""Smoke checks for the thin Hermes pilot runner (no real dispatch)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet import run_hermes_pilot as pilot
from pd_fleet.runtime_adapter import RuntimeRunnerRequiredError
from pd_fleet.sandbox import LocalSandboxRunner

_PLAN_YAML = """schema_version: "1"
agents:
  - id: coder-hermes
    role: coder
waves:
  - id: wave-1
    tasks: [T-1]
    status: pending
tasks:
  - id: T-1
    wave: 1
    role: coder
    objective: escrever um resumo curto em resumo.md
    allowed_paths: [workspace/]
    acceptance_criteria: [resumo.md existe]
    owner: coder-hermes
    status: pending
gates: []
"""


def _plan_file(tmp_path: Path) -> Path:
    plan = tmp_path / "pilot" / "plan.yaml"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(_PLAN_YAML, encoding="utf-8")
    return plan


def test_smoke_builds_argv_and_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = pilot.main(["--smoke", "--plan", str(_plan_file(tmp_path))])
    out = capsys.readouterr().out
    assert rc == 0
    assert "fail-closed OK" in out
    assert "nenhum subprocesso" in out


def test_profile_is_ready_and_adapter_name() -> None:
    profile = pilot.build_profile()
    assert profile.readiness_status.value == "ready"
    adapter = pilot.build_adapter(profile)
    assert adapter.name == "hermes/opencode-go"


def test_runner_allowlist_matches_built_argv(tmp_path: Path) -> None:
    plan = pilot.load_plan(_plan_file(tmp_path))
    profile = pilot.build_profile()
    adapter = pilot.build_adapter(profile)
    out_root = tmp_path / "out"
    runner = pilot.build_runner(plan, profile, adapter, "model-x", "pilot", out_root,
                                tool_root=tmp_path)
    assert isinstance(runner, LocalSandboxRunner)
    argv = pilot.executed_argv(adapter, pilot.build_envelope(plan.tasks[0], profile, "model-x", "pilot"))
    assert argv in runner.allowlist
    assert argv[0] == pilot.HERMES_EXECUTABLE
    assert "opencode-go" in argv


def test_execute_without_runner_raises(tmp_path: Path) -> None:
    plan = pilot.load_plan(_plan_file(tmp_path))
    profile = pilot.build_profile()
    adapter = pilot.build_adapter(profile)
    envelope = pilot.build_envelope(plan.tasks[0], profile, "model-x", "pilot")
    with pytest.raises(RuntimeRunnerRequiredError):
        adapter.execute(envelope, runner=None)


def test_prompt_is_metachar_free() -> None:
    class _Task:
        id = "T-9"
        objective = "a; b | c & d $ e `f`"
        acceptance_criteria = ("x < y",)

    prompt = pilot.task_prompt(_Task(), "m")
    for char in ";&|<>$`":
        assert char not in prompt
    assert "\n" not in prompt


def test_live_requires_authorization(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = pilot.main(["--live", "--plan", str(_plan_file(tmp_path))])
    out = capsys.readouterr().out
    assert rc == 2
    assert "--authorized" in out
