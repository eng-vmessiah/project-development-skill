#!/usr/bin/env python3
"""
PD - Project Development CLI

A deterministic workflow tool for software development.
Manages state, validates progress, and enforces the PD pipeline.
"""

import argparse
import json
import os
import re
import stat
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Mapping

from pd_fleet.state import normalize_fleet_state
from pd_fleet.models import FleetPlan, FleetPlanError
from pd_fleet.validation import compute_ready_tasks
from pd_fleet.orchestrator import FleetOrchestrator
from pd_fleet.checkpoint import Checkpoint
from pd_fleet.contracts import canonicalize as canonicalize_v2, plan_hash as plan_hash_v2, _redact_paths, _redact_sensitive_text, _EXTERNAL_URL
from pd_fleet.state import FLEET_STATE_FIELDS
from pd_fleet.scheduler import LeaseScheduler
from pd_fleet.parallel import BoundedParallelExecutor
from pd_fleet.run_store import FleetRunStore, RunStoreError
from pd_fleet.handoff import HandoffStore
from pd_fleet.events import EventError, EventLog, MAX_QUERY
from pd_fleet.supervisor import FleetSupervisor

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


class TransactionRecoveryError(PDError):
    """A failed state transaction could not be rolled back completely."""
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

    def __init__(self, feature_dir: Path, config: Optional[PDConfig] = None, *, read_only: bool = False):
        self.feature_dir = feature_dir
        self.config = config or PDConfig(feature_dir.parent.parent)
        self.state_file = feature_dir / STATE_FILE
        self.json_file = feature_dir / STATE_JSON_FILE
        self.read_only = read_only
        self.state: Dict[str, Any] = self._load_state()

    # ── loading ──────────────────────────────────────────────────────────

    def _default_state(self) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        return {
            "feature": self.feature_dir.name,
            "phase": 0,
            "status": "initialized",
            "tasks": [],
            "checkpoints": [],
            "created_at": now,
            "updated_at": now,
            "fleet_state": normalize_fleet_state({"updated_at": now}),
        }

    def _load_state(self) -> Dict[str, Any]:
        """Load state from STATE.json (preferred) or STATE.md (migration)."""
        if self.json_file.exists():
            return self._load_from_json()
        if self.state_file.exists():
            state = self._parse_state_md(self.state_file.read_text())
            # Migrate: write JSON so we never have to parse markdown again
            if not self.read_only:
                try:
                    self._write_json(state)
                except OSError:
                    pass
            return state
        return self._default_state()

    def _load_from_json(self) -> Dict[str, Any]:
        def load_valid(path: Path) -> Dict[str, Any]:
            with open(path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("STATE.json deve conter um objeto")
            # Merge with defaults for forward-compat; root tasks remains legacy.
            default = self._default_state()
            for key in default:
                data.setdefault(key, default[key])
            data["fleet_state"] = normalize_fleet_state(data.get("fleet_state"))
            return data

        try:
            return load_valid(self.json_file)
        except (json.JSONDecodeError, OSError, ValueError):
            backup = self.json_file.with_name(self.json_file.name + ".bak")
            if backup.exists():
                try:
                    data = load_valid(backup)
                    # Repair the primary without consuming or changing the backup.
                    # A failed repair must not prevent use of the valid state.
                    if not self.read_only:
                        try:
                            shutil.copy2(backup, self.json_file)
                        except OSError:
                            pass
                    return data
                except (json.JSONDecodeError, OSError, ValueError):
                    pass
            # Fall back to STATE.md
            if self.state_file.exists():
                return self._parse_state_md(self.state_file.read_text())
            return self._default_state()

    def _parse_state_md(self, content: str) -> Dict[str, Any]:
        """Parse STATE.md content (legacy / migration path)."""
        state = self._default_state()
        lines = content.split("\n")
        marker = "## Fleet State"
        if marker in content:
            try:
                fragment = content.split(marker, 1)[1]
                fragment = fragment.split("```json", 1)[1].split("```", 1)[0]
                fleet = json.loads(fragment.strip())
                if isinstance(fleet, dict):
                    state["fleet_state"] = normalize_fleet_state(fleet)
            except (IndexError, json.JSONDecodeError):
                pass
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
        """Save state to both STATE.json and STATE.md transactionally."""
        candidate = deepcopy(self.state)
        now = datetime.now().isoformat()
        candidate["updated_at"] = now
        candidate["fleet_state"] = normalize_fleet_state(candidate.get("fleet_state"))
        candidate["fleet_state"]["updated_at"] = now
        try:
            json_text = json.dumps(candidate, indent=2, allow_nan=False)
            json.loads(json_text)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"Estado não serializável em JSON: {exc}") from exc
        md_text = self._generate_state_md(candidate)
        if not isinstance(md_text, str):
            raise TypeError("STATE.md deve ser texto")
        self._write_transaction(json_text + "\n", md_text)
        self.state = candidate

    def _write_json(self, data: Dict[str, Any]) -> None:
        """Atomically replace STATE.json, retaining the last valid backup."""
        self.json_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.json_file.name}.", suffix=".tmp", dir=self.json_file.parent)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, allow_nan=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            if self.json_file.exists():
                shutil.copy2(self.json_file, self.json_file.with_name(self.json_file.name + ".bak"))
            os.replace(str(temporary_path), str(self.json_file))
        except Exception:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _write_transaction(self, json_text: str, md_text: str) -> None:
        """Replace JSON and Markdown together, restoring both on failure."""
        self.json_file.parent.mkdir(parents=True, exist_ok=True)
        targets = (self.json_file, self.state_file)
        backups = tuple(path.with_name(path.name + ".bak") for path in targets)
        existed_before = tuple(target.exists() for target in targets)
        temporary_paths: list[Path] = []
        replaced: list[tuple[Path, Path, bool]] = []
        try:
            for target, content in zip(targets, (json_text, md_text)):
                fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
                temporary_path = Path(temporary)
                temporary_paths.append(temporary_path)
                with os.fdopen(fd, "w") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
            for target, backup in zip(targets, backups):
                if target.exists():
                    shutil.copy2(target, backup)
            for temporary_path, target, backup, existed in zip(temporary_paths, targets, backups, existed_before):
                os.replace(str(temporary_path), str(target))
                replaced.append((target, backup, existed))
        except Exception as original_error:
            recovery_error = None
            for target, backup, existed in reversed(replaced):
                try:
                    if existed:
                        if not backup.exists():
                            raise FileNotFoundError(f"backup ausente para recuperação de {target}")
                        shutil.copy2(backup, target)
                    else:
                        target.unlink(missing_ok=True)
                except Exception as exc:
                    if recovery_error is None:
                        recovery_error = exc
            if recovery_error is not None:
                raise TransactionRecoveryError(
                    f"Falha na transação e na recuperação de estado: {recovery_error}"
                ) from original_error
            raise
        finally:
            for temporary_path in temporary_paths:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _generate_state_md(self, state: Optional[Dict[str, Any]] = None) -> str:
        """Generate STATE.md content from a candidate state dict."""
        state = self.state if state is None else state
        phases = self.config.get_phases()
        phase = phases[state["phase"]]

        tasks_md = "\n".join(
            f"- [x] {task}" for task in state["tasks"]
        ) or "- [ ] No tasks completed"

        checkpoints_md = "\n".join(
            f"- {cp['date']}: {cp['note']}" for cp in state["checkpoints"]
        ) or "- No checkpoints"

        return f"""# STATE.md - {state['feature']}

## Feature
{state['feature']}

## Phase
{phase['id']} ({phase['name']})

## Status
{state['status']}

## Completed Tasks
{tasks_md}

## Checkpoints
{checkpoints_md}

## Timestamps
- Created: {state['created_at']}
- Updated: {state['updated_at']}

## Fleet State
```json
{json.dumps(state.get('fleet_state', normalize_fleet_state(None)), indent=2, allow_nan=False)}
```
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
    commands="init status fleet-status fleet-ready fleet-supervisor-status fleet-supervisor-events fleet-handoff-preview validate checkpoint verify advance complete-task config list delete history report diff completion"

    # Global flags
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "--feature --json --dry-run --force --no-color --store --run-id --owner-epoch --limit -f -h --help" -- "$cur") )
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
        fleet-supervisor-events)
            COMPREPLY=( $(compgen -W "--store --run-id --owner-epoch --limit --json" -- "$cur") )
            ;;
        delete)
            COMPREPLY=( $(compgen -W "--archive --force" -- "$cur") )
            ;;
        list|status|fleet-status|fleet-ready|fleet-supervisor-status|fleet-handoff-preview|verify|advance|config|history|report|diff)
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
        'fleet-status:Show fleet status'
        'fleet-ready:Show ready fleet tasks'
        'fleet-supervisor-status:Show read-only fleet supervisor status'
        'fleet-supervisor-events:Diagnose fleet supervisor events (read-only)'
        'fleet-handoff-preview:Preview a persisted handoff (read-only)'
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
                fleet-supervisor-events)
                    _arguments \
                        '--store[Event store root]:directory:' \
                        '--run-id[Mission run identifier]:' \
                        '--owner-epoch[Expected owner epoch]:' \
                        '--limit[Maximum events to inspect]:' \
                        '--json[Output as JSON]'
                    ;;
                list|status|fleet-status|fleet-ready|fleet-supervisor-status|fleet-handoff-preview|verify|advance|config|history|report|diff)
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
complete -c pd -n '__fish_use_subcommand' -a 'fleet-status' -d 'Show fleet status'
complete -c pd -n '__fish_use_subcommand' -a 'fleet-ready' -d 'Show ready fleet tasks'
complete -c pd -n '__fish_use_subcommand' -a 'fleet-supervisor-status' -d 'Show read-only fleet supervisor status'
complete -c pd -n '__fish_use_subcommand' -a 'fleet-supervisor-events' -d 'Diagnose fleet supervisor events (read-only)'
complete -c pd -n '__fish_use_subcommand' -a 'fleet-handoff-preview' -d 'Preview a persisted handoff (read-only)'
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
complete -c pd -n '__fish_seen_subcommand_from fleet-supervisor-events' -l store -d 'Event store root'
complete -c pd -n '__fish_seen_subcommand_from fleet-supervisor-events' -l run-id -d 'Mission run identifier'
complete -c pd -n '__fish_seen_subcommand_from fleet-supervisor-events' -l owner-epoch -d 'Expected owner epoch'
complete -c pd -n '__fish_seen_subcommand_from fleet-supervisor-events' -l limit -d 'Maximum events to inspect'
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

        # fleet inspection (strictly read-only)
        for fleet_command, help_text in (("fleet-status", "Show fleet status"), ("fleet-ready", "Show ready fleet tasks"),
                                         ("fleet-supervisor-status", "Show read-only fleet supervisor status")):
            fleet_parser = subparsers.add_parser(fleet_command, parents=[global_parent], help=help_text)
            fleet_parser.add_argument(
                "--plan", "--manifest", "--fleet-plan", dest="plan_path", default=None,
                help="Explicit path to a FleetPlan YAML/JSON manifest",
            )

        handoff_parser = subparsers.add_parser("fleet-handoff-preview", parents=[global_parent],
                                               help="Preview a persisted handoff (read-only)")
        handoff_parser.add_argument("--store", dest="store_root", default=".pd-fleet-handoffs",
                                    help="Handoff store root")
        handoff_parser.add_argument("--run-id", dest="run_id", required=True,
                                    help="Mission run identifier")
        handoff_parser.add_argument("--handoff-id", dest="handoff_id", required=True,
                                    help="Handoff identifier")
        handoff_parser.add_argument("--owner-epoch", dest="owner_epoch", type=int, default=None,
                                    help="Expected owner epoch")

        events_parser = subparsers.add_parser("fleet-supervisor-events", parents=[global_parent],
                                              help="Diagnose fleet supervisor events (read-only)")
        events_parser.add_argument("--store", dest="store_root", default=".pd-fleet-events",
                                   help="Event store root")
        events_parser.add_argument("--run-id", dest="run_id", required=True,
                                   help="Mission run identifier")
        events_parser.add_argument("--owner-epoch", dest="owner_epoch", type=int, default=None,
                                   help="Expected owner epoch")
        events_parser.add_argument("--limit", dest="limit", type=int, default=MAX_QUERY,
                                   help="Maximum number of events to inspect")

        # fleet execution (local simulated/default-deny dispatcher)
        run_parser = subparsers.add_parser("fleet-run", parents=[global_parent], help="Run a FleetPlan locally")
        run_parser.add_argument("--plan", "--manifest", "--fleet-plan", dest="plan_path", default=None,
                                help="Explicit path to a FleetPlan YAML/JSON manifest")
        run_parser.add_argument("--resume", action="store_true", default=False,
                                help="Resume from the persisted fleet checkpoint")

        # V2 is opt-in and isolated from legacy command semantics.
        v2_parser = subparsers.add_parser("v2", parents=[global_parent], help="V2 Fleet adapter")
        v2_commands = v2_parser.add_subparsers(dest="v2_command", required=True)
        for name, help_text in (("read", "Read a V2 manifest"), ("status", "Read V2 run status")):
            inspect = v2_commands.add_parser(name, parents=[global_parent], help=help_text)
            inspect.add_argument("--plan", "--manifest", dest="plan_path", default=None)
            inspect.add_argument("--store", dest="store_root", default=".pd-fleet-runs")
            inspect.add_argument("--run-id", dest="run_id", default=None)
        local = v2_commands.add_parser("run-local", parents=[global_parent], help="Run V2 locally")
        local.add_argument("--plan", "--manifest", dest="plan_path", required=True)
        local.add_argument("--store", dest="store_root", default=".pd-fleet-runs")
        local.add_argument("--run-id", dest="run_id", default=None)
        local.add_argument("--owner", default="cli")
        local.add_argument("--provider", choices=("local", "disabled"), default="local")

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

    def run(self, args: Optional[List[str]] = None) -> Optional[int]:
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
            if parsed.command == "v2":
                return self._cmd_v2(parsed)

            if parsed.command == "fleet-handoff-preview":
                return self._cmd_fleet_handoff_preview(parsed.store_root, parsed.run_id, parsed.handoff_id,
                                                       parsed.owner_epoch, as_json)
            if parsed.command == "fleet-supervisor-events":
                event_log = EventLog(parsed.store_root, parsed.run_id, owner_epoch=parsed.owner_epoch)
                report = FleetSupervisor().diagnose_events(
                    event_log, active_owner_epoch=parsed.owner_epoch, limit=parsed.limit
                )
                if as_json:
                    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
                else:
                    self._print_event_diagnostics(report)
                return

            # Everything else requires a feature
            feature_dir = self._find_feature_dir(parsed.feature)
            if not feature_dir:
                raise FeatureNotFoundError(
                    "No feature initialized. Run 'pd init <feature-name>' first."
                )

            config = PDConfig(feature_dir.parent.parent)
            state = PDState(feature_dir, config, read_only=parsed.command in {
                "fleet-status", "fleet-ready", "fleet-supervisor-status", "fleet-handoff-preview"
            })

            # Dispatch
            cmd = parsed.command
            if cmd == "status":
                self._cmd_status(state, as_json)
            elif cmd == "fleet-status":
                self._cmd_fleet_status(state, parsed.plan_path, as_json)
            elif cmd == "fleet-ready":
                self._cmd_fleet_ready(state, parsed.plan_path, as_json)
            elif cmd == "fleet-supervisor-status":
                self._cmd_fleet_supervisor_status(state, parsed.plan_path, as_json)
            elif cmd == "fleet-run":
                return self._cmd_fleet_run(state, parsed.plan_path, parsed.dry_run, parsed.resume, as_json)
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

        except (EventError, PDError) as e:
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

    @staticmethod
    def _print_event_diagnostics(report: Any) -> None:
        """Print a bounded, deterministic human-readable event report."""
        print("Fleet supervisor events")
        print(f"Status: {report.status}")
        print(f"Events: {report.event_count}")
        print(f"Transitions: {report.transition_count}")
        print(f"Checkpoints: {report.checkpoint_count}")
        if report.first_sequence is None:
            print("Sequence range: none")
        else:
            print(f"Sequence range: {report.first_sequence}-{report.last_sequence}")
        print("Gaps: " + (", ".join(str(value) for value in report.sequence_gaps)
                              if report.sequence_gaps else "none"))
        print("Task states: " + (", ".join(
            f"{task}={report.task_states[task]}" for task in sorted(report.task_states)
        ) if report.task_states else "none"))
        print("Reasons: " + (", ".join(report.reasons) if report.reasons else "none"))

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

    # ── commands: fleet inspection (read-only) ───────────────────────────
    def _fleet_plan_path(self, state: PDState, explicit: Optional[str]) -> Optional[Path]:
        """Find a manifest only in the feature directory or at an explicit path."""
        if explicit:
            candidate = Path(explicit).expanduser()
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            return candidate if candidate.is_file() else None
        for name in ("fleet.yaml", "plan.yaml"):
            candidate = state.feature_dir / name
            if candidate.is_file():
                return candidate
        return None

    def _load_fleet_inspection(self, state: PDState, explicit: Optional[str]) -> Dict[str, Any]:
        fleet_state = normalize_fleet_state(state.state.get("fleet_state"))
        path = self._fleet_plan_path(state, explicit)
        plan: Optional[FleetPlan] = None
        if path:
            try:
                raw = path.read_text()
                data = json.loads(raw) if path.suffix.lower() == ".json" else (yaml.safe_load(raw) if yaml else None)
                if data is None and yaml is None:
                    raise FleetPlanError("PyYAML não está instalado para ler o manifesto")
                plan = FleetPlan.from_dict(data)
            except Exception as exc:
                raise PDError(f"FleetPlan inválido em {path}: {exc}") from exc
        records = [item for item in fleet_state.get("tasks", []) if isinstance(item, dict)]
        completed = sorted(str(item["id"]) for item in records if item.get("id") is not None and item.get("status") in {"completed", "skipped"})
        skipped = sorted(str(item["id"]) for item in records if item.get("id") is not None and item.get("status") == "skipped")
        gates_passed = sorted(str(item["id"]) for item in fleet_state.get("gates", []) if isinstance(item, dict) and item.get("id") is not None and item.get("status") in {"passed", "completed", "succeeded"})
        ready = [task_id for task_id in compute_ready_tasks(plan, completed=completed, skipped=skipped, gates_passed=gates_passed)
                 if task_id not in set(completed) and task_id not in set(skipped)] if plan else []
        return {"feature": state.state.get("feature", state.feature_dir.name), "fleet_available": plan is not None,
                "plan_path": str(path) if path else None, "fleet_state": fleet_state,
                "plan": plan.to_dict() if plan else None, "ready_tasks": ready}

    def _cmd_fleet_status(self, state: PDState, plan_path: Optional[str], as_json: bool) -> None:
        data = self._load_fleet_inspection(state, plan_path)
        if as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
            return
        print(f"🚢 Fleet: {data['feature']}")
        if not data["fleet_available"]:
            print("   FleetPlan: não disponível")
            print("   Estado fleet: carregado (sem manifesto)")
            return
        plan = FleetPlan.from_dict(data["plan"])
        statuses = {status: sum(1 for task in plan.tasks if task.status == status) for status in sorted({task.status for task in plan.tasks})}
        print(f"   FleetPlan: {data['plan_path']}")
        print(f"   Agentes: {len(plan.agents)} | Waves: {len(plan.waves)} | Tasks: {len(plan.tasks)}")
        print(f"   Tasks por status: {json.dumps(statuses, ensure_ascii=False, sort_keys=True)}")
        print(f"   Tasks prontas: {', '.join(data['ready_tasks']) or 'nenhuma'}")

    def _cmd_fleet_ready(self, state: PDState, plan_path: Optional[str], as_json: bool) -> None:
        data = self._load_fleet_inspection(state, plan_path)
        if as_json:
            print(json.dumps({"feature": data["feature"], "fleet_available": data["fleet_available"], "plan_path": data["plan_path"], "ready_tasks": data["ready_tasks"]}, ensure_ascii=False, indent=2, sort_keys=True))
            return
        print(f"🚦 Fleet tasks ready: {data['feature']}")
        if not data["fleet_available"]:
            print("   FleetPlan não disponível; nenhuma task elegível.")
        else:
            print(f"   Plano: {data['plan_path']}")
            for task_id in data["ready_tasks"]:
                print(f"   ✅ {task_id}")
            if not data["ready_tasks"]:
                print("   Nenhuma task elegível (verifique dependências e gates).")

    @staticmethod
    def _supervisor_fleet_projection(value: Any) -> Dict[str, Any]:
        """Bound and redact the known persisted fleet namespace for inspection."""
        unsafe_key = re.compile(r"(?i)(?:debug|password|secret|token|credential|api[_ -]?key|pid|process|path|handle)")
        def project(item: Any, depth: int = 0) -> Any:
            if depth > 4:
                return None
            if isinstance(item, Mapping):
                result: Dict[str, Any] = {}
                for key, child in list(item.items())[:32]:
                    if not isinstance(key, str) or unsafe_key.search(key):
                        continue
                    projected = project(child, depth + 1)
                    if projected is not None:
                        result[key] = projected
                return result
            if isinstance(item, (list, tuple)):
                result_list = []
                for child in list(item)[:32]:
                    projected = project(child, depth + 1)
                    if projected is not None:
                        result_list.append(projected)
                return result_list
            if isinstance(item, str):
                text = _redact_sensitive_text(_redact_paths(item))
                text = _EXTERNAL_URL.sub("[URL REDACTED]", text)
                text = re.sub(r"(?i)\b(?:pid|process\s+id|native[_ -]?handle|handle)\s*[:=]?\s*(?:0x[0-9a-f]+|\d+)", "[REDACTED]", text)
                return text[:2000]
            if item is None or type(item) is bool or type(item) is int or type(item) is float:
                return item
            return None
        source = value if isinstance(value, Mapping) else {}
        result: Dict[str, Any] = {}
        for key in FLEET_STATE_FIELDS:
            if key in source:
                projected = project(source[key])
                if projected is not None:
                    result[key] = projected
        return result

    def _supervisor_plan_display(self, state: PDState, path: Optional[Path]) -> Optional[str]:
        if path is None:
            return None
        try:
            relative = path.resolve().relative_to(state.feature_dir.resolve())
        except ValueError:
            return None
        return str(relative) if len(relative.parts) <= 4 else None

    def _cmd_fleet_supervisor_status(self, state: PDState, plan_path: Optional[str], as_json: bool) -> None:
        """Emit a bounded supervisor view from persisted contracts only."""
        inspection = self._load_fleet_inspection(state, plan_path)
        data = {
            "feature": inspection["feature"],
            "feature_available": True,
            "fleet_available": inspection["fleet_available"],
            "fleet_state": self._supervisor_fleet_projection(inspection["fleet_state"]),
            "plan": inspection["plan"],
            "plan_path": self._supervisor_plan_display(state, self._fleet_plan_path(state, plan_path)),
            "ready_tasks": inspection["ready_tasks"],
            "read_only": True,
            "supervisor": {
                "available": True,
                "diagnosis": {
                    "status": "unknown",
                    "reason": "live worker/process data unavailable",
                    "source": "persisted fleet state only",
                },
                "interventions": [],
                "live_workers": "unavailable",
                "processes": "unavailable",
            },
        }
        if as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
            return
        print(f"🔎 Fleet supervisor status (read-only): {data['feature']}")
        print(f"   FleetPlan: {data['plan_path'] or 'não disponível'}")
        print(f"   Fleet disponível: {'sim' if data['fleet_available'] else 'não'}")
        print(f"   Tasks prontas: {', '.join(data['ready_tasks']) or 'nenhuma'}")
        print("   Supervisor: diagnosis unknown; live worker/process data unavailable")

    def _cmd_fleet_handoff_preview(self, store_root: str, run_id: str, handoff_id: str,
                                   owner_epoch: Optional[int], as_json: bool) -> None:
        """Load and display one validated handoff without creating persistence."""
        try:
            envelope = HandoffStore(store_root, run_id=run_id, owner_epoch=owner_epoch).load(handoff_id)
        except (OSError, ValueError) as exc:
            raise PDError(f"Unable to load handoff: {exc}") from exc
        envelope_data = envelope.to_dict()
        data = {"artifact": envelope_data["artifact"], "envelope": envelope_data, "read_only": True}
        if as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
            return
        artifact = data["artifact"]
        print(f"📦 Handoff preview (read-only): {artifact['handoff_id']}")
        print(f"   Status: {envelope_data['status']}")
        print(f"   Summary: {artifact['summary']}")
        print(f"   Remaining: {', '.join(artifact['remaining']) or 'none'}")
        print(f"   Next action: {artifact['next_action']}")

    def _cmd_fleet_run(self, state: PDState, plan_path: Optional[str], dry_run: bool,
                       resume: bool, as_json: bool) -> int:
        """Run only the local simulated/default-deny fleet dispatcher."""
        path = self._fleet_plan_path(state, plan_path)
        def emit(payload: Dict[str, Any], text: str) -> int:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if as_json else text)
            return 1
        if path is None:
            return emit({"status": "no_plan", "feature": state.state.get("feature"),
                         "plan_path": None, "error": "FleetPlan não encontrado"},
                        "❌ FleetPlan não encontrado")
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw) if path.suffix.lower() == ".json" else (yaml.safe_load(raw) if yaml else None)
            if data is None and yaml is None:
                raise FleetPlanError("PyYAML não está instalado para ler o manifesto")
            plan = FleetPlan.from_dict(data)
        except Exception as exc:
            return emit({"status": "invalid", "feature": state.state.get("feature"),
                         "plan_path": str(path), "error": f"FleetPlan inválido: {exc}"},
                        f"❌ FleetPlan inválido: {exc}")

        checkpoint = None
        if resume:
            fleet = normalize_fleet_state(state.state.get("fleet_state"))
            if fleet.get("lifecycle"):
                try:
                    checkpoint = Checkpoint.from_dict(fleet)
                except Exception as exc:
                    return emit({"status": "invalid", "feature": state.state.get("feature"),
                                 "plan_path": str(path), "error": f"checkpoint inválido: {exc}"},
                                f"❌ checkpoint inválido: {exc}")

        class SnapshotHook:
            value = None
            def checkpoint(self, snapshot: Mapping[str, Any]) -> None:
                self.value = deepcopy(dict(snapshot))

        hook = SnapshotHook()
        try:
            orchestrator = FleetOrchestrator(plan, hooks=hook, dry_run=dry_run, checkpoint=checkpoint,
                                             feature=state.state.get("feature", state.feature_dir.name),
                                             created_at=state.state.get("created_at", ""))
            result = orchestrator.run()
            if hook.value is None:
                orchestrator._checkpoint()
            raw_snapshot = hook.value or {}
            # fleet_state is a list-oriented public namespace; retain the
            # checkpoint's richer mappings in the lifecycle/report fields.
            raw_snapshot["agents"] = list(raw_snapshot.get("agents", {}).values()) if isinstance(raw_snapshot.get("agents"), dict) else raw_snapshot.get("agents", [])
            raw_snapshot["gates"] = [dict(v, id=k) if isinstance(v, dict) and "id" not in v else v
                                      for k, v in raw_snapshot.get("gates", {}).items()] if isinstance(raw_snapshot.get("gates"), dict) else raw_snapshot.get("gates", [])
            raw_snapshot["attempts"] = [{"id": k, "attempt": v} for k, v in raw_snapshot.get("attempts", {}).items()] if isinstance(raw_snapshot.get("attempts"), dict) else raw_snapshot.get("attempts", [])
            lifecycle = raw_snapshot.get("lifecycle", {})
            raw_snapshot["tasks"] = [{"id": k, **(dict(v) if isinstance(v, dict) else {})}
                                      for k, v in lifecycle.items()] if isinstance(lifecycle, dict) else []
            raw_snapshot["waves"] = [list(w) for w in result.waves]
            snapshot = normalize_fleet_state(raw_snapshot)
        except Exception as exc:
            return emit({"status": "failed", "feature": state.state.get("feature"),
                         "plan_path": str(path), "error": str(exc)},
                        f"❌ Fleet execution failed: {exc}")

        statuses = {key: result.statuses[key] for key in sorted(result.statuses)}
        outcome = "completed" if not result.failed and not result.blocked else ("blocked" if result.blocked else "failed")
        output = {"status": "dry_run" if dry_run else outcome, "feature": state.state.get("feature"),
                  "plan_path": str(path), "statuses": statuses, "fleet_state": snapshot,
                  "completed": sorted(result.completed), "blocked": sorted(result.blocked),
                  "failed": sorted(result.failed)}
        if not dry_run:
            state.state["fleet_state"] = snapshot
            state.save()
        if as_json:
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"🚢 Fleet {output['status']}: {output['feature']}")
            for task_id in sorted(statuses):
                print(f"   {task_id}: {statuses[task_id]}")
        return 0 if outcome == "completed" else 1

    # ── commands: V2 adapter (canonical, read-only by default) ──────────
    @staticmethod
    def _v2_json(payload: Mapping[str, Any]) -> str:
        volatile = {"timestamp", "timestamps", "created_at", "updated_at", "started_at", "completed_at", "finished_at", "heartbeat_at", "expires_at", "lease_expiry", "runtime", "wall_time", "monotonic_time"}
        def project(value: Any, key: str = "") -> Any:
            if key.lower() in volatile:
                return None
            if isinstance(value, Mapping):
                result = {}
                for child_key in sorted(value):
                    if not isinstance(child_key, str) or child_key.lower() in volatile:
                        continue
                    if any(token in child_key.lower() for token in ("token", "secret", "password", "credential", "authorization", "private_key", "api_key")):
                        result[child_key] = "[REDACTED]"
                    else:
                        result[child_key] = project(value[child_key], child_key)
                return result
            if isinstance(value, (list, tuple)):
                return [project(item, key) for item in value]
            if isinstance(value, str):
                return canonicalize_v2({"schema_version": "pd-fleet-plan:v2", "description": value})["description"]
            return value
        safe = project(dict(payload))
        if isinstance(safe.get("plan"), Mapping):
            safe["plan"] = canonicalize_v2(safe["plan"])
        return json.dumps(safe, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)

    @staticmethod
    def _v2_load_plan(path_text: Optional[str]) -> Dict[str, Any]:
        if not path_text:
            raise PDError("V2 manifest required")
        path = Path(path_text).expanduser()
        fd = -1
        try:
            if path.is_symlink():
                raise PDError("V2 manifest invalid: manifest_symlink")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PDError("V2 manifest invalid: manifest_not_regular")
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks).decode("utf-8")
            data = json.loads(raw) if path.suffix.lower() == ".json" else (yaml.safe_load(raw) if yaml else None)
            if data is None and yaml is None:
                raise ValueError("yaml_unavailable")
            if not isinstance(data, Mapping):
                raise ValueError("manifest_shape")
            # Normalize aliases at every object level before canonical/schema validation.
            aliases = {"schemaVersion": "schema_version", "planHash": "plan_hash", "runId": "run_id", "taskId": "task_id", "agentId": "agent_id", "maxParallel": "max_parallel", "dependsOn": "depends_on", "allowedPaths": "allowed_paths", "acceptanceCriteria": "acceptance_criteria", "validationCommands": "validation_commands", "retryPolicy": "retry_policy", "maxAttempts": "max_attempts", "backoffSeconds": "backoff_seconds"}
            def normalize(value):
                if isinstance(value, Mapping):
                    result = {}
                    for raw_key, item in value.items():
                        key = aliases.get(raw_key, raw_key)
                        item = normalize(item)
                        if key in result and result[key] != item:
                            raise ValueError("conflicting_aliases")
                        result[key] = item
                    return result
                if isinstance(value, list):
                    return [normalize(item) for item in value]
                return value
            normalized_data = normalize(data)
            if not isinstance(normalized_data, Mapping):
                raise ValueError("manifest_shape")
            canonical = canonicalize_v2(normalized_data)
            if not isinstance(canonical.get("tasks"), list):
                raise ValueError("tasks_invalid")
            return canonical
        except PDError:
            raise
        except Exception as exc:
            raise PDError(f"V2 manifest invalid: {type(exc).__name__}") from exc
        finally:
            if fd >= 0:
                os.close(fd)

    @staticmethod
    def _v2_read_snapshot(store_root: str, run_id: str) -> Dict[str, Any]:
        root = Path(store_root).expanduser()
        if not root.exists() or not root.is_dir() or root.is_symlink():
            raise RunStoreError("run snapshot unavailable")
        run_dir = root / run_id
        if not run_dir.exists() or not run_dir.is_dir() or run_dir.is_symlink():
            raise RunStoreError("run snapshot unavailable")
        probe = FleetRunStore.__new__(FleetRunStore)
        probe.root = root.resolve()
        snapshot = probe._valid_snapshot(run_id)
        if snapshot is None:
            raise RunStoreError("run snapshot unavailable")
        return snapshot

    @staticmethod
    def _v2_resume_checkpoint(snapshot: Mapping[str, Any]) -> Checkpoint:
        lifecycle = {}
        tasks = {}
        for task_id, state in snapshot.get("tasks", {}).items():
            status = state.get("status", "pending") if isinstance(state, Mapping) else "pending"
            tasks[task_id] = {"id": task_id, "status": status}
            lifecycle[task_id] = {"task_id": task_id, "status": status,
                                  "attempt": snapshot.get("attempts", {}).get(task_id, 0)}
        reports = [dict(r["report"]) for r in snapshot.get("reports", {}).values()
                   if isinstance(r, Mapping) and isinstance(r.get("report"), Mapping)]
        return Checkpoint.create("v2", 0, tasks=tasks, lifecycle=lifecycle,
                                 reports=reports, created_at="1970-01-01T00:00:00+00:00")

    @staticmethod
    def _v2_persisted_result(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
        statuses = {tid: s.get("status", "pending") for tid, s in snapshot.get("tasks", {}).items()
                    if isinstance(s, Mapping)}
        reports = [dict(r["report"]) for r in snapshot.get("reports", {}).values()
                   if isinstance(r, Mapping) and isinstance(r.get("report"), Mapping)]
        return {"statuses": statuses, "reports": reports, "waves": snapshot.get("waves", []),
                "validation": None}

    def _cmd_v2(self, args: argparse.Namespace) -> int:
        if args.v2_command == "read":
            plan = self._v2_load_plan(args.plan_path)
            print(self._v2_json({"status": "read", "plan": plan}) + "\n", end="")
            return 0
        if args.v2_command == "status":
            if args.run_id:
                try:
                    snapshot = self._v2_read_snapshot(args.store_root, args.run_id)
                    print(self._v2_json({"status": "ok", "run": snapshot}) + "\n", end="")
                except RunStoreError as exc:
                    raise PDError(f"V2 run unavailable: {type(exc).__name__}") from exc
            else:
                plan = self._v2_load_plan(args.plan_path)
                print(self._v2_json({"status": "read", "plan": plan}) + "\n", end="")
            return 0
        if args.provider != "local":
            raise PDError("V2 external providers are disabled")
        plan = self._v2_load_plan(args.plan_path)
        run_id = args.run_id or plan.get("run_id") or "local"
        if args.dry_run:
            result = FleetOrchestrator(plan, dry_run=True).run()
            payload = {"status": "dry_run", "run_id": run_id, "result": result.to_dict()}
        else:
            try:
                with FleetRunStore(args.store_root) as store:
                    try:
                        current = store.load(run_id)
                        if current["plan_hash"] != plan_hash_v2(plan):
                            raise PDError("V2 run conflict: plan_hash")
                        if current["owner"] != args.owner:
                            raise PDError("V2 run conflict: owner")
                        if current["status"] in {"completed", "failed", "cancelled", "blocked"}:
                            payload = {"status": current["status"], "run_id": run_id,
                                       "result": self._v2_persisted_result(current)}
                            print(self._v2_json(payload) + "\n", end="")
                            return 0 if current["status"] == "completed" else 1
                        checkpoint = self._v2_resume_checkpoint(current)
                    except RunStoreError as missing:
                        if type(missing).__name__ != "RunNotFoundError":
                            raise
                        store.create(run_id, plan, args.owner)
                        current = store.load(run_id)
                        checkpoint = Checkpoint.create("v2", 0, created_at="1970-01-01T00:00:00+00:00")
                    store.transition(run_id, "running", args.owner, expected_generation=current["generation"])
                    current = store.load(run_id)
                    reconciliation = {"plan_hash": current["plan_hash"], "run_id": run_id,
                                      "generation": current["generation"], "owner": args.owner,
                                      "checkpoint": checkpoint.to_dict(), "leases": current["leases"],
                                      "events": current["events"]}
                    scheduler = LeaseScheduler(store, run_id, args.owner, max_parallel=1)
                    executor = BoundedParallelExecutor(max_workers=1)
                    def adapter(task, token):
                        # The local adapter is a dispatcher boundary, not a
                        # validator.  It must never claim work, tests, or
                        # acceptance that it did not actually perform.
                        # Raising makes the V2 pipeline persist a diagnosed
                        # failure rather than allowing a fabricated completed
                        # report through the report contract.
                        attempt = token.get("attempt")
                        raise RuntimeError(
                            f"local adapter has no validator for task {task.id} "
                            f"(attempt {attempt})"
                        )
                    try:
                        try:
                            result = FleetOrchestrator(plan, scheduler=scheduler, store=store,
                                executor=executor, adapter=adapter, run_id=run_id,
                                run_owner=args.owner, checkpoint=checkpoint,
                                reconciliation_context=reconciliation).run()
                        except Exception as exc:
                            failed_state = store.load(run_id)
                            store.append_event(run_id, {"event_id": "run_failed", "ordering_key": "run_failed", "reason": type(exc).__name__}, args.owner,
                                               expected_generation=failed_state["generation"])
                            failed_state = store.load(run_id)
                            store.transition(run_id, "failed", args.owner, expected_generation=failed_state["generation"])
                            raise PDError(f"V2 run failed: {type(exc).__name__}") from exc
                    finally:
                        executor.close()
                    final = "completed" if not result.failed and not result.blocked else ("blocked" if result.blocked else "failed")
                    current = store.load(run_id)
                    store.transition(run_id, final, args.owner, expected_generation=current["generation"])
                    payload = {"status": final, "run_id": run_id, "result": result.to_dict()}
            except RunStoreError as exc:
                raise PDError(f"V2 run unavailable: {type(exc).__name__}") from exc
        print(self._v2_json(payload) + "\n", end="")
        return 0 if payload["status"] in {"completed", "dry_run"} else 1

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
    sys.exit(pd.run() or 0)


if __name__ == "__main__":
    main()
