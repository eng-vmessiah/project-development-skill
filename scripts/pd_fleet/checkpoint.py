"""Versioned, pure checkpoint persistence for fleet task execution.

This module deliberately knows nothing about the CLI or an executor.  A
checkpoint is a JSON-safe snapshot and can therefore be written after every
lifecycle change and loaded by a later process.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import hashlib
import os
import re
import stat
from pathlib import Path
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

import fcntl

from .lifecycle import LifecycleState, TaskLifecycle

SCHEMA_VERSION = 1


class CheckpointError(ValueError):
    """Invalid, unreadable, or unsupported checkpoint."""


@dataclass
class Checkpoint:
    schema_version: int = SCHEMA_VERSION
    feature: str = ""
    wave: Any = 0
    tasks: dict[str, Any] = field(default_factory=dict)
    lifecycle: dict[str, dict[str, Any]] = field(default_factory=dict)
    reports: Any = field(default_factory=list)
    evidence: Any = field(default_factory=list)
    blockers: list[Any] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self) -> None:
        self.tasks = _task_mapping(self.tasks)
        self.lifecycle = _lifecycle_mapping(self.lifecycle)
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.validate()

    @classmethod
    def create(cls, feature: str, wave: Any, *, tasks: Any = None,
               lifecycle: Any = None, reports: Any = None, evidence: Any = None,
               blockers: Any = None, created_at: str | None = None) -> "Checkpoint":
        return cls(feature=feature, wave=wave, tasks=_task_mapping(tasks),
                   lifecycle=_lifecycle_mapping(lifecycle), reports=[] if reports is None else deepcopy(reports),
                   evidence=[] if evidence is None else deepcopy(evidence), blockers=[] if blockers is None else deepcopy(blockers),
                   created_at=created_at or "")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Checkpoint":
        if not isinstance(value, Mapping):
            raise CheckpointError("checkpoint deve ser um objeto JSON")
        data = deepcopy(dict(value))
        # Older producers used task records carrying lifecycle inline.
        data["tasks"] = _task_mapping(data.get("tasks"))
        data["lifecycle"] = _lifecycle_mapping(data.get("lifecycle"))
        if not data["lifecycle"]:
            for task_id, task in data["tasks"].items():
                if isinstance(task, Mapping) and ("status" in task or "state" in task):
                    data["lifecycle"][task_id] = _snapshot(task_id, task)
        return cls(schema_version=data.get("schema_version", SCHEMA_VERSION),
                   feature=data.get("feature", ""), wave=data.get("wave", 0),
                   tasks=data["tasks"], lifecycle=data["lifecycle"],
                   reports=data.get("reports", []), evidence=data.get("evidence", []),
                   blockers=data.get("blockers", []), created_at=data.get("created_at", ""))

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"schema_version": self.schema_version, "feature": self.feature,
                "wave": self.wave, "tasks": deepcopy(self.tasks),
                "lifecycle": deepcopy(self.lifecycle), "reports": deepcopy(self.reports),
                "evidence": deepcopy(self.evidence), "blockers": deepcopy(self.blockers),
                "created_at": self.created_at}

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version != SCHEMA_VERSION:
            raise CheckpointError(f"schema_version incompatível: {self.schema_version!r}")
        if not isinstance(self.feature, str) or not self.feature.strip():
            raise CheckpointError("feature deve ser string não vazia")
        if isinstance(self.wave, bool) or not isinstance(self.wave, int) or self.wave < 0:
            raise CheckpointError("wave deve ser inteiro >= 0")
        if not isinstance(self.created_at, str) or not self.created_at.strip():
            raise CheckpointError("created_at deve ser string não vazia")
        if not isinstance(self.tasks, Mapping) or not isinstance(self.lifecycle, Mapping):
            raise CheckpointError("tasks e lifecycle devem ser objetos")
        if not isinstance(self.reports, list) or not isinstance(self.evidence, list) or not isinstance(self.blockers, list):
            raise CheckpointError("reports, evidence e blockers devem ser listas")
        for task_id, task in self.tasks.items():
            if not isinstance(task_id, str) or not task_id.strip():
                raise CheckpointError("tasks contém task id inválido")
            if not isinstance(task, Mapping):
                raise CheckpointError(f"tasks.{task_id} deve ser objeto")
            if "id" in task and (not isinstance(task["id"], str) or not task["id"].strip()):
                raise CheckpointError(f"tasks.{task_id}.id deve ser string não vazia")
            if "id" in task and task["id"] != task_id:
                raise CheckpointError(f"tasks.{task_id}.id inconsistente")
        for task_id, snapshot in self.lifecycle.items():
            if not isinstance(task_id, str) or not task_id.strip():
                raise CheckpointError("lifecycle contém task id inválido")
            if not isinstance(snapshot, Mapping):
                raise CheckpointError(f"lifecycle.{task_id} deve ser objeto")
            if "task_id" in snapshot and (not isinstance(snapshot["task_id"], str) or not snapshot["task_id"].strip()):
                raise CheckpointError(f"lifecycle.{task_id}.task_id deve ser string não vazia")
            if "task_id" in snapshot and snapshot["task_id"] != task_id:
                raise CheckpointError(f"lifecycle.{task_id}.task_id inconsistente")
            status = snapshot.get("status", snapshot.get("state"))
            if status is not None and (not isinstance(status, str) or status not in {s.value for s in LifecycleState}):
                raise CheckpointError(f"estado inválido para task {task_id}: {status!r}")
            _validate_lifecycle_fields(task_id, snapshot)
        payload = {"schema_version": self.schema_version, "feature": self.feature, "wave": self.wave,
                   "tasks": self.tasks, "lifecycle": self.lifecycle, "reports": self.reports,
                   "evidence": self.evidence, "blockers": self.blockers, "created_at": self.created_at}
        try:
            json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError, OverflowError) as exc:
            raise CheckpointError(f"checkpoint não é JSON serializável: {exc}") from exc

    def save(self, path: str | os.PathLike[str]) -> None:
        save_checkpoint(self, path)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "Checkpoint":
        return load_checkpoint(path)

    def completed_tasks(self) -> list[str]:
        """Stable task IDs already completed; callers must not dispatch these."""
        result = []
        seen: set[str] = set()
        for task_id in [*self.tasks, *self.lifecycle]:
            if task_id in seen:
                continue
            seen.add(task_id)
            task = self.tasks.get(task_id, {})
            snap = self.lifecycle.get(task_id, task)
            status = snap.get("status", snap.get("state")) if isinstance(snap, Mapping) else None
            if status == LifecycleState.COMPLETED.value:
                result.append(task_id)
        return result

    completed = completed_tasks

    def resume_tasks(self) -> list[str]:
        """Tasks eligible for resume (completed tasks are intentionally excluded)."""
        completed = set(self.completed_tasks())
        result = []
        for task_id, task in self.tasks.items():
            if task_id in completed:
                continue
            snapshot = self.lifecycle.get(task_id, task)
            status = snapshot.get("status", snapshot.get("state", "pending")) if isinstance(snapshot, Mapping) else "pending"
            if status not in {"blocked", "skipped"}:
                result.append(task_id)
        return result

    def recover_orphans(self, *, now: Any, timeout_seconds: float = 300) -> list[str]:
        recovered = []
        for task_id, raw in self.lifecycle.items():
            if raw.get("status", raw.get("state")) != "running":
                continue
            life = _lifecycle(task_id, raw)
            if life.recover_orphan(now=now, timeout_seconds=timeout_seconds):
                self.lifecycle[task_id] = _snapshot(task_id, life)
                recovered.append(task_id)
        return recovered

    recover_orphaned = recover_orphans

    def retry_task(self, task_id: str, *, now: Any = None) -> dict[str, Any]:
        if task_id not in self.lifecycle:
            raise CheckpointError(f"task desconhecida: {task_id}")
        life = _lifecycle(task_id, self.lifecycle[task_id])
        life.retry(now=now)
        self.lifecycle[task_id] = _snapshot(task_id, life)
        return deepcopy(self.lifecycle[task_id])

    retry = retry_task


def save_checkpoint(checkpoint: Checkpoint | str | os.PathLike[str], path: str | os.PathLike[str] | Checkpoint) -> None:
    """Atomically save JSON.  Both ``(checkpoint, path)`` and ``(path, checkpoint)`` work."""
    if isinstance(checkpoint, (str, os.PathLike)):
        checkpoint, path = path, checkpoint
    if not isinstance(checkpoint, Checkpoint):
        checkpoint = Checkpoint.from_dict(checkpoint)  # type: ignore[arg-type]
    checkpoint.validate()
    target = Path(path)  # type: ignore[arg-type]
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(checkpoint.to_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, target)
        try:
            directory_fd = os.open(target.parent, os.O_DIRECTORY)
            try: os.fsync(directory_fd)
            finally: os.close(directory_fd)
        except OSError:  # directory fsync is not available on every filesystem
            pass
    except Exception:
        try: os.unlink(name)
        except FileNotFoundError: pass
        raise


def load_checkpoint(path: str | os.PathLike[str]) -> Checkpoint:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"checkpoint inválido ou ilegível: {path}") from exc
    return Checkpoint.from_dict(value)


def _task_mapping(value: Any) -> dict[str, Any]:
    if value is None: return {}
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise CheckpointError("tasks contém task id inválido")
            result[key] = deepcopy(item)
        return result
    if isinstance(value, list):
        result = {}
        for item in value:
            if isinstance(item, Mapping) and item.get("id") is not None:
                if not isinstance(item["id"], str) or not item["id"].strip():
                    raise CheckpointError("tasks contém id inválido")
                result[item["id"]] = deepcopy(dict(item))
            elif isinstance(item, str) and item.strip(): result[item] = {"id": item}
            else: raise CheckpointError("tasks contém registro sem id")
        return result
    raise CheckpointError("tasks deve ser objeto ou lista")


def _lifecycle_mapping(value: Any) -> dict[str, dict[str, Any]]:
    if value is None: return {}
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise CheckpointError("lifecycle contém task id inválido")
            if isinstance(item, TaskLifecycle): result[key] = _snapshot(key, item)
            elif isinstance(item, Mapping): result[key] = deepcopy(dict(item))
            else: raise CheckpointError(f"lifecycle.{key} deve ser objeto")
        return result
    if isinstance(value, (list, tuple)):
        result = {}
        for item in value:
            if isinstance(item, TaskLifecycle): result[item.task_id] = _snapshot(item.task_id, item)
            elif isinstance(item, Mapping) and item.get("task_id", item.get("id")) is not None:
                key = item.get("task_id", item.get("id"))
                if not isinstance(key, str) or not key.strip():
                    raise CheckpointError("lifecycle contém task_id inválido")
                result[key] = deepcopy(dict(item))
            else: raise CheckpointError("lifecycle contém registro sem task_id")
        return result
    raise CheckpointError("lifecycle deve ser objeto ou lista")


def _snapshot(task_id: str, value: Any) -> dict[str, Any]:
    if isinstance(value, TaskLifecycle):
        result = {"task_id": value.task_id, "status": value.status, "attempt": value.attempt,
                  "max_attempts": value.max_attempts, "agent": value.agent, "heartbeat": value.heartbeat,
                  "started_at": value.started_at, "finished_at": value.finished_at, "outputs": deepcopy(value.outputs),
                  "evidence": deepcopy(value.evidence), "reason": value.reason, "error": value.error,
                  "history": deepcopy(value.history), "final_report": deepcopy(value.final_report), "retryable": value.retryable}
        return result
    result = deepcopy(dict(value)); result.setdefault("task_id", task_id)
    if "state" in result and "status" not in result: result["status"] = result["state"]
    return result



def _validate_lifecycle_fields(task_id: str, snapshot: Mapping[str, Any]) -> None:
    """Validate persisted lifecycle data before constructing TaskLifecycle."""
    for name in ("attempt", "max_attempts"):
        if name in snapshot and (isinstance(snapshot[name], bool) or not isinstance(snapshot[name], int)):
            raise CheckpointError(f"lifecycle.{task_id}.{name} deve ser inteiro")
    if "attempt" in snapshot and snapshot["attempt"] < 0:
        raise CheckpointError(f"lifecycle.{task_id}.attempt deve ser >= 0")
    if "max_attempts" in snapshot and snapshot["max_attempts"] < 1:
        raise CheckpointError(f"lifecycle.{task_id}.max_attempts deve ser >= 1")
    if "attempt" in snapshot and "max_attempts" in snapshot and snapshot["attempt"] > snapshot["max_attempts"]:
        raise CheckpointError(f"lifecycle.{task_id}.attempt fora dos limites")
    if "retryable" in snapshot and not isinstance(snapshot["retryable"], bool):
        raise CheckpointError(f"lifecycle.{task_id}.retryable deve ser booleano")
    for name in ("heartbeat", "started_at", "finished_at"):
        value = snapshot.get(name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise CheckpointError(f"lifecycle.{task_id}.{name} deve ser número ou null")


def _lifecycle(task_id: str, value: Any) -> TaskLifecycle:
    data = _snapshot(task_id, value)
    data["state"] = data.pop("status", data.get("state", "pending"))
    allowed = {"task_id", "state", "attempt", "max_attempts", "agent", "heartbeat", "started_at", "finished_at", "outputs", "evidence", "reason", "error", "history", "final_report", "report_final", "retryable"}
    return TaskLifecycle(**{key: data[key] for key in allowed if key in data})


# Functional helpers keep integrations independent of the dataclass implementation.
def completed_tasks(checkpoint: Checkpoint) -> list[str]:
    return checkpoint.completed_tasks()


def resume_tasks(checkpoint: Checkpoint) -> list[str]:
    return checkpoint.resume_tasks()


def recover_orphans(checkpoint: Checkpoint, *, now: Any, timeout_seconds: float = 300) -> list[str]:
    return checkpoint.recover_orphans(now=now, timeout_seconds=timeout_seconds)


def retry_task(checkpoint: Checkpoint, task_id: str, *, now: Any = None) -> dict[str, Any]:
    return checkpoint.retry_task(task_id, now=now)


# Explicit aliases make the small API discoverable to integrations.
CheckpointStore = Checkpoint


# V2 durable envelope.  Kept below the V1 implementation deliberately: the
# original JSON shape and helpers remain byte-for-byte compatible.
V2_SCHEMA_VERSION = "pd-fleet-checkpoint:v2"

class CheckpointV2Store:
    """Small crash-safe checkpoint store with generation/CAS metadata."""
    schema_version = V2_SCHEMA_VERSION

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_id(run_id: str) -> str:
        if type(run_id) is not str or not run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
            raise CheckpointError("run_id/path traversal inválido")
        return run_id

    def _paths(self, run_id: str) -> tuple[Path, Path]:
        rid = self._safe_id(run_id)
        directory = self.root / rid
        try:
            if directory.is_symlink():
                raise CheckpointError("run path is symlink")
        except OSError as exc:
            raise CheckpointError("run path unavailable") from exc
        return directory / "checkpoint.json", directory / "checkpoint.json.bak"

    @contextmanager
    def _locked(self, directory: Path) -> Iterator[None]:
        """Serialize writers across processes; the lock itself is never followed."""
        lock = directory / ".checkpoint.lock"
        fd: int | None = None
        try:
            fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise CheckpointError("checkpoint lock inválido")
        except CheckpointError:
            if fd is not None:
                os.close(fd)
            raise
        except (OSError, TypeError, ValueError) as exc:
            if fd is not None:
                os.close(fd)
            raise CheckpointError("checkpoint lock indisponível") from exc
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError as exc:
            os.close(fd)
            raise CheckpointError("checkpoint lock indisponível") from exc
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    @staticmethod
    def _redact(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {(k if type(k) is str else "[UNSUPPORTED TYPE]"): ("[REDACTED]" if type(k) is str and re.search(r"(?i)(token|secret|password|credential|api[_ -]?key|authorization|private[_ -]?key)", k) else CheckpointV2Store._redact(v)) for k, v in value.items()}
        if isinstance(value, list): return [CheckpointV2Store._redact(v) for v in value]
        if isinstance(value, str):
            value = re.sub(r"(?i)(?:https?|ftp|wss?)://[^\s\"'<>]+", "[URL REDACTED]", value)
            # Redact the complete path, including UNC and tilde forms, so a
            # username/filename cannot survive as a suffix.
            return re.sub(
                r'''(?<![\w.])(?:~[\\/][^ \t\n\r\f\v\"'<>;,]*|/[^ \t\n\r\f\v\"'<>;,]+|[A-Za-z]:[\\/][^ \t\n\r\f\v\"'<>;,]*|\\\\[^ \t\n\r\f\v\"'<>;,]+)''',
                "[PATH REDACTED]",
                value,
            )
        return value

    @staticmethod
    def _checksum(envelope: Mapping[str, Any]) -> str:
        # Domain separation prevents a checkpoint checksum from being confused
        # with the plan hash (and deliberately invalidates pre-T2-05 V2 files).
        body = {k: v for k, v in envelope.items() if k != "checksum"}
        raw = (b"pd-fleet-checkpoint:v2\x00" + json.dumps(
            body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8"))
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def _seal(cls, run_id: str, checkpoint: Checkpoint, plan_hash_value: str, generation: int) -> dict[str, Any]:
        if type(plan_hash_value) is not str or len(plan_hash_value) != 64 or any(c not in "0123456789abcdef" for c in plan_hash_value):
            raise CheckpointError("plan_hash inválido")
        if type(generation) is not int or generation < 0:
            raise CheckpointError("generation inválida")
        envelope = {"schema_version": V2_SCHEMA_VERSION, "run_id": run_id,
                    "plan_hash": plan_hash_value, "generation": generation,
                    "checkpoint": cls._redact(checkpoint.to_dict())}
        envelope["checksum"] = cls._checksum(envelope)
        return envelope

    @classmethod
    def _valid(cls, value: Any, run_id: str, expected_plan_hash: str | None = None) -> bool:
        if not isinstance(value, Mapping) or set(value) != {"schema_version", "run_id", "plan_hash", "generation", "checkpoint", "checksum"}:
            return False
        plan_hash = value.get("plan_hash")
        if (value.get("schema_version") != V2_SCHEMA_VERSION or value.get("run_id") != run_id
                or type(plan_hash) is not str or not re.fullmatch(r"[0-9a-f]{64}", plan_hash)
                or (expected_plan_hash is not None and plan_hash != expected_plan_hash)):
            return False
        if type(value.get("generation")) is not int or value["generation"] < 0:
            return False
        try:
            if cls._checksum(value) != value["checksum"]: return False
            _validate_v2_nested(value["checkpoint"])
            Checkpoint.from_dict(value["checkpoint"])
        except (CheckpointError, TypeError, ValueError, OverflowError):
            return False
        return True

    def save(self, run_id: str, checkpoint: Checkpoint | Mapping[str, Any], *, plan_hash: str, generation: int,
             fault_injector: Any = None) -> dict[str, Any]:
        target, backup = self._paths(run_id)
        cp = checkpoint if isinstance(checkpoint, Checkpoint) else Checkpoint.from_dict(checkpoint)
        envelope = self._seal(run_id, cp, plan_hash, generation)
        directory = target.parent
        try:
            if directory.exists() and directory.is_symlink():
                raise CheckpointError("checkpoint path is symlink")
            directory.mkdir(parents=True, exist_ok=True)
        except CheckpointError:
            raise
        except OSError as exc:
            raise CheckpointError("checkpoint directory unavailable") from exc
        with self._locked(directory):
            # CAS is evaluated while holding the inter-process lock.
            current = self._candidates(run_id)
            if current and generation <= max(item["generation"] for item in current):
                raise CheckpointError("generation stale or non-increasing")
            for path in (target, backup):
                if path.is_symlink():
                    raise CheckpointError("checkpoint path is symlink")
            def fault(stage: str) -> None:
                if fault_injector is not None: fault_injector(stage)
            fd, temporary = tempfile.mkstemp(prefix=".checkpoint.", dir=str(directory))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    fault("write")
                    json.dump(envelope, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
                    handle.write("\n"); handle.flush(); fault("fsync"); os.fsync(handle.fileno())
                if target.exists():
                    fault("backup"); os.replace(target, backup)
                fault("replace"); os.replace(temporary, target)
                try:
                    fault("directory_fsync")
                    dfd = os.open(directory, os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
                    try: os.fsync(dfd)
                    finally: os.close(dfd)
                except OSError as exc:
                    raise CheckpointError("checkpoint directory fsync failed") from exc
            except CheckpointError:
                try: os.unlink(temporary)
                except FileNotFoundError: pass
                raise
            except Exception:
                try: os.unlink(temporary)
                except FileNotFoundError: pass
                raise
        return deepcopy(envelope)

    def _candidates(self, run_id: str, expected_plan_hash: str | None = None) -> list[dict[str, Any]]:
        target, backup = self._paths(run_id); found = []
        for path in (target, backup):
            fd: int | None = None
            try:
                # Open and validate the same descriptor: no symlink-check/open TOCTOU.
                fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                candidate_stat = os.fstat(fd)
                if not stat.S_ISREG(candidate_stat.st_mode) or candidate_stat.st_nlink != 1:
                    continue
                with os.fdopen(fd, "r", encoding="utf-8") as handle:
                    fd = None
                    value = json.load(handle)
                if self._valid(value, run_id, expected_plan_hash): found.append(dict(value))
            except (OSError, ValueError, UnicodeError, TypeError, CheckpointError):
                continue
            finally:
                if fd is not None:
                    os.close(fd)
        return found

    def load(self, run_id: str, *, expected_plan_hash: str | None = None, expected_generation: int | None = None) -> dict[str, Any]:
        if expected_plan_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_plan_hash):
            raise CheckpointError("plan hash drift")
        candidates = self._candidates(run_id, expected_plan_hash)
        if not candidates:
            if expected_plan_hash is not None and self._candidates(run_id):
                raise CheckpointError("plan hash drift")
            raise CheckpointError("checkpoint inválido ou ilegível")
        result = deepcopy(max(candidates, key=lambda item: item["generation"]))
        if expected_plan_hash is not None and result["plan_hash"] != expected_plan_hash:
            raise CheckpointError("plan hash drift")
        if expected_generation is not None and result["generation"] != expected_generation:
            raise CheckpointError("generation drift")
        return result

    def recover(self, run_id: str, *, expected_plan_hash: str | None = None, expected_generation: int | None = None,
                now: Any = None, timeout_seconds: float = 300) -> dict[str, Any]:
        envelope = self.load(run_id, expected_plan_hash=expected_plan_hash, expected_generation=expected_generation)
        checkpoint = Checkpoint.from_dict(envelope["checkpoint"])
        orphaned = checkpoint.recover_orphans(now=now, timeout_seconds=timeout_seconds) if now is not None else []
        if orphaned:
            envelope = self.save(run_id, checkpoint, plan_hash=envelope["plan_hash"], generation=envelope["generation"] + 1)
        envelope["orphaned"] = orphaned
        return envelope

    def resume(self, run_id: str, *, expected_plan_hash: str | None = None, expected_generation: int | None = None,
               now: Any = None, timeout_seconds: float = 300) -> dict[str, Any]:
        envelope = self.recover(run_id, expected_plan_hash=expected_plan_hash, expected_generation=expected_generation, now=now, timeout_seconds=timeout_seconds)
        checkpoint = Checkpoint.from_dict(envelope["checkpoint"])
        envelope["resume_tasks"] = checkpoint.resume_tasks()
        envelope["completed_tasks"] = checkpoint.completed_tasks()
        return deepcopy(envelope)



def _validate_v2_nested(value: Any) -> None:
    """Validate V2 structural records while isolating explicit extension payloads."""
    lifecycle_fields = {"task_id", "status", "state", "attempt", "max_attempts", "agent", "heartbeat",
                        "started_at", "finished_at", "outputs", "evidence", "reason", "error", "history",
                        "final_report", "report_final", "retryable"}
    task_fields = {"id", "name", "title", "description", "owner", "depends_on", "dependencies", "wave",
                   "status", "state", "metadata", "inputs", "outputs", "acceptance", "tags"}
    checkpoint_fields = {"schema_version", "feature", "wave", "tasks", "lifecycle", "reports", "evidence", "blockers", "created_at"}
    history_fields = {"from", "to", "reason"}
    report_fields = {"task_id", "status", "summary", "details", "content", "text", "report", "agent", "created_at", "outputs", "evidence", "error"}
    evidence_fields = {"task_id", "kind", "type", "path", "uri", "url", "sha256", "description", "value", "metadata"}
    blocker_fields = {"task_id", "reason", "details", "status"}
    extension_fields = {"metadata", "inputs", "outputs", "acceptance", "tags", "value", "details", "content"}
    unsafe = re.compile(r"(?i)(token|secret|password|credential|api[_ -]?key|authorization|private[_ -]?key)")

    def walk(item: Any, where: str, allowed: set[str] | None = None, extension: bool = False) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if not isinstance(key, str) or unsafe.search(key):
                    raise CheckpointError(f"campo inseguro em {where}")
                if allowed is not None and key not in allowed and not extension:
                    raise CheckpointError(f"campo desconhecido em {where}")
                walk(child, f"{where}.{key}", extension=extension or key in extension_fields)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{where}[{index}]", extension=extension)
        elif isinstance(item, (str, int, float, bool)) or item is None:
            if isinstance(item, float) and not __import__("math").isfinite(item):
                raise CheckpointError(f"valor inválido em {where}")
        else:
            raise CheckpointError(f"valor não JSON em {where}")

    if not isinstance(value, Mapping):
        raise CheckpointError("checkpoint V2 inválido")
    walk(value, "checkpoint", checkpoint_fields)
    tasks = value.get("tasks")
    if not isinstance(tasks, Mapping):
        raise CheckpointError("checkpoint.tasks deve ser objeto")
    for task_id, task in tasks.items():
        if not isinstance(task_id, str) or not task_id.strip() or not isinstance(task, Mapping):
            raise CheckpointError("registro de task inválido")
        walk(task, f"tasks.{task_id}", task_fields)
    lifecycle = value.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        raise CheckpointError("checkpoint.lifecycle deve ser objeto")
    for task_id, snapshot in lifecycle.items():
        if not isinstance(task_id, str) or not task_id.strip() or not isinstance(snapshot, Mapping):
            raise CheckpointError("registro de lifecycle inválido")
        walk(snapshot, f"lifecycle.{task_id}", lifecycle_fields)
        history = snapshot.get("history", [])
        if not isinstance(history, list):
            raise CheckpointError("history deve ser lista")
        for index, record in enumerate(history):
            if not isinstance(record, Mapping):
                raise CheckpointError("registro de history inválido")
            walk(record, f"lifecycle.{task_id}.history[{index}]", history_fields)
    for name, fields in (("reports", report_fields), ("evidence", evidence_fields), ("blockers", blocker_fields)):
        records = value.get(name)
        if not isinstance(records, list):
            raise CheckpointError(f"checkpoint.{name} deve ser lista")
        for index, record in enumerate(records):
            if isinstance(record, Mapping):
                walk(record, f"{name}[{index}]", fields)
            else:
                walk(record, f"{name}[{index}]")


DurableCheckpointStore = CheckpointV2Store
CheckpointStoreV2 = CheckpointV2Store

def save_checkpoint_v2(root: str | os.PathLike[str], run_id: str, checkpoint: Checkpoint | Mapping[str, Any], *, plan_hash: str, generation: int, fault_injector: Any = None) -> dict[str, Any]:
    return CheckpointV2Store(root).save(run_id, checkpoint, plan_hash=plan_hash, generation=generation, fault_injector=fault_injector)

def load_checkpoint_v2(root: str | os.PathLike[str], run_id: str, **kwargs: Any) -> dict[str, Any]:
    return CheckpointV2Store(root).load(run_id, **kwargs)

def recover_checkpoint_v2(root: str | os.PathLike[str], run_id: str, **kwargs: Any) -> dict[str, Any]:
    return CheckpointV2Store(root).recover(run_id, **kwargs)

def resume_checkpoint_v2(root: str | os.PathLike[str], run_id: str, **kwargs: Any) -> dict[str, Any]:
    return CheckpointV2Store(root).resume(run_id, **kwargs)
