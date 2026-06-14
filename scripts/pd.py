#!/usr/bin/env python3
"""
PD - Project Development CLI

A deterministic workflow tool for software development.
Manages state, validates progress, and enforces the PD pipeline.
"""

import argparse
import json
import os
import subprocess
import sys
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Constants
SPEC_DIR = ".spec"
STATE_FILE = "STATE.md"
CONFIG_FILE = "pd.yaml"
HOME_CONFIG = "~/.pd.yaml"

# Default phases
DEFAULT_PHASES = [
    {"id": 0, "name": "Setup", "description": "Initialize worktree and project"},
    {"id": 1, "name": "Brainstorming", "description": "Understand the problem"},
    {"id": 2, "name": "Planning", "description": "Decide the approach"},
    {"id": 3, "name": "Structure", "description": "Organize the work"},
    {"id": 4, "name": "Coding", "description": "Implement the solution"},
    {"id": 5, "name": "Testing", "description": "Verify correctness"},
    {"id": 6, "name": "Validation", "description": "Confirm value"},
    {"id": 7, "name": "Merge", "description": "Deliver results"},
]

PHASES = DEFAULT_PHASES


class PDError(Exception):
    """Base exception for PD errors."""
    pass


class FeatureNotFoundError(PDError):
    """Feature directory not found."""
    pass


class FeatureExistsError(PDError):
    """Feature already exists."""
    pass


class PhaseError(PDError):
    """Phase-related error."""
    pass


class ConfigError(PDError):
    """Configuration error."""
    pass


class PDConfig:
    """PD configuration manager."""
    
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from pd.yaml."""
        config = {
            "phases": DEFAULT_PHASES,
            "directories": {
                "spec": ".spec",
                "state": "STATE.md",
                "backend": "backend",
                "frontend": "frontend",
                "tests": "tests",
            },
            "required_files": {
                "1": ["SPEC.md"],
                "2": ["PLAN.md"],
                "3": ["CONTEXT.md"],
                "5": ["tests/"],
                "6": ["VERIFICATION.md"],
            },
            "hooks": {
                "before_advance": [],
                "after_advance": [],
                "before_checkpoint": [],
                "after_checkpoint": [],
                "before_verify": [],
                "after_verify": [],
            },
            "validation": {
                "require_all_requirements": True,
                "require_tests": True,
                "require_verification": True,
            },
        }
        
        # Try loading from project root
        project_config = self.project_dir / CONFIG_FILE
        if project_config.exists():
            try:
                with open(project_config) as f:
                    user_config = yaml.safe_load(f)
                    if user_config:
                        config.update(user_config)
            except yaml.YAMLError as e:
                raise ConfigError(f"Invalid YAML in {project_config}: {e}")
        
        # Try loading from home directory
        home_config = Path(HOME_CONFIG).expanduser()
        if home_config.exists():
            try:
                with open(home_config) as f:
                    user_config = yaml.safe_load(f)
                    if user_config:
                        config.update(user_config)
            except yaml.YAMLError as e:
                raise ConfigError(f"Invalid YAML in {home_config}: {e}")
        
        return config
    
    def get_phases(self) -> List[Dict]:
        """Get configured phases."""
        return self.config.get("phases", DEFAULT_PHASES)
    
    def get_hooks(self, phase: str) -> List[str]:
        """Get hooks for a phase."""
        return self.config.get("hooks", {}).get(phase, [])
    
    def get_validation_rules(self) -> Dict:
        """Get validation rules."""
        return self.config.get("validation", {})


class PDState:
    """Manages project state."""
    
    def __init__(self, feature_dir: Path, config: Optional[PDConfig] = None):
        self.feature_dir = feature_dir
        self.config = config or PDConfig(feature_dir.parent.parent)
        self.state_file = feature_dir / STATE_FILE
        self.state = self._load_state()
    
    def _load_state(self) -> Dict[str, Any]:
        """Load state from STATE.md."""
        if not self.state_file.exists():
            return self._default_state()
        
        content = self.state_file.read_text()
        return self._parse_state(content)
    
    def _default_state(self) -> Dict[str, Any]:
        return {
            "feature": self.feature_dir.name,
            "phase": 0,
            "status": "initialized",
            "tasks": [],
            "checkpoints": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    
    def _parse_state(self, content: str) -> Dict[str, Any]:
        """Parse STATE.md content."""
        state = self._default_state()
        
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("## Phase:"):
                try:
                    state["phase"] = int(line.split(":")[1].strip().split(" ")[0])
                except (IndexError, ValueError):
                    pass
            elif line.startswith("## Phase"):
                # Phase value is on the next line
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    try:
                        state["phase"] = int(next_line.split(" ")[0])
                    except (ValueError, IndexError):
                        pass
            elif line.startswith("## Status:"):
                state["status"] = line.split(":")[1].strip()
            elif line.startswith("## Status"):
                # Status value is on the next line
                if i + 1 < len(lines):
                    state["status"] = lines[i + 1].strip()
            elif line.startswith("- [x]"):
                task = line.replace("- [x]", "").strip()
                if task not in state["tasks"]:
                    state["tasks"].append(task)
        
        return state
    
    def save(self):
        """Save state to STATE.md."""
        self.state["updated_at"] = datetime.now().isoformat()
        
        content = self._generate_state_md()
        self.state_file.write_text(content)
    
    def _generate_state_md(self) -> str:
        """Generate STATE.md content."""
        phases = self.config.get_phases()
        phase = phases[self.state["phase"]]
        
        tasks_md = "\n".join([
            f"- [x] {task}" for task in self.state["tasks"]
        ]) or "- [ ] No tasks completed"
        
        checkpoints_md = "\n".join([
            f"- {cp['date']}: {cp['note']}" for cp in self.state["checkpoints"]
        ]) or "- No checkpoints"
        
        return f"""# STATE.md - {self.state['feature']}

