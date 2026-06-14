#!/usr/bin/env python3
"""
PD - Project Development CLI

A deterministic workflow tool for software development.
Manages state, validates progress, and enforces the PD pipeline.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

try:
    import yaml
except ImportError:
    yaml = None  # Optional dependency; config loading will degrade gracefully

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
SPEC_DIR = ".spec"
STATE_FILE = "STATE.md"
STATE_JSON_FILE = "STATE.json"
CONFIG_FILE = "pd.yaml"
HOME_CONFIG = "~/.pd.yaml"
TOTAL_PHASES = 7  # 0‑7 inclusive = 8 phases

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


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# ANSI colour helpers
# ─────────────────────────────────────────────────────────────────────────────
_COLOR = True  # toggled by --no-color


def _green(text: str) -> str:
    return f"\033[32m{text}\033[0m" if _COLOR else text


def _red(text: str) -> str:
    return f"\033[31m{text}\033[0m" if _COLOR else text


def _yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m" if _COLOR else text


def _cyan(text: str) -> str:
    return f"\033[36m{text}\033[0m" if _COLOR else text


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
class PDConfig:
    """PD configuration manager."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.config: Dict[str, Any] = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from pd.yaml."""
        config: Dict[str, Any] = {
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

        if yaml is None:
            return config

        # Project-level config
        project_config = self.project_dir / CONFIG_FILE
        if project_config.exists():
            try:
                with open(project_config) as f:
                    user_config = yaml.safe_load(f)
                    if user_config:
                        config.update(user_config)
            except yaml.YAMLError as e:
                raise ConfigError(f"Invalid YAML in {project_config}: {e}")

        # Home-level config
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

    def get_phases(self) -> List[Dict[str, Any]]:
        """Get configured phases."""
        return self.config.get("phases", DEFAULT_PHASES)

    def get_hooks(self, phase: str) -> List[str]:
        """Get hooks for a phase."""
        return self.config.get("hooks", {}).get(phase, [])

    def get_validation_rules(self) -> Dict[str, Any]:
        """Get validation rules."""
        return self.config.get("validation", {})


# ─────────────────────────────────────────────────────────────────────────────
# State management (STATE.json + STATE.md)
# ─────────────────────────────────────────────────────────────────────────────
class PDState:
    """Manages project state with a dual JSON/Markdown backend."""

    def __init__(self, feature_dir: Path, config: Optional[PDConfig] = None):
        self.feature_dir = feature_dir
        self.config = config or PDConfig(feature_dir.parent.parent)
        self.state_file = feature_dir / STATE_FILE
        self.json_file = feature_dir / STATE_JSON_FILE
        self.state: Dict[str, Any] = self._load_state()

    # ── loading ──────────────────────────────────────────────────────────

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

    def _load_state(self) -> Dict[str, Any]:
        """Load state from STATE.json (preferred) or STATE.md (migration)."""
        if self.json_file.exists():
            return self._load_from_json()
        if self.state_file.exists():
            state = self._parse_state_md(self.state_file.read_text())
            # Migrate: write JSON so we never have to parse markdown again
            self._write_json(state)
            return state
        return self._default_state()

    def _load_from_json(self) -> Dict[str, Any]:
        try:
            with open(self.json_file) as f:
                data = json.load(f)
            # Merge with defaults for forward-compat
            default = self._default_state()
            for key in default:
                data.setdefault(key, default[key])
            return data
        except (json.JSONDecodeError, OSError):
            # Fall back to STATE.md
            if self.state_file.exists():
                return self._parse_state_md(self.state_file.read_text())
            return self._default_state()

    def _parse_state_md(self, content: str) -> Dict[str, Any]:
        """Parse STATE.md content (legacy / migration path)."""
        state = self._default_state()
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("## Phase:"):
                try:
                    state["phase"] = int(line.split(":")[1].strip().split(" ")[0])
                except (IndexError, ValueError):
                    pass
            elif line.startswith("## Phase"):
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    try:
                        state["phase"] = int(next_line.split(" ")[0])
                    except (ValueError, IndexError):
                        pass
            elif line.startswith("## Status:"):
                state["status"] = line.split(":")[1].strip()
            elif line.startswith("## Status"):
                if i + 1 < len(lines):
                    state["status"] = lines[i + 1].strip()
            elif line.startswith("- [x]"):
                task = line.replace("- [x]", "").strip()
                if task not in state["tasks"]:
                    state["tasks"].append(task)
        return state

    # ── saving ───────────────────────────────────────────────────────────

    def save(self) -> None:
        """Save state to both STATE.json and STATE.md."""
        self.state["updated_at"] = datetime.now().isoformat()
        self._write_json(self.state)
        self.state_file.write_text(self._generate_state_md())

    def _write_json(self, data: Dict[str, Any]) -> None:
        with open(self.json_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _generate_state_md(self) -> str:
        """Generate STATE.md content from the state dict."""
        phases = self.config.get_phases()
        phase = phases[self.state["phase"]]

        tasks_md = "\n".join(
            f"- [x] {task}" for task in self.state["tasks"]
        ) or "- [ ] No tasks completed"

        checkpoints_md = "\n".join(
            f"- {cp['date']}: {cp['note']}" for cp in self.state["checkpoints"]
        ) or "- No checkpoints"

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

    # ── mutations ────────────────────────────────────────────────────────

    def advance_phase(self, skip_validation: bool = False) -> bool:
        """Advance to next phase. Returns True on success."""
        phases = self.config.get_phases()
        if self.state["phase"] < len(phases) - 1:
            self.state["phase"] += 1
            self.state["status"] = phases[self.state["phase"]]["name"].lower()
            self._run_hooks("after_advance")
            self.save()
            return True
        return False

    def add_task(self, task: str) -> None:
        """Mark a task as complete."""
        if task not in self.state["tasks"]:
            self.state["tasks"].append(task)
            self.save()

    def add_checkpoint(self, note: str) -> None:
        """Record a checkpoint."""
        self._run_hooks("before_checkpoint")
        self.state["checkpoints"].append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "phase": self.state["phase"],
            "note": note,
            "tasks_snapshot": list(self.state["tasks"]),
        })
        self._run_hooks("after_checkpoint")
        self.save()

    def delete(self, archive: bool = False) -> None:
        """Delete or archive the feature directory."""
        if archive:
            archive_dir = self.feature_dir.parent / "archive"
            archive_dir.mkdir(exist_ok=True)
            dest = archive_dir / self.feature_dir.name
            shutil.move(str(self.feature_dir), str(dest))
        else:
            shutil.rmtree(self.feature_dir)

    # ── hooks ────────────────────────────────────────────────────────────

    def _run_hooks(self, hook_type: str) -> None:
        hooks = self.config.get_hooks(hook_type)
        for hook in hooks:
            try:
                subprocess.run(hook, shell=True, check=True, cwd=self.feature_dir)
            except subprocess.CalledProcessError as e:
                print(_yellow(f"⚠️  Hook failed: {hook}"))
                print(f"   Error: {e}")

    # ── helpers ──────────────────────────────────────────────────────────

    def task_stats(self) -> Tuple[int, int]:
        """Return (done, total) task counts from PLAN.md + state."""
        plan_path = self.feature_dir / "PLAN.md"
        total = 0
        if plan_path.exists():
            for line in plan_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("- [ ]") or line.startswith("- [x]"):
                    total += 1
        done = len(self.state["tasks"])
        return done, total

    def phase_info(self) -> Dict[str, Any]:
        phases = self.config.get_phases()
        idx = self.state["phase"]
        return phases[idx]


