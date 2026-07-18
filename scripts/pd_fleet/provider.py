"""Capability-based future provider boundary (default-deny).

Only immutable contracts and a disabled adapter live here.  There is no SDK,
credential handling, dynamic loading, network access, or dispatch path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable
import json
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
# Runtime profiles use a closed vocabulary; ProviderRequest retains its older
# open capability contract for compatibility.
RUNTIME_CAPABILITIES = frozenset({"read", "write", "execute", "network", "provider_network", "shell", "nested_agents"})
# Provider egress is deliberately incompatible with capabilities that can
# mutate state, execute arbitrary work, use ordinary network access, or spawn
# agents. Keep this vocabulary aligned with the runtime envelope boundary.
_PROVIDER_NETWORK_CONFLICTS = frozenset({"write", "execute", "shell", "network", "nested_agents"})


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
_RUNTIME_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")


def _runtime_identifier(value: Any) -> str:
    """Accept only inert, lowercase catalog identifiers at the runtime boundary."""
    if (
        type(value) is not str
        or not _RUNTIME_IDENTIFIER.fullmatch(value)
        or _SENSITIVE.search(value)
        or _URL.search(value)
        or _ABSOLUTE_PATH.search(value)
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _configuration_rejected()
    return value


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


def _runtime_caps(values: Sequence[str] | None) -> tuple[str, ...]:
    result = _caps(values)
    if not set(result).issubset(RUNTIME_CAPABILITIES):
        raise _configuration_rejected()
    return result


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


# Runtime profiles deliberately describe an adapter; they do not discover or
# start one.  ``auth_ref`` is an opaque reference owned by the runtime (for
# example ``env:OPENAI_API_KEY``), never a credential value or a filesystem
# location to be opened by Fleet.
class ReadinessStatus(str, Enum):
    UNKNOWN = "unknown"
    READY = "ready"
    NOT_READY = "not_ready"
    BLOCKED = "blocked"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class CommandMetadata:
    """Non-executable command description for a runtime adapter."""

    executable: str
    arguments: tuple[str, ...] = ()
    working_directory: str | None = None
    transport: str = "local"

    def __post_init__(self) -> None:
        if type(self.executable) is not str or not self.executable or any(
            c in self.executable for c in "\r\n\x00"
        ):
            raise _configuration_rejected()
        if isinstance(self.arguments, (str, bytes, bytearray)):
            raise _configuration_rejected()
        if any(type(arg) is not str or not arg or any(ord(c) < 32 or ord(c) == 127 for c in arg) for arg in self.arguments):
            raise _configuration_rejected()
        if self.working_directory is not None and type(self.working_directory) is not str:
            raise _configuration_rejected()
        if type(self.transport) is not str or not self.transport:
            raise _configuration_rejected()
        object.__setattr__(self, "arguments", tuple(self.arguments))

    def as_dict(self) -> Mapping[str, Any]:
        """Return an immutable public view without command details.

        The dataclass fields remain available to the contract's internal
        consumers, but this public serialization boundary must not become a
        convenient way to recover an executable, its arguments, or a local
        path. Keep the shape (including argument count) while replacing each
        potentially identifying value.
        """
        return _immutable({
            "executable": "[EXECUTABLE REDACTED]",
            "arguments": tuple("[ARGUMENT REDACTED]" for _ in self.arguments),
            "working_directory": (
                None if self.working_directory is None else "[PATH REDACTED]"
            ),
            "transport": self.transport,
        })

    def __repr__(self) -> str:
        return "CommandMetadata(<redacted command metadata>)"

    def __deepcopy__(self, memo: dict[int, Any]) -> "CommandMetadata":
        return self


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """Pure policy input; no policy field can contain an auth value."""

    enabled: bool = False
    allow_nested_subagents: bool = False
    # Provider egress is separate from ordinary network and remains opt-in.
    allow_provider_network: bool = False
    allowed_capabilities: Sequence[str] = ()

    def __post_init__(self) -> None:
        if (type(self.enabled) is not bool or type(self.allow_nested_subagents) is not bool
                or type(self.allow_provider_network) is not bool):
            raise _configuration_rejected()
        object.__setattr__(self, "allowed_capabilities", _runtime_caps(self.allowed_capabilities))
        if self.allow_provider_network and "provider_network" not in self.allowed_capabilities:
            raise _configuration_rejected()
        if self.allow_provider_network and _PROVIDER_NETWORK_CONFLICTS.intersection(self.allowed_capabilities):
            raise _configuration_rejected()


@dataclass(frozen=True, slots=True)
class RuntimeReadiness:
    status: ReadinessStatus | str = ReadinessStatus.UNKNOWN
    reason: str = ""
    checked_by: str = "contract"

    def __post_init__(self) -> None:
        status = self.status.value if isinstance(self.status, ReadinessStatus) else self.status
        if type(status) is not str or status not in {item.value for item in ReadinessStatus}:
            raise _configuration_rejected()
        if type(self.reason) is not str or type(self.checked_by) is not str:
            raise _configuration_rejected()
        object.__setattr__(self, "status", ReadinessStatus(status))

    def __deepcopy__(self, memo: dict[int, Any]) -> "RuntimeReadiness":
        return self

    def __repr__(self) -> str:
        """Keep diagnostic output from disclosing free-form readiness text."""
        return f"RuntimeReadiness(status={getattr(self.status, 'value', self.status)!r})"


@dataclass(frozen=True, slots=True)
class RuntimeProviderProfile:
    """Versioned, serializable description of a runtime provider.

    This object is intentionally not an adapter and has no ``invoke`` method.
    Readiness is supplied by an owner or a test fixture; constructing a profile
    never probes a binary, reads auth, accesses a socket, or starts a process.
    """

    provider_name: str
    runtime_name: str
    auth_ref: str | None = None
    capabilities: Sequence[str] = ()
    command: Any = None
    readiness: RuntimeReadiness = field(default_factory=RuntimeReadiness)
    policy: RuntimePolicy = field(default_factory=RuntimePolicy)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = PROVIDER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.version != PROVIDER_SCHEMA_VERSION:
            raise _configuration_rejected()
        object.__setattr__(self, "provider_name", _runtime_identifier(self.provider_name))
        object.__setattr__(self, "runtime_name", _runtime_identifier(self.runtime_name))
        if self.auth_ref is not None and (
            type(self.auth_ref) is not str
            or not re.fullmatch(r"(?:env|runtime|vault|keyring):[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", self.auth_ref)
        ):
            raise _configuration_rejected()
        object.__setattr__(self, "capabilities", _runtime_caps(self.capabilities))
        if "provider_network" in self.capabilities and _PROVIDER_NETWORK_CONFLICTS.intersection(self.capabilities):
            raise _configuration_rejected()
        if self.command is not None and not isinstance(self.command, CommandMetadata):
            raise _configuration_rejected()
        if self.command is not None:
            command = self.command

            executable = _redact(command.executable)
            if executable == command.executable:
                executable = "[EXECUTABLE REDACTED]"
            arguments = tuple(
                redacted if redacted != argument else "[ARGUMENT REDACTED]"
                for argument in command.arguments
                for redacted in (_redact(argument),)
            )
            object.__setattr__(self, "command", _immutable({
                "executable": executable,
                "arguments": arguments,
                "working_directory": _redact(command.working_directory),
                "transport": command.transport,
            }))
        if not isinstance(self.readiness, RuntimeReadiness) or not isinstance(self.policy, RuntimePolicy):
            raise _configuration_rejected()
        _mapping(self.metadata)
        _validate_metadata(self.metadata)
        object.__setattr__(self, "metadata", _immutable(_redact(self.metadata)))
        # Readiness is derived from immutable declarative inputs. A stale
        # caller-supplied value can never be observed through the profile.
        object.__setattr__(self, "readiness", _derive_readiness(self))

    @property
    def name(self) -> str:
        return self.provider_name

    @property
    def command_metadata(self) -> Mapping[str, Any] | None:
        """Mapping-shaped view for state/report consumers."""
        return self.command


    @property
    def readiness_status(self) -> ReadinessStatus:
        return self.readiness.status if isinstance(self.readiness.status, ReadinessStatus) else ReadinessStatus(self.readiness.status)

    def as_dict(self) -> dict[str, Any]:
        """Return stable redacted data suitable for evidence/state files."""
        return {
            "version": self.version,
            "provider_name": self.provider_name,
            "runtime_name": self.runtime_name,
            "auth_ref": "[AUTH REF]" if self.auth_ref is not None else None,
            "capabilities": list(self.capabilities),
            "command": None if self.command is None else {
                "executable": self.command["executable"],
                "arguments": list(self.command["arguments"]),
                "working_directory": self.command["working_directory"],
                "transport": self.command["transport"],
            },
            "readiness": {
                "status": self.readiness.status.value if isinstance(self.readiness.status, ReadinessStatus) else self.readiness.status,
                "reason": _redact(self.readiness.reason),
                "checked_by": _redact(self.readiness.checked_by),
            },
            "policy": {
                "enabled": self.policy.enabled,
                "allow_nested_subagents": self.policy.allow_nested_subagents,
                "allow_provider_network": self.policy.allow_provider_network,
                "allowed_capabilities": list(self.policy.allowed_capabilities),
            },
            "metadata": _redact(self.metadata),
        }

    def serialize(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    # Familiar names for callers that use serialization protocols.
    to_dict = as_dict
    to_json = serialize

    def __repr__(self) -> str:
        return (f"RuntimeProviderProfile(provider_name={self.provider_name!r}, "
                f"runtime_name={self.runtime_name!r}, auth_ref='[AUTH REF]', "
                f"readiness={getattr(self.readiness.status, 'value', self.readiness.status)!r})")

    def __copy__(self) -> "RuntimeProviderProfile":
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> "RuntimeProviderProfile":
        return self


def _derive_readiness(profile: RuntimeProviderProfile) -> RuntimeReadiness:
    """Pure readiness calculation; deliberately performs no probing."""
    if not profile.policy.enabled:
        return RuntimeReadiness(ReadinessStatus.BLOCKED, "runtime disabled by policy")
    if profile.provider_name == "claude-code" and profile.runtime_name == "claude-code" and not profile.policy.allow_nested_subagents:
        return RuntimeReadiness(ReadinessStatus.BLOCKED, "nested subagents denied by policy")
    if not set(profile.capabilities).issubset(profile.policy.allowed_capabilities):
        return RuntimeReadiness(ReadinessStatus.BLOCKED, "capabilities denied by policy")
    if "provider_network" in profile.capabilities and not profile.policy.allow_provider_network:
        return RuntimeReadiness(ReadinessStatus.BLOCKED, "provider network denied by policy")
    if profile.auth_ref is None:
        return RuntimeReadiness(ReadinessStatus.NOT_READY, "auth reference not configured")
    if profile.command is None:
        return RuntimeReadiness(ReadinessStatus.NOT_READY, "command metadata not configured")
    return RuntimeReadiness(ReadinessStatus.READY, "contract checks passed")


def assess_readiness(profile: RuntimeProviderProfile) -> RuntimeReadiness:
    """Evaluate only declarative gates; never probe or execute a runtime."""
    if not isinstance(profile, RuntimeProviderProfile):
        raise _configuration_rejected()
    return _derive_readiness(profile)


def default_runtime_profiles() -> tuple[RuntimeProviderProfile, ...]:
    """Return safe metadata for the initial runtimes, all disabled by default."""
    runtimes = (("hermes", "openai-codex"), ("codex-cli", "codex-cli"), ("opencode", "opencode-go"), ("claude-code", "claude-code"))
    return tuple(
        RuntimeProviderProfile(provider_name=name, runtime_name=runtime)
        for name, runtime in runtimes
    )


# Public aliases keep the contract name discoverable without introducing a
# second mutable/profile implementation.
RuntimeProfile = RuntimeProviderProfile
ProviderProfile = RuntimeProviderProfile
