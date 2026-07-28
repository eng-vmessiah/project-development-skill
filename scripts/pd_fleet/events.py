"""Envelope imutável e log local append-only de eventos da fleet."""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterator
from .safe_rendering import UNSUPPORTED_TYPE
from .clock import Clock, clock_iso

SCHEMA_VERSION = 1
MAX_STRING = 256
MAX_COLLECTION = 256
MAX_DEPTH = 8
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_EVENTS = 10000
MAX_QUERY = 1000
MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_LOG_LINE_BYTES = MAX_PAYLOAD_BYTES + 1024
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_URL = re.compile(r"(?:https?://|ftp://|www\.)", re.I)
_ABSOLUTE = re.compile(r"^(?:/|[A-Za-z]:[\\/]|\\\\)")
_SENSITIVE = re.compile(
    r"(?:secret|token|password|passwd|api[_-]?key|authorization|credential|prompt|cot|chain.?of.?thought|pid|process[_-]?id|handle|native|socket|url|uri|path)",
    re.I,
)
_SENSITIVE_VALUE = re.compile(
    r"(?:secret|password|api[_-]?key|authorization|chain.?of.?thought|\bcot\b)", re.I
)
_SENSITIVE_FIELD = re.compile(
    r"(?:\btoken\b|\bpassword\b|\bpasswd\b|\bcredential\b|\bauthorization\b|\bprompt\b|chain.?of.?thought|\bcot\b|"
    r"\bpid\b|process[_-]?id|native[_-]?handle|\bhandle\b)", re.I
)
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


class EventError(ValueError):
    """Evento inválido, stale, corrompido ou replay conflitante."""


