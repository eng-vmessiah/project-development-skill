#!/usr/bin/python3
"""Ground InterventionProposal's reason vocabulary."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))

from pd_fleet.supervision import InterventionProposal, SupervisionError  # noqa: E402


def proposal(reason: str) -> InterventionProposal:
    return InterventionProposal("inspect", reason, "T-301", ("snapshot:run:T-301",), False)


def main() -> int:
    invalid_error = None
    try:
        proposal("kill_now")
    except SupervisionError as exc:
        invalid_error = f"{type(exc).__name__}: {exc}"
    accepted = proposal("retry")
    passed = invalid_error is not None and accepted.reason == "retry"
    print(f"invalid_reason='kill_now' result={invalid_error!r}")
    print(f"valid_reason='retry' stored_reason={accepted.reason!r}")
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
