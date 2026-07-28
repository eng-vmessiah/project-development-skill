"""Small, fail-closed local process runner for validation tools.

This is *not* a kernel sandbox.  It provides the process-level contract needed
by the validation boundary: exact argv allowlisting, pinned executables,
root/cwd containment, an explicit environment, bounded output, and timeout
cleanup.  Callers needing protection from a malicious executable must use a
real container/VM or a platform sandbox; this module deliberately refuses to
pretend otherwise.

Linux/WSL is the supported target.  Shell parsing is never used.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
import math
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time
from types import MappingProxyType
from typing import Any

_CREDENTIAL = re.compile(
    r"(?i)(?:secret|token|password|credential|api[_-]?key|access[_-]?(?:key|token)|private[_-]?key|authorization|bearer)"
)
_META = re.compile(r"[;&|<>$`\n\r]|\$\(|&&|\|\|")
_URL = re.compile(r"(?i)\b(?:https?|ftp|ws|wss)://")


_CAPABILITY_ISSUER = object()


class SandboxCapability:
    """Opaque proof issued by a LocalSandboxRunner and bound to that runner."""
    __slots__ = ("_owner",)

    def __init__(self, issuer: object, owner: object) -> None:
        if issuer is not _CAPABILITY_ISSUER:
            raise TypeError("sandbox capability is runner-issued")
        self._owner = owner


def _issue_capability(owner: object) -> SandboxCapability:
    return SandboxCapability(_CAPABILITY_ISSUER, owner)


class SandboxConfigurationError(ValueError):
    """Invalid or unsafe runner configuration (message contains only a code)."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"sandbox configuration rejected: {code}")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _pin(path: Path) -> tuple[int, int, int, int, int]:
    st = path.stat(follow_symlinks=False)
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_mode


def _safe_text(data: bytes, limit: int, secrets: Sequence[str] = ()) -> tuple[str, bool]:
    clipped = data[:limit]
    # Replacement is deterministic and cannot raise on hostile bytes.
    text = _redact(clipped.decode("utf-8", errors="replace"), secrets)
    encoded = text.encode("utf-8")
    if len(encoded) > limit:
        text = encoded[:limit].decode("utf-8", errors="ignore")
    return text, len(data) > limit


def _redact(text: str, secrets: Sequence[str] = ()) -> str:
    # Never expose URLs or path-like values from tool output.  Credential-like
    # output is intentionally not guessed; output should be treated as public
    # only after the caller's own policy has approved the tool.
    # Redact configured values first, including values which are not URL-like.
    # Empty values are ignored to avoid turning every output string into a tag.
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "[SECRET REDACTED]")
    text = _URL.sub("[URL REDACTED]", text)
    return re.sub(r"(?<![\w.])(?:~[/\\]|/)[^\s\"'<>;,]+", "[PATH REDACTED]", text)