# ─────────────────────────────────────────────────────────────────────────────
# Shell completion scripts
# ─────────────────────────────────────────────────────────────────────────────
_BASH_COMPLETION = """\
_pd() {
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    commands="init status validate checkpoint verify advance complete-task config list delete history report diff completion"

    # Global flags
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "--feature --json --dry-run --force --no-color -f -h --help" -- "$cur") )
        return 0
    fi

    # Subcommand completion
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return 0
    fi

    local subcmd="${COMP_WORDS[1]}"
    case "$subcmd" in
        init)
            ;;
        complete-task)
            ;;
        checkpoint)
            COMPREPLY=( $(compgen -W "--note -n" -- "$cur") )
            ;;
        validate)
            COMPREPLY=( $(compgen -W "--deep" -- "$cur") )
            ;;
        delete)
            COMPREPLY=( $(compgen -W "--archive --force" -- "$cur") )
            ;;
        list|status|verify|advance|config|history|report|diff)
            COMPREPLY=( $(compgen -W "--feature -f --json" -- "$cur") )
            ;;
        completion)
            COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") )
            ;;
    esac
}
complete -F _pd pd
"""

_ZSH_COMPLETION = """\
#compdef pd

_pd() {
    local -a commands
    commands=(
        'init:Initialize a new feature'
        'status:Show current status'
        'validate:Validate progress'
        'checkpoint:Create checkpoint'
        'verify:Verify before completing'
        'advance:Advance to next phase'
        'complete-task:Mark task as complete'
        'config:Show current configuration'
        'list:List all features'
        'delete:Delete a feature'
        'history:Show feature history'
        'report:Generate progress report'
        'diff:Show changes since last checkpoint'
        'completion:Generate shell completions'
    )

    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'

    case $state in
        command)
            _describe 'command' commands
            ;;
        args)
            case $words[1] in
                init)
                    _arguments '1:feature name:'
                    ;;
                complete-task)
                    _arguments '1:task description:'
                    ;;
                checkpoint)
                    _arguments '--note[Checkpoint note]:note:' '-n[Checkpoint note]:note:'
                    ;;
                validate)
                    _arguments '--deep[Run deep validation]'
                    ;;
                delete)
                    _arguments '--archive[Archive instead of delete]' '--force[Skip confirmation]'
                    ;;
                list|status|verify|advance|config|history|report|diff)
                    _arguments \
                        '--feature[Target feature]:feature:' \
                        '-f[Target feature]:feature:' \
                        '--json[Output as JSON]'
                    ;;
                completion)
                    _arguments '1:shell:(bash zsh fish)'
                    ;;
            esac
            ;;
    esac
}

compdef _pd pd
"""

