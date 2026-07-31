from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))
from scripts.pd_fleet.fake_gateway import FakeGateway
from scripts.pd_fleet.fleet_gateway_bridge import FleetGatewayBridge
from scripts.pd_fleet.gateway_bridge_contracts import (
    BridgeErrorCode, BridgeEvent, BridgeValidationError, ObserverIdentity, OwnershipMode,
    ReplayWindow,
)


def setup(retention=32):
    observer = ObserverIdentity("observer-1", "owner-1", "profile-1")
    gateway = FakeGateway(retention=retention)
    gateway.connect(observer)
    binding = dict(owner_ref="owner-1", profile_ref="profile-1", workspace_ref="workspace-1",
                   session_ref="session-1", association_ref="association-1", purpose="pd_observation")
    ticket = gateway.issue_activation(observer, **binding)
    return gateway, observer, binding, ticket


def test_attach_rejects_unknown_and_malicious_binding_without_forwarding():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    original = bridge._connection
    calls = []

    class RecordingConnection:
        def consume_activation(self, activation, **values):
            calls.append((activation, values))
            return original.consume_activation(activation, **values)

        def snapshot(self, association):
            return original.snapshot(association)

    bridge._connection = RecordingConnection()
    with pytest.raises(BridgeValidationError) as unknown:
        bridge.attach(ticket, {**binding, "token": "credential-secret"})
    assert unknown.value.code is BridgeErrorCode.INVALID_REQUEST
    assert unknown.value.audit_reason == "unknown_binding_field"
    assert calls == []

    for field, value in (("session_ref", "../secret"), ("workspace_ref", "https://host/path"),
                         ("profile_ref", "profile-1\\nleak"), ("owner_ref", "x" * 129)):
        with pytest.raises(BridgeValidationError):
            bridge.attach(ticket, {**binding, field: value})
    assert calls == []


def test_attach_normalizes_injected_errors_to_bounded_text():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()

    class ExplodingConnection:
        def consume_activation(self, activation, **values):
            raise RuntimeError("provider token=TOP-SECRET https://internal.example/credential")

    bridge._connection = ExplodingConnection()
    with pytest.raises(BridgeValidationError) as exc:
        bridge.attach(ticket, binding)
    assert exc.value.code is BridgeErrorCode.INVALID_REQUEST
    assert str(exc.value) == BridgeErrorCode.INVALID_REQUEST.value
    assert "TOP-SECRET" not in str(exc.value)
    assert "internal.example" not in str(exc.value)


def test_attach_snapshot_subscribe_and_bounded_outbox():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    assert bridge.snapshot(association).ownership_mode is OwnershipMode.USER_OWNED_SESSION
    stream = bridge.subscribe(association)
    assert [event.event_type for event in stream.events] == ["session.registered"]
    assert len(bridge.pending()) == 1
    bridge.ack(stream.events[0].event_id)
    assert not bridge.pending()
    bridge.close()


def test_replay_pagination_persists_cursor_and_duplicate_delivery_is_idempotent():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    bridge.heartbeat(association)
    bridge.heartbeat(association)
    epoch = bridge.snapshot(association).stream_epoch
    first = bridge.replay(ReplayWindow(association.association_ref, epoch, 0, 1))
    second = bridge.replay(ReplayWindow(association.association_ref, epoch, 1, 1), first.cursor)
    assert first.cursor.last_sequence == 1 and second.cursor.last_sequence == 2
    # Re-delivery cannot create another row or move the cursor backwards.
    bridge.replay(ReplayWindow(association.association_ref, epoch, 1, 1), first.cursor)
    assert bridge._store.cursor(association.association_ref, observer.observer_ref).last_sequence == 2


def test_failure_does_not_advance_cursor_and_fleet_owned_is_denied():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    with pytest.raises(BridgeValidationError) as exc:
        bridge.attach(ticket, {**binding, "ownership_mode": "fleet_owned_task"})
    assert exc.value.code is BridgeErrorCode.CAPABILITY_DENIED
    association = bridge.attach(ticket, binding)
    stream = bridge.subscribe(association)
    with pytest.raises(BridgeValidationError):
        bridge.replay(ReplayWindow(association.association_ref, "wrong-epoch", stream.cursor.last_sequence), stream.cursor)
    assert bridge._store.cursor(association.association_ref, observer.observer_ref).last_sequence == stream.cursor.last_sequence


