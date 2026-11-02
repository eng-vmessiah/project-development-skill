#!/usr/bin/python3
"""Probe sandbox configuration refusal without ever invoking runner.run()."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))

from pd_fleet.sandbox import LocalSandboxRunner, SandboxConfigurationError  # noqa: E402


def configure(argument: str) -> str:
    executable = str(Path(sys.executable).resolve(strict=True))
    try:
        LocalSandboxRunner(str(Path(executable).parent), allowlist=((executable, argument),))
    except SandboxConfigurationError as exc:
        return f"rejected:{exc.code}"
    return "accepted"


def main() -> int:
    meta = configure("value;uname")
    url = configure("https://example.invalid/resource")
    passed = meta.startswith("rejected:") and url.startswith("rejected:")
    print(f"shell_metacharacter={meta}")
    print(f"url_argument={url}")
    if passed:
        print("PASS")
        return 0
    print("REFUTED: public constructor rejects shell metacharacters but permits URL argv; run() was not called")
    print("FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
