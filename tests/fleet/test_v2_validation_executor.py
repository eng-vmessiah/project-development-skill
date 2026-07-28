import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.validation_executor import (
    DeclarativeValidation, ValidationError, ValidationExecutor, ValidationPolicy,
)


def command(tmp_path, *args):
    executable = tmp_path / "validator"
    if not executable.exists():
        executable.write_text("validator")
    return (str(executable), *args)


def policy(tmp_path, *, allow=None, **kwargs):
    if allow is None:
        allow = command(tmp_path, "--check")
    options = {"env": {"LANG": "C"}, "sandbox_capability": True}
    options.update(kwargs)
    return ValidationPolicy(allowlist=(tuple(allow),), root=tmp_path, cwd=tmp_path,
                            **options)


def test_default_deny_and_fail_closed_without_sandbox(tmp_path):
    calls = []
    executor = ValidationExecutor(policy=ValidationPolicy(allowlist=((str(tmp_path / "validator"),),)),
                                  runner=lambda *a, **k: calls.append((a, k)))
    result = executor.execute(command(tmp_path))
    assert result.status == "denied" and result.error_code == "sandbox_unavailable"
    assert not result.executed and calls == []
    assert ValidationExecutor(runner=lambda: pytest.fail("must not run")).execute(command(tmp_path)).error_code == "default_deny"


def test_declarative_never_executes_even_with_full_policy(tmp_path):
    calls = []
    executor = ValidationExecutor(policy=policy(tmp_path), runner=lambda *a, **k: calls.append(1))
    result = executor.execute(command(tmp_path, "--check"), declarative=True)
    assert isinstance(result, DeclarativeValidation)
    assert result.status == "declared" and not result.executed and calls == []
    assert executor.declare(command(tmp_path, "--check")).status == "declared"


@pytest.mark.parametrize("argv", [(), "validator", ("validator", ""), ("validator", "x\x00y"), ("validator", 1)])
def test_argv_is_structured_and_strict(argv, tmp_path):
    with pytest.raises(ValidationError):
        ValidationExecutor().execute(argv)


@pytest.mark.parametrize("arg", ["validator; touch pwned", "validator && evil", "$(evil)", "x|evil", "x>out"])
def test_shell_metacharacters_rejected(arg, tmp_path):
    (tmp_path / "validator").write_text("validator")
    with pytest.raises(ValidationError, match="shell_syntax"):
        ValidationPolicy(allowlist=((str(tmp_path / "validator"), arg),), root=tmp_path, cwd=tmp_path)


def test_non_allowlisted_argv_is_denied_without_runner(tmp_path):
    calls = []
    executor = ValidationExecutor(policy=policy(tmp_path), runner=lambda *a, **k: calls.append(1))
    result = executor.execute(command(tmp_path, "--other"))
    assert result.status == "denied" and result.error_code == "not_allowlisted" and calls == []


def test_root_cwd_containment_and_symlink_safety(tmp_path):
    outside = tmp_path / "outside"; outside.mkdir()
    root = tmp_path / "root"; root.mkdir()
    link = root / "link"; link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValidationError, match="cwd_outside_root"):
        ValidationPolicy(allowlist=(("validator",),), root=root, cwd=link)


def test_environment_is_minimal_and_rejects_secrets_and_urls(tmp_path):
    with pytest.raises(ValidationError, match="unsafe_environment"):
        ValidationPolicy(root=tmp_path, cwd=tmp_path, env={"API_TOKEN": "x"})
    with pytest.raises(ValidationError, match="unsafe_environment"):
        ValidationPolicy(root=tmp_path, cwd=tmp_path, env={"CHECK_URL": "https://example.invalid"})


