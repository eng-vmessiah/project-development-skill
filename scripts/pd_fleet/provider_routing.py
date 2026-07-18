"""Deterministic, explicit provider routing for Fleet.

This module is deliberately a data-only policy boundary: it does not inspect the
host, credentials, environment, network, or filesystem.  A caller supplies the
already-known profile catalog and readiness information.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .provider import ReadinessStatus, RuntimeProviderProfile


class RoutingError(ValueError):
    """Base error for invalid routing contracts."""


class RoutingConfigurationError(RoutingError):
    pass


class RouteStatus(str, Enum):
    SELECTED = "selected"
    BLOCKED = "blocked"
    NO_PROVIDER = "no_provider"


class AuditReason(str, Enum):
    """Closed, non-sensitive reasons emitted by the routing contract."""

    PREFERRED_SELECTED = "preferred_selected"
    EXPLICIT_FALLBACK_SELECTED = "explicit_fallback_selected"
    FALLBACK_NOT_PERMITTED = "fallback_not_permitted"
    NO_ELIGIBLE_PROVIDER = "no_eligible_provider"
    NO_PROVIDER_CONFIGURED = "no_provider_configured"


_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._/-]*\Z")
_SAFE_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SENSITIVE_ID = re.compile(
    r"(?i)(?:credential|secret|token|password|passwd|api[_ -]?key|access[_ -]?(?:key|token)|"
    r"private[_ -]?key|authorization|bearer|prompt)"
)
_AUDIT_REASONS = frozenset(item.value for item in AuditReason)
_FORBIDDEN_CAPABILITIES = frozenset({"shell", "network", "nested_agents"})


def _ids(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise RoutingConfigurationError(f"invalid {field_name}")
    result = tuple(values)
    if any(type(value) is not str or not _SAFE_ID.fullmatch(value) or
           value.startswith(("/", "-")) or "/../" in f"/{value}/" or
           value.endswith("/..") or value.startswith("../") or "//" in value or
           _SENSITIVE_ID.search(value) for value in result):
        raise RoutingConfigurationError(f"invalid {field_name}")
    if len(set(result)) != len(result):
        raise RoutingConfigurationError(f"duplicate {field_name}")
    return result


def _capabilities(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise RoutingConfigurationError("invalid required capabilities")
    result = tuple(values)
    if any(type(value) is not str or not value for value in result):
        raise RoutingConfigurationError("invalid required capabilities")
    if set(result) & _FORBIDDEN_CAPABILITIES:
        raise RoutingConfigurationError("forbidden capability")
    if len(set(result)) != len(result):
        raise RoutingConfigurationError("duplicate required capabilities")
    return tuple(sorted(result))


def profile_id(profile: RuntimeProviderProfile) -> str:
    """Canonical provider/runtime identity (exact matching only)."""
    return f"{profile.provider_name}/{profile.runtime_name}"


@dataclass(frozen=True, slots=True)
class ProviderRoutePolicy:
    preferred_ids: Sequence[str] = ()
    fallback_ids: Sequence[str] = ()
    required_capabilities: Sequence[str] = ()
    allow_fallback: bool = False
    max_candidates: int = 1

    def __post_init__(self) -> None:
        preferred = _ids(self.preferred_ids, "preferred IDs")
        fallback = _ids(self.fallback_ids, "fallback IDs")
        if set(preferred) & set(fallback):
            raise RoutingConfigurationError("duplicate provider ID across preference lists")
        required = _capabilities(self.required_capabilities)
        if type(self.allow_fallback) is not bool or type(self.max_candidates) is not int or self.max_candidates < 1:
            raise RoutingConfigurationError("invalid routing limits")
        object.__setattr__(self, "preferred_ids", preferred)
        object.__setattr__(self, "fallback_ids", fallback)
        object.__setattr__(self, "required_capabilities", required)

    @property
    def ordered_ids(self) -> tuple[str, ...]:
        return tuple(self.preferred_ids) + (tuple(self.fallback_ids) if self.allow_fallback else ())


@dataclass(frozen=True, slots=True)
class ProviderAuditEvent:
    """Append-only redacted evidence of *contract-ready* selection.

    ``READY`` is only a declaration that the supplied profile satisfies this
    policy boundary; it is not operational credential verification.
    """
    task_id: str
    run_id: str
    candidates: tuple[str, ...]
    selected: str | None
    status: RouteStatus | str
    reason: str

    def __post_init__(self) -> None:
        if (type(self.task_id) is not str or type(self.run_id) is not str or
                not _SAFE_SLUG.fullmatch(self.task_id) or
                not _SAFE_SLUG.fullmatch(self.run_id) or
                len(self.task_id) > 128 or len(self.run_id) > 128 or
                _SENSITIVE_ID.search(self.task_id) or _SENSITIVE_ID.search(self.run_id)):
            raise RoutingConfigurationError("invalid audit identity")
        candidates = _ids(self.candidates, "audit candidates")
        selected = self.selected
        if selected is not None:
            _ids((selected,), "audit selected")
            if selected not in candidates:
                raise RoutingConfigurationError("selected audit provider is not a candidate")
        status = self.status.value if isinstance(self.status, RouteStatus) else self.status
        if type(status) is not str or status not in {s.value for s in RouteStatus}:
            raise RoutingConfigurationError("invalid audit status")
        reason = self.reason.value if isinstance(self.reason, AuditReason) else self.reason
        if type(reason) is not str or reason not in _AUDIT_REASONS:
            raise RoutingConfigurationError("invalid audit reason")

        # Keep the audit stream self-consistent: a selected route must identify
        # a candidate and use a selection reason, while non-selected routes
        # must never claim a selected provider.
        compatible_reasons = {
            RouteStatus.SELECTED.value: {
                AuditReason.PREFERRED_SELECTED.value,
                AuditReason.EXPLICIT_FALLBACK_SELECTED.value,
            },
            RouteStatus.BLOCKED.value: {
                AuditReason.FALLBACK_NOT_PERMITTED.value,
                AuditReason.NO_ELIGIBLE_PROVIDER.value,
            },
            RouteStatus.NO_PROVIDER.value: {AuditReason.NO_PROVIDER_CONFIGURED.value},
        }
        if reason not in compatible_reasons[status]:
            raise RoutingConfigurationError("audit reason is incompatible with status")
        if status == RouteStatus.SELECTED.value:
            if selected is None:
                raise RoutingConfigurationError("selected audit provider is required")
        elif selected is not None:
            raise RoutingConfigurationError("non-selected audit status cannot select a provider")
        if not candidates:
            if status != RouteStatus.NO_PROVIDER.value:
                raise RoutingConfigurationError("audit candidates cannot be empty")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "status", RouteStatus(status))
        object.__setattr__(self, "reason", reason)

    def as_dict(self) -> dict[str, Any]:
        return {"candidates": list(self.candidates), "reason": self.reason,
                "run_id": self.run_id, "selected": self.selected,
                "status": getattr(self.status, "value", self.status), "task_id": self.task_id}

    def serialize(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True, slots=True)
class ProviderRouteResult:
    status: RouteStatus
    selected: RuntimeProviderProfile | None
    audit: ProviderAuditEvent


def _catalog_map(catalog: Iterable[RuntimeProviderProfile]) -> dict[str, RuntimeProviderProfile]:
    profiles = tuple(catalog)
    if any(not isinstance(profile, RuntimeProviderProfile) for profile in profiles):
        raise RoutingConfigurationError("catalog contains invalid profile")
    result: dict[str, RuntimeProviderProfile] = {}
    for profile in profiles:
        identity = profile_id(profile)
        if identity in result:
            raise RoutingConfigurationError("duplicate catalog identity")
        result[identity] = profile
    return result


def route_provider(task_id: str, run_id: str, policy: ProviderRoutePolicy,
                   catalog: Iterable[RuntimeProviderProfile]) -> ProviderRouteResult:
    """Select the first eligible exact identity, with no implicit fallback.

    Selection is contract-ready only: readiness is supplied policy evidence, not
    an operational check that credentials work or that a provider was invoked.
    """
    if not isinstance(policy, ProviderRoutePolicy):
        raise RoutingConfigurationError("invalid route policy")
    profiles = _catalog_map(catalog)
    requested = policy.ordered_ids
    configured = tuple(policy.preferred_ids) + tuple(policy.fallback_ids)
    unknown = tuple(identity for identity in configured if identity not in profiles)
    if unknown:
        raise RoutingConfigurationError("unknown provider ID")
    eligible: list[str] = []
    for identity in requested:
        profile = profiles[identity]
        if not profile.policy.enabled or profile.readiness_status is not ReadinessStatus.READY:
            continue
        if profile.auth_ref is None or not set(policy.required_capabilities).issubset(profile.capabilities):
            continue
        if set(profile.capabilities) & _FORBIDDEN_CAPABILITIES:
            raise RoutingConfigurationError("forbidden capability")
        eligible.append(identity)
    selected_id = next((identity for identity in eligible[:policy.max_candidates]), None)
    audit_candidates = tuple(requested) or tuple(policy.fallback_ids)
    if selected_id is not None:
        status, reason, selected = RouteStatus.SELECTED, "preferred_selected" if selected_id in policy.preferred_ids else "explicit_fallback_selected", profiles[selected_id]
    else:
        status, reason, selected = RouteStatus.BLOCKED, "fallback_not_permitted" if not policy.allow_fallback else "no_eligible_provider", None
        if not configured:
            reason = "no_provider_configured"
        selected_id = None
        status = RouteStatus.NO_PROVIDER if not configured else status
    audit = ProviderAuditEvent(task_id, run_id, audit_candidates, selected_id, status, reason)
    return ProviderRouteResult(status, selected, audit)


select_provider = route_provider
route = route_provider
