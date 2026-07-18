"""Injectable provider dispatch boundary for the Fleet orchestrator.

The boundary composes the declarative router, a caller-owned adapter catalog and
caller-owned sandbox runners.  It does not discover providers, read credentials,
start nested agents, or perform implicit failover.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, cast

from .provider import RuntimeProviderProfile
from .provider_routing import (
    AuditReason, ProviderAuditEvent, ProviderRoutePolicy, ProviderRouteResult,
    RouteStatus, profile_id, route_provider,
)
from .runtime_adapter import (
    RuntimeAdapter, RuntimeErrorCode, RuntimeResult, RuntimeStatus,
    RuntimeTaskEnvelope,
)


class DispatchError(ValueError):
    """Invalid dispatch wiring or envelope; messages contain safe codes only."""


class DispatchConfigurationError(DispatchError):
    pass


class DispatchStatus(str, Enum):
    OK = "ok"
    BLOCKED = "blocked"
    FAILED = "failed"
    NO_PROVIDER = "no_provider"


class DispatchAuditReason(str, Enum):
    ROUTE_BLOCKED = "route_blocked"
    PROVIDER_EXECUTED = "provider_executed"
    PROVIDER_FAILED = "provider_failed"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    ADAPTER_MISSING = "adapter_missing"
    RUNNER_MISSING = "runner_missing"
    DISPATCH_ERROR = "dispatch_error"


@dataclass(frozen=True, slots=True)
class DispatchAuditEvent:
    """Safe, append-only dispatch evidence (never output, argv, paths or errors)."""
    task_id: str
    run_id: str
    provider_id: str | None
    status: DispatchStatus | str
    reason: DispatchAuditReason | str

    def __post_init__(self) -> None:
        status = self.status.value if isinstance(self.status, DispatchStatus) else self.status
        reason = self.reason.value if isinstance(self.reason, DispatchAuditReason) else self.reason
        if type(self.task_id) is not str or type(self.run_id) is not str:
            raise DispatchConfigurationError("invalid_identity")
        if type(status) is not str or status not in {x.value for x in DispatchStatus}:
            raise DispatchConfigurationError("invalid_status")
        if type(reason) is not str or reason not in {x.value for x in DispatchAuditReason}:
            raise DispatchConfigurationError("invalid_reason")
        if self.provider_id is not None and (type(self.provider_id) is not str or not self.provider_id):
            raise DispatchConfigurationError("invalid_provider")
        object.__setattr__(self, "status", DispatchStatus(status))
        object.__setattr__(self, "reason", reason)

    def as_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "run_id": self.run_id,
                "provider_id": self.provider_id, "status": getattr(self.status, "value", self.status),
                "reason": self.reason}


@dataclass(frozen=True, slots=True)
class ProviderDispatchResult:
    status: DispatchStatus
    route: ProviderRouteResult
    runtime: RuntimeResult | None
    audit: DispatchAuditEvent

    @property
    def selected(self) -> RuntimeProviderProfile | None:
        return self.route.selected

    @property
    def output(self) -> str:
        return "" if self.runtime is None else self.runtime.output

    @property
    def runtime_result(self) -> RuntimeResult | None:
        return self.runtime

    @property
    def route_audit(self) -> ProviderAuditEvent:
        return self.route.audit


class ProviderDispatchBoundary:
    """Route and execute exactly one trusted adapter through one injected runner."""

    def __init__(self, *, catalog: Iterable[RuntimeProviderProfile],
                 adapters: Mapping[str, RuntimeAdapter],
                 runners: Mapping[str, Any],
                 router=route_provider) -> None:
        if not isinstance(adapters, Mapping) or not isinstance(runners, Mapping):
            raise DispatchConfigurationError("invalid_dependencies")
        self._catalog = tuple(catalog)
        if any(not isinstance(p, RuntimeProviderProfile) for p in self._catalog):
            raise DispatchConfigurationError("invalid_catalog")
        self._adapters = dict(adapters)
        self._runners = dict(runners)
        if not callable(router):
            raise DispatchConfigurationError("invalid_router")
        self._router = router

    def dispatch(self, envelope: RuntimeTaskEnvelope, policy: ProviderRoutePolicy,
                 *, run_id: str) -> ProviderDispatchResult:
        if not isinstance(envelope, RuntimeTaskEnvelope):
            raise DispatchConfigurationError("invalid_envelope")
        if type(run_id) is not str or not run_id:
            raise DispatchConfigurationError("invalid_identity")
        route = cast(ProviderRouteResult, self._router(envelope.task_id, run_id, policy, self._catalog))
        selected = route.selected
        if route.status is RouteStatus.NO_PROVIDER:
            audit = DispatchAuditEvent(envelope.task_id, run_id, None,
                                       DispatchStatus.NO_PROVIDER,
                                       DispatchAuditReason.PROVIDER_NOT_CONFIGURED)
            return ProviderDispatchResult(DispatchStatus.NO_PROVIDER, route, None, audit)
        if selected is None:
            audit = DispatchAuditEvent(envelope.task_id, run_id, None,
                                       DispatchStatus.BLOCKED,
                                       DispatchAuditReason.ROUTE_BLOCKED)
            return ProviderDispatchResult(DispatchStatus.BLOCKED, route, None, audit)

        identity = profile_id(selected)
        adapter = self._adapters.get(identity)
        if adapter is None:
            audit = DispatchAuditEvent(envelope.task_id, run_id, identity,
                                       DispatchStatus.BLOCKED, DispatchAuditReason.ADAPTER_MISSING)
            return ProviderDispatchResult(DispatchStatus.BLOCKED, route, None, audit)
        if not isinstance(adapter, RuntimeAdapter):
            raise DispatchConfigurationError("invalid_adapter")
        if getattr(adapter, "profile", None) != selected:
            raise DispatchConfigurationError("adapter_profile_mismatch")
        runner = self._runners.get(identity)
        if runner is None:
            audit = DispatchAuditEvent(envelope.task_id, run_id, identity,
                                       DispatchStatus.BLOCKED, DispatchAuditReason.RUNNER_MISSING)
            return ProviderDispatchResult(DispatchStatus.BLOCKED, route, None, audit)
        try:
            runtime = adapter.execute(envelope, runner=runner)
        except Exception as exc:
            # Do not expose exception text and, importantly, never try another adapter.
            runtime = RuntimeResult(RuntimeStatus.FAILED, RuntimeErrorCode.RUNNER_ERROR,
                                    metadata={"exception": type(exc).__name__})
        if not isinstance(runtime, RuntimeResult):
            raise DispatchConfigurationError("adapter_result_invalid")
        ok = runtime.status is RuntimeStatus.OK
        status = DispatchStatus.OK if ok else DispatchStatus.FAILED
        reason = DispatchAuditReason.PROVIDER_EXECUTED if ok else DispatchAuditReason.PROVIDER_FAILED
        audit = DispatchAuditEvent(envelope.task_id, run_id, identity, status, reason)
        return ProviderDispatchResult(status, route, runtime, audit)

    __call__ = dispatch


def dispatch_provider(envelope: RuntimeTaskEnvelope, policy: ProviderRoutePolicy,
                      catalog: Iterable[RuntimeProviderProfile],
                      adapters: Mapping[str, RuntimeAdapter],
                      runners: Mapping[str, Any], *, run_id: str,
                      router=route_provider) -> ProviderDispatchResult:
    """Functional convenience API around :class:`ProviderDispatchBoundary`."""
    return ProviderDispatchBoundary(catalog=catalog, adapters=adapters,
                                    runners=runners, router=router).dispatch(
                                        envelope, policy, run_id=run_id)


ProviderDispatch = ProviderDispatchBoundary
DispatchResult = ProviderDispatchResult