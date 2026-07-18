"""Capability-gated, non-authenticating readiness probes.

This module is intentionally a policy boundary.  It does not discover commands,
read the host, inspect environment/credentials, perform network access, or invoke
subprocesses itself.  Execution is possible only through an explicitly injected
runner and its runner-issued capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence
import re

from .provider import CommandMetadata, RuntimeProviderProfile, ReadinessStatus, assess_readiness
from .sandbox import SandboxCapability


class ProviderReadinessError(ValueError):
    """Invalid probe contract; messages contain stable codes only."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ProbeStatus(str, Enum):
    CONTRACT_READY = "contract_ready"
    RUNTIME_PRESENT = "runtime_present"
    AUTH_UNKNOWN = "auth_unknown"
    AVAILABLE = "available"
    DENIED = "denied"
    TIMEOUT = "timeout"
    FAILED = "failed"


class ReadinessAuditReason(str, Enum):
    CONTRACT_VALID = "contract_valid"
    RUNTIME_VERSION_CONFIRMED = "runtime_version_confirmed"
    AUTH_NOT_VERIFIED = "auth_not_verified"
    AUTH_EXPLICITLY_CONFIRMED = "auth_explicitly_confirmed"
    CONTRACT_BLOCKED = "contract_blocked"
    SANDBOX_DENIED = "sandbox_denied"
    SANDBOX_TIMEOUT = "sandbox_timeout"
    SANDBOX_FAILED = "sandbox_failed"


class TrustedSandboxRunner(Protocol):
    def run(self, argv: Sequence[str], *, cwd: str, env: Mapping[str, str],
            timeout: float, output_limits: tuple[int, int]) -> Any: ...


_RUNTIME_EXECUTABLES = {
    "openai-codex": "hermes", "codex-cli": "codex",
    "opencode-go": "opencode", "claude-code": "claude",
}
_SAFE_RUNTIME = frozenset(_RUNTIME_EXECUTABLES)
def _fixed_status_argv(value: Any) -> tuple[str, ...]:
    """Validate the compatibility argument, while keeping the probe fixed."""
    if value is None:
        return ("--version",)
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ProviderReadinessError("invalid_status_command")
    if tuple(value) != ("--version",):
        raise ProviderReadinessError("invalid_status_command")
    return ("--version",)


def _executable(command_metadata: CommandMetadata | None, executable: str | None, runtime: str) -> str:
    if executable is None and command_metadata is not None:
        executable = command_metadata.executable
    if type(executable) is not str or not executable or "\x00" in executable:
        raise ProviderReadinessError("executable_pin_required")
    # An executable pin is opaque to this module, but must be absolute and inert;
    # the trusted runner performs the actual pin/path verification.
    if not executable.startswith("/") or any(ord(c) < 32 or ord(c) == 127 for c in executable):
        raise ProviderReadinessError("invalid_executable_pin")
    if any(c in executable for c in ";&|<>$`\n\r"):
        raise ProviderReadinessError("invalid_executable_pin")
    return executable


def _auth_confirmed(auth_result: Any, evidence: Any) -> bool:
    """Accept authentication only from explicit injected evidence."""
    if type(auth_result) is bool:
        return auth_result
    if isinstance(auth_result, Mapping) and type(auth_result.get("authenticated")) is bool:
        return auth_result["authenticated"]
    if isinstance(evidence, Mapping) and type(evidence.get("authenticated")) is bool:
        return evidence["authenticated"]
    return False


def _runner_result(result: Any) -> tuple[str, Any]:
    if isinstance(result, Mapping):
        status = result.get("status", "failed")
        return (status.value if isinstance(status, Enum) else status), result
    return "failed", None


@dataclass(frozen=True, slots=True)
class ProviderReadinessAudit:
    runtime: str
    status: ProbeStatus
    reason: ReadinessAuditReason

    def __post_init__(self) -> None:
        if self.runtime not in _SAFE_RUNTIME:
            raise ProviderReadinessError("invalid_runtime")
        object.__setattr__(self, "status", ProbeStatus(self.status))
        object.__setattr__(self, "reason", ReadinessAuditReason(self.reason))

    def as_dict(self) -> dict[str, str]:
        return {"runtime": self.runtime, "status": self.status.value, "reason": self.reason.value}


