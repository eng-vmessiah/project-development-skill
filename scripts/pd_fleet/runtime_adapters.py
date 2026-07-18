"""Named, data-only runtime adapters.

Factories in this module only validate declarative inputs and construct argv
lists.  They never resolve an executable, inspect the environment, read auth,
or invoke a provider.  Execution remains opt-in through the existing
``TemplateRuntimeAdapter`` and an explicitly injected sandbox runner.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Sequence

from .provider import CommandMetadata, RuntimeProviderProfile
from .runtime_adapter import (
    RuntimeConfigurationError, RuntimeErrorCode, RuntimeResult, RuntimeStatus,
    RuntimeTaskEnvelope, TemplateRuntimeAdapter,
)


class RuntimeFactoryError(RuntimeConfigurationError):
    """Stable factory validation error; ``code`` is safe to persist/log."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


RuntimeAdapterFactoryError = RuntimeFactoryError

FACTORY_UNKNOWN_RUNTIME = "unknown_runtime"
FACTORY_PROFILE_MISMATCH = "profile_runtime_mismatch"
FACTORY_COMMAND_REQUIRED = "command_metadata_required"
FACTORY_INVALID_EXECUTABLE = "invalid_executable"
FACTORY_INVALID_MODEL = "invalid_model"
FACTORY_INVALID_MAX_TURNS = "invalid_max_turns"
FACTORY_COMMAND_ARGUMENTS_UNSUPPORTED = "command_arguments_unsupported"

_TEMPLATES = {
    "openai-codex": ("hermes", "chat", "-q", "{prompt}", "--provider", "openai-codex", "--model", "{model}"),
    "codex-cli": ("codex", "exec", "{prompt}"),
    "opencode-go": ("opencode", "run", "{prompt}", "--format", "json"),
    "claude-code": ("claude", "-p", "{prompt}", "--output-format", "json", "--max-turns", "{max_turns}"),
}
_RUNTIME_PROVIDERS = {"openai-codex": "hermes", "codex-cli": "codex-cli", "opencode-go": "opencode", "claude-code": "claude-code"}


def _metadata_value(envelope: RuntimeTaskEnvelope, key: str) -> str:
    value = envelope.metadata.get(key)
    if type(value) is not str or not value or "\x00" in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise RuntimeFactoryError(FACTORY_INVALID_MODEL if key == "model" else FACTORY_INVALID_MAX_TURNS)
    if re.search(r"[;&|<>$`]|\$\(|\|\|", value):
        raise RuntimeFactoryError(FACTORY_INVALID_MODEL if key == "model" else FACTORY_INVALID_MAX_TURNS)
    return value


def parse_runtime_output(value: Any, *, runner_status: str = "passed", stderr: str = "", metadata: Mapping[str, Any] | None = None) -> RuntimeResult:
    """Convert untrusted runner output to a result, failing closed.

    Provider JSON fields (especially ``status``/``error``) are data and cannot
    control the result status. A successful runner status is accepted only
    when a recognized, non-empty result field is present.
    """
    text = value if isinstance(value, str) else ("" if value is None else str(value))
    output = ""
    evidence = False
    try:
        document = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        document = None
    if isinstance(document, Mapping):
        for key in ("output", "result", "structured_output", "text", "content"):
            candidate = document.get(key)
            if isinstance(candidate, str) and candidate.strip():
                output, evidence = candidate, True
                break
            if key in ("output", "result", "structured_output") and candidate not in (None, "", {}, [], ()):
                output = json.dumps(candidate, ensure_ascii=True, sort_keys=True)
                evidence = bool(output.strip())
                break
    elif isinstance(document, list):
        items = [item for item in document if isinstance(item, str) and item.strip()]
        if items:
            output, evidence = "\n".join(items), True
    safe_meta = dict(metadata) if isinstance(metadata, Mapping) else {}
    safe_meta["stderr"] = stderr if isinstance(stderr, str) else str(stderr)
    safe_status = runner_status.value if isinstance(runner_status, RuntimeStatus) else runner_status
    mapping = {
        "denied": (RuntimeStatus.DENIED, RuntimeErrorCode.SANDBOX_DENIED),
        "timeout": (RuntimeStatus.TIMEOUT, RuntimeErrorCode.SANDBOX_TIMEOUT),
        "failed": (RuntimeStatus.FAILED, RuntimeErrorCode.SANDBOX_FAILED),
        "error": (RuntimeStatus.ERROR, RuntimeErrorCode.RUNNER_ERROR),
        "blocked": (RuntimeStatus.BLOCKED, RuntimeErrorCode.CAPABILITY_DENIED),
    }
    if safe_status in mapping:
        status, code = mapping[safe_status]
        return RuntimeResult(status, code, output=output, metadata=safe_meta)
    if safe_status in ("passed", "ok") and evidence:
        return RuntimeResult(RuntimeStatus.OK, output=output, metadata=safe_meta)
    return RuntimeResult(RuntimeStatus.FAILED, RuntimeErrorCode.SANDBOX_FAILED, output=output, metadata=safe_meta)


