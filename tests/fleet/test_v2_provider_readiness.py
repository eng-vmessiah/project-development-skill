"""Adversarial tests for capability-gated, non-authenticating readiness."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.provider import CommandMetadata, RuntimePolicy, RuntimeProviderProfile
from pd_fleet.provider_readiness import (
    LocalRuntimeReadinessProbe, ProbeStatus, ProviderReadinessError,
    probe_provider_readiness,
)
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
    assert result.output == ""
    assert result.as_dict()["output"] == ""
    assert '"output":""' in result.serialize()


def test_provider_probe_discards_pii_output(tmp_path: Path) -> None:
    exe = tmp_path / "tool"
    exe.write_text("#!/bin/sh\nprintf 'token=private-secret https://private.example /home/user/key\\n'\n")
    exe.chmod(0o700)
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(exe), "--version"),))
    result = probe_provider_readiness(_profile("codex-cli", "codex-cli", str(exe)),
        runner=runner, capability=runner.capability, executable=str(exe), cwd=str(tmp_path))
    assert result.output == ""
    assert "private-secret" not in result.serialize()
    assert "private.example" not in result.serialize()


def test_default_runner_combined_output_cap_is_exactly_4096(tmp_path: Path) -> None:
    exe = tmp_path / "tool"
    exe.write_text("#!/bin/sh\nprintf '%*s' 4097 ''\n")
    exe.chmod(0o700)
    raw = LocalRuntimeReadinessProbe._default_runner(
        (str(exe),), timeout=2.0, output_limits=(4096, 4096), env={})
    assert raw["status"] == "output_limit"
    assert len(raw["stdout"].encode("utf-8")) == 4096


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


def test_local_probe_uses_only_fixed_auth_commands(monkeypatch) -> None:
    class FakeRunner:
        def __init__(self, output):
            self.output = output
            self.calls = []

        def run(self, argv, **kwargs):
            self.calls.append((argv, kwargs))
            return {"status": "passed", "returncode": 0, "stdout": self.output}

    expected = {
        "openai-codex": ("hermes", "auth", "status", "openai-codex"),
        "codex-cli": ("codex", "login", "status"),
        "opencode-go": ("opencode", "providers", "list"),
        "claude-code": ("claude", "auth", "status", "--json"),
    }
    monkeypatch.setattr("pd_fleet.provider_readiness.shutil.which", lambda name: "/bin/" + name)
    outputs = {
        "openai-codex": "openai-codex: logged in",
        "codex-cli": "Logged in using ChatGPT",
        "opencode-go": "OpenCode Go api\n2 credentials",
        "claude-code": '{"loggedIn": true, "email": "private@example.test"}',
    }
    for runtime, suffix in expected.items():
        runner = FakeRunner(outputs[runtime])
        result = LocalRuntimeReadinessProbe(runner).probe(runtime)
        assert result.authenticated and result.status == "authenticated"
        assert runner.calls[0][0] == ("/bin/" + suffix[0],) + suffix[1:]
        assert runner.calls[0][1]["env"] == {}
        assert runner.calls[0][1]["timeout"] <= 10
        assert "email" not in repr(result)


def test_local_probe_rejects_ambiguous_auth_output(monkeypatch) -> None:
    class FakeRunner:
        def __init__(self, output):
            self.output = output

        def run(self, argv, **kwargs):
            return {"status": "passed", "returncode": 0, "stdout": self.output}

    monkeypatch.setattr("pd_fleet.provider_readiness.shutil.which", lambda _: "/bin/tool")
    ambiguous_outputs = {
        "openai-codex": "logged in",
        "codex-cli": "ChatGPT",
    }
    for runtime, output in ambiguous_outputs.items():
        result = LocalRuntimeReadinessProbe(FakeRunner(output)).probe(runtime)
        assert not result.authenticated and result.status == "auth_absent"


def test_local_probe_rejects_opencode_missing_credentials_or_errors(monkeypatch) -> None:
    class FakeRunner:
        def __init__(self, output):
            self.output = output

        def run(self, argv, **kwargs):
            return {"status": "passed", "returncode": 0, "stdout": self.output}

    monkeypatch.setattr("pd_fleet.provider_readiness.shutil.which", lambda _: "/bin/tool")
    for output in (
        "OpenCode Go api\n0 credentials",
        "OpenCode Go api\nError loading credentials",
        "OpenCode Go api\nno credentials",
        "OpenCode Go api\ncredential data",
    ):
        result = LocalRuntimeReadinessProbe(FakeRunner(output)).probe("opencode-go")
        assert not result.authenticated and result.status == "auth_absent"


def test_local_probe_discards_output_and_fails_closed(monkeypatch) -> None:
    class FakeRunner:
        def run(self, argv, **kwargs):
            return {"status": "passed", "returncode": 0,
                    "stdout": '{"loggedIn": false, "email": "secret@example.test"}'}

    monkeypatch.setattr("pd_fleet.provider_readiness.shutil.which", lambda _: "/bin/tool")
    result = LocalRuntimeReadinessProbe(FakeRunner()).probe("claude-code")
    assert not result.authenticated and result.status == "auth_absent"
    assert "secret@example.test" not in repr(result)
