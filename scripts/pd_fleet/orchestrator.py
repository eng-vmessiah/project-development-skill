"""Orquestração local, determinística e orientada a DAG para FleetPlan.

A API deste módulo é deliberadamente isolada: não abre processos, não acessa a
rede e não conhece CLI. O dispatch é injetável, mas ``Dispatcher`` simulado é o
padrão. Persistência e observabilidade são hooks injetáveis e nunca obrigatórias.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
import inspect
import math
import re
from numbers import Real
from typing import Any, Callable, Iterable, Mapping, Protocol

from .checkpoint import Checkpoint
try:
    from .checkpoint import CheckpointV2Store
except ImportError:  # pragma: no cover
    CheckpointV2Store = None
from .dispatch import DispatchResult, Dispatcher
from .lifecycle import LifecycleState, TaskLifecycle
from .lifecycle import GatePolicy as LifecycleGatePolicy
try:
    from .gates import GatePolicy as ContractGatePolicy, GateResult, HumanVerificationGate
except ImportError:  # pragma: no cover
    ContractGatePolicy = None
    GateResult = None
    HumanVerificationGate = None
from .models import FleetPlan, TaskSpec
from .validation import ValidationReport, compute_ready_tasks, validate_plan
from .safe_rendering import RUNTIME_ERROR, safe_repr, safe_repr_list, safe_text
try:
    from .scheduler import LeaseScheduler
    from .parallel import BoundedParallelExecutor, TaskResult
except ImportError:  # pragma: no cover - V1-only installations
    LeaseScheduler = None
    BoundedParallelExecutor = None
    TaskResult = None

# V2 canonical hashing is shared with FleetRunStore/checkpoint producers.  Keep
# this import additive so the V1 orchestrator remains importable in reduced
# installations where contracts is unavailable.
try:
    from .contracts import V2_SCHEMA_VERSION as V2_PLAN_SCHEMA_VERSION, plan_hash as _contract_plan_hash
    from .contracts import parse_agent_report_v2
except ImportError:  # pragma: no cover - compatibility with V1-only installs
    V2_PLAN_SCHEMA_VERSION = "pd-fleet-plan:v2"
    _contract_plan_hash = None
    parse_agent_report_v2 = None


class OrchestratorError(ValueError):
    """Erro de contrato ou de execução do orchestrator."""


_REPORT_URL_RE = re.compile(r"(?i)(?:https?|ftp|wss?)://[^\s\"'<>]+")
# Match the complete path, including its final component.  Keep this separate
# from URL redaction (URLs are removed first) and support POSIX, drive-letter,
# UNC and WSL forms without treating ``\\s`` as a literal backslash/s.
_REPORT_PATH_RE = re.compile(
    r'''(?<![\w.])(?:[A-Za-z]:[\\/][^\s"'<>;,]+|/[^\s"'<>;,]+|\\\\[^\s"'<>;,]+)'''
)
_REPORT_SECRET_RE = re.compile(r"(?i)\b(?:bearer\s+\S+|sk-[a-z0-9_-]+)")
_REPORT_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![a-z0-9])([a-z][a-z0-9_.-]{1,80})\s*[:=]\s*([^\s,;]+)"
)
_SENSITIVE_KEYS = ("secret", "token", "password", "credential", "apikey",
                   "accesskey", "privatekey", "authorization", "bearer")

_V2_KEY_ALIASES = {"schemaVersion": "schema_version", "planHash": "plan_hash",
                  "runId": "run_id", "taskId": "task_id", "agentId": "agent_id",
                  "maxParallel": "max_parallel", "eventSequence": "event_sequence",
                  "checkpointId": "checkpoint_id", "leaseId": "lease_id",
                  "dependsOn": "depends_on", "allowedPaths": "allowed_paths",
                  "acceptanceCriteria": "acceptance_criteria", "validationCommands": "validation_commands",
                  "blockedWhen": "blocked_when", "retryPolicy": "retry_policy",
                  "maxAttempts": "max_attempts", "backoffSeconds": "backoff_seconds",
                  "retryableErrors": "retryable_errors", "agentRole": "agent_role"}

def _strict_copy(value: Any, *, _seen: set[int] | None = None) -> Any:
    """Copy hostile JSON-shaped values without coercing keys or invoking str()."""
    seen = _seen if _seen is not None else set()
    if value is None or type(value) in (str, bool, int): return value
    if type(value) is float:
        if not math.isfinite(value): raise ValueError("non-finite")
        return value
    marker = id(value)
    if marker in seen: raise ValueError("cyclic")
    seen.add(marker)
    try:
        if isinstance(value, Mapping):
            result = {}
            for key, item in value.items():
                if type(key) is not str or not key.strip(): raise ValueError("invalid key")
                result[key] = _strict_copy(item, _seen=seen)
            return result
        if isinstance(value, (list, tuple)): return [_strict_copy(x, _seen=seen) for x in value]
        raise ValueError("non-json")
    finally: seen.discard(marker)

def _runtime_aliases(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            normalized = _V2_KEY_ALIASES.get(key, key)
            converted = _runtime_aliases(item)
            if normalized in result and result[normalized] != converted: raise ValueError("conflicting aliases")
            result[normalized] = converted
        return result
    if isinstance(value, list): return [_runtime_aliases(v) for v in value]
    return value


def _sanitize_text(value: Any, default: str | None) -> str | None:
    """Make untrusted dispatch text safe for reports and persisted callbacks."""
    if value is None:
        return default
    try:
        text = value if type(value) is str else default
        if text is None:
            return default
    except Exception:
        return default
    text = _REPORT_URL_RE.sub("[redacted-url]", text)
    text = _REPORT_PATH_RE.sub("[redacted-path]", text)
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


@dataclass(frozen=True)
class ReconciliationResult:
    """Sanitized V2 pre-dispatch decision; it never mutates supplied snapshots."""
    valid: bool
    issues: tuple[dict[str, Any], ...] = ()
    events: tuple[dict[str, Any], ...] = ()

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(item["reason"] for item in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "issues": deepcopy(list(self.issues)),
                "events": deepcopy(list(self.events)), "reasons": list(self.reasons)}


class FleetOrchestrator:
    """Executa tasks de um plano em waves, sem efeitos externos implícitos."""

    def __init__(self, plan: FleetPlan | Mapping[str, Any], *, dispatcher: Any = None,
                 hooks: Any = None, max_parallel: int = 1,
                 timeout_seconds: float | None = None, clock: Callable[[], float] | None = None,
                 dry_run: bool = False, checkpoint: Checkpoint | Mapping[str, Any] | None = None,
                 gates: Mapping[str, Any] | None = None, context: Mapping[str, Any] | None = None,
                 input_values: Mapping[str, Any] | None = None,
                 sleeper: Callable[[float], None] | None = None,
                 feature: str | None = None, created_at: str | None = None,
                 reconciliation_context: Mapping[str, Any] | None = None,
                 scheduler: Any = None, store: Any = None, executor: Any = None,
                 adapter: Any = None, run_id: str | None = None,
                 run_owner: str | None = None) -> None:
        self._canonical_plan: Mapping[str, Any] | None = None
        if isinstance(plan, FleetPlan):
            self.plan = plan
        elif isinstance(plan, Mapping):
            try:
                candidate = _strict_copy(plan)
                runtime_plan = _runtime_aliases(candidate)
            except Exception as exc:
                raise OrchestratorError("plano inválido") from exc
            if candidate.get("schema_version", candidate.get("schemaVersion")) == V2_PLAN_SCHEMA_VERSION:
                # Hash the untouched canonical V2 input; aliases are runtime-only.
                self._canonical_plan = candidate
                runtime_plan["schema_version"] = "1"
                # V2 run metadata is not part of the legacy FleetPlan model.
                runtime_plan.pop("run_id", None)
            try:
                self.plan = FleetPlan.from_dict(runtime_plan)
            except Exception as exc:
                raise OrchestratorError("plano inválido") from exc
        else:
            raise OrchestratorError("plano inválido")
        # Validate before resume or any lifecycle mutation.
        self.validation = validate_plan(self.plan)
        try:
            self._v2_context = deepcopy(reconciliation_context) if reconciliation_context is not None else None
        except Exception:
            # Reconciliation is fail-closed and must sanitize malformed input,
            # not leak a raw deepcopy/type exception from construction.
            self._v2_context = reconciliation_context
        # Ordinary V1 ``context=`` is runtime input, not reconciliation state.
        # V2 reconciliation is opt-in through the explicit keyword above.
        self._reconciliation = self.reconcile(self._v2_context) if self._v2_context is not None else None
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
        if context is not None and not isinstance(context, Mapping):
            raise OrchestratorError("context deve ser um objeto")
        if input_values is not None and not isinstance(input_values, Mapping):
            raise OrchestratorError("input_values deve ser um objeto")
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
        self._v2_execution = self._canonical_plan is not None
        self._committed_attempts: set[tuple[str, int]] = set()
        # These are deliberately opt-in seams.  Leaving them unset preserves
        # the V1 serial dispatcher byte-for-byte and avoids importing/creating
        # durable V2 components for legacy callers.
        self.scheduler = scheduler
        self.store = store
        self.executor = executor
        self.adapter = adapter
        self.run_id = run_id
        self.run_owner = run_owner
        self._resume()

    @classmethod
    def load(cls, plan: FleetPlan | Mapping[str, Any], **kwargs: Any) -> "FleetOrchestrator":
        """Alias explícito para carregar um FleetPlan sem executar."""
        return cls(plan, **kwargs)

    @staticmethod
    def _plan_digest(plan: Any) -> str:
        """Return the same canonical V2 digest used by durable stores."""
        canonical = getattr(plan, "_canonical_plan", None)
        model = getattr(plan, "plan", plan)
        payload = deepcopy(canonical if canonical is not None else model.to_dict())
        payload["schema_version"] = V2_PLAN_SCHEMA_VERSION
        if _contract_plan_hash is not None:
            try:
                return _contract_plan_hash(payload)
            except Exception as exc:
                raise OrchestratorError("hash_contract_error") from exc
        raise OrchestratorError("contrato V2 de hash indisponível")

    def reconcile(self, context: Mapping[str, Any] | None = None) -> ReconciliationResult:
        """Fail-closed V2 state reconciliation, deterministic and side-effect free."""
        if context is None:
            return ReconciliationResult(True)
        issues: list[dict[str, Any]] = []
        def add(code: str, reason: str, task_id: Any = None) -> None:
            item = {"code": code, "reason": reason}
            if task_id is not None: item["task_id"] = str(task_id)
            issues.append(item)
        if not isinstance(context, Mapping):
            add("context_invalid", "incompatible reconciliation context")
        if isinstance(context, Mapping):
            # Strict V2 envelope gate: never stringify, sort, or deepcopy hostile keys.
            try:
                raw_strict = _strict_copy(context)
            except Exception:
                raw_strict = None
                add("context_invalid", "incompatible reconciliation context")
            if raw_strict is not None:
                for name in ("plan_hash", "run_id", "generation", "owner", "checkpoint", "leases", "events"):
                    if name not in raw_strict: add(f"missing_{name}", f"missing {name}")
                if type(raw_strict.get("plan_hash")) is not str or not raw_strict.get("plan_hash", "").strip(): add("plan_hash_invalid", "invalid plan hash")
                try:
                    expected_strict_hash = self._plan_digest(self)
                    if type(raw_strict.get("plan_hash")) is str and raw_strict.get("plan_hash") != expected_strict_hash: add("plan_hash_drift", "plan hash drift")
                except Exception:
                    add("hash_contract_error", "canonical hash unavailable")
                if type(raw_strict.get("run_id")) is not str or not raw_strict.get("run_id", "").strip(): add("run_id_invalid", "invalid run id")
                if type(raw_strict.get("generation")) is not int or raw_strict.get("generation", -1) < 0: add("generation_invalid", "invalid generation")
                if "expected_generation" in raw_strict and (type(raw_strict.get("expected_generation")) is not int or raw_strict.get("generation") != raw_strict.get("expected_generation")): add("stale_generation", "stale generation")
                if "owner" not in raw_strict:
                    pass  # missing_owner above is the canonical envelope error
                elif type(raw_strict["owner"]) is not str or not raw_strict["owner"].strip():
                    add("owner_invalid", "invalid owner")
                if "expected_owner" in raw_strict and raw_strict.get("owner") != raw_strict.get("expected_owner"): add("owner_mismatch", "owner mismatch")
                if "schema_version" in raw_strict and raw_strict.get("schema_version") not in (None, 1, "1", "pd-fleet-checkpoint:v2"): add("schema_mismatch", "incompatible schema")
                if "expected_run_id" in raw_strict and (type(raw_strict["expected_run_id"]) is not str or not raw_strict["expected_run_id"].strip()): add("run_id_invalid", "invalid run id")
                elif "expected_run_id" in raw_strict and raw_strict.get("run_id") != raw_strict.get("expected_run_id"): add("run_id_drift", "run id drift")
                leases_strict = raw_strict.get("leases")
                if not isinstance(leases_strict, Mapping): add("leases_invalid", "incompatible leases")
                else:
                    valid_task_ids = {task.id for task in self.plan.tasks}
                    for task_id, lease in leases_strict.items():
                        if type(task_id) is not str or not task_id.strip() or task_id not in valid_task_ids:
                            add("lease_task_mismatch", "lease task is not present in loaded plan", task_id if type(task_id) is str else None)
                            if type(task_id) is not str or not task_id.strip() or not isinstance(lease, Mapping):
                                continue
                        if not isinstance(lease, Mapping): add("stale_lease", "stale lease", task_id); continue
                        lease_shape_valid = (type(lease.get("lease_id")) is str and bool(lease.get("lease_id", "").strip()) and
                                              type(lease.get("owner")) is str and bool(lease.get("owner", "").strip()) and
                                              type(lease.get("generation")) is int and lease.get("generation", -1) >= 0)
                        if not lease_shape_valid: add("stale_lease", "stale lease", task_id)
                        elif "owner" in raw_strict and lease.get("owner") != raw_strict.get("owner"):
                            add("lease_owner_mismatch", "lease owner mismatch", task_id)
                        if lease_shape_valid and lease.get("generation") != raw_strict.get("generation"):
                            add("stale_lease", "stale lease", task_id)
                events_strict = raw_strict.get("events")
                if not isinstance(events_strict, list): add("events_invalid", "incompatible events")
                else:
                    seq_strict = [e.get("sequence", e.get("seq", e.get("event_sequence"))) if isinstance(e, Mapping) else None for e in events_strict]
                    if any(type(n) is not int for n in seq_strict) or seq_strict != list(range(1, len(seq_strict) + 1)): add("event_sequence_invalid", "duplicate or non-contiguous event sequence")
                cp_strict = raw_strict.get("checkpoint")
                cp_ok = False
                if isinstance(cp_strict, Mapping) and cp_strict.get("schema_version") == "pd-fleet-checkpoint:v2":
                    cp_ok = CheckpointV2Store is not None and CheckpointV2Store._valid(cp_strict, raw_strict.get("run_id"), raw_strict.get("plan_hash"))
                elif isinstance(cp_strict, Mapping) and cp_strict.get("schema_version", 1) in (1, "1"):
                    try: Checkpoint.from_dict(cp_strict); cp_ok = True
                    except Exception: cp_ok = False
                if not cp_ok: add("checkpoint_invalid", "missing or incompatible checkpoint")
                if isinstance(raw_strict.get("snapshots"), Mapping) and isinstance(leases_strict, Mapping):
                    for task_id, snapshot in raw_strict["snapshots"].items():
                        if isinstance(snapshot, Mapping) and snapshot.get("status", snapshot.get("state")) == "running" and (not isinstance(leases_strict.get(task_id), Mapping) or not leases_strict[task_id].get("lease_id")): add("orphan_running_task", "orphaned running task", task_id if type(task_id) is str else None)
                if issues:
                    issues.sort(key=lambda x: (x["code"], x.get("task_id", ""), x["reason"]))
                    safe = tuple(_sanitize_payload(x) for x in issues)
                    event = {"type": "reconciliation", "status": "blocked", "reason": issues[0]["reason"]}
                    return ReconciliationResult(False, safe, (_sanitize_payload(event),))
        else:
            try:
                raw = deepcopy(dict(context))
            except Exception:
                raw = {}
                add("context_invalid", "incompatible reconciliation context")
            if raw:
                try:
                    try:
                        expected_hash = self._plan_digest(self)
                    except OrchestratorError:
                        expected_hash = None
                        add("hash_contract_error", "canonical hash unavailable")
                    if "plan_hash" not in raw or (type(raw.get("plan_hash")) is not str or raw["plan_hash"] != expected_hash):
                        add("plan_hash_drift", "plan hash drift")
                    if "generation" in raw and "expected_generation" in raw:
                        if type(raw["generation"]) is not int or type(raw["expected_generation"]) is not int or raw["generation"] != raw["expected_generation"]:
                            add("stale_generation", "stale generation")
                    if "owner" in raw and not isinstance(raw["owner"], str): add("owner_mismatch", "owner mismatch")
                    if "expected_owner" in raw and raw.get("owner") != raw.get("expected_owner"): add("owner_mismatch", "owner mismatch")
                    if "run_id" in raw or "expected_run_id" in raw:
                        actual_run, expected_run = raw.get("run_id"), raw.get("expected_run_id")
                        if (type(actual_run) is not str or not actual_run.strip() or
                                type(expected_run) is not str or not expected_run.strip()):
                            add("run_id_invalid", "invalid run id")
                        elif actual_run != expected_run:
                            add("run_id_drift", "run id drift")
                    schema = raw.get("schema_version")
                    if schema not in (None, 1, "1", "pd-fleet-checkpoint:v2"): add("schema_mismatch", "incompatible schema")
                    if "expected_schema_version" in raw and schema != raw["expected_schema_version"]: add("schema_mismatch", "incompatible schema")
                    checkpoint_present = "checkpoint" in raw or "snapshot" in raw
                    if not checkpoint_present:
                        add("checkpoint_invalid", "missing or incompatible checkpoint")
                    checkpoint = raw.get("checkpoint", raw.get("snapshot"))
                    if checkpoint_present and not isinstance(checkpoint, Mapping):
                        add("checkpoint_invalid", "missing or incompatible checkpoint")
                    elif checkpoint is not None:
                        cp_schema = checkpoint.get("schema_version", 1)
                        if cp_schema == "pd-fleet-checkpoint:v2":
                            # Durable V2 envelopes have a sealed, exact shape;
                            # validate checksum before trusting their nested body.
                            if ("checksum" in checkpoint and CheckpointV2Store is not None):
                                valid_envelope = CheckpointV2Store._valid(
                                    checkpoint, raw.get("run_id", ""), raw.get("plan_hash"))
                                if not valid_envelope:
                                    add("checkpoint_invalid", "missing or incompatible checkpoint")
                                nested = checkpoint.get("checkpoint")
                            else:
                                nested = checkpoint.get("checkpoint")
                            if not isinstance(nested, Mapping) or nested.get("schema_version", 1) not in (1, "1") or not isinstance(nested.get("lifecycle", {}), Mapping):
                                add("checkpoint_invalid", "missing or incompatible checkpoint")
                            else: checkpoint = nested
                        elif cp_schema not in (1, "1") or not isinstance(checkpoint.get("lifecycle", {}), Mapping):
                            add("checkpoint_invalid", "missing or incompatible checkpoint")
                        if isinstance(checkpoint, Mapping) and isinstance(checkpoint.get("lifecycle", {}), Mapping):
                            valid_ids = {task.id for task in self.plan.tasks}
                            for task_id in sorted(set(checkpoint.get("lifecycle", {})) - valid_ids): add("checkpoint_owner_mismatch", "checkpoint task mismatch", task_id)
                    leases = raw.get("leases", {})
                    if not isinstance(leases, Mapping): add("leases_invalid", "incompatible leases"); leases = {}
                    for task_id, lease in sorted(leases.items(), key=lambda p: str(p[0])):
                        if not isinstance(lease, Mapping): add("stale_lease", "stale lease", task_id); continue
                        if (type(lease.get("lease_id")) is not str or not lease.get("lease_id").strip() or
                                ("generation" in lease and type(lease.get("generation")) is not int) or
                                ("owner" in lease and type(lease.get("owner")) is not str)):
                            add("stale_lease", "stale lease", task_id)
                        if raw.get("generation") is not None and lease.get("generation") not in (None, raw["generation"]): add("stale_lease", "stale lease", task_id)
                        if raw.get("owner") and lease.get("owner") not in (None, raw["owner"]): add("lease_owner_mismatch", "lease owner mismatch", task_id)
                    events = raw.get("events", [])
                    if not isinstance(events, (list, tuple)): add("events_invalid", "incompatible events")
                    else:
                        seq = [e.get("sequence", e.get("seq", e.get("event_sequence"))) if isinstance(e, Mapping) else None for e in events]
                        valid_seq = all(type(n) is int for n in seq)
                        integer_seq = [n for n in seq if type(n) is int]
                        if seq and (not valid_seq or sorted(integer_seq) != list(range(1, len(seq) + 1))): add("event_sequence_invalid", "duplicate or non-contiguous event sequence")
                    snapshots = raw.get("snapshots", raw.get("persisted", raw.get("persisted_run", {})))
                    if isinstance(snapshots, Mapping):
                        for task_id, snapshot in sorted(snapshots.items(), key=lambda p: str(p[0])):
                            if isinstance(snapshot, Mapping) and snapshot.get("status", snapshot.get("state")) == "running" and (not isinstance(leases.get(task_id), Mapping) or not leases[task_id].get("lease_id")): add("orphan_running_task", "orphaned running task", task_id)
                except OrchestratorError:
                    raise
                except (TypeError, ValueError, RecursionError, OverflowError):
                    add("context_invalid", "incompatible reconciliation context")
        issues.sort(key=lambda x: (x["code"], x.get("task_id", ""), x["reason"]))
        safe = tuple(_sanitize_payload(x) for x in issues)
        event = {"type": "reconciliation", "status": "blocked" if issues else "valid", "reason": issues[0]["reason"] if issues else "reconciliation valid"}
        return ReconciliationResult(not issues, safe, (_sanitize_payload(event),))

    def plan_ready(self) -> ValidationReport:
        """Valida integralmente antes de qualquer dispatch ou mutação."""
        return self.validation

    def ready_tasks(self) -> tuple[str, ...]:
        if self._reconciliation is not None and not self._reconciliation.valid:
            return ()
        self.plan_ready()
        by_id = {t.id: t for t in self.plan.tasks}
        completed = {i for i, l in self.lifecycles.items() if l.state in {LifecycleState.COMPLETED, LifecycleState.SKIPPED}}
        skipped = {i for i, l in self.lifecycles.items() if l.state == LifecycleState.SKIPPED}
        passed = {i for i, g in self.gates.items() if self._current_gate_passed(g)}
        return tuple(i for i in compute_ready_tasks(self.plan, completed=completed, skipped=skipped, gates_passed=passed)
                      if self._inputs_available(by_id[i]) and not self._blocked_condition(by_id[i])
                      and self._agent_compatible(by_id[i]))

    def run(self) -> OrchestrationResult:
        if self._v2_integration_enabled:
            # Durable V2 integration is fail-closed without an explicit
            # reconciliation envelope.  Check this before consulting or
            # claiming from the scheduler.
            if self._v2_context is None:
                return OrchestrationResult(
                    {task.id: "blocked" for task in self.plan.tasks},
                    [{"status": "blocked", "reason": "reconciliation context required"}],
                    [], self.validation,
                )
            return self._run_v2_integration()
        if self._reconciliation is not None and not self._reconciliation.valid:
            reason = self._reconciliation.reasons[0] if self._reconciliation.reasons else "reconciliation blocked"
            return OrchestrationResult({task.id: "blocked" for task in self.plan.tasks},
                [{"status": "blocked", "reason": reason, "reconciliation": self._reconciliation.to_dict()}], [], self.validation)
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

    @property
    def _v2_integration_enabled(self) -> bool:
        """Whether the explicitly injected V2 pipeline should be used."""
        return all(x is not None for x in (self.scheduler, self.store,
                                            self.executor, self.adapter,
                                            self.run_id, self.run_owner))

    def _adapter_lease(self, task: Any, token: Mapping[str, Any]) -> dict[str, Any]:
        """Create a safe, detached lease for an injected adapter.

        Scheduler tokens intentionally contain only lease fencing data.  Provider
        adapters additionally need the run owner and the *durable* retry attempt;
        never mutate the scheduler token (or the store snapshot) while adding
        those fields.  A malformed snapshot is a hard failure rather than an
        invitation to guess an attempt/owner.
        """
        if not isinstance(token, Mapping):
            raise OrchestratorError("V2 scheduler returned invalid lease")
        try:
            lease = _strict_copy(token)
            snapshot = self.store.load(self.run_id)
        except Exception as exc:
            raise OrchestratorError("V2 lease enrichment store read failed") from exc
        if not isinstance(lease, dict) or not isinstance(snapshot, Mapping):
            raise OrchestratorError("V2 lease enrichment received malformed state")
        attempts = snapshot.get("attempts")
        if not isinstance(attempts, Mapping):
            raise OrchestratorError("V2 lease enrichment received malformed attempts")
        task_id = getattr(task, "id", None)
        if type(task_id) is not str or not task_id:
            raise OrchestratorError("V2 task has invalid id")
        durable_attempt = attempts.get(task_id, lease.get("attempt", 1))
        if type(durable_attempt) is not int or durable_attempt < 1:
            raise OrchestratorError("V2 lease enrichment received invalid attempt")
        if type(self.run_id) is not str or not self.run_id:
            raise OrchestratorError("V2 run_id is invalid")
        if type(self.run_owner) is not str or not self.run_owner:
            raise OrchestratorError("V2 run owner is invalid")
        lease["run_id"] = self.run_id
        lease["owner"] = self.run_owner
        lease["attempt"] = durable_attempt
        return lease

    def _adapter_run(self, task: Any, token: Mapping[str, Any]) -> Any:
        """Run a worker without granting it a store capability."""
        fn = getattr(self.adapter, "run", None) or getattr(self.adapter, "execute", None)
        if not callable(fn):
            if callable(self.adapter):
                fn = self.adapter
            else:
                raise OrchestratorError("V2 adapter must be callable")
        lease = self._adapter_lease(task, token) if self._v2_integration_enabled else deepcopy(token)
        if self._v2_integration_enabled and callable(getattr(self.store, "use", None)):
            # Claim -> use is the final fence: the original scheduler token is
            # checked under the store lock immediately before the external
            # effect.  The enriched lease is only the adapter-facing copy.
            self.store.use(self.run_id, task.id, token, self.run_owner)
        # Adapters in early V2 tests used either task or task+lease.  Resolve
        # that compatibility before calling: retrying after a TypeError from
        # inside an adapter could repeat a side-effecting invocation.
        task_arg, lease_arg = deepcopy(task), deepcopy(lease)
        try:
            signature = inspect.signature(fn)
        except (TypeError, ValueError):
            signature = None
        if signature is not None:
            try:
                signature.bind(task_arg, lease_arg)
            except TypeError:
                signature.bind(task_arg)
                return fn(task_arg)
        return fn(task_arg, lease_arg)

    @staticmethod
    def _task_result_parts(item: Any) -> tuple[str, str, Any, str | None]:
        task_id = getattr(item, "task_id", item.get("task_id") if isinstance(item, Mapping) else None)
        status = getattr(item, "status", item.get("status") if isinstance(item, Mapping) else "failed")
        value = getattr(item, "value", item.get("value", item.get("report")) if isinstance(item, Mapping) else None)
        error = getattr(item, "error", item.get("error") if isinstance(item, Mapping) else None)
        if not isinstance(task_id, str):
            raise OrchestratorError("V2 executor returned invalid task id")
        return task_id, status if type(status) is str else RUNTIME_ERROR, value, error

    @staticmethod
    def _store_report_projection(parsed: Any, *, status: str | None = None) -> dict[str, Any]:
        """Allow-list a validated AgentReportV2 for FleetRunStore's ABI."""
        source = parsed.to_dict() if hasattr(parsed, "to_dict") else parsed
        if not isinstance(source, Mapping):
            raise ValueError("invalid AgentReport projection")
        report_status = status or source.get("status")
        allowed = ("status", "outputs", "evidence", "tests", "validation",
                   "decision", "started_at", "completed_at", "reason",
                   "error", "blocker")
        projection = {key: _sanitize_payload(source[key]) for key in allowed if key in source}
        projection["status"] = report_status
        return projection

    @staticmethod
    def _failure_projection(task_id: str, attempt: int, reason: Any,
                            *, status: str = "failed", error: Any = None) -> dict[str, Any]:
        safe_reason = _sanitize_text(reason, "terminal execution failure") or "terminal execution failure"
        safe_error = _sanitize_text(error, safe_reason) or safe_reason
        return {"status": status, "evidence": {"task_id": task_id, "attempt": attempt,
                "terminal": True}, "reason": safe_reason, "error": safe_error,
                "started_at": "1970-01-01T00:00:00Z", "completed_at": "1970-01-01T00:00:00Z"}

    def _run_v2_integration(self) -> OrchestrationResult:
        """Execute reconcile -> claim -> bounded run -> sorted CAS commits.

        Workers only receive an immutable task/lease pair.  All store writes
        (including events) happen here, after results are buffered and sorted,
        so completion scheduling cannot influence persisted JSON.
        """
        if self._reconciliation is not None and not self._reconciliation.valid:
            reason = self._reconciliation.reasons[0] if self._reconciliation.reasons else "reconciliation blocked"
            return OrchestrationResult({t.id: "blocked" for t in self.plan.tasks},
                [{"status": "blocked", "reason": reason}], [], self.validation)
        by_id = {task.id: task for task in self.plan.tasks}
        waves: list[tuple[str, ...]] = []
        reports: list[dict[str, Any]] = []
        statuses: dict[str, str] = {task.id: "pending" for task in self.plan.tasks}
        terminal_ids: set[str] = set()
        # A scheduler's ready_ids is the authoritative dependency barrier.  One
        # claim/run/commit cycle is a wave; no child can be claimed mid-wave.
        while True:
            ready = [task_id for task_id in self.scheduler.ready_ids() if task_id not in terminal_ids]
            if not ready:
                break
            tokens = self.scheduler.claim(self.run_owner, limit=min(self.max_parallel, len(ready)))
            if not tokens:
                break
            tokens = sorted(tokens, key=lambda token: token["task_id"])
            task_ids = tuple(token["task_id"] for token in tokens)
            waves.append(task_ids)
            token_by_id = {token["task_id"]: token for token in tokens}
            def worker(task_id: str) -> Any:
                return self._adapter_run(by_id[task_id], token_by_id[task_id])
            raw_results = self.executor.run(task_ids, worker, timeout=self.timeout_seconds)
            results = sorted((self._task_result_parts(item) for item in raw_results), key=lambda p: p[0])
            for task_id, status, value, error in results:
                token = token_by_id.get(task_id)
                if token is None:
                    continue
                parsed_failure_report = None
                if status == "completed":
                    candidate = value.get("report") if isinstance(value, Mapping) and "report" in value else value
                    try:
                        parsed = parse_agent_report_v2(candidate) if parse_agent_report_v2 else None
                        expected_attempt = self.store.load(self.run_id).get("attempts", {}).get(task_id, 1)
                        if (parsed is None or parsed.task_id != task_id or
                                parsed.attempt != expected_attempt):
                            raise ValueError("invalid AgentReport")
                        # The executor's status only describes invocation.  The
                        # validated AgentReport is the authority for the task
                        # lifecycle; a provider may have run successfully while
                        # reporting failed/blocked.
                        parsed_status = parsed.status
                        if parsed_status == "completed":
                            report = self._store_report_projection(parsed, status="completed")
                        elif parsed_status == "blocked":
                            report = self._store_report_projection(parsed, status="blocked")
                            self.store.commit(self.run_id, task_id, token, self.run_owner,
                                              report, status="blocked")
                            statuses[task_id] = "blocked"
                            terminal_ids.add(task_id)
                            reports.append(report)
                            try:
                                self.store.append_event(self.run_id, {"event_id": task_id,
                                    "ordering_key": task_id, "task_id": task_id, "status": "blocked"}, self.run_owner)
                            except Exception as event_exc:
                                warning = _sanitize_text(event_exc, "event persistence failed") or "event persistence failed"
                                reports[-1]["event_persistence_warning"] = warning
                            continue
                        elif parsed_status == "failed":
                            parsed_failure_report = self._store_report_projection(parsed, status="failed")
                            error = (_sanitize_text(getattr(parsed, "error", None), "") or
                                     _sanitize_text(getattr(parsed, "reason", None), "") or
                                     "provider execution failed")
                            status = "failed"
                        else:
                            raise ValueError("invalid AgentReport status")
                        if parsed_status == "completed":
                            # The terminal commit is durable truth.  Event append
                            # is separate best-effort observability: once commit
                            # succeeds, an event failure must never change status,
                            # release/retry the consumed lease, or cause a second
                            # terminal commit.
                            self.store.commit(self.run_id, task_id, token, self.run_owner, report, status="completed")
                            statuses[task_id] = "completed"
                            reports.append(report)
                            try:
                                self.store.append_event(self.run_id, {"event_id": task_id,
                                    "ordering_key": task_id, "task_id": task_id, "status": "completed"}, self.run_owner)
                            except Exception as event_exc:
                                warning = _sanitize_text(event_exc, "event persistence failed") or "event persistence failed"
                                reports[-1]["event_persistence_warning"] = warning
                                try:
                                    self._call("report", {"type": "event_persistence_warning",
                                        "task_id": task_id, "status": "completed", "error": warning})
                                except Exception:
                                    pass
                            continue
                    except Exception:
                        status, error = "failed", RUNTIME_ERROR
                if status != "completed":
                    cancelled = status in {"cancelled", "canceled"}
                    statuses[task_id] = "blocked" if cancelled else "failed"
                    attempt = token.get("attempt", 1)
                    try:
                        attempt = self.store.load(self.run_id).get("attempts", {}).get(task_id, attempt)
                    except Exception:
                        pass
                    policy = by_id[task_id].retry_policy
                    can_retry = (not cancelled and attempt < policy.max_attempts and
                                 (not policy.retryable_errors or
                                  self._retry_error_matches(safe_text(error or status, RUNTIME_ERROR), policy.retryable_errors)))
                    if not can_retry:
                        terminal_status = "blocked" if cancelled else "failed"
                        terminal_report = (parsed_failure_report if terminal_status == "failed" and parsed_failure_report
                                           else self._failure_projection(task_id, attempt,
                                               "cancelled" if cancelled else (error or status),
                                               status=terminal_status, error=error or status))
                        try:
                            self.store.commit(self.run_id, task_id, token, self.run_owner,
                                              terminal_report, status=terminal_status)
                            committed = True
                        except Exception:
                            # Release plus this local fence prevents a broken
                            # commit from becoming an infinite reclaim loop.
                            committed = False
                        if committed:
                            try:
                                self.store.append_event(self.run_id, {"event_id": task_id,
                                    "ordering_key": task_id, "task_id": task_id,
                                    "status": terminal_status}, self.run_owner)
                            except Exception as event_exc:
                                warning = _sanitize_text(event_exc, "event persistence failed") or "event persistence failed"
                                terminal_report["event_persistence_warning"] = warning
                                try:
                                    self._call("report", {"type": "event_persistence_warning",
                                        "task_id": task_id, "status": terminal_status, "error": warning})
                                except Exception:
                                    pass
                        terminal_ids.add(task_id)
                    release = getattr(self.scheduler, "release", None)
                    if callable(release):
                        try: release(token)
                        except Exception: pass
                    if can_retry:
                        statuses[task_id] = "pending"
                    reports.append({"task_id": task_id, "status": statuses[task_id], "error": error or status})
        for task_id in statuses:
            if statuses[task_id] == "pending":
                statuses[task_id] = "blocked"
        reports.sort(key=lambda report: report.get("task_id", ""))
        return OrchestrationResult(statuses, reports, waves, self.validation)

    # Explicit name for callers that want to opt into V2 without relying on
    # the injected-component auto-selection in ``run``.
    def run_v2(self) -> OrchestrationResult:
        if not self._v2_integration_enabled:
            raise OrchestratorError("V2 integration requires scheduler, store, executor, adapter, run_id and run_owner")
        if self._v2_context is None:
            return OrchestrationResult({t.id: "blocked" for t in self.plan.tasks},
                [{"status": "blocked", "reason": "reconciliation context required"}], [], self.validation)
        if not self._reconciliation or not self._reconciliation.valid:
            reason = (self._reconciliation.reasons[0] if self._reconciliation and self._reconciliation.reasons
                      else "reconciliation blocked")
            return OrchestrationResult({t.id: "blocked" for t in self.plan.tasks},
                [{"status": "blocked", "reason": reason}], [], self.validation)
        return self._run_v2_integration()

    execute_v2 = run_v2

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
    def _canonical_gate_scope(value: Any) -> dict[str, Any] | None:
        """Normalize the JSON scope without comparing serialized representations."""
        if not isinstance(value, Mapping):
            return None
        if set(value) != {"schema_version", "plan_hash", "tasks", "waves"}:
            return None
        schema_version = value.get("schema_version")
        plan_hash = value.get("plan_hash")
        tasks = value.get("tasks")
        waves = value.get("waves")
        if (type(schema_version) is not str or type(plan_hash) is not str or
                not isinstance(tasks, (list, tuple)) or not isinstance(waves, (list, tuple))):
            return None
        if any(type(item) is not str for item in tasks) or any(type(item) is not str for item in waves):
            return None
        return {"schema_version": schema_version, "plan_hash": plan_hash,
                "tasks": sorted(tasks), "waves": sorted(set(waves))}

    @staticmethod
    def _gate_passed(gate: Any, *, expected_run: str | None = None,
                     expected_scope: Mapping[str, Any] | None = None) -> bool:
        if gate is None:
            return False
        # Governance gates require an explicit human verification record and a
        # binding to the current run and complete plan scope. This is context
        # binding only; identity remains audit metadata, not authentication.
        if HumanVerificationGate is not None and isinstance(gate, HumanVerificationGate):
            actual_scope = FleetOrchestrator._canonical_gate_scope(gate.scope)
            current_scope = FleetOrchestrator._canonical_gate_scope(expected_scope)
            if (type(expected_run) is not str or not expected_run.strip() or
                    expected_scope is None or current_scope is None or gate.run != expected_run or
                    actual_scope != current_scope):
                return False
            try:
                return bool(gate.allows())
            except Exception:
                return False
        if isinstance(gate, Mapping):
            human_keys = {"owner", "identity", "decision", "scope", "evidence_digest",
                          "artifact_digest", "freshness_window"}
            has_run = "run" in gate or "run_id" in gate
            if human_keys.issubset(gate) and has_run:
                actual_scope = FleetOrchestrator._canonical_gate_scope(gate.get("scope"))
                current_scope = FleetOrchestrator._canonical_gate_scope(expected_scope)
                if (type(expected_run) is not str or not expected_run.strip() or
                        expected_scope is None or current_scope is None or
                        gate.get("run", gate.get("run_id")) != expected_run or
                        actual_scope != current_scope):
                    return False
                try:
                    return bool(HumanVerificationGate.from_dict(gate).allows()) if HumanVerificationGate is not None else False
                except Exception:
                    return False
            gate_type = gate.get("gate_type", gate.get("kind", gate.get("type")))
            if str(gate_type) in {"review", "grill"}:
                return False
        # Automatic contract GateResult (or its mapping form) remains policy
        # evaluated; status alone must never grant access.
        if GateResult is not None and isinstance(gate, GateResult) and gate.gate_type in {"review", "grill"}:
            return False
        if GateResult is not None and (isinstance(gate, GateResult) or
                (isinstance(gate, Mapping) and ("gate_id" in gate or "gate_type" in gate))):
            try:
                return bool(FleetOrchestrator._policy.allows(gate))
            except Exception:
                return False
        return False

    def plan_hash(self) -> str:
        """Return the canonical digest used to bind human gate scope."""
        return self._plan_digest(self)

    def _gate_scope(self) -> dict[str, Any]:
        return {"schema_version": "pd-fleet-gate-scope:v1", "plan_hash": self.plan_hash(),
                "tasks": sorted(task.id for task in self.plan.tasks),
                "waves": sorted({str(task.wave) for task in self.plan.tasks})}

    def _current_gate_passed(self, gate: Any) -> bool:
        return self._gate_passed(gate, expected_run=self.run_id,
                                 expected_scope=self._gate_scope())

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
            gates_passed={i for i,g in self.gates.items() if self._current_gate_passed(g)})
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
                                                         "report_v2": self._v2_execution,
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
            v2_valid = False
            if self._v2_execution:
                candidate = output.get("report") if isinstance(output, Mapping) else None
                try:
                    parsed = parse_agent_report_v2(candidate) if parse_agent_report_v2 else None
                    if parsed is None or parsed.task_id != task.id or parsed.attempt != life.attempt:
                        raise ValueError("incomplete V2 report")
                    output, evidence = parsed.outputs, parsed.evidence
                    if parsed.status == "completed":
                        self._commit_v2_report(task, parsed)
                        status = "completed"
                        v2_valid = True
                    else:
                        status, error, reason = parsed.status, parsed.error or parsed.reason, parsed.reason
                except Exception:
                    if status == "completed":
                        status, error, reason = "failed", "incomplete AgentReportV2", "invalid terminal report"
            if status == "completed":
                normalized = (output, evidence) if v2_valid else self._normalize_completion(task, output, evidence)
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

    def _commit_v2_report(self, task: TaskSpec, report: Any) -> None:
        """Commit exactly once through an injected durable capability.

        The local set only suppresses duplicate calls within this process; it is
        deliberately not treated as persistence.  A V2 completion without a
        durable commit hook is therefore rejected closed.
        """
        key = (task.id, report.attempt)
        if key in self._committed_attempts:
            return
        callback = (getattr(self.hooks, "commit_report", None)
                    if self.hooks is not None else None)
        if not callable(callback) and self.hooks is not None:
            callback = getattr(self.hooks, "commit", None)
        if not callable(callback):
            raise OrchestratorError("V2 exige capacidade de commit durável")
        # The callback/store owns cross-process idempotency.  Preserve the
        # historical one-argument callback contract for V1/V2 integrations.
        callback(deepcopy(report.to_dict()))
        self._committed_attempts.add(key)

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
                return (f"owner incompatível: agente {safe_repr(task.owner)} não existe",
                        {"agent_matching": {"owner": task.owner, "role": task.role,
                                             "capabilities": sorted(required), "candidates": []}})
            if owner not in candidates:
                return (f"owner incompatível: agente {safe_repr(task.owner)} não atende role/capabilities",
                        {"agent_matching": {"owner": owner.id, "role": task.role,
                                             "capabilities": sorted(required),
                                             "missing_capabilities": sorted(required - set(owner.capabilities)),
                                             "agent_role": owner.role}})
            return None
        if candidates:
            return None
        return (f"nenhum agente compatível para role {safe_repr(task.role)} e capabilities {safe_repr_list(sorted(required))}",
                {"agent_matching": {"role": task.role, "capabilities": sorted(required),
                                     "candidates": [agent.id for agent in self.plan.agents]}})

    def _block_wave_stalls(self, wave: str, by_id: Mapping[str, TaskSpec]) -> None:
        # Gate failures are explicit blockers; unresolved dependencies remain pending.
        for task_id in sorted(by_id):
            if self._wave_key(self._wave(task_id, by_id)) != self._wave_key(wave): continue
            life = self.lifecycles[task_id]
            if life.state in {LifecycleState.PENDING, LifecycleState.READY}:
                required = [g for w in self.plan.waves if self._wave_key(str(w.id)) == self._wave_key(wave) for g in w.gates]
                missing = [g for g in required if not self._current_gate_passed(self.gates.get(g))]
                if missing:
                    life.block("gate: " + ", ".join(sorted(missing))); self._notify(life); self._checkpoint()

    def _call(self, name: str, *args: Any) -> None:
        if self.hooks is None: return
        fn = getattr(self.hooks, name, None)
        if callable(fn): fn(*args)

    def _notify(self, life: TaskLifecycle) -> None:
        # V1 historically treated both names as independent lifecycle sinks:
        # when an integration exposed both ``lifecycle`` and ``on_lifecycle``,
        # both were called.  Keep that observable behaviour for legacy plans.
        # V2 may opt into the canonical single-hook behaviour to avoid duplicate
        # side effects while retaining the old-name fallback for V2 adapters.
        if self.hooks is None:
            return
        lifecycle = getattr(self.hooks, "lifecycle", None)
        on_lifecycle = getattr(self.hooks, "on_lifecycle", None)
        if self._v2_execution:
            callback = lifecycle if callable(lifecycle) else on_lifecycle
            if callable(callback):
                callback(life)
            return
        if callable(lifecycle):
            lifecycle(life)
        if callable(on_lifecycle):
            on_lifecycle(life)

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
