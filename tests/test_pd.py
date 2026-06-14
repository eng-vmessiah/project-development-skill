#!/usr/bin/env python3
"""Comprehensive tests for PD CLI — all commands including new features."""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pd import (
    PD,
    PDConfig,
    PDState,
    PDError,
    FeatureNotFoundError,
    FeatureExistsError,
    PhaseError,
    ConfigError,
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
        if stripped.startswith("{") or stripped.startswith("["):
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
