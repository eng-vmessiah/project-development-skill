"""Máquina de estados pura para tasks da fleet e política de gates.

Não há persistência, relógio global, CLI ou chamadas a adapters neste módulo. O
orchestrator fornece o instante corrente e decide quando invocar as operações.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping


class LifecycleState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class LifecycleError(ValueError):
    """Operação não permitida ou dados obrigatórios ausentes."""


class InvalidTransition(LifecycleError):
    pass


class CompletionError(LifecycleError):
    pass


class RetryExhausted(LifecycleError):
    pass


# A task bloqueada não pode ser reativada por retry automático. A única saída
# de failed é retry explícito; completed/skipped são terminais.
VALID_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.PENDING: frozenset({LifecycleState.READY, LifecycleState.SKIPPED, LifecycleState.BLOCKED}),
    LifecycleState.READY: frozenset({LifecycleState.RUNNING, LifecycleState.SKIPPED, LifecycleState.BLOCKED}),
    LifecycleState.RUNNING: frozenset({LifecycleState.COMPLETED, LifecycleState.FAILED, LifecycleState.BLOCKED}),
    LifecycleState.FAILED: frozenset({LifecycleState.READY}),
    LifecycleState.BLOCKED: frozenset(),
    LifecycleState.COMPLETED: frozenset(),
    LifecycleState.SKIPPED: frozenset(),
}


def _state(value: LifecycleState | str) -> LifecycleState:
    if not isinstance(value, LifecycleState) and type(value) is not str:
        raise LifecycleError("estado inválido")
    try:
        return value if isinstance(value, LifecycleState) else LifecycleState(value)
    except (TypeError, ValueError) as exc:
        raise LifecycleError("estado inválido") from exc


def _has(value: Any) -> bool:
    return value is not None and (not hasattr(value, "__len__") or len(value) > 0)


def _seconds(value: Any) -> float:
    if hasattr(value, "timestamp"):
        return float(value.timestamp())
    return float(value)


@dataclass
class TaskLifecycle:
    task_id: str
    state: LifecycleState = LifecycleState.PENDING
    attempt: int = 0
    max_attempts: int = 1
    agent: str | None = None
    heartbeat: float | None = None
    started_at: float | None = None
    finished_at: float | None = None
    outputs: Any = None
    evidence: Any = None
    reason: str | None = None
    error: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    # A final report is distinct from the last heartbeat: a worker can be
    # alive while never producing the report needed to resume.
    final_report: Any = None
    # Compatibility spelling used by some adapters/persisted payloads.
    report_final: Any = None
    retryable: bool = True

    def __post_init__(self) -> None:
        self.state = _state(self.state)
        if not self.task_id or not isinstance(self.task_id, str):
            raise LifecycleError("task_id deve ser uma string não vazia")
        if self.max_attempts < 1:
            raise LifecycleError("max_attempts deve ser >= 1")
        if self.attempt < 0 or self.attempt > self.max_attempts:
            raise LifecycleError("attempt fora dos limites de max_attempts")

    @property
    def status(self) -> str:
        return self.state.value

    @property
    def attempts(self) -> int:
        return self.attempt

    def can_transition(self, target: LifecycleState | str) -> bool:
        target = _state(target)
        return target in VALID_TRANSITIONS[self.state]

    def transition(self, target: LifecycleState | str, *, reason: str | None = None) -> "TaskLifecycle":
        target = _state(target)
        if not self.can_transition(target):
            raise InvalidTransition(f"{self.status} → {target.value} não permitido")
        previous = self.state.value
        self.state = target
        if reason is not None:
            self.reason = reason
        self.history.append({"from": previous, "to": target.value, "reason": reason})
        return self

    def mark_ready(self) -> "TaskLifecycle":
        return self.transition(LifecycleState.READY)

    def start(self, agent: str, *, now: Any = None) -> "TaskLifecycle":
        if not agent:
            raise LifecycleError("running exige agent")
        self.transition(LifecycleState.RUNNING)
        if self.attempt == 0:
            self.attempt = 1
        self.agent = agent
        if now is not None:
            self.started_at = self.heartbeat = _seconds(now)
        return self

    def beat(self, *, now: Any) -> "TaskLifecycle":
        if self.state != LifecycleState.RUNNING:
            raise InvalidTransition("heartbeat só é válido em running")
        self.heartbeat = _seconds(now)
        return self

    heartbeat_at = beat

    def complete(self, outputs: Any = None, evidence: Any = None, *, now: Any = None) -> "TaskLifecycle":
        if self.state == LifecycleState.COMPLETED:
            return self  # resume/replay é idempotente
        if self.state != LifecycleState.RUNNING:
            raise InvalidTransition(f"{self.status} → completed não permitido")
        if not _has(outputs) or not _has(evidence):
            raise CompletionError("completed exige outputs e evidence não vazios")
        self.outputs, self.evidence = outputs, evidence
        self.final_report = evidence
        self.report_final = evidence
        self.finished_at = _seconds(now) if now is not None else self.finished_at
        return self.transition(LifecycleState.COMPLETED)

    def fail(self, error: str, *, retryable: bool = True, now: Any = None) -> "TaskLifecycle":
        if self.state != LifecycleState.RUNNING:
            raise InvalidTransition(f"{self.status} → failed não permitido")
        self.error = error
        self.retryable = bool(retryable)
        self.finished_at = _seconds(now) if now is not None else self.finished_at
        return self.transition(LifecycleState.FAILED, reason=error)

    def retry(self, *, now: Any = None) -> "TaskLifecycle":
        if self.state != LifecycleState.FAILED:
            raise InvalidTransition("retry só é permitido para failed")
        if self.attempt >= self.max_attempts:
            raise RetryExhausted(f"max_attempts ({self.max_attempts}) atingido")
        if not self.retryable:
            raise RetryExhausted("falha não é retryable")
        self.attempt += 1
        self.error = None
        return self.transition(LifecycleState.READY, reason="explicit_retry")

    def block(self, reason: str) -> "TaskLifecycle":
        if not reason or not reason.strip():
            raise LifecycleError("blocked exige motivo acionável")
        return self.transition(LifecycleState.BLOCKED, reason=reason)

    def skip(self, reason: str) -> "TaskLifecycle":
        if not reason or not reason.strip():
            raise LifecycleError("skipped exige decisão/razão")
        return self.transition(LifecycleState.SKIPPED, reason=reason)

    def recover_orphan(self, *, now: Any, timeout_seconds: float = 300) -> bool:
        """Converte running sem heartbeat recente em failed/orphaned_run."""
        if self.state != LifecycleState.RUNNING:
            return False
        if timeout_seconds < 0:
            raise LifecycleError("timeout_seconds deve ser >= 0")
        reference = self.heartbeat if self.heartbeat is not None else self.started_at
        report = self.final_report if self.final_report is not None else self.report_final
        if report is None or reference is None or _seconds(now) - reference >= timeout_seconds:
            self.fail("orphaned_run", retryable=True, now=now)
            return True
        return False

    recover_orphaned = recover_orphan


@dataclass(frozen=True)
class GatePolicy:
    """Avalia gates sem conhecer CLI ou mecanismo de persistência."""
    required: tuple[str, ...] = ()
    allow_skipped_dependencies: bool = True

    @classmethod
    def from_gates(cls, gates: Iterable[Any] = ()) -> "GatePolicy":
        required = []
        for gate in gates:
            if isinstance(gate, Mapping):
                gate_id, status = gate.get("id", gate.get("gate_id")), gate.get("status", "pending")
            else:
                gate_id, status = getattr(gate, "id", None), getattr(gate, "status", "pending")
            if gate_id:
                required.append(str(gate_id))
        return cls(tuple(required))

    def allows(self, gates: Mapping[str, Any] | Iterable[Any] = ()) -> bool:
        values = gates if isinstance(gates, Mapping) else {str(getattr(g, "id", getattr(g, "gate_id", ""))): g for g in gates}
        return all(self._passed(values.get(gate_id)) for gate_id in self.required)

    def blocked_by(self, gates: Mapping[str, Any] | Iterable[Any] = ()) -> tuple[str, ...]:
        values = gates if isinstance(gates, Mapping) else {str(getattr(g, "id", getattr(g, "gate_id", ""))): g for g in gates}
        return tuple(gate_id for gate_id in self.required if not self._passed(values.get(gate_id)))

    @staticmethod
    def _passed(gate: Any) -> bool:
        if gate is None:
            return False
        if isinstance(gate, Mapping):
            status = gate.get("status")
            present = gate.__contains__
            get = gate.get
        else:
            status = getattr(gate, "status", None)
            present = lambda name: hasattr(gate, name)
            get = lambda name: getattr(gate, name, None)
        if status != "passed":
            return False
        # Status-only gates remain valid.  Contract fields are validated when
        # they are supplied by the gate representation.
        if present("evidence") and not _has(get("evidence")):
            return False
        if present("owner") and not _has(get("owner")):
            return False
        if present("decision") and not _has(get("decision")):
            return False
        if present("blockers") and _has(get("blockers")):
            return False
        return True

    def require_ready(self, lifecycle: TaskLifecycle, gates: Mapping[str, Any] | Iterable[Any] = ()) -> TaskLifecycle:
        if lifecycle.state == LifecycleState.PENDING:
            if self.allows(gates):
                lifecycle.mark_ready()
            else:
                lifecycle.block("gate: " + ", ".join(self.blocked_by(gates)))
        return lifecycle


# Nomes funcionais convenientes para integrações futuras.
def transition(lifecycle: TaskLifecycle, target: LifecycleState | str, **kwargs: Any) -> TaskLifecycle:
    return lifecycle.transition(target, **kwargs)


TaskState = LifecycleState
Lifecycle = TaskLifecycle

__all__ = ["LifecycleState", "TaskState", "TaskLifecycle", "Lifecycle", "GatePolicy", "LifecycleError", "InvalidTransition", "CompletionError", "RetryExhausted", "VALID_TRANSITIONS", "transition"]
