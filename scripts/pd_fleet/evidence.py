"""Verifiable evidence gate for local fleet execution.

Evidence is intentionally passive unless an executor is explicitly injected.  This
module never invokes a shell, subprocess, network, or provider on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256 as _sha256
from copy import deepcopy
import math
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class EvidenceError(ValueError):
    """Invalid or unverifiable evidence."""


class EvidenceValidationError(EvidenceError):
    """Evidence failed a gate validation with a stable machine-readable code."""

    def __init__(self, message: str, *, code: str = "invalid_evidence") -> None:
        self.code = code
        super().__init__(message)


_URL = re.compile(r"(?i)\b(?:https?|ftp|wss?)://[^\s\"'<>]+")
_BEARER = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(?:[A-Za-z_][A-Za-z0-9_.-]*(?:password|passwd|token|secret|"
    r"api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|authorization|"
    r"credential)[A-Za-z0-9_.-]*|password|passwd|token|secret|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|client[_-]?secret|authorization|credential)\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_SECRET_TOKEN = re.compile(r"(?i)\b(?:sk|gh[psoru])[-_][A-Za-z0-9_-]{8,}\b")
_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_.-])(?:/home/[^\s,;]+|/tmp/[^\s,;]+|[A-Za-z]:\\[^\s,;]+)")
_HEX = re.compile(r"^[0-9a-fA-F]{64}$")


def sanitize(value: Any) -> str:
    """Return bounded, single-value text with secrets, URLs and host paths removed."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if type(value) is not str:
        raise EvidenceValidationError("stdout/stderr devem ser texto")
    text = value.replace("\x00", "")
    text = _URL.sub("[REDACTED_URL]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _SECRET_ASSIGNMENT.sub("[REDACTED_ASSIGNMENT]", text)
    text = _SECRET_TOKEN.sub("[REDACTED]", text)
    text = _ABSOLUTE_PATH.sub("[REDACTED_PATH]", text)
    return text


def _text(value: Any, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise EvidenceValidationError(f"{field_name} deve ser string não vazia")
    return value.strip()


def _relative(path: Any) -> str:
    value = _text(path, "artifact path").replace("\\", "/")
    parts = value.split("/")
    if value.startswith("/") or value.startswith("~") or ".." in parts or re.match(r"^[A-Za-z]:$", parts[0]):
        raise EvidenceValidationError("artifact path inseguro")
    return "/".join(part for part in parts if part) or "."


def _timestamp(value: Any, field_name: str = "timestamp", *, required: bool = False) -> str:
    if value is None or value == "":
        if required:
            raise EvidenceValidationError(f"{field_name} ausente", code=f"missing_{field_name}")
        return datetime.now(timezone.utc).isoformat()
    text = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceValidationError(f"{field_name} inválido", code=f"invalid_{field_name}") from exc
    if field_name == "verified_at" and (parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed)):
        raise EvidenceValidationError("verified_at deve ser UTC", code="invalid_verified_at")
    return text


@dataclass
class EvidenceRecord:
    command: str = ""
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    artifacts: list[str] = field(default_factory=list)
    sha256: str | Mapping[str, str] | None = None
    timestamp: str = ""
    source: str = "manual"
    provenance: str = ""
    verified_at: str = ""

    # artifact_paths is accepted by callers using the contract's terminology.
    def __post_init__(self) -> None:
        self.command = "" if self.command is None or (type(self.command) is str and not self.command.strip()) else _text(self.command, "command")
        if self.command and (_URL.search(self.command) or _SECRET_ASSIGNMENT.search(self.command) or _SECRET_TOKEN.search(self.command)):
            raise EvidenceValidationError("command contém segredo ou URL")
        if self.exit_code is not None and (type(self.exit_code) is not int):
            raise EvidenceValidationError("exit_code deve ser inteiro")
        self.stdout = sanitize(self.stdout)
        self.stderr = sanitize(self.stderr)
        raw = self.artifacts
        if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
            raise EvidenceValidationError("artifacts deve ser lista")
        self.artifacts = [_relative(p) for p in raw]
        self.timestamp = _timestamp(self.timestamp)
        self.source = "" if self.source is None else _text(self.source, "source")
        if _URL.search(self.source) or _SECRET_ASSIGNMENT.search(self.source) or _SECRET_TOKEN.search(self.source):
            raise EvidenceValidationError("source contém segredo ou URL")
        if self.provenance is None or self.provenance == "":
            raise EvidenceValidationError("provenance ausente", code="missing_provenance")
        self.provenance = _text(self.provenance, "provenance")
        if _URL.search(self.provenance) or _SECRET_ASSIGNMENT.search(self.provenance) or _SECRET_TOKEN.search(self.provenance) or _ABSOLUTE_PATH.search(self.provenance):
            raise EvidenceValidationError("provenance contém segredo, URL ou caminho", code="unsafe_provenance")
        self.verified_at = _timestamp(self.verified_at, "verified_at", required=True)
        if not self.command and not self.artifacts:
            raise EvidenceValidationError("evidência declarativa exige comando ou artefato")
        self._validate_hash_shape()

    @property
    def artifact_paths(self) -> list[str]:
        return list(self.artifacts)

    def _validate_hash_shape(self) -> None:
        if self.sha256 is None:
            return
        if isinstance(self.sha256, Mapping):
            normalized: dict[str, str] = {}
            for key, value in self.sha256.items():
                try:
                    normalized[_relative(key)] = value
                except EvidenceValidationError:
                    raise EvidenceValidationError("sha256 inválido") from None
                if type(value) is not str or not _HEX.fullmatch(value):
                    raise EvidenceValidationError("sha256 inválido")
            self.sha256 = dict(sorted(normalized.items()))
        elif type(self.sha256) is str and _HEX.fullmatch(self.sha256):
            self.sha256 = self.sha256.lower()
        else:
            raise EvidenceValidationError("sha256 inválido")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | "EvidenceRecord") -> "EvidenceRecord":
        if isinstance(value, cls):
            return cls(**value.to_dict())
        if not isinstance(value, Mapping):
            raise EvidenceValidationError("evidence deve ser objeto")
        allowed = {"command", "exit_code", "stdout", "stderr", "artifacts", "artifact_paths", "sha256", "timestamp", "created_at", "source", "provenance", "verified_at"}
        if any(not isinstance(key, str) or key not in allowed for key in value):
            raise EvidenceValidationError("evidence contém campo desconhecido", code="unknown_field")
        for canonical, alias in (("artifacts", "artifact_paths"), ("timestamp", "created_at")):
            if canonical in value and alias in value:
                raise EvidenceValidationError("evidence contém alias conflitante", code="conflicting_alias")
        return cls(command=value.get("command", ""), exit_code=value.get("exit_code"), stdout=value.get("stdout", ""), stderr=value.get("stderr", ""), artifacts=value.get("artifacts", value.get("artifact_paths", [])), sha256=value.get("sha256"), timestamp=value.get("timestamp", value.get("created_at", "")), source=value.get("source", "manual"), provenance=value.get("provenance", ""), verified_at=value.get("verified_at", ""))

    def to_dict(self) -> dict[str, Any]:
        # Return an independent, canonical structure; callers cannot mutate the
        # record through a hash mapping and JSON serializers see only primitives.
        hashes = deepcopy(self.sha256)
        if isinstance(hashes, dict):
            hashes = dict(sorted(hashes.items()))
        return {"command": self.command, "exit_code": self.exit_code, "stdout": self.stdout, "stderr": self.stderr, "artifacts": list(self.artifacts), "sha256": hashes, "timestamp": self.timestamp, "source": self.source, "provenance": self.provenance, "verified_at": self.verified_at}


@dataclass
class EvidenceStore:
    allowed_paths: Sequence[str | Path] = field(default_factory=list)
    records: list[EvidenceRecord] = field(default_factory=list)
    max_age_seconds: float = 86400
    clock: Callable[[], datetime | str] = field(default=lambda: datetime.now(timezone.utc), repr=False)

    def __post_init__(self) -> None:
        if type(self.max_age_seconds) not in (int, float) or isinstance(self.max_age_seconds, bool) or not math.isfinite(self.max_age_seconds) or self.max_age_seconds <= 0:
            raise EvidenceValidationError("max_age_seconds deve ser positivo e finito", code="invalid_max_age_seconds")
        if not callable(self.clock):
            raise EvidenceValidationError("clock inválido", code="invalid_clock")
        self.allowed_paths = tuple(Path(p).resolve() for p in self.allowed_paths)
        self.records = [EvidenceRecord.from_dict(r) for r in self.records]

    def capture(self, command: str, *, executor: Callable[[str], Any] | None = None,
                artifacts: Sequence[str | Path] = (), sha256: str | Mapping[str, str] | None = None,
                source: str = "injected", provenance: str = "") -> EvidenceRecord:
        """Capture a command result through an explicitly injected test double.

        No executor means fail closed; notably, this does not fall back to shell.
        Executors may return a mapping or ``(exit_code, stdout, stderr)`` tuple.
        """
        # Do all untrusted metadata validation before handing anything to an
        # injected callable.  In particular, secrets and URLs must never reach
        # even a test double that records commands.
        command = _text(command, "command")
        if _URL.search(command) or _SECRET_ASSIGNMENT.search(command) or _SECRET_TOKEN.search(command):
            raise EvidenceValidationError("command contém segredo ou URL")
        source = _text(source, "source")
        if _URL.search(source) or _SECRET_ASSIGNMENT.search(source) or _SECRET_TOKEN.search(source):
            raise EvidenceValidationError("source contém segredo ou URL")
        if provenance is None or provenance == "":
            raise EvidenceValidationError("provenance ausente", code="missing_provenance")
        provenance = _text(provenance, "provenance")
        if _URL.search(provenance) or _SECRET_ASSIGNMENT.search(provenance) or _SECRET_TOKEN.search(provenance) or _ABSOLUTE_PATH.search(provenance):
            raise EvidenceValidationError("provenance contém segredo, URL ou caminho", code="unsafe_provenance")
        if executor is None or not callable(executor):
            raise EvidenceError("capture exige executor injetado; shell/rede desabilitados")
        try:
            result = executor(command)
        except Exception:
            raise EvidenceError("executor falhou") from None
        if isinstance(result, Mapping):
            code, out, err = result.get("exit_code"), result.get("stdout", ""), result.get("stderr", "")
        elif isinstance(result, (tuple, list)) and len(result) == 3:
            code, out, err = result
        else:
            raise EvidenceError("executor deve retornar mapping ou (exit_code, stdout, stderr)")
        now = _clock_datetime(self.clock)
        stamp = now.isoformat().replace("+00:00", "Z")
        record = EvidenceRecord(command=command, exit_code=code, stdout=out, stderr=err, artifacts=[str(p) for p in artifacts], sha256=sha256, timestamp=stamp, source=source, provenance=provenance, verified_at=stamp)
        self.validate(record)
        self.records.append(record)
        return record

    def add(self, record: EvidenceRecord | Mapping[str, Any]) -> EvidenceRecord:
        record = EvidenceRecord.from_dict(record)
        self.validate(record)
        self.records.append(record)
        return record

    def validate(self, record: EvidenceRecord | Mapping[str, Any]) -> EvidenceRecord:
        record = EvidenceRecord.from_dict(record)
        now = _clock_datetime(self.clock)
        verified = _parse_utc(record.verified_at, "verified_at")
        age = (now - verified).total_seconds()
        if age < 0:
            raise EvidenceValidationError("verified_at está no futuro", code="verified_at_future")
        if age > self.max_age_seconds:
            raise EvidenceValidationError("evidence está stale", code="evidence_stale")
        if record.exit_code != 0:
            raise EvidenceValidationError("evidence exige exit_code=0")
        if not record.command and not record.artifacts:
            raise EvidenceValidationError("evidência sem comando/artefato")
        resolved: dict[str, Path] = {}
        for relative in record.artifacts:
            candidate = None
            for root in self.allowed_paths:
                probe = (root / relative).resolve()
                try:
                    probe.relative_to(root)
                except ValueError:
                    continue
                if probe.exists() and probe.is_file():
                    candidate = probe
                    break
            if candidate is None:
                raise EvidenceValidationError("artefato ausente ou fora de allowed_paths")
            resolved[relative] = candidate
        if isinstance(record.sha256, Mapping):
            for relative, expected in record.sha256.items():
                if relative not in resolved:
                    raise EvidenceValidationError("hash sem artefato")
                actual = _sha256(resolved[relative].read_bytes()).hexdigest()
                if actual.lower() != expected.lower():
                    raise EvidenceValidationError("hash mismatch")
        elif record.sha256 is not None:
            if len(resolved) != 1:
                raise EvidenceValidationError("sha256 único exige exatamente um artefato")
            actual = _sha256(next(iter(resolved.values())).read_bytes()).hexdigest()
            if actual.lower() != record.sha256.lower():
                raise EvidenceValidationError("hash mismatch")
        return record

    def validate_all(self) -> list[EvidenceRecord]:
        return [self.validate(record) for record in self.records]

    def to_dict(self) -> list[dict[str, Any]]:
        self.validate_all()
        return [record.to_dict() for record in self.records]


def _parse_utc(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceValidationError(f"{field_name} inválido", code=f"invalid_{field_name}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise EvidenceValidationError(f"{field_name} deve ser UTC", code=f"invalid_{field_name}")
    return parsed.astimezone(timezone.utc)


def _clock_datetime(clock: Callable[[], datetime | str]) -> datetime:
    value = clock()
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise EvidenceValidationError("clock deve retornar UTC", code="invalid_clock")
        return value.astimezone(timezone.utc)
    if type(value) is str:
        return _parse_utc(value, "clock")
    raise EvidenceValidationError("clock deve retornar datetime ou string UTC", code="invalid_clock")
