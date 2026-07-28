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
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import time
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence
import re

from .provider import CommandMetadata, RuntimeProviderProfile, ReadinessStatus, assess_readiness
from .sandbox import SandboxCapability


# Local status checks are deliberately separate from the older, capability
# gated version probe below.  The command table is closed: callers cannot add
# arguments, choose an executable, or turn this into a login/model invocation.
_LOCAL_COMMANDS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "openai-codex": ("hermes", "auth", "status", "openai-codex"),
    "codex-cli": ("codex", "login", "status"),
    "opencode-go": ("opencode", "providers", "list"),
    "claude-code": ("claude", "auth", "status", "--json"),
})
_LOCAL_EXECUTABLES = MappingProxyType({key: value[0] for key, value in _LOCAL_COMMANDS.items()})
_LOCAL_OUTPUT_LIMIT = 4096
_COMBINED_OUTPUT_LIMIT = 4096
_LOCAL_TIMEOUT = 10.0
_DEFAULT_DENIED_REASON = "trusted_runner_required"


@dataclass(frozen=True, slots=True)
class LocalReadinessResult:
    """Safe, immutable result for a local runtime authentication check.

    It intentionally contains neither argv/path nor command output.  Status
    commands may perform their own provider network request, but this module
    never logs in, reads credentials, or executes a model prompt.
    """
    runtime_id: str
    installed: bool
    authenticated: bool
    status: str
    reason: str


