"""Read-only, bounded diagnostics for a fleet event log."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
import re
from types import MappingProxyType
from typing import Any

from .events import EventError, EventLog, FleetEvent, MAX_QUERY
from .lifecycle import LifecycleState

_STATUS = frozenset({"healthy", "degraded", "blocked", "unknown"})
_REASON_MALFORMED = "malformed_transition"
_REASON_INCONSISTENT = "inconsistent_transition"
_REASON_GAP = "sequence_gap"
_REASON_NON_INTEGER = "non_integer_sequence"
_REASON_DUPLICATE = "duplicate_sequence"
_REASON_NON_MONOTONIC = "non_monotonic_sequence"
_REASONS = frozenset({
    _REASON_MALFORMED, _REASON_INCONSISTENT, _REASON_GAP,
    _REASON_NON_INTEGER, _REASON_DUPLICATE, _REASON_NON_MONOTONIC,
})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MAX_REASONS = 32
_MAX_TASK_STATES = 256
_MAX_STRING = 256


def _bounded_tuple(value: Any, maximum: int, message: str) -> tuple[Any, ...]:
    """Detach a possibly hostile iterable without consuming it unboundedly."""
    try:
        iterator = iter(value)
        items: list[Any] = []
        for _ in range(maximum + 1):
            try:
                items.append(next(iterator))
            except StopIteration:
                return tuple(items)
        raise ValueError(message)
    except ValueError:
        raise
    except Exception:
        raise ValueError(message) from None


@dataclass(frozen=True)
class EventDiagnosticsReport:
    status: str
    event_count: int
    transition_count: int
    checkpoint_count: int
    first_sequence: int | float | None
    last_sequence: int | float | None
    sequence_gaps: tuple[int, ...]
    task_states: Mapping[str, str]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        # This is an output boundary: validate and detach before publishing any
        # caller-owned collection.  Deliberately use fixed errors so hostile
        # objects cannot smuggle their exception text into diagnostics.
        if type(self.status) is not str or self.status not in _STATUS:
            raise ValueError("invalid diagnostics status")

        def count(value: Any, name: str) -> int:
            if type(value) is not int or value < 0:
                raise ValueError(f"invalid diagnostics {name}")
            return value

        event_count = count(self.event_count, "event count")
        transition_count = count(self.transition_count, "transition count")
        checkpoint_count = count(self.checkpoint_count, "checkpoint count")
        if event_count > MAX_QUERY or transition_count > event_count or checkpoint_count > event_count:
            raise ValueError("diagnostics counts out of bounds")

        def sequence(value: Any) -> int | float | None:
            if value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("invalid diagnostics sequence")
            if not math.isfinite(value) or value < 0:
                raise ValueError("invalid diagnostics sequence")
            return value

        first_sequence = sequence(self.first_sequence)
        last_sequence = sequence(self.last_sequence)

        gaps = _bounded_tuple(self.sequence_gaps, 32, "invalid diagnostics sequence gaps")
        if len(gaps) > 32 or any(type(value) is not int or value < 0 for value in gaps):
            raise ValueError("invalid diagnostics sequence gaps")

        try:
            state_items = self.task_states.items()
        except Exception:
            raise ValueError("invalid diagnostics task states") from None
        items = _bounded_tuple(state_items, _MAX_TASK_STATES, "invalid diagnostics task states")
        if len(items) > _MAX_TASK_STATES:
            raise ValueError("invalid diagnostics task states")
        detached_states: dict[str, str] = {}
        for key, value in items:
            if (type(key) is not str or not _SAFE_ID.fullmatch(key)
                    or type(value) is not str or value not in {state.value for state in LifecycleState}):
                raise ValueError("invalid diagnostics task states")
            detached_states[key] = value

        report_reasons = _bounded_tuple(self.reasons, _MAX_REASONS, "invalid diagnostics reasons")
        if len(report_reasons) > _MAX_REASONS or any(
            type(reason) is not str or len(reason) > _MAX_STRING or reason not in _REASONS
            for reason in report_reasons
        ):
            raise ValueError("invalid diagnostics reasons")

        object.__setattr__(self, "event_count", event_count)
        object.__setattr__(self, "transition_count", transition_count)
        object.__setattr__(self, "checkpoint_count", checkpoint_count)
        object.__setattr__(self, "first_sequence", first_sequence)
        object.__setattr__(self, "last_sequence", last_sequence)
        object.__setattr__(self, "sequence_gaps", gaps)
        object.__setattr__(self, "reasons", report_reasons)
        object.__setattr__(self, "task_states", MappingProxyType(detached_states))

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh, stable JSON-safe snapshot (never the internal mapping)."""
        return {
            "checkpoint_count": self.checkpoint_count,
            "event_count": self.event_count,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "reasons": list(self.reasons),
            "sequence_gaps": list(self.sequence_gaps),
            "status": self.status,
            "task_states": {key: self.task_states[key] for key in sorted(self.task_states)},
            "transition_count": self.transition_count,
        }


