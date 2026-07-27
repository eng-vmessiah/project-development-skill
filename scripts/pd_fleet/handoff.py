"""Bounded, redacted and resumable handoff contracts.

This module is deliberately local/in-process: ownership validation checks a supplied
snapshot and epoch, but does not claim to provide a distributed lease or CAS.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import PurePath
import re
import tempfile
import fcntl
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .contracts import _EXTERNAL_URL, _redact_paths, _redact_sensitive_text

MAX_ITEMS = 32
MAX_TEXT = 2000
MAX_ID = 200
_PROMPT_LIKE = re.compile(r"(?i)(?:ignore\s+(?:all\s+)?previous\s+instructions|system\s+prompt|chain[- _]of[- ]thought|full\s+prompt|developer\s+message|\bprompt\b\s*[:=])")
_OPERATIONAL_HANDLE = re.compile(r"(?i)(?:\bpid\b|process\s+id|native[_ -]?handle|\bhandle\b)\s*[:=#]?\s*(?:0x[0-9a-f]+|\d+)|\b0x[0-9a-f]{8,}\b")
_SECRET_ASSIGNMENT = re.compile(r"(?i)\b(?:api[_ -]?key|secret|token|password|credential)\s*[:=]")


def _unsafe_identifier(value: str) -> bool:
    return (bool(_EXTERNAL_URL.search(value)) or bool(_PROMPT_LIKE.search(value)) or
            bool(_OPERATIONAL_HANDLE.search(value)) or bool(_SECRET_ASSIGNMENT.search(value)) or
            value.startswith(("/", "\\", "~", "[PATH", "[URL")) or
            (len(value) >= 2 and value[1] == ":" and value[0].isalpha()) or "\\" in value or
            bool(re.search(r"(?:^|[=\s])/(?:[^\s]+)", value)))


class HandoffReason(str, Enum):
    RETRY = "retry"
    FALLBACK = "fallback"
    HANDOFF = "handoff"
    REPLAN = "replan"
    HUMAN_INTERVENTION = "human_intervention"

_LEGACY_REASONS = {"worker_lost": "fallback", "context_exhausted": "handoff", "phase_boundary": "handoff"}


def _sanitize_text(name: str, value: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > MAX_TEXT:
        raise ValueError(f"{name} must be a non-empty bounded string")
    if any(ord(char) < 32 for char in value if char not in "\n\t"):
        raise ValueError(f"{name} contains control characters")
    if _PROMPT_LIKE.search(value) or _OPERATIONAL_HANDLE.search(value):
        raise ValueError(f"{name} contains prohibited operational or prompt content")
    if _EXTERNAL_URL.search(value):
        value = _EXTERNAL_URL.sub("[URL REDACTED]", value)
    value = _redact_paths(value)
    value = _redact_sensitive_text(value).strip()
    if not value:
        raise ValueError(f"{name} became empty after redaction")
    return value


def _bounded_id(name: str, value: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > MAX_ID:
        raise ValueError(f"{name} must be a non-empty bounded string")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"invalid {name}")
    value = value.strip()
    if _unsafe_identifier(value):
        raise ValueError(f"invalid or unsafe {name}")
    return value


def _reason(value: str) -> str:
    if isinstance(value, HandoffReason):
        return value.value
    value = _LEGACY_REASONS.get(value, value)
    if value not in {item.value for item in HandoffReason}:
        raise ValueError("reason must be a bounded HandoffReason")
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    if type(value) is float and not math.isfinite(value):
        raise ValueError("non-finite number")
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset, set)):
        return [_thaw(item) for item in value]
    return value


def _items(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a list")
    result: list[str] = []
    for value in values:
        result.append(_sanitize_text(f"{name} item", value))
        if len(result) > MAX_ITEMS:
            raise ValueError(f"{name} exceeds item limit")
    return tuple(result)


def _bounded_refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("evidence_refs must be a list")
    result: list[str] = []
    for value in values:
        result.append(_ref(value))
        if len(result) > MAX_ITEMS:
            raise ValueError("evidence_refs exceeds item limit")
    return tuple(result)


def _ref(value: str) -> str:
    value = _sanitize_text("evidence_ref", value)
    if (_EXTERNAL_URL.search(value) or PurePath(value).is_absolute() or value.startswith("~")
            or value.startswith(("[PATH REDACTED]", "[URL REDACTED]"))):
        raise ValueError("evidence_ref must not be an absolute path")
    return value


def _safe_metadata(value: Any, *, depth: int = 0, count: list[int] | None = None) -> Any:
    if count is None:
        count = [0]
    if depth > 4:
        raise ValueError("safety metadata exceeds depth limit")
    count[0] += 1
    if count[0] > MAX_ITEMS:
        raise ValueError("safety metadata exceeds item limit")
    if isinstance(value, Mapping):
        if len(value) > MAX_ITEMS:
            raise ValueError("safety metadata exceeds item limit")
        result = {}
        for key, item in value.items():
            if (type(key) is not str or not key.strip() or len(key) > MAX_ID or _unsafe_identifier(key) or
                    re.fullmatch(r"(?i)(?:secret|secrets|token|password|credential|api[_ -]?key)", key.strip())):
                raise ValueError("unsafe safety metadata key")
            result[key.strip()] = _safe_metadata(item, depth=depth + 1, count=count)
        return MappingProxyType(result)
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_ITEMS:
            raise ValueError("safety metadata exceeds item limit")
        return tuple(_safe_metadata(item, depth=depth + 1, count=count) for item in value)
    if type(value) is str:
        return _sanitize_text("safety metadata", value)
    if type(value) is bool or value is None:
        return value
    if type(value) in (int, float):
        try:
            finite = math.isfinite(value)
        except (OverflowError, TypeError):
            finite = False
        if finite:
            return value
    raise ValueError("safety metadata contains invalid value")


@dataclass(frozen=True)
class HandoffLineage:
    mission_id: str
    mission_run_id: str
    task_id: str
    source_lane_id: str
    attempt_id: str
    session_id: str
    target_role: str
    owner_epoch: int

    def __post_init__(self) -> None:
        for name in ("mission_id", "mission_run_id", "task_id", "source_lane_id", "attempt_id", "session_id", "target_role"):
            object.__setattr__(self, name, _bounded_id(name, getattr(self, name)))
        if type(self.owner_epoch) is not int or self.owner_epoch < 0:
            raise ValueError("owner_epoch must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in ("mission_id", "mission_run_id", "task_id", "source_lane_id", "attempt_id", "session_id", "target_role", "owner_epoch")}

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


@dataclass(frozen=True)
class HandoffArtifact:
    handoff_id: str
    reason: str
    summary: str
    completed: tuple[str, ...]
    remaining: tuple[str, ...]
    decisions: tuple[str, ...]
    risks: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    next_action: str
    lineage: HandoffLineage
    safety: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "handoff_id", _bounded_id("handoff_id", self.handoff_id))
        object.__setattr__(self, "reason", _reason(self.reason))
        for name in ("summary", "next_action"):
            object.__setattr__(self, name, _sanitize_text(name, getattr(self, name)))
        object.__setattr__(self, "completed", _items("completed", self.completed))
        object.__setattr__(self, "remaining", _items("remaining", self.remaining))
        object.__setattr__(self, "decisions", _items("decisions", self.decisions))
        object.__setattr__(self, "risks", _items("risks", self.risks))
        object.__setattr__(self, "evidence_refs", _bounded_refs(self.evidence_refs))
        if not isinstance(self.lineage, HandoffLineage):
            raise ValueError("lineage must be HandoffLineage")
        if not isinstance(self.safety, Mapping):
            raise ValueError("safety must be a mapping")
        object.__setattr__(self, "safety", _safe_metadata(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {"handoff_id": self.handoff_id, "reason": self.reason, "summary": self.summary,
                "completed": list(self.completed), "remaining": list(self.remaining),
                "decisions": list(self.decisions), "risks": list(self.risks),
                "evidence_refs": list(self.evidence_refs), "next_action": self.next_action,
                "lineage": self.lineage.to_dict(), "safety": _thaw(self.safety)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def create_handoff(*, mission_id: str = "legacy-mission", mission_run_id: str, task_id: str,
                   source_lane_id: str, attempt_id: str = "legacy-attempt", session_id: str = "legacy-session",
                   target_role: str, owner_epoch: int, reason: str, summary: str,
                   completed: Iterable[str], remaining: Iterable[str], decisions: Iterable[str],
                   risks: Iterable[str], evidence_refs: Iterable[str], next_action: str,
                   notes: dict[str, Any] | None = None) -> HandoffArtifact:
    """Create a safe artifact. ``notes`` is intentionally never persisted."""
    lineage = HandoffLineage(mission_id, mission_run_id, task_id, source_lane_id, attempt_id, session_id, target_role, owner_epoch)
    reason = _reason(reason)
    refs = _bounded_refs(evidence_refs)
    if not refs:
        raise ValueError("evidence_refs must not be empty")
    identity = json.dumps({**lineage.to_dict(), "reason": reason}, sort_keys=True, separators=(",", ":")).encode()
    handoff_id = "handoff:" + hashlib.sha256(identity).hexdigest()
    return HandoffArtifact(handoff_id, reason, summary, _items("completed", completed), _items("remaining", remaining),
                           _items("decisions", decisions), _items("risks", risks), refs, next_action, lineage,
                           {"external_dispatch": False, "secrets_included": False, "native_handles_included": False,
                            "distributed_lease_or_cas": False})


def validate_handoff_epoch(artifact: HandoffArtifact, *, active_owner_epoch: int) -> bool:
    if not isinstance(artifact, HandoffArtifact) or type(active_owner_epoch) is not int or active_owner_epoch < 0:
        raise ValueError("invalid handoff or active_owner_epoch")
    return artifact.lineage.owner_epoch == active_owner_epoch


def validate_handoff_ownership(artifact: HandoffArtifact, *, mission_id: str, mission_run_id: str,
                               task_id: str, source_lane_id: str, attempt_id: str, session_id: str,
                               owner_epoch: int) -> bool:
    """Fail closed against stale/mismatched supplied ownership; not a distributed lease/CAS."""
    if not isinstance(artifact, HandoffArtifact):
        raise ValueError("artifact must be HandoffArtifact")
    expected = HandoffLineage(mission_id, mission_run_id, task_id, source_lane_id, attempt_id,
                              session_id, artifact.lineage.target_role, owner_epoch)
    if artifact.lineage != expected:
        raise ValueError("handoff ownership is stale or mismatched")
    return True


HANDOFF_SCHEMA_VERSION = 1
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")


def _safe_segment(name: str, value: str) -> str:
    if type(value) is not str or value in {".", ".."} or not _SAFE_SEGMENT.fullmatch(value):
        raise ValueError(f"{name} must be a safe path segment")
    return value


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("handoff envelope is not JSON-safe") from exc


@dataclass(frozen=True)
class HandoffEnvelope:
    """Immutable result returned by the bounded persistence boundary."""
    schema_version: int
    handoff_id: str
    artifact: HandoffArtifact
    status: str
    evidence_refs: tuple[str, ...]
    checksum: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "handoff_id": self.handoff_id,
                "artifact": self.artifact.to_dict(), "status": self.status,
                "evidence_refs": list(self.evidence_refs), "checksum": self.checksum}


class HandoffStore:
    """Small local persistence boundary, independent of fleet STATE/lifecycle."""

    def __init__(self, root: str | os.PathLike[str], *, run_id: str,
                 owner_epoch: int | None = None,
                 expected_lineage: HandoffLineage | None = None) -> None:
        self.root = os.fspath(root)
        self.run_id = _safe_segment("run_id", run_id)
        if owner_epoch is not None and (type(owner_epoch) is not int or owner_epoch < 0):
            raise ValueError("owner_epoch must be a non-negative integer")
        if expected_lineage is not None and not isinstance(expected_lineage, HandoffLineage):
            raise ValueError("expected_lineage must be HandoffLineage")
        if expected_lineage is not None and expected_lineage.mission_run_id != self.run_id:
            raise ValueError("expected_lineage does not match run_id")
        if owner_epoch is not None and expected_lineage is not None and owner_epoch != expected_lineage.owner_epoch:
            raise ValueError("owner_epoch does not match expected_lineage")
        self.owner_epoch = owner_epoch
        self.expected_lineage = expected_lineage

    def _directory(self, *, create: bool) -> str:
        root = os.path.abspath(self.root)
        self._reject_symlink_components(root, "handoff store root")
        if create:
            os.makedirs(root, exist_ok=True)
        elif not os.path.isdir(root):
            raise FileNotFoundError(root)
        directory = os.path.join(root, self.run_id)
        self._reject_symlink_components(directory, "handoff run directory")
        if create:
            os.makedirs(directory, exist_ok=True)
        elif not os.path.isdir(directory):
            raise FileNotFoundError(directory)
        if not os.path.isdir(directory):
            raise ValueError("handoff run directory is not a directory")
        return directory

    @staticmethod
    def _reject_symlink_components(path: str, label: str) -> None:
        current = os.path.sep
        for component in os.path.abspath(path).split(os.path.sep):
            if not component:
                continue
            current = os.path.join(current, component)
            if os.path.lexists(current) and os.path.islink(current):
                raise ValueError(f"{label} contains a symlink component")

    def _path(self, handoff_id: str) -> str:
        return os.path.join(self._directory(create=False), _safe_segment("handoff_id", handoff_id) + ".json")

    def _save_path(self, handoff_id: str) -> str:
        return os.path.join(self._directory(create=True), _safe_segment("handoff_id", handoff_id) + ".json")

    def _check_owner(self, artifact: HandoffArtifact) -> None:
        if artifact.lineage.mission_run_id != self.run_id:
            raise ValueError("handoff ownership is stale or mismatched")
        if self.owner_epoch is not None and artifact.lineage.owner_epoch != self.owner_epoch:
            raise ValueError("handoff ownership is stale or mismatched")
        if self.expected_lineage is not None and artifact.lineage != self.expected_lineage:
            raise ValueError("handoff ownership is stale or mismatched")

    @staticmethod
    def _payload(artifact: HandoffArtifact, status: str, evidence_refs: tuple[str, ...]) -> dict[str, Any]:
        return {"schema_version": HANDOFF_SCHEMA_VERSION, "handoff_id": artifact.handoff_id,
                "artifact": artifact.to_dict(), "status": status, "evidence_refs": list(evidence_refs)}

    @classmethod
    def _decode(cls, raw: bytes, *, requested_id: str) -> HandoffEnvelope:
        try:
            payload = json.loads(raw.decode("utf-8"))
            if type(payload) is not dict or set(payload) != {"schema_version", "handoff_id", "artifact", "status", "evidence_refs", "checksum"}:
                raise ValueError("malformed handoff envelope")
            checksum = payload.pop("checksum")
            if type(checksum) is not str or hashlib.sha256(_canonical_json(payload)).hexdigest() != checksum:
                raise ValueError("handoff checksum is invalid")
            if type(payload["schema_version"]) is not int or payload["schema_version"] != HANDOFF_SCHEMA_VERSION:
                raise ValueError("malformed handoff envelope")
            if type(payload["handoff_id"]) is not str or payload["handoff_id"] != requested_id:
                raise ValueError("malformed handoff envelope")
            if type(payload["evidence_refs"]) is not list or len(payload["evidence_refs"]) > MAX_ITEMS:
                raise ValueError("malformed evidence refs")
            artifact_data = payload["artifact"]
            required_artifact = {"handoff_id", "reason", "summary", "completed", "remaining", "decisions", "risks", "evidence_refs", "next_action", "lineage", "safety"}
            if type(artifact_data) is not dict or set(artifact_data) != required_artifact or artifact_data["handoff_id"] != requested_id:
                raise ValueError("malformed handoff artifact")
            for field in ("completed", "remaining", "decisions", "risks", "evidence_refs"):
                if type(artifact_data[field]) is not list:
                    raise ValueError("malformed handoff artifact")
            if type(artifact_data["lineage"]) is not dict or type(artifact_data["safety"]) is not dict:
                raise ValueError("malformed handoff artifact")
            lineage_data = artifact_data.pop("lineage")
            artifact = HandoffArtifact(
                artifact_data.pop("handoff_id"), artifact_data.pop("reason"), artifact_data.pop("summary"),
                tuple(artifact_data.pop("completed")), tuple(artifact_data.pop("remaining")),
                tuple(artifact_data.pop("decisions")), tuple(artifact_data.pop("risks")),
                tuple(artifact_data.pop("evidence_refs")), artifact_data.pop("next_action"),
                HandoffLineage(**lineage_data), artifact_data.pop("safety"))
            if artifact_data:
                raise ValueError("malformed handoff artifact")
            status = _sanitize_text("status", payload["status"])
            refs = tuple(_ref(item) for item in payload["evidence_refs"])
            return HandoffEnvelope(HANDOFF_SCHEMA_VERSION, requested_id, artifact, status, refs, checksum)
        except (KeyError, TypeError, AttributeError, json.JSONDecodeError, ValueError) as exc:
            if "checksum" in str(exc):
                raise
            raise ValueError("malformed handoff envelope") from exc

    def load(self, handoff_id: str) -> HandoffEnvelope:
        try:
            path = self._path(handoff_id)
        except FileNotFoundError as exc:
            raise ValueError("handoff record does not exist") from exc
        if os.path.islink(path):
            raise ValueError("handoff record is a symlink")
        try:
            with open(path, "rb") as handle:
                envelope = self._decode(handle.read(), requested_id=handoff_id)
        except FileNotFoundError as exc:
            raise ValueError("handoff record does not exist") from exc
        self._check_owner(envelope.artifact)
        return envelope

    def save(self, artifact: HandoffArtifact, *, status: str, evidence_refs: Iterable[str]) -> HandoffEnvelope:
        if not isinstance(artifact, HandoffArtifact):
            raise ValueError("artifact must be HandoffArtifact")
        self._check_owner(artifact)
        status = _sanitize_text("status", status)
        if isinstance(evidence_refs, (str, bytes)):
            raise ValueError("evidence_refs must be a list")
        refs = _bounded_refs(evidence_refs)
        payload = self._payload(artifact, status, refs)
        checksum = hashlib.sha256(_canonical_json(payload)).hexdigest()
        envelope = HandoffEnvelope(HANDOFF_SCHEMA_VERSION, artifact.handoff_id, artifact, status, refs, checksum)
        path = self._save_path(artifact.handoff_id)
        directory = os.path.dirname(path)
        encoded = _canonical_json({**payload, "checksum": checksum})
        lock_path = os.path.join(directory, ".handoff.lock")
        with open(lock_path, "a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if os.path.lexists(path):
                if os.path.islink(path):
                    raise ValueError("handoff record is a symlink")
                existing = self.load(artifact.handoff_id)
                if existing != envelope:
                    raise ValueError("conflicting reuse of handoff_id")
                return existing
            fd, temporary = tempfile.mkstemp(prefix=".handoff-", suffix=".tmp", dir=directory)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
                dir_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return envelope


__all__ = ["HANDOFF_SCHEMA_VERSION", "HandoffArtifact", "HandoffEnvelope", "HandoffLineage", "HandoffReason", "HandoffStore", "create_handoff", "validate_handoff_epoch", "validate_handoff_ownership"]