## Feature
{self.state['feature']}

## Phase
{phase['id']} ({phase['name']})

## Status
{self.state['status']}

## Completed Tasks
{tasks_md}

## Checkpoints
{checkpoints_md}

## Timestamps
- Created: {self.state['created_at']}
- Updated: {self.state['updated_at']}
"""
    
    def advance_phase(self) -> bool:
        """Advance to next phase."""
        phases = self.config.get_phases()
        if self.state["phase"] < len(phases) - 1:
            self.state["phase"] += 1
            self.state["status"] = phases[self.state["phase"]]["name"].lower()
            
            # Run hooks
            self._run_hooks("after_advance")
            
            self.save()
            return True
        return False
    
    def add_task(self, task: str):
        """Add completed task."""
        if task not in self.state["tasks"]:
            self.state["tasks"].append(task)
            self.save()
    
    def add_checkpoint(self, note: str):
        """Add checkpoint."""
        # Run hooks
        self._run_hooks("before_checkpoint")
        
        self.state["checkpoints"].append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "note": note,
        })
        
        # Run hooks
        self._run_hooks("after_checkpoint")
        
        self.save()
    
    def _run_hooks(self, hook_type: str):
        """Run hooks for a specific type."""
        hooks = self.config.get_hooks(hook_type)
        for hook in hooks:
            try:
                subprocess.run(hook, shell=True, check=True, cwd=self.feature_dir)
            except subprocess.CalledProcessError as e:
                print(f"⚠️  Hook failed: {hook}")
                print(f"   Error: {e}")


class PD:
    """Main PD CLI class."""
    
    def __init__(self):
        self.parser = self._create_parser()
        self.spec_dir = Path.cwd() / SPEC_DIR
    
    def _create_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="pd",
            description="Project Development CLI - Deterministic workflow tool"
        )
        
        subparsers = parser.add_subparsers(dest="command", help="Commands")
        
        # init
        init_parser = subparsers.add_parser("init", help="Initialize a new feature")
        init_parser.add_argument("feature", help="Feature name")
        
        # status
        subparsers.add_parser("status", help="Show current status")
        
        # validate
        subparsers.add_parser("validate", help="Validate progress")
        
        # checkpoint
        checkpoint_parser = subparsers.add_parser("checkpoint", help="Create checkpoint")
        checkpoint_parser.add_argument("--note", "-n", default="", help="Checkpoint note")
        
        # verify
        subparsers.add_parser("verify", help="Verify before completing")
        
        # advance
        subparsers.add_parser("advance", help="Advance to next phase")
        
        # complete-task
        task_parser = subparsers.add_parser("complete-task", help="Mark task as complete")
        task_parser.add_argument("task", help="Task description")
        
        # config
        subparsers.add_parser("config", help="Show current configuration")
        
        return parser
    
    def run(self, args=None):
        """Run the CLI."""
        args = self.parser.parse_args(args)
        
        if not args.command:
            self.parser.print_help()
            return
        
        try:
            # Get current feature
            feature_dir = self._find_feature_dir()
            
            if args.command == "init":
                self._init_feature(args.feature)
            elif not feature_dir:
                raise FeatureNotFoundError(
                    "No feature initialized. Run 'pd init <feature-name>' first."
                )
            else:
                config = PDConfig(feature_dir.parent.parent)
                state = PDState(feature_dir, config)
                
                if args.command == "status":
                    self._show_status(state)
                elif args.command == "validate":
                    self._validate(state)
                elif args.command == "checkpoint":
                    self._checkpoint(state, args.note)
                elif args.command == "verify":
                    self._verify(state)
                elif args.command == "advance":
                    self._advance(state)
                elif args.command == "complete-task":
                    self._complete_task(state, args.task)
                elif args.command == "config":
                    self._show_config(config)
        
        except PDError as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            sys.exit(1)
    
    def _find_feature_dir(self) -> Optional[Path]:
        """Find the current feature directory."""
        if not self.spec_dir.exists():
            return None
        
        # Find the most recent feature directory
        feature_dirs = [
            d for d in self.spec_dir.iterdir()
            if d.is_dir() and (d / STATE_FILE).exists()
        ]
        
        if not feature_dirs:
            return None
        
        # Return the most recently modified
        return max(feature_dirs, key=lambda d: d.stat().st_mtime)
    
    def _init_feature(self, feature_name: str):
        """Initialize a new feature."""
        feature_dir = self.spec_dir / feature_name
        
        if feature_dir.exists():
            raise FeatureExistsError(f"Feature '{feature_name}' already exists.")
        
        # Create directories
        feature_dir.mkdir(parents=True)
        (feature_dir / "backend").mkdir()
        (feature_dir / "frontend").mkdir()
        (feature_dir / "tests").mkdir()
        
        # Create initial files
        (feature_dir / "SPEC.md").write_text(f"""# SPEC.md - {feature_name}