def _empty_report() -> EventDiagnosticsReport:
    return EventDiagnosticsReport("unknown", 0, 0, 0, None, None, (), {}, ())


def _reason_add(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _state(value: Any) -> str | None:
    try:
        return LifecycleState(value).value
    except (TypeError, ValueError):
        return None


def _transition(event: FleetEvent, states: dict[str, str], reasons: list[str]) -> bool:
    """Project one transition without ever exposing its payload."""
    try:
        task_id = event.task_id
        payload = event.payload
        if not isinstance(task_id, str) or not task_id or not isinstance(payload, Mapping):
            raise ValueError
        from_state = _state(payload.get("from"))
        to_state = _state(payload.get("to"))
        if from_state is None or to_state is None:
            raise ValueError
        previous = states.get(task_id)
        if previous is not None and from_state != previous:
            _reason_add(reasons, _REASON_INCONSISTENT)
        states[task_id] = to_state
        return True
    except Exception:
        _reason_add(reasons, _REASON_MALFORMED)
        return False


def diagnose_event_log(
    event_log: EventLog,
    *,
    active_owner_epoch: int | float | None = None,
    limit: int = MAX_QUERY,
) -> EventDiagnosticsReport:
    """Diagnose at most ``limit`` replayed events without creating or mutating state."""
    if not isinstance(event_log, EventLog):
        raise TypeError("event_log deve ser EventLog")
    if active_owner_epoch is not None:
        if (isinstance(active_owner_epoch, bool)
                or not isinstance(active_owner_epoch, (int, float))
                or not math.isfinite(active_owner_epoch)
                or active_owner_epoch < 0):
            raise EventError("active_owner_epoch inválido")
        if active_owner_epoch != event_log.owner_epoch:
            raise EventError("owner_epoch stale ou fora da ownership")

    # replay() performs the EventLog's bounded validation and checksum checks;
    # importantly, its missing-file path is read-only and does not mkdir.
    events = event_log.replay(limit=limit)
    if not events:
        return _empty_report()

    states: dict[str, str] = {}
    reasons: list[str] = []
    try:
        sequences = [event.sequence for event in events]
    except Exception:
        raise EventError("replay contém sequência inválida") from None
    transitions = checkpoints = 0
    for event in events:
        if not isinstance(event, FleetEvent):
            raise EventError("replay contém evento inválido")
        try:
            if event.owner_epoch != event_log.owner_epoch and event_log.owner_epoch is not None:
                raise EventError("evento stale ou fora da ownership")
            kind = event.kind
            if kind == "lifecycle.transition":
                transitions += 1
                _transition(event, states, reasons)
            elif kind == "checkpoint.committed":
                checkpoints += 1
        except EventError:
            raise
        except Exception:
            # A malformed event object or hostile mapping is data, not a reason
            # to leak an implementation exception from this read-only report.
            _reason_add(reasons, _REASON_MALFORMED)

    integer_sequences = all(type(sequence) is int for sequence in sequences)
    numeric_sequences = all(
        not isinstance(sequence, bool)
        and isinstance(sequence, (int, float))
        and math.isfinite(sequence)
        and sequence >= 0
        for sequence in sequences
    )
    replay_anomaly = False
    if len(sequences) > 1 and numeric_sequences:
        for previous, current in zip(sequences, sequences[1:]):
            if current == previous:
                _reason_add(reasons, _REASON_DUPLICATE)
                replay_anomaly = True
            elif current < previous:
                _reason_add(reasons, _REASON_NON_MONOTONIC)
                replay_anomaly = True

    if not integer_sequences:
        _reason_add(reasons, _REASON_NON_INTEGER)
        gaps: tuple[int, ...] = ()
    elif replay_anomaly:
        # Gaps are meaningful only for a strictly increasing replay stream.
        # Sorting a corrupted stream would invent a false continuity claim.
        gaps = ()
    else:
        missing: list[int] = []
        for lower, upper in zip(sequences, sequences[1:]):
            lower, upper = int(lower), int(upper)
            if upper > lower + 1:
                for value in range(lower + 1, upper):
                    if len(missing) < 32:
                        missing.append(value)
                    else:
                        break
            if len(missing) >= 32:
                break
        gaps = tuple(missing)
        if gaps:
            _reason_add(reasons, _REASON_GAP)

    try:
        first_sequence, last_sequence = min(sequences), max(sequences)
    except Exception:
        raise EventError("replay contém sequência inválida") from None
    status = "degraded" if reasons else "healthy"
    return EventDiagnosticsReport(
        status, len(events), transitions, checkpoints,
        first_sequence, last_sequence, gaps, states, tuple(reasons),
    )


__all__ = ["EventDiagnosticsReport", "diagnose_event_log"]
