"""B15b.3 fixtures — subscription v1: ordering, ack/outbox, TTLs, gaps.

Explicit association scope; contiguous ordering; outbox/ACK retriable;
liveness transitions; explicit `replay_gap`/`cursor_stale`/`cursor_expired`
— never silent. Local only; no live Hermes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.gateway_subscription import (
    ASSOCIATION_REQUIRED,
    ASSOCIATION_STALE,
    CURSOR_EXPIRED,
    CURSOR_TTL_S,
    GRACE_S,
    IDLE_TTL_S,
    NO_NEW_EVENTS,
    OBSERVING,
    RECONNECTING,
    REPLAY_GAP,
    STALE,
    GatewaySubscriptionStore,
)

NOW = 1_000_000.0


def _sub(store, subscriber="sub-1", association="assoc-1", epoch="epoch-1", snapshot=0, now=NOW):
    return store.subscribe(
        subscriber_ref=subscriber,
        association_ref=association,
        stream_epoch=epoch,
        boundary_ref="bnd-1",
        snapshot_sequence=snapshot,
        now=now,
    )


def _append(store, n, start=1):
    for sequence in range(start, start + n):
        assert store.append(sequence, f"evt-{sequence}")


def test_subscribe_requires_explicit_association():
    store = GatewaySubscriptionStore()
    assert _sub(store, association="") is None  # v1: no global/wildcard scope
    assert _sub(store, subscriber="") is None
    assert _sub(store, epoch="") is None
    assert (
        store.subscribe(
            subscriber_ref="sub-1",
            association_ref="assoc-1",
            stream_epoch="epoch-1",
            boundary_ref="",
            snapshot_sequence=0,
            now=NOW,
        )
        is None
    )
    subscription = _sub(store, snapshot=7)
    assert subscription is not None and subscription.cursor_seq == 7


def test_ordering_contiguous_append():
    store = GatewaySubscriptionStore()
    _append(store, 2)  # 1, 2
    assert not store.append(4, "evt-4")  # gap: no silent advancement
    assert store.append(3, "evt-3")
    assert not store.append(3, "evt-3-dup")  # duplicate


def test_event_id_sequence_bijection_enforced():
    store = GatewaySubscriptionStore()
    assert store.append(1, "evt-a")
    assert not store.append(2, "evt-a")  # same id, new sequence: conflict
    assert ("evt-a", "invalid_provenance") in store.audit_log()
    assert store.append(2, "evt-b")  # advancement resumes with a fresh id


def test_read_events_after_cursor_in_order():
    store = GatewaySubscriptionStore()
    _append(store, 3)
    _sub(store, snapshot=1)
    result = store.read("sub-1", "epoch-1", NOW + 1)
    assert result.outcome == "ok"
    assert [e.sequence for e in result.events] == [2, 3]


def test_no_new_events_at_head():
    store = GatewaySubscriptionStore()
    _append(store, 2)
    _sub(store, snapshot=2)
    result = store.read("sub-1", "epoch-1", NOW + 1)
    assert result.outcome == NO_NEW_EVENTS and result.events == ()
    assert not result.resync_required


def test_replay_gap_explicit():
    store = GatewaySubscriptionStore()
    _append(store, 3)
    _sub(store)
    store.prune(2)
    result = store.read("sub-1", "epoch-1", NOW + 1)
    assert result.outcome == REPLAY_GAP and result.resync_required
    assert result.events == ()
    assert ("sub-1", REPLAY_GAP) in store.audit_log()


def test_cursor_stale_on_epoch_mismatch():
    store = GatewaySubscriptionStore()
    _append(store, 1)
    _sub(store)
    result = store.read("sub-1", "epoch-other", NOW + 1)
    assert result.outcome == "cursor_stale" and result.resync_required
    assert ("sub-1", "cursor_stale") in store.audit_log()


def test_cursor_expired_ttl():
    store = GatewaySubscriptionStore()
    _append(store, 1)
    _sub(store)
    for i in range(1, 31):  # heartbeats every 30s keep liveness alive
        assert store.heartbeat("sub-1", i, NOW + i * 30)
    result = store.read("sub-1", "epoch-1", NOW + CURSOR_TTL_S + 1)
    assert result.outcome == CURSOR_EXPIRED and result.resync_required
    assert ("sub-1", CURSOR_EXPIRED) in store.audit_log()


def test_heartbeat_ordering():
    store = GatewaySubscriptionStore()
    _sub(store)
    assert store.heartbeat("sub-1", 1, NOW + 1)
    assert not store.heartbeat("sub-1", 1, NOW + 2)  # duplicate
    assert not store.heartbeat("sub-1", 0, NOW + 3)  # out-of-order
    assert store.heartbeat("sub-1", 2, NOW + 4)


def test_liveness_transitions_and_read():
    store = GatewaySubscriptionStore()
    _append(store, 1)
    _sub(store)
    assert store.evaluate("sub-1", NOW + IDLE_TTL_S + 1) == RECONNECTING
    result = store.read("sub-1", "epoch-1", NOW + IDLE_TTL_S + 1)  # liveness ≠ auth
    assert result.outcome == "ok"
    assert store.evaluate("sub-1", NOW + IDLE_TTL_S + GRACE_S + 2) == STALE
    denied = store.read("sub-1", "epoch-1", NOW + IDLE_TTL_S + GRACE_S + 2)
    assert denied.outcome == ASSOCIATION_STALE
    assert not store.heartbeat("sub-1", 9, NOW + IDLE_TTL_S + GRACE_S + 3)  # stale denies
    assert ("sub-1", ASSOCIATION_STALE) in store.audit_log()


def test_staleness_derived_immediately_without_evaluate():
    store = GatewaySubscriptionStore()
    _append(store, 1)
    _sub(store)
    result = store.read("sub-1", "epoch-1", NOW + IDLE_TTL_S + GRACE_S + 2)
    assert result.outcome == ASSOCIATION_STALE  # derived inline, no external step
    assert not store.heartbeat("sub-1", 1, NOW + IDLE_TTL_S + GRACE_S + 3)  # no revive


def test_heartbeat_resumes_from_reconnecting():
    store = GatewaySubscriptionStore()
    _sub(store)
    assert store.evaluate("sub-1", NOW + IDLE_TTL_S + 1) == RECONNECTING
    assert store.heartbeat("sub-1", 1, NOW + IDLE_TTL_S + 2)
    assert store.evaluate("sub-1", NOW + IDLE_TTL_S + 3) == OBSERVING


def test_ack_flow_and_outbox_retry():
    store = GatewaySubscriptionStore()
    _append(store, 2)
    _sub(store)
    result = store.read("sub-1", "epoch-1", NOW + 1)
    assert result.outcome == "ok"
    assert store.pending("sub-1") == (1, 2)  # delivered, not yet acked
    assert store.ack("sub-1", 1)
    assert store.pending("sub-1") == (2,)  # retriable from outbox
    assert not store.ack("sub-1", 1)  # already acked
    assert ("sub-1", "invalid_request") in store.audit_log()
    assert store.ack("sub-1", 2)
    assert store.pending("sub-1") == ()
    assert store.read("sub-1", "epoch-1", NOW + 2).outcome == NO_NEW_EVENTS


def test_ack_advances_only_contiguously():
    store = GatewaySubscriptionStore()
    _append(store, 3)
    _sub(store)
    store.read("sub-1", "epoch-1", NOW + 1)
    assert store.ack("sub-1", 2)  # out-of-order ack accepted...
    subscription = store._subscriptions["sub-1"]
    assert subscription.cursor_seq == 0  # ...but cursor does not jump
    assert store.ack("sub-1", 1)
    assert subscription.cursor_seq == 2  # contiguous run advanced
    assert store.ack("sub-1", 3)
    assert subscription.cursor_seq == 3


def test_detach_cancels_outbox_and_tombstones():
    store = GatewaySubscriptionStore()
    _append(store, 1)
    _sub(store)
    store.read("sub-1", "epoch-1", NOW + 1)
    assert store.pending("sub-1") == (1,)
    assert store.detach("sub-1")
    assert store.pending("sub-1") == ()  # cancelled, not delivered
    assert store.read("sub-1", "epoch-1", NOW + 2).outcome == ASSOCIATION_REQUIRED
    assert not store.heartbeat("sub-1", 9, NOW + 3)
    assert _sub(store) is None  # reassociation always emits new refs


def test_unknown_subscriber_no_disclosure():
    store = GatewaySubscriptionStore()
    result = store.read("sub-nope", "epoch-1", NOW)
    assert result.outcome == ASSOCIATION_REQUIRED and result.events == ()
    assert ("sub-nope", ASSOCIATION_REQUIRED) in store.audit_log()


def test_gap_blocks_ingestion_cursor_advancement():
    store = GatewaySubscriptionStore()
    assert store.append(1, "evt-1")
    assert not store.append(3, "evt-3")  # hole: blocked
    assert store.append(2, "evt-2")  # contiguous resumes
    _sub(store)
    result = store.read("sub-1", "epoch-1", NOW + 1)
    assert [e.sequence for e in result.events] == [1, 2]