def test_forged_returned_cursor_subscriber_is_rejected_before_persistence():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    original = bridge._connection

    class ForgedCursorConnection:
        def __getattr__(self, name):
            return getattr(original, name)

        def subscribe(self, association, cursor=None, *, limit=None):
            result = original.subscribe(association, cursor, limit=limit)
            forged = replace(result.cursor, subscriber_ref="forged-subscriber")
            return replace(result, cursor=forged)

    bridge._connection = ForgedCursorConnection()
    with pytest.raises(BridgeValidationError) as exc:
        bridge.subscribe(association)
    assert exc.value.code is BridgeErrorCode.INVALID_PROVENANCE
    assert bridge._store.cursor(association.association_ref, observer.observer_ref) is None
    assert bridge.pending() == ()


@pytest.mark.parametrize("field", ["association_ref", "stream_epoch", "subscriber_ref"])
def test_supplied_cursor_binding_is_rejected_before_permissive_upstream(field):
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    stream = bridge.subscribe(association)
    original = bridge._connection
    calls = []
    values = {
        "association_ref": "other-association",
        "stream_epoch": "other-epoch",
        "subscriber_ref": "other-subscriber",
    }

    class PermissiveConnection:
        def subscribe(self, requested, cursor=None, *, limit=None):
            calls.append(("subscribe", requested, cursor))
            return original.subscribe(requested, cursor, limit=limit)

        def replay(self, window, cursor=None):
            calls.append(("replay", window, cursor))
            return original.replay(window, cursor)

        def __getattr__(self, name):
            return getattr(original, name)

    bridge._connection = PermissiveConnection()
    forged = replace(stream.cursor, **{field: values[field]})
    with pytest.raises(BridgeValidationError) as exc:
        bridge.subscribe(association, forged)
    assert exc.value.code is BridgeErrorCode.INVALID_PROVENANCE
    assert calls == []
    assert bridge._store.cursor(association.association_ref, observer.observer_ref) == stream.cursor

    epoch = bridge.snapshot(association).stream_epoch
    forged = replace(stream.cursor, **{field: values[field]})
    window = ReplayWindow(association.association_ref, epoch, stream.cursor.last_sequence)
    with pytest.raises(BridgeValidationError) as exc:
        bridge.replay(window, forged)
    assert exc.value.code is BridgeErrorCode.INVALID_PROVENANCE
    assert calls == []


def test_expired_supplied_cursor_is_rejected_before_permissive_upstream():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    stream = bridge.subscribe(association)
    original = bridge._connection
    calls = []

    class PermissiveConnection:
        def subscribe(self, requested, cursor=None, *, limit=None):
            calls.append("subscribe")
            return original.subscribe(requested, cursor, limit=limit)

        def __getattr__(self, name):
            return getattr(original, name)

    bridge._connection = PermissiveConnection()
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    expired = replace(
        stream.cursor,
        issued_at=(datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat().replace("+00:00", "Z"),
        expires_at=expired_at,
    )
    with pytest.raises(BridgeValidationError) as exc:
        bridge.subscribe(association, expired)
    assert exc.value.code is BridgeErrorCode.RESYNC_REQUIRED
    assert exc.value.audit_reason == "cursor_expired"
    assert calls == []
    assert bridge._store.cursor(association.association_ref, observer.observer_ref) == stream.cursor


def test_reopen_sqlite_store_and_corruption_fails_closed():
    gateway, observer, binding, ticket = setup()
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "bridge.sqlite")
        first = FleetGatewayBridge(gateway, observer, store_path=path).connect()
        association = first.attach(ticket, binding); first.subscribe(association); first.close()
        second = FleetGatewayBridge(gateway, observer, store_path=path).connect()
        assert second.status(association).association_ref == association.association_ref
        second._store.db.execute("UPDATE fleet_bridge_events SET record_json='{}'"); second._store.db.commit()
        with pytest.raises(BridgeValidationError) as exc: second._store.events(association.association_ref)
        assert exc.value.code is BridgeErrorCode.INVALID_EVENT
        second.close()


def test_malformed_existing_schema_fails_closed():
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "malformed.sqlite")
        db = __import__("sqlite3").connect(path)
        db.executescript("""
            CREATE TABLE fleet_bridge_associations (association_ref TEXT);
            CREATE TABLE fleet_bridge_events (association_ref TEXT, stream_epoch TEXT, sequence INTEGER, event_id TEXT, record_json TEXT);
            CREATE TABLE fleet_bridge_outbox (event_id TEXT, association_ref TEXT, record_json TEXT, acknowledged INTEGER);
            CREATE TABLE fleet_bridge_cursors (association_ref TEXT, subscriber_ref TEXT, record_json TEXT, last_sequence INTEGER);
        """)
        db.commit(); db.close()
        with pytest.raises(BridgeValidationError) as exc:
            FleetGatewayBridge(object(), ObserverIdentity("observer-1", "owner-1", "profile-1"), store_path=path)
        assert exc.value.code is BridgeErrorCode.INVALID_REQUEST
        assert exc.value.audit_reason == "incompatible_store_schema"



