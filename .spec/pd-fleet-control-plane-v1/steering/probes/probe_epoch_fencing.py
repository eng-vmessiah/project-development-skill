#!/usr/bin/python3
"""Ground owner_epoch fencing in supervision reconciliation."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))

from pd_fleet.supervision import HealthSignal, HealthSnapshot, reconcile_snapshot  # noqa: E402


def main() -> int:
    epoch = 7
    snapshot = HealthSnapshot(
        mission_run_id="run-t301", task_id="T-301", lane_id="lane-1",
        owner_epoch=epoch,
        signal=HealthSignal("alive", "ready", "advanced", "healthy"),
    )
    result = reconcile_snapshot(snapshot, desired_state="running", active_owner_epoch=epoch + 1)
    passed = result.status == "blocked" and result.reasons == ("stale_owner_epoch",)
    print(f"snapshot.owner_epoch={snapshot.owner_epoch} active_owner_epoch={epoch + 1}")
    print(f"status={result.status!r} reasons={result.reasons!r}")
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
