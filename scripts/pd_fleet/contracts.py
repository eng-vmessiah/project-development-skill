"""Versioned, JSON-safe contracts exchanged with fleet agents.

The models in this module are deliberately passive: they never execute commands,
access the network, or resolve paths.  An empty ``allowed_paths`` is intentional
and means that an agent has no write scope (default deny).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
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
    "credential", "secret", "token", "password", "api_key", "access_key",
    "private_key", "client_secret", "authorization", "bearer",
})
_SECRET_VALUE = re.compile(r"(?:bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|AKIA[A-Z0-9]{12,})", re.I)
_EXTERNAL_URL = re.compile(r"(?i)(?:https?|ftp|wss?)://[^\s\"'<>]+")
_ASSIGNMENT = re.compile(r"(?i)([A-Za-z][A-Za-z0-9_. -]{1,80})\s*[:=]\s*(\S+)")
_SENSITIVE_VALUE = re.compile(
    r"(?i)(?<![a-z0-9_])((?:credential|secret|token|password|api[_ -]?key|access[_ -]?(?:key|token)|"
    r"private[_ -]?key|client[_ -]?secret|authorization|bearer))\b\s*(?::|=)?\s+([^\s,;]+)"
)
_PATH_ASSIGNMENT = re.compile(r"(?i)(?<![a-z0-9_])(?:source|path)\s*[:=]\s*[^\s,;]+")
MAX_RETRY_ATTEMPTS = 100  # operational upper bound; prevents runaway retries


def _required(data: Mapping[str, Any], name: str) -> Any:
    value = data.get(name)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ContractValidationError(f"campo obrigatório ausente ou vazio: {name}")
    return value


def _normalize_sensitive_key(label: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(label).strip().lower()).strip("_")


def _is_sensitive_label(label: Any) -> bool:
    normalized = _normalize_sensitive_key(label)
    return any(
        normalized == key or normalized.startswith(f"{key}_") or normalized.endswith(f"_{key}")
        for key in _SENSITIVE_KEYS
    ) or any(part in _SENSITIVE_KEYS for part in normalized.split("_"))


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
            raise ContractValidationError(f"{path} contém número não finito")
        return value
    marker = id(value)
    if marker in seen:
        raise ContractValidationError(f"{path} contém estrutura cíclica")
    seen.add(marker)
    try:
        if isinstance(value, Mapping):
            result = {}
            for key, item in value.items():
                if type(key) is not str or not key:
                    raise ContractValidationError(f"{path} contém chave JSON inválida")
                result[key] = _json_safe(item, f"{path}.{key}", seen)
            return result
        if isinstance(value, (list, tuple)):
            return [_json_safe(item, f"{path}[{i}]", seen) for i, item in enumerate(value)]
        raise ContractValidationError(f"{path} não é JSON-safe")
    finally:
        seen.discard(marker)


def _check_secrets(value: Any, path: str = "value") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            label = str(key)
            if _is_sensitive_label(label):
                raise ContractValidationError(f"credencial proibida em {path}.{label}")
            _check_secrets(item, f"{path}.{label}")
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _check_secrets(item, f"{path}[{i}]")
    elif isinstance(value, str):
        if _SECRET_VALUE.search(value) or _EXTERNAL_URL.search(value):
            raise ContractValidationError(f"segredo ou endpoint externo proibido em {path}")
        for match in _ASSIGNMENT.finditer(value):
            if _is_sensitive_label(match.group(1)):
                raise ContractValidationError(f"credencial proibida em {path}")


def _paths(value: Any, name: str) -> list[str]:
    values = _texts(value, name)
    for path in values:
        normalized = path.replace("\\", "/")
        if normalized.startswith("/") or normalized.startswith("~") or ".." in normalized.split("/"):
            raise ContractValidationError(f"{name} contém path inseguro: {path}")
        if re.match(r"(?i)^(?:[a-z]+://|[a-z]:/)", normalized):
            raise ContractValidationError(f"{name} contém path externo: {path}")
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
            raise ContractValidationError(f"schema_version não suportada: {self.schema_version!r}")

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
    text = _SECRET_VALUE.sub("[REDACTED]", text)
    text = _SENSITIVE_VALUE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
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
            raise ContractValidationError(f"status inválido: {self.status}")
        if self.status == "completed" and not _meaningful(self.evidence):
            raise ContractValidationError("completed exige evidence meaningful")
        payload = {"outputs": self.outputs, "evidence": self.evidence, "tests": self.tests, "blockers": self.blockers, "assumptions": self.assumptions, "decisions": self.decisions, "timestamps": self.timestamps}
        _json_safe(payload)
        _check_secrets(payload)
        self.outputs, self.evidence, self.tests = _json_safe(self.outputs), _json_safe(self.evidence), _json_safe(self.tests)
        self.blockers, self.assumptions, self.decisions, self.timestamps = _json_safe(self.blockers), _json_safe(self.assumptions), _json_safe(self.decisions), _json_safe(self.timestamps)
        self.error = _sanitize_error(self.error) if self.error is not None else None
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError(f"schema_version não suportada: {self.schema_version!r}")

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


__all__ = ["SCHEMA_VERSION", "MAX_RETRY_ATTEMPTS", "ContractError", "ContractValidationError", "RetryPolicy", "AgentContract", "AgentReport"]
