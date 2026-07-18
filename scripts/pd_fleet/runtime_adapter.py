"""Pure runtime adapter contracts and command templates.

This module deliberately contains no process, network, environment, or config
access.  Builders return argv data only.  An adapter can execute only when a
trusted sandbox runner is explicitly injected by its caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import re
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .provider import CommandMetadata, RuntimeProviderProfile
from .sandbox import SandboxCapability

RUNTIME_ADAPTER_SCHEMA_VERSION = "pd-runtime-adapter:v1"
ALLOWED_PATHS = frozenset({"workspace", "artifacts", "inputs", "outputs"})
ALLOWED_CAPABILITIES = frozenset({"read", "write", "execute", "network", "provider_network", "shell", "nested_agents"})
_SENSITIVE = re.compile(r"(?i)(secret|token|password|credential|api[_ -]?key|authorization|bearer)")
_PATH = re.compile(r"(?i)(?:https?://[^\s]+|(?:~|/|[A-Za-z]:[\\/]|\\\\)[^\s]+)")
_SECRET_VALUE = re.compile(r"(?i)(?:token|secret|password|api[_ -]?key)\s*[=:]\s*[^\s]+")
_PRODUCTION_DENIED_CAPABILITIES = frozenset({"shell", "network"})
RUNTIME_TIMEOUT_DEFAULT = 10.0
RUNTIME_TIMEOUT_MIN = 1
RUNTIME_TIMEOUT_MAX = 120


class RuntimeAdapterError(ValueError):
    """Stable base error for invalid runtime envelopes."""


class RuntimeConfigurationError(RuntimeAdapterError):
    pass


class RuntimeCapabilityError(RuntimeAdapterError):
    pass


class RuntimeRunnerRequiredError(RuntimeAdapterError):
    pass


class RuntimeStatus(str, Enum):
    OK = "ok"
    DENIED = "denied"
    TIMEOUT = "timeout"
    FAILED = "failed"
    ERROR = "error"
    BLOCKED = "blocked"


class RuntimeErrorCode(str, Enum):
    INVALID_ENVELOPE = "invalid_envelope"
    CAPABILITY_DENIED = "capability_denied"
    PATH_DENIED = "path_denied"
    NESTED_AGENTS_DENIED = "nested_agents_denied"
    RUNNER_REQUIRED = "runner_required"
    RUNNER_ERROR = "runner_error"
    SANDBOX_DENIED = "sandbox_denied"
    SANDBOX_TIMEOUT = "sandbox_timeout"
    SANDBOX_FAILED = "sandbox_failed"
    COMMAND_UNRESOLVED = "command_unresolved"
    CATALOG_INVALID = "catalog_invalid"
    INVALID_TIMEOUT = "invalid_timeout"


def _immutable(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(type(k) is not str for k in value):
            raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
        return MappingProxyType({k: _immutable(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_immutable(v) for v in value)
    if type(value) in (str, int, float, bool) or value is None:
        return value
    raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)


def _slug(value: Any) -> str:
    if type(value) is not str or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
    return value


def _sequence(value: Any, *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
    if any(type(v) is not str or not v for v in value):
        raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
    return tuple(sorted(set(value)))


def _safe_paths(value: Any) -> tuple[str, ...]:
    paths = _sequence(value, field_name="allowed_paths")
    for path in paths:
        if path.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", path):
            raise RuntimeCapabilityError(RuntimeErrorCode.PATH_DENIED.value)
        parts = path.replace("\\", "/").split("/")
        if (not parts or parts[0] not in ALLOWED_PATHS or ".." in parts
                or any(ord(c) < 32 or ord(c) == 127 for c in path)):
            raise RuntimeCapabilityError(RuntimeErrorCode.PATH_DENIED.value)
    return paths


def _redact(value: Any, *, key: str = "") -> Any:
    if type(key) is not str:
        raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
    if _SENSITIVE.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {k: _redact(v, key=k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return _PATH.sub("[PATH REDACTED]", _SECRET_VALUE.sub("[SECRET REDACTED]", value))
    return value


@dataclass(frozen=True, slots=True)
class RuntimeTaskEnvelope:
    """Validated, immutable task boundary passed to a runtime adapter."""

    task_id: str
    prompt: str
    provider_profile: RuntimeProviderProfile
    allowed_paths: Sequence[str] = ()
    capabilities: Sequence[str] = ("read",)
    nested_agents: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = RUNTIME_ADAPTER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.version != RUNTIME_ADAPTER_SCHEMA_VERSION or type(self.task_id) is not str or not self.task_id:
            raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
        if type(self.prompt) is not str or not self.prompt:
            raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
        if not isinstance(self.provider_profile, RuntimeProviderProfile):
            raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
        paths = _safe_paths(self.allowed_paths)
        capabilities = _sequence(self.capabilities, field_name="capabilities")
        if not set(capabilities).issubset(ALLOWED_CAPABILITIES):
            raise RuntimeCapabilityError(RuntimeErrorCode.CAPABILITY_DENIED.value)
        # Ordinary network is never an authority for provider egress. The
        # provider_network capability is separately opt-in and cannot be
        # combined with dangerous execution/agent capabilities.
        if _PRODUCTION_DENIED_CAPABILITIES.intersection(capabilities):
            raise RuntimeCapabilityError(RuntimeErrorCode.CAPABILITY_DENIED.value)
        if "provider_network" in capabilities:
            if not self.provider_profile.policy.allow_provider_network:
                raise RuntimeCapabilityError(RuntimeErrorCode.CAPABILITY_DENIED.value)
            if {"write", "execute", "shell", "nested_agents"}.intersection(capabilities):
                raise RuntimeCapabilityError(RuntimeErrorCode.CAPABILITY_DENIED.value)
        if "nested_agents" in capabilities or self.nested_agents:
            raise RuntimeCapabilityError(RuntimeErrorCode.NESTED_AGENTS_DENIED.value)
        if not set(capabilities).issubset(set(self.provider_profile.capabilities)):
            raise RuntimeCapabilityError(RuntimeErrorCode.CAPABILITY_DENIED.value)
        if not set(capabilities).issubset(set(self.provider_profile.policy.allowed_capabilities)):
            raise RuntimeCapabilityError(RuntimeErrorCode.CAPABILITY_DENIED.value)
        if "nested_agents" in capabilities or self.nested_agents:
            raise RuntimeCapabilityError(RuntimeErrorCode.NESTED_AGENTS_DENIED.value)
        if type(self.nested_agents) is not bool:
            raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
        if not isinstance(self.metadata, Mapping):
            raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
        object.__setattr__(self, "allowed_paths", paths)
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "metadata", _immutable(self.metadata))

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "task_id": self.task_id,
            "prompt": _redact(self.prompt),
            "provider": self.provider_profile.provider_name,
            "runtime": self.provider_profile.runtime_name,
            "allowed_paths": list(self.allowed_paths),
            "capabilities": list(self.capabilities),
            "nested_agents": self.nested_agents,
            "metadata": _redact(self.metadata),
        }

    def serialize(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    to_dict = as_dict
    to_json = serialize


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    status: RuntimeStatus | str
    error_code: RuntimeErrorCode | str | None = None
    output: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        status = self.status.value if isinstance(self.status, RuntimeStatus) else self.status
        if type(status) is not str or status not in {s.value for s in RuntimeStatus}:
            raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
        if self.error_code is not None:
            code = self.error_code.value if isinstance(self.error_code, RuntimeErrorCode) else self.error_code
            if type(code) is not str or code not in {c.value for c in RuntimeErrorCode}:
                raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
            object.__setattr__(self, "error_code", code)
        if type(self.output) is not str or not isinstance(self.metadata, Mapping):
            raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
        object.__setattr__(self, "status", RuntimeStatus(status))
        # Redact at construction so callers cannot observe unsafe runner output
        # before the later serialization boundary.
        object.__setattr__(self, "output", _redact(self.output))
        object.__setattr__(self, "metadata", _immutable(_redact(self.metadata)))

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "error_code": self.error_code,
                "output": _redact(self.output), "metadata": _redact(self.metadata)}

    def serialize(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=True, sort_keys=True,
                          separators=(",", ":"))

    to_dict = as_dict
    to_json = serialize


@runtime_checkable
class SandboxRunner(Protocol):
    network: bool

    def run(self, argv: Sequence[str], *, cwd: str, env: Mapping[str, str],
            timeout: float, output_limits: tuple[int, int]) -> Any: ...


@runtime_checkable
class RuntimeAdapter(Protocol):
    name: str
    profile: RuntimeProviderProfile

    def build_argv(self, envelope: RuntimeTaskEnvelope) -> tuple[str, ...]: ...
    def execute(self, envelope: RuntimeTaskEnvelope, *, runner: SandboxRunner | Any) -> RuntimeResult: ...


def _validate_envelope(envelope: RuntimeTaskEnvelope, profile: RuntimeProviderProfile) -> None:
    if not isinstance(envelope, RuntimeTaskEnvelope) or envelope.provider_profile != profile:
        raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)


def _runtime_timeout(metadata: Mapping[str, Any]) -> float:
    """Return the policy-bounded runner timeout from envelope metadata."""
    if "timeout_seconds" not in metadata:
        return RUNTIME_TIMEOUT_DEFAULT
    value = metadata["timeout_seconds"]
    # bool is an int subclass, but is not a valid timeout input; do not coerce.
    if type(value) is not int or not RUNTIME_TIMEOUT_MIN <= value <= RUNTIME_TIMEOUT_MAX:
        raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_TIMEOUT.value)
    return float(value)


@dataclass(frozen=True, slots=True)
class TemplateRuntimeAdapter:
    name: str
    profile: RuntimeProviderProfile
    template: tuple[str, ...]
    command_metadata: CommandMetadata | None = None

    def __post_init__(self) -> None:
        if self.command_metadata is not None and not isinstance(self.command_metadata, CommandMetadata):
            raise RuntimeConfigurationError(RuntimeErrorCode.COMMAND_UNRESOLVED.value)

    def _trusted_command(self) -> CommandMetadata | None:
        command = self.command_metadata
        if command is None:
            return None
        # Adapter identity is part of the trusted construction seam.
        expected = self.name.split("/", 1)[0]
        if expected != self.profile.provider_name and self.name != self.profile.runtime_name:
            raise RuntimeConfigurationError(RuntimeErrorCode.COMMAND_UNRESOLVED.value)
        return command

    def build_argv(self, envelope: RuntimeTaskEnvelope) -> tuple[str, ...]:
        _validate_envelope(envelope, self.profile)
        try:
            values: dict[str, Any] = {"prompt": envelope.prompt, "task_id": envelope.task_id}
            # Named adapters may bind declarative scalar metadata (never
            # shell-expand it), but timeout_seconds is reserved exclusively for
            # the runner and can never be formatted into argv/configuration.
            values.update({key: value for key, value in envelope.metadata.items()
                           if key != "timeout_seconds" and type(value) in (str, int)
                           and not isinstance(value, bool)})
            argv = tuple(part.format(**values) for part in self.template)
        except (KeyError, IndexError, ValueError) as exc:
            raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value) from exc
        if not argv or any(type(item) is not str or "\x00" in item
                           or any(ord(c) < 32 or ord(c) == 127 for c in item)
                           or re.search(r"[;&|<>$`]|\$\(|&&|\|\|", item)
                           for item in argv):
            raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
        return argv

    def execute(self, envelope: RuntimeTaskEnvelope, *, runner: SandboxRunner | Any = None) -> RuntimeResult:
        _validate_envelope(envelope, self.profile)
        timeout = _runtime_timeout(envelope.metadata)
        if _PRODUCTION_DENIED_CAPABILITIES.intersection(envelope.capabilities):
            raise RuntimeCapabilityError(RuntimeErrorCode.CAPABILITY_DENIED.value)
        if "provider_network" in envelope.capabilities:
            if not self.profile.policy.allow_provider_network:
                return RuntimeResult(RuntimeStatus.DENIED, RuntimeErrorCode.CAPABILITY_DENIED)
            if {"write", "execute", "shell", "nested_agents"}.intersection(envelope.capabilities):
                raise RuntimeCapabilityError(RuntimeErrorCode.CAPABILITY_DENIED.value)
        # A disabled or not-ready profile denies every capability, including read.
        if self.profile.readiness_status.value != "ready":
            return RuntimeResult(RuntimeStatus.DENIED, RuntimeErrorCode.CAPABILITY_DENIED)
        # Callable bridges are deliberately not accepted on the production path.
        if (runner is None or callable(runner)
                or not callable(getattr(runner, "run", None))
                or not isinstance(getattr(runner, "capability", None), SandboxCapability)
                or getattr(runner.capability, "_owner", None) is not runner):
            raise RuntimeRunnerRequiredError(RuntimeErrorCode.RUNNER_REQUIRED.value)
        # Fail closed at the provider path: only an explicitly network-enabled
        # runner may service provider_network, and ordinary provider runs must
        # never accidentally inherit network access.
        runner_network = getattr(runner, "network", False)
        if type(runner_network) is not bool:
            return RuntimeResult(RuntimeStatus.DENIED, RuntimeErrorCode.CAPABILITY_DENIED)
        if "provider_network" in envelope.capabilities:
            if not runner_network:
                return RuntimeResult(RuntimeStatus.DENIED, RuntimeErrorCode.CAPABILITY_DENIED)
        elif runner_network:
            return RuntimeResult(RuntimeStatus.DENIED, RuntimeErrorCode.CAPABILITY_DENIED)
        argv = self.build_argv(envelope)
        command = self._trusted_command()
        if command is None or type(command.executable) is not str:
            return RuntimeResult(RuntimeStatus.DENIED, RuntimeErrorCode.COMMAND_UNRESOLVED)
        executable = command.executable
        if not executable.startswith("/") or "\x00" in executable:
            return RuntimeResult(RuntimeStatus.DENIED, RuntimeErrorCode.COMMAND_UNRESOLVED)
        argv = (executable,) + tuple(argv[1:])
        roots = getattr(runner, "path_roots", None)
        if not envelope.allowed_paths or not isinstance(roots, Mapping):
            return RuntimeResult(RuntimeStatus.DENIED, RuntimeErrorCode.PATH_DENIED)
        namespace = envelope.allowed_paths[0].replace("\\", "/").split("/", 1)[0]
        if any(path.replace("\\", "/").split("/", 1)[0] != namespace for path in envelope.allowed_paths):
            return RuntimeResult(RuntimeStatus.DENIED, RuntimeErrorCode.PATH_DENIED)
        cwd = roots.get(namespace)
        if type(cwd) is not str or not cwd:
            return RuntimeResult(RuntimeStatus.DENIED, RuntimeErrorCode.PATH_DENIED)
        try:
            value = runner.run(argv, cwd=cwd, env=getattr(runner, "env", {}),
                               timeout=timeout, output_limits=(65536, 65536))
        except Exception as exc:
            return RuntimeResult(RuntimeStatus.FAILED, RuntimeErrorCode.RUNNER_ERROR,
                                 metadata={"exception": type(exc).__name__})
        if isinstance(value, RuntimeResult):
            # Reconstruct even a typed result so this boundary owns redaction.
            return RuntimeResult(value.status, value.error_code, value.output, value.metadata)
        if not isinstance(value, Mapping):
            return RuntimeResult(RuntimeStatus.FAILED, RuntimeErrorCode.SANDBOX_FAILED,
                                 output=_redact(str(value)))
        status = value.get("status")
        output = str(value.get("stdout", ""))
        stderr = str(value.get("stderr", ""))
        for secret in sorted((s for s in getattr(runner, "secrets", ()) if s), key=len, reverse=True):
            output = output.replace(secret, "[SECRET REDACTED]")
            stderr = stderr.replace(secret, "[SECRET REDACTED]")
        if status in ("passed", "ok"):
            metadata = value.get("metadata", {})
            if not isinstance(metadata, Mapping):
                metadata = {"runner_metadata": str(metadata)}
            metadata = dict(metadata)
            metadata["stderr"] = stderr
            return RuntimeResult(RuntimeStatus.OK, output=output, metadata=metadata)
        mapped = {"denied": (RuntimeStatus.DENIED, RuntimeErrorCode.SANDBOX_DENIED),
                  "timeout": (RuntimeStatus.TIMEOUT, RuntimeErrorCode.SANDBOX_TIMEOUT),
                  "failed": (RuntimeStatus.FAILED, RuntimeErrorCode.SANDBOX_FAILED)}
        result_status, code = mapped.get(status, (RuntimeStatus.FAILED, RuntimeErrorCode.SANDBOX_FAILED))
        metadata = value.get("metadata", {})
        if not isinstance(metadata, Mapping):
            metadata = {"runner_metadata": str(metadata)}
        metadata = dict(metadata)
        metadata["stderr"] = stderr
        return RuntimeResult(result_status, code, output=output, metadata=metadata)

    def dry_run(self, envelope: RuntimeTaskEnvelope, *, bridge: Any) -> RuntimeResult:
        """Explicit test-only callable bridge; never used by ``execute``."""
        _validate_envelope(envelope, self.profile)
        if not callable(bridge):
            raise RuntimeRunnerRequiredError(RuntimeErrorCode.RUNNER_REQUIRED.value)
        value = bridge(self.build_argv(envelope), envelope=envelope)
        return RuntimeResult(RuntimeStatus.OK, output=_redact(str(value)))


def _adapter(name: str, profile: RuntimeProviderProfile, template: tuple[str, ...]) -> TemplateRuntimeAdapter:
    return TemplateRuntimeAdapter(name, profile, template)


def _fixed_builder(envelope: RuntimeTaskEnvelope, provider: str, runtime: str,
                   template: tuple[str, ...]) -> tuple[str, ...]:
    if (not isinstance(envelope, RuntimeTaskEnvelope)
            or envelope.provider_profile.provider_name != provider
            or envelope.provider_profile.runtime_name != runtime):
        raise RuntimeConfigurationError(RuntimeErrorCode.INVALID_ENVELOPE.value)
    return _adapter(f"{provider}/{runtime}", envelope.provider_profile, template).build_argv(envelope)


def build_hermes_argv(envelope: RuntimeTaskEnvelope) -> tuple[str, ...]:
    return _fixed_builder(envelope, "hermes", "openai-codex", ("hermes", "chat", "-q", "{prompt}", "--provider", "openai-codex", "--model", "default", "-Q", "--safe-mode", "--ignore-rules", "--max-turns", "1"))


def build_codex_cli_argv(envelope: RuntimeTaskEnvelope) -> tuple[str, ...]:
    return _fixed_builder(envelope, "codex-cli", "codex-cli", ("codex", "exec", "--json", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check", "{prompt}"))


def build_opencode_go_argv(envelope: RuntimeTaskEnvelope) -> tuple[str, ...]:
    return _fixed_builder(envelope, "opencode", "opencode-go", ("opencode", "run", "--format", "json", "--pure", "{prompt}"))


def build_claude_code_argv(envelope: RuntimeTaskEnvelope) -> tuple[str, ...]:
    return _fixed_builder(envelope, "claude-code", "claude-code", ("claude", "-p", "{prompt}", "--output-format", "json", "--no-session-persistence", "--tools=", "--max-budget-usd", "0.10"))


build_hermes_openai_codex_argv = build_hermes_argv
build_opencode_argv = build_opencode_go_argv


def runtime_adapters(profiles: Sequence[RuntimeProviderProfile]) -> tuple[TemplateRuntimeAdapter, ...]:
    required = {"openai-codex", "codex-cli", "opencode-go", "claude-code"}
    if (isinstance(profiles, (str, bytes, bytearray)) or not isinstance(profiles, Sequence)
            or any(not isinstance(p, RuntimeProviderProfile) for p in profiles)):
        raise RuntimeConfigurationError(RuntimeErrorCode.CATALOG_INVALID.value)
    names = [p.runtime_name for p in profiles]
    if len(names) != len(set(names)) or set(names) != required:
        raise RuntimeConfigurationError(RuntimeErrorCode.CATALOG_INVALID.value)
    by_runtime = {p.runtime_name: p for p in profiles}
    return (
        _adapter("hermes/openai-codex", by_runtime["openai-codex"], ("hermes", "chat", "-q", "{prompt}", "--provider", "openai-codex", "--model", "default", "-Q", "--safe-mode", "--ignore-rules", "--max-turns", "1")),
        _adapter("codex-cli", by_runtime["codex-cli"], ("codex", "exec", "--json", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check", "{prompt}")),
        _adapter("opencode-go", by_runtime["opencode-go"], ("opencode", "run", "--format", "json", "--pure", "{prompt}")),
        _adapter("claude-code", by_runtime["claude-code"], ("claude", "-p", "{prompt}", "--output-format", "json", "--no-session-persistence", "--tools=", "--max-budget-usd", "0.10")),
    )
