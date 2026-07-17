"""Versioned, JSON-safe contracts exchanged with fleet agents.

The models in this module are deliberately passive: they never execute commands,
access the network, or resolve paths.  An empty ``allowed_paths`` is intentional
and means that an agent has no write scope (default deny).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import math
import re
from typing import Any, ClassVar, Mapping

SCHEMA_VERSION = "1"


class ContractError(ValueError):
    """Invalid, unsafe, or incomplete contract/report."""


class ContractValidationError(ContractError):
    pass


_SENSITIVE_KEYS = frozenset({
    "credential", "secret", "token", "password", "api_key", "access_key", "access_token",
    "private_key", "client_secret", "authorization", "bearer",
})
_SECRET_VALUE = re.compile(r"(?:bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|AKIA[A-Z0-9]{12,})", re.I)
_EXTERNAL_URL = re.compile(r"(?i)(?:https?|ftp|wss?)://[^\s\"'<>]+")
_ASSIGNMENT = re.compile(r"(?i)([A-Za-z][A-Za-z0-9_. -]{1,80})\s*[:=]\s*(\S+)")
_SENSITIVE_VALUE = re.compile(
    r"(?i)(?<![a-z0-9_])((?:credential|secret|token|password|api[_ -]?key|access[_ -]?(?:key|token)|"
    r"private[_ -]?key|client[_ -]?secret|authorization|bearer))\b\s*(?::|=)?\s+([^\s,;]+)"
)
# Assignment scanner.  Quoted values support escaped characters; an
# unterminated quote consumes the remainder so malformed input cannot leak.
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?ix)(?<!\w)(?P<label_quote>[\"']?)(?P<label>credential|secret|token|password|"
    r"api[_ -]?key|access[_ -]?(?:key|token)|private[_ -]?key|client[_ -]?secret|"
    r"authorization|bearer)\b(?P=label_quote)(?P<separator>\s*[:=]\s*)"
    r"(?:(?P<quote>[\"'])(?P<quoted>(?:\\.|(?!\\3).)*?)(?P=quote)(?P<quoted_tail>[^\n]*)|"
    r"(?P<unterminated>[\"'])(?P<tail>.*)|"
    r"(?P<bare>(?:bearer\s+)?[^\s,;}]+))"
)
# Bare prose is normally alphabetic and short.  Credentials have a marker
# character (digit/punctuation) or are long enough to be credential-like.
_CREDENTIAL_SHAPE = re.compile(r"(?i)(?=.{8,}$)(?:[a-z0-9._-]+)$|[a-z0-9]*[0-9_-][a-z0-9_-]*$")
_SENSITIVE_WHITESPACE = re.compile(
    r"(?i)(?<!\w)(?P<label>credential|secret|token|password|api[_ -]?key|"
    r"access[_ -]?(?:key|token)|private[_ -]?key|client[_ -]?secret|"
    r"authorization|bearer)\s+(?P<value>(?:bearer\s+)?[^\s,;}]+)"
)
_PATH_ASSIGNMENT = re.compile(r"(?i)(?<![a-z0-9_])(?:source|path)\s*[:=]\s*[^\s,;]+")
# YAML permits optional chomping and indentation indicators in either order.
_BLOCK_SCALAR_HEADER = re.compile(r"^[|>](?:[1-9][+-]?|[+-]?[1-9]?)$")
# Malformed marker tokens still own an indented continuation region.
_BLOCK_SCALAR_TOKEN = re.compile(r"^[|>][^\s]*$")
MAX_RETRY_ATTEMPTS = 100  # operational upper bound; prevents runaway retries

# V2 canonical identity.  These helpers are intentionally independent of the
# V1 dataclasses below: callers can hash a decoded plan without constructing a
# model (and without invoking a clock, filesystem, or serializer fallback).
V2_SCHEMA_VERSION = "pd-fleet-plan:v2"
V2_HASH_DOMAIN = b"pd-fleet-plan:v2\0"
_RUNTIME_KEYS = frozenset({
    "timestamp", "timestamps", "created_at", "updated_at", "started_at",
    "finished_at", "completed_at", "heartbeat_at", "expires_at",
    "lease_expiry", "runtime", "wall_time", "monotonic_time",
})
_V2_ALIASES = {
    "schemaVersion": "schema_version", "planHash": "plan_hash",
    "runId": "run_id", "taskId": "task_id", "agentId": "agent_id",
    "maxParallel": "max_parallel", "eventSequence": "event_sequence",
    "checkpointId": "checkpoint_id", "leaseId": "lease_id",
}
_V2_PLAN_FIELDS = frozenset({
    "schema_version", "plan_hash", "generation", "run_id", "owner", "status",
    "waves", "tasks", "dependencies", "gates", "agents", "capabilities",
    "inputs", "constraints", "context", "commands", "validation_commands",
    "max_parallel", "checkpoints", "leases", "attempts", "reports", "events",
    "event_sequence", "checkpoint_id", "lease_id", "audit", "metrics",
    "project", "name", "description", "path", "source", "cwd",
    "task_id", "agent_id", "role",
})
# Paths are redacted, rather than discarded: ``None`` is meaningful in the
# plan protocol and must remain distinguishable from an omitted field.
_EMBEDDED_PATH = re.compile(
    # Components intentionally accept Unicode; otherwise /é/... is redacted partially.
    r'''(?<![\w.])(?:~[\\/][^ \t\n\r\f\v"'<>;,]*|/[^ \t\n\r\f\v"'<>;,]+|[A-Za-z]:[\\/][^ \t\n\r\f\v"'<>;,]*|\\\\[^ \t\n\r\f\v"'<>;,]+)'''
)


def _v2_error(code: str) -> ContractValidationError:
    # Never include user supplied keys, values, or paths in this diagnostic.
    return ContractValidationError(f"v2 contract rejected: {code}")


def _redact_paths(text: str) -> str:
    return _EMBEDDED_PATH.sub("[PATH REDACTED]", text)


def _parse_block_scalar_header(header: str, key_indent: int) -> tuple[bool, int]:
    """Parse a YAML block marker and return validity plus its declared indent."""
    parsed = _BLOCK_SCALAR_HEADER.fullmatch(header)
    if parsed is None:
        return False, key_indent + 1
    suffix = header[1:]
    digits = next((char for char in suffix if char.isdigit()), None)
    return True, key_indent + int(digits) if digits is not None else key_indent + 1


def _block_scalar_owns_continuation(content: str, key_indent: int, declared_indent: int) -> bool:
    """Return whether a non-empty physical line belongs to a scalar.

    The declared indicator is advisory only: an underflowing marker such as
    ``|9`` must still consume every non-empty line indented beyond its key.
    Tabs are invalid YAML indentation, but are consumed fail-closed too.
    """
    if not content.strip():
        return True
    leading = content[:len(content) - len(content.lstrip(" \t"))]
    if "\t" in leading:
        return True
    indentation = len(leading)
    return indentation > key_indent


def _redact_block_scalar_line(continuation: str) -> str:
    """Redact one consumed scalar line while preserving indentation/newline."""
    newline = continuation[len(continuation.rstrip("\r\n")):]
    content = continuation.rstrip("\r\n")
    if not content.strip():
        return continuation
    indentation = content[:len(content) - len(content.lstrip(" \t"))]
    return f"{indentation}[REDACTED]{newline}"


def _block_scalar_end(lines: list[str], assignment_index: int, key_indent: int,
                      header: str) -> int:
    """Find the first physical line not owned by a block scalar."""
    _, declared_indent = _parse_block_scalar_header(header, key_indent)
    index = assignment_index + 1
    while index < len(lines):
        content = lines[index].rstrip("\r\n")
        if not _block_scalar_owns_continuation(content, key_indent, declared_indent):
            break
        index += 1
    return index


def _redact_block_scalar_lines(lines: list[str], start: int, end: int) -> list[str]:
    """Redact consumed scalar content while retaining line endings/shape."""
    return [_redact_block_scalar_line(line) for line in lines[start:end]]


def _redact_sensitive_text(text: str) -> str:
    """Replace sensitive assignments in a quote-aware, fail-closed pass.

    Once an assignment is recognized, its complete physical line is consumed;
    this includes YAML comments and collection syntax. Block scalar values are
    consumed through their indented continuation lines too.
    """
    def replace(match: re.Match[str]) -> str:
        label = match.group("label")
        label_quote = match.group("label_quote")
        separator = match.group("separator")
        label_text = f"{label_quote}{label}{label_quote}" if label_quote else label
        if match.group("unterminated") is not None or match.group("quote") is not None:
            return f"{label_text}{separator}[REDACTED]"
        bare = (match.group("bare") or "").removeprefix("Bearer ").strip()
        collection_or_comment = bare.startswith(("[", "{")) or any(
            mark in bare for mark in ("]", "}", "#")
        )
        if bare.startswith(("|", ">")):
            collection_or_comment = True
        if not _CREDENTIAL_SHAPE.fullmatch(bare):
            # Keep ordinary prose (``token: policy``) unchanged.
            if "=" not in separator and not collection_or_comment:
                return match.group(0)
        return f"{label_text}{separator}[REDACTED]"

    lines = text.splitlines(keepends=True)
    redacted_lines: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = _SENSITIVE_ASSIGNMENT.search(line)
        if match is None:
            redacted_lines.append(line)
            index += 1
            continue
        replacement = replace(match)
        if replacement != match.group(0):
            # A recognized assignment owns the remainder of this physical line,
            # including comments and any subsequent YAML collection text.
            newline = "" if not line.endswith(("\n", "\r")) else line[len(line.rstrip("\r\n")):]
            redacted_lines.append(line[:match.start()] + replacement + newline)
        else:
            redacted_lines.append(line)
        bare = (match.group("bare") or "").strip()
        if _BLOCK_SCALAR_TOKEN.fullmatch(bare) is not None:
            physical = line.rstrip("\r\n")
            key_indent = len(physical) - len(physical.lstrip(" "))
            end = _block_scalar_end(lines, index, key_indent, bare)
            redacted_lines.extend(_redact_block_scalar_lines(lines, index + 1, end))
            index = end
        else:
            index += 1
    text = "".join(redacted_lines)
    def redact_whitespace(match: re.Match[str]) -> str:
        value = match.group("value").removeprefix("Bearer ").strip()
        return match.group(0) if not _CREDENTIAL_SHAPE.fullmatch(value) else f"{match.group('label')} [REDACTED]"
    text = _SENSITIVE_WHITESPACE.sub(redact_whitespace, text)
    return _SECRET_VALUE.sub("[REDACTED]", text)


def _normalized_aliases(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize aliases and reject ambiguous duplicate spellings."""
    result: dict[str, Any] = {}
    for raw_key, item in value.items():
        if type(raw_key) is not str or not raw_key:
            raise _v2_error("invalid object key")
        key = _V2_ALIASES.get(raw_key, raw_key)
        if key in result:
            try:
                old = json.dumps(result[key], sort_keys=True, ensure_ascii=False,
                                  separators=(",", ":"), allow_nan=False)
                new = json.dumps(item, sort_keys=True, ensure_ascii=False,
                                  separators=(",", ":"), allow_nan=False)
            except (TypeError, ValueError, UnicodeError) as exc:
                raise _v2_error("invalid alias value") from exc
            if old != new:
                raise _v2_error("conflicting aliases")
        else:
            result[key] = item
    return result


