"""Offline, in-process observability primitives for fleet runs."""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from threading import RLock
from types import MappingProxyType
from typing import Any
from .safe_rendering import safe_text

class ObservabilityError(ValueError):
    """Invalid or unsafe observability input."""

_URL = re.compile(r"(?i)(?:https?|ftp|wss?)://[^\s\"'<>]+")
_PATH = re.compile(r'''(?<![\w.])(?:~[\\/][^ \t\n\r\f\v"'<>;,]*|/[^ \t\n\r\f\v"'<>;,]+|[A-Za-z]:[\\/][^ \t\n\r\f\v"'<>;,]*|\\\\[^ \t\n\r\f\v"'<>;,]+)''')
_SECRET = re.compile(r"(?i)(?<!\w)(?:credential|secret|token|password|api[_ -]?key|access[_ -]?(?:key|token)|private[_ -]?key|client[_ -]?secret|authorization|bearer)\s*(?::|=)?\s*[^\s,;}]+")
_SECRET_VALUE = re.compile(r"(?i)(?:bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|AKIA[A-Z0-9]{12,})")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")

def _redact_text(value: str, limit: int) -> str:
    value = _URL.sub("[URL REDACTED]", value)
    value = _PATH.sub("[PATH REDACTED]", value)
    value = _SECRET.sub("[SECRET REDACTED]", value)
    return safe_text(_SECRET_VALUE.sub("[SECRET REDACTED]", value), "[UNSUPPORTED TYPE]", limit=limit)

def _immutable(value: Any, *, depth: int = 0, max_depth: int = 8,
               max_fields: int = 32, max_string_length: int = 1024) -> Any:
    if depth > max_depth: return "[DEPTH REDACTED]"
    if value is None or type(value) in (bool, int): return value
    if type(value) is float:
        if value != value or value in (float("inf"), float("-inf")): raise ObservabilityError("non-finite field")
        return value
    if type(value) is str: return _redact_text(value, max_string_length)
    if isinstance(value, Mapping):
        keys = list(value)
        if any(type(key) is not str or not key for key in keys):
            raise ObservabilityError("field keys must be non-empty strings")
        result = {}
        for key in sorted(keys)[:max_fields]:
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            result[key] = "[SECRET REDACTED]" if any(word in normalized for word in ("credential", "secret", "token", "password", "apikey", "accesskey", "accesstoken", "privatekey", "authorization")) else _immutable(value[key], depth=depth + 1, max_depth=max_depth, max_fields=max_fields, max_string_length=max_string_length)
        return MappingProxyType(result)
    if isinstance(value, (list, tuple)):
        return tuple(_immutable(item, depth=depth + 1, max_depth=max_depth, max_fields=max_fields, max_string_length=max_string_length) for item in value[:max_fields])
    if isinstance(value, (set, frozenset)):
        normalized = [_immutable(item, depth=depth + 1, max_depth=max_depth, max_fields=max_fields, max_string_length=max_string_length) for item in value]
        normalized.sort(key=lambda item: json.dumps(_plain(item), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return tuple(normalized[:max_fields])
    return "[UNSUPPORTED TYPE]"

def _plain(value: Any) -> Any:
    if isinstance(value, Mapping): return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)): return [_plain(item) for item in value]
    return value

@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    event: str
    correlation_id: str
    run_id: str | None
    task_id: str | None
    fields: Mapping[str, Any]
    def to_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "event": self.event, "correlation_id": self.correlation_id, "run_id": self.run_id, "task_id": self.task_id, "fields": _plain(self.fields)}

class AuditSink:
    """Bounded append-only local audit sink with deterministic snapshots."""
    def __init__(self, *, max_events: int = 10000, max_fields: int = 32, max_string_length: int = 1024) -> None:
        if any(type(item) is not int or item < 1 for item in (max_events, max_fields, max_string_length)): raise ObservabilityError("bounds must be positive integers")
        self.max_events, self.max_fields, self.max_string_length = max_events, max_fields, max_string_length
        self._events: list[AuditEvent] = []; self._counters: dict[str, int] = {}; self._sequence = 0; self._lock = RLock()
    @staticmethod
    def _id(value: str | None, name: str) -> str | None:
        if value is None: return None
        if type(value) is not str or not _ID.fullmatch(value): raise ObservabilityError(f"invalid {name}")
        return value
    def record(self, event: str, fields: Mapping[str, Any] | None = None, *, run_id: str | None = None, task_id: str | None = None, correlation_id: str | None = None) -> AuditEvent:
        if type(event) is not str or not _ID.fullmatch(event): raise ObservabilityError("invalid event")
        if fields is not None and not isinstance(fields, Mapping): raise ObservabilityError("fields must be an object")
        run_id, task_id = self._id(run_id, "run_id"), self._id(task_id, "task_id"); correlation_id = self._id(correlation_id, "correlation_id")
        with self._lock:
            if len(self._events) >= self.max_events: raise ObservabilityError("audit sink capacity exceeded")
            # Validate and freeze the payload before consuming a sequence. A
            # rejected record must not create a gap in the append-only stream.
            safe = _immutable(fields or {}, max_fields=self.max_fields, max_string_length=self.max_string_length)
            sequence = self._sequence + 1
            correlation_id = correlation_id or (f"corr-{run_id}-{task_id}" if run_id and task_id else f"corr-{sequence}")
            item = AuditEvent(sequence, event, correlation_id, run_id, task_id, safe); self._events.append(item); self._sequence = sequence; self._counters[event] = self._counters.get(event, 0) + 1
            return item
    emit = record
    record_event = record
    append = record
    append_event = record
    def increment(self, name: str, amount: int = 1) -> int:
        if type(name) is not str or not _ID.fullmatch(name) or type(amount) is not int or amount < 1: raise ObservabilityError("invalid counter")
        with self._lock: self._counters[name] = self._counters.get(name, 0) + amount; return self._counters[name]
    increment_counter = increment
    def events(self) -> tuple[Mapping[str, Any], ...]:
        with self._lock:
            return tuple(MappingProxyType({"sequence": item.sequence, "event": item.event,
                                           "correlation_id": item.correlation_id,
                                           "run_id": item.run_id, "task_id": item.task_id,
                                           "fields": item.fields}) for item in self._events)
    def export(self) -> dict[str, Any]:
        with self._lock: return {"events": [item.to_dict() for item in self._events], "counters": {key: self._counters[key] for key in sorted(self._counters)}}
    def export_json(self) -> str:
        return json.dumps(self.export(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

Observability = AuditSink
InProcessAuditSink = AuditSink