def _string(value: Any, name: str, *, identifier: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_STRING or _CONTROL.search(value):
        raise EventError(f"{name} deve ser uma string bounded e sem control chars")
    if identifier and (not _ID.fullmatch(value) or value in {".", ".."}):
        raise EventError(f"{name} não é um identificador seguro")
    if _URL.search(value) or _ABSOLUTE.match(value):
        raise EventError(f"{name} contém URL ou path absoluto")
    # Envelope text is metadata, never a place for credentials, prompts, or
    # process/native handles. ISO timestamps are the one intentional use of
    # ':' in this schema; other colon/equal forms are unsafe metadata.
    if _SENSITIVE_FIELD.search(value) or (":" in value or "=" in value) and (
        name != "created_at" or not _TIMESTAMP.fullmatch(value)
    ):
        raise EventError(f"{name} contém texto sensível ou formato inseguro")
    return value


def _number(value: Any, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise EventError(f"{name} deve ser finito e não negativo")
    return value


def _created_at(value: Any) -> str:
    """Validate the supported timestamp syntax and its calendar semantics."""
    _string(value, "created_at")
    if not value.endswith("Z"):
        offset_hours = int(value[-6:-3])
        offset_minutes = int(value[-2:])
        if abs(offset_hours) > 23 or offset_minutes > 59:
            raise EventError("created_at contém um offset inválido")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventError("created_at não é um timestamp ISO válido") from exc
    return value


def _bounded_sequence(value: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    """Consume at most MAX_COLLECTION+1 values from a sequence."""
    try:
        iterator = iter(value)
        items: list[Any] = []
        for _ in range(MAX_COLLECTION + 1):
            try:
                items.append(next(iterator))
            except StopIteration:
                return tuple(items)
        raise EventError("payload excede o limite de coleção")
    except EventError:
        raise
    except Exception as exc:
        raise EventError("payload sequência não pôde ser lida") from exc


def _freeze(value: Any, depth: int = 0, *, key: str = "payload") -> Any:
    if depth > MAX_DEPTH:
        raise EventError("payload excede a profundidade máxima")
    if isinstance(value, str):
        if (len(value) > MAX_STRING or _CONTROL.search(value) or _URL.search(value)
                or _ABSOLUTE.match(value) or _SENSITIVE_VALUE.search(value)):
            raise EventError("payload contém string proibida")
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EventError("payload contém número não finito")
        return value
    if isinstance(value, Mapping):
        items = _bounded_items(value)
        result: dict[str, Any] = {}
        for raw_key, raw_value in items:
            if not isinstance(raw_key, str) or len(raw_key) > MAX_STRING or _CONTROL.search(raw_key) or _SENSITIVE.search(raw_key):
                raise EventError("payload contém chave sensível ou inválida")
            result[raw_key] = _freeze(raw_value, depth + 1, key=raw_key)
        return MappingProxyType(result)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item, depth + 1) for item in _bounded_sequence(value))
    raise EventError(f"tipo não JSON-safe no payload: {UNSUPPORTED_TYPE}")


def _bounded_items(value: Mapping[Any, Any]) -> list[tuple[Any, Any]]:
    """Consume at most MAX_COLLECTION+1 items from a custom mapping."""
    try:
        iterator = iter(value.items())
        items: list[tuple[Any, Any]] = []
        for _ in range(MAX_COLLECTION + 1):
            try:
                item = next(iterator)
            except StopIteration:
                return items
            if not isinstance(item, tuple) or len(item) != 2:
                raise EventError("payload mapping contém item inválido")
            items.append(item)
        raise EventError("payload excede o limite de coleção")
    except EventError:
        raise
    except Exception as exc:
        raise EventError("payload mapping não pôde ser lido") from exc


def _reject_symlink_components(path: Path) -> None:
    """Reject symlinks in every existing component, including ancestors."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            if current.is_symlink():
                raise EventError("caminho do log não pode conter symlink")
            current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise EventError("não foi possível verificar o caminho do log") from exc


def _open_nofollow(path: Path, flags: int, mode: int = 0o600) -> Any:
    """Open a final path without following a symlink where supported."""
    try:
        descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)
        return os.fdopen(descriptor, "rb")
    except OSError as exc:
        raise EventError("caminho final inseguro ou inacessível") from exc


def _open_append_nofollow(path: Path) -> Any:
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
        return os.fdopen(descriptor, "ab")
    except OSError as exc:
        raise EventError("caminho final inseguro ou inacessível") from exc


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key if type(key) is str else UNSUPPORTED_TYPE: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise EventError("evento não é JSON canonical") from exc


@dataclass(frozen=True)
class FleetEvent:
    schema_version: int = SCHEMA_VERSION
    event_id: str = ""
    run_id: str = ""
    task_id: str | None = None
    kind: str = ""
    ordering_key: str = ""
    sequence: int | float = 0
    owner_epoch: int | float | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""
    # Audit timestamp source; deliberately excluded from the event envelope.
    clock: Clock | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or isinstance(self.schema_version, bool):
            raise EventError("schema_version incompatível")
        for name in ("event_id", "run_id", "kind", "ordering_key"):
            _string(getattr(self, name), name, identifier=name in {"event_id", "run_id"})
        if self.task_id is not None:
            _string(self.task_id, "task_id", identifier=True)
        _number(self.sequence, "sequence")
        if self.owner_epoch is not None:
            _number(self.owner_epoch, "owner_epoch")
        created = self.created_at or clock_iso(self.clock)
        _created_at(created)
        frozen = _freeze(self.payload)
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "payload", frozen)
        raw = self.to_dict()
        if len(_canonical(raw)) > MAX_PAYLOAD_BYTES:
            raise EventError("evento excede o limite de payload")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "event_id": self.event_id, "run_id": self.run_id,
                "task_id": self.task_id, "kind": self.kind, "ordering_key": self.ordering_key,
                "sequence": self.sequence, "owner_epoch": self.owner_epoch, "payload": _thaw(self.payload),
                "created_at": self.created_at}

    def to_json(self) -> str:
        return _canonical(self.to_dict()).decode("utf-8")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FleetEvent":
        if not isinstance(value, Mapping):
            raise EventError("evento deve ser objeto")
        expected = {"schema_version", "event_id", "run_id", "task_id", "kind", "ordering_key", "sequence", "owner_epoch", "payload", "created_at"}
        items = _bounded_items(value)
        fields = dict(items)
        if set(fields) != expected or len(items) != len(fields):
            raise EventError("envelope contém campos desconhecidos ou ausentes")
        return cls(**fields)


class EventLog:
    """Log por run; leitura não cria diretórios e escrita é serializada por flock."""

    def __init__(self, root: str | os.PathLike[str], run_id: str,
                 owner_epoch: int | float | None = None, *, clock: Clock | None = None) -> None:
        self.root = Path(root)
        _string(run_id, "run_id", identifier=True)
        if owner_epoch is not None:
            _number(owner_epoch, "owner_epoch")
        self.run_id, self.owner_epoch, self.clock = run_id, owner_epoch, clock
        self._directory = self.root / run_id
        self._path = self._directory / "events.jsonl"
        self._lock_path = self._directory / ".events.lock"

    def create_event(self, **values: Any) -> FleetEvent:
        """Build an event using this log's run/ownership and audit clock."""
        values.setdefault("run_id", self.run_id)
        if self.owner_epoch is not None:
            values.setdefault("owner_epoch", self.owner_epoch)
        values.setdefault("clock", self.clock)
        return FleetEvent(**values)

    @contextmanager
    def _lock(self) -> Iterator[Any]:
        self._ensure_directory()
        try:
            descriptor = os.open(self._lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            handle = os.fdopen(descriptor, "a+b")
        except OSError as exc:
            raise EventError("arquivo de lock inseguro ou inacessível") from exc
        with handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield handle
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _ensure_directory(self) -> None:
        _reject_symlink_components(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        _reject_symlink_components(self.root)
        self._directory.mkdir(exist_ok=True)
        _reject_symlink_components(self._directory)
        _reject_symlink_components(self._lock_path)
        _reject_symlink_components(self._path)

    def _records(self) -> list[tuple[FleetEvent, bytes]]:
        _reject_symlink_components(self.root)
        _reject_symlink_components(self._directory)
        _reject_symlink_components(self._path)
        if not self._path.exists():
            return []
        records: list[tuple[FleetEvent, bytes]] = []
        try:
            if self._path.stat().st_size > MAX_LOG_BYTES:
                raise EventError("log excede o limite de bytes")
            with _open_nofollow(self._path, os.O_RDONLY) as handle:
                consumed = 0
                for _ in range(MAX_EVENTS + 1):
                    line = handle.readline(MAX_LOG_LINE_BYTES + 1)
                    if not line:
                        break
                    consumed += len(line)
                    if consumed > MAX_LOG_BYTES or len(line) > MAX_LOG_LINE_BYTES or not line.endswith(b"\n"):
                        raise EventError("log contém linha parcial ou grande demais")
                    try:
                        record = json.loads(line[:-1].decode("utf-8"))
                        if not isinstance(record, dict) or set(record) != {
                            "schema_version", "event_id", "run_id", "task_id", "kind", "ordering_key",
                            "sequence", "owner_epoch", "payload", "created_at", "checksum",
                        }:
                            raise EventError("registro contém campos desconhecidos")
                        checksum = record.pop("checksum")
                        canonical = _canonical(record)
                        if not isinstance(checksum, str) or hashlib.sha256(canonical).hexdigest() != checksum:
                            raise EventError("checksum inválido")
                        records.append((FleetEvent.from_dict(record), canonical))
                    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
                        raise EventError("registro de evento inválido") from exc
                else:
                    raise EventError("log excede o limite de eventos")
        except EventError:
            raise
        except OSError as exc:
            raise EventError("não foi possível ler o log") from exc
        return records

    def append(self, event: FleetEvent) -> FleetEvent:
        if not isinstance(event, FleetEvent):
            raise EventError("append exige FleetEvent")
        if event.run_id != self.run_id or self.owner_epoch is not None and event.owner_epoch != self.owner_epoch:
            raise EventError("evento stale ou fora da ownership")
        canonical = _canonical(event.to_dict())
        with self._lock():
            records = self._records()
            for existing, existing_bytes in records:
                if existing.event_id == event.event_id:
                    if existing_bytes == canonical:
                        return existing
                    raise EventError("colisão de event_id")
                if existing.sequence == event.sequence:
                    raise EventError("sequence duplicada")
            if records and event.sequence <= records[-1][0].sequence:
                raise EventError("sequence deve ser monotônica")
            record = json.loads(canonical)
            record["checksum"] = hashlib.sha256(canonical).hexdigest()
            line = _canonical(record) + b"\n"
            if len(records) >= MAX_EVENTS or len(line) > MAX_PAYLOAD_BYTES:
                raise EventError("append excede limites")
            with _open_append_nofollow(self._path) as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                directory_fd = os.open(self._directory, os.O_RDONLY)
                os.fsync(directory_fd)
                os.close(directory_fd)
            except OSError:
                pass
            return event

    def replay(self, *, limit: int = MAX_QUERY) -> tuple[FleetEvent, ...]:
        self._check_limit(limit)
        return tuple(item[0] for item in self._records()[:limit])

    def query(self, *, ordering_key: str | None = None, task_id: str | None = None, limit: int = MAX_QUERY) -> tuple[FleetEvent, ...]:
        self._check_limit(limit)
        if ordering_key is not None:
            _string(ordering_key, "ordering_key")
        if task_id is not None:
            _string(task_id, "task_id", identifier=True)
        events = [event for event, _ in self._records() if (ordering_key is None or event.ordering_key == ordering_key) and (task_id is None or event.task_id == task_id)]
        events.sort(key=lambda item: (item.ordering_key, item.sequence))
        return tuple(events[:limit])

    @staticmethod
    def _check_limit(limit: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_QUERY:
            raise EventError("limit fora dos limites")


__all__ = ["EventError", "EventLog", "FleetEvent", "SCHEMA_VERSION"]