## Requirements
- [ ] Requirement 1
- [ ] Requirement 2

## Constraints
- Constraint 1

## Success Criteria
- [ ] Criterion 1
""")
        
        (feature_dir / "PLAN.md").write_text(f"""# PLAN.md - {feature_name}

## Wave 1: Foundation
- [ ] Task 1: Setup
- [ ] Task 2: Create models

## Wave 2: Implementation
- [ ] Task 3: Implement core
- [ ] Task 4: Implement API

## Wave 3: Testing
- [ ] Task 5: Write tests
- [ ] Task 6: Integration tests
""")
        
        (feature_dir / "CONTEXT.md").write_text(f"""# CONTEXT.md - {feature_name}

## Decisions
- Decision 1: [date] - [description]

## Trade-offs
- Trade-off 1: [description]

## Notes
- Note 1: [description]
""")
        
        # Create state
        state = PDState(feature_dir)
        state.save()
        
        print(f"✅ Initialized feature: {feature_name}")
        print(f"📁 Created: {feature_dir}")
        print(f"📝 Created: SPEC.md, PLAN.md, CONTEXT.md, STATE.md")
        print(f"📂 Created: backend/, frontend/, tests/")
    
    def _show_status(self, state: PDState):
        """Show current status."""
        phases = state.config.get_phases()
        phase = phases[state.state["phase"]]
        
        print(f"📋 Feature: {state.state['feature']}")
        print(f"   Phase: {phase['id']} ({phase['name']})")
        print(f"   Status: {state.state['status']}")
        print(f"   Tasks: {len(state.state['tasks'])} complete")
        print(f"   Checkpoints: {len(state.state['checkpoints'])}")
        print(f"   Last updated: {state.state['updated_at']}")
    
    def _validate(self, state: PDState):
        """Validate progress."""
        print("🔍 Validating progress...\n")
        
        feature_dir = state.feature_dir
        current_phase = state.state["phase"]
        phases = state.config.get_phases()
        
        # Check required files
        required_files = ["SPEC.md", "PLAN.md", "CONTEXT.md", STATE_FILE]
        for file in required_files:
            if (feature_dir / file).exists():
                print(f"✅ {file} exists")
            else:
                print(f"❌ {file} missing")
        
        # Check phase requirements
        if current_phase >= 1:
            spec_content = (feature_dir / "SPEC.md").read_text()
            if "Requirements" in spec_content and "- [ ]" in spec_content:
                print("✅ SPEC.md has requirements")
            else:
                print("⚠️  SPEC.md may be incomplete")
        
        if current_phase >= 2:
            plan_content = (feature_dir / "PLAN.md").read_text()
            if "Wave" in plan_content:
                print("✅ PLAN.md has waves")
            else:
                print("⚠️  PLAN.md may be incomplete")
        
        # Show next steps
        if current_phase < len(phases) - 1:
            next_phase = phases[current_phase + 1]
            print(f"\n📌 Next phase: {next_phase['name']}")
            print(f"   Run 'pd advance' to move to next phase")
    
    def _checkpoint(self, state: PDState, note: str):
        """Create checkpoint."""
        if not note:
            note = f"Checkpoint at phase {state.state['phase']}"
        
        state.add_checkpoint(note)
        
        # Create checkpoint file
        checkpoint_file = state.feature_dir / f"CHECKPOINT-{datetime.now().strftime('%Y%m%d-%H%M')}.md"
        checkpoint_file.write_text(f"""# Checkpoint - {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Feature
{state.state['feature']}

