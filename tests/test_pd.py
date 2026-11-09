#!/usr/bin/env python3
"""Comprehensive tests for PD CLI — all commands including new features."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pd import (
    _BASH_COMPLETION,
    _FISH_COMPLETION,
    _ZSH_COMPLETION,
    PD,
    PDState,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        yield Path(tmpdir)
        os.chdir(original_cwd)


@pytest.fixture
def pd_cli():
    """Create a PD CLI instance."""
    return PD()


def extract_json(captured_out):
    """Extract the first JSON block from captured output.
    
    pytest capsys captures ALL stdout, so init messages appear
    before the actual command output. This extracts the FIRST
    valid JSON block found.
    """
    lines = captured_out.strip().split("\n")
    # Find the FIRST line that starts with { or [
    json_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("{", "[")):
            json_start = i
            break
    if json_start is not None:
        json_text = "\n".join(lines[json_start:])
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass
    return None


# ============================================================
# ORIGINAL TESTS (backward compatibility)
# ============================================================


class TestPDInit:
    def test_init_creates_directory(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        assert (temp_dir / ".spec" / "test-feature").exists()

    def test_init_creates_required_files(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        fd = temp_dir / ".spec" / "test-feature"
        assert (fd / "SPEC.md").exists()
        assert (fd / "PLAN.md").exists()
        assert (fd / "CONTEXT.md").exists()
        assert (fd / "STATE.md").exists()

    def test_init_creates_subdirectories(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        fd = temp_dir / ".spec" / "test-feature"
        assert (fd / "backend").is_dir()
        assert (fd / "frontend").is_dir()
        assert (fd / "tests").is_dir()

    def test_init_fails_if_exists(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        with pytest.raises(SystemExit):
            pd_cli.run(["init", "test-feature"])

    def test_init_custom_templates_render_feature(self, temp_dir, pd_cli):
        templates = temp_dir / "templates"
        templates.mkdir()
        (templates / "SPEC.md").write_text(
            "# Custom SPEC - {{feature}}\n\n## Requirements\n- [ ] Custom\n",
            encoding="utf-8",
        )
        pd_cli.run(["init", "custom-feature", "--template-dir", str(templates)])
        feature_dir = temp_dir / ".spec" / "custom-feature"
        assert (feature_dir / "SPEC.md").read_text(encoding="utf-8") == (
            "# Custom SPEC - custom-feature\n\n## Requirements\n- [ ] Custom\n"
        )
        assert "# PLAN.md - custom-feature" in (feature_dir / "PLAN.md").read_text(encoding="utf-8")

    def test_init_custom_templates_reject_empty_directory(self, temp_dir, pd_cli):
        templates = temp_dir / "templates"
        templates.mkdir()
        (templates / "README.md").write_text("not a template\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            pd_cli.run(["init", "custom-feature", "--template-dir", str(templates)])
        assert not (temp_dir / ".spec" / "custom-feature").exists()

    def test_init_rejects_missing_template_directory(self, temp_dir, pd_cli):
        with pytest.raises(SystemExit):
            pd_cli.run(["init", "custom-feature", "--template-dir", str(temp_dir / "missing")])

    def test_init_rejects_symlinked_template(self, temp_dir, pd_cli):
        templates = temp_dir / "templates"
        templates.mkdir()
        target = temp_dir / "target.md"
        target.write_text("# target\n", encoding="utf-8")
        try:
            os.symlink(target, templates / "SPEC.md")
        except OSError:
            pytest.skip("symlinks are unavailable on this platform")
        with pytest.raises(SystemExit):
            pd_cli.run(["init", "custom-feature", "--template-dir", str(templates)])


class TestPDStatus:
    def test_status_shows_feature(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["status"])
        assert "test-feature" in capsys.readouterr().out

    def test_status_shows_phase(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["status"])
        assert "Phase" in capsys.readouterr().out


class TestPDValidate:
    def test_validate_shows_files(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["validate"])
        out = capsys.readouterr().out
        assert "SPEC.md" in out and "PLAN.md" in out and "CONTEXT.md" in out


class TestPDAdvance:
    def test_advance_increments_phase(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["advance"])
        state = PDState(temp_dir / ".spec" / "test-feature")
        assert state.state["phase"] == 1

    def test_advance_multiple_times(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        for _ in range(3):
            pd_cli.run(["advance"])
        state = PDState(temp_dir / ".spec" / "test-feature")
        assert state.state["phase"] == 3


class TestPDCheckpoint:
    def test_checkpoint_creates_file(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["checkpoint", "--note", "Test cp"])
        assert len(list((temp_dir / ".spec" / "test-feature").glob("CHECKPOINT-*.md"))) > 0


class TestPDCompleteTask:
    def test_complete_task_adds_to_state(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["complete-task", "Implemented model"])
        state = PDState(temp_dir / ".spec" / "test-feature")
        assert "Implemented model" in state.state["tasks"]


class TestPDVerify:
    def test_verify_checks_files(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["verify"])
        out = capsys.readouterr().out
        assert "SPEC.md" in out or "requirements" in out.lower()


class TestPDHooks:
    def _write_hooks(self, temp_dir, hooks):
        lines = ["hooks:"]
        for name, command in hooks.items():
            lines.extend([f"  {name}:", f"    - '{command}'"])
        (temp_dir / "pd.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_advance_runs_before_and_after_hooks(self, temp_dir, pd_cli):
        self._write_hooks(temp_dir, {
            "before_advance": "printf before > before.txt",
            "after_advance": "printf after > after.txt",
        })
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["advance"])
        feature_dir = temp_dir / ".spec" / "test-feature"
        assert (feature_dir / "before.txt").read_text(encoding="utf-8") == "before"
        assert (feature_dir / "after.txt").read_text(encoding="utf-8") == "after"

    def test_checkpoint_runs_before_and_after_hooks(self, temp_dir, pd_cli):
        self._write_hooks(temp_dir, {
            "before_checkpoint": "printf before > before-cp.txt",
            "after_checkpoint": "printf after > after-cp.txt",
        })
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["checkpoint", "--note", "hook test"])
        feature_dir = temp_dir / ".spec" / "test-feature"
        assert (feature_dir / "before-cp.txt").exists()
        assert (feature_dir / "after-cp.txt").exists()

    def test_verify_runs_before_and_after_hooks(self, temp_dir, pd_cli):
        self._write_hooks(temp_dir, {
            "before_verify": "printf before > before-verify.txt",
            "after_verify": "printf after > after-verify.txt",
        })
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["verify"])
        feature_dir = temp_dir / ".spec" / "test-feature"
        assert (feature_dir / "before-verify.txt").exists()
        assert (feature_dir / "after-verify.txt").exists()

    def test_hook_failure_warns_but_does_not_block_advance(self, temp_dir, pd_cli, capsys):
        self._write_hooks(temp_dir, {"before_advance": "exit 3"})
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["advance"])
        out = capsys.readouterr().out
        assert "Hook failed" in out
        state = PDState(temp_dir / ".spec" / "test-feature")
        assert state.state["phase"] == 1


class TestPDState:
    def test_state_default(self, temp_dir):
        fd = temp_dir / ".spec" / "test-feature"
        fd.mkdir(parents=True)
        state = PDState(fd)
        assert state.state["phase"] == 0
        assert state.state["status"] == "initialized"

    def test_state_save_load(self, temp_dir):
        fd = temp_dir / ".spec" / "test-feature"
        fd.mkdir(parents=True)
        s1 = PDState(fd)
        s1.add_task("Test task")
        s1.save()
        s2 = PDState(fd)
        assert "Test task" in s2.state["tasks"]


# ============================================================
# NEW FEATURE TESTS
# ============================================================


class TestPDList:
    def test_list_shows_features(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "feature-a"])
        pd_cli.run(["init", "feature-b"])
        pd_cli.run(["list"])
        out = capsys.readouterr().out
        assert "feature-a" in out and "feature-b" in out

    def test_list_empty_when_no_features(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["list"])
        out = capsys.readouterr().out.lower()
        assert "no features" in out or "found" in out

    def test_list_json_output(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "feature-a"])
        pd_cli.run(["list", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None, "No JSON found"
        assert "features" in data
        assert any(f["name"] == "feature-a" for f in data["features"])


class TestPDListWithFeatureFlag:
    def test_feature_flag_targets_specific(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "feature-a"])
        pd_cli.run(["init", "feature-b"])
        pd_cli.run(["advance", "-f", "feature-a"])
        pd_cli.run(["status", "-f", "feature-a"])
        assert "feature-a" in capsys.readouterr().out

    def test_feature_flag_not_found(self, temp_dir, pd_cli):
        with pytest.raises(SystemExit):
            pd_cli.run(["status", "-f", "nonexistent"])


class TestPDValidateDeep:
    def test_deep_validate_on_fresh_feature(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["validate", "--deep"])
        out = capsys.readouterr().out.lower()
        assert "check" in out or "pass" in out or "score" in out

    def test_deep_validate_json(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["validate", "--deep", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None, "No JSON found"
        assert "checks" in data or "score" in data

    @staticmethod
    def _manifest(status: str) -> str:
        return (
            'schema_version: "1"\n'
            "agents: []\n"
            "waves:\n"
            "  - id: wave-0\n"
            "    tasks: [T-1]\n"
            "    status: pending\n"
            "tasks:\n"
            "  - id: T-1\n"
            "    wave: 0\n"
            "    role: coder\n"
            "    objective: x\n"
            f"    status: {status}\n"
            "gates: []\n"
        )

    def test_deep_validate_rejects_manifest_status_drift(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        fd = temp_dir / ".spec" / "test-feature"
        (fd / "plan.yaml").write_text(self._manifest("done"))
        pd_cli.run(["validate", "--deep", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None
        check = next(c for c in data["checks"] if c["name"] == "plan.yaml manifest")
        assert check["passed"] is False
        assert "status" in check["detail"]

    def test_deep_validate_accepts_canonical_manifest(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        fd = temp_dir / ".spec" / "test-feature"
        (fd / "plan.yaml").write_text(self._manifest("completed"))
        pd_cli.run(["validate", "--deep", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None
        check = next(c for c in data["checks"] if c["name"] == "plan.yaml manifest")
        assert check["passed"] is True

    def test_deep_validate_flags_task_pointing_at_missing_wave(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        fd = temp_dir / ".spec" / "test-feature"
        (fd / "plan.yaml").write_text(self._manifest("pending").replace("wave: 0", "wave: 9"))
        pd_cli.run(["validate", "--deep", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None
        check = next(c for c in data["checks"] if c["name"] == "plan.yaml manifest")
        assert check["passed"] is False
        assert "wave" in check["detail"]


class TestPDFleetRunGates:
    """`pd fleet-run` must be able to carry a human gate — otherwise a review gate can never pass."""

    @staticmethod
    def _manifest() -> str:
        return (
            'schema_version: "1"\n'
            "agents:\n"
            "  - id: orchestrator-isis\n"
            "    role: orchestrator\n"
            "    capabilities: [planning]\n"
            "    status: available\n"
            "waves:\n"
            "  - id: wave-1\n"
            "    tasks: [T-001]\n"
            "    status: pending\n"
            "    gates: [G1]\n"
            "tasks:\n"
            "  - id: T-001\n"
            "    wave: 1\n"
            "    role: orchestrator\n"
            "    objective: noop\n"
            "    depends_on: []\n"
            "    inputs: []\n"
            "    outputs:\n"
            "      - name: noop\n"
            "        description: nothing\n"
            "        required: true\n"
            '    acceptance_criteria: ["noop"]\n'
            "    validation_commands:\n"
            "      - /usr/bin/true\n"
            "    blocked_when: []\n"
            "    status: pending\n"
            "gates:\n"
            "  - id: G1\n"
            "    kind: review\n"
            "    scope: plan\n"
            "    owner: vitor\n"
            "    status: approved\n"
            "    required_evidence: [spec]\n"
        )

    def _prep(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "feat-g"])
        fd = temp_dir / ".spec" / "feat-g"
        (fd / "plan.yaml").write_text(self._manifest())
        capsys.readouterr()
        return fd

    def test_review_gate_blocks_without_human_gate(self, temp_dir, pd_cli, capsys):
        self._prep(temp_dir, pd_cli, capsys)
        pd_cli.run(["fleet-run", "-f", "feat-g", "--dry-run", "--json", "--run-id", "run-1"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None
        assert data["blocked"] == ["T-001"]
        assert data["gate_templates"]["G1"]["run"] == "run-1"
        assert "hint" in data

    def test_human_gate_unblocks_the_wave(self, temp_dir, pd_cli, capsys):
        fd = self._prep(temp_dir, pd_cli, capsys)
        pd_cli.run(["fleet-run", "-f", "feat-g", "--dry-run", "--json", "--run-id", "run-1"])
        first = extract_json(capsys.readouterr().out)
        assert first is not None
        gates = first["gate_templates"]
        gates["G1"]["owner"] = "vitor"
        gates["G1"]["identity"] = "vitor@local"
        # placeholder zero e recusado: o gate assina o sha256 do que foi revisado
        digest = hashlib.sha256((fd / "SPEC.md").read_bytes()).hexdigest()
        gates["G1"]["evidence_digest"] = digest
        gates["G1"]["artifact_digest"] = digest
        gate_file = fd / "gate.json"
        gate_file.write_text(json.dumps(gates))
        pd_cli.run(["fleet-run", "-f", "feat-g", "--dry-run", "--json", "--run-id", "run-1",
                    "--human-gate", str(gate_file)])
        second = extract_json(capsys.readouterr().out)
        assert second is not None
        assert second["blocked"] == []
        assert second["statuses"] == {"T-001": "pending"}

    def test_human_gate_for_another_run_is_refused(self, temp_dir, pd_cli, capsys):
        fd = self._prep(temp_dir, pd_cli, capsys)
        pd_cli.run(["fleet-run", "-f", "feat-g", "--dry-run", "--json", "--run-id", "run-1"])
        first = extract_json(capsys.readouterr().out)
        assert first is not None
        gate_file = fd / "gate.json"
        signed = first["gate_templates"]
        digest = hashlib.sha256((fd / "SPEC.md").read_bytes()).hexdigest()
        signed["G1"]["evidence_digest"] = digest
        signed["G1"]["artifact_digest"] = digest
        gate_file.write_text(json.dumps(signed))
        pd_cli.run(["fleet-run", "-f", "feat-g", "--dry-run", "--json", "--run-id", "run-2",
                    "--human-gate", str(gate_file)])
        second = extract_json(capsys.readouterr().out)
        assert second is not None
        assert second["blocked"] == ["T-001"]

    def test_human_gate_for_unknown_gate_id_is_an_error(self, temp_dir, pd_cli, capsys):
        fd = self._prep(temp_dir, pd_cli, capsys)
        gate_file = fd / "gate.json"
        gate_file.write_text(json.dumps({"G-OTHER": {"owner": "x"}}))
        pd_cli.run(["fleet-run", "-f", "feat-g", "--dry-run", "--json", "--human-gate", str(gate_file)])
        data = extract_json(capsys.readouterr().out)
        assert data is not None
        assert data["status"] == "invalid"
        assert "G-OTHER" in data["error"]


    def test_placeholder_digest_does_not_authorize_the_wave(self, temp_dir, pd_cli, capsys):
        """D6: o template vem com digest zero; aprovar sem trocar o hash nao prova nada."""
        fd = self._prep(temp_dir, pd_cli, capsys)
        pd_cli.run(["fleet-run", "-f", "feat-g", "--dry-run", "--json", "--run-id", "run-1"])
        first = extract_json(capsys.readouterr().out)
        assert first is not None
        gate_file = fd / "gate.json"
        gate_file.write_text(json.dumps(first["gate_templates"]))
        pd_cli.run(["fleet-run", "-f", "feat-g", "--dry-run", "--json", "--run-id", "run-1",
                    "--human-gate", str(gate_file)])
        second = extract_json(capsys.readouterr().out)
        assert second is not None
        assert second["status"] == "invalid"
        assert "placeholder" in second["error"]


class TestPDStateIntegrity:
    def test_out_of_range_phase_is_accepted_by_status_but_flagged_by_validate(self, temp_dir, pd_cli, capsys):
        """D4: STATE.json corrompido nao pode render 'All checks passed'."""
        pd_cli.run(["init", "feat-p"])
        capsys.readouterr()
        state_file = temp_dir / ".spec" / "feat-p" / "STATE.json"
        data = json.loads(state_file.read_text())
        data["phase"] = 99
        state_file.write_text(json.dumps(data))

        pd_cli.run(["status", "-f", "feat-p"])
        assert "Unexpected error" not in capsys.readouterr().out

        pd_cli.run(["validate", "--deep", "-f", "feat-p", "--json"])
        report = extract_json(capsys.readouterr().out)
        assert report is not None
        check = next(c for c in report["checks"] if c["name"] == "STATE.json loads")
        assert check["passed"] is False
        assert "fora de faixa" in check["detail"]


class TestPDStateConcurrency:
    def test_parallel_complete_task_keeps_every_update(self, temp_dir, pd_cli, capsys):
        """D1: sem lock entre processos, 8 `complete-task` em paralelo perdiam 2-4 tasks.

        O repro do review de codigo rodava exatamente este cenario e metade dos updates
        desaparecia com rc=0 em todos os processos. Agora o save faz lock + merge.
        """
        import subprocess
        import sys

        pd_cli.run(["init", "race"])
        capsys.readouterr()
        fd = temp_dir / ".spec" / "race"
        script = Path(__file__).parents[1] / "scripts" / "pd.py"
        procs = [
            subprocess.Popen(
                [sys.executable, str(script), "complete-task", "-f", "race", f"task-{index}"],
                cwd=str(temp_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for index in range(8)
        ]
        codes = [proc.wait(timeout=120) for proc in procs]
        assert codes == [0] * 8
        state = json.loads((fd / "STATE.json").read_text())
        recorded = [task for task in state["tasks"] if str(task).startswith("task-")]
        assert len(recorded) == 8, state["tasks"]


class TestPDJsonOutput:
    def test_status_json(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["status", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None and data["feature"] == "test-feature"

    def test_validate_json(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["validate", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None and isinstance(data, dict)

    def test_checkpoint_json(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["checkpoint", "--note", "Test", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None and ("checkpoint" in data or "note" in data)


class TestPDDelete:
    def test_delete_removes_feature(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["delete", "test-feature", "--force"])
        assert not (temp_dir / ".spec" / "test-feature").exists()

    def test_delete_with_archive(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["delete", "test-feature", "--archive", "--force"])
        assert not (temp_dir / ".spec" / "test-feature").exists()
        assert (temp_dir / ".spec" / "archive").exists()

    def test_delete_nonexistent_fails(self, temp_dir, pd_cli):
        with pytest.raises(SystemExit):
            pd_cli.run(["delete", "nonexistent", "--force"])


class TestPDHistory:
    def test_history_after_checkpoints(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["checkpoint", "--note", "First cp"])
        pd_cli.run(["advance"])
        pd_cli.run(["checkpoint", "--note", "Second cp"])
        pd_cli.run(["history"])
        out = capsys.readouterr().out
        assert "First cp" in out or "checkpoint" in out.lower()

    def test_history_json(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["checkpoint", "--note", "Test"])
        pd_cli.run(["history", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None and isinstance(data, dict)


class TestPDReport:
    def test_report_shows_progress(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["complete-task", "Task 1"])
        pd_cli.run(["report"])
        assert "test-feature" in capsys.readouterr().out

    def test_report_json(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["report", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None and "feature" in data


class TestPDDryRun:
    def test_dry_run_advance_does_not_change(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["advance", "--dry-run"])
        state = PDState(temp_dir / ".spec" / "test-feature")
        assert state.state["phase"] == 0

    def test_dry_run_shows_output(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["advance", "--dry-run"])
        assert len(capsys.readouterr().out) > 0


class TestPDForce:
    def test_force_advance(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["advance", "--force"])
        state = PDState(temp_dir / ".spec" / "test-feature")
        assert state.state["phase"] == 1


class TestPDDiff:
    def test_diff_after_tasks(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["checkpoint", "--note", "Baseline"])
        pd_cli.run(["complete-task", "New task"])
        pd_cli.run(["diff"])
        assert len(capsys.readouterr().out) > 0

    def test_diff_json(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["checkpoint", "--note", "Baseline"])
        pd_cli.run(["diff", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None and isinstance(data, dict)


class TestPDConfig:
    def test_config_shows_phases(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["config"])
        out = capsys.readouterr().out.lower()
        assert "phase" in out

    def test_config_json(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["config", "--json"])
        data = extract_json(capsys.readouterr().out)
        assert data is not None and isinstance(data, dict)


class TestPDCompletion:
    def test_every_parser_subcommand_is_in_every_completion(self, pd_cli):
        subcommands = next(
            action.choices
            for action in pd_cli.parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        for shell, completion in {
            "bash": _BASH_COMPLETION,
            "zsh": _ZSH_COMPLETION,
            "fish": _FISH_COMPLETION,
        }.items():
            missing = {
                command
                for command in subcommands
                if re.search(rf"(?<![\w-]){re.escape(command)}(?![\w-])", completion) is None
            }
            assert not missing, f"{shell} completion is missing: {sorted(missing)}"

    def test_completion_bash(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["completion", "bash"])
        out = capsys.readouterr().out.lower()
        assert "complete" in out or "pd" in out

    def test_completion_zsh(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["completion", "zsh"])
        assert len(capsys.readouterr().out) > 0

    def test_completion_fish(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["completion", "fish"])
        assert len(capsys.readouterr().out) > 0


class TestPDStateJSON:
    def test_state_json_created_on_init(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        assert (temp_dir / ".spec" / "test-feature" / "STATE.json").exists()

    def test_state_json_valid_json(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        with open(temp_dir / ".spec" / "test-feature" / "STATE.json") as f:
            data = json.load(f)
        assert "phase" in data and "status" in data

    def test_state_json_updated_on_advance(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["advance"])
        with open(temp_dir / ".spec" / "test-feature" / "STATE.json") as f:
            data = json.load(f)
        assert data["phase"] == 1

    def test_state_md_still_generated(self, temp_dir, pd_cli):
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["advance"])
        assert (temp_dir / ".spec" / "test-feature" / "STATE.md").exists()


class TestPDErrorHandling:
    def test_no_command_shows_help(self, temp_dir, pd_cli, capsys):
        pd_cli.run([])
        out = capsys.readouterr().out.lower()
        assert "usage" in out or "pd" in out

    def test_invalid_command(self, temp_dir, pd_cli):
        with pytest.raises(SystemExit):
            pd_cli.run(["invalid-command"])


class TestMultipleFeatures:
    def test_multiple_features_coexist(self, temp_dir, pd_cli):
        pd_cli.run(["init", "feature-a"])
        pd_cli.run(["init", "feature-b"])
        pd_cli.run(["advance", "-f", "feature-a"])
        pd_cli.run(["advance", "-f", "feature-a"])
        pd_cli.run(["advance", "-f", "feature-b"])
        sa = PDState(temp_dir / ".spec" / "feature-a")
        sb = PDState(temp_dir / ".spec" / "feature-b")
        assert sa.state["phase"] == 2 and sb.state["phase"] == 1

    def test_list_shows_all_features(self, temp_dir, pd_cli, capsys):
        pd_cli.run(["init", "alpha"])
        pd_cli.run(["init", "beta"])
        pd_cli.run(["init", "gamma"])
        pd_cli.run(["list"])
        out = capsys.readouterr().out
        assert "alpha" in out and "beta" in out and "gamma" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