def _canonical_value(value: Any, *, root: bool = False, seen: set[int] | None = None) -> Any:
    if seen is None:
        seen = set()
    if value is None or type(value) in (str, bool, int):
        if isinstance(value, str):
            # Detect URLs before path replacement; otherwise ``https://...`` can
            # become a malformed ``https:[PATH REDACTED]`` fragment.
            if _EXTERNAL_URL.search(value):
                return None
            value = _redact_paths(value)
        if isinstance(value, str):
            value = _redact_sensitive_text(value)
        if isinstance(value, str) and _SECRET_VALUE.search(value):
            return None
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise _v2_error("non-finite number")
        return value
    marker = id(value)
    if marker in seen:
        raise _v2_error("cyclic value")
    seen.add(marker)
    try:
        if isinstance(value, Mapping):
            result: dict[str, Any] = {}
            normalized_mapping = _normalized_aliases(value)
            has_schema = "schema_version" in normalized_mapping
            for key, item in normalized_mapping.items():
                if key in _RUNTIME_KEYS or _is_sensitive_label(key):
                    continue
                if root and has_schema and key not in _V2_PLAN_FIELDS:
                    raise _v2_error("unknown field")
                normalized = _canonical_value(item, seen=seen)
                # None is explicit and meaningful; runtime and sensitive keys
                # are the intentional exceptions handled above.
                result[key] = normalized
            # Collections whose meaning is set-like are ordered by their
            # canonical bytes; task/event order remains meaningful.
            for key in ("capabilities", "dependencies"):
                if isinstance(result.get(key), list):
                    result[key] = sorted(result[key], key=lambda x: json.dumps(
                        x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                    ))
            return result
        if isinstance(value, (list, tuple)):
            result_list: list[Any] = []
            for item in value:
                normalized = _canonical_value(item, seen=seen)
                # None is an explicit list member, not an omitted runtime key.
                result_list.append(normalized)
            return result_list
        raise _v2_error("non-JSON value")
    finally:
        seen.discard(marker)


