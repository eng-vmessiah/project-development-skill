"""Bounded lifecycle/checkpoint projections onto the append-only fleet event log."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .events import EventError, EventLog, FleetEvent
from .lifecycle import LifecycleState

_MAX_IDS = 128
_DEFAULT_CREATED_AT = "1970-01-01T00:00:00+00:00"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_UNSAFE_REASON = re.compile(
    r"(?:secret|token|password|passwd|api[_-]?key|authorization|credential|prompt|cot|chain.?of.?thought|pid|process[_-]?id|handle|native|https?://|ftp://|www\.|[\x00-\x1f\x7f])",
    re.I,
)


def _value(value: Any) -> Any:
    try:
        return getattr(value, "value", value)
    except Exception as exc:
        raise EventError("valor não pôde ser lido") from exc


def _safe_text(value: Any) -> bool:
    try:
        return (
            isinstance(value, str)
            and bool(value)
            and bool(value.strip())
            and len(value) <= 256
            and ":" not in value
            and "=" not in value
            and not _UNSAFE_REASON.search(value)
        )
    except Exception as exc:
        raise EventError("texto não pôde ser validado") from exc


def _safe_ids(values: Any) -> list[str]:
    result: list[str] = []
    try:
        iterator = iter(() if values is None else values)
    except Exception as exc:
        if values is None:
            return result
        raise EventError("ids não puderam ser lidos") from exc
    for _ in range(_MAX_IDS + 1):
        try:
            raw = next(iterator)
        except StopIteration:
            return result
        except Exception as exc:
            raise EventError("ids não puderam ser lidos") from exc
        value = _value(raw)
        try:
            valid = isinstance(value, str) and bool(_ID.fullmatch(value)) and not _UNSAFE_REASON.search(value)
        except Exception as exc:
            raise EventError("id não pôde ser validado") from exc
        if not valid:
            raise EventError("id inválido")
        result.append(value)
        if len(result) == _MAX_IDS:
            # Probe one final item so an unbounded source cannot be
            # silently accepted merely because its first IDs were valid.
            continue
    raise EventError("ids excedem o limite de coleção")


def _bounded_keys(value: Any) -> list[Any]:
    """Read at most ``_MAX_IDS + 1`` keys without materializing a mapping."""
    if not isinstance(value, Mapping):
        raise EventError("checkpoint mapping inválido")
    try:
        iterator = iter(value.keys())
        result: list[Any] = []
        for _ in range(_MAX_IDS + 1):
            try:
                result.append(next(iterator))
            except StopIteration:
                return result
        raise EventError("checkpoint mapping excede o limite de coleção")
    except EventError:
        raise
    except Exception as exc:
        raise EventError("checkpoint mapping não pôde ser lido") from exc


def _mapping_get(value: Mapping[Any, Any], key: Any, default: Any = None) -> Any:
    try:
        return value.get(key, default)
    except Exception as exc:
        raise EventError("checkpoint mapping não pôde ser lido") from exc


def _valid_state(value: Any, name: str) -> str:
    if isinstance(value, LifecycleState):
        return value.value
    if not isinstance(value, str):
        raise EventError(f"{name} inválido")
    try:
        return LifecycleState(value).value
    except Exception as exc:
        raise EventError(f"{name} inválido") from exc


def _created_at(value: Any) -> str:
    """Use the deterministic default only for omitted timestamps."""
    if value is None:
        return _DEFAULT_CREATED_AT
    if not isinstance(value, str) or not value:
        raise EventError("created_at inválido")
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
            raise EventError("created_at inválido")
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except EventError:
        raise
    except Exception as exc:
        raise EventError("created_at inválido") from exc
    return value


def _deepcopy(value: Any, name: str) -> Any:
    try:
        return deepcopy(value)
    except Exception as exc:
        raise EventError(f"{name} não pôde ser copiado") from exc


def _attribute(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name, default)
    except Exception as exc:
        raise EventError(f"{name} não pôde ser lido") from exc


def _present(value: Any) -> bool:
    try:
        return bool(value)
    except Exception as exc:
        raise EventError("valor não pôde ser avaliado") from exc


def _is_empty_mapping(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    try:
        return len(value) == 0
    except Exception as exc:
        raise EventError("checkpoint mapping não pôde ser avaliado") from exc


def _identity(run_id: str, task_id: str | None, sequence: int | float, kind: str) -> str:
    raw = json.dumps([run_id, task_id, sequence, kind], ensure_ascii=False, separators=(",", ":"))
    return "e2-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


class LifecycleEventRecorder:
    """Explicit, side-effect-free projection seam over :class:`EventLog`.

    Inputs are deep-copied before inspection.  Only the small summaries built
    here are passed to ``FleetEvent``; raw task outputs and checkpoint material
    never cross this boundary.
    """

    def __init__(self, event_log: EventLog, run_id: str | None = None,
                 owner_epoch: int | float | None = None) -> None:
        if not isinstance(event_log, EventLog):
            raise TypeError("event_log deve ser EventLog")
        if run_id is not None and run_id != event_log.run_id:
            raise EventError("run_id fora da ownership")
        if owner_epoch is not None and event_log.owner_epoch is not None and owner_epoch != event_log.owner_epoch:
            raise EventError("owner_epoch stale ou fora da ownership")
        self.event_log = event_log
        self.run_id = event_log.run_id
        self.owner_epoch = event_log.owner_epoch if owner_epoch is None else owner_epoch

    def record_transition(self, lifecycle: Any, from_state: Any, to_state: Any,
                          sequence: int | float, reason: str | None = None,
                          created_at: str | None = None) -> FleetEvent:
        snapshot = _deepcopy(lifecycle, "lifecycle")
        task_id = _attribute(snapshot, "task_id")
        if task_id is None and isinstance(snapshot, Mapping):
            task_id = _mapping_get(snapshot, "task_id")
            if task_id is None:
                task_id = _mapping_get(snapshot, "id")
        if not isinstance(task_id, str) or not _ID.fullmatch(task_id):
            raise EventError("lifecycle task_id inválido")
        attempt = _attribute(snapshot, "attempt", 0)
        if isinstance(snapshot, Mapping):
            attempt = _mapping_get(snapshot, "attempt", 0)
        if isinstance(attempt, bool) or not isinstance(attempt, (int, float)) or attempt < 0:
            raise EventError("lifecycle attempt inválido")
        payload: dict[str, Any] = {
            "from": _valid_state(from_state, "from_state"),
            "to": _valid_state(to_state, "to_state"),
            "attempt": attempt,
        }
        if reason is not None and reason != "":
            if not _safe_text(reason):
                raise EventError("reason inválido")
            payload["reason"] = reason
        event = FleetEvent(
            event_id=_identity(self.run_id, task_id, sequence, "lifecycle.transition"),
            run_id=self.run_id, task_id=task_id, kind="lifecycle.transition",
            ordering_key=task_id, sequence=sequence, owner_epoch=self.owner_epoch,
            payload=payload, created_at=_created_at(created_at),
        )
        return self.event_log.append(event)

    def record_checkpoint(self, checkpoint: Any, sequence: int | float,
                          created_at: str | None = None) -> FleetEvent:
        snapshot = _deepcopy(checkpoint, "checkpoint")
        if isinstance(snapshot, Mapping):
            feature = _mapping_get(snapshot, "feature")
            wave = _mapping_get(snapshot, "wave")
            tasks = _mapping_get(snapshot, "tasks", {})
            lifecycle = _mapping_get(snapshot, "lifecycle", {})
            reports = _mapping_get(snapshot, "reports", [])
            evidence = _mapping_get(snapshot, "evidence", [])
            blockers = _mapping_get(snapshot, "blockers", [])
            completed = _mapping_get(snapshot, "completed_task_ids", [])
            resume = _mapping_get(snapshot, "resume_task_ids", [])
        else:
            feature = _attribute(snapshot, "feature", "")
            wave = _attribute(snapshot, "wave", 0)
            tasks, lifecycle = _attribute(snapshot, "tasks", {}), _attribute(snapshot, "lifecycle", {})
            reports = _attribute(snapshot, "reports", [])
            evidence = _attribute(snapshot, "evidence", [])
            blockers = _attribute(snapshot, "blockers", [])
            completed_method = _attribute(snapshot, "completed_tasks")
            resume_method = _attribute(snapshot, "resume_tasks")
            try:
                completed = completed_method() if callable(completed_method) else []
                resume = resume_method() if callable(resume_method) else []
            except Exception as exc:
                raise EventError("checkpoint derivação não pôde ser lida") from exc
        # Validate persisted mappings even when explicit lists were supplied.
        # The two mappings must each be checked before either one is used as
        # the preferred snapshot for projection.
        self._validate_statuses(tasks, lifecycle)
        self._completed_from(tasks, lifecycle)
        if not _present(completed):
            completed = self._completed_from(tasks, lifecycle)
        if not _present(resume):
            resume = self._resume_from(tasks, lifecycle, completed)
        if not _safe_text(feature) or isinstance(wave, bool) or not isinstance(wave, int) or wave < 0:
            raise EventError("checkpoint summary inválido")
        summary = {
            "feature": feature, "wave": wave,
            "completed_task_ids": _safe_ids(completed), "resume_task_ids": _safe_ids(resume),
            "blocker_count": self._count(blockers), "report_count": self._count(reports),
            "evidence_count": self._count(evidence),
        }
        canonical = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        summary["digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        event = FleetEvent(
            event_id=_identity(self.run_id, None, sequence, "checkpoint.committed"),
            run_id=self.run_id, task_id=None, kind="checkpoint.committed", ordering_key="checkpoint",
            sequence=sequence, owner_epoch=self.owner_epoch, payload=summary,
            created_at=_created_at(created_at),
        )
        return self.event_log.append(event)

    @staticmethod
    def _count(value: Any) -> int:
        try:
            count = len(value)
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise EventError("coleção possui tamanho inválido")
            return min(count, _MAX_IDS)
        except EventError:
            raise
        except Exception as exc:
            raise EventError("coleção não pôde ser contada") from exc

    @staticmethod
    def _snapshot(mapping: Any, task_id: Any) -> Any:
        if not isinstance(mapping, Mapping):
            raise EventError("checkpoint mapping inválido")
        return _mapping_get(mapping, task_id, {})

    @staticmethod
    def _bounded_task_ids(tasks: Any, lifecycle: Any) -> list[Any]:
        # Mapping keys are input IDs too: apply exactly the same strict policy
        # as explicit completed/resume IDs, rather than only checking their
        # collection size.
        task_keys = _safe_ids(_bounded_keys(tasks))
        lifecycle_keys = _safe_ids(_bounded_keys(lifecycle))
        result = list(task_keys)
        seen = set()
        try:
            seen.update(task_keys)
            for key in lifecycle_keys:
                if key not in seen:
                    result.append(key)
                    seen.add(key)
        except Exception as exc:
            raise EventError("checkpoint mapping contém chaves inválidas") from exc
        if len(result) > _MAX_IDS:
            raise EventError("checkpoint excede o limite de tasks")
        return result

    @staticmethod
    def _validate_statuses(tasks: Any, lifecycle: Any) -> None:
        """Validate every record in both mappings before snapshot selection."""
        for mapping in (tasks, lifecycle):
            for task_id in _safe_ids(_bounded_keys(mapping)):
                LifecycleEventRecorder._status(
                    LifecycleEventRecorder._snapshot(mapping, task_id)
                )

    @staticmethod
    def _status(snapshot: Any, default: str | None = None) -> Any:
        if not isinstance(snapshot, Mapping):
            status = default
            state = None
        else:
            status = _mapping_get(snapshot, "status", None)
            state = _mapping_get(snapshot, "state", None)
        # Validate both aliases when present.  Projection still prefers
        # ``status`` for compatibility, but an invalid ``state`` cannot hide
        # behind a valid status (or vice versa).
        valid_status = None if status is None else _valid_state(_value(status), "checkpoint status")
        valid_state = None if state is None else _valid_state(_value(state), "checkpoint state")
        if valid_status is not None:
            return valid_status
        if valid_state is not None:
            return valid_state
        return None

    @staticmethod
    def _completed_from(tasks: Any, lifecycle: Any) -> list[str]:
        result: list[str] = []
        for task_id in LifecycleEventRecorder._bounded_task_ids(tasks, lifecycle):
            snap = LifecycleEventRecorder._snapshot(lifecycle, task_id)
            if _is_empty_mapping(snap):
                snap = LifecycleEventRecorder._snapshot(tasks, task_id)
            if LifecycleEventRecorder._status(snap) == LifecycleState.COMPLETED.value:
                result.append(task_id)
        return result

    @staticmethod
    def _resume_from(tasks: Any, lifecycle: Any, completed: Any) -> list[str]:
        completed_ids = _safe_ids(completed)
        done = set(completed_ids)
        result: list[str] = []
        for task_id in _bounded_keys(tasks):
            snap = LifecycleEventRecorder._snapshot(lifecycle, task_id)
            if _is_empty_mapping(snap):
                snap = LifecycleEventRecorder._snapshot(tasks, task_id)
            status = LifecycleEventRecorder._status(snap, "pending")
            if task_id not in done and status not in {"blocked", "skipped"}:
                result.append(task_id)
        return result

    def replay(self, **kwargs: Any) -> tuple[FleetEvent, ...]:
        return self.event_log.replay(**kwargs)

    def query(self, **kwargs: Any) -> tuple[FleetEvent, ...]:
        return self.event_log.query(**kwargs)


__all__ = ["LifecycleEventRecorder"]
