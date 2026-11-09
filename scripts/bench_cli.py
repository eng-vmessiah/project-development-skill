#!/usr/bin/env python3
"""Advisory latency benchmark for the pd CLI on disposable fixtures."""
from __future__ import annotations

import argparse
import itertools
import json
import math
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PD = REPO / "scripts" / "pd.py"
PYTHON = sys.executable


class BenchError(RuntimeError):
    """The CLI failed while preparing or measuring a scenario."""


def run_pd(args: Sequence[str], cwd: Path) -> None:
    result = subprocess.run(
        [PYTHON, str(PD), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-300:]
        raise BenchError(f"pd {' '.join(args)} failed ({result.returncode}): {detail}")


def measure(action: Callable[[], None], repeat: int, warmup: int) -> list[float]:
    for _ in range(warmup):
        action()
    samples: list[float] = []
    for _ in range(repeat):
        start = time.perf_counter()
        action()
        samples.append((time.perf_counter() - start) * 1000.0)
    return samples


def summarize(name: str, samples: Sequence[float]) -> dict[str, object]:
    ordered = sorted(samples)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "scenario": name,
        "runs": len(ordered),
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[index], 3),
        "min_ms": round(ordered[0], 3),
        "max_ms": round(ordered[-1], 3),
    }


def scenario_init(repeat: int, warmup: int) -> list[float]:
    with tempfile.TemporaryDirectory(prefix="pd-bench-init-") as raw:
        root = Path(raw)
        counter = itertools.count()
        return measure(lambda: run_pd(["init", f"bench-{next(counter)}"], root), repeat, warmup)


def scenario_status(repeat: int, warmup: int) -> list[float]:
    with tempfile.TemporaryDirectory(prefix="pd-bench-status-") as raw:
        root = Path(raw)
        run_pd(["init", "seed"], root)
        return measure(lambda: run_pd(["status", "-f", "seed", "--json"], root), repeat, warmup)


def scenario_complete(repeat: int, warmup: int) -> list[float]:
    with tempfile.TemporaryDirectory(prefix="pd-bench-complete-") as raw:
        root = Path(raw)
        run_pd(["init", "seed"], root)
        counter = itertools.count()
        action = lambda: run_pd(
            ["complete-task", "-f", "seed", f"T-{next(counter)} — bench"], root
        )
        return measure(action, repeat, warmup)


def scenario_list(repeat: int, warmup: int) -> list[float]:
    with tempfile.TemporaryDirectory(prefix="pd-bench-list-") as raw:
        root = Path(raw)
        for index in range(10):
            run_pd(["init", f"seed-{index}"], root)
        return measure(lambda: run_pd(["list", "--json"], root), repeat, warmup)


SCENARIOS: dict[str, Callable[[int, int], list[float]]] = {
    "init": scenario_init,
    "status": scenario_status,
    "complete": scenario_complete,
    "list": scenario_list,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default=None,
                        help="run one scenario (default: all)")
    parser.add_argument("--repeat", type=int, default=15,
                        help="measured runs per scenario (default: 15)")
    parser.add_argument("--warmup", type=int, default=2,
                        help="untimed warmup runs per scenario (default: 2)")
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")
    if args.warmup < 0:
        parser.error("--warmup must be >= 0")

    names = [args.scenario] if args.scenario else list(SCENARIOS)
    results = []
    for name in names:
        results.append(summarize(name, SCENARIOS[name](args.repeat, args.warmup)))

    version = (REPO / "VERSION").read_text(encoding="utf-8").strip() or "unknown"
    if args.json:
        print(json.dumps({
            "benchmark": "pd-cli",
            "version": version,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "repeat": args.repeat,
            "warmup": args.warmup,
            "results": results,
        }, indent=2))
        return 0

    print(f"pd {version} · Python {platform.python_version()} · {platform.platform()}")
    print(f"{'scenario':<10} {'runs':>5} {'median ms':>10} {'p95 ms':>10} "
          f"{'min ms':>10} {'max ms':>10}")
    for item in results:
        print(f"{item['scenario']:<10} {item['runs']:>5} {item['median_ms']:>10.3f} "
              f"{item['p95_ms']:>10.3f} {item['min_ms']:>10.3f} {item['max_ms']:>10.3f}")
    print("\nAdvisory only: compare runs on the same machine; no CI threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
