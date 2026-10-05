"""B15b.2 fixtures — composite-deny (matrix §B; all-gates-pass, fail-closed).

Every gate of the matrix has a named fixture; absence, malformation,
out-of-allowlist capability, partial maps and hot-reload re-validation all
deny. No gate is inherited from another layer.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.gateway_deny import GATE_IDS, GATE_NAMES, GateValue, evaluate_gates

_GATE_IDS = [f"{gate_id}-{GATE_NAMES[gate_id]}" for gate_id in GATE_IDS]


def _all_pass(overrides=None):
    gates = {gate_id: GateValue(present=True, valid=True) for gate_id in GATE_IDS}
    gates["B7"] = GateValue(present=True, valid=True, capability="observation")
    if overrides:
        gates.update(overrides)
    return gates


def test_all_gates_pass_allows():
    decision = evaluate_gates(_all_pass())
    assert decision.allowed and decision.denied_by == ()


@pytest.mark.parametrize("gate_id", GATE_IDS, ids=_GATE_IDS)
def test_gate_absent_denies(gate_id):
    gates = _all_pass()
    del gates[gate_id]
    decision = evaluate_gates(gates)
    assert not decision.allowed and decision.denied_by == (gate_id,)


@pytest.mark.parametrize("gate_id", GATE_IDS, ids=_GATE_IDS)
def test_gate_malformed_denies(gate_id):
    decision = evaluate_gates(_all_pass({gate_id: GateValue(present=True, valid=False)}))
    assert not decision.allowed and decision.denied_by == (gate_id,)


def test_b7_capability_outside_v1_denies():
    decision = evaluate_gates(
        _all_pass({"B7": GateValue(present=True, valid=True, capability="admin")})
    )
    assert not decision.allowed and decision.denied_by == ("B7",)


def test_hot_reload_revalidation_denies():
    # allow now; the same call-site must re-evaluate on every use
    assert evaluate_gates(_all_pass()).allowed
    decision = evaluate_gates(_all_pass({"B3": GateValue(present=True, valid=False)}))
    assert not decision.allowed and decision.denied_by == ("B3",)


def test_partial_map_and_empty_map_deny():
    gates = _all_pass()
    del gates["B8"]
    decision = evaluate_gates(gates)
    assert not decision.allowed and decision.denied_by == ("B8",)
    decision = evaluate_gates({})
    assert not decision.allowed and decision.denied_by == GATE_IDS


def test_non_contract_input_denies():
    # defensive: out-of-contract input denies instead of raising (review NIT-1)
    assert not evaluate_gates(None).allowed
    decision = evaluate_gates({"B1": "not-a-gate-value"})
    assert not decision.allowed and "B1" in decision.denied_by
    gates = _all_pass()
    gates["B7"] = GateValue(present=True, valid=True, capability=["not", "hashable"])
    decision = evaluate_gates(gates)
    assert not decision.allowed and decision.denied_by == ("B7",)