def test_no_hermes_state_db_or_control_surface():
    source = (Path(__file__).parents[2] / "scripts/pd_fleet/fleet_gateway_bridge.py").read_text()
    tree = ast.parse(source)
    imports = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert "hermes" not in imports and "subprocess" not in imports
    names = {n.name for n in tree.body if isinstance(n, ast.ClassDef) for n in n.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not names & {"prompt", "dispatch", "cancel", "tool", "provider", "mutate", "send"}


def test_detach_persists_terminal_event_and_local_detached_state():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    bridge.detach(association)
    assert [event.event_type for event in bridge.pending()] == ["session.detached"]
    row = bridge._store.db.execute(
        "SELECT record_json, status FROM fleet_bridge_associations WHERE association_ref=?",
        (association.association_ref,),
    ).fetchone()
    assert row[1] == "detached"
    assert __import__("json").loads(row[0])["status"] == "detached"


@pytest.mark.parametrize("field", ["association_ref", "session_ref", "stream_epoch", "sequence"])
def test_detach_rejects_terminal_provenance_mismatch_before_local_writes(field):
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    original = bridge._connection

    class ForgedDetach:
        def revoke(self, requested):
            event = original.revoke(requested)
            values = {
                "association_ref": "other-association",
                "session_ref": "other-session",
                "stream_epoch": "other-epoch",
                "sequence": event.sequence + 2,
            }
            return replace(event, **{field: values[field]})

        def __getattr__(self, name):
            return getattr(original, name)

    bridge._connection = ForgedDetach()
    with pytest.raises(BridgeValidationError) as exc:
        bridge.detach(association)
    assert exc.value.code in (
        BridgeErrorCode.ASSOCIATION_REQUIRED,
        BridgeErrorCode.INVALID_EVENT,
        BridgeErrorCode.INVALID_PROVENANCE,
        BridgeErrorCode.REPLAY_GAP,
        BridgeErrorCode.RESYNC_REQUIRED,
    )
    assert not bridge._store.events(association.association_ref)
    row = bridge._store.db.execute(
        "SELECT status FROM fleet_bridge_associations WHERE association_ref=?",
        (association.association_ref,),
    ).fetchone()
    assert row[0] == "observing"


def test_subscribe_always_transmits_conservative_bound():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    original = bridge._connection
    seen = []

    class RecordingConnection:
        def __getattr__(self, name):
            return getattr(original, name)

        def subscribe(self, association, cursor=None, *, limit=None):
            seen.append(limit)
            return original.subscribe(association, cursor, limit=limit)

    bridge._connection = RecordingConnection()
    bridge.subscribe(association)
    bridge.subscribe(association, limit=7)
    assert seen == [100, 7]
    with pytest.raises(BridgeValidationError) as exc:
        bridge.subscribe(association, limit=101)
    assert exc.value.code is BridgeErrorCode.INVALID_REQUEST


def test_replay_always_transmits_and_enforces_conservative_bound():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    epoch = bridge.snapshot(association).stream_epoch
    original = bridge._connection
    seen = []

    class RecordingConnection:
        def __getattr__(self, name):
            return getattr(original, name)

        def replay(self, window, cursor=None):
            seen.append(window.limit)
            return original.replay(window, cursor)

    bridge._connection = RecordingConnection()
    bridge.replay(ReplayWindow(association.association_ref, epoch, 0, 1))
    assert seen == [1]
    for limit in (101, 1000):
        with pytest.raises(BridgeValidationError) as exc:
            bridge.replay(ReplayWindow(association.association_ref, epoch, 0, limit))
        assert exc.value.code is BridgeErrorCode.INVALID_REQUEST
    assert seen == [1]


def test_malformed_upstream_results_are_normalized_and_not_persisted():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    epoch = bridge.snapshot(association).stream_epoch
    original = bridge._connection

    class MalformedConnection:
        def snapshot(self, association):
            return object()

        def subscribe(self, association, cursor=None, *, limit=None):
            return object()

        def replay(self, window, cursor=None):
            return object()

        def __getattr__(self, name):
            return getattr(original, name)

    bridge._connection = MalformedConnection()
    for operation in (
        lambda: bridge.snapshot(association),
        lambda: bridge.subscribe(association),
        lambda: bridge.replay(ReplayWindow(association.association_ref, epoch, 0, 1)),
    ):
        with pytest.raises(BridgeValidationError) as exc:
            operation()
        assert exc.value.code in (BridgeErrorCode.INVALID_EVENT, BridgeErrorCode.RESYNC_REQUIRED)
        assert exc.value.audit_reason
    assert bridge._store.db.execute(
        "SELECT 1 FROM fleet_bridge_associations WHERE association_ref=?",
        (association.association_ref,),
    ).fetchone() is not None
    assert not bridge._store.events(association.association_ref)


def test_event_identity_conflicts_are_invalid_provenance():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    event = bridge.subscribe(association).events[0]
    snapshot = bridge.snapshot(association)

    conflicting_sequence = BridgeEvent.from_dict({**event.to_dict(), "sequence": event.sequence + 1})
    with pytest.raises(BridgeValidationError) as exc:
        bridge._store.ingest(snapshot, (conflicting_sequence,), None)
    assert exc.value.code is BridgeErrorCode.INVALID_PROVENANCE
    assert exc.value.audit_reason == "event_id_conflict"

    conflicting_payload = BridgeEvent.from_dict({
        **event.to_dict(), "payload": {"runtime_surface": "gateway_bridge", "metadata_version": 0},
    })
    with pytest.raises(BridgeValidationError) as exc:
        bridge._store.ingest(snapshot, (conflicting_payload,), None)
    assert exc.value.code is BridgeErrorCode.INVALID_PROVENANCE
    assert exc.value.audit_reason == "sequence_identity_conflict"


def test_malformed_heartbeat_result_is_bounded_and_not_persisted():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    original = bridge._connection

    class MalformedHeartbeat:
        def heartbeat(self, association):
            return type("Result", (), {"snapshot": object(), "event": object()})()

        def __getattr__(self, name):
            return getattr(original, name)

    bridge._connection = MalformedHeartbeat()
    with pytest.raises(BridgeValidationError) as exc:
        bridge.heartbeat(association)
    assert exc.value.code in (BridgeErrorCode.INVALID_EVENT, BridgeErrorCode.RESYNC_REQUIRED)
    assert exc.value.audit_reason
    assert not bridge._store.events(association.association_ref)


@pytest.mark.parametrize("event_source", [None, object()])
def test_malformed_detach_event_source_is_rejected_before_persistence(event_source):
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    original = bridge._connection

    class MalformedDetach:
        def revoke(self, association):
            return None

        def events(self, association):
            return event_source

        def __getattr__(self, name):
            return getattr(original, name)

    bridge._connection = MalformedDetach()
    with pytest.raises(BridgeValidationError) as exc:
        bridge.detach(association)
    assert exc.value.code is BridgeErrorCode.INVALID_EVENT
    assert exc.value.audit_reason == "malformed_event_source"
    assert not bridge._store.events(association.association_ref)


def test_legacy_detach_event_source_failure_is_normalized_before_persistence():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    original = bridge._connection

    class MalformedLegacyDetach:
        def revoke(self, association):
            return None

        def events(self, observer, association_ref):
            raise AttributeError("malformed legacy source")

        def __getattr__(self, name):
            return getattr(original, name)

    bridge._connection = MalformedLegacyDetach()
    with pytest.raises(BridgeValidationError) as exc:
        bridge.detach(association)
    assert exc.value.code is BridgeErrorCode.INVALID_EVENT
    assert exc.value.audit_reason == "malformed_event_source"
    assert not bridge._store.events(association.association_ref)


def test_requested_binding_mismatch_is_rejected_before_persistence():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    original = bridge._connection
    class ForgedSnapshot:
        def snapshot(self, association):
            return replace(original.snapshot(association), session_ref="forged-session")
        def __getattr__(self, name):
            return getattr(original, name)
    bridge._connection = ForgedSnapshot()
    with pytest.raises(BridgeValidationError) as exc:
        bridge.attach(ticket, binding)
    assert exc.value.code is BridgeErrorCode.INVALID_PROVENANCE
    assert not bridge._store.events(binding["association_ref"])


def test_terminal_state_is_sticky_against_late_observing_snapshot():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    prior = bridge.snapshot(association)
    bridge.detach(association)
    original = bridge._connection
    class LateObserving:
        def snapshot(self, requested):
            return replace(prior, status="observing", sequence=0)
        def __getattr__(self, name):
            return getattr(original, name)
    bridge._connection = LateObserving()
    bridge.snapshot(association)
    assert bridge._store.db.execute("SELECT status FROM fleet_bridge_associations WHERE association_ref=?", (association.association_ref,)).fetchone()[0] == "detached"


def test_duplicate_detach_event_is_idempotent():
    gateway, observer, binding, ticket = setup()
    bridge = FleetGatewayBridge(gateway, observer, in_memory=True).connect()
    association = bridge.attach(ticket, binding)
    event = bridge._connection.revoke(association)
    bridge._store.ingest_events((event,))
    bridge._store.ingest_events((event,))
    assert [item.event_id for item in bridge._store.events(association.association_ref)] == [event.event_id]
    assert bridge._store.db.execute("SELECT status FROM fleet_bridge_associations WHERE association_ref=?", (association.association_ref,)).fetchone()[0] == "detached"