@dataclass(frozen=True, slots=True)
class ProviderReadinessResult:
    status: ProbeStatus
    runtime: str
    argv: tuple[str, ...]
    output: str = ""
    audit: ProviderReadinessAudit | None = None
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if self.runtime not in _SAFE_RUNTIME or not isinstance(self.argv, tuple):
            raise ProviderReadinessError("invalid_result")
        if not all(type(arg) is str for arg in self.argv):
            raise ProviderReadinessError("invalid_result")
        object.__setattr__(self, "status", ProbeStatus(self.status))
        # Results are an untrusted serialization boundary: never retain or
        # expose the pinned absolute executable path.
        if self.argv:
            object.__setattr__(self, "argv", ("[PATH REDACTED]",) + self.argv[1:])
        object.__setattr__(self, "output", _redact(self.output if type(self.output) is str else ""))
        object.__setattr__(self, "metadata", MappingProxyType({"runtime": self.runtime}))

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "runtime": self.runtime,
                "argv": list(self.argv), "output": self.output,
                "audit": None if self.audit is None else self.audit.as_dict(),
                "metadata": dict(self.metadata)}

    def serialize(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    to_dict = as_dict
    to_json = serialize


def _redact(value: str) -> str:
    value = re.sub(r"(?i)(?:https?|ftp|wss?)://[^\s]+", "[URL REDACTED]", value)
    value = re.sub(r"(?<![\w.])(?:~[/\\]|/)[^\s\"'<>;,]+", "[PATH REDACTED]", value)
    value = re.sub(r"(?i)(?:token|secret|password|credential|api[_ -]?key|authorization|bearer)\s*[=:]\s*[^\s]+", "[SECRET REDACTED]", value)
    return value[:4096]


def probe_provider_readiness(profile: RuntimeProviderProfile, *, runner: TrustedSandboxRunner,
                             capability: SandboxCapability, executable: str | None = None,
                             command_metadata: CommandMetadata | None = None,
                             cwd: str = "/", timeout: float = 5.0,
                             auth_result: Any = None, auth_evidence: Any = None,
                             status_command: Sequence[str] | None = None) -> ProviderReadinessResult:
    """Probe one runtime with a fixed version argv; never logs in or verifies auth."""
    if not isinstance(profile, RuntimeProviderProfile) or profile.runtime_name not in _SAFE_RUNTIME:
        raise ProviderReadinessError("invalid_runtime")
    if not isinstance(capability, SandboxCapability) or getattr(capability, "_owner", None) is not runner:
        raise ProviderReadinessError("capability_required")
    contract = assess_readiness(profile)
    runtime = profile.runtime_name
    if contract.status is not ReadinessStatus.READY:
        audit = ProviderReadinessAudit(runtime, ProbeStatus.CONTRACT_READY, ReadinessAuditReason.CONTRACT_BLOCKED)
        return ProviderReadinessResult(ProbeStatus.CONTRACT_READY, runtime, (), audit=audit)
    exe = _executable(command_metadata, executable, runtime)
    suffix = _fixed_status_argv(status_command)
    argv = (exe,) + suffix
    result = runner.run(argv, cwd=cwd, env={}, timeout=timeout, output_limits=(4096, 4096))
    runner_status, raw = _runner_result(result)
    if runner_status == "denied":
        status, reason = ProbeStatus.DENIED, ReadinessAuditReason.SANDBOX_DENIED
    elif runner_status == "timeout":
        status, reason = ProbeStatus.TIMEOUT, ReadinessAuditReason.SANDBOX_TIMEOUT
    elif runner_status in {"failed", "error", "blocked"}:
        status, reason = ProbeStatus.FAILED, ReadinessAuditReason.SANDBOX_FAILED
    elif runner_status in {"passed", "ok"}:
        # Runner output is never authentication evidence. Only values
        # explicitly injected by the trusted caller may establish auth.
        status = ProbeStatus.AVAILABLE if _auth_confirmed(auth_result, auth_evidence) else ProbeStatus.RUNTIME_PRESENT
        reason = (ReadinessAuditReason.AUTH_EXPLICITLY_CONFIRMED if status is ProbeStatus.AVAILABLE
                  else ReadinessAuditReason.AUTH_NOT_VERIFIED)
    else:
        status, reason = ProbeStatus.FAILED, ReadinessAuditReason.SANDBOX_FAILED
    output = _redact(str(raw.get("stdout", "")) if isinstance(raw, Mapping) else "")
    audit = ProviderReadinessAudit(runtime, status, reason)
    return ProviderReadinessResult(status, runtime, argv, output, audit)


readiness_probe = probe_provider_readiness
probe_readiness = probe_provider_readiness
