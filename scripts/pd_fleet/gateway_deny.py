"""B15b.2 — composite-deny gate evaluation (matrix §B, all-gates-pass).

A Fleet capability is granted ONLY when all eight gates pass on every use.
Absent, malformed or hot-reload-invalidated gates deny (fail-closed); there
is no inheritance between layers (each gate is supplied explicitly by its own
source and re-validated per call); defaults never widen access.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

GATE_IDS = ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8")

GATE_NAMES = {
    "B1": "plugin_allowlist",
    "B2": "integration_flag",
    "B3": "seam_supported",
    "B4": "caller_authenticated",
    "B5": "session_resolved",
    "B6": "association_explicit",
    "B7": "capability_allowlist",
    "B8": "lifecycle_current",
}

#: v1 capability allow-list (observation-only) — B7 must be within it.
CAPABILITIES_V1 = frozenset({"observation"})


@dataclass(frozen=True)
class GateValue:
    """One gate's state for THIS use (explicit; never carried over)."""

    present: bool
    valid: bool
    capability: str | None = None  # only meaningful for B7


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    denied_by: tuple[str, ...]


def evaluate_gates(gates: Mapping[str, GateValue]) -> GateDecision:
    """All-gates-pass evaluation; re-run for every use (anti-hot-reload)."""
    if not isinstance(gates, Mapping):
        return GateDecision(allowed=False, denied_by=GATE_IDS)
    denied: list[str] = []
    for gate_id in GATE_IDS:
        value = gates.get(gate_id)
        if not isinstance(value, GateValue) or not value.present or not value.valid:
            denied.append(gate_id)
            continue
        if gate_id == "B7" and (
            not isinstance(value.capability, str) or value.capability not in CAPABILITIES_V1
        ):
            denied.append(gate_id)
    return GateDecision(allowed=not denied, denied_by=tuple(denied))