parse_runner_output = parse_runtime_output


@dataclass(frozen=True, slots=True)
class NamedRuntimeAdapter:
    """A named template adapter with strict envelope/profile identity."""
    name: str
    profile: RuntimeProviderProfile
    command_metadata: CommandMetadata
    runtime: str

    def _template(self, envelope: RuntimeTaskEnvelope) -> tuple[str, ...]:
        if envelope.provider_profile != self.profile:
            raise RuntimeFactoryError(FACTORY_PROFILE_MISMATCH)
        template = _TEMPLATES[self.runtime]
        values = {"prompt": envelope.prompt}
        if self.runtime == "openai-codex":
            values["model"] = _metadata_value(envelope, "model")
        if self.runtime == "claude-code":
            value = envelope.metadata.get("max_turns")
            if type(value) is not int or isinstance(value, bool) or not (1 <= value <= 100):
                raise RuntimeFactoryError(FACTORY_INVALID_MAX_TURNS)
            values["max_turns"] = str(value)
        return tuple(part.format(**values) for part in template)

    def build_argv(self, envelope: RuntimeTaskEnvelope) -> tuple[str, ...]:
        argv = self._template(envelope)
        return (self.command_metadata.executable,) + argv[1:]

    def execute(self, envelope: RuntimeTaskEnvelope, *, runner: Any = None) -> RuntimeResult:
        # Delegate sandbox checks and result mapping, then parse JSON payload.
        base = TemplateRuntimeAdapter(self.name, self.profile, self._template(envelope), self.command_metadata).execute(envelope, runner=runner)
        return parse_runtime_output(base.output, runner_status=base.status.value, stderr=str(base.metadata.get("stderr", "")), metadata={"runtime": self.runtime})


HermesRuntimeAdapter = NamedRuntimeAdapter
CodexRuntimeAdapter = NamedRuntimeAdapter
OpenCodeGoRuntimeAdapter = NamedRuntimeAdapter
ClaudeCodeRuntimeAdapter = NamedRuntimeAdapter
# Friendly names used by callers; canonical profile runtime names remain stable.
HermesAdapter = HermesRuntimeAdapter
CodexAdapter = CodexRuntimeAdapter
OpenCodeGoAdapter = OpenCodeGoRuntimeAdapter
ClaudeCodeAdapter = ClaudeCodeRuntimeAdapter
_RUNTIME_ALIASES = {"hermes": "openai-codex", "codex": "codex-cli", "opencode": "opencode-go", "opencode-go": "opencode-go", "claude": "claude-code", "claude-code": "claude-code", "openai-codex": "openai-codex", "codex-cli": "codex-cli"}


def create_runtime_adapter(runtime: str, profile: RuntimeProviderProfile, command_metadata: CommandMetadata | None = None) -> NamedRuntimeAdapter:
    if type(runtime) is not str or runtime not in _RUNTIME_ALIASES:
        raise RuntimeFactoryError(FACTORY_UNKNOWN_RUNTIME)
    canonical = _RUNTIME_ALIASES[runtime]
    if not isinstance(profile, RuntimeProviderProfile) or profile.runtime_name != canonical or profile.provider_name != _RUNTIME_PROVIDERS[canonical]:
        raise RuntimeFactoryError(FACTORY_PROFILE_MISMATCH)
    if not isinstance(command_metadata, CommandMetadata):
        raise RuntimeFactoryError(FACTORY_COMMAND_REQUIRED)
    executable = command_metadata.executable
    if (type(executable) is not str or not executable.startswith("/") or "\x00" in executable
            or any(ord(char) < 32 or ord(char) == 127 for char in executable)
            or any(char in ";&|<>$`" for char in executable)):
        raise RuntimeFactoryError(FACTORY_INVALID_EXECUTABLE)
    if command_metadata.arguments:
        raise RuntimeFactoryError(FACTORY_COMMAND_ARGUMENTS_UNSUPPORTED)
    return NamedRuntimeAdapter(f"{profile.provider_name}/{canonical}", profile, command_metadata, canonical)


runtime_adapter_factory = create_runtime_adapter
factory = create_runtime_adapter


def create_named_runtime_adapters(profiles: Sequence[RuntimeProviderProfile], commands: Mapping[str, CommandMetadata]) -> tuple[NamedRuntimeAdapter, ...]:
    if not isinstance(profiles, Sequence) or isinstance(profiles, (str, bytes, bytearray)) or not isinstance(commands, Mapping):
        raise RuntimeFactoryError(FACTORY_PROFILE_MISMATCH)
    result = []
    for profile in profiles:
        result.append(create_runtime_adapter(profile.runtime_name, profile, commands.get(profile.runtime_name)))
    return tuple(result)
