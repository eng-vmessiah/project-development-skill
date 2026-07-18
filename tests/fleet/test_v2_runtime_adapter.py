"""TDD checks for the pure runtime adapter boundary."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.provider import CommandMetadata, RuntimePolicy, RuntimeProviderProfile, default_runtime_profiles  # noqa: E402
from pd_fleet.runtime_adapter import (  # noqa: E402
    RuntimeErrorCode,
    RuntimeStatus,
    RuntimeTaskEnvelope,
    RuntimeCapabilityError,
    RuntimeConfigurationError,
    RuntimeResult,
    RuntimeRunnerRequiredError,
    runtime_adapters,
    build_claude_code_argv,
    build_codex_cli_argv,
    build_hermes_argv,
    build_opencode_go_argv,
)


def _envelope(runtime: str = "openai-codex") -> RuntimeTaskEnvelope:
    profile = next(p for p in default_runtime_profiles() if p.runtime_name == runtime)
    profile = RuntimeProviderProfile(
        provider_name=profile.provider_name, runtime_name=runtime,
        auth_ref="runtime:default", capabilities=("read",), policy=RuntimePolicy(enabled=True, allowed_capabilities=("read",)),
    )
    return RuntimeTaskEnvelope("task-1", "inspect the project", profile, ("workspace/src",), ("read",))


def test_envelope_is_immutable_and_serialization_is_stable_redacted() -> None:
    envelope = RuntimeTaskEnvelope(
        "task-1", "use token=secret at /home/user/private", _envelope().provider_profile,
        ("workspace",), ("read",), metadata={"api_key": "secret", "owner": "team"},
    )
    assert envelope.serialize() == envelope.serialize()
    rendered = json.loads(envelope.serialize())
    assert "secret" not in envelope.serialize()
    assert rendered["metadata"]["api_key"] == "[REDACTED]"
    with pytest.raises(TypeError):
        envelope.metadata["x"] = 1  # type: ignore[index]


def test_nested_agents_and_host_paths_are_denied() -> None:
    profile = _envelope().provider_profile
    with pytest.raises(RuntimeCapabilityError) as nested:
        RuntimeTaskEnvelope("x", "do", profile, capabilities=("nested_agents",))
    assert str(nested.value) == RuntimeErrorCode.NESTED_AGENTS_DENIED.value
    with pytest.raises(RuntimeCapabilityError):
        RuntimeTaskEnvelope("x", "do", profile, allowed_paths=("/etc",))


@pytest.mark.parametrize(
    ("runtime", "builder", "executable"),
    [("openai-codex", build_hermes_argv, "hermes"), ("codex-cli", build_codex_cli_argv, "codex"),
     ("opencode-go", build_opencode_go_argv, "opencode"), ("claude-code", build_claude_code_argv, "claude")],
)
def test_four_builders_are_data_only(runtime, builder, executable) -> None:
    argv = builder(_envelope(runtime))
    assert isinstance(argv, tuple)
    assert argv[0] == executable
    assert "inspect the project" in argv


def test_execution_requires_injected_runner() -> None:
    from pd_fleet.runtime_adapter import TemplateRuntimeAdapter
    envelope = _envelope()
    adapter = TemplateRuntimeAdapter("hermes/openai-codex", envelope.provider_profile, ("hermes", "{prompt}"))
    result = adapter.execute(envelope, runner=None)
    assert result.status is RuntimeStatus.DENIED
    assert result.error_code == RuntimeErrorCode.CAPABILITY_DENIED
    seen = {}
    result = adapter.dry_run(envelope, bridge=lambda argv, envelope: seen.setdefault("argv", argv) or "ok")
    assert result.status is RuntimeStatus.OK
    assert seen["argv"] == ("hermes", "inspect the project")


def test_module_has_no_execution_or_environment_discovery_imports() -> None:
    tree = ast.parse(Path(__file__).parents[2].joinpath("scripts/pd_fleet/runtime_adapter.py").read_text())
    forbidden = {"os", "subprocess", "socket", "requests", "httpx", "urllib", "pathlib"}
    imports = {node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)}
    imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not imports & forbidden


def test_capabilities_and_builder_identity_are_fail_closed() -> None:
    profile = _envelope().provider_profile
    with pytest.raises(RuntimeCapabilityError):
        RuntimeTaskEnvelope("x", "do", profile, capabilities=("write",))
    wrong = RuntimeProviderProfile("other", "openai-codex", auth_ref="runtime:x",
                                   capabilities=("read",),
                                   policy=RuntimePolicy(enabled=True, allowed_capabilities=("read",)))
    with pytest.raises(RuntimeConfigurationError):
        build_hermes_argv(RuntimeTaskEnvelope("x", "do", wrong, capabilities=("read",)))


def test_namespace_control_and_catalog_validation() -> None:
    profile = _envelope().provider_profile
    for path in ("tmp/file", "workspace/../secrets", "workspace/\x7f"):
        with pytest.raises(RuntimeCapabilityError):
            RuntimeTaskEnvelope("x", "do", profile, allowed_paths=(path,))
    with pytest.raises(RuntimeConfigurationError):
        runtime_adapters(default_runtime_profiles()[:-1])
    with pytest.raises(RuntimeConfigurationError):
        runtime_adapters(default_runtime_profiles() + (default_runtime_profiles()[0],))
    hostile = RuntimeTaskEnvelope("x", "do; rm", profile, capabilities=("read",))
    with pytest.raises(RuntimeConfigurationError):
        build_hermes_argv(hostile)


def test_runtime_result_serialization_redacts_public_fields() -> None:
    result = RuntimeResult(RuntimeStatus.ERROR, output="token=supersecret /home/vitor/private",
                           metadata={"nested": "https://example.invalid/x"})
    rendered = result.serialize()
    assert "supersecret" not in rendered
    assert "/home/vitor/private" not in rendered
    assert "example.invalid" not in rendered


def test_runner_bridge_passes_sandbox_contract_without_typeerror() -> None:
    envelope = _envelope()
    seen = {}
    class Runner:
        env = {"SAFE": "1"}
        tool_root = "/safe/root"
        def run(self, argv, *, cwd, env, timeout, output_limits):
            seen.update(cwd=cwd, env=env, timeout=timeout, output_limits=output_limits)
            return {"status": "passed", "stdout": "ok", "stderr": ""}
    from pd_fleet.runtime_adapter import TemplateRuntimeAdapter
    result = TemplateRuntimeAdapter("x", envelope.provider_profile, ("tool",)).execute(envelope, runner=Runner())
    assert result.status is RuntimeStatus.DENIED
    assert result.error_code == RuntimeErrorCode.CAPABILITY_DENIED


@pytest.mark.parametrize("capability", ["shell", "network"])
def test_production_boundary_rejects_shell_and_network_even_with_runner(capability: str) -> None:
    profile = RuntimeProviderProfile(
        "safe", "safe", auth_ref="runtime:default", capabilities=(capability,),
        policy=RuntimePolicy(enabled=True, allowed_capabilities=(capability,)),
    )
    with pytest.raises(RuntimeCapabilityError) as exc:
        RuntimeTaskEnvelope("x", "do", profile, capabilities=(capability,))
    assert str(exc.value) == RuntimeErrorCode.CAPABILITY_DENIED.value


def test_runtime_result_is_redacted_before_callers_can_inspect_it() -> None:
    result = RuntimeResult(
        RuntimeStatus.OK,
        output="secret=raw https://evil.example/a /home/vitor/private",
        metadata={"details": "C:\\Users\\vitor\\secret", "api_token": "raw-token"},
    )
    assert "raw" not in result.output
    assert "evil.example" not in result.output
    assert "/home/vitor/private" not in result.output
    assert "vitor" not in str(result.metadata)
    assert result.metadata["api_token"] == "[REDACTED]"


def test_execute_uses_explicit_trusted_command_and_sandbox_capability(tmp_path: Path) -> None:
    from pd_fleet.runtime_adapter import TemplateRuntimeAdapter
    from pd_fleet.sandbox import LocalSandboxRunner
    tool = tmp_path / "tool"
    tool.write_text("#!/bin/sh\nprintf 'ok\\n'\n")
    tool.chmod(0o700)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = RuntimeProviderProfile(
        "safe", "safe", auth_ref="runtime:default", capabilities=("read",),
        command=CommandMetadata(str(tool)),
        policy=RuntimePolicy(enabled=True, allowed_capabilities=("read",)),
    )
    envelope = RuntimeTaskEnvelope("x", "do", profile, ("workspace",), ("read",))
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(tool), "do"),), path_roots={"workspace": workspace})
    result = TemplateRuntimeAdapter("safe", profile, ("tool", "{prompt}"), CommandMetadata(str(tool))).execute(envelope, runner=runner)
    assert result.status is RuntimeStatus.OK
    assert result.output == "ok\n"


def test_fake_runner_is_denied_even_when_it_has_run() -> None:
    from pd_fleet.runtime_adapter import TemplateRuntimeAdapter
    profile = RuntimeProviderProfile(
        "hermes", "openai-codex", auth_ref="runtime:default", command=CommandMetadata("/private/tool"),
        capabilities=("read",), policy=RuntimePolicy(enabled=True, allowed_capabilities=("read",)),
    )
    envelope = RuntimeTaskEnvelope("x", "do", profile, ("workspace",), ("read",))
    class Fake:
        def run(self, *args, **kwargs):
            raise AssertionError("must not be called")
    adapter = TemplateRuntimeAdapter("hermes/openai-codex", envelope.provider_profile, ("hermes",))
    with pytest.raises(RuntimeRunnerRequiredError):
        adapter.execute(envelope, runner=Fake())


def test_profile_never_stores_raw_command_or_execution_accessor() -> None:
    profile = RuntimeProviderProfile("safe", "safe", command=CommandMetadata("/private/tool"))
    assert not hasattr(profile, "_raw_command")
    assert not hasattr(profile, "_execution_command_metadata")
    assert "private" not in str(profile.command)


def test_runtime_timeout_policy_and_reserved_argv_metadata() -> None:
    from pd_fleet.runtime_adapter import _runtime_timeout, TemplateRuntimeAdapter

    assert _runtime_timeout({}) == 10.0
    assert _runtime_timeout({"timeout_seconds": 30}) == 30.0
    for value in (0, 121, True, "30"):
        with pytest.raises(RuntimeConfigurationError) as exc:
            _runtime_timeout({"timeout_seconds": value})
        assert str(exc.value) == RuntimeErrorCode.INVALID_TIMEOUT.value

    envelope = RuntimeTaskEnvelope(
        "x", "do", _envelope().provider_profile, metadata={"timeout_seconds": 30, "label": "safe"}
    )
    adapter = TemplateRuntimeAdapter("hermes/openai-codex", envelope.provider_profile,
                                    ("tool", "{label}", "{prompt}"))
    assert adapter.build_argv(envelope) == ("tool", "safe", "do")
    reserved = TemplateRuntimeAdapter("hermes/openai-codex", envelope.provider_profile,
                                      ("tool", "{timeout_seconds}"))
    with pytest.raises(RuntimeConfigurationError):
        reserved.build_argv(envelope)
