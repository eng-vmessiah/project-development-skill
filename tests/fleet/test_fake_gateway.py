from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))
from scripts.pd_fleet.fake_gateway import FakeGateway
from scripts.pd_fleet.gateway_bridge_contracts import (
    BridgeErrorCode, BridgeValidationError, ObserverIdentity, OwnershipMode,
    ReplayWindow,
)


class Clock:
    def __init__(self): self.value = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)
    def __call__(self): return self.value
    def advance(self, **kwargs): self.value += timedelta(**kwargs)


def setup(*, retention=32, heartbeat=30):
    clock = Clock(); gateway = FakeGateway(clock=clock, retention=retention, heartbeat_ttl=timedelta(seconds=heartbeat))
    observer = ObserverIdentity("observer-1", "owner-1", "profile-1")
    gateway.connect(observer)
    binding = dict(owner_ref="owner-1", profile_ref="profile-1", workspace_ref="workspace-1", session_ref="session-1", association_ref="association-1", purpose="pd_observation")
    ticket = gateway.issue_activation(observer, **binding)
    return clock, gateway, observer, binding, ticket


def consume(gateway, observer, binding, ticket, key="op-1", **extra):
    return gateway.consume_activation(ticket, observer, **binding, operation_key=key, **extra)


def test_positive_activation_snapshot_before_stream_and_lifecycle_allowlist():
    _, gateway, observer, binding, ticket = setup()
    assert "owner-1" not in ticket.activation_ref and "session-1" not in ticket.activation_ref
    association = consume(gateway, observer, binding, ticket)
    stream = gateway.connect(observer).subscribe(association)
    assert stream.snapshot.sequence == 1
    assert stream.boundary_ref == "boundary-1"
    assert [event.event_type for event in stream.events] == ["session.registered"]
    assert all(event.source_system == "hermes-gateway" for event in stream.events)


def test_same_operation_is_idempotent_but_replay_and_different_binding_are_uniform():
    _, gateway, observer, binding, ticket = setup()
    first = consume(gateway, observer, binding, ticket)
    assert consume(gateway, observer, binding, ticket) == first
    with pytest.raises(BridgeValidationError) as exc:
        consume(gateway, observer, binding, ticket, key="different")
    assert exc.value.external_code is BridgeErrorCode.ACTIVATION_INVALID
    assert exc.value.audit_reason == "replayed"
    other = ObserverIdentity("observer-2")
    gateway.connect(other)
    with pytest.raises(BridgeValidationError) as exc:
        consume(gateway, other, binding, ticket, key="other")
    assert exc.value.external_code is BridgeErrorCode.ACTIVATION_INVALID
    assert exc.value.audit_reason == "binding_mismatch"


def test_concurrent_duplicate_consume_creates_one_association():
    _, gateway, observer, binding, ticket = setup()
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: consume(gateway, observer, binding, ticket), range(12)))
    assert {result.association_ref for result in results} == {"association-1"}
    assert len(tuple(gateway.events(observer, "association-1"))) == 1


def test_fleet_owned_task_is_denied_and_malformed_is_rejected():
    _, gateway, observer, binding, ticket = setup()
    with pytest.raises(BridgeValidationError) as exc:
        consume(gateway, observer, binding, ticket, ownership_mode=OwnershipMode.FLEET_OWNED_TASK)
    assert exc.value.code is BridgeErrorCode.CAPABILITY_DENIED
    assert str(exc.value) == "activation_invalid"
    assert exc.value.args == ("activation_invalid",)
    assert exc.value.audit_reason == "fleet_owned_task"
    with pytest.raises(BridgeValidationError) as exc:
        gateway.consume_activation("not-a-ticket", observer, **{**binding, "purpose": "observe"}, operation_key="x")
    assert exc.value.external_code is BridgeErrorCode.ACTIVATION_INVALID
    assert str(exc.value) == "activation_invalid"
    assert exc.value.args == ("activation_invalid",)


def test_replay_no_new_events_gap_and_cursor_stale():
    clock, gateway, observer, binding, ticket = setup(retention=2)
    association = consume(gateway, observer, binding, ticket)
    connection = gateway.connect(observer)
    first = connection.subscribe(association)
    connection.heartbeat(association); connection.heartbeat(association)
    with pytest.raises(BridgeValidationError) as exc:
        connection.replay(ReplayWindow("association-1", first.snapshot.stream_epoch, 0))
    assert exc.value.code is BridgeErrorCode.REPLAY_GAP
    current = connection.subscribe(association)
    with pytest.raises(BridgeValidationError) as exc:
        connection.replay(ReplayWindow("association-1", current.snapshot.stream_epoch, current.snapshot.sequence))
    assert exc.value.code is BridgeErrorCode.NO_NEW_EVENTS
    future = type(current.cursor)(current.cursor.cursor_version, current.cursor.association_ref, current.cursor.subscriber_ref, current.cursor.stream_epoch, 999, current.cursor.issued_at, current.cursor.expires_at)
    with pytest.raises(BridgeValidationError) as exc:
        connection.subscribe(association, future)
    assert exc.value.code is BridgeErrorCode.CURSOR_STALE
    clock.advance(minutes=10)
    with pytest.raises(BridgeValidationError) as exc:
        connection.subscribe(association, current.cursor)
    assert exc.value.code is BridgeErrorCode.CURSOR_EXPIRED