class LocalRuntimeReadinessProbe:
    """Check the four supported local runtimes using fixed read-only commands.

    ``runner`` is injectable and may be a callable or an object with ``run``.
    No runner is selected implicitly: omitted runners fail closed before PATH
    discovery or subprocess execution.  The legacy ``_default_runner`` helper
    remains available only to explicit internal callers and is never used by
    ``probe`` without a trusted runner.
    """

    def __init__(self, runner: Any = None, *, timeout: float = _LOCAL_TIMEOUT,
                 output_limit: int = _LOCAL_OUTPUT_LIMIT) -> None:
        # Do not allow callers to weaken the safety bounds.
        self._runner = runner
        self._timeout = min(float(timeout), _LOCAL_TIMEOUT)
        self._output_limit = min(int(output_limit), _LOCAL_OUTPUT_LIMIT)

    @staticmethod
    def _default_runner(argv: Sequence[str], *, timeout: float,
                        output_limits: tuple[int, int], env: Mapping[str, str]) -> Any:
        try:
            executable = Path(argv[0]).resolve(strict=True)
            if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
                return {"status": "failed"}
            fixed_argv = (str(executable),) + tuple(argv[1:])
        except (OSError, RuntimeError, IndexError, TypeError):
            return {"status": "failed"}
        # Keep the per-stream contract and read chunks above, but enforce one
        # hard aggregate ceiling for the whole probe.
        cap = _COMBINED_OUTPUT_LIMIT
        proc = None
        chunks: list[bytes] = []
        selector = selectors.DefaultSelector()
        try:
            proc = subprocess.Popen(list(fixed_argv), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env={},
                start_new_session=True)
            assert proc.stdout is not None and proc.stderr is not None
            selector.register(proc.stdout, selectors.EVENT_READ)
            selector.register(proc.stderr, selectors.EVENT_READ)
            started = time.monotonic()
            while selector.get_map():
                remaining = float(timeout) - (time.monotonic() - started)
                if remaining <= 0:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    return {"status": "timeout"}
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    chunks.append(chunk)
                    if sum(map(len, chunks)) > cap:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                        data = b"".join(chunks)[:cap].decode("utf-8", "replace")
                        return {"status": "output_limit", "stdout": data, "stderr": "",
                                "returncode": proc.returncode}
            proc.wait()
            data = b"".join(chunks)[:cap].decode("utf-8", "replace")
            return {"status": "passed" if proc.returncode == 0 else "failed",
                    "stdout": data, "stderr": "", "returncode": proc.returncode}
        except (OSError, subprocess.TimeoutExpired):
            if proc is not None and proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                except OSError:
                    pass
            return {"status": "failed"}
        finally:
            # ``Popen`` does not close the parent-side BufferedReader objects
            # when the child is reaped.  Close them explicitly on every exit
            # path (normal, timeout, output cap, and exceptions).  Do not use
            # ``communicate`` here: it could drain an unbounded pipe after the
            # aggregate cap has fired and reintroduce the DoS this runner is
            # intended to prevent.
            selector.close()
            if proc is not None and proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
                try:
                    proc.wait()
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if proc is not None:
                for stream in (proc.stdout, proc.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass

    def _invoke(self, argv: tuple[str, ...]) -> Any:
        runner = self._runner
        if runner is None:
            return {"status": "denied"}
        if hasattr(runner, "run"):
            return runner.run(argv, timeout=self._timeout,
                              output_limits=(self._output_limit, self._output_limit), env={})
        return runner(argv, timeout=self._timeout,
                      output_limits=(self._output_limit, self._output_limit), env={})

    @staticmethod
    def _opencode_go_authenticated(text: str) -> bool:
        """Recognize only the structured, positive OpenCode Go status shape.

        The CLI prints the provider label and credential summary on separate
        lines (for example ``OpenCode Go api`` followed by ``2 credentials``).
        Keep this parser deliberately fail-closed: an error or explicit empty
        credential state anywhere in the output wins over a positive-looking
        line, and the credential evidence must follow the provider label.
        """
        lines = [" ".join(line.casefold().split()) for line in text.splitlines()]
        provider_index = next((i for i, line in enumerate(lines) if "opencode go" in line), None)
        if provider_index is None:
            return False

        for line in lines[provider_index:]:
            if re.search(r"\b(?:error|failed|failure|unauthori[sz]ed|invalid)\b", line):
                return False
            if re.search(r"\b(?:no|zero|0)\s+credentials?\b|\bcredentials?\s*[:=-]?\s*(?:none|0)\b", line):
                return False

        for line in lines[provider_index + 1:]:
            if re.search(r"\b[1-9]\d* credentials?\b", line):
                return True
            if re.search(r"\bcredentials? (?:configured|available)\b", line):
                return True
        return False

    @staticmethod
    def _parts(raw: Any) -> tuple[int | None, str, str, str]:
        if isinstance(raw, Mapping):
            status = raw.get("status", "")
            status = status.value if isinstance(status, Enum) else str(status)
            return raw.get("returncode"), str(raw.get("stdout", ""))[:_LOCAL_OUTPUT_LIMIT], str(raw.get("stderr", ""))[:_LOCAL_OUTPUT_LIMIT], status
        return getattr(raw, "returncode", None), str(getattr(raw, "stdout", ""))[:_LOCAL_OUTPUT_LIMIT], str(getattr(raw, "stderr", ""))[:_LOCAL_OUTPUT_LIMIT], ""

    def probe(self, runtime_id: str) -> LocalReadinessResult:
        if runtime_id not in _LOCAL_COMMANDS:
            return LocalReadinessResult(str(runtime_id), False, False, "unknown", "runtime_unknown")
        if self._runner is None:
            return LocalReadinessResult(runtime_id, False, False, "denied", _DEFAULT_DENIED_REASON)
        executable = shutil.which(_LOCAL_EXECUTABLES[runtime_id])
        if not executable:
            return LocalReadinessResult(runtime_id, False, False, "not_installed", "executable_not_found")
        # The real runner validates this path immediately before exec.  Keeping
        # discovery opaque here also lets injected test runners model discovery.
        argv = (executable,) + _LOCAL_COMMANDS[runtime_id][1:]
        try:
            raw = self._invoke(argv)
        except (subprocess.TimeoutExpired, TimeoutError):
            return LocalReadinessResult(runtime_id, True, False, "timeout", "command_timeout")
        except Exception:
            return LocalReadinessResult(runtime_id, True, False, "failed", "command_failed")
        returncode, stdout, stderr, runner_status = self._parts(raw)
        if runner_status == "timeout":
            return LocalReadinessResult(runtime_id, True, False, "timeout", "command_timeout")
        if runner_status in {"failed", "error", "denied", "blocked"}:
            return LocalReadinessResult(runtime_id, True, False, "failed", "command_failed")
        # Fake runners commonly expose only the existing sandbox status; a
        # successful status is equivalent to a zero process exit.
        succeeded = returncode == 0 or (returncode is None and runner_status in {"passed", "ok", "success"})
        text = (stdout + "\n" + stderr)
        authenticated = False
        if succeeded:
            lines = {line.strip().lower() for line in text.splitlines()}
            if runtime_id == "openai-codex":
                authenticated = "openai-codex: logged in" in lines
            elif runtime_id == "codex-cli":
                authenticated = "logged in using chatgpt" in lines
            elif runtime_id == "opencode-go":
                authenticated = self._opencode_go_authenticated(text)
            else:
                try:
                    payload = json.loads(stdout)
                    authenticated = type(payload) is dict and payload.get("loggedIn") is True
                except (TypeError, ValueError):
                    authenticated = False
        return LocalReadinessResult(runtime_id, True, authenticated,
                                    "authenticated" if authenticated else "auth_absent",
                                    "auth_confirmed" if authenticated else "auth_not_confirmed")

    check = probe
    readiness = probe


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


def _runner_status(result: Any) -> str:
    if isinstance(result, Mapping):
        status = result.get("status", "failed")
        return status.value if isinstance(status, Enum) else status
    return "failed"


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
        # ``output`` is retained only as a legacy API field.  Probe diagnostics
        # may contain credentials or other PII, so never redact-and-retain them.
        object.__setattr__(self, "output", "")
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
    runner_status = _runner_status(result)
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
    audit = ProviderReadinessAudit(runtime, status, reason)
    return ProviderReadinessResult(status, runtime, argv, audit=audit)


readiness_probe = probe_provider_readiness
probe_readiness = probe_provider_readiness
