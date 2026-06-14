#!/usr/bin/env python3
"""Tests for PD CLI."""

import os
import shutil
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

# Add scripts directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pd import PD, PDState


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


class TestPDInit:
    """Tests for pd init command."""
    
    def test_init_creates_directory(self, temp_dir, pd_cli):
        """Test that init creates the feature directory."""
        pd_cli.run(["init", "test-feature"])
        
        feature_dir = temp_dir / ".spec" / "test-feature"
        assert feature_dir.exists()
        assert feature_dir.is_dir()
    
    def test_init_creates_required_files(self, temp_dir, pd_cli):
        """Test that init creates all required files."""
        pd_cli.run(["init", "test-feature"])
        
        feature_dir = temp_dir / ".spec" / "test-feature"
        assert (feature_dir / "SPEC.md").exists()
        assert (feature_dir / "PLAN.md").exists()
        assert (feature_dir / "CONTEXT.md").exists()
        assert (feature_dir / "STATE.md").exists()
    
    def test_init_creates_subdirectories(self, temp_dir, pd_cli):
        """Test that init creates backend, frontend, tests directories."""
        pd_cli.run(["init", "test-feature"])
        
        feature_dir = temp_dir / ".spec" / "test-feature"
        assert (feature_dir / "backend").is_dir()
        assert (feature_dir / "frontend").is_dir()
        assert (feature_dir / "tests").is_dir()
    
    def test_init_fails_if_exists(self, temp_dir, pd_cli):
        """Test that init fails if feature already exists."""
        pd_cli.run(["init", "test-feature"])
        
        with pytest.raises(SystemExit):
            pd_cli.run(["init", "test-feature"])


class TestPDStatus:
    """Tests for pd status command."""
    
    def test_status_shows_feature(self, temp_dir, pd_cli, capsys):
        """Test that status shows feature name."""
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["status"])
        
        captured = capsys.readouterr()
        assert "test-feature" in captured.out
    
    def test_status_shows_phase(self, temp_dir, pd_cli, capsys):
        """Test that status shows current phase."""
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["status"])
        
        captured = capsys.readouterr()
        assert "Phase" in captured.out


class TestPDValidate:
    """Tests for pd validate command."""
    
    def test_validate_shows_files(self, temp_dir, pd_cli, capsys):
        """Test that validate checks for required files."""
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["validate"])
        
        captured = capsys.readouterr()
        assert "SPEC.md" in captured.out
        assert "PLAN.md" in captured.out
        assert "CONTEXT.md" in captured.out


class TestPDAdvance:
    """Tests for pd advance command."""
    
    def test_advance_increments_phase(self, temp_dir, pd_cli):
        """Test that advance increments the phase."""
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["advance"])
        
        feature_dir = temp_dir / ".spec" / "test-feature"
        state = PDState(feature_dir)
        assert state.state["phase"] == 1
    
    def test_advance_multiple_times(self, temp_dir, pd_cli):
        """Test that advance can be called multiple times."""
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["advance"])
        pd_cli.run(["advance"])
        pd_cli.run(["advance"])
        
        feature_dir = temp_dir / ".spec" / "test-feature"
        state = PDState(feature_dir)
        assert state.state["phase"] == 3


class TestPDCheckpoint:
    """Tests for pd checkpoint command."""
    
    def test_checkpoint_creates_file(self, temp_dir, pd_cli):
        """Test that checkpoint creates a checkpoint file."""
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["checkpoint", "--note", "Test checkpoint"])
        
        feature_dir = temp_dir / ".spec" / "test-feature"
        checkpoint_files = list(feature_dir.glob("CHECKPOINT-*.md"))
        assert len(checkpoint_files) > 0


class TestPDCompleteTask:
    """Tests for pd complete-task command."""
    
    def test_complete_task_adds_to_state(self, temp_dir, pd_cli):
        """Test that complete-task adds task to state."""
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["complete-task", "Implemented user model"])
        
        feature_dir = temp_dir / ".spec" / "test-feature"
        state = PDState(feature_dir)
        assert "Implemented user model" in state.state["tasks"]


class TestPDVerify:
    """Tests for pd verify command."""
    
    def test_verify_checks_files(self, temp_dir, pd_cli, capsys):
        """Test that verify checks for required files."""
        pd_cli.run(["init", "test-feature"])
        pd_cli.run(["verify"])
        
        captured = capsys.readouterr()
        assert "SPEC.md" in captured.out or "requirements" in captured.out.lower()


class TestPDState:
    """Tests for PDState class."""
    
    def test_state_default(self, temp_dir):
        """Test default state values."""
        feature_dir = temp_dir / ".spec" / "test-feature"
        feature_dir.mkdir(parents=True)
        
        state = PDState(feature_dir)
        assert state.state["phase"] == 0
        assert state.state["status"] == "initialized"
        assert state.state["tasks"] == []
    
    def test_state_save_load(self, temp_dir):
        """Test that state can be saved and loaded."""
        feature_dir = temp_dir / ".spec" / "test-feature"
        feature_dir.mkdir(parents=True)
        
        state = PDState(feature_dir)
        state.add_task("Test task")
        state.save()
        
        # Load from file
        state2 = PDState(feature_dir)
        assert "Test task" in state2.state["tasks"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