_FISH_COMPLETION = """\
# Fish completions for pd

# Subcommands
complete -c pd -n '__fish_use_subcommand' -a 'init' -d 'Initialize a new feature'
complete -c pd -n '__fish_use_subcommand' -a 'status' -d 'Show current status'
complete -c pd -n '__fish_use_subcommand' -a 'validate' -d 'Validate progress'
complete -c pd -n '__fish_use_subcommand' -a 'checkpoint' -d 'Create checkpoint'
complete -c pd -n '__fish_use_subcommand' -a 'verify' -d 'Verify before completing'
complete -c pd -n '__fish_use_subcommand' -a 'advance' -d 'Advance to next phase'
complete -c pd -n '__fish_use_subcommand' -a 'complete-task' -d 'Mark task as complete'
complete -c pd -n '__fish_use_subcommand' -a 'config' -d 'Show current configuration'
complete -c pd -n '__fish_use_subcommand' -a 'list' -d 'List all features'
complete -c pd -n '__fish_use_subcommand' -a 'delete' -d 'Delete a feature'
complete -c pd -n '__fish_use_subcommand' -a 'history' -d 'Show feature history'
complete -c pd -n '__fish_use_subcommand' -a 'report' -d 'Generate progress report'
complete -c pd -n '__fish_use_subcommand' -a 'diff' -d 'Show changes since last checkpoint'
complete -c pd -n '__fish_use_subcommand' -a 'completion' -d 'Generate shell completions'

# Global flags
complete -c pd -l feature -s f -d 'Target a specific feature'
complete -c pd -l json -d 'Output as JSON'
complete -c pd -l dry-run -d 'Show what would happen without changing state'
complete -c pd -l force -d 'Skip confirmation prompts'
complete -c pd -l no-color -d 'Disable colored output'

# Subcommand-specific flags
complete -c pd -n '__fish_seen_subcommand_from validate' -l deep -d 'Run deep validation'
complete -c pd -n '__fish_seen_subcommand_from delete' -l archive -d 'Archive instead of delete'
complete -c pd -n '__fish_seen_subcommand_from delete' -l force -d 'Skip confirmation'
complete -c pd -n '__fish_seen_subcommand_from checkpoint' -l note -s n -d 'Checkpoint note'
complete -c pd -n '__fish_seen_subcommand_from completion' -a 'bash zsh fish'
"""


