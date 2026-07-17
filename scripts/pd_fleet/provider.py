"""Capability-based future provider boundary (default-deny).

Only immutable contracts and a disabled adapter live here.  There is no SDK,
credential handling, dynamic loading, network access, or dispatch path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable
import re

PROVIDER_SCHEMA_VERSION = "pd-provider:v1"
EXTERNAL_PROVIDERS_ENABLED = False
DISABLED_AUDIT_REASON = "external providers disabled by policy"


class ProviderError(ValueError):
    """Stable base error for boundary violations."""


class ProviderDisabledError(ProviderError):
    """The selected provider is intentionally unavailable."""


class ProviderCapabilityError(ProviderError):
    """Requested capabilities exceed policy."""


class ProviderConfigurationError(ProviderError):
    """Unsafe or unsupported provider configuration."""


class ProviderStatus(str, Enum):
    DISABLED = "disabled"
    OK = "ok"
    ERROR = "error"


_ALLOWED_STATUS = frozenset(item.value for item in ProviderStatus)


def _configuration_rejected() -> ProviderConfigurationError:
    return ProviderConfigurationError("provider configuration rejected")


def _immutable(value: Any) -> Any:
    """Copy supported data into immutable containers; never retain user objects."""
    if callable(value):
        raise _configuration_rejected()
    if isinstance(value, Mapping):
        # Keys cross the boundary as data too. Validate their exact type before
        # any redaction/stringification can invoke user-defined behavior.
        if any(type(key) is not str for key in value):
            raise _configuration_rejected()
        return MappingProxyType({key: _immutable(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_immutable(item) for item in value)
    if type(value) in (str, int, float, bool) or value is None:
        return value
    raise _configuration_rejected()


_SENSITIVE = re.compile(
    r"(?i)(credential|secret|token|password|api[_ -]?key|access[_ -]?(key|token)|private[_ -]?key|authorization|bearer)"
)
_URL = re.compile(r"(?i)(?:https?|ftp|wss?)://[^\s\"'<>]+")
# Keep path redaction whole-value and cross-platform. In particular, UNC and
# home-relative paths must not leave a username or filename suffix behind.
_ABSOLUTE_PATH = re.compile(
    r'''(?<![\w.])(?:~[\\/][^ \t\n\r\f\v\"'<>;,]*|/[^ \t\n\r\f\v\"'<>;,]+|[A-Za-z]:[\\/][^ \t\n\r\f\v\"'<>;,]*|\\\\[^ \t\n\r\f\v\"'<>;,]+)'''
)


def _redact(value: Any, *, key: str = "") -> Any:
    if _SENSITIVE.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        if any(type(k) is not str for k in value):
            raise _configuration_rejected()
        return {k: _redact(v, key=k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _ABSOLUTE_PATH.sub("[PATH REDACTED]", _URL.sub("[URL REDACTED]", value))
    return value


def _validate_injection(value: Any) -> None:
    if callable(value):
        raise _configuration_rejected()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                raise _configuration_rejected()
            if _SENSITIVE.search(key):
                raise _configuration_rejected()
            _validate_injection(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_injection(item)


def _validate_metadata(value: Any) -> None:
    if callable(value):
        raise _configuration_rejected()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                raise _configuration_rejected()
            _validate_metadata(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_metadata(item)


def _caps(values: Sequence[str] | None) -> tuple[str, ...]:
    if values is None or isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise _configuration_rejected()
    if any(type(item) is not str or not item for item in values):
        raise _configuration_rejected()
    return tuple(sorted(set(values)))


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _configuration_rejected()
    return value


def _audit_reason(value: Any) -> str:
    # Stable enum-like reason prevents URLs, paths, and secrets being persisted.
    if type(value) is not str or value != DISABLED_AUDIT_REASON:
        raise _configuration_rejected()
    return value


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    role: str
    capabilities: tuple[str, ...] = ()
    owner: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)
    version: str = PROVIDER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.version != PROVIDER_SCHEMA_VERSION or type(self.role) is not str or not self.role:
            raise _configuration_rejected()
        object.__setattr__(self, "capabilities", _caps(self.capabilities))
        if type(self.owner) is not str:
            raise _configuration_rejected()
        _mapping(self.payload)
        _validate_injection(self.payload)
        object.__setattr__(self, "payload", _immutable(self.payload))


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    status: ProviderStatus | str
    provider_name: str
    audit_reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = PROVIDER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.version != PROVIDER_SCHEMA_VERSION:
            raise _configuration_rejected()
        status = self.status.value if isinstance(self.status, ProviderStatus) else self.status
        if type(status) is not str or status not in _ALLOWED_STATUS:
            raise _configuration_rejected()
        if type(self.provider_name) is not str or not self.provider_name:
            raise _configuration_rejected()
        _audit_reason(self.audit_reason)
        _mapping(self.metadata)
        _validate_metadata(self.metadata)
        object.__setattr__(self, "status", ProviderStatus(status))
        object.__setattr__(self, "metadata", _immutable(_redact(self.metadata)))

    @property
    def provider(self) -> str:
        """Compatibility alias for the explicitly named provider_name field."""
        return self.provider_name


@runtime_checkable
class ProviderAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> tuple[str, ...]: ...

    def invoke(self, request: ProviderRequest) -> ProviderResponse: ...


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    allowed_provider_names: Sequence[str] = ("disabled",)
    capabilities: Sequence[str] = ()
    audit_reason: str = DISABLED_AUDIT_REASON

    def __post_init__(self) -> None:
        names = self.allowed_provider_names
        if isinstance(names, (str, bytes, bytearray)) or not isinstance(names, Sequence):
            raise _configuration_rejected()
        if any(type(name) is not str or not name for name in names):
            raise _configuration_rejected()
        object.__setattr__(self, "allowed_provider_names", tuple(sorted(set(names))))
        object.__setattr__(self, "capabilities", _caps(self.capabilities))
        _audit_reason(self.audit_reason)


@dataclass(frozen=True, slots=True)
class DisabledProvider:
    audit_reason: str = DISABLED_AUDIT_REASON
    metadata: Mapping[str, Any] = field(default_factory=dict)
    name: str = "disabled"
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _audit_reason(self.audit_reason)
        if type(self.name) is not str or self.name != "disabled":
            raise _configuration_rejected()
        _mapping(self.metadata)
        _validate_metadata(self.metadata)
        object.__setattr__(self, "metadata", _immutable(_redact(self.metadata)))
        object.__setattr__(self, "capabilities", ())

    def invoke(self, request: ProviderRequest) -> ProviderResponse:
        if not isinstance(request, ProviderRequest):
            raise _configuration_rejected()
        raise ProviderDisabledError("provider disabled: external providers disabled by policy")


def create_provider(
    provider_name: str = "disabled",
    *,
    required_capabilities: Sequence[str] = (),
    policy: ProviderPolicy | None = None,
    credentials: Any = None,
    network: Any = None,
    metadata: Mapping[str, Any] | None = None,
) -> ProviderAdapter:
    """Return only the disabled adapter; external construction is impossible."""
    if credentials is not None or network is not None:
        raise _configuration_rejected()
    if metadata is not None:
        _mapping(metadata)
        _validate_metadata(metadata)
    if type(provider_name) is not str or not provider_name:
        raise _configuration_rejected()
    if policy is None:
        selected = ProviderPolicy()
    elif isinstance(policy, ProviderPolicy):
        selected = policy
    else:
        raise _configuration_rejected()
    requested = _caps(required_capabilities)
    if not set(requested).issubset(selected.capabilities):
        raise ProviderCapabilityError("provider capability mismatch")
    if provider_name != "disabled":
        raise ProviderConfigurationError("external provider disabled by policy")
    if "disabled" not in selected.allowed_provider_names:
        raise ProviderConfigurationError("provider name not allowed")
    return DisabledProvider(audit_reason=selected.audit_reason, metadata={} if metadata is None else metadata)


provider_factory = create_provider
