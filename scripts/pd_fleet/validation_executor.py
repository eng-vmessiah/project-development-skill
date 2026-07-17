"""Fail-closed validation declarations and an explicit sandbox boundary.

This module does *not* provide a native subprocess sandbox.  ValidationExecutor
can only execute when a trusted ``sandbox_runner`` capability is explicitly
injected by its caller.  A boolean policy flag is not a capability and never
causes process creation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
import os
from pathlib import Path
import re
import stat as fs_stat
from typing import Callable, Mapping, Sequence, Any

from .contracts import _EXTERNAL_URL, _redact_paths, _redact_sensitive_text


class ValidationError(ValueError):
    """Stable, non-sensitive validation failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"validation rejected: {code}")


class ValidationExecutionError(RuntimeError):
    """Stable execution failure; details are deliberately not exposed."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"validation execution failed: {code}")


@dataclass(frozen=True)
class ValidationResult:
    status: str
    argv: tuple[str, ...] = ()
    executed: bool = False
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error_code: str | None = None
    truncated_stdout: bool = False
    truncated_stderr: bool = False


_CREDENTIAL_NAME = re.compile(r"(?i)(?:secret|token|password|credential|api[_-]?key|access[_-]?(?:key|token)|private[_-]?key|authorization|bearer)")
_URL = re.compile(r"(?i)\b(?:https?|ftp|ws|wss)://")
_META = re.compile(r"[;&|<>$`\n\r]|\$\(|&&|\|\|")


def _bounded(value: Any, limit: int) -> tuple[str, bool]:
    if type(value) is not str:
        raise TypeError("runner output must be string")
    return value[:limit], len(value) > limit


def _redact_output(value: str) -> str:
    """Apply the contracts redaction rules to untrusted runner output."""
    # URLs must be removed before path redaction (the latter would otherwise
    # leave a misleading ``https:[PATH REDACTED]`` fragment).
    return _redact_sensitive_text(_redact_paths(_EXTERNAL_URL.sub("[URL REDACTED]", value)))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_argv(argv: Sequence[str], *, root: Path | None = None) -> tuple[str, ...]:
    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
        raise ValidationError("argv_must_be_sequence")
    if not argv:
        raise ValidationError("argv_empty")
    result = []
    for index, arg in enumerate(argv):
        if type(arg) is not str or not arg:
            raise ValidationError("argv_invalid_argument")
        if "\x00" in arg:
            raise ValidationError("argv_nul")
        if _META.search(arg):
            raise ValidationError("shell_syntax")
        if index == 0:
            executable = Path(arg)
            if not executable.is_absolute():
                raise ValidationError("executable_not_absolute")
            if root is None:
                # Policy construction performs the root/pinning check; bare
                # declarations are syntax-checked without an execution root.
                result.append(arg)
                continue
            # Do not resolve a symlink here: the executable must itself be a
            # regular, non-symlink file pinned beneath the policy root.
            if executable.is_symlink() or not executable.is_file():
                raise ValidationError("executable_invalid")
            try:
                resolved = executable.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise ValidationError("executable_invalid") from exc
            if not _inside(resolved, root) or resolved != executable:
                raise ValidationError("executable_outside_root")
        result.append(arg)
    return tuple(result)


@dataclass(frozen=True)
class ValidationPolicy:
    """Immutable execution policy; defaults deny every process.

    ``sandbox_capability`` is retained as a compatibility/policy marker, but
    is intentionally insufficient for execution.  A trusted runner must be
    supplied to :class:`ValidationExecutor` separately.
    """

    allowlist: tuple[tuple[str, ...], ...] = ()
    root: str | os.PathLike[str] | None = None
    cwd: str | os.PathLike[str] | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    output_limits: tuple[int, int] = (65536, 65536)
    sandbox_capability: bool = False
    _executable_pins: tuple[tuple[str, int, int, int, int], ...] = field(default=(), init=False, repr=False, compare=False)
    _root_pin: tuple[int, int, int, int] | None = field(default=None, init=False, repr=False, compare=False)
    _cwd_pin: tuple[int, int, int, int] | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.timeout_seconds) not in (int, float) or isinstance(self.timeout_seconds, bool) \
                or self.timeout_seconds <= 0 or self.timeout_seconds > 3600:
            raise ValidationError("invalid_timeout")
        if (not isinstance(self.output_limits, tuple) or len(self.output_limits) != 2
                or any(type(x) is not int or x <= 0 for x in self.output_limits)):
            raise ValidationError("invalid_output_limits")
        root_path: Path | None = None
        if self.root is None or self.cwd is None:
            if self.root is not None or self.cwd is not None:
                raise ValidationError("root_cwd_required")
        else:
            try:
                raw_root = Path(self.root)
                raw_cwd = Path(self.cwd)
                # Check links before resolve: resolving a symlink root would
                # otherwise silently redefine the policy boundary.
                if raw_root.is_symlink():
                    raise ValidationError("root_invalid")
                if raw_cwd.is_symlink():
                    raise ValidationError("cwd_outside_root")
                root_lstat = raw_root.stat(follow_symlinks=False)
                cwd_lstat = raw_cwd.stat(follow_symlinks=False)
                if not fs_stat.S_ISDIR(root_lstat.st_mode) or not fs_stat.S_ISDIR(cwd_lstat.st_mode):
                    raise ValidationError("cwd_unavailable")
                root_path = raw_root.resolve(strict=True)
                cwd_path = raw_cwd.resolve(strict=True)
            except (OSError, RuntimeError, TypeError) as exc:
                raise ValidationError("cwd_unavailable") from exc
            if not root_path.is_dir() or not cwd_path.is_dir() or not _inside(cwd_path, root_path):
                raise ValidationError("cwd_outside_root")
            object.__setattr__(self, "root", str(root_path))
            object.__setattr__(self, "cwd", str(cwd_path))
            root_stat = root_path.stat(follow_symlinks=False)
            cwd_stat = cwd_path.stat(follow_symlinks=False)
            if not fs_stat.S_ISDIR(root_stat.st_mode) or not fs_stat.S_ISDIR(cwd_stat.st_mode):
                raise ValidationError("cwd_unavailable")
            object.__setattr__(self, "_root_pin", (root_stat.st_dev, root_stat.st_ino, root_stat.st_size, root_stat.st_mtime_ns))
            object.__setattr__(self, "_cwd_pin", (cwd_stat.st_dev, cwd_stat.st_ino, cwd_stat.st_size, cwd_stat.st_mtime_ns))
        normalized = []
        pins = []
        for item in self.allowlist:
            argv = _validate_argv(item, root=root_path)
            normalized.append(argv)
            if root_path is not None and Path(argv[0]).is_absolute():
                stat = os.stat(argv[0], follow_symlinks=False)
                pins.append((argv[0], stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns))
        object.__setattr__(self, "allowlist", tuple(normalized))
        object.__setattr__(self, "_executable_pins", tuple(pins))
        if not isinstance(self.env, Mapping):
            raise ValidationError("invalid_environment")
        clean_env = {}
        for key, value in self.env.items():
            if type(key) is not str or not key or "\x00" in key or _CREDENTIAL_NAME.search(key):
                raise ValidationError("unsafe_environment")
            if type(value) is not str or "\x00" in value or _URL.search(value):
                raise ValidationError("unsafe_environment")
            clean_env[key] = value
        object.__setattr__(self, "env", MappingProxyType(clean_env))


class ValidationExecutor:
    """Validate declarations and execute only through an explicit capability.

    ``runner`` is accepted as a backwards-compatible spelling for the
    capability.  It is never a native subprocess fallback; callers remain
    responsible for providing a trusted sandbox implementation.  A runner
    callable (or object exposing ``run``) must honor ``shell=False`` and the
    supplied cwd, environment, timeout, and output limits.
    """

    def __init__(self, policy: ValidationPolicy | None = None, *,
                 sandbox_runner: Callable[..., Mapping[str, Any]] | Any | None = None,
                 runner: Callable[..., Mapping[str, Any]] | Any | None = None):
        if sandbox_runner is not None and runner is not None and sandbox_runner is not runner:
            raise ValidationError("duplicate_sandbox_runner")
        self.policy = policy
        self.sandbox_runner = sandbox_runner if sandbox_runner is not None else runner
        if self.sandbox_runner is not None and not (callable(self.sandbox_runner) or callable(getattr(self.sandbox_runner, "run", None))):
            raise ValidationError("invalid_sandbox_runner")

    def declare(self, argv: Sequence[str]) -> ValidationResult:
        checked = _validate_argv(argv)
        return ValidationResult(status="declared", argv=checked)

    def execute(self, argv: Sequence[str], *, declarative: bool = False) -> ValidationResult:
        checked = _validate_argv(argv)
        if declarative:
            return ValidationResult(status="declared", argv=checked)
        policy = self.policy
        if policy is None:
            return ValidationResult(status="denied", argv=checked, error_code="default_deny")
        if checked not in policy.allowlist:
            return ValidationResult(status="denied", argv=checked, error_code="not_allowlisted")
        if self.sandbox_runner is None:
            return ValidationResult(status="denied", argv=checked, error_code="sandbox_unavailable")
        if policy.root is None or policy.cwd is None:
            return ValidationResult(status="denied", argv=checked, error_code="sandbox_unavailable")
        root, cwd = Path(policy.root), Path(policy.cwd)
        try:
            if root.is_symlink() or cwd.is_symlink():
                return ValidationResult(status="denied", argv=checked, error_code="cwd_outside_root")
            root_stat = root.stat(follow_symlinks=False)
            cwd_stat = cwd.stat(follow_symlinks=False)
            root_pin = (root_stat.st_dev, root_stat.st_ino, root_stat.st_size, root_stat.st_mtime_ns)
            cwd_pin = (cwd_stat.st_dev, cwd_stat.st_ino, cwd_stat.st_size, cwd_stat.st_mtime_ns)
            if (not fs_stat.S_ISDIR(root_stat.st_mode) or not fs_stat.S_ISDIR(cwd_stat.st_mode)
                    or root_pin != policy._root_pin or cwd_pin != policy._cwd_pin
                    or not _inside(cwd.resolve(strict=True), root.resolve(strict=True))):
                return ValidationResult(status="denied", argv=checked, error_code="cwd_outside_root")
            for path, dev, ino, size, mtime_ns in policy._executable_pins:
                stat = os.stat(path, follow_symlinks=False)
                if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != (dev, ino, size, mtime_ns):
                    return ValidationResult(status="denied", argv=checked, error_code="executable_changed")
        except (OSError, RuntimeError):
            return ValidationResult(status="denied", argv=checked, error_code="executable_unavailable")
        try:
            call = self.sandbox_runner if callable(self.sandbox_runner) else self.sandbox_runner.run
            raw = call(checked, cwd=str(cwd), env=policy.env,
                       timeout=policy.timeout_seconds, output_limits=policy.output_limits,
                       shell=False)
        except Exception:
            return ValidationResult(status="failed", argv=checked, executed=True, error_code="runner_failed")
        try:
            if not isinstance(raw, Mapping):
                raise TypeError("runner result")
            required = ("returncode", "stdout", "stderr")
            if any(key not in raw for key in required):
                raise TypeError("runner result missing field")
            returncode = raw["returncode"]
            stdout = raw["stdout"]
            stderr = raw["stderr"]
            timed_out = raw.get("timed_out", False)
            truncated = raw.get("truncated", False)
            truncated_stdout = raw.get("truncated_stdout", False)
            truncated_stderr = raw.get("truncated_stderr", False)
            runner_status = raw.get("status")
            runner_error = raw.get("error")
            if type(returncode) is not int or type(timed_out) is not bool \
                    or type(truncated) is not bool or type(truncated_stdout) is not bool \
                    or type(truncated_stderr) is not bool or type(stdout) is not str \
                    or type(stderr) is not str or (runner_status is not None and type(runner_status) is not str) \
                    or (runner_error is not None and type(runner_error) is not str):
                raise TypeError("runner result type")
            out, out_truncated = _bounded(stdout, policy.output_limits[0])
            err, err_truncated = _bounded(stderr, policy.output_limits[1])
            out = _redact_output(out)
            err = _redact_output(err)
            return ValidationResult(status="timeout" if timed_out else ("passed" if raw.get("returncode") == 0 else "failed"),
                                    argv=checked, executed=True, returncode=returncode,
                                    stdout=out, stderr=err, timed_out=timed_out,
                                    truncated_stdout=truncated or truncated_stdout or out_truncated,
                                    truncated_stderr=truncated or truncated_stderr or err_truncated)
        except Exception:
            return ValidationResult(status="failed", argv=checked, executed=True, error_code="runner_contract_error")


DeclarativeValidation = ValidationResult
