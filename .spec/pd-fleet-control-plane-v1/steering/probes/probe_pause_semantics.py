#!/usr/bin/python3
"""Ground the honest semantics for an unobserved cooperative pause."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))

from pd_fleet.supervision import HealthSignal, HealthSnapshot, reconcile_snapshot  # noqa: E402


def main() -> int:
    snapshot = HealthSnapshot(
        mission_run_id="run-t301", task_id="T-301", lane_id="lane-1", owner_epoch=7,
        signal=HealthSignal("alive", "ready", "advanced", "healthy"),
    )
    result = reconcile_snapshot(snapshot, desired_state="paused", active_owner_epoch=7)
    passed = result.status == "degraded" and result.reasons == ("pause_not_observed",)
    print(f"desired_state='paused' liveness={snapshot.signal.liveness!r}")
    print(f"status={result.status!r} reasons={result.reasons!r}")
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
