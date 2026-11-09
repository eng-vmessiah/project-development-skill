# CLI Benchmarks

`scripts/bench_cli.py` measures `pd` command latency on disposable fixtures. It is
an advisory tool: numbers are useful for comparing changes on the same machine,
not as a CI threshold.

## Run

From the repository root:

```bash
/usr/bin/python3 scripts/bench_cli.py
```

Useful options:

```bash
/usr/bin/python3 scripts/bench_cli.py --scenario status --repeat 20 --warmup 3
/usr/bin/python3 scripts/bench_cli.py --json
```

Each scenario gets its own temporary `.spec/`; nothing is written to the repository.

## Scenarios

| Scenario | Fixture | What is measured |
|---|---|---|
| `init` | Fresh feature name per run | `pd init <feature>` incl. directory and state creation |
| `status` | One initialized feature | `pd status -f seed --json` |
| `complete` | One initialized feature; one new task per run | `pd complete-task -f seed ...` incl. the state lock/merge path |
| `list` | Ten initialized features | `pd list --json` across a small multi-feature repo |

## Baseline

Measured on 2026-11-09 with `pd` 1.3.3, Python 3.12.3, WSL2
(`Linux 5.15.167.4-microsoft-standard-WSL2`), 20 runs after 3 warmups:

| Scenario | Median | p95 | Min | Max |
|---|---:|---:|---:|---:|
| `init` | 96.627 ms | 99.891 ms | 93.545 ms | 99.921 ms |
| `status` | 90.693 ms | 94.298 ms | 88.311 ms | 95.099 ms |
| `complete` | 99.470 ms | 112.086 ms | 93.862 ms | 120.130 ms |
| `list` | 92.677 ms | 95.108 ms | 88.768 ms | 95.355 ms |

Python process startup dominates every single-command measurement (~88–100 ms
on this machine). Optimizing `pd` internals will move `complete`/`list` more than
`status`/`init`; measure before and after on the same machine.

## What this does not measure

- Fleet runs, provider dispatch, or any live/external execution.
- `pd validate --deep` (closer to an integration test than a CLI microbenchmark).
- Large repositories or cold filesystems; both vary by machine.
- Memory usage or concurrency.

`scripts/release_preflight.sh` does not run the benchmark; performance is not a
release gate. Use the output as evidence when changing startup or state code, and
record the before/after table in the change's `.spec`/review notes.