class LocalSandboxRunner:
    """Run only predeclared absolute executables beneath ``tool_root``.

    ``allowlist`` is a collection of complete argv tuples.  A run must match
    one tuple exactly; arguments are never interpreted as shell syntax.
    ``env`` is the complete child environment (the parent environment is never
    inherited).  ``network=False`` is the default.  ``network=True`` is an explicit broad
    egress mode for a provider_network-authorized runner; this class does not
    create a network namespace or provide an allowlist.
    """

    @property
    def tool_root(self) -> Path:
        return self._tool_root

    @property
    def allowlist(self) -> frozenset[tuple[str, ...]]:
        return self._allowlist

    @property
    def env(self) -> Mapping[str, str]:
        """Read-only compatibility view of the explicit child environment."""
        return self._env

    @property
    def path_roots(self) -> Mapping[str, str]:
        return self._path_roots

    @property
    def secrets(self) -> tuple[str, ...]:
        return self._secrets

    @property
    def network(self) -> bool:
        """Whether this runner was explicitly configured for broad egress."""
        return self._network

    @property
    def trusted_executables(self) -> tuple[str, ...]:
        """Immutable, explicitly pinned executable exceptions outside ``tool_root``."""
        return self._trusted_executables

    def __init__(self, tool_root: str | os.PathLike[str], *,
                 allowlist: Sequence[Sequence[str]] = (),
                 env: Mapping[str, str] | None = None,
                 network: bool = False, secrets: Sequence[str] = (),
                 path_roots: Mapping[str, str | os.PathLike[str]] | None = None,
                 trusted_executables: Sequence[str] = ()):
        if type(network) is not bool:
            raise SandboxConfigurationError("network_invalid")
        root = Path(tool_root)
        try:
            if root.is_symlink() or not root.is_dir():
                raise SandboxConfigurationError("tool_root_invalid")
            root = root.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise SandboxConfigurationError("tool_root_invalid") from exc
        # Keep validated configuration private/read-only after construction.
        self._tool_root = root
        self._network = network
        self._root_pin = _pin(root)
        if (isinstance(trusted_executables, (str, bytes))
                or not isinstance(trusted_executables, Sequence)):
            raise SandboxConfigurationError("trusted_executables_invalid")
        trusted: list[str] = []
        for value in trusted_executables:
            if type(value) is not str or not value or "\x00" in value:
                raise SandboxConfigurationError("trusted_executable_invalid")
            executable = Path(value)
            if not executable.is_absolute():
                raise SandboxConfigurationError("trusted_executable_not_absolute")
            try:
                if executable.is_symlink():
                    raise SandboxConfigurationError("trusted_executable_invalid")
                resolved = executable.resolve(strict=True)
                st = executable.stat(follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode) or not (st.st_mode & stat.S_IXUSR):
                    raise SandboxConfigurationError("trusted_executable_invalid")
            except SandboxConfigurationError:
                raise
            except (OSError, RuntimeError) as exc:
                raise SandboxConfigurationError("trusted_executable_invalid") from exc
            trusted.append(str(resolved))
        self._trusted_executables = tuple(dict.fromkeys(trusted))
        trusted_set = frozenset(self._trusted_executables)
        if isinstance(allowlist, (str, bytes)) or not isinstance(allowlist, Sequence):
            raise SandboxConfigurationError("allowlist_invalid")
        normalized: list[tuple[str, ...]] = []
        pins: dict[str, tuple[int, int, int, int, int]] = {}
        for item in allowlist:
            if isinstance(item, (str, bytes)) or not isinstance(item, Sequence) or not item:
                raise SandboxConfigurationError("argv_invalid")
            argv = tuple(item)
            if any(type(arg) is not str or not arg or "\x00" in arg or _META.search(arg) for arg in argv):
                raise SandboxConfigurationError("argv_invalid")
            executable = Path(argv[0])
            if not executable.is_absolute():
                raise SandboxConfigurationError("executable_not_absolute")
            try:
                if executable.is_symlink() or not executable.is_file():
                    raise SandboxConfigurationError("executable_invalid")
                resolved = executable.resolve(strict=True)
                st = executable.stat(follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode) or not (st.st_mode & stat.S_IXUSR):
                    raise SandboxConfigurationError("executable_invalid")
                if not _inside(resolved, root) and str(resolved) not in trusted_set:
                    raise SandboxConfigurationError("executable_outside_root")
            except (OSError, RuntimeError) as exc:
                raise SandboxConfigurationError("executable_invalid") from exc
            normalized.append(argv)
            pins[str(executable)] = _pin(executable)
        self._allowlist = frozenset(normalized)
        self._pins = MappingProxyType(pins)
        if env is None:
            env = {}
        if not isinstance(env, Mapping):
            raise SandboxConfigurationError("environment_invalid")
        clean: dict[str, str] = {}
        for key, value in env.items():
            if type(key) is not str or not key or "\x00" in key or _CREDENTIAL.search(key):
                raise SandboxConfigurationError("unsafe_environment")
            if type(value) is not str or "\x00" in value or _URL.search(value):
                raise SandboxConfigurationError("unsafe_environment")
            clean[key] = value
        self._env = MappingProxyType(dict(clean))
        if isinstance(secrets, (str, bytes)) or not isinstance(secrets, Sequence) or any(type(s) is not str for s in secrets):
            raise SandboxConfigurationError("secrets_invalid")
        self._secrets = tuple(s for s in secrets if s)
        roots: dict[str, str] = {}
        if path_roots is not None:
            if not isinstance(path_roots, Mapping):
                raise SandboxConfigurationError("path_roots_invalid")
            for namespace, value in path_roots.items():
                if type(namespace) is not str or not namespace or not isinstance(value, (str, os.PathLike)):
                    raise SandboxConfigurationError("path_roots_invalid")
                root_path = Path(value)
                if root_path.is_symlink() or not root_path.is_dir():
                    raise SandboxConfigurationError("path_root_invalid")
                resolved_path = root_path.resolve(strict=True)
                if not _inside(resolved_path, root):
                    raise SandboxConfigurationError("path_root_outside_root")
                roots[namespace] = str(resolved_path)
        self._path_roots = MappingProxyType(roots)
        self._capability = _issue_capability(self)

    @property
    def capability(self) -> SandboxCapability:
        """Opaque, runner-bound proof required by production adapters."""
        return self._capability

    def _validate_run(self, argv: Sequence[str], cwd: str | os.PathLike[str]) -> tuple[tuple[str, ...], Path, int]:
        if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
            raise SandboxConfigurationError("argv_invalid")
        checked = tuple(argv)
        if checked not in self._allowlist:
            raise SandboxConfigurationError("argv_not_allowlisted")
        path = Path(checked[0])
        cwd_fd: int | None = None
        try:
            root_st = _pin(self._tool_root)
            cwd_path = Path(cwd)
            if not cwd_path.is_absolute():
                raise SandboxConfigurationError("cwd_not_absolute")
            if cwd_path.is_symlink() or not cwd_path.is_dir():
                raise SandboxConfigurationError("cwd_invalid")
            cwd_resolved = cwd_path.resolve(strict=True)
            if root_st != self._root_pin or not _inside(cwd_resolved, self._tool_root):
                raise SandboxConfigurationError("cwd_outside_root")
            # Pin the directory before returning from validation. Passing the
            # pathname to Popen would reopen it after these checks and leave a
            # stat/validation-to-chdir TOCTOU window.
            cwd_fd = os.open(
                cwd_path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            cwd_st = os.fstat(cwd_fd)
            if not stat.S_ISDIR(cwd_st.st_mode):
                raise SandboxConfigurationError("cwd_changed")
            try:
                resolved_st = cwd_resolved.stat()
                fd_resolved = Path(f"/proc/self/fd/{cwd_fd}").resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise SandboxConfigurationError("cwd_changed") from exc
            if (cwd_st.st_dev, cwd_st.st_ino) != (resolved_st.st_dev, resolved_st.st_ino):
                raise SandboxConfigurationError("cwd_changed")
            if not _inside(fd_resolved, self._tool_root):
                raise SandboxConfigurationError("cwd_changed")
            if path.is_symlink() or not path.is_file() or _pin(path) != self._pins[str(path)]:
                raise SandboxConfigurationError("executable_changed")
        except SandboxConfigurationError:
            if cwd_fd is not None:
                os.close(cwd_fd)
            raise
        except (OSError, RuntimeError, KeyError) as exc:
            if cwd_fd is not None:
                os.close(cwd_fd)
            raise SandboxConfigurationError("path_unavailable") from exc
        assert cwd_fd is not None
        return checked, cwd_resolved, cwd_fd

    def run(self, argv: Sequence[str], *, cwd: str | os.PathLike[str],
            env: Mapping[str, str] | None = None, timeout: float = 10.0,
            output_limits: tuple[int, int] = (65536, 65536), shell: bool = False) -> dict[str, Any]:
        """Return a stable mapping compatible with ``ValidationExecutor``."""
        cwd_fd: int | None = None
        try:
            checked, cwd_resolved, cwd_fd = self._validate_run(argv, cwd)
            if shell is not False:
                raise SandboxConfigurationError("shell_forbidden")
            if (type(timeout) not in (int, float) or isinstance(timeout, bool)
                    or not math.isfinite(float(timeout)) or timeout <= 0):
                raise SandboxConfigurationError("timeout_invalid")
            if type(output_limits) is not tuple or len(output_limits) != 2 or any(type(x) is not int or x <= 0 for x in output_limits):
                raise SandboxConfigurationError("output_limits_invalid")
            if env is not None and not isinstance(env, Mapping):
                raise SandboxConfigurationError("environment_invalid")
            if env is not None and dict(env) != dict(self._env):
                raise SandboxConfigurationError("environment_mismatch")
            child_env = dict(self._env)
        except SandboxConfigurationError as exc:
            if cwd_fd is not None:
                os.close(cwd_fd)
            return {"status": "denied", "returncode": -1, "stdout": "", "stderr": "", "error": exc.code}

        proc: subprocess.Popen[bytes] | None = None
        sel: selectors.BaseSelector | None = None
        executable_fd: int | None = None
        out = bytearray(); err = bytearray(); truncated_out = truncated_err = timed_out = False
        try:
            # Execute an already-open descriptor rather than reopening the
            # pathname after validation, closing the stat-then-exec TOCTOU
            # replacement window.
            executable = Path(checked[0])
            executable_fd = os.open(executable, os.O_RDONLY | os.O_CLOEXEC)
            if _pin(executable) != self._pins[str(executable)]:
                raise SandboxConfigurationError("executable_changed")
            proc = subprocess.Popen(checked, cwd=f"/proc/self/fd/{cwd_fd}", env=child_env, shell=False,
                                    executable=f"/proc/self/fd/{executable_fd}",
                                    pass_fds=(executable_fd, cwd_fd),
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    start_new_session=True, close_fds=True)
            assert proc.stdout is not None and proc.stderr is not None
            sel = selectors.DefaultSelector()
            sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
            sel.register(proc.stderr, selectors.EVENT_READ, "stderr")
            deadline = time.monotonic() + float(timeout)
            while sel.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    break
                for key, _ in sel.select(min(remaining, 0.1)):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        sel.unregister(key.fileobj); key.fileobj.close(); continue
                    target = out if key.data == "stdout" else err
                    limit = output_limits[0] if key.data == "stdout" else output_limits[1]
                    available = max(0, limit - len(target))
                    if available:
                        target.extend(chunk[:available])
                    if len(chunk) > available:
                        if key.data == "stdout": truncated_out = True
                        else: truncated_err = True
            if timed_out:
                proc.wait(timeout=1.0)
            else:
                proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            stdout_text, stdout_cut = _safe_text(bytes(out), output_limits[0], tuple(self._env.values()) + self._secrets)
            stderr_text, stderr_cut = _safe_text(bytes(err), output_limits[1], tuple(self._env.values()) + self._secrets)
            return {"status": "timeout" if timed_out else ("passed" if proc.returncode == 0 else "failed"),
                    "returncode": -9 if timed_out else proc.returncode, "stdout": stdout_text,
                    "stderr": stderr_text, "timed_out": timed_out,
                    "truncated_stdout": truncated_out or stdout_cut, "truncated_stderr": truncated_err or stderr_cut}
        except SandboxConfigurationError as exc:
            return {"status": "denied", "returncode": -1, "stdout": "", "stderr": "", "error": exc.code}
        except Exception:
            if proc is not None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    pass
            return {"status": "failed", "returncode": -1,
                    "stdout": _redact(bytes(out).decode("utf-8", "replace"), tuple(self._env.values()) + self._secrets),
                    "stderr": _redact(bytes(err).decode("utf-8", "replace"), tuple(self._env.values()) + self._secrets),
                    "error": "process_failed"}
        finally:
            if sel is not None:
                try:
                    sel.close()
                except Exception:
                    pass
            if proc is not None:
                for stream in (proc.stdout, proc.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass
            if executable_fd is not None:
                try:
                    os.close(executable_fd)
                except OSError:
                    pass
            if cwd_fd is not None:
                try:
                    os.close(cwd_fd)
                except OSError:
                    pass