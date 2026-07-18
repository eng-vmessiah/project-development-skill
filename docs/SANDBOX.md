# Local validation runner: security boundary and limitations

`scripts.pd_fleet.sandbox.LocalSandboxRunner` is a small Linux/WSL-first
process runner. It is intentionally **not** a kernel sandbox.

## Guarantees provided by the runner

- `shell=False`, `stdin=DEVNULL`, and exact complete-argv allowlisting;
  arguments are data and are never parsed as shell commands.
- The executable must be an existing regular, executable, non-symlink file
  physically beneath the declared tool root. Device/inode/size/mtime pins are
  checked again immediately before launch. A runtime binary outside the tool
  root is allowed only when its exact absolute real path is supplied through
  `trusted_executables`; each such path is resolved strictly and pinned at
  construction. These are explicit trusted runtime exceptions, not arbitrary
  external execution: there is no `PATH` lookup, wildcard/prefix matching, or
  shell execution.
- The tool root and working directory are regular directories, and the cwd is
  contained by the root. Cwd must be absolute; its validated, resolved path is
  passed to `Popen`. Root identity and cwd containment are rechecked on every
  run.
- The child receives only the explicit environment supplied at construction;
  credential-shaped variable names and URL values are rejected. The stored
  environment/configuration is private and immutable after construction.
- A monotonic timeout kills the complete process group (the child is started
  in a new session with `setsid`; descendants in that process group are also
  targeted). stdout and stderr are drained without retaining more than their
  configured byte limits, and output is UTF-8 decoded deterministically and
  redacted for URLs, absolute paths, and every configured environment value.
- Invalid requests return stable, non-sensitive error codes. The parent
  environment is never inherited.

## Deliberate limitations (fail closed)

Python's standard library cannot guarantee a portable network namespace,
seccomp policy, filesystem namespace, resource quota, or protection against a
malicious executable that is already trusted by the host. Accordingly,
`network=True` is rejected rather than implying that networking is blocked.
The runner does not claim isolation from the host, does not change users or
capabilities, and does not prevent an approved executable from reading files
available to its OS identity. Use a separately provisioned container, VM, or
platform sandbox for hostile code. If that stronger capability is unavailable,
keep validation declarative and do not inject this runner.

`network=False` is only a policy/configuration requirement: this runner does
**not** provide network isolation. It rejects `network=True` because the
standard library cannot reliably establish a network namespace on Linux/WSL;
an approved process may still use the host network.

This is a defense-in-depth execution boundary, not authorization to run
arbitrary commands. The allowlist and tool root must be provisioned by a
trusted operator; untrusted plans must not be allowed to construct them.

# Runtime smoke-policy flags

The named Hermes and Codex smoke adapters may use provider-specific repository
checks as an explicit smoke-policy opt-in: Hermes `--ignore-rules` and Codex
`--skip-git-repo-check`. These flags are **not production defaults** and must
not be copied into production execution paths. The adapters do not enable
unsafe bypass flags; production remains subject to the normal sandbox and
capability policy.
