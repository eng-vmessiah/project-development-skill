"""Local-only, in-memory fake adapter for the PD Fleet → Hermes contract.

This module is intentionally isolated from the existing provider/runtime seams.
It has no runner, command, filesystem, network, credential, or Hermes capability.
It is a deterministic contract harness, not an execution runtime.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import re
import threading
from typing import Any, Mapping

SCHEMA_VERSION = "pd-fleet-hermes-adapter:v0"
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_ERROR_CODES = {
    "invalid_lineage", "owner_mismatch", "stale_generation", "stale_handle",
    "invalid_transition", "idempotency_conflict", "replay_in_progress",
    "input_too_large", "forbidden_field", "invalid_cursor", "cancel_not_confirmed",
    "cleanup_failed", "dispatch_not_allowed", "unknown_field",
}


class FakeAdapterError(ValueError):
    """Stable, bounded fake-adapter error."""

    def __init__(self, code: str):
        if code not in _ERROR_CODES:
            code = "invalid_lineage"
        self.code = code
        super().__init__(code)


_SENSITIVE_KEY = re.compile(r"(?i)(secret|token|password|credential|private[_ -]?key|access[_ -]?key|client[_ -]?key|api[_ -]?key|authorization|bearer)")


def _valid_id(value: Any) -> bool:
    return type(value) is str and len(value.encode("utf-8")) <= 128 and _SAFE_ID.fullmatch(value) is not None


_SECRET_VALUE = re.compile(r"(?i)(?:token|secret|password|credential|private[_ -]?key|access[_ -]?key|client[_ -]?key|api[_ -]?key)\s*[=:]\s*[^\s]+|bearer\s+[^\s]+")
_URL_VALUE = re.compile(r"(?i)https?://[^\s]+")
_PATH_VALUE = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:\\|/)[^\s]+|(?<![A-Za-z0-9])\\\\[^\s]+(?:\\[^\s]+)+")


def _redact_string(value: str) -> str:
    value = _URL_VALUE.sub("[REDACTED]", value)
    value = _PATH_VALUE.sub("[REDACTED]", value)
    return _SECRET_VALUE.sub("[REDACTED]", value)


def _redacted(value: Any, *, seen: set[int] | None = None, key: str = "", depth: int = 0) -> Any:
    if depth > 64:
        raise FakeAdapterError("input_too_large")
    seen = set() if seen is None else seen
    if isinstance(value, Mapping):
        marker = id(value)
        if marker in seen:
            raise FakeAdapterError("forbidden_field")
        seen.add(marker)
        try:
            sanitized = {}
            for raw_key, raw_value in value.items():
                if type(raw_key) is not str or any(ord(c) < 32 or ord(c) == 127 for c in raw_key):
                    raise FakeAdapterError("forbidden_field")
                sanitized[raw_key] = (
                    "[REDACTED]" if _SENSITIVE_KEY.search(raw_key)
                    else _redacted(raw_value, seen=seen, key=raw_key, depth=depth + 1)
                )
            return sanitized
        finally:
            seen.remove(marker)
    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in seen:
            raise FakeAdapterError("forbidden_field")
        seen.add(marker)
        try:
            return [_redacted(v, seen=seen, depth=depth + 1) for v in value]
        finally:
            seen.remove(marker)
    if isinstance(value, float) and not math.isfinite(value):
        raise FakeAdapterError("forbidden_field")
    if isinstance(value, str):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise FakeAdapterError("forbidden_field")
        return _redact_string(value)
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise FakeAdapterError("forbidden_field")


def canonical_request_fingerprint(request: Mapping[str, Any]) -> str:
    """Return the v0 redacted canonical request digest without trusting caller input."""
    if not isinstance(request, Mapping):
        raise FakeAdapterError("forbidden_field")
    body = {key: value for key, value in request.items() if key != "request_fingerprint"}
    canonical = json.dumps(_redacted(body), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    domain = b"pd-fleet-hermes-adapter:v0\x00request\x00"
    return "sha256:" + hashlib.sha256(domain + canonical).hexdigest()


class LifecycleState(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


_TERMINAL = {LifecycleState.SUCCEEDED, LifecycleState.FAILED, LifecycleState.TIMED_OUT, LifecycleState.CANCELLED}


@dataclass
class _Record:
    lineage: dict[str, str]
    owner: str
    generation: int
    status: LifecycleState = LifecycleState.QUEUED
    dispatch_count: int = 0
    sequence: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    replay: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    tombstones: set[tuple[str, str]] = field(default_factory=set)
    cleanup_marker: str = "not_cleaned"
    cleanup_result: dict[str, Any] | None = None


class FakeAgentRuntime:
    """Deterministic in-memory fake with a deliberately narrow public boundary."""

    def __init__(self, *, outcome: str = "succeeded", execute_gate: threading.Event | None = None, reservation_event: threading.Event | None = None):
        if outcome not in {"succeeded", "failed", "timed_out"}:
            raise ValueError("invalid outcome")
        self._outcome = outcome
        self._execute_gate = execute_gate
        self._reservation_event = reservation_event
        self._lock = threading.RLock()
        self._inflight: set[tuple[str, str]] = set()
        self._record: _Record | None = None
        self._next_handle = 1

    @property
    def dispatch_count(self) -> int:
        with self._lock:
            return 0 if self._record is None else self._record.dispatch_count

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            record = self._record
            if record is None:
                return {"status": None, "dispatch_count": 0, "sequence": 0, "cleanup_marker": "not_cleaned"}
            return {
                "status": record.status.value,
                "dispatch_count": record.dispatch_count,
                "sequence": record.sequence,
                "cleanup_marker": record.cleanup_marker,
                "tombstone_count": len(record.tombstones),
                "lineage": deepcopy(record.lineage),
            }

    def prepare(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self._prepare_unlocked(request)

    def _prepare_unlocked(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self._validate_envelope(request, "prepare", mutating=True)
        if self._record is not None:
            if self._lineage(request)["session_handle_id"] is not None:
                raise FakeAdapterError("invalid_lineage")
            self._validate_identity(request, require_handle=False)
            replay = self._replay(request)
            if replay is not None:
                return replay
            raise FakeAdapterError("invalid_transition")
        lineage = self._lineage(request)
        if lineage["session_handle_id"] is not None:
            raise FakeAdapterError("invalid_lineage")
        workspace = request.get("workspace")
        if (not isinstance(workspace, Mapping) or set(workspace) != {"workspace_id", "root_ref", "isolation", "cleanup_policy"}
                or workspace.get("workspace_id") != lineage["workspace_id"]
                or workspace.get("isolation") != "dedicated" or workspace.get("cleanup_policy") != "always"
                or not isinstance(workspace.get("root_ref"), str)
                or ".." in workspace["root_ref"] or not _valid_id(workspace["root_ref"])):
            raise FakeAdapterError("invalid_lineage")
        self._record = _Record(lineage=deepcopy(lineage), owner=request["owner"], generation=request["expected_generation"])
        record = self._record
        record.status = LifecycleState.PREPARING
        self._event("preparing")
        handle = f"handle-{self._next_handle:03d}"
        self._next_handle += 1
        record.lineage["session_handle_id"] = handle
        record.status = LifecycleState.READY
        result = self._result("ready", dispatch_count=0, attempt_id=record.lineage["attempt_id"], session_handle_id=handle)
        self._event("ready")
        result["event_sequence"] = record.sequence
        self._reserve(request, result)
        return deepcopy(result)

    def execute(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self._validate_envelope(request, "execute", mutating=True, check_fingerprint=False)
        self._validate_execute_input(request.get("input"))
        self._validate_request_fingerprint(request)
        self._validate_identity(request)
        payload = request.get("input")
        if (not isinstance(payload, Mapping) or set(payload) != {"goal_ref", "payload"}
                or not isinstance(payload.get("goal_ref"), str) or not _valid_id(payload["goal_ref"])
                or not isinstance(payload.get("payload"), str)):
            raise FakeAdapterError("input_too_large")
        if len(payload["payload"].encode("utf-8")) > 8192:
            raise FakeAdapterError("input_too_large")
        if any(ord(c) < 32 or ord(c) == 127 for c in payload["payload"]):
            raise FakeAdapterError("forbidden_field")
        key = (request["operation"], request["idempotency_key"])
        with self._lock:
            replay = self._replay(request)
            if replay is not None:
                return replay
            if key in self._inflight:
                raise FakeAdapterError("replay_in_progress")
            record = self._require_record()
            if record.status is not LifecycleState.READY:
                raise FakeAdapterError("invalid_transition")
            self._inflight.add(key)
            if self._reservation_event is not None:
                self._reservation_event.set()
        try:
            if self._execute_gate is not None:
                self._execute_gate.wait()
            with self._lock:
                record = self._require_record()
                if record.status is not LifecycleState.READY:
                    raise FakeAdapterError("invalid_transition")
                record.status = LifecycleState.RUNNING
                record.dispatch_count += 1
                self._event("running")
                record.status = LifecycleState(self._outcome)
                self._event(record.status.value)
                result = self._result(record.status.value, dispatch_count=record.dispatch_count, attempt_id=record.lineage["attempt_id"], session_handle_id=record.lineage["session_handle_id"])
                if record.status is not LifecycleState.SUCCEEDED:
                    result["error_code"] = None
                self._reserve(request, result)
                return deepcopy(result)
        finally:
            with self._lock:
                self._inflight.discard(key)

    def observe(self, request: Mapping[str, Any]) -> list[dict[str, Any]]:
        with self._lock:
            return self._observe_unlocked(request)

    def _observe_unlocked(self, request: Mapping[str, Any]) -> list[dict[str, Any]]:
        self._validate_envelope(request, "observe", mutating=False)
        self._validate_identity(request, require_owner=False, require_generation=False)
        cursor = request.get("cursor")
        if cursor is not None and (not isinstance(cursor, str) or len(cursor.encode("utf-8")) > 128 or re.fullmatch(r"event-[0-9]+", cursor) is None):
            raise FakeAdapterError("invalid_cursor")
        record = self._require_record()
        start = 0
        if cursor is not None:
            try:
                start = int(cursor.rsplit("-", 1)[1])
            except (ValueError, IndexError):
                raise FakeAdapterError("invalid_cursor") from None
        return deepcopy([event for event in record.events if event["sequence"] > start][:64])

    def cancel(self, request: Mapping[str, Any], *, confirm_termination: bool = False) -> dict[str, Any]:
        with self._lock:
            return self._cancel_unlocked(request, confirm_termination=confirm_termination)

    def _cancel_unlocked(self, request: Mapping[str, Any], *, confirm_termination: bool = False) -> dict[str, Any]:
        self._validate_envelope(request, "cancel", mutating=True)
        self._validate_identity(request)
        replay = self._replay(request)
        if replay is not None:
            return replay
        record = self._require_record()
        if record.status in _TERMINAL:
            if record.status is LifecycleState.CANCELLED:
                result = self._result("cancelled", dispatch_count=record.dispatch_count, cancel_confirmed=True, termination_ref="termination-001")
            elif record.status in {LifecycleState.FAILED, LifecycleState.TIMED_OUT}:
                result = self._result(record.status.value, dispatch_count=record.dispatch_count, error_code="cancel_not_confirmed", cancel_confirmed=False, termination_ref=None)
            else:
                raise FakeAdapterError("invalid_transition")
            for field_name in ("dispatch_count", "output_ref", "output_bytes"):
                result.pop(field_name, None)
            self._reserve(request, result)
            return deepcopy(result)
        record.status = LifecycleState.CANCELLING
        self._event("cancelling")
        if confirm_termination:
            record.status = LifecycleState.CANCELLED
            self._event("cancelled")
            result = self._result("cancelled", dispatch_count=record.dispatch_count, cancel_confirmed=True, termination_ref="termination-001")
            result.pop("dispatch_count", None)
            result.pop("output_ref", None)
            result.pop("output_bytes", None)
        else:
            result = self._result("failed", dispatch_count=record.dispatch_count, error_code="cancel_not_confirmed", cancel_confirmed=False, termination_ref=None)
            result.pop("dispatch_count", None)
            result.pop("output_ref", None)
            result.pop("output_bytes", None)
            record.status = LifecycleState.FAILED
            self._event("failed")
        self._reserve(request, result)
        return deepcopy(result)

    def handoff(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self._handoff_unlocked(request)

    def _handoff_unlocked(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self._validate_envelope(request, "handoff", mutating=True)
        self._validate_identity(request)
        replay = self._replay(request)
        if replay is not None:
            return replay
        if self._inflight:
            raise FakeAdapterError("replay_in_progress")
        record = self._require_record()
        result = {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": f"handoff-{record.sequence + 1:03d}",
            "artifact_version": 1,
            "lineage_ref": deepcopy(record.lineage),
            "status": record.status.value,
            "next_action": "resume_local_fake" if record.status not in _TERMINAL else "cleanup",
            "evidence_refs": [f"evidence-{record.sequence + 1:03d}"],
        }
        self._reserve(request, result)
        return deepcopy(result)

    def cleanup(self, request: Mapping[str, Any], *, succeed: bool = True) -> dict[str, Any]:
        with self._lock:
            return self._cleanup_unlocked(request, succeed=succeed)

    def _cleanup_unlocked(self, request: Mapping[str, Any], *, succeed: bool = True) -> dict[str, Any]:
        self._validate_envelope(request, "cleanup", mutating=True)
        self._validate_identity(request)
        replay = self._replay(request)
        if replay is not None:
            return replay
        record = self._require_record()
        if record.status not in _TERMINAL:
            raise FakeAdapterError("invalid_transition")
        if record.cleanup_result is not None:
            self._reserve(request, record.cleanup_result)
            return deepcopy(record.cleanup_result)
        record.cleanup_marker = "cleaning"
        if succeed:
            record.cleanup_marker = "cleaned"
            result = self._cleanup_result(record, True, None)
        else:
            record.cleanup_marker = "not_cleaned"
            result = self._cleanup_result(record, False, "cleanup_failed")
        record.cleanup_result = deepcopy(result) if succeed else None
        self._reserve(request, result)
        return deepcopy(result)

    def _validate_envelope(self, request: Mapping[str, Any], operation: str, *, mutating: bool, check_fingerprint: bool = True) -> None:
        if not isinstance(request, Mapping) or request.get("schema_version") != SCHEMA_VERSION or request.get("operation") != operation:
            raise FakeAdapterError("unknown_field")
        allowed = {
            "prepare": {"schema_version", "operation", "lineage", "owner", "expected_generation", "idempotency_key", "request_fingerprint", "workspace"},
            "execute": {"schema_version", "operation", "lineage", "owner", "expected_generation", "idempotency_key", "request_fingerprint", "input"},
            "observe": {"schema_version", "operation", "lineage", "cursor"},
            "cancel": {"schema_version", "operation", "lineage", "owner", "expected_generation", "idempotency_key", "request_fingerprint", "cancel_reason"},
            "handoff": {"schema_version", "operation", "lineage", "owner", "expected_generation", "idempotency_key", "request_fingerprint", "handoff_reason"},
            "cleanup": {"schema_version", "operation", "lineage", "owner", "expected_generation", "idempotency_key", "request_fingerprint", "cleanup_reason"},
        }[operation]
        if set(request) - allowed:
            raise FakeAdapterError("unknown_field")
        if mutating:
            for field_name in ("lineage", "owner", "expected_generation", "idempotency_key", "request_fingerprint"):
                if field_name not in request:
                    raise FakeAdapterError("unknown_field")
            if not isinstance(request["owner"], str) or not _valid_id(request["owner"]):
                raise FakeAdapterError("owner_mismatch")
            if type(request["expected_generation"]) is not int or request["expected_generation"] < 0:
                raise FakeAdapterError("stale_generation")
            if not isinstance(request["idempotency_key"], str) or not _valid_id(request["idempotency_key"]):
                raise FakeAdapterError("unknown_field")
            if not isinstance(request.get("request_fingerprint"), str) or not _FINGERPRINT.fullmatch(request["request_fingerprint"]):
                raise FakeAdapterError("unknown_field")
        if operation == "observe" and "cursor" not in request:
            raise FakeAdapterError("unknown_field")
        reason_name = {"cancel": "cancel_reason", "handoff": "handoff_reason", "cleanup": "cleanup_reason"}.get(operation)
        if reason_name is not None:
            reason = request.get(reason_name)
            if (not isinstance(reason, str) or not reason or len(reason.encode("utf-8")) > 256
                    or any(ord(c) < 32 or ord(c) == 127 for c in reason)):
                raise FakeAdapterError("forbidden_field")
        if mutating and check_fingerprint:
            try:
                self._validate_request_fingerprint(request)
            except FakeAdapterError:
                raise

    def _validate_request_fingerprint(self, request: Mapping[str, Any]) -> None:
        derived = canonical_request_fingerprint(request)
        if request["request_fingerprint"] != derived:
            key = (request["operation"], request["idempotency_key"])
            if self._record is None or key not in self._record.replay:
                raise FakeAdapterError("forbidden_field")

    def _validate_execute_input(self, payload: Any) -> None:
        if not isinstance(payload, Mapping) or len(payload) > 2 or set(payload) != {"goal_ref", "payload"}:
            raise FakeAdapterError("unknown_field")
        if not isinstance(payload.get("goal_ref"), str) or not _valid_id(payload["goal_ref"]):
            raise FakeAdapterError("input_too_large")
        if not isinstance(payload.get("payload"), str):
            raise FakeAdapterError("input_too_large")
        if len(payload["payload"].encode("utf-8")) > 8192:
            raise FakeAdapterError("input_too_large")
        if any(ord(c) < 32 or ord(c) == 127 for c in payload["payload"]):
            raise FakeAdapterError("forbidden_field")

    def _lineage(self, request: Mapping[str, Any]) -> dict[str, Any]:
        lineage = request.get("lineage")
        if not isinstance(lineage, Mapping):
            raise FakeAdapterError("invalid_lineage")
        required = {"run_id", "task_id", "attempt_id", "session_handle_id", "workspace_id"}
        if set(lineage) != required:
            raise FakeAdapterError("invalid_lineage")
        for key, value in lineage.items():
            if key != "session_handle_id" and (not isinstance(value, str) or not _valid_id(value)):
                raise FakeAdapterError("invalid_lineage")
        if lineage["session_handle_id"] is not None and (not isinstance(lineage["session_handle_id"], str) or not _valid_id(lineage["session_handle_id"])):
            raise FakeAdapterError("invalid_lineage")
        return dict(lineage)

    def _validate_identity(self, request: Mapping[str, Any], *, require_handle: bool = True, require_owner: bool = True, require_generation: bool = True) -> None:
        record = self._require_record()
        supplied = self._lineage(request)
        if supplied.get("run_id") != record.lineage["run_id"] or supplied.get("task_id") != record.lineage["task_id"] or supplied.get("attempt_id") != record.lineage["attempt_id"] or supplied.get("workspace_id") != record.lineage["workspace_id"]:
            raise FakeAdapterError("invalid_lineage")
        if require_owner and request.get("owner") != record.owner:
            raise FakeAdapterError("owner_mismatch")
        if require_generation and request.get("expected_generation") != record.generation:
            raise FakeAdapterError("stale_generation")
        if require_handle and supplied.get("session_handle_id") != record.lineage["session_handle_id"]:
            raise FakeAdapterError("stale_handle")

    def _require_record(self) -> _Record:
        if self._record is None:
            raise FakeAdapterError("invalid_lineage")
        return self._record

    def _replay(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        record = self._require_record()
        key = (request["operation"], request["idempotency_key"])
        existing = record.replay.get(key)
        if existing is None:
            return None
        if existing["_fingerprint"] != request.get("request_fingerprint"):
            raise FakeAdapterError("idempotency_conflict")
        return deepcopy(existing["result"])

    def _reserve(self, request: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        record = self._require_record()
        key = (request["operation"], request["idempotency_key"])
        record.replay[key] = {"_fingerprint": request.get("request_fingerprint"), "result": deepcopy(dict(result))}
        if result.get("status") in {state.value for state in _TERMINAL} or result.get("cleanup_marker") == "cleaned":
            record.tombstones.add(key)

    def _event(self, event_type: str) -> None:
        record = self._require_record()
        record.sequence += 1
        record.events.append({
            "schema_version": SCHEMA_VERSION,
            "event_id": f"event-{record.sequence:03d}",
            "sequence": record.sequence,
            "event_type": event_type,
            "run_id": record.lineage["run_id"],
            "task_id": record.lineage["task_id"],
            "attempt_id": record.lineage["attempt_id"],
            "status": record.status.value,
            "payload_ref": f"payload-{record.sequence:03d}",
        })

    def _result(self, status: str, *, dispatch_count: int, error_code: str | None = None, cancel_confirmed: bool | None = None, termination_ref: str | None = None, attempt_id: str | None = None, session_handle_id: str | None = None) -> dict[str, Any]:
        record = self._require_record()
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "error_code": error_code,
            "lineage_ref": deepcopy(record.lineage),
            "event_sequence": record.sequence,
            "evidence_refs": [f"evidence-{record.sequence:03d}"],
            "dispatch_count": dispatch_count,
        }
        if attempt_id is not None:
            result["attempt_id"] = attempt_id
        if session_handle_id is not None:
            result["session_handle_id"] = session_handle_id
        if status in {"succeeded", "failed", "timed_out"}:
            result["output_ref"] = f"output-{record.sequence:03d}"
            result["output_bytes"] = 0
        if cancel_confirmed is not None:
            result["cancel_confirmed"] = cancel_confirmed
            result["termination_ref"] = termination_ref
        return result

    def _cleanup_result(self, record: _Record, confirmed: bool, error_code: str | None) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "cleaned" if confirmed else "cleanup_failed",
            "error_code": error_code,
            "lineage_ref": deepcopy(record.lineage),
            "event_sequence": record.sequence,
            "evidence_refs": [f"evidence-cleanup-{record.sequence:03d}"],
            "cleanup_marker": record.cleanup_marker,
            "original_terminal_status": record.status.value,
            "cleanup_confirmed": confirmed,
        }