## Phase
{state.config.get_phases()[state.state['phase']]['name']}

## Note
{note}

## Completed Tasks
{chr(10).join(f'- {t}' for t in state.state['tasks']) or '- None'}

## Next Steps
- Continue with current phase
""")
        
        print(f"✅ Checkpoint saved to {checkpoint_file}")
    
    def _verify(self, state: PDState):
        """Verify before completing."""
        print("🔍 Verifying before completion...\n")
        
        feature_dir = state.feature_dir
        validation_rules = state.config.get_validation_rules()
        checks = []
        
        # Check requirements
        if validation_rules.get("require_all_requirements", True):
            if (feature_dir / "SPEC.md").exists():
                spec = (feature_dir / "SPEC.md").read_text()
                if "- [ ]" not in spec:
                    checks.append(("✅", "All requirements addressed"))
                else:
                    checks.append(("❌", "Some requirements not addressed"))
        
        # Check tests
        if validation_rules.get("require_tests", True):
            test_dir = feature_dir / "tests"
            if test_dir.exists() and any(test_dir.glob("*.py")):
                checks.append(("✅", "Test files exist"))
            else:
                checks.append(("❌", "No test files found"))
        
        # Check verification file
        if validation_rules.get("require_verification", True):
            if (feature_dir / "VERIFICATION.md").exists():
                checks.append(("✅", "VERIFICATION.md created"))
            else:
                checks.append(("❌", "VERIFICATION.md not created"))
        
        # Print results
        for icon, message in checks:
            print(f"{icon} {message}")
        
        # Overall status
        failed = [c for c in checks if c[0] == "❌"]
        if not failed:
            print("\n✅ All checks passed! Ready to merge.")
        else:
            print(f"\n❌ {len(failed)} check(s) failed. Fix before merging.")
    
    def _advance(self, state: PDState):
        """Advance to next phase."""
        # Run hooks
        state._run_hooks("before_advance")
        
        if state.advance_phase():
            phases = state.config.get_phases()
            phase = phases[state.state["phase"]]
            print(f"✅ Advanced to phase {phase['id']}: {phase['name']}")
        else:
            print("⚠️  Already at final phase")
    
    def _complete_task(self, state: PDState, task: str):
        """Mark task as complete."""
        state.add_task(task)
        print(f"✅ Task completed: {task}")
    
    def _show_config(self, config: PDConfig):
        """Show current configuration."""
        print("⚙️  Current configuration:\n")
        
        print("Phases:")
        for phase in config.get_phases():
            print(f"  {phase['id']}: {phase['name']}")
        
        print("\nValidation rules:")
        for rule, value in config.get_validation_rules().items():
            print(f"  {rule}: {value}")
        
        print("\nHooks:")
        for hook_type, hooks in config.get_hooks("").items():
            if hooks:
                print(f"  {hook_type}: {hooks}")


def main():
    pd = PD()
    pd.run()


if __name__ == "__main__":
    main()
