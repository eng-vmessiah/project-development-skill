"""Pure, fail-closed policy engine for PD fleet gates.

This module only validates and evaluates data.  It never executes commands or
accesses a filesystem/network.  Gate payloads are defensive JSON-safe copies so
that persisted reports are reproducible and deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Mapping, cast


class GateError(ValueError):
    """Invalid gate data or an invalid state transition."""


class GateType(str, Enum):
    REVIEW = "review"
    GRILL = "grill"
    SMOKE_TEST = "smoke_test"
    EVIDENCE = "evidence"


class GateStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


_VALID_TRANSITIONS = {
    GateStatus.PENDING: frozenset({GateStatus.RUNNING, GateStatus.BLOCKED}),
    GateStatus.RUNNING: frozenset({GateStatus.PASSED, GateStatus.FAILED, GateStatus.BLOCKED}),
    GateStatus.FAILED: frozenset({GateStatus.RUNNING}),
    GateStatus.BLOCKED: frozenset({GateStatus.RUNNING}),
    GateStatus.PASSED: frozenset(),
}


def _safe(value: Any, path: str = "value", seen: set[int] | None = None) -> Any:
    if seen is None:
        seen = set()
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if value != value or value in (float("inf"), float("-inf")):
            raise GateError(f"{path} contém número não finito")
        return value
    marker = id(value)
    if marker in seen:
        raise GateError(f"{path} contém estrutura cíclica")
    seen.add(marker)
    try:
        if isinstance(value, Mapping):
            if any(type(k) is not str or not k for k in value):
                raise GateError(f"{path} contém chave JSON inválida")
            return {k: _safe(v, f"{path}.{k}", seen) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_safe(v, f"{path}[{i}]", seen) for i, v in enumerate(value)]
        raise GateError(f"{path} não é JSON-safe")
    finally:
        seen.discard(marker)


def _text(value: Any, name: str, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if type(value) is not str or (required and not value.strip()):
        raise GateError(f"{name} deve ser string não vazia")
    return value.strip()


def _status(value: Any) -> GateStatus:
    try:
        return value if isinstance(value, GateStatus) else GateStatus(value)
    except (ValueError, TypeError) as exc:
        raise GateError(f"status inválido: {value!r}") from exc


def _items(value: Any, name: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise GateError(f"{name} deve ser uma lista")
    return list(value)


def _references(value: Any, name: str) -> list[Any]:
    # Copy and validate the complete payload, including nested metadata.
    result = _safe(_items(value, name), name)
    for item in result:
        if type(item) is str:
            if not item.strip():
                raise GateError(f"{name} contém referência vazia")
        elif isinstance(item, Mapping):
            if not any(type(item.get(k)) is str and item[k].strip() for k in ("ref", "id", "path", "name")):
                raise GateError(f"{name} contém referência sem id/ref/path")
        else:
            raise GateError(f"{name} contém referência inválida")
    return result


def _passes_gate_contract(gate: "GateResult") -> bool:
    """Whether a result has enough data to truthfully be passed."""
    return bool(gate.owner and gate.decision and gate.evidence and gate.reports) and not any(
        _open_blocker(item) for item in gate.blockers
    )


def _frozen_policy(value: Any, path: str = "policy") -> Any:
    """Copy JSON-safe policy data and make mapping containers immutable."""
    value = _safe(value, path)
    if isinstance(value, Mapping):
        return MappingProxyType({key: _frozen_policy(item, f"{path}.{key}") for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_frozen_policy(item, f"{path}[{index}]") for index, item in enumerate(value))
    return value


def _open_blocker(item: Any) -> bool:
    if isinstance(item, Mapping):
        severity = str(item.get("severity", item.get("level", ""))).lower()
        status = str(item.get("status", "open")).lower()
        return status not in {"closed", "resolved", "done", "passed"} and severity in {"blocker", "high"}
    return bool(item)


@dataclass
class GateResult:
    gate_id: str
    gate_type: str
    status: GateStatus | str = GateStatus.PENDING
    owner: str | None = None
    decision: str | None = None
    blockers: list[Any] = field(default_factory=list)
    evidence: list[Any] = field(default_factory=list)
    reports: list[Any] = field(default_factory=list)
    details: Any = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.gate_id = cast(str, _text(self.gate_id, "gate_id"))
        self.gate_type = cast(str, _text(self.gate_type, "gate_type"))
        if self.gate_type not in {x.value for x in GateType}:
            raise GateError(f"gate_type inválido: {self.gate_type!r}")
        current = _status(self.status)
        self.status = cast(GateStatus, current)
        self.owner = _text(self.owner, "owner", required=False)
        self.decision = _text(self.decision, "decision", required=False)
        self.blockers = _safe(_items(self.blockers, "blockers"))
        self.evidence = _references(self.evidence, "evidence")
        self.reports = _references(self.reports, "reports")
        if not isinstance(self.details, Mapping):
            raise GateError("details deve ser objeto")
        self.details = _safe(self.details, "details")
        if current is GateStatus.PASSED and not _passes_gate_contract(self):
            raise GateError("resultado passed exige owner, decision, evidence, reports e nenhum blocker aberto")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | "GateResult") -> "GateResult":
        if isinstance(value, cls):
            return cls.from_dict(value.to_dict())
        if not isinstance(value, Mapping):
            raise GateError("gate result deve ser objeto")
        gate_id = value.get("gate_id", value.get("id"))
        gate_type = value.get("gate_type", value.get("kind", value.get("type")))
        return cls(gate_id, gate_type, value.get("status", "pending"), value.get("owner"),
                   value.get("decision"), value.get("blockers", []),
                   value.get("evidence", value.get("evidence_refs", [])),
                   value.get("reports", []), value.get("details", {}))

    def transition(self, target: GateStatus | str, *, reason: str | None = None) -> "GateResult":
        target = _status(target)
        if target not in _VALID_TRANSITIONS[self.status]:
            raise GateError(f"{self.status.value} → {target.value} não permitido")
        if target in {GateStatus.PASSED, GateStatus.FAILED}:
            if not self.owner or not self.decision:
                raise GateError("resultado final exige owner e decision")
        if target is GateStatus.PASSED and not _passes_gate_contract(self):
            raise GateError("resultado passed exige owner, decision, evidence, reports e nenhum blocker aberto")
        self.status = target
        if reason is not None:
            if not isinstance(self.details, Mapping):
                raise GateError("details deve ser objeto")
            self.details = {**self.details, "reason": _text(reason, "reason")}
        return self

    def to_dict(self) -> dict[str, Any]:
        return _safe({"gate_id": self.gate_id, "gate_type": self.gate_type,
                      "status": self.status.value, "owner": self.owner,
                      "decision": self.decision, "blockers": self.blockers,
                      "evidence": self.evidence, "reports": self.reports,
                      "details": self.details})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, value: str) -> "GateResult":
        try:
            return cls.from_dict(json.loads(value))
        except (TypeError, json.JSONDecodeError) as exc:
            raise GateError("JSON inválido") from exc


@dataclass(frozen=True)
class GatePolicy:
    """Configurable requirements; every unspecified requirement denies access."""
    requirements: Mapping[str, Mapping[str, bool]] = field(default_factory=dict)
    default_requirements: Mapping[str, bool] = field(default_factory=lambda: {
        "owner": True, "decision": True, "evidence": True, "reports": True,
        "no_blockers": True,
    })

    def __post_init__(self) -> None:
        if not isinstance(self.requirements, Mapping):
            raise GateError("requirements deve ser objeto")
        normalized = {}
        for kind, req in self.requirements.items():
            if type(kind) is not str or not kind:
                raise GateError("requirements contém chave JSON inválida")
            if kind not in {x.value for x in GateType}:
                raise GateError(f"gate_type inválido: {kind!r}")
            if not isinstance(req, Mapping):
                raise GateError("requirements deve conter objetos")
            safe_req = _safe(req, f"requirements.{kind}")
            normalized[kind] = {key: bool(item) for key, item in safe_req.items()}
        if not isinstance(self.default_requirements, Mapping):
            raise GateError("default_requirements deve ser objeto")
        safe_defaults = _safe(self.default_requirements, "default_requirements")
        defaults = {key: bool(item) for key, item in safe_defaults.items()}
        object.__setattr__(self, "requirements", _frozen_policy(normalized, "requirements"))
        object.__setattr__(self, "default_requirements", _frozen_policy(defaults, "default_requirements"))

    @classmethod
    def from_dict(cls, value: Any) -> "GatePolicy":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise GateError("policy deve ser objeto")
        req = value.get("requirements", value.get("gates", {}))
        defaults = value.get("default_requirements", cls().default_requirements)
        if not isinstance(defaults, Mapping):
            raise GateError("default_requirements deve ser objeto")
        return cls(req, {str(k): bool(v) for k, v in defaults.items()})

    def evaluate(self, result: GateResult | Mapping[str, Any]) -> GateStatus:
        gate = result if isinstance(result, GateResult) else GateResult.from_dict(result)
        if gate.status in {GateStatus.PENDING, GateStatus.RUNNING}:
            return gate.status
        req = dict(self.default_requirements)
        req.update(self.requirements.get(gate.gate_type, {}))
        # Human decisions are deliberately never auto-promoted.
        if gate.decision and str(gate.decision).lower() in {"human", "human_required", "needs_approval", "pending"}:
            return GateStatus.PENDING
        if gate.status != GateStatus.PASSED:
            return gate.status
        if req.get("owner", True) and not gate.owner:
            return GateStatus.BLOCKED
        if req.get("decision", True) and not gate.decision:
            return GateStatus.PENDING
        if req.get("evidence", True) and not gate.evidence:
            return GateStatus.BLOCKED
        if req.get("reports", True) and not gate.reports:
            return GateStatus.BLOCKED
        if req.get("no_blockers", True) and any(_open_blocker(x) for x in gate.blockers):
            return GateStatus.BLOCKED
        return GateStatus.PASSED

    def allows(self, result: GateResult | Mapping[str, Any]) -> bool:
        return self.evaluate(result) is GateStatus.PASSED

    def to_dict(self) -> dict[str, Any]:
        return _safe({"requirements": self.requirements, "default_requirements": self.default_requirements})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
