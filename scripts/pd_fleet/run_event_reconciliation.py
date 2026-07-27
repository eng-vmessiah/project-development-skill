"""Read-only reconciliation between a persisted run snapshot and its event log."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
import re
import stat
from typing import Any, cast

from .events import EventError, EventLog, MAX_QUERY
from .run_store import FleetRunStore, RunNotFoundError

_STATUS = frozenset({"consistent", "degraded", "unknown"})
_REASONS = (
    "event_sequence_mismatch",
    "event_count_mismatch",
    "missing_store_snapshot",
    "missing_event_log",
    "run_id_mismatch",
    "owner_context_mismatch",
)
_REASON_SET = frozenset(_REASONS)
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_MAX_REASONS = len(_REASONS)


@dataclass(frozen=True)
class RunEventReconciliationReport:
    """A bounded, detached result of a run snapshot/log comparison."""

    status: str
    run_id: str
    snapshot_status: str | None
    snapshot_generation: int | None
    store_event_sequence: int | None
    event_log_count: int
    event_log_last_sequence: int | float | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.status) is not str or self.status not in _STATUS:
            raise ValueError("invalid reconciliation status")
        if type(self.run_id) is not str or not _ID.fullmatch(self.run_id):
            raise ValueError("invalid reconciliation run id")
        if self.snapshot_status is not None and (
            type(self.snapshot_status) is not str or len(self.snapshot_status) > 256
        ):
            raise ValueError("invalid snapshot status")

        def nonnegative_int(value: Any, name: str) -> int | None:
            if value is None:
                return None
            if type(value) is not int or value < 0:
                raise ValueError(f"invalid reconciliation {name}")
            return value

        generation = nonnegative_int(self.snapshot_generation, "generation")
        store_sequence = nonnegative_int(self.store_event_sequence, "event sequence")
        if type(self.event_log_count) is not int or self.event_log_count < 0 or self.event_log_count > MAX_QUERY:
            raise ValueError("invalid reconciliation event count")
        last = self.event_log_last_sequence
        if last is not None and (
            isinstance(last, bool) or not isinstance(last, (int, float))
            or not math.isfinite(last) or last < 0
        ):
            raise ValueError("invalid reconciliation last sequence")

        try:
            reasons = tuple(self.reasons)
        except Exception:
            raise ValueError("invalid reconciliation reasons") from None
        if (
            len(reasons) > _MAX_REASONS
            or any(type(reason) is not str or reason not in _REASON_SET for reason in reasons)
            or len(set(reasons)) != len(reasons)
        ):
            raise ValueError("invalid reconciliation reasons")
        if self.status == "consistent" and reasons:
            raise ValueError("consistent reconciliation cannot have reasons")
        if self.status == "unknown" and reasons:
            raise ValueError("unknown reconciliation cannot have reasons")

        object.__setattr__(self, "snapshot_generation", generation)
        object.__setattr__(self, "store_event_sequence", store_sequence)
        object.__setattr__(self, "reasons", reasons)

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-safe mapping with stable key ordering."""
        return {
            "event_log_count": self.event_log_count,
            "event_log_last_sequence": self.event_log_last_sequence,
            "reasons": list(self.reasons),
            "run_id": self.run_id,
            "snapshot_generation": self.snapshot_generation,
            "snapshot_status": self.snapshot_status,
            "status": self.status,
            "store_event_sequence": self.store_event_sequence,
        }


def _add(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _event_log_file_exists(event_log: EventLog) -> bool:
    """Classify the supplied log path without following or changing it."""
    path = getattr(event_log, "_path", None)
    if not hasattr(path, "__fspath__"):
        raise EventError("caminho do log inválido")
    path = cast(os.PathLike[str], path)
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise EventError("não foi possível verificar o caminho do log") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise EventError("caminho do log não aponta para arquivo regular")
    return True


def reconcile_run_events(
    store: FleetRunStore,
    event_log: EventLog,
    *,
    run_id: str,
    limit: int = MAX_QUERY,
) -> RunEventReconciliationReport:
    """Compare existing sources without creating, changing, or indexing either."""
    if not isinstance(store, FleetRunStore):
        raise TypeError("store deve ser FleetRunStore")
    if not isinstance(event_log, EventLog):
        raise TypeError("event_log deve ser EventLog")
    if type(run_id) is not str or not _ID.fullmatch(run_id):
        raise ValueError("run_id inválido")
    if isinstance(limit, bool) or type(limit) is not int or not 1 <= limit <= MAX_QUERY:
        raise ValueError("limit fora dos limites")

    # These are deliberately the only source reads.  In particular, do not
    # inspect paths or instantiate replacement stores/logs for absent sources.
    try:
        snapshot = store.load(run_id)
    except RunNotFoundError:
        snapshot = None
    events = event_log.replay(limit=limit)

    snapshot_exists = snapshot is not None
    log_exists = _event_log_file_exists(event_log)
    identity_mismatch = event_log.run_id != run_id or any(event.run_id != run_id for event in events)
    if not snapshot_exists and not log_exists and not identity_mismatch:
        return RunEventReconciliationReport("unknown", run_id, None, None, None, 0, None, ())

    reasons: list[str] = []
    if not snapshot_exists:
        _add(reasons, "missing_store_snapshot")
    if not log_exists:
        _add(reasons, "missing_event_log")

    snapshot_status = snapshot.get("status") if snapshot_exists else None
    snapshot_generation = snapshot.get("generation") if snapshot_exists else None
    store_sequence = snapshot.get("event_sequence") if snapshot_exists else None
    snapshot_events = snapshot.get("events", []) if snapshot_exists else []
    event_count = len(events)
    last_sequence = events[-1].sequence if events else (0 if log_exists else None)

    if snapshot_exists and snapshot.get("run_id") != run_id:
        _add(reasons, "run_id_mismatch")
    if event_log.run_id != run_id or any(event.run_id != run_id for event in events):
        _add(reasons, "run_id_mismatch")

    # EventLog's owner_epoch is the only owner context shared by all replayed
    # records.  Snapshot ``owner`` is a different identity namespace and is
    # therefore never compared to it or exported.
    if event_log.owner_epoch is not None and any(
        event.owner_epoch != event_log.owner_epoch for event in events
    ):
        _add(reasons, "owner_context_mismatch")

    if snapshot_exists and log_exists:
        if store_sequence != last_sequence:
            _add(reasons, "event_sequence_mismatch")
        if len(snapshot_events) != event_count:
            _add(reasons, "event_count_mismatch")

    status = "consistent" if not reasons else "degraded"
    ordered_reasons = tuple(reason for reason in _REASONS if reason in reasons)
    return RunEventReconciliationReport(
        status, run_id, snapshot_status, snapshot_generation, store_sequence,
        event_count, last_sequence, ordered_reasons,
    )


__all__ = ["RunEventReconciliationReport", "reconcile_run_events"]