# ─────────────────────────────────────────────────────────────────────────────
# Main PD class
# ─────────────────────────────────────────────────────────────────────────────
class PD:
    """Main PD CLI class."""

    def __init__(self) -> None:
        self.parser: argparse.ArgumentParser = self._create_parser()
        self.spec_dir: Path = Path.cwd() / SPEC_DIR

    # ── argument parser ──────────────────────────────────────────────────

    def _create_parser(self) -> argparse.ArgumentParser:
        # Create a parent parser with global flags
        # These flags are inherited by ALL subparsers
        global_parent = argparse.ArgumentParser(add_help=False)
        global_parent.add_argument(
            "-f", "--feature",
            default=None,
            help="Target a specific feature by name",
        )
        global_parent.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="Output all commands as JSON",
        )
        global_parent.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show what would happen without changing state",
        )
        global_parent.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Skip confirmation prompts and validation checks",
        )
        global_parent.add_argument(
            "--no-color",
            action="store_true",
            default=False,
            help="Disable colored output",
        )

        parser = argparse.ArgumentParser(
            prog="pd",
            description="Project Development CLI - Deterministic workflow tool",
            parents=[global_parent],
        )

        subparsers = parser.add_subparsers(dest="command", help="Commands")

        # init
        init_parser = subparsers.add_parser("init", parents=[global_parent], help="Initialize a new feature")
        init_parser.add_argument("feature", help="Feature name")

        # status
        subparsers.add_parser("status", parents=[global_parent], help="Show current status")

        # validate
        validate_parser = subparsers.add_parser("validate", parents=[global_parent], help="Validate progress")
        validate_parser.add_argument(
            "--deep",
            action="store_true",
            default=False,
            help="Run deep validation (content checks)",
        )

        # checkpoint
        checkpoint_parser = subparsers.add_parser("checkpoint", parents=[global_parent], help="Create checkpoint")
        checkpoint_parser.add_argument("--note", "-n", default="", help="Checkpoint note")

        # verify
        subparsers.add_parser("verify", parents=[global_parent], help="Verify before completing")

        # advance
        subparsers.add_parser("advance", parents=[global_parent], help="Advance to next phase")

        # complete-task
        task_parser = subparsers.add_parser("complete-task", parents=[global_parent], help="Mark task as complete")
        task_parser.add_argument("task", help="Task description")

        # config
        subparsers.add_parser("config", parents=[global_parent], help="Show current configuration")

        # list
        subparsers.add_parser("list", parents=[global_parent], help="List all features")

        # delete
        delete_parser = subparsers.add_parser("delete", parents=[global_parent], help="Delete a feature")
        delete_parser.add_argument("feature_name", nargs="?", default=None, help="Feature to delete")
        delete_parser.add_argument("--archive", action="store_true", default=False, help="Archive instead of delete")

        # history
        subparsers.add_parser("history", parents=[global_parent], help="Show feature history")

        # report
        subparsers.add_parser("report", parents=[global_parent], help="Generate progress report")

        # diff
        subparsers.add_parser("diff", parents=[global_parent], help="Show changes since last checkpoint")

        # completion
        completion_parser = subparsers.add_parser("completion", parents=[global_parent], help="Generate shell completions")
        completion_parser.add_argument("shell", choices=["bash", "zsh", "fish"], help="Shell type")

        return parser

    # ── entry point ──────────────────────────────────────────────────────

    def run(self, args: Optional[List[str]] = None) -> None:
        """Run the CLI."""
        parsed = self.parser.parse_args(args)

        # Global colour toggle
        global _COLOR
        if parsed.no_color:
            _COLOR = False

        if not parsed.command:
            self.parser.print_help()
            return

        # Build output mode helper
        as_json = parsed.json

        try:
            # Commands that don't require a feature directory
            if parsed.command == "init":
                self._cmd_init(parsed)
                return
            if parsed.command == "list":
                self._cmd_list(parsed, as_json)
                return
            if parsed.command == "completion":
                self._cmd_completion(parsed.shell)
                return

            # Everything else requires a feature
            feature_dir = self._find_feature_dir(parsed.feature)
            if not feature_dir:
                raise FeatureNotFoundError(
                    "No feature initialized. Run 'pd init <feature-name>' first."
                )

            config = PDConfig(feature_dir.parent.parent)
            state = PDState(feature_dir, config)

            # Dispatch
            cmd = parsed.command
            if cmd == "status":
                self._cmd_status(state, as_json)
            elif cmd == "validate":
                self._cmd_validate(state, parsed.deep, as_json)
            elif cmd == "checkpoint":
                self._cmd_checkpoint(state, parsed.note, as_json)
            elif cmd == "verify":
                self._cmd_verify(state, as_json)
            elif cmd == "advance":
                self._cmd_advance(state, parsed.dry_run, parsed.force, as_json)
            elif cmd == "complete-task":
                self._cmd_complete_task(state, parsed.task, as_json)
            elif cmd == "config":
                self._cmd_config(config, as_json)
            elif cmd == "delete":
                target = parsed.feature_name or parsed.feature
                self._cmd_delete(state, target, parsed.archive, parsed.force, as_json)
            elif cmd == "history":
                self._cmd_history(state, as_json)
            elif cmd == "report":
                self._cmd_report(state, as_json)
            elif cmd == "diff":
                self._cmd_diff(state, as_json)

        except PDError as e:
            if as_json:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(_red(f"❌ Error: {e}"))
            sys.exit(1)
        except Exception as e:
            if as_json:
                print(json.dumps({"error": f"Unexpected: {e}"}, indent=2))
            else:
                print(_red(f"❌ Unexpected error: {e}"))
            sys.exit(1)

    # ── feature discovery ────────────────────────────────────────────────

    def _find_feature_dir(self, name: Optional[str] = None) -> Optional[Path]:
        """Find a feature directory by name, or the most recently modified one."""
        if not self.spec_dir.exists():
            return None

        if name:
            candidate = self.spec_dir / name
            if candidate.is_dir() and (candidate / STATE_JSON_FILE).exists():
                return candidate
            # Also check for STATE.md (migration path)
            if candidate.is_dir() and (candidate / STATE_FILE).exists():
                return candidate
            return None

        # Most recent feature
        feature_dirs = [
            d for d in self.spec_dir.iterdir()
            if d.is_dir() and ((d / STATE_JSON_FILE).exists() or (d / STATE_FILE).exists())
        ]
        if not feature_dirs:
            return None
        return max(feature_dirs, key=lambda d: d.stat().st_mtime)

    def _all_feature_dirs(self) -> List[Path]:
        """Return all feature directories sorted by name."""
        if not self.spec_dir.exists():
            return []
        dirs = [
            d for d in self.spec_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
            and ((d / STATE_JSON_FILE).exists() or (d / STATE_FILE).exists())
        ]
        return sorted(dirs, key=lambda d: d.name)

    # ── command: init ────────────────────────────────────────────────────

    def _cmd_init(self, args: argparse.Namespace) -> None:
        feature_name = args.feature
        feature_dir = self.spec_dir / feature_name

        if feature_dir.exists():
            raise FeatureExistsError(f"Feature '{feature_name}' already exists.")

        # Create directories
        feature_dir.mkdir(parents=True)
        (feature_dir / "backend").mkdir()
        (feature_dir / "frontend").mkdir()
        (feature_dir / "tests").mkdir()

        # Create initial files
        (feature_dir / "SPEC.md").write_text(
            f"# SPEC.md - {feature_name}\n\n"
            "## Requirements\n- [ ] Requirement 1\n- [ ] Requirement 2\n\n"
            "## Constraints\n- Constraint 1\n\n"
            "## Success Criteria\n- [ ] Criterion 1\n"
        )
        (feature_dir / "PLAN.md").write_text(
            f"# PLAN.md - {feature_name}\n\n"
            "## Wave 1: Foundation\n- [ ] Task 1: Setup\n- [ ] Task 2: Create models\n\n"
            "## Wave 2: Implementation\n- [ ] Task 3: Implement core\n- [ ] Task 4: Implement API\n\n"
            "## Wave 3: Testing\n- [ ] Task 5: Write tests\n- [ ] Task 6: Integration tests\n"
        )
        (feature_dir / "CONTEXT.md").write_text(
            f"# CONTEXT.md - {feature_name}\n\n"
            "## Decisions\n- Decision 1: [date] - [description]\n\n"
            "## Trade-offs\n- Trade-off 1: [description]\n\n"
            "## Notes\n- Note 1: [description]\n"
        )

        # Create state (generates both STATE.json and STATE.md)
        state = PDState(feature_dir)
        state.save()

        if args.json if hasattr(args, "json") else False:
            print(json.dumps({"feature": feature_name, "created": str(feature_dir)}, indent=2))
        else:
            print(f"✅ Initialized feature: {feature_name}")
            print(f"📁 Created: {feature_dir}")
            print("📝 Created: SPEC.md, PLAN.md, CONTEXT.md, STATE.md")
            print("📂 Created: backend/, frontend/, tests/")

    # ── command: status ──────────────────────────────────────────────────

    def _cmd_status(self, state: PDState, as_json: bool) -> None:
        phases = state.config.get_phases()
        phase = phases[state.state["phase"]]
        total_phases = len(phases)
        done_tasks, total_tasks = state.task_stats()
        pct = (state.state["phase"] / (total_phases - 1) * 100) if total_phases > 1 else 0
        task_pct = (done_tasks / total_tasks * 100) if total_tasks > 0 else 0

        if as_json:
            print(json.dumps({
                "feature": state.state["feature"],
                "phase": phase["id"],
                "phase_name": phase["name"],
                "total_phases": total_phases,
                "phase_pct": round(pct),
                "status": state.state["status"],
                "tasks_done": done_tasks,
                "tasks_total": total_tasks,
                "tasks_pct": round(task_pct),
                "checkpoints": len(state.state["checkpoints"]),
                "created_at": state.state["created_at"],
                "updated_at": state.state["updated_at"],
            }, indent=2))
            return

        # Human-readable
        progress = _make_progress_bar(pct, 20)
        print(f"📋 Feature: {state.state['feature']}")
        print(f"   Phase: {phase['id']}/{total_phases - 1}: {phase['name']} ({round(pct)}%)")
        print(f"   Progress: {progress}")
        print(f"   Status: {state.state['status']}")
        print(f"   Tasks: {done_tasks}/{total_tasks} complete ({round(task_pct)}%)")
        print(f"   Checkpoints: {len(state.state['checkpoints'])}")
        print(f"   Last updated: {state.state['updated_at']}")

    # ── command: validate ────────────────────────────────────────────────

    def _cmd_validate(self, state: PDState, deep: bool, as_json: bool) -> None:
        feature_dir = state.feature_dir
        current_phase = state.state["phase"]
        checks: List[Dict[str, Any]] = []

        def _add(name: str, passed: bool, detail: str = "") -> None:
            checks.append({"name": name, "passed": passed, "detail": detail})

        # ── basic checks (always run) ──
        for fname in ["SPEC.md", "PLAN.md", "CONTEXT.md", "STATE.md", "STATE.json"]:
            _add(fname, (feature_dir / fname).exists(), f"{fname} exists")

        # ── deep checks ──
        if deep:
            # SPEC.md has non-empty requirements
            spec = feature_dir / "SPEC.md"
            if spec.exists():
                content = spec.read_text()
                # Check not just template placeholders
                lines = [ln for ln in content.splitlines() if ln.strip().startswith("- [")]
                real_reqs = [ln for ln in lines if "Requirement" not in ln and ln.strip() != "- [ ] "]
                _add("SPEC.md requirements", len(real_reqs) > 0,
                     f"{len(real_reqs)} real requirements found")
            else:
                _add("SPEC.md requirements", False, "File missing")

            # PLAN.md has actual tasks
            plan = feature_dir / "PLAN.md"
            if plan.exists():
                content = plan.read_text()
                # Better: just count any `- [ ]` or `- [x]` that aren't pure templates
                all_tasks = [ln for ln in content.splitlines()
                             if ln.strip().startswith("- [")]
                _add("PLAN.md tasks", len(all_tasks) > 0,
                     f"{len(all_tasks)} tasks found")
            else:
                _add("PLAN.md tasks", False, "File missing")

            # VERIFICATION.md exists and has evidence
            verif = feature_dir / "VERIFICATION.md"
            if verif.exists():
                content = verif.read_text()
                _add("VERIFICATION.md", len(content.strip()) > 50,
                     "Has content" if len(content.strip()) > 50 else "Too short / placeholder")
            else:
                _add("VERIFICATION.md", False, "File missing")

            # Test files exist and are non-empty
            test_dir = feature_dir / "tests"
            if test_dir.exists():
                py_files = [f for f in test_dir.iterdir()
                            if f.suffix == ".py" and f.stat().st_size > 0]
                _add("Test files", len(py_files) > 0,
                     f"{len(py_files)} non-empty test file(s)")
            else:
                _add("Test files", False, "tests/ directory missing")

            # STATE.md is parseable
            _add("STATE.md parseable", True, "Loaded successfully")

            # CONTEXT.md has decisions recorded
            ctx = feature_dir / "CONTEXT.md"
            if ctx.exists():
                content = ctx.read_text()
                has_decisions = "## Decisions" in content and len(
                    [ln for ln in content.splitlines() if ln.strip().startswith("- ")]) > 1
                _add("CONTEXT.md decisions", has_decisions,
                     "Has decisions" if has_decisions else "No decisions recorded")
            else:
                _add("CONTEXT.md decisions", False, "File missing")

        # ── scoring ──
        passed_count = sum(1 for c in checks if c["passed"])
        total_count = len(checks)
        all_passed = passed_count == total_count
        score = f"{passed_count}/{total_count}"

        if as_json:
            print(json.dumps({
                "checks": checks,
                "score": score,
                "all_passed": all_passed,
            }, indent=2))
            return

        # Human-readable
        print(_cyan("🔍 Validating progress...\n"))
        for c in checks:
            icon = _green("✅") if c["passed"] else _red("❌")
            detail = f" — {c['detail']}" if c["detail"] else ""
            print(f"  {icon} {c['name']}{detail}")

        print()
        if all_passed:
            print(_green(f"✅ All checks passed ({score})"))
        else:
            print(_yellow(f"⚠️  {score} checks passed"))

        # Next steps hint
        phases = state.config.get_phases()
        if current_phase < len(phases) - 1:
            next_phase = phases[current_phase + 1]
            print(f"\n📌 Next phase: {next_phase['name']}")
            print("   Run 'pd advance' to move to next phase")

    # ── command: checkpoint ──────────────────────────────────────────────

    def _cmd_checkpoint(self, state: PDState, note: str, as_json: bool) -> None:
        if not note:
            note = f"Checkpoint at phase {state.state['phase']}"

        state.add_checkpoint(note)

        # Create checkpoint file
        cp_file = state.feature_dir / f"CHECKPOINT-{datetime.now().strftime('%Y%m%d-%H%M')}.md"
        cp_file.write_text(
            f"# Checkpoint - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"## Feature\n{state.state['feature']}\n\n"
            f"## Phase\n{state.config.get_phases()[state.state['phase']]['name']}\n\n"
            f"## Note\n{note}\n\n"
            f"## Completed Tasks\n"
            + ("\n".join(f"- {t}" for t in state.state["tasks"]) or "- None")
            + "\n\n## Next Steps\n- Continue with current phase\n"
        )

        if as_json:
            print(json.dumps({
                "checkpoint": note,
                "file": str(cp_file),
                "phase": state.state["phase"],
            }, indent=2))
        else:
            print(f"✅ Checkpoint saved to {cp_file}")

    # ── command: verify ──────────────────────────────────────────────────

    def _cmd_verify(self, state: PDState, as_json: bool) -> None:
        feature_dir = state.feature_dir
        rules = state.config.get_validation_rules()
        checks: List[Dict[str, Any]] = []

        def _add(name: str, passed: bool) -> None:
            checks.append({"name": name, "passed": passed})

        if rules.get("require_all_requirements", True):
            if (feature_dir / "SPEC.md").exists():
                spec = (feature_dir / "SPEC.md").read_text()
                _add("All requirements addressed", "- [ ]" not in spec)
            else:
                _add("All requirements addressed", False)

        if rules.get("require_tests", True):
            test_dir = feature_dir / "tests"
            _add("Test files exist",
                 test_dir.exists() and any(test_dir.glob("*.py")))

        if rules.get("require_verification", True):
            _add("VERIFICATION.md created", (feature_dir / "VERIFICATION.md").exists())

        failed = [c for c in checks if not c["passed"]]

        if as_json:
            print(json.dumps({
                "checks": checks,
                "all_passed": len(failed) == 0,
                "failed_count": len(failed),
            }, indent=2))
            return

        print(_cyan("🔍 Verifying before completion...\n"))
        for c in checks:
            icon = _green("✅") if c["passed"] else _red("❌")
            print(f"  {icon} {c['name']}")

        if not failed:
            print(f"\n{_green('✅ All checks passed! Ready to merge.')}")
        else:
            print(f"\n{_red(f'❌ {len(failed)} check(s) failed. Fix before merging.')}")

    # ── command: advance ─────────────────────────────────────────────────

    def _cmd_advance(self, state: PDState, dry_run: bool, force: bool, as_json: bool) -> None:
        phases = state.config.get_phases()
        current = state.state["phase"]

        if current >= len(phases) - 1:
            if as_json:
                print(json.dumps({"error": "Already at final phase"}, indent=2))
            else:
                print(_yellow("⚠️  Already at final phase"))
            return

        next_phase = phases[current + 1]

        if dry_run:
            if as_json:
                print(json.dumps({
                    "dry_run": True,
                    "from_phase": current,
                    "from_phase_name": phases[current]["name"],
                    "to_phase": current + 1,
                    "to_phase_name": next_phase["name"],
                }, indent=2))
            else:
                print(_cyan(f"🔍 Dry run — would advance from phase {current} "                          f"({phases[current]['name']}) \u2192 {current + 1} ({next_phase['name']})"))

            return

        # Run before hooks
        if not force:
            state._run_hooks("before_advance")

        old_phase = current
        if state.advance_phase(skip_validation=force):
            if as_json:
                print(json.dumps({
                    "advanced": True,
                    "from_phase": old_phase,
                    "to_phase": current + 1,
                    "phase_name": next_phase["name"],
                }, indent=2))
            else:
                print(_green(f"✅ Advanced to phase {next_phase['id']}: {next_phase['name']}"))
        else:
            if as_json:
                print(json.dumps({"error": "Could not advance"}, indent=2))
            else:
                print(_yellow("⚠️  Already at final phase"))

    # ── command: complete-task ───────────────────────────────────────────

    def _cmd_complete_task(self, state: PDState, task: str, as_json: bool) -> None:
        state.add_task(task)
        if as_json:
            print(json.dumps({"task": task, "completed": True}, indent=2))
        else:
            print(f"✅ Task completed: {task}")

    # ── command: config ──────────────────────────────────────────────────

    def _cmd_config(self, config: PDConfig, as_json: bool) -> None:
        if as_json:
            print(json.dumps(config.config, indent=2, default=str))
            return

        print("⚙️  Current configuration:\n")
        print("Phases:")
        for phase in config.get_phases():
            print(f"  {phase['id']}: {phase['name']}")
        print("\nValidation rules:")
        for rule, value in config.get_validation_rules().items():
            print(f"  {rule}: {value}")
        print("\nHooks:")
        hooks = config.config.get("hooks", {})
        for hook_type, hook_list in hooks.items():
            if hook_list:
                print(f"  {hook_type}: {hook_list}")

    # ── command: list ────────────────────────────────────────────────────

    def _cmd_list(self, args: argparse.Namespace, as_json: bool) -> None:
        dirs = self._all_feature_dirs()

        if not dirs:
            if as_json:
                print(json.dumps({"features": []}, indent=2))
            else:
                print(_yellow("No features found. Run 'pd init <name>' to create one."))
            return

        features: List[Dict[str, Any]] = []
        for d in dirs:
            config = PDConfig(d.parent.parent)
            state = PDState(d, config)
            phases = state.config.get_phases()
            phase = phases[state.state["phase"]]
            done, total = state.task_stats()
            features.append({
                "name": d.name,
                "phase": phase["id"],
                "phase_name": phase["name"],
                "status": state.state["status"],
                "tasks_done": done,
                "tasks_total": total,
                "checkpoints": len(state.state["checkpoints"]),
                "updated_at": state.state["updated_at"],
            })

        if as_json:
            print(json.dumps({"features": features}, indent=2))
            return

        # Table
        header = f"{'Name':<25} {'Phase':<12} {'Status':<15} {'Tasks':<12} {'Updated'}"
        print(_cyan(header))
        print(_cyan("─" * len(header)))
        for f in features:
            tasks_str = f"{f['tasks_done']}/{f['tasks_total']}"
            updated = f["updated_at"][:19] if f["updated_at"] else "N/A"
            print(f"  {f['name']:<23} {f['phase_name']:<12} {f['status']:<15} {tasks_str:<12} {updated}")

    # ── command: delete ──────────────────────────────────────────────────

    def _cmd_delete(self, state: PDState, target: Optional[str],
                    archive: bool, force: bool, as_json: bool) -> None:
        feature_name = target or state.state["feature"]
        feature_dir = self.spec_dir / feature_name

        if not feature_dir.exists():
            raise FeatureNotFoundError(f"Feature '{feature_name}' not found.")

        action = "archive" if archive else "delete"

        if not force:
            confirm = input(
                f"⚠️  Are you sure you want to {action} '{feature_name}'? [y/N] "
            )
            if confirm.lower() != "y":
                print("Aborted.")
                return

        state.delete(archive=archive)

        if as_json:
            print(json.dumps({
                "feature": feature_name,
                "action": action,
                "archived": archive,
            }, indent=2))
        else:
            if archive:
                print(_green(f"📦 Feature '{feature_name}' archived."))
            else:
                print(_green(f"🗑️  Feature '{feature_name}' deleted."))

    # ── command: history ─────────────────────────────────────────────────

    def _cmd_history(self, state: PDState, as_json: bool) -> None:
        checkpoints = state.state.get("checkpoints", [])
        phases = state.config.get_phases()

        entries: List[Dict[str, Any]] = []
        for cp in checkpoints:
            phase_idx = cp.get("phase", state.state["phase"])
            phase_name = phases[phase_idx]["name"] if phase_idx < len(phases) else "Unknown"
            entries.append({
                "date": cp["date"],
                "phase": phase_idx,
                "phase_name": phase_name,
                "note": cp["note"],
                "tasks_snapshot": cp.get("tasks_snapshot", []),
            })

        if as_json:
            print(json.dumps({"feature": state.state["feature"], "history": entries}, indent=2))
            return

        if not entries:
            print(_yellow("No checkpoints recorded yet."))
            return

        print(_cyan(f"📜 History for: {state.state['feature']}\n"))
        header = f"{'Date':<20} {'Phase':<15} {'Action':<40} {'Note'}"
        print(_cyan(header))
        print(_cyan("─" * len(header)))
        for e in entries:
            print(f"  {e['date']:<20} {e['phase_name']:<15} {e['note']:<40}")

    # ── command: report ──────────────────────────────────────────────────

    def _cmd_report(self, state: PDState, as_json: bool) -> None:
        phases = state.config.get_phases()
        phase = phases[state.state["phase"]]
        total_phases = len(phases)
        done, total = state.task_stats()
        pct = (state.state["phase"] / (total_phases - 1) * 100) if total_phases > 1 else 0
        progress = _make_progress_bar(pct, 30)

        # Read blockers from CONTEXT.md
        blockers: List[str] = []
        ctx = state.feature_dir / "CONTEXT.md"
        if ctx.exists():
            content = ctx.read_text()
            in_blockers = False
            for line in content.splitlines():
                if line.strip().lower().startswith("## blocker"):
                    in_blockers = True
                    continue
                if in_blockers and line.startswith("## "):
                    in_blockers = False
                if in_blockers and line.strip().startswith("- "):
                    blockers.append(line.strip()[2:])

        # Build report
        report_lines = [
            f"# Progress Report: {state.state['feature']}",
            "",
            f"**Current Phase:** {phase['id']}/{total_phases - 1} — {phase['name']}",
            f"**Status:** {state.state['status']}",
            f"**Progress:** {progress} ({round(pct)}%)",
            f"**Tasks:** {done}/{total} complete",
            "",
            "## Checkpoints",
        ]

        for cp in state.state.get("checkpoints", []):
            report_lines.append(f"- {cp['date']}: {cp['note']}")

        if not state.state.get("checkpoints"):
            report_lines.append("- No checkpoints recorded")

        report_lines.append("")
        report_lines.append("## Next Steps")

        if state.state["phase"] < total_phases - 1:
            next_phase = phases[state.state["phase"] + 1]
            report_lines.append(f"- Advance to phase {next_phase['id']}: {next_phase['name']}")
            report_lines.append("- Run `pd advance` to proceed")
        else:
            report_lines.append("- Feature is at the final phase!")
            report_lines.append("- Run `pd verify` to confirm completion")

        if blockers:
            report_lines.append("")
            report_lines.append("## Blockers")
            for b in blockers:
                report_lines.append(f"- ⚠️ {b}")

        report_lines.append("")
        report_lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

        report_md = "\n".join(report_lines)

        if as_json:
            print(json.dumps({
                "feature": state.state["feature"],
                "phase": phase["id"],
                "phase_name": phase["name"],
                "progress_pct": round(pct),
                "tasks_done": done,
                "tasks_total": total,
                "checkpoints": state.state.get("checkpoints", []),
                "blockers": blockers,
                "report_md": report_md,
            }, indent=2))
        else:
            print(report_md)

    # ── command: diff ────────────────────────────────────────────────────

    def _cmd_diff(self, state: PDState, as_json: bool) -> None:
        checkpoints = state.state.get("checkpoints", [])
        phases = state.config.get_phases()

        if not checkpoints:
            if as_json:
                print(json.dumps({"diff": None, "message": "No checkpoints to diff against"}, indent=2))
            else:
                print(_yellow("No checkpoints to diff against."))
            return

        last_cp = checkpoints[-1]
        last_tasks = set(last_cp.get("tasks_snapshot", []))
        current_tasks = set(state.state["tasks"])

        added = sorted(current_tasks - last_tasks)
        removed = sorted(last_tasks - current_tasks)

        old_phase = last_cp.get("phase", 0)
        new_phase = state.state["phase"]
        phase_changed = old_phase != new_phase

        diff_data = {
            "feature": state.state["feature"],
            "last_checkpoint_date": last_cp["date"],
            "last_checkpoint_note": last_cp["note"],
            "phase_changed": phase_changed,
            "old_phase": old_phase,
            "old_phase_name": phases[old_phase]["name"] if old_phase < len(phases) else "?",
            "new_phase": new_phase,
            "new_phase_name": phases[new_phase]["name"] if new_phase < len(phases) else "?",
            "tasks_added": added,
            "tasks_removed": removed,
        }

        if as_json:
            print(json.dumps(diff_data, indent=2))
            return

        print(_cyan(f"📊 Diff since checkpoint: {last_cp['note']} ({last_cp['date']})\n"))

        if phase_changed:
            print(f"  Phase: {diff_data['old_phase_name']} → {diff_data['new_phase_name']}")
        else:
            print(f"  Phase: {phases[new_phase]['name']} (unchanged)")

        print()
        if added:
            print(_green("  Added tasks:"))
            for t in added:
                print(_green(f"    + {t}"))
        if removed:
            print(_red("  Removed tasks:"))
            for t in removed:
                print(_red(f"    - {t}"))
        if not added and not removed:
            print(_yellow("  No task changes since last checkpoint."))

    # ── command: completion ──────────────────────────────────────────────

    def _cmd_completion(self, shell: str) -> None:
        if shell == "bash":
            print(_BASH_COMPLETION)
        elif shell == "zsh":
            print(_ZSH_COMPLETION)
        elif shell == "fish":
            print(_FISH_COMPLETION)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_progress_bar(pct: float, width: int = 20) -> str:
    """Build a unicode progress bar string."""
    filled = int(pct / 100 * width)
    empty = width - filled
    return _green("█" * filled) + _yellow("░" * empty) + f" {round(pct)}%"


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    pd = PD()
    pd.run()


if __name__ == "__main__":
    main()
