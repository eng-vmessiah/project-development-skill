"""Red-first tests for the local/injected B15a read-only TUI RPC contract."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

import pytest

from pd_fleet.tui_readonly_contract import (
    TUI_SNAPSHOT_METHOD,
    TUI_SCHEMA_VERSION,
    TuiContractError,
    TuiBindingLease,
    TuiBindingRegistry,
    TuiHostBinding,
    TuiSnapshotRequest,
    build_snapshot_response,
)
from pd_fleet.gateway_bridge_contracts import OwnershipMode, SessionSnapshot


def _snapshot() -> SessionSnapshot:
    return SessionSnapshot(
        session_ref="session-1",
        association_ref="association-1",
        ownership_mode=OwnershipMode.USER_OWNED_SESSION,
        status="observing",
        stream_epoch="epoch-1",
        sequence=4,
        metadata_version=2,
    )


def _binding(**overrides) -> TuiHostBinding:
    values = {
        "observer_ref": "observer-1",
        "owner_ref": "owner-1",
        "profile_ref": "profile-1",
        "workspace_ref": "workspace-1",
        "association_ref": "association-1",
        "session_ref": "session-1",
        "authenticated": True,
        "capabilities": frozenset({"observe_session_metadata"}),
        "ownership_mode": OwnershipMode.USER_OWNED_SESSION,
    }
    values.update(overrides)
    return TuiHostBinding(**values)


def test_request_accepts_only_explicit_session_and_version():
    request = TuiSnapshotRequest.from_dict(
        {"session_id": "session-1", "schema_version": TUI_SCHEMA_VERSION}
    )
    assert request.session_id == "session-1"
    assert request.method == TUI_SNAPSHOT_METHOD


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": TUI_SCHEMA_VERSION},
        {"session_id": "session-1", "schema_version": TUI_SCHEMA_VERSION, "owner_ref": "spoof"},
        {"session_id": "session-1"},
        {"session_id": "../escape", "schema_version": TUI_SCHEMA_VERSION},
    ],
)
def test_request_rejects_missing_unknown_or_unsafe_fields(payload):
    with pytest.raises(TuiContractError):
        TuiSnapshotRequest.from_dict(payload)


def test_response_requires_authenticated_host_binding_and_capability():
    request = TuiSnapshotRequest("session-1")

    with pytest.raises(TuiContractError, match="CAPABILITY_DENIED"):
        build_snapshot_response(request, _binding(authenticated=False), _snapshot())

    with pytest.raises(TuiContractError, match="CAPABILITY_DENIED"):
        build_snapshot_response(request, _binding(capabilities=frozenset()), _snapshot())

    with pytest.raises(TuiContractError, match="CAPABILITY_DENIED"):
        build_snapshot_response(
            request,
            _binding(ownership_mode=OwnershipMode.FLEET_OWNED_TASK),
            _snapshot(),
        )


def test_binding_rejects_oversized_or_unbounded_capabilities():
    with pytest.raises(TuiContractError, match="INVALID_BINDING"):
        _binding(capabilities=frozenset(f"cap-{index}" for index in range(17)))

    with pytest.raises(TuiContractError, match="INVALID_BINDING"):
        _binding(capabilities=frozenset({"x" * 65}))

    with pytest.raises(TuiContractError, match="INVALID_BINDING"):
        _binding(capabilities=frozenset({"bad/value"}))


def test_response_requires_server_resolved_session_binding():
    request = TuiSnapshotRequest("session-1")
    with pytest.raises(TuiContractError, match="SESSION_BINDING_MISMATCH"):
        build_snapshot_response(request, _binding(session_ref="other"), _snapshot())

    with pytest.raises(TuiContractError, match="SESSION_BINDING_MISMATCH"):
        build_snapshot_response(request, _binding(association_ref="other"), _snapshot())


def test_binding_rejects_missing_identity_reference():
    with pytest.raises(TuiContractError, match="INVALID_BINDING"):
        _binding(owner_ref="")


def test_response_is_closed_bounded_and_redacted():
    response = build_snapshot_response(TuiSnapshotRequest("session-1"), _binding(), _snapshot())
    assert response == {
        "method": TUI_SNAPSHOT_METHOD,
        "schema_version": TUI_SCHEMA_VERSION,
        "redacted": True,
        "capability": "observe_session_metadata",
        "session": {
            "session_ref": "session-1",
            "association_ref": "association-1",
            "ownership_mode": "user_owned_session",
            "status": "observing",
            "stream_epoch": "epoch-1",
            "sequence": 4,
            "metadata_version": 2,
        },
    }
    assert "owner_ref" not in response
    assert "profile_ref" not in response
    assert "workspace_ref" not in response
    assert "prompt" not in response


def test_binding_registry_issues_and_resolves_exact_epoch():
    registry = TuiBindingRegistry(clock=lambda: 100.0)
    lease = registry.issue(_binding(), ttl=30)

    assert lease.epoch == 1
    assert registry.resolve("session-1", "observer-1", 1).binding == _binding()

    with pytest.raises(TuiContractError, match="BINDING_MISMATCH"):
        registry.resolve("session-1", "observer-2", 1)
    with pytest.raises(TuiContractError, match="STALE_EPOCH"):
        registry.resolve("session-1", "observer-1", 2)


def test_binding_registry_expiry_is_fail_closed():
    now = [100.0]
    registry = TuiBindingRegistry(clock=lambda: now[0])
    lease = registry.issue(_binding(), ttl=5)
    now[0] = 105.0

    with pytest.raises(TuiContractError, match="BINDING_EXPIRED"):
        registry.resolve("session-1", "observer-1", lease.epoch)


def test_binding_registry_revoke_and_reissue_advance_epoch():
    registry = TuiBindingRegistry(clock=lambda: 100.0)
    first = registry.issue(_binding(), ttl=30)
    assert registry.revoke("session-1") is True

    with pytest.raises(TuiContractError, match="BINDING_REVOKED"):
        registry.resolve("session-1", "observer-1", first.epoch)

    second = registry.issue(_binding(), ttl=30)
    assert second.epoch == 2
    with pytest.raises(TuiContractError, match="STALE_EPOCH"):
        registry.resolve("session-1", "observer-1", first.epoch)


def test_binding_registry_rejects_oversized_ttl_and_silent_eviction():
    registry = TuiBindingRegistry(clock=lambda: 100.0, max_bindings=1)
    registry.issue(_binding(), ttl=30)

    with pytest.raises(TuiContractError, match="INVALID_TTL"):
        TuiBindingRegistry(clock=lambda: 100.0).issue(_binding(), ttl=301)
    with pytest.raises(TuiContractError, match="REGISTRY_FULL"):
        registry.issue(_binding(session_ref="session-2", association_ref="association-2"), ttl=30)


def test_binding_registry_rejects_clock_failure_and_rollback():
    registry = TuiBindingRegistry(clock=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(TuiContractError, match="INVALID_CLOCK"):
        registry.issue(_binding(), ttl=30)

    now = [100.0]
    registry = TuiBindingRegistry(clock=lambda: now[0])
    registry.issue(_binding(), ttl=30)
    now[0] = 99.0
    with pytest.raises(TuiContractError, match="CLOCK_ROLLBACK"):
        registry.resolve("session-1", "observer-1", 1)


def test_binding_lease_rejects_malformed_public_construction():
    with pytest.raises(TuiContractError, match="INVALID_LEASE"):
        TuiBindingLease(_binding(), 0, 1.0, 2.0)
    with pytest.raises(TuiContractError, match="INVALID_LEASE"):
        TuiBindingLease(_binding(), 1, True, 2.0)
    with pytest.raises(TuiContractError, match="INVALID_LEASE"):
        TuiBindingLease(_binding(), 1, "1", 2.0)
    with pytest.raises(TuiContractError, match="INVALID_LEASE"):
        TuiBindingLease(_binding(), 1, 1.0, 302.0)
    with pytest.raises(TuiContractError, match="INVALID_LEASE"):
        TuiBindingLease(_binding(), 1, 1.0, 2.0, status=[])


def test_binding_registry_rejects_clock_precision_collapse():
    clock = lambda: float.fromhex("0x1.fffffffffffffp1023")
    with pytest.raises(TuiContractError, match="INVALID_LEASE"):
        TuiBindingRegistry(clock=clock).issue(_binding(), ttl=1)
    with pytest.raises(TuiContractError, match="INVALID_TIME"):
        TuiBindingRegistry(clock=lambda: 10**1000).issue(_binding(), ttl=1)
    with pytest.raises(TuiContractError, match="INVALID_TTL"):
        TuiBindingRegistry(clock=lambda: 100.0).issue(_binding(), ttl=10**1000)


def test_binding_registry_serializes_same_session_issues():
    registry = TuiBindingRegistry(clock=lambda: 100.0)
    barrier = threading.Barrier(8)

    def issue_once():
        barrier.wait()
        return registry.issue(_binding(), ttl=30).epoch

    with ThreadPoolExecutor(max_workers=8) as pool:
        epochs = list(pool.map(lambda _: issue_once(), range(8)))
    assert sorted(epochs) == list(range(1, 9))