def test_replay_pagination_cursor_advances_to_last_delivered_event():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    connection = gateway.connect(observer)
    connection.heartbeat(association)
    connection.heartbeat(association)
    connection.heartbeat(association)
    epoch = connection.snapshot(association).stream_epoch
    assert epoch is not None

    first = connection.replay(ReplayWindow(association.association_ref, epoch, 0, limit=1))
    assert [event.sequence for event in first.events] == [1]
    assert first.cursor.last_sequence == 1

    second = connection.replay(
        ReplayWindow(association.association_ref, epoch, first.cursor.last_sequence, limit=1),
        first.cursor,
    )
    assert [event.sequence for event in second.events] == [2]
    assert second.cursor.last_sequence == 2


def test_heartbeat_stale_revoke_disconnect_and_reset():
    clock, gateway, observer, binding, ticket = setup(heartbeat=5)
    connection = gateway.connect(observer); association = consume(gateway, observer, binding, ticket)
    heartbeat = connection.heartbeat(association)
    assert heartbeat.event.event_type == "session.heartbeat"
    clock.advance(seconds=5)
    assert gateway.expire_stale() == 1
    with pytest.raises(BridgeValidationError) as exc: connection.heartbeat(association)
    assert exc.value.code is BridgeErrorCode.ASSOCIATION_STALE
    gateway.reset()
    with pytest.raises(BridgeValidationError): connection.snapshot(association)


def test_revoke_is_idempotent_and_stale_after_reconnect():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    connection = gateway.connect(observer); connection.revoke(association); connection.revoke(association); connection.disconnect()
    reconnected = gateway.connect(observer)
    with pytest.raises(BridgeValidationError) as exc:
        reconnected.subscribe(association)
    assert exc.value.code is BridgeErrorCode.ASSOCIATION_STALE


def test_no_disclosure_and_import_boundary():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    wire = gateway.snapshot(observer, association).to_dict()
    text = repr(wire) + repr(ticket)
    for forbidden in ("prompt", "history", "tool", "provider", "credential", "terminal", "path", "url"):
        assert forbidden not in text.lower()
    tree = ast.parse((Path(__file__).parents[2] / "scripts/pd_fleet/fake_gateway.py").read_text())
    imports = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    imports |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not imports & {"socket", "requests", "httpx", "aiohttp", "websockets", "subprocess"}


def test_disconnect_invalidates_all_existing_facades_uniformly():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    first = gateway.connect(observer); second = gateway.connect(observer)
    first.disconnect()
    for operation in (
        lambda: first.snapshot(association), lambda: second.snapshot(association),
        lambda: first.subscribe(association), lambda: first.heartbeat(association),
    ):
        with pytest.raises(BridgeValidationError) as exc:
            operation()
        assert exc.value.external_code is BridgeErrorCode.ACTIVATION_INVALID
        assert exc.value.audit_reason == "disconnected"


def test_forged_epoch_without_cursor_fails_closed():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    with pytest.raises(BridgeValidationError) as exc:
        gateway.replay(observer, ReplayWindow(association.association_ref, "forged-epoch", 0))
    assert exc.value.code is BridgeErrorCode.RESYNC_REQUIRED


def test_purpose_is_exactly_pd_observation():
    _, gateway, observer, binding, _ = setup()
    with pytest.raises(BridgeValidationError) as exc:
        gateway.issue_activation(observer, **{**binding, "purpose": "admin"})
    assert exc.value.external_code is BridgeErrorCode.ACTIVATION_INVALID
    assert str(exc.value) == "activation_invalid"
    assert exc.value.args == ("activation_invalid",)
    assert exc.value.audit_reason == "capability_denied"


def test_concurrent_auto_association_issuance_is_unique():
    clock = Clock(); gateway = FakeGateway(clock=clock)
    observer = ObserverIdentity("observer-issuance")
    gateway.connect(observer)
    common = dict(owner_ref="owner-x", profile_ref="profile-x", workspace_ref="workspace-x", session_ref="session-x", purpose="pd_observation")
    with ThreadPoolExecutor(max_workers=12) as pool:
        tickets = list(pool.map(lambda _: gateway.issue_activation(observer, **common), range(12)))
    assert len({ticket.activation_ref for ticket in tickets}) == 12


def test_timeout_emits_session_ended_with_allowed_payload():
    clock, gateway, observer, binding, ticket = setup(heartbeat=5)
    association = consume(gateway, observer, binding, ticket)
    connection = gateway.connect(observer); connection.heartbeat(association)
    clock.advance(seconds=5); assert gateway.expire_stale() == 1
    event = tuple(gateway.events(observer, association.association_ref))[-1]
    assert event.event_type == "session.ended"
    assert event.payload["terminal_state"] == "disconnected"
    assert set(event.payload) == {"terminal_state", "reason_code", "metadata_version"}


