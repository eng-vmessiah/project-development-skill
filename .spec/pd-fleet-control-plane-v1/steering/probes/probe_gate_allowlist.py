#!/usr/bin/python3
"""Ground the gateway allowlist and composite-deny claims."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))

from pd_fleet.gateway_deny import (  # noqa: E402
    CAPABILITIES_V1, GATE_IDS, GateValue, evaluate_gates,
)


def main() -> int:
    absent = evaluate_gates({})
    gates = {gate_id: GateValue(True, True) for gate_id in GATE_IDS}
    gates["B7"] = GateValue(True, True, "steer.kill")
    steering = evaluate_gates(gates)
    expected = frozenset({"observation"})
    passed = (
        CAPABILITIES_V1 == expected
        and absent.allowed is False
        and absent.denied_by == GATE_IDS
        and steering.allowed is False
        and steering.denied_by == ("B7",)
    )
    print(f"CAPABILITIES_V1={CAPABILITIES_V1!r}")
    print(f"absent.allowed={absent.allowed} absent.denied_by={absent.denied_by!r}")
    print(f"steer.kill.allowed={steering.allowed} steer.kill.denied_by={steering.denied_by!r}")
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
