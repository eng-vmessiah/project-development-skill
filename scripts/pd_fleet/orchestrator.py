"""Orquestração local, determinística e orientada a DAG para FleetPlan.

A API deste módulo é deliberadamente isolada: não abre processos, não acessa a
rede e não conhece CLI. O dispatch é injetável, mas ``Dispatcher`` simulado é o
padrão. Persistência e observabilidade são hooks injetáveis e nunca obrigatórias.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
import math
import re
from numbers import Real
from typing import Any, Callable, Iterable, Mapping, Protocol

from .checkpoint import Checkpoint
from .dispatch import DispatchResult, Dispatcher
from .lifecycle import LifecycleState, TaskLifecycle
from .lifecycle import GatePolicy as LifecycleGatePolicy
try:
    from .gates import GatePolicy as ContractGatePolicy, GateResult
except ImportError:  # pragma: no cover
    ContractGatePolicy = None
    GateResult = None
from .models import FleetPlan, TaskSpec
from .validation import ValidationReport, compute_ready_tasks, validate_plan


class OrchestratorError(ValueError):
    """Erro de contrato ou de execução do orchestrator."""


_REPORT_URL_RE = re.compile(r"(?i)(?:https?|ftp|wss?)://[^\s\"'<>]+")
_REPORT_SECRET_RE = re.compile(r"(?i)\b(?:bearer\s+\S+|sk-[a-z0-9_-]+)")
_REPORT_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![a-z0-9])([a-z][a-z0-9_.-]{1,80})\s*[:=]\s*([^\s,;]+)"
)
_SENSITIVE_KEYS = ("secret", "token", "password", "credential", "apikey",
                   "accesskey", "privatekey", "authorization", "bearer")


def _sanitize_text(value: Any, default: str | None) -> str | None:
    """Make untrusted dispatch text safe for reports and persisted callbacks."""
    if value is None:
        return default
    try:
        text = value if type(value) is str else str(value)
    except Exception:
        return default
    text = _REPORT_URL_RE.sub("[redacted-url]", text)
    text = _REPORT_SECRET_RE.sub("[redacted-secret]", text)

    def redact_assignment(match: re.Match[str]) -> str:
        key = match.group(1).lower().replace("_", "").replace("-", "")
        return match.group(1) + "=[redacted-secret]" if any(word in key for word in _SENSITIVE_KEYS) else match.group(0)

    return _REPORT_ASSIGNMENT_RE.sub(redact_assignment, text)


def _sanitize_payload(value: Any, *, _seen: set[int] | None = None) -> Any:
    """Recursively produce a JSON-safe, redacted copy for reports and sinks."""
    seen = _seen if _seen is not None else set()
    if value is None or type(value) in (str, bool, int):
        return _sanitize_text(value, None) if type(value) is str else value
    if type(value) is float:
        return value if math.isfinite(value) else None
    marker = id(value)
    if marker in seen:
        return "[redacted-cycle]"
    seen.add(marker)
    try:
        if isinstance(value, Mapping):
            result = {}
            for key, item in value.items():
                name = _sanitize_text(key, "key") or "key"
                normalized = re.sub(r"[^a-z0-9]", "", name.lower())
                result[name] = ("[redacted-secret]" if any(k in normalized for k in _SENSITIVE_KEYS)
                                else _sanitize_payload(item, _seen=seen))
            return result
        if isinstance(value, (list, tuple, set, frozenset)):
            return [_sanitize_payload(item, _seen=seen) for item in value]
        return _sanitize_text(value, "[redacted-value]") or "[redacted-value]"
    finally:
        seen.discard(marker)


class LifecycleHooks(Protocol):
    """Protocolo opcional de persistência/observabilidade.

    Implementações podem fornecer qualquer subconjunto dos métodos; o
    orchestrator chama apenas os que existem. ``checkpoint`` pode retornar um
    checkpoint ou ser apenas um callback de persistência.
    """

    def lifecycle(self, lifecycle: TaskLifecycle) -> None: ...
    def report(self, report: Mapping[str, Any]) -> None: ...
    def evidence(self, task_id: str, evidence: Any) -> None: ...
    def checkpoint(self, snapshot: Mapping[str, Any]) -> None: ...


@dataclass(frozen=True)
class TaskReport:
    task_id: str
    wave: Any
    status: str
    attempt: int
    output: Any = None
    evidence: Any = None
    error: str | None = None
    reason: str | None = None
    agent_id: str | None = None
    role: str | None = None
    outputs: Any = None
    tests: Any = None
    blockers: Any = None
    assumptions: Any = None
    decisions: Any = None
    timestamps: Any = None

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({"task_id": self.task_id, "wave": self.wave, "status": self.status,
                         "attempt": self.attempt, "output": self.output,
                         "outputs": self.outputs if self.outputs is not None else self.output,
                         "agent_id": self.agent_id, "role": self.role,
                         "evidence": self.evidence, "error": self.error,
                         "reason": self.reason, "tests": self.tests if self.tests is not None else [],
                         "blockers": self.blockers if self.blockers is not None else [],
                         "assumptions": self.assumptions if self.assumptions is not None else [],
                         "decisions": self.decisions if self.decisions is not None else [],
                         "timestamps": self.timestamps if self.timestamps is not None else {}})


@dataclass
class OrchestrationResult:
    statuses: dict[str, str]
    reports: list[dict[str, Any]] = field(default_factory=list)
    waves: list[tuple[str, ...]] = field(default_factory=list)
    validation: ValidationReport | None = None

    @property
    def completed(self) -> tuple[str, ...]:
        return tuple(k for k in self.statuses if self.statuses[k] == "completed")

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(k for k in self.statuses if self.statuses[k] == "failed")

    @property
    def blocked(self) -> tuple[str, ...]:
        return tuple(k for k in self.statuses if self.statuses[k] == "blocked")

    def to_dict(self) -> dict[str, Any]:
        return {"statuses": deepcopy(self.statuses), "reports": deepcopy(self.reports),
                "waves": [list(w) for w in self.waves],
                "validation": (deepcopy(self.validation.__dict__) if self.validation is not None else None)}


class FleetOrchestrator:
    """Executa tasks de um plano em waves, sem efeitos externos implícitos."""

    def __init__(self, plan: FleetPlan | Mapping[str, Any], *, dispatcher: Any = None,
                 hooks: Any = None, max_parallel: int = 1,
                 timeout_seconds: float | None = None, clock: Callable[[], float] | None = None,
                 dry_run: bool = False, checkpoint: Checkpoint | Mapping[str, Any] | None = None,
                 gates: Mapping[str, Any] | None = None, context: Mapping[str, Any] | None = None,
                 input_values: Mapping[str, Any] | None = None,
                 sleeper: Callable[[float], None] | None = None,
                 feature: str | None = None, created_at: str | None = None) -> None:
        self.plan = FleetPlan.from_dict(plan) if not isinstance(plan, FleetPlan) else plan
        # Validate before resume or any lifecycle mutation.
        self.validation = validate_plan(self.plan)
        if isinstance(max_parallel, bool) or not isinstance(max_parallel, int) or max_parallel < 1:
            raise OrchestratorError("max_parallel deve ser inteiro >= 1")
        if timeout_seconds is not None:
            if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, Real):
                raise OrchestratorError("timeout_seconds deve ser número finito >= 0")
            try:
                timeout_seconds = float(timeout_seconds)
            except (TypeError, ValueError, OverflowError):
                raise OrchestratorError("timeout_seconds deve ser número finito >= 0") from None
            if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
                raise OrchestratorError("timeout_seconds deve ser número finito >= 0")
        self.max_parallel = max_parallel
        self.timeout_seconds = timeout_seconds
        self.clock = clock or __import__("time").monotonic
        # Do not consume an injected monotonic clock during construction: that
        # would alter timeout behaviour.  Explicit metadata remains stable.
        self.feature = feature.strip() if isinstance(feature, str) and feature.strip() else "fleet"
        self.created_at = created_at.strip() if isinstance(created_at, str) and created_at.strip() else "1970-01-01T00:00:00+00:00"
        self.dispatcher = dispatcher if dispatcher is not None else Dispatcher(dry_run=dry_run)
        self.hooks = hooks
        self.dry_run = dry_run
        # None means no override; an explicit empty mapping is still an override.
        self.gates = (dict(gates) if gates is not None else
                      {gate.id: gate for gate in self.plan.gates})
        self.context = dict(context or {})
        self.context.update(input_values or {})
        self._context_supplied = context is not None or input_values is not None
        self.sleeper = sleeper or (lambda _seconds: None)
        self.gate_policy = ContractGatePolicy() if ContractGatePolicy else LifecycleGatePolicy()
        self.checkpoint = (Checkpoint.from_dict(checkpoint) if isinstance(checkpoint, Mapping)
                           else checkpoint)
        self.lifecycles: dict[str, TaskLifecycle] = {}
        self.reports: list[dict[str, Any]] = []
        self._dry_run_seen: set[str] = set()
        self._current_wave = 0
        self._last_wave = 0
        self._resume()

    @classmethod
    def load(cls, plan: FleetPlan | Mapping[str, Any], **kwargs: Any) -> "FleetOrchestrator":
        """Alias explícito para carregar um FleetPlan sem executar."""
        return cls(plan, **kwargs)

    def plan_ready(self) -> ValidationReport:
        """Valida integralmente antes de qualquer dispatch ou mutação."""
        return self.validation

    def ready_tasks(self) -> tuple[str, ...]:
        self.plan_ready()
        by_id = {t.id: t for t in self.plan.tasks}
        completed = {i for i, l in self.lifecycles.items() if l.state in {LifecycleState.COMPLETED, LifecycleState.SKIPPED}}
        skipped = {i for i, l in self.lifecycles.items() if l.state == LifecycleState.SKIPPED}
        passed = {i for i, g in self.gates.items() if self._gate_passed(g)}
        return tuple(i for i in compute_ready_tasks(self.plan, completed=completed, skipped=skipped, gates_passed=passed)
                      if self._inputs_available(by_id[i]) and not self._blocked_condition(by_id[i])
                      and self._agent_compatible(by_id[i]))

    def run(self) -> OrchestrationResult:
        validation = self.plan_ready()  # must precede all execution
        by_id = {t.id: t for t in self.plan.tasks}
        self._block_unresolvable(by_id)
        wave_ids = self._ordered_waves(by_id)
        executed_waves: list[tuple[str, ...]] = []
        for wave in wave_ids:
            self._current_wave = self._wave_number(wave)
            self._last_wave = self._current_wave
            while True:
                ready = [i for i in self._ready_ids(by_id) if self._wave_key(self._wave(i, by_id)) == self._wave_key(wave)]
                if not ready:
                    break
                # A batch is safe: validation already rejected overlapping ownership.
                batch = tuple(ready[:self.max_parallel])
                executed_waves.append(batch)
                if self.dry_run:
                    for task_id in batch:
                        self._mark_dry_run(by_id[task_id])
                else:
                    for task_id in batch:  # deterministic dispatch order
                        self._execute(by_id[task_id])
                self._block_unresolvable(by_id)
            self._block_wave_stalls(wave, by_id)
        self._block_unresolvable(by_id)
        return OrchestrationResult({i: self.lifecycles[i].status for i in sorted(self.lifecycles)},
                                   deepcopy(self.reports), executed_waves, validation)

    execute = run
    start = run

    def _resume(self) -> None:
        for task in self.plan.tasks:
            snap = deepcopy(self.checkpoint.lifecycle.get(task.id, {})) if self.checkpoint else {}
            if isinstance(snap, Mapping):
                snap["error"] = _sanitize_text(snap.get("error"), None)
                snap["reason"] = _sanitize_text(snap.get("reason"), None)
            state = snap.get("status", snap.get("state", task.status)) if isinstance(snap, Mapping) else task.status
            # A process crash can leave a task running.  Resume never replays a
            # completed task, while an interrupted run is safely made eligible
            # again (the injected dispatcher decides whether its attempt fails).
            if state == LifecycleState.RUNNING.value:
                state = LifecycleState.READY.value
            try:
                self.lifecycles[task.id] = TaskLifecycle(task.id, state=state,
                    attempt=int(snap.get("attempt", 0)), max_attempts=task.retry_policy.max_attempts,
                    agent=snap.get("agent"), heartbeat=snap.get("heartbeat"),
                    started_at=snap.get("started_at"), finished_at=snap.get("finished_at"),
                    outputs=deepcopy(snap.get("outputs")), evidence=deepcopy(snap.get("evidence")),
                    reason=snap.get("reason"), error=snap.get("error"),
                    history=deepcopy(snap.get("history", [])), retryable=bool(snap.get("retryable", True)),
                    final_report=deepcopy(snap.get("final_report", snap.get("report_final"))),
                    report_final=deepcopy(snap.get("report_final")))
            except (TypeError, ValueError) as exc:
                raise OrchestratorError(f"checkpoint inválido para task {task.id}") from exc
        if self.checkpoint:
            for report in deepcopy(self.checkpoint.reports):
                if isinstance(report, Mapping):
                    report["error"] = _sanitize_text(report.get("error"), None)
                    report["reason"] = _sanitize_text(report.get("reason"), None)
                self.reports.append(_sanitize_payload(report))

    @staticmethod
    def _gate_passed(gate: Any) -> bool:
        if gate is None:
            return False
        # Contract GateResult (or its mapping form) is always policy evaluated;
        # status alone must never grant access.
        if GateResult is not None and (isinstance(gate, GateResult) or
                (isinstance(gate, Mapping) and ("gate_id" in gate or "gate_type" in gate))):
            try:
                return bool(FleetOrchestrator._policy.allows(gate))
            except Exception:
                return False
        # GateSpec/status-only records are declarations, not authorization.
        # Only a complete GateResult (or its mapping representation) can pass.
        return False

    _policy = ContractGatePolicy() if ContractGatePolicy else LifecycleGatePolicy()

    @staticmethod
    def _wave(task_id: str, by_id: Mapping[str, TaskSpec]) -> str:
        return str(by_id[task_id].wave)

    @staticmethod
    def _wave_key(value: str) -> str:
        value = str(value).strip().lower()
        return value[5:] if value.startswith("wave-") else value

    @staticmethod
    def _wave_number(value: Any) -> int:
        text = str(value).strip().lower()
        text = text[5:] if text.startswith("wave-") else text
        try:
            return max(0, int(text))
        except (TypeError, ValueError):
            return 0

    def _ordered_waves(self, by_id: Mapping[str, TaskSpec]) -> list[str]:
        values = {self._wave(t.id, by_id) for t in self.plan.tasks}
        return sorted(values, key=lambda x: (0, int(x.removeprefix("wave-"))) if x.removeprefix("wave-").isdigit() else (1, x))

    def _ready_ids(self, by_id: Mapping[str, TaskSpec]) -> tuple[str, ...]:
        return tuple(i for i in compute_ready_tasks(self.plan,
            completed={i for i,l in self.lifecycles.items() if l.state in {LifecycleState.COMPLETED, LifecycleState.SKIPPED}},
            skipped={i for i,l in self.lifecycles.items() if l.state == LifecycleState.SKIPPED},
            gates_passed={i for i,g in self.gates.items() if self._gate_passed(g)})
            if self.lifecycles[i].state in {LifecycleState.PENDING, LifecycleState.READY}
            and i not in self._dry_run_seen
            and self._agent_compatible(by_id[i]))

    def _execute(self, task: TaskSpec) -> None:
        life = self.lifecycles[task.id]
        if life.state == LifecycleState.COMPLETED:
            return
        # Defense in depth: dispatch must never be reached for an unresolvable
        # task, even if an injected caller invokes this private path directly.
        agent_block = self._agent_block(task)
        if agent_block is not None:
            self._block_with_report(task, agent_block[0], agent_block[1])
            return
        if not self._inputs_available(task):
            self._block_with_report(task, "input ausente", {"missing_inputs": self._missing_inputs(task)})
            return
        if self._blocked_condition(task):
            self._block_with_report(task, "blocked_when não resolvido", {"blocked_when": list(task.blocked_when)})
            return
        if life.state == LifecycleState.PENDING:
            life.mark_ready(); self._notify(life)
        policy = task.retry_policy
        while True:
            started = self.clock()
            life.start(task.owner or task.role, now=started); self._notify(life)
            try:
                result = self.dispatcher.dispatch(task, {"attempt": life.attempt, "dry_run": False,
                                                         "inputs": deepcopy(self.context)})
            except Exception as exc:
                result = DispatchResult(task.id, task.owner or task.role, "failed", life.attempt,
                                        None, {}, _sanitize_text(exc, "dispatch failed"))
            elapsed = self.clock() - started
            status = getattr(result, "status", result.get("status") if isinstance(result, Mapping) else "failed")
            if self.timeout_seconds is not None and elapsed >= self.timeout_seconds:
                status = "timeout"
            output = getattr(result, "result", result.get("result", result.get("output")) if isinstance(result, Mapping) else None)
            evidence = getattr(result, "evidence", result.get("evidence") if isinstance(result, Mapping) else {})
            error = getattr(result, "error", result.get("error") if isinstance(result, Mapping) else None)
            reason = getattr(result, "reason", result.get("reason") if isinstance(result, Mapping) else None)
            if status == "completed":
                normalized = self._normalize_completion(task, output, evidence)
                if normalized is not None:
                    output, evidence = normalized
                    life.complete(output, evidence, now=self.clock())
                    self._record(task, life, output, evidence)
                    break
            if status == "completed":
                error, reason = "completed report contract inválido", "outputs/evidence ausentes ou acceptance não atendida"
            elif status in {"timeout", "timed_out"}:
                error, reason = "timeout", "timeout"
            safe_error = _sanitize_text(error, "dispatch failed") or "dispatch failed"
            safe_reason = _sanitize_text(reason, None)
            life.fail(safe_error, retryable=(status not in {"timeout", "timed_out"}), now=self.clock())
            self._record(task, life, None, evidence or {"error": safe_error}, safe_error, safe_reason)
            retryable = life.retryable and (not policy.retryable_errors or
                         self._retry_error_matches(safe_error, policy.retryable_errors))
            if not retryable or life.attempt >= policy.max_attempts:
                break
            self.sleeper(policy.backoff_seconds)
            life.retry(now=self.clock()); self._notify(life)
        self._notify(life); self._checkpoint()

    @staticmethod
    def _retry_error_matches(error: str, tokens: Iterable[str]) -> bool:
        """Match error classes/tokens exactly, never arbitrary substrings."""
        normalized = re.sub(r"[^a-z0-9]+", " ", error.lower()).strip()
        words = set(normalized.split())
        classes = set(re.findall(r"\b[a-z_][a-z0-9_]*(?:error|exception|timeout)\b", normalized))
        for token in tokens:
            candidate = re.sub(r"[^a-z0-9]+", " ", str(token).lower()).strip()
            if not candidate:
                continue
            if " " in candidate:
                if candidate == normalized or re.search(r"(?:^| )" + re.escape(candidate) + r"(?:$| )", normalized):
                    return True
            elif candidate in words and not re.search(r"(?:^| )not (?:transient|retryable)? ?" + re.escape(candidate) + r"(?:$| )", normalized):
                return True
        return False

    def _missing_inputs(self, task: TaskSpec) -> list[str]:
        if not self._context_supplied:
            return []  # legacy callers did not provide an input namespace
        declared = task.inputs.keys() if isinstance(task.inputs, Mapping) else task.inputs or []
        return [str(item) for item in declared if str(item) not in self.context and
                not (isinstance(self.context.get("available_inputs"), (list, tuple, set)) and
                     str(item) in self.context["available_inputs"])]

    def _inputs_available(self, task: TaskSpec) -> bool:
        return not self._missing_inputs(task)

    def _blocked_condition(self, task: TaskSpec) -> bool:
        if not self._context_supplied:
            return False
        for condition in task.blocked_when:
            text = str(condition).strip()
            if text in self.context:
                if bool(self.context[text]): return True
                continue
            match = re.match(r"^([\w.-]+)\s*(?:==|=|is)\s*(.+)$", text, re.I)
            if match and match.group(1) in self.context:
                expected = match.group(2).strip().strip("'\"")
                if str(self.context[match.group(1)]).lower() == expected.lower(): return True
                continue
            return True
        return False

    def _normalize_completion(self, task: TaskSpec, output: Any, evidence: Any) -> tuple[Any, Any] | None:
        """Validate and normalize a dispatcher's completion contract."""
        names = [spec.name for spec in task.outputs]
        if not names or output is None or evidence is None:
            return None
        if isinstance(output, Mapping):
            if set(output) == set(names):
                normalized_output = {name: output[name] for name in names}
            elif (len(names) == 1 and set(output) >= {"output"}
                  and isinstance(evidence, Mapping) and evidence.get("adapter") == "simulated"):
                normalized_output = {names[0]: output["output"]}
            else:
                return None
        elif len(names) == 1:
            # Deterministic simulated/legacy compatibility: one declared output.
            normalized_output = {names[0]: output}
        else:
            return None
        if not isinstance(evidence, Mapping) or not evidence:
            return None
        if not any(value not in (None, "", [], {}, ()) for value in evidence.values()):
            return None
        acceptance = (evidence.get("acceptance") or evidence.get("acceptance_metadata") or
                      evidence.get("acceptance_criteria") or evidence.get("validation"))
        if task.acceptance_criteria and not acceptance:
            # The built-in simulated adapter's deterministic fingerprint is the
            # legacy acceptance proof; arbitrary dispatchers must be explicit.
            if not (isinstance(evidence, Mapping) and evidence.get("adapter") == "simulated"
                    and evidence.get("deterministic") is True and evidence.get("fingerprint")):
                return None
        if acceptance is False or (isinstance(acceptance, Mapping) and acceptance.get("passed") is False):
            return None
        return _sanitize_payload(normalized_output), _sanitize_payload(evidence)

    # Kept as a small compatibility hook for integrations/tests using the old name.
    def _completion_valid(self, task: TaskSpec, output: Any, evidence: Any) -> bool:
        return self._normalize_completion(task, output, evidence) is not None

    def _block_with_report(self, task: TaskSpec, reason: str, evidence: Any) -> None:
        life = self.lifecycles[task.id]
        life.block(reason); self._record(task, life, None, evidence, reason=reason)
        self._notify(life); self._checkpoint()

    def _mark_dry_run(self, task: TaskSpec) -> None:
        self._dry_run_seen.add(task.id)
        report = TaskReport(task.id, task.wave, "dry_run", self.lifecycles[task.id].attempt,
                            {"would_dispatch": True}, {"dry_run": True}, reason="dry_run").to_dict()
        self.reports.append(report)
        self._call("report", report); self._call("evidence", task.id, report["evidence"])

    def _record(self, task: TaskSpec, life: TaskLifecycle, output: Any, evidence: Any, error: str | None = None, reason: str | None = None) -> None:
        report = TaskReport(task.id, task.wave, life.status, life.attempt, _sanitize_payload(output), _sanitize_payload(evidence),
                            _sanitize_text(error, None), _sanitize_text(reason, None),
                            agent_id=task.owner, role=task.role, outputs=_sanitize_payload(output),
                            blockers=([reason] if life.status == "blocked" and reason else []),
                            timestamps={}).to_dict()
        self.reports.append(report)
        self._call("report", report); self._call("evidence", task.id, evidence)

    def _block_unresolvable(self, by_id: Mapping[str, TaskSpec]) -> None:
        for task_id in sorted(by_id):
            life = self.lifecycles[task_id]
            if life.state in {LifecycleState.COMPLETED, LifecycleState.FAILED, LifecycleState.BLOCKED, LifecycleState.SKIPPED}: continue
            agent_block = self._agent_block(by_id[task_id])
            if agent_block is not None:
                self._block_with_report(by_id[task_id], agent_block[0], agent_block[1])
                continue
            deps = [self.lifecycles[d] for d in by_id[task_id].depends_on]
            if any(d.state in {LifecycleState.FAILED, LifecycleState.BLOCKED} for d in deps):
                life.block("dependency failed or blocked"); self._notify(life); self._checkpoint()

    def _agent_compatible(self, task: TaskSpec) -> bool:
        return self._agent_block(task) is None

    def _agent_block(self, task: TaskSpec) -> tuple[str, dict[str, Any]] | None:
        # No declaration preserves legacy simulated-dispatch behavior.
        if not self.plan.agents:
            return None
        required = set(task.capabilities)
        candidates = [agent for agent in self.plan.agents
                      if agent.role == task.role and required.issubset(set(agent.capabilities))]
        if task.owner is not None:
            owner = next((agent for agent in self.plan.agents if agent.id == task.owner), None)
            if owner is None:
                return (f"owner incompatível: agente {task.owner!r} não existe",
                        {"agent_matching": {"owner": task.owner, "role": task.role,
                                             "capabilities": sorted(required), "candidates": []}})
            if owner not in candidates:
                return (f"owner incompatível: agente {task.owner!r} não atende role/capabilities",
                        {"agent_matching": {"owner": owner.id, "role": task.role,
                                             "capabilities": sorted(required),
                                             "missing_capabilities": sorted(required - set(owner.capabilities)),
                                             "agent_role": owner.role}})
            return None
        if candidates:
            return None
        return (f"nenhum agente compatível para role {task.role!r} e capabilities {sorted(required)!r}",
                {"agent_matching": {"role": task.role, "capabilities": sorted(required),
                                     "candidates": [agent.id for agent in self.plan.agents]}})

    def _block_wave_stalls(self, wave: str, by_id: Mapping[str, TaskSpec]) -> None:
        # Gate failures are explicit blockers; unresolved dependencies remain pending.
        for task_id in sorted(by_id):
            if self._wave_key(self._wave(task_id, by_id)) != self._wave_key(wave): continue
            life = self.lifecycles[task_id]
            if life.state in {LifecycleState.PENDING, LifecycleState.READY}:
                required = [g for w in self.plan.waves if self._wave_key(str(w.id)) == self._wave_key(wave) for g in w.gates]
                missing = [g for g in required if not self._gate_passed(self.gates.get(g))]
                if missing:
                    life.block("gate: " + ", ".join(sorted(missing))); self._notify(life); self._checkpoint()

    def _call(self, name: str, *args: Any) -> None:
        if self.hooks is None: return
        fn = getattr(self.hooks, name, None)
        if callable(fn): fn(*args)

    def _notify(self, life: TaskLifecycle) -> None:
        self._call("lifecycle", life)
        self._call("on_lifecycle", life)

    def _checkpoint(self) -> None:
        agents = {a.id: {"id": a.id, "role": a.role,
                         "capabilities": list(a.capabilities), "status": a.status}
                  for a in self.plan.agents}
        gates = {str(i): _sanitize_payload(getattr(g, "__dict__", g))
                 for i, g in self.gates.items()}
        attempts = {i: l.attempt for i, l in self.lifecycles.items()}
        snapshot = {"schema_version": 1, "feature": self.feature,
                    "wave": self._current_wave, "last_wave": self._last_wave,
                    "created_at": self.created_at,
                    "tasks": {t.id: {"id": t.id} for t in self.plan.tasks},
                    "lifecycle": {i: {"task_id": i, "status": l.status, "attempt": l.attempt,
                                      "max_attempts": l.max_attempts,
                                      "outputs": _sanitize_payload(l.outputs), "evidence": _sanitize_payload(l.evidence),
                                      "reason": _sanitize_text(l.reason, None), "error": _sanitize_text(l.error, None),
                                      "retryable": l.retryable, "history": _sanitize_payload(l.history),
                                      "agent": l.agent, "heartbeat": l.heartbeat, "started_at": l.started_at,
                                      "finished_at": l.finished_at, "final_report": _sanitize_payload(l.final_report),
                                      "report_final": _sanitize_payload(l.report_final)} for i,l in self.lifecycles.items()},
                    "reports": _sanitize_payload(self.reports), "evidence": [_sanitize_payload(r.get("evidence")) for r in self.reports],
                    "blockers": [i for i,l in self.lifecycles.items() if l.state == LifecycleState.BLOCKED],
                    "attempts": attempts, "gates": gates, "agents": agents}
        self._call("checkpoint", snapshot)
        self._call("save", snapshot)


Orchestrator = FleetOrchestrator
__all__ = ["FleetOrchestrator", "Orchestrator", "OrchestrationResult", "TaskReport", "OrchestratorError", "LifecycleHooks"]