def canonicalize(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the deterministic, secret/path/runtime-free V2 plan form."""
    if not isinstance(value, Mapping):
        raise _v2_error("plan must be an object")
    normalized = _normalized_aliases(value)
    if "schema_version" not in normalized or normalized["schema_version"] != V2_SCHEMA_VERSION:
        raise _v2_error("unsupported schema version")
    result = _canonical_value(normalized, root=True)
    if not isinstance(result, dict):  # pragma: no cover - defensive
        raise _v2_error("plan must be an object")
    return result


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Serialize a V2 value using the normative compact UTF-8 JSON encoding."""
    try:
        return json.dumps(canonicalize(value), sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise _v2_error("invalid JSON") from exc


def plan_hash(value: Mapping[str, Any]) -> str:
    """Hash canonical plan bytes with the versioned V2 domain separator."""
    return hashlib.sha256(V2_HASH_DOMAIN + canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class ReconciliationInput:
    """Immutable expected/current tokens checked before claim or dispatch."""
    expected_plan_hash: str
    actual_plan_hash: str
    expected_generation: int
    actual_generation: int
    expected_run_id: str
    actual_run_id: str
    expected_checkpoint: int = 0
    actual_checkpoint: int = 0
    expected_lease: str | None = None
    actual_lease: str | None = None
    expected_event_sequence: int = 0
    actual_event_sequence: int = 0


@dataclass(frozen=True)
class ReconciliationError:
    code: str
    message: str


@dataclass(frozen=True)
class ReconciliationResult:
    allowed: bool
    errors: tuple[ReconciliationError, ...] = ()

    @property
    def blocked(self) -> bool:
        return not self.allowed


_TOKEN_HASH = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_LEASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


def _token_valid(name: str, token: Any) -> bool:
    if name.endswith("_plan_hash"):
        return type(token) is str and bool(_TOKEN_HASH.fullmatch(token))
    if name.endswith("_generation") or name.endswith("_checkpoint") or name.endswith("_event_sequence"):
        return type(token) is int and token >= 0
    if name.endswith("_run_id"):
        return type(token) is str and bool(token)
    if name.endswith("_lease"):
        return type(token) is str and bool(_TOKEN_LEASE.fullmatch(token))
    return False


def reconcile(value: ReconciliationInput) -> ReconciliationResult:
    """Compare tokens; malformed tokens block before any equality comparison."""
    if not isinstance(value, ReconciliationInput):
        raise _v2_error("invalid reconciliation input")
    pairs = (
        ("plan_hash", "plan_hash_drift"), ("generation", "generation_drift"),
        ("run_id", "run_drift"), ("checkpoint", "checkpoint_drift"),
        ("lease", "lease_stale"), ("event_sequence", "event_sequence_drift"),
    )
    errors: list[ReconciliationError] = []
    for label, drift_code in pairs:
        expected_name, actual_name = f"expected_{label}", f"actual_{label}"
        expected, actual = getattr(value, expected_name), getattr(value, actual_name)
        if label == "lease" and expected is None and actual is None:
            continue
        if not (_token_valid(expected_name, expected) and _token_valid(actual_name, actual)):
            errors.append(ReconciliationError(f"invalid_{label}", "reconciliation blocked"))
        elif expected != actual:
            errors.append(ReconciliationError(drift_code, "reconciliation blocked"))
    return ReconciliationResult(not errors, tuple(errors))


def _required(data: Mapping[str, Any], name: str) -> Any:
    value = data.get(name)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ContractValidationError(f"campo obrigatório ausente ou vazio: {name}")
    return value


def _normalize_sensitive_key(label: Any) -> str:
    # Split lowerCamelCase and acronym boundaries before punctuation normalization.
    text = str(label).strip()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _is_sensitive_label(label: Any) -> bool:
    normalized = _normalize_sensitive_key(label)
    compact = normalized.replace("_", "")
    return any(
        normalized == key or normalized.startswith(f"{key}_") or normalized.endswith(f"_{key}")
        for key in _SENSITIVE_KEYS
    ) or any(part in _SENSITIVE_KEYS for part in normalized.split("_")) or any(
        compact == key.replace("_", "") for key in _SENSITIVE_KEYS
    )


def _text(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ContractValidationError(f"{name} deve ser uma string não vazia")
    return value.strip()


def _texts(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ContractValidationError(f"{name} deve ser uma lista")
    result = [_text(item, name) for item in value]
    return result


def _json_safe(value: Any, path: str = "value", seen: set[int] | None = None) -> Any:
    """Return a defensive JSON-compatible copy, rejecting unsafe values."""
    if seen is None:
        seen = set()
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ContractValidationError("payload contém número não finito")
        return value
    marker = id(value)
    if marker in seen:
        raise ContractValidationError("payload contém estrutura cíclica")
    seen.add(marker)
    try:
        if isinstance(value, Mapping):
            result = {}
            for key, item in value.items():
                if type(key) is not str or not key:
                    raise ContractValidationError("payload contém chave JSON inválida")
                result[key] = _json_safe(item, f"{path}.{key}", seen)
            return result
        if isinstance(value, (list, tuple)):
            return [_json_safe(item, f"{path}[{i}]", seen) for i, item in enumerate(value)]
        raise ContractValidationError("payload não é JSON-safe")
    finally:
        seen.discard(marker)


def _check_secrets(value: Any, path: str = "value") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            label = str(key)
            if _is_sensitive_label(label):
                raise ContractValidationError("credencial proibida no payload")
            _check_secrets(item, f"{path}.{label}")
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _check_secrets(item, f"{path}[{i}]")
    elif isinstance(value, str):
        if _SECRET_VALUE.search(value) or _EXTERNAL_URL.search(value):
            raise ContractValidationError("segredo ou endpoint externo proibido no payload")
        if _redact_sensitive_text(value) != value:
            raise ContractValidationError("credencial proibida no payload")
        # The consolidated scanner above is the single source of truth for
        # textual assignments; do not use a broad label/value fallback here.


def _paths(value: Any, name: str) -> list[str]:
    values = _texts(value, name)
    for path in values:
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        if "\x00" in path or normalized.startswith("/") or normalized.startswith("~") or any(part in (".", "..") for part in parts) or any(not part for part in parts[:-1]):
            raise ContractValidationError(f"{name} contém path inseguro")
        # Reject every URI scheme and Windows drive-relative path (C:foo),
        # including malformed one-slash/backslash variants such as https:/x.
        if re.match(r"(?i)^[a-z][a-z0-9+.-]*:", normalized):
            raise ContractValidationError(f"{name} contém path externo")
        if _is_sensitive_label(normalized):
            raise ContractValidationError(f"{name} contém path de credencial")
    return [p.replace("\\", "/").rstrip("/") or "." for p in values]


def _conflicts(allowed: list[str], forbidden: list[str]) -> bool:
    """Detect path overlap, including globs occurring in the middle of a path."""
    def overlap(left: str, right: str) -> bool:
        left = left.replace("\\", "/").rstrip("/")
        right = right.replace("\\", "/").rstrip("/")
        if left in ("", ".", "*", "**") or right in ("", ".", "*", "**"):
            return True
        if fnmatch.fnmatchcase(left, right) or fnmatch.fnmatchcase(right, left):
            return True
        left_base = re.split(r"[*?\[]", left, maxsplit=1)[0].rstrip("/")
        right_base = re.split(r"[*?\[]", right, maxsplit=1)[0].rstrip("/")
        if left_base == right_base:
            return True
        return left_base.startswith(right_base + "/") or right_base.startswith(left_base + "/")
    return any(overlap(a, f) for a in allowed for f in forbidden)


@dataclass
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.0
    retryable_errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= MAX_RETRY_ATTEMPTS:
            raise ContractValidationError(f"max_attempts deve ser inteiro entre 1 e {MAX_RETRY_ATTEMPTS}")
        if type(self.backoff_seconds) not in (int, float) or not math.isfinite(float(self.backoff_seconds)) or self.backoff_seconds < 0:
            raise ContractValidationError("backoff_seconds deve ser finito e >= 0")
        self.backoff_seconds = float(self.backoff_seconds)
        self.retryable_errors = _texts(self.retryable_errors, "retryable_errors")

    @classmethod
    def from_dict(cls, value: Any) -> "RetryPolicy":
        if value is None:
            return cls()
        if isinstance(value, cls):
            value = value.to_dict()
        if not isinstance(value, Mapping):
            raise ContractValidationError("retry_policy deve ser um objeto")
        attempts = value.get("max_attempts", 1)
        backoff = value.get("backoff_seconds", 0.0)
        if type(attempts) is not int or not 1 <= attempts <= MAX_RETRY_ATTEMPTS:
            raise ContractValidationError(f"max_attempts deve ser inteiro entre 1 e {MAX_RETRY_ATTEMPTS}")
        if type(backoff) not in (int, float) or not math.isfinite(float(backoff)) or backoff < 0:
            raise ContractValidationError("backoff_seconds deve ser finito e >= 0")
        result = cls(attempts, float(backoff), _texts(value.get("retryable_errors", value.get("retry_on")), "retryable_errors"))
        _check_secrets(result.to_dict())
        return result

    def to_dict(self) -> dict[str, Any]:
        return {"max_attempts": self.max_attempts, "backoff_seconds": self.backoff_seconds, "retryable_errors": list(self.retryable_errors)}


@dataclass
class AgentContract:
    task_id: str
    agent_id: str
    role: str
    capabilities: list[str] = field(default_factory=list)
    context: Any = field(default_factory=dict)
    constraints: Any = field(default_factory=dict)
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    expected_outputs: Any = field(default_factory=list)
    validation_commands: list[str] = field(default_factory=list)
    timeout_seconds: float = 300.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    schema_version: str = SCHEMA_VERSION
    REQUIRED: ClassVar[tuple[str, ...]] = ("task_id", "agent_id", "role")

    def __post_init__(self) -> None:
        self.task_id, self.agent_id, self.role = _text(self.task_id, "task_id"), _text(self.agent_id, "agent_id"), _text(self.role, "role")
        self.capabilities = _texts(self.capabilities, "capabilities")
        self.allowed_paths, self.forbidden_paths = _paths(self.allowed_paths, "allowed_paths"), _paths(self.forbidden_paths, "forbidden_paths")
        if _conflicts(self.allowed_paths, self.forbidden_paths):
            raise ContractValidationError("allowed_paths e forbidden_paths entram em conflito")
        if type(self.timeout_seconds) not in (int, float) or not math.isfinite(float(self.timeout_seconds)) or self.timeout_seconds <= 0:
            raise ContractValidationError("timeout_seconds deve ser finito e > 0")
        self.timeout_seconds = float(self.timeout_seconds)
        if not isinstance(self.retry_policy, RetryPolicy):
            self.retry_policy = RetryPolicy.from_dict(self.retry_policy)
        else:
            self.retry_policy = RetryPolicy.from_dict(self.retry_policy.to_dict())
        payload = {"context": self.context, "constraints": self.constraints, "expected_outputs": self.expected_outputs, "validation_commands": self.validation_commands}
        _json_safe(payload)
        _check_secrets(payload)
        self.context, self.constraints, self.expected_outputs = _json_safe(self.context), _json_safe(self.constraints), _json_safe(self.expected_outputs)
        self.validation_commands = _texts(self.validation_commands, "validation_commands")
        _check_secrets(self.to_dict())
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("schema_version não suportada")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | "AgentContract") -> "AgentContract":
        if isinstance(value, cls):
            return cls.from_dict(value.to_dict())
        if not isinstance(value, Mapping):
            raise ContractValidationError("contract deve ser um objeto")
        for key in cls.REQUIRED:
            _required(value, key)
        return cls(**{key: value[key] for key in cls.REQUIRED}, capabilities=value.get("capabilities", []), context=value.get("context", {}), constraints=value.get("constraints", {}), allowed_paths=value.get("allowed_paths", []), forbidden_paths=value.get("forbidden_paths", []), expected_outputs=value.get("expected_outputs", []), validation_commands=value.get("validation_commands", []), timeout_seconds=value.get("timeout_seconds", 300), retry_policy=RetryPolicy.from_dict(value.get("retry_policy")), schema_version=value.get("schema_version", SCHEMA_VERSION))

    def to_dict(self) -> dict[str, Any]:
        return _json_safe({"schema_version": self.schema_version, "task_id": self.task_id, "agent_id": self.agent_id, "role": self.role, "capabilities": list(self.capabilities), "context": self.context, "constraints": self.constraints, "allowed_paths": list(self.allowed_paths), "forbidden_paths": list(self.forbidden_paths), "expected_outputs": self.expected_outputs, "validation_commands": list(self.validation_commands), "timeout_seconds": self.timeout_seconds, "retry_policy": self.retry_policy.to_dict()})

    def to_json(self) -> str:
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("contract não pode ser serializado como JSON") from exc

    @classmethod
    def from_json(cls, value: str) -> "AgentContract":
        try:
            return cls.from_dict(json.loads(value))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ContractValidationError("JSON inválido") from exc


def _sanitize_error(value: Any) -> str:
    text = value if type(value) is str else "erro do agente"
    lines = []
    for line in text.splitlines():
        if re.search(r"(?i)traceback \(most recent call last\)", line):
            break
        if re.search(r"^\s*file\s+[\"']|^\s*(?:at\s+)?(?:/|[A-Za-z]:[\\/])", line, re.I):
            continue
        line = _PATH_ASSIGNMENT.sub("", line)
        if line.strip():
            lines.append(line)
            break
    text = lines[0] if lines else ""
    text = _EXTERNAL_URL.sub("[URL REDACTED]", text)
    text = _redact_paths(text)
    text = _SECRET_VALUE.sub("[REDACTED]", text)
    text = _redact_sensitive_text(text)
    text = _ASSIGNMENT.sub(
        lambda match: f"{match.group(1).strip()}=[REDACTED]" if _is_sensitive_label(match.group(1)) else match.group(0),
        text,
    )
    return re.sub(r"\s+", " ", text).strip()[:2000] or "erro do agente"


def _meaningful(value: Any) -> bool:
    """Whether a value contains at least one meaningful scalar leaf."""
    def visit(item: Any, seen: set[int]) -> bool:
        if item is None or item is False or (type(item) in (int, float) and item == 0):
            return False
        if isinstance(item, str):
            return bool(item.strip())
        if isinstance(item, Mapping):
            marker = id(item)
            if marker in seen:
                return False
            seen.add(marker)
            try:
                return any(visit(child, seen) for child in item.values())
            finally:
                seen.discard(marker)
        if isinstance(item, (list, tuple, set, frozenset)):
            marker = id(item)
            if marker in seen:
                return False
            seen.add(marker)
            try:
                return any(visit(child, seen) for child in item)
            finally:
                seen.discard(marker)
        return True

    return visit(value, set())


@dataclass
class AgentReport:
    task_id: str
    agent_id: str
    status: str
    outputs: Any = field(default_factory=dict)
    evidence: Any = field(default_factory=list)
    tests: Any = field(default_factory=list)
    blockers: Any = field(default_factory=list)
    assumptions: Any = field(default_factory=list)
    decisions: Any = field(default_factory=list)
    timestamps: Any = field(default_factory=dict)
    error: str | None = None
    schema_version: str = SCHEMA_VERSION
    STATUSES: ClassVar[frozenset[str]] = frozenset({"pending", "running", "completed", "failed", "blocked", "skipped"})

    def __post_init__(self) -> None:
        self.task_id, self.agent_id, self.status = _text(self.task_id, "task_id"), _text(self.agent_id, "agent_id"), _text(self.status, "status").lower()
        if self.status not in self.STATUSES:
            raise ContractValidationError("status inválido")
        if self.status == "completed" and not _meaningful(self.evidence):
            raise ContractValidationError("completed exige evidence meaningful")
        payload = {"outputs": self.outputs, "evidence": self.evidence, "tests": self.tests, "blockers": self.blockers, "assumptions": self.assumptions, "decisions": self.decisions, "timestamps": self.timestamps}
        _json_safe(payload)
        _check_secrets(payload)
        self.outputs, self.evidence, self.tests = _json_safe(self.outputs), _json_safe(self.evidence), _json_safe(self.tests)
        self.blockers, self.assumptions, self.decisions, self.timestamps = _json_safe(self.blockers), _json_safe(self.assumptions), _json_safe(self.decisions), _json_safe(self.timestamps)
        self.error = _sanitize_error(self.error) if self.error is not None else None
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("schema_version não suportada")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | "AgentReport") -> "AgentReport":
        if isinstance(value, cls):
            return cls.from_dict(value.to_dict())
        if not isinstance(value, Mapping):
            raise ContractValidationError("report deve ser um objeto")
        for key in ("task_id", "agent_id", "status"):
            _required(value, key)
        fields = {"task_id", "agent_id", "status", "outputs", "evidence", "tests", "blockers", "assumptions", "decisions", "timestamps", "error", "schema_version"}
        return cls(**{key: value[key] for key in fields if key in value})

    def to_dict(self) -> dict[str, Any]:
        return _json_safe({"schema_version": self.schema_version, "task_id": self.task_id, "agent_id": self.agent_id, "status": self.status, "outputs": self.outputs, "evidence": self.evidence, "tests": self.tests, "blockers": self.blockers, "assumptions": self.assumptions, "decisions": self.decisions, "timestamps": self.timestamps, "error": self.error})

    def to_json(self) -> str:
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("report não pode ser serializado como JSON") from exc

    @classmethod
    def from_json(cls, value: str) -> "AgentReport":
        try:
            return cls.from_dict(json.loads(value))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ContractValidationError("JSON inválido") from exc


AGENT_REPORT_V2_SCHEMA_VERSION = "pd-fleet-report:v2"
MAX_REPORT_RETRY_ATTEMPTS = MAX_RETRY_ATTEMPTS
_REPORT_V2_FIELDS = frozenset({
    "schema_version", "task_id", "attempt", "agent_id", "agent", "role", "capabilities",
    "status", "outputs", "evidence", "tests", "validation", "decision", "started_at",
    "completed_at", "timestamps", "reason", "error", "blocker", "diagnostics", "retry", "metadata", "extensions",
})
_REPORT_V2_RETRY_FIELDS = frozenset({"recommended", "max_attempts", "backoff_seconds", "reason"})
_REPORT_V2_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$")


def redact_report_value(value: Any) -> Any:
    """Detached/canonical JSON-safe report value with one central redaction policy."""
    def visit(item: Any, seen: set[int]) -> Any:
        if item is None or type(item) in (str, bool, int):
            if type(item) is str:
                return _redact_sensitive_text(_redact_paths(_EXTERNAL_URL.sub("[URL REDACTED]", item)))
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise _v2_error("non-finite number")
            return item
        marker = id(item)
        if marker in seen:
            raise _v2_error("cyclic value")
        seen.add(marker)
        try:
            if isinstance(item, Mapping):
                result = {}
                for key, child in item.items():
                    if type(key) is not str or not key or _is_sensitive_label(key):
                        raise _v2_error("invalid or sensitive nested field")
                    result[key] = visit(child, seen)
                return {key: result[key] for key in sorted(result)}
            if isinstance(item, (list, tuple)):
                return [visit(child, seen) for child in item]
            raise _v2_error("non-JSON value")
        finally:
            seen.discard(marker)
    return visit(value, set())


def _report_meaningful(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value) and any(_report_meaningful(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return bool(value) and any(_report_meaningful(v) for v in value)
    return value is not None and value is not False


def _report_timestamp(value: Any, name: str) -> str:
    if type(value) is not str or _REPORT_V2_TIMESTAMP_RE.fullmatch(value.strip()) is None:
        raise _v2_error(f"invalid {name}")
    return value.strip()


def _report_instant(value: Any, name: str) -> datetime:
    text = _report_timestamp(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    except (TypeError, ValueError, OverflowError) as exc:
        raise _v2_error(f"invalid {name}") from exc


def _validate_report_retry(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping) or set(value) - _REPORT_V2_RETRY_FIELDS:
        raise _v2_error("invalid retry recommendation")
    attempts = value.get("max_attempts", 1)
    if type(attempts) is not int or not 1 <= attempts <= MAX_REPORT_RETRY_ATTEMPTS:
        raise _v2_error("retry recommendation out of bounds")
    if "recommended" in value and type(value["recommended"]) is not bool:
        raise _v2_error("invalid retry recommendation")
    backoff = value.get("backoff_seconds", 0.0)
    if type(backoff) is bool or type(backoff) not in (int, float) or not math.isfinite(float(backoff)) or backoff < 0:
        raise _v2_error("invalid retry backoff")
    if "reason" in value and (type(value["reason"]) is not str or not value["reason"].strip()):
        raise _v2_error("invalid retry reason")


@dataclass(frozen=True)
class AgentReportV2:
    """Immutable validated view of a complete terminal V2 report."""
    schema_version: str
    task_id: str
    attempt: int
    agent_id: str
    role: str
    capabilities: tuple[str, ...]
    status: str
    outputs: Any
    evidence: Any
    tests: Any
    validation: Any
    decision: Any
    started_at: str
    completed_at: str
    agent: str | None = None
    reason: Any = None
    error: Any = None
    blocker: Any = None
    diagnostics: Any = None
    retry: Any = None
    metadata: Any = None
    extensions: Any = None

    _DETACHED_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "outputs", "evidence", "tests", "validation", "decision", "reason", "error",
        "blocker", "diagnostics", "retry", "metadata", "extensions", "capabilities",
    })

    def __getattribute__(self, name: str) -> Any:
        value = object.__getattribute__(self, name)
        if name in type(self)._DETACHED_FIELDS:
            return deepcopy(value)
        return value

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_REPORT_V2_SCHEMA_VERSION:
            raise _v2_error("unsupported schema version")
        if type(self.task_id) is not str or not self.task_id.strip() or type(self.agent_id) is not str or not self.agent_id.strip() or type(self.role) is not str or not self.role.strip():
            raise _v2_error("invalid identity field")
        if type(self.agent) is not type(None) and (type(self.agent) is not str or not self.agent.strip() or self.agent.strip() != self.agent_id.strip()):
            raise _v2_error("conflicting identity aliases")
        if type(self.attempt) is not int or self.attempt < 1:
            raise _v2_error("invalid attempt")
        if type(self.status) is not str or self.status not in {"completed", "failed", "blocked"}:
            raise _v2_error("invalid terminal status")
        if not isinstance(self.capabilities, (tuple, list)) or any(type(x) is not str or not x.strip() for x in self.capabilities):
            raise _v2_error("invalid capabilities")
        started_instant = _report_instant(self.started_at, "started_at")
        completed_instant = _report_instant(self.completed_at, "completed_at")
        if completed_instant < started_instant:
            raise _v2_error("completed_at before started_at")
        if self.status == "completed":
            if not all(_report_meaningful(getattr(self, key)) for key in ("outputs", "evidence", "tests", "validation", "decision")):
                raise _v2_error("completed missing required field")
        else:
            if not any(_report_meaningful(getattr(self, key)) for key in ("reason", "error", "blocker")) or not _report_meaningful(self.evidence):
                raise _v2_error("terminal failure missing reason or diagnosis evidence")
        _validate_report_retry(self.retry)
        payload_fields = ("outputs", "evidence", "tests", "validation", "decision", "reason", "error", "blocker", "diagnostics", "retry", "metadata", "extensions")
        payload = {key: getattr(self, key) for key in payload_fields if getattr(self, key) is not None}
        _json_safe(payload)
        _check_secrets(payload)
        for key in payload_fields:
            if getattr(self, key) is not None:
                object.__setattr__(self, key, redact_report_value(getattr(self, key)))
        if self.error is not None:
            object.__setattr__(self, "error", _sanitize_error(self.error))
        if isinstance(self.diagnostics, str):
            object.__setattr__(self, "diagnostics", _sanitize_error(self.diagnostics))
        for key in self._DETACHED_FIELDS:
            object.__setattr__(self, key, deepcopy(getattr(self, key)))
        object.__setattr__(self, "capabilities", tuple(self.capabilities))

    def to_dict(self) -> dict[str, Any]:
        result = {"schema_version": self.schema_version, "task_id": self.task_id, "attempt": self.attempt,
                  "agent_id": self.agent_id, "role": self.role, "capabilities": list(self.capabilities),
                  "status": self.status, "outputs": self.outputs, "evidence": self.evidence, "tests": self.tests,
                  "validation": self.validation, "decision": self.decision, "started_at": self.started_at,
                  "completed_at": self.completed_at}
        for key in ("reason", "error", "blocker", "diagnostics", "retry", "metadata", "extensions"):
            if getattr(self, key) is not None:
                result[key] = getattr(self, key)
        return redact_report_value(result)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, reject_unknown_fields: bool = True) -> "AgentReportV2":
        return parse_agent_report_v2(value, reject_unknown_fields=reject_unknown_fields)

    @classmethod
    def from_json(cls, value: str, *, reject_unknown_fields: bool = True) -> "AgentReportV2":
        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise _v2_error("invalid JSON") from exc
        return cls.from_dict(decoded, reject_unknown_fields=reject_unknown_fields)


def parse_agent_report_v2(value: Mapping[str, Any] | AgentReportV2, *, reject_unknown_fields: bool = True) -> AgentReportV2:
    """Parse V2 reports; unknown fields reject by default or become extensions.

    With ``reject_unknown_fields=False``, non-sensitive unknown top-level fields
    are retained under ``extensions``; sensitive structural names remain errors.
    """
    if isinstance(value, AgentReportV2):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        raise _v2_error("report must be an object")
    data = dict(value)
    unknown = set(data) - _REPORT_V2_FIELDS
    if unknown and reject_unknown_fields:
        raise _v2_error("unknown field")
    if unknown:
        if any(type(key) is not str or not key or _is_sensitive_label(key) for key in unknown):
            raise _v2_error("unknown field")
        existing_extensions = data.get("extensions")
        if existing_extensions is None:
            existing_extensions = {}
        if not isinstance(existing_extensions, Mapping):
            raise _v2_error("invalid extensions")
        data["extensions"] = {**existing_extensions, **{key: data[key] for key in unknown}}
    if data.get("schema_version") != AGENT_REPORT_V2_SCHEMA_VERSION:
        raise _v2_error("unsupported schema version")
    status = data.get("status")
    if type(status) is not str or status not in {"completed", "failed", "blocked"}:
        raise _v2_error("invalid terminal status")
    required = ("task_id", "attempt", "role", "capabilities")
    if any(key not in data or data[key] is None for key in required):
        raise _v2_error("missing required field")
    task_id, role = data["task_id"], data["role"]
    agent_id = data.get("agent_id", data.get("agent"))
    if "agent_id" in data and "agent" in data and (type(data["agent_id"]) is not str or type(data["agent"]) is not str or data["agent_id"].strip() != data["agent"].strip()):
        raise _v2_error("conflicting identity aliases")
    if any(type(x) is not str or not x.strip() for x in (task_id, agent_id, role)):
        raise _v2_error("invalid identity field")
    if type(data["attempt"]) is not int or data["attempt"] < 1:
        raise _v2_error("invalid attempt")
    capabilities = data["capabilities"]
    if not isinstance(capabilities, (list, tuple)) or any(type(x) is not str or not x.strip() for x in capabilities):
        raise _v2_error("invalid capabilities")
    started, completed = data.get("started_at"), data.get("completed_at")
    timestamps = data.get("timestamps")
    if isinstance(timestamps, Mapping):
        if set(timestamps) - {"started_at", "completed_at"}:
            raise _v2_error("unknown timestamp field")
        started = started if started is not None else timestamps.get("started_at")
        completed = completed if completed is not None else timestamps.get("completed_at")
    elif timestamps is not None:
        raise _v2_error("invalid timestamps")
    if started is None or completed is None:
        raise _v2_error("missing execution timestamps")
    started, completed = _report_timestamp(started, "started_at"), _report_timestamp(completed, "completed_at")
    def parse_instant(text: str, name: str) -> str:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except (TypeError, ValueError, OverflowError) as exc:
            raise _v2_error(f"invalid {name}") from exc
    if isinstance(timestamps, Mapping):
        for key in ("started_at", "completed_at"):
            top, nested = data.get(key), timestamps.get(key)
            if top is not None and nested is not None and parse_instant(_report_timestamp(top, key), key) != parse_instant(_report_timestamp(nested, key), key):
                raise _v2_error("conflicting timestamps")
    started, completed = parse_instant(started, "started_at"), parse_instant(completed, "completed_at")
    payload = {key: redact_report_value(data[key]) for key in data if key in _REPORT_V2_FIELDS and key != "timestamps"}
    if payload.get("error") is not None:
        payload["error"] = _sanitize_error(payload["error"])
    if isinstance(payload.get("diagnostics"), str):
        payload["diagnostics"] = _sanitize_error(payload["diagnostics"])
    if status == "completed":
        for key in ("outputs", "evidence", "tests", "validation", "decision"):
            if key not in payload or not _report_meaningful(payload[key]):
                raise _v2_error(f"completed missing {key}")
    else:
        has_reason = any(_report_meaningful(payload.get(key)) for key in ("reason", "error", "blocker"))
        if not has_reason or not _report_meaningful(payload.get("evidence")):
            raise _v2_error("terminal failure missing reason or diagnosis evidence")
    retry = payload.get("retry")
    _validate_report_retry(retry)
    return AgentReportV2(AGENT_REPORT_V2_SCHEMA_VERSION, task_id.strip(), data["attempt"], agent_id.strip(), role.strip(),
                         tuple(sorted(capabilities)), status, payload.get("outputs"), payload.get("evidence"),
                         payload.get("tests"), payload.get("validation"), payload.get("decision"), started, completed,
                         data.get("agent"), payload.get("reason"), payload.get("error"), payload.get("blocker"),
                         payload.get("diagnostics"), payload.get("retry"), payload.get("metadata"),
                         payload.get("extensions"))


__all__ = [
    "SCHEMA_VERSION", "MAX_RETRY_ATTEMPTS", "ContractError", "ContractValidationError", "RetryPolicy",
    "AgentContract", "AgentReport", "AGENT_REPORT_V2_SCHEMA_VERSION", "MAX_REPORT_RETRY_ATTEMPTS",
    "AgentReportV2", "parse_agent_report_v2", "redact_report_value", "V2_SCHEMA_VERSION", "V2_HASH_DOMAIN",
    "canonicalize", "canonical_json_bytes", "plan_hash", "ReconciliationInput", "ReconciliationError",
    "ReconciliationResult", "reconcile",
]