def test_cursor_expiry_normalizes_offsets_and_exact_boundary_expires():
    clock, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    connection = gateway.connect(observer); current = connection.subscribe(association)
    cursor_type = type(current.cursor)
    exact = cursor_type(current.cursor.cursor_version, current.cursor.association_ref, current.cursor.subscriber_ref,
                        current.cursor.stream_epoch, current.cursor.last_sequence,
                        "2026-07-29T14:00:00+02:00", "2026-07-29T14:00:00+02:00")
    with pytest.raises(BridgeValidationError) as exc:
        connection.subscribe(association, exact)
    assert exc.value.code is BridgeErrorCode.CURSOR_EXPIRED


def test_old_facade_stays_closed_after_reconnect():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    old = gateway.connect(observer)
    old.disconnect()
    new = gateway.connect(observer)
    assert new.snapshot(association).association_ref == association.association_ref
    with pytest.raises(BridgeValidationError) as exc:
        old.snapshot(association)
    assert exc.value.audit_reason == "disconnected"


def test_association_collision_never_overwrites_live_state():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    with pytest.raises(BridgeValidationError) as exc:
        gateway.issue_activation(observer, **{**binding, "session_ref": "other-session"})
    assert exc.value.audit_reason == "association_collision"
    assert gateway.snapshot(observer, association).session_ref == "session-1"


def test_revoke_returns_authenticated_detached_event_and_connection_events_path():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    connection = gateway.connect(observer)
    result = connection.revoke(association)
    assert result is not None and result.event_type == "session.detached"
    assert tuple(connection.events(association))[-1] == result


def test_direct_operations_and_events_require_connected_observer():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    gateway.disconnect(observer)
    with pytest.raises(BridgeValidationError) as exc:
        gateway.snapshot(observer, association)
    assert exc.value.audit_reason == "disconnected"
    with pytest.raises(BridgeValidationError) as exc:
        gateway.issue_activation(observer, **binding)
    assert exc.value.audit_reason == "disconnected"
    with pytest.raises(BridgeValidationError) as exc:
        gateway.consume_activation(ticket, observer, **binding, operation_key="unauthenticated")  # type: ignore[arg-type]
    assert exc.value.audit_reason == "disconnected"
    with pytest.raises(BridgeValidationError) as exc:
        gateway.events(observer, association.association_ref)
    assert exc.value.audit_reason == "disconnected"


def test_future_cursor_and_mismatched_cursor_window_fail_closed():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    connection = gateway.connect(observer)
    current = connection.subscribe(association)
    cursor_type = type(current.cursor)
    future = cursor_type(current.cursor.cursor_version, current.cursor.association_ref, current.cursor.subscriber_ref,
                         current.cursor.stream_epoch, current.cursor.last_sequence,
                         "2026-07-29T13:00:00Z", "2026-07-29T14:00:00Z")
    with pytest.raises(BridgeValidationError) as exc:
        connection.replay(ReplayWindow(association.association_ref, current.snapshot.stream_epoch, current.cursor.last_sequence), future)
    assert exc.value.audit_reason == "future_cursor"
    with pytest.raises(BridgeValidationError) as exc:
        connection.replay(ReplayWindow(association.association_ref, current.snapshot.stream_epoch, 0), current.cursor)
    assert exc.value.audit_reason == "cursor_window_mismatch"


def test_observer_claims_and_initial_association_ttl_are_fail_closed():
    clock, gateway, observer, binding, ticket = setup(heartbeat=5)
    association = consume(gateway, observer, binding, ticket)
    forged = ObserverIdentity(observer.observer_ref, "other-owner", observer.profile_ref)
    with pytest.raises(BridgeValidationError) as exc:
        gateway.snapshot(forged, association)
    assert exc.value.code is BridgeErrorCode.FOREIGN_OWNER
    clock.advance(seconds=5)
    assert gateway.expire_stale() == 1


def test_public_operations_reject_malformed_observers_and_refs_with_validation_errors():
    _, gateway, observer, binding, ticket = setup()
    association = consume(gateway, observer, binding, ticket)
    operations = (
        lambda: gateway.snapshot(None, association),
        lambda: gateway.events(None, association),
        lambda: gateway.heartbeat(None, association),
        lambda: gateway.replay(None, ReplayWindow(association.association_ref, "epoch-1", 0)),
        lambda: gateway.disconnect(None),
        lambda: gateway.issue_activation(None, **binding),
        lambda: gateway.consume_activation(ticket, None, **binding, operation_key="bad"),
        lambda: gateway.snapshot(observer, None),
        lambda: gateway.events(observer, None),
        lambda: gateway.heartbeat(observer, None),
        lambda: gateway.revoke(observer, None),
    )
    for operation in operations:
        with pytest.raises(BridgeValidationError):
            operation()


def test_activation_error_text_is_uniform_but_audit_code_is_retained():
    error = BridgeValidationError(BridgeErrorCode.ACTIVATION_EXPIRED, audit_reason="sensitive-expiry-detail")
    assert str(error) == "activation_invalid"
    assert error.args == ("activation_invalid",)
    assert error.code is BridgeErrorCode.ACTIVATION_EXPIRED
    assert error.audit_reason == "sensitive-expiry-detail"
