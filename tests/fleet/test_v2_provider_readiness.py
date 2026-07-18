"""Adversarial tests for capability-gated, non-authenticating readiness."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.provider import CommandMetadata, RuntimePolicy, RuntimeProviderProfile
from pd_fleet.provider_readiness import ProbeStatus, ProviderReadinessError, probe_provider_readiness
from pd_fleet.sandbox import LocalSandboxRunner


def _profile(runtime: str, provider: str, executable: str) -> RuntimeProviderProfile:
    return RuntimeProviderProfile(provider, runtime, auth_ref="runtime:default",
        command=CommandMetadata(executable), capabilities=("read",),
        policy=RuntimePolicy(enabled=True, allowed_capabilities=("read",)))


def test_version_probe_is_fixed_and_does_not_claim_auth(tmp_path: Path) -> None:
    exe = tmp_path / "tool"
    exe.write_text("#!/bin/sh\nprintf 'version token=private /home/user/key\\n'\n")
    exe.chmod(0o700)
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(exe), "--version"),))
    result = probe_provider_readiness(_profile("codex-cli", "codex-cli", str(exe)),
        runner=runner, capability=runner.capability, executable=str(exe), cwd=str(tmp_path))
    assert result.status is ProbeStatus.RUNTIME_PRESENT
    assert result.argv == ("[PATH REDACTED]", "--version")
    assert str(exe) not in result.serialize()
    assert "private" not in result.output and "[SECRET REDACTED]" in result.output


def test_explicit_injected_auth_is_the_only_way_to_be_available(tmp_path: Path) -> None:
    exe = tmp_path / "tool"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o700)
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(exe), "--version"),))
    profile = _profile("opencode-go", "opencode", str(exe))
    assert probe_provider_readiness(profile, runner=runner, capability=runner.capability, executable=str(exe), cwd=str(tmp_path)).status is ProbeStatus.RUNTIME_PRESENT
    assert probe_provider_readiness(profile, runner=runner, capability=runner.capability, executable=str(exe), cwd=str(tmp_path), auth_result=True).status is ProbeStatus.AVAILABLE


def test_wrong_capability_and_runner_outcomes_fail_closed(tmp_path: Path) -> None:
    exe = tmp_path / "tool"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o700)
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(exe), "--version"),))
    profile = _profile("claude-code", "claude-code", str(exe))
    try:
        other = LocalSandboxRunner(tmp_path, allowlist=((str(exe), "--version"),))
        probe_provider_readiness(profile, runner=runner, capability=other.capability)
        assert False
    except ProviderReadinessError as exc:
        assert exc.code == "capability_required"


def test_status_command_cannot_inject_arguments(tmp_path: Path) -> None:
    exe = tmp_path / "tool"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o700)
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(exe), "--version"),))
    profile = _profile("openai-codex", "hermes", str(exe))
    try:
        probe_provider_readiness(profile, runner=runner, capability=runner.capability,
                                 executable=str(exe), status_command=("status;login",))
        assert False
    except ProviderReadinessError as exc:
        assert exc.code == "invalid_status_command"


def test_runner_authentication_fields_are_not_trusted(tmp_path: Path) -> None:
    exe = tmp_path / "tool"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o700)

    class LyingRunner(LocalSandboxRunner):
        def run(self, *args, **kwargs):
            return {"status": "passed", "authenticated": True, "auth": True, "stdout": ""}

    runner = LyingRunner(tmp_path, allowlist=((str(exe), "--version"),))
    result = probe_provider_readiness(_profile("codex-cli", "codex-cli", str(exe)),
        runner=runner, capability=runner.capability, executable=str(exe), cwd=str(tmp_path))
    assert result.status is ProbeStatus.RUNTIME_PRESENT


def test_status_command_accepts_only_fixed_version_argv(tmp_path: Path) -> None:
    exe = tmp_path / "tool"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o700)
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(exe), "--version"),))
    profile = _profile("codex-cli", "codex-cli", str(exe))
    result = probe_provider_readiness(profile, runner=runner, capability=runner.capability,
        executable=str(exe), status_command=("--version",))
    assert result.argv == ("[PATH REDACTED]", "--version")
