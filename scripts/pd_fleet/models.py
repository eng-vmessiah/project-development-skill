"""Modelos puros e serializáveis para planos de fleet do PD.

Este módulo deliberadamente não implementa DAG, ownership ou lifecycle. Ele apenas
normaliza o formato do plano e valida o contrato mínimo necessário para as tarefas
posteriores.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from typing import Any, ClassVar, Mapping


SCHEMA_VERSION = "1"


class FleetPlanError(ValueError):
    """Erro de contrato ao construir ou normalizar um plano."""


def _required(data: Mapping[str, Any], name: str) -> Any:
    value = data.get(name)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise FleetPlanError(f"campo obrigatório ausente ou vazio: {name}")
    return value


def _string(value: Any, name: str, *, required: bool = True) -> str | None:
    if not isinstance(value, str) or (required and not value.strip()):
        suffix = " não vazio" if required else ""
        raise FleetPlanError(f"{name} deve ser uma string{suffix}")
    return value.strip() if required else value


def _list(value: Any, name: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise FleetPlanError(f"{name} deve ser uma lista")
    return list(value)


def _string_list(value: Any, name: str) -> list[str]:
    items = _list(value, name)
    if any(not isinstance(item, str) for item in items):
        raise FleetPlanError(f"{name} deve conter apenas strings")
    normalized = [item.strip() for item in items]
    if any(not item for item in normalized):
        raise FleetPlanError(f"{name} deve conter strings não vazias")
    return normalized


def _id(value: Any, name: str = "id") -> str:
    if not isinstance(value, str) or not value.strip():
        raise FleetPlanError(f"{name} deve ser um identificador string não vazio")
    return value.strip()


@dataclass
class AgentSpec:
    id: str
    role: str
    capabilities: list[str] = field(default_factory=list)
    status: str = "available"

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | "AgentSpec") -> "AgentSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise FleetPlanError("agent deve ser um objeto")
        return cls(_id(_required(value, "id")), _string(_required(value, "role"), "role"),
                   _string_list(value.get("capabilities"), "capabilities"),
                   _string(value.get("status", "available"), "status"))


@dataclass
class OutputSpec:
    name: str
    description: str | None = None
    required: bool = True

    @classmethod
    def from_dict(cls, value: Any) -> "OutputSpec":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(_id(value, "output name"))
        if not isinstance(value, Mapping):
            raise FleetPlanError("output deve ser string ou objeto")
        name = value.get("name", value.get("id"))
        description = value.get("description")
        if description is not None:
            description = _string(description, "description", required=False)
        required = value.get("required", True)
        if not isinstance(required, bool):
            raise FleetPlanError("required deve ser booleano")
        return cls(_id(_required({"name": name}, "name"), "output name"), description, required)


@dataclass
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0
    retryable_errors: list[str] = field(default_factory=list)

    @property
    def retry_on(self) -> list[str]:
        """Nome alternativo conveniente, mantido para compatibilidade."""
        return self.retryable_errors

    @classmethod
    def from_dict(cls, value: Any) -> "RetryPolicy":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise FleetPlanError("retry_policy deve ser um objeto")
        attempts = value.get("max_attempts", 1)
        if isinstance(attempts, bool) or not isinstance(attempts, int):
            raise FleetPlanError("max_attempts deve ser inteiro")
        if attempts < 1:
            raise FleetPlanError("max_attempts deve ser >= 1")
        backoff = value.get("backoff_seconds", 0)
        if isinstance(backoff, bool) or not isinstance(backoff, (int, float)):
            raise FleetPlanError("backoff_seconds deve ser numérico")
        backoff = float(backoff)
        if not math.isfinite(backoff):
            raise FleetPlanError("backoff_seconds deve ser finito")
        if backoff < 0:
            raise FleetPlanError("backoff_seconds deve ser >= 0")
        errors = value.get("retryable_errors", value.get("retry_on"))
        return cls(attempts, backoff, _string_list(errors, "retryable_errors"))


@dataclass
class TaskSpec:
    id: str
    wave: Any
    role: str
    objective: str
    title: str | None = None
    capabilities: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    parallel_group: str | None = None
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    inputs: Any = field(default_factory=dict)
    outputs: list[OutputSpec] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    validation_commands: list[str] = field(default_factory=list)
    blocked_when: list[str] = field(default_factory=list)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    owner: str | None = None
    status: str = "pending"

    REQUIRED: ClassVar[tuple[str, ...]] = ("id", "wave", "role", "objective")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | "TaskSpec") -> "TaskSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise FleetPlanError("task deve ser um objeto")
        for key in cls.REQUIRED:
            _required(value, key)
        return cls(
            _id(value["id"]), value["wave"], _string(value["role"], "role"), _string(value["objective"], "objective"),
            _string(value["title"], "title", required=False) if value.get("title") is not None else None,
            _string_list(value.get("capabilities"), "capabilities"),
            _string_list(value.get("depends_on"), "depends_on"),
            _string(value["parallel_group"], "parallel_group", required=False) if value.get("parallel_group") is not None else None,
            _string_list(value.get("allowed_paths"), "allowed_paths"), _string_list(value.get("forbidden_paths"), "forbidden_paths"),
            value.get("inputs", {}), [OutputSpec.from_dict(x) for x in _list(value.get("outputs"), "outputs")],
            _string_list(value.get("acceptance_criteria"), "acceptance_criteria"), _string_list(value.get("validation_commands"), "validation_commands"),
            _string_list(value.get("blocked_when"), "blocked_when"), RetryPolicy.from_dict(value.get("retry_policy")),
            _string(value["owner"], "owner") if value.get("owner") is not None else None,
            _string(value.get("status", "pending"), "status"),
        )


@dataclass
class WaveSpec:
    id: str
    tasks: list[str] = field(default_factory=list)
    status: str = "pending"
    gates: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | "WaveSpec") -> "WaveSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise FleetPlanError("wave deve ser um objeto")
        return cls(_id(_required(value, "id")), _string_list(value.get("tasks"), "wave.tasks"),
                   _string(value.get("status", "pending"), "status"), _string_list(value.get("gates"), "wave.gates"))


@dataclass
class GateSpec:
    id: str
    kind: str = "validation"
    scope: str = "plan"
    owner: str | None = None
    status: str = "pending"
    required_evidence: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | "GateSpec") -> "GateSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise FleetPlanError("gate deve ser um objeto")
        owner = value.get("owner")
        if owner is not None:
            owner = _string(owner, "owner", required=False)
        return cls(_id(_required(value, "id")), _string(value.get("kind", "validation"), "kind"),
                   _string(value.get("scope", "plan"), "scope"), owner, _string(value.get("status", "pending"), "status"),
                   _string_list(value.get("required_evidence"), "required_evidence"))


def _unique(items: list[Any], label: str) -> None:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise FleetPlanError(f"IDs duplicados em {label}")


@dataclass
class FleetPlan:
    schema_version: str = SCHEMA_VERSION
    agents: list[AgentSpec] = field(default_factory=list)
    waves: list[WaveSpec] = field(default_factory=list)
    tasks: list[TaskSpec] = field(default_factory=list)
    gates: list[GateSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | "FleetPlan") -> "FleetPlan":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise FleetPlanError("fleet plan deve ser um objeto")
        schema_version = value.get("schema_version", SCHEMA_VERSION)
        if not isinstance(schema_version, str) or schema_version != SCHEMA_VERSION:
            raise FleetPlanError(f"schema_version não suportada: {schema_version!r}")
        plan = cls(schema_version,
                   [AgentSpec.from_dict(x) for x in _list(value.get("agents"), "agents")],
                   [WaveSpec.from_dict(x) for x in _list(value.get("waves"), "waves")],
                   [TaskSpec.from_dict(x) for x in _list(value.get("tasks"), "tasks")],
                   [GateSpec.from_dict(x) for x in _list(value.get("gates"), "gates")])
        for items, label in ((plan.agents, "agents"), (plan.waves, "waves"), (plan.tasks, "tasks"), (plan.gates, "gates")):
            _unique(items, label)
        return plan

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise FleetPlanError("plano não pode ser serializado como JSON válido") from exc

    @classmethod
    def from_json(cls, value: str) -> "FleetPlan":
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise FleetPlanError("JSON inválido") from exc
        return cls.from_dict(data)
