#!/usr/bin/python3
"""Run every steering grounding probe and summarize their real outcomes."""
from pathlib import Path
import subprocess
import sys


def main() -> int:
    directory = Path(__file__).resolve().parent
    probes = sorted(path for path in directory.glob("probe_*.py") if path.name != Path(__file__).name)
    results = []
    for probe in probes:
        completed = subprocess.run(
            ["/usr/bin/python3", str(probe)], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=directory,
            check=False,
        )
        output = completed.stdout.rstrip()
        print(f"=== {probe.name} ===")
        print(output)
        results.append((probe.name, completed.returncode, output))
    print("\nPROBE                         RESULT  EXIT")
    print("----------------------------  ------  ----")
    for name, code, _ in results:
        print(f"{name:<28}  {'PASS' if code == 0 else 'FAIL':<6}  {code}")
    failures = sum(code != 0 for _, code, _ in results)
    print(f"TOTAL={len(results)} PASS={len(results) - failures} FAIL={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