def test_injected_runner_gets_only_structured_safe_arguments(tmp_path):
    seen = {}
    def runner(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        return {"returncode": 0, "stdout": "ok", "stderr": ""}
    result = ValidationExecutor(policy=policy(tmp_path), runner=runner).execute(command(tmp_path, "--check"))
    assert result.status == "passed" and result.executed and result.stdout == "ok"
    assert seen["argv"] == command(tmp_path, "--check") and seen["cwd"] == str(tmp_path)
    assert seen["env"] == {"LANG": "C"} and seen["timeout"] == 10.0


def test_timeout_is_structured_and_kill_reap_is_runner_responsibility(tmp_path):
    calls = []
    def runner(*args, **kwargs):
        calls.append(kwargs)
        return {"returncode": -9, "timed_out": True, "stdout": "partial", "stderr": ""}
    result = ValidationExecutor(policy=policy(tmp_path, timeout_seconds=0.1), runner=runner).execute(command(tmp_path, "--check"))
    assert result.status == "timeout" and result.timed_out and result.returncode == -9
    assert calls[0]["timeout"] == 0.1


def test_stdout_and_stderr_are_bounded(tmp_path):
    def runner(*args, **kwargs):
        return {"returncode": 1, "stdout": "123456", "stderr": "abcdef"}
    result = ValidationExecutor(policy=policy(tmp_path, output_limits=(3, 2)), runner=runner).execute(command(tmp_path, "--check"))
    assert result.status == "failed" and result.stdout == "123" and result.stderr == "ab"
    assert result.truncated_stdout and result.truncated_stderr


def test_runner_errors_are_stable_and_sanitized(tmp_path):
    def runner(*args, **kwargs):
        raise RuntimeError("/secret/path and token=abc")
    result = ValidationExecutor(policy=policy(tmp_path), runner=runner).execute(command(tmp_path, "--check"))
    assert result.error_code == "runner_failed" and "/secret/path" not in str(result) and "abc" not in str(result)


def test_boolean_sandbox_marker_never_substitutes_for_explicit_runner(tmp_path):
    p = policy(tmp_path, sandbox_capability=True)
    result = ValidationExecutor(policy=p).execute(command(tmp_path, "--check"))
    assert result.error_code == "sandbox_unavailable" and not result.executed


def test_policy_environment_is_snapshot_and_runner_cannot_mutate_it(tmp_path):
    source = {"LANG": "C"}
    p = policy(tmp_path, env=source)
    source["LANG"] = "evil"
    seen = []
    def runner(argv, **kwargs):
        seen.append(kwargs)
        with pytest.raises(TypeError):
            kwargs["env"]["NEW"] = "x"
        return {"returncode": 0, "stdout": "", "stderr": ""}
    assert ValidationExecutor(policy=p, sandbox_runner=runner).execute(command(tmp_path, "--check")).status == "passed"
    assert seen[0]["env"]["LANG"] == "C"


def test_absolute_executable_is_pinned_regular_and_non_symlink(tmp_path):
    executable = tmp_path / "validator"
    executable.write_text("validator")
    p = ValidationPolicy(allowlist=((str(executable),),), root=tmp_path, cwd=tmp_path,
                         env={}, sandbox_capability=True)
    executable.unlink()
    executable.write_text("replacement")
    result = ValidationExecutor(policy=p, sandbox_runner=lambda *a, **k: {"returncode": 0}).execute((str(executable),))
    assert result.status == "denied" and result.error_code == "executable_changed"


def test_child_executable_replacement_is_reported_before_cwd_mutation(tmp_path):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    executable = cwd / "validator"
    executable.write_text("validator")
    p = ValidationPolicy(allowlist=((str(executable),),), root=tmp_path, cwd=cwd,
                         env={}, sandbox_capability=True)
    executable.unlink()
    executable.write_text("replacement")
    result = ValidationExecutor(policy=p, sandbox_runner=lambda *a, **k: {"returncode": 0}).execute((str(executable),))
    assert result.status == "denied" and result.error_code == "executable_changed"


def test_cwd_directory_replacement_is_rejected_fail_closed(tmp_path):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    executable = cwd / "validator"
    executable.write_text("validator")
    p = ValidationPolicy(allowlist=((str(executable),),), root=tmp_path, cwd=cwd,
                         env={}, sandbox_capability=True)
    executable.unlink()
    retired = tmp_path / "retired-cwd"
    cwd.rename(retired)
    cwd.mkdir()
    executable = cwd / "validator"
    executable.write_text("validator")
    result = ValidationExecutor(policy=p, sandbox_runner=lambda *a, **k: {"returncode": 0}).execute((str(executable),))
    assert result.status == "denied" and result.error_code == "cwd_outside_root"


def test_runner_contract_is_shell_false(tmp_path):
    seen = {}
    def runner(argv, **kwargs):
        seen.update(kwargs)
        return {"returncode": 0, "stdout": "", "stderr": ""}
    assert ValidationExecutor(policy=policy(tmp_path), sandbox_runner=runner).execute(command(tmp_path, "--check")).status == "passed"
    assert seen["shell"] is False


def test_executable_must_be_absolute_even_for_declarations():
    with pytest.raises(ValidationError, match="executable_not_absolute"):
        ValidationExecutor().declare(("validator", "--check"))


def test_root_symlink_is_rejected_before_resolution(tmp_path):
    real_root = tmp_path / "real"
    real_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ValidationError, match="root_invalid"):
        ValidationPolicy(root=linked_root, cwd=linked_root, env={})


def test_runner_output_is_redacted_after_bounding(tmp_path):
    def runner(*args, **kwargs):
        return {"returncode": 0, "stdout": "https://example.invalid /home/alice secret=top-secret", "stderr": "C:\\Users\\alice\\token=hidden"}
    result = ValidationExecutor(policy=policy(tmp_path, output_limits=(200, 200)), runner=runner).execute(command(tmp_path, "--check"))
    assert "example.invalid" not in result.stdout and "/home/alice" not in result.stdout and "top-secret" not in result.stdout
    assert "C:\\Users\\alice" not in result.stderr and "hidden" not in result.stderr


@pytest.mark.parametrize("field,value", [
    ("returncode", True), ("timed_out", 1), ("truncated_stdout", 1),
    ("truncated_stderr", 1), ("stdout", b"bytes"), ("stderr", 7),
])
def test_malformed_runner_result_is_contract_error_without_coercion(tmp_path, field, value):
    result_data = {"returncode": 0, "stdout": "", "stderr": ""}
    result_data[field] = value
    result = ValidationExecutor(policy=policy(tmp_path), runner=lambda *a, **k: result_data).execute(command(tmp_path, "--check"))
    assert result.error_code == "runner_contract_error" and result.returncode is None
