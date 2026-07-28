"""Injectable provider dispatch boundary for the Fleet orchestrator.

The boundary composes the declarative router, a caller-owned adapter catalog and
caller-owned sandbox runners.  It does not discover providers, read credentials,
start nested agents, or perform implicit failover.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, cast

from .provider import RuntimeProviderProfile
from .provider_routing import (
    AuditReason, ProviderAuditEvent, ProviderRoutePolicy, ProviderRouteResult,
    RouteStatus, profile_id, route_provider,
)
from .runtime_adapter import (
    ALLOWED_CAPABILITIES, ALLOWED_PATHS,
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


def _request_immutable(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise DispatchConfigurationError("invalid_request")
        return MappingProxyType({key: _request_immutable(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_request_immutable(item) for item in value)
    if type(value) in (str, int, float, bool) or value is None:
        return value
    raise DispatchConfigurationError("invalid_request")


def _request_paths(value: Any) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, (tuple, list)):
        raise DispatchConfigurationError("invalid_request")
    values = tuple(value)
    if any(type(path) is not str or not path for path in values):
        raise DispatchConfigurationError("invalid_request")
    paths = tuple(sorted(set(values)))
    for path in paths:
        parts = path.replace("\\\\", "/").split("/")
        if (path.startswith(("/", "\\\\", "~")) or re.match(r"^[A-Za-z]:", path)
                or not parts or parts[0] not in ALLOWED_PATHS or ".." in parts
                or any(ord(char) < 32 or ord(char) == 127 for char in path)):
            raise DispatchConfigurationError("invalid_request")
    return paths


def _request_capabilities(value: Any) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, (tuple, list)):
        raise DispatchConfigurationError("invalid_request")
    values = tuple(value)
    if any(type(capability) is not str or not capability for capability in values):
        raise DispatchConfigurationError("invalid_request")
    capabilities = tuple(sorted(set(values)))
    if (not set(capabilities).issubset(ALLOWED_CAPABILITIES)
            or {"shell", "network", "nested_agents"}.intersection(capabilities)):
        raise DispatchConfigurationError("invalid_request")
    return capabilities


@dataclass(frozen=True, slots=True)
class ProviderDispatchRequest:
    """Provider-independent input; routing must precede envelope construction."""
    task_id: str
    prompt: str
    allowed_paths: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ("read",)
    nested_agents: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (type(self.task_id) is not str or not self.task_id
                or type(self.prompt) is not str or not self.prompt
                or type(self.nested_agents) is not bool or self.nested_agents):
            raise DispatchConfigurationError("invalid_request")
        if not isinstance(self.metadata, Mapping):
            raise DispatchConfigurationError("invalid_request")
        object.__setattr__(self, "allowed_paths", _request_paths(self.allowed_paths))
        object.__setattr__(self, "capabilities", _request_capabilities(self.capabilities))
        object.__setattr__(self, "metadata", _request_immutable(self.metadata))


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

    def _execute(self, request: ProviderDispatchRequest, route: ProviderRouteResult,
                 *, run_id: str) -> ProviderDispatchResult:
        selected = route.selected
        if route.status is RouteStatus.NO_PROVIDER:
            audit = DispatchAuditEvent(request.task_id, run_id, None,
                                       DispatchStatus.NO_PROVIDER,
                                       DispatchAuditReason.PROVIDER_NOT_CONFIGURED)
            return ProviderDispatchResult(DispatchStatus.NO_PROVIDER, route, None, audit)
        if selected is None:
            audit = DispatchAuditEvent(request.task_id, run_id, None,
                                       DispatchStatus.BLOCKED,
                                       DispatchAuditReason.ROUTE_BLOCKED)
            return ProviderDispatchResult(DispatchStatus.BLOCKED, route, None, audit)
        identity = profile_id(selected)
        adapter = self._adapters.get(identity)
        if adapter is None:
            audit = DispatchAuditEvent(request.task_id, run_id, identity,
                                       DispatchStatus.BLOCKED, DispatchAuditReason.ADAPTER_MISSING)
            return ProviderDispatchResult(DispatchStatus.BLOCKED, route, None, audit)
        if not isinstance(adapter, RuntimeAdapter):
            raise DispatchConfigurationError("invalid_adapter")
        if getattr(adapter, "profile", None) != selected:
            raise DispatchConfigurationError("adapter_profile_mismatch")
        runner = self._runners.get(identity)
        if runner is None:
            audit = DispatchAuditEvent(request.task_id, run_id, identity,
                                       DispatchStatus.BLOCKED, DispatchAuditReason.RUNNER_MISSING)
            return ProviderDispatchResult(DispatchStatus.BLOCKED, route, None, audit)
        # This is intentionally constructed only after routing selected a profile.
        envelope = RuntimeTaskEnvelope(request.task_id, request.prompt, selected,
                                       request.allowed_paths, request.capabilities,
                                       request.nested_agents, request.metadata)
        try:
            runtime = adapter.execute(envelope, runner=runner)
        except Exception as exc:
            runtime = RuntimeResult(RuntimeStatus.FAILED, RuntimeErrorCode.RUNNER_ERROR,
                                    metadata={"exception": "[PROVIDER ERROR]"})
        if not isinstance(runtime, RuntimeResult):
            raise DispatchConfigurationError("adapter_result_invalid")
        status = DispatchStatus.OK if runtime.status is RuntimeStatus.OK else DispatchStatus.FAILED
        reason = (DispatchAuditReason.PROVIDER_EXECUTED if status is DispatchStatus.OK
                  else DispatchAuditReason.PROVIDER_FAILED)
        audit = DispatchAuditEvent(request.task_id, run_id, identity, status, reason)
        return ProviderDispatchResult(status, route, runtime, audit)

    def dispatch_request(self, request: ProviderDispatchRequest, policy: ProviderRoutePolicy,
                         *, run_id: str) -> ProviderDispatchResult:
        if not isinstance(request, ProviderDispatchRequest):
            raise DispatchConfigurationError("invalid_request")
        if type(run_id) is not str or not run_id:
            raise DispatchConfigurationError("invalid_identity")
        route = cast(ProviderRouteResult, self._router(request.task_id, run_id, policy, self._catalog))
        return self._execute(request, route, run_id=run_id)

    def dispatch(self, envelope: RuntimeTaskEnvelope, policy: ProviderRoutePolicy,
                 *, run_id: str) -> ProviderDispatchResult:
        """Backward-compatible envelope API; route result owns the effective profile."""
        if not isinstance(envelope, RuntimeTaskEnvelope):
            raise DispatchConfigurationError("invalid_envelope")
        request = ProviderDispatchRequest(envelope.task_id, envelope.prompt,
                                          tuple(envelope.allowed_paths), tuple(envelope.capabilities),
                                          envelope.nested_agents, envelope.metadata)
        return self.dispatch_request(request, policy, run_id=run_id)

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


def dispatch_request(request: ProviderDispatchRequest, policy: ProviderRoutePolicy,
                     catalog: Iterable[RuntimeProviderProfile],
                     adapters: Mapping[str, RuntimeAdapter],
                     runners: Mapping[str, Any], *, run_id: str,
                     router=route_provider) -> ProviderDispatchResult:
    """Functional request-first API; profile selection precedes envelope creation."""
    return ProviderDispatchBoundary(catalog=catalog, adapters=adapters,
                                    runners=runners, router=router).dispatch_request(
                                        request, policy, run_id=run_id)


ProviderDispatch = ProviderDispatchBoundary
DispatchResult = ProviderDispatchResult