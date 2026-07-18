from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import time

import pytest

try:
    from scripts.pd_fleet.sandbox import LocalSandboxRunner, SandboxCapability, SandboxConfigurationError
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).parents[2]))
    from scripts.pd_fleet.sandbox import LocalSandboxRunner, SandboxCapability, SandboxConfigurationError  # noqa: E402


def _tool(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_exact_allowlist_no_shell_and_explicit_env(tmp_path: Path):
    tool = _tool(tmp_path, "tool", "import os; print(os.getenv('SAFE', 'missing'))")
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(tool), "ok"),), env={"SAFE": "yes"})
    result = runner.run((str(tool), "ok"), cwd=tmp_path)
    assert result["status"] == "passed"
    assert result["stdout"] == "[SECRET REDACTED]\n"
    denied = runner.run((str(tool), "$(touch pwned)"), cwd=tmp_path)
    assert denied["status"] == "denied"
    assert not (tmp_path / "pwned").exists()


def test_rejects_symlink_and_credential_environment(tmp_path: Path):
    target = _tool(tmp_path, "tool", "print('ok')")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(SandboxConfigurationError):
        LocalSandboxRunner(tmp_path, allowlist=((str(link),),))
    with pytest.raises(SandboxConfigurationError):
        LocalSandboxRunner(tmp_path, allowlist=((str(target),),), env={"API_TOKEN": "no"})


def test_external_executable_requires_exact_trusted_pin(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    external = _tool(tmp_path, "external-tool", "print('external ok')")
    argv = (str(external), "--exact")
    with pytest.raises(SandboxConfigurationError):
        LocalSandboxRunner(root, allowlist=(argv,))
    runner = LocalSandboxRunner(root, allowlist=(argv,), trusted_executables=(str(external),))
    assert runner.trusted_executables == (str(external.resolve()),)
    assert runner.run(argv, cwd=root)["status"] == "passed"
    assert runner.run((str(external), "--different"), cwd=root)["error"] == "argv_not_allowlisted"


def test_trusted_executable_symlink_is_rejected(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    target = _tool(tmp_path, "external-tool", "print('ok')")
    link = tmp_path / "external-link"
    link.symlink_to(target)
    with pytest.raises(SandboxConfigurationError):
        LocalSandboxRunner(root, allowlist=((str(link),),), trusted_executables=(str(link),))


def test_external_trusted_runner_keeps_cwd_root_contained(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    external = _tool(tmp_path, "external-tool", "print('ok')")
    runner = LocalSandboxRunner(root, allowlist=((str(external),),), trusted_executables=(str(external),))
    result = runner.run((str(external),), cwd=tmp_path)
    assert result["status"] == "denied"
    assert result["error"] == "cwd_outside_root"


def test_output_is_bounded_and_timeout_kills_process_group(tmp_path: Path):
    tool = _tool(tmp_path, "tool", "import sys,time; print('x'*100); sys.stdout.flush(); time.sleep(10)")
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(tool),),), env={})
    result = runner.run((str(tool),), cwd=tmp_path, timeout=0.1, output_limits=(8, 8))
    assert result["status"] == "timeout"
    assert result["timed_out"] is True
    assert len(result["stdout"].encode()) <= 8
    assert result["truncated_stdout"] is True


def test_root_and_cwd_containment(tmp_path: Path):
    tool = _tool(tmp_path, "tool", "print('ok')")
    outside = tmp_path.parent
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(tool),),), env={})
    result = runner.run((str(tool),), cwd=outside)
    assert result["status"] == "denied"
    assert result["error"] == "cwd_outside_root"


def test_relative_cwd_is_rejected(tmp_path: Path):
    tool = _tool(tmp_path, "tool", "print('ok')")
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(tool),),), env={})
    result = runner.run((str(tool),), cwd=".")
    assert result["status"] == "denied"
    assert result["error"] == "cwd_not_absolute"


def test_environment_is_copied_and_read_only(tmp_path: Path):
    tool = _tool(tmp_path, "tool", "print('ok')")
    configured = {"SAFE": "before"}
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(tool),),), env=configured)
    configured["SAFE"] = "after"
    assert runner.env["SAFE"] == "before"
    with pytest.raises(TypeError):
        runner.env["SAFE"] = "changed"  # type: ignore[index]


def test_configured_environment_values_are_redacted(tmp_path: Path):
    tool = _tool(tmp_path, "tool", "import os; print(os.environ['SAFE'])")
    runner = LocalSandboxRunner(tmp_path, allowlist=((str(tool),),), env={"SAFE": "supersecret"})
    result = runner.run((str(tool),), cwd=str(tmp_path))
    assert result["status"] == "passed"
    assert "supersecret" not in result["stdout"]
    assert "[SECRET REDACTED]" in result["stdout"]


def test_network_is_fail_closed(tmp_path: Path):
    tool = _tool(tmp_path, "tool", "pass")
    with pytest.raises(SandboxConfigurationError):
        LocalSandboxRunner(tmp_path, allowlist=((str(tool),),), network=True)


def test_capability_is_runner_issued_unique_and_not_publicly_mintable(tmp_path: Path):
    tool = _tool(tmp_path, "tool", "pass")
    first = LocalSandboxRunner(tmp_path, allowlist=((str(tool),),), env={})
    second = LocalSandboxRunner(tmp_path, allowlist=((str(tool),),), env={})
    assert isinstance(first.capability, SandboxCapability)
    assert first.capability is not second.capability
    with pytest.raises(TypeError):
        SandboxCapability(object(), first)  # type: ignore[arg-type]

