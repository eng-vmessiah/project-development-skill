"""B15b.3 — subscription v1 (explicit association) + ordering/ack + TTLs.

Local, deterministic implementation of the B15a Delivery and Recovery
Contract under matrix A4/A9/A10: order scoped to
``(association_ref, stream_epoch, sequence)``; durable processing order
(persist → outbox → deliver → ACK); gaps are explicit
(``replay_gap``/``cursor_stale``/``cursor_expired`` — never silent); TTL and
heartbeat are liveness, not authorization. v1 = explicit association scope
only (one association per store instance; opaque refs are literals — no
wildcard semantics); global/multi-session is deferred by design. Liveness
transitions (idle/grace) are derived immediately on every read, heartbeat
and evaluate call — never dependent on an external step.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

# ── Frozen constants (matrix A4/A9) ──────────────────────────────────────────
HEARTBEAT_S = 30
IDLE_TTL_S = 90
GRACE_S = 60
CURSOR_TTL_S = 900  # 15 min

# Canonical codes (G1 §7) — bounded, no disclosure.
INVALID_REQUEST = "invalid_request"
ASSOCIATION_REQUIRED = "association_required"
ASSOCIATION_STALE = "association_stale"
CURSOR_STALE = "cursor_stale"
CURSOR_EXPIRED = "cursor_expired"
REPLAY_GAP = "replay_gap"
NO_NEW_EVENTS = "no_new_events"

#: Subscription lifecycle states (delivery contract §Lifecycle, subset v1).
OBSERVING = "observing"
RECONNECTING = "reconnecting"
STALE = "stale"
DETACHED = "detached"


@dataclass(frozen=True)
class EventRecord:
    sequence: int
    event_id: str


@dataclass
class Subscription:
    subscriber_ref: str
    association_ref: str
    stream_epoch: str
    boundary_ref: str
    snapshot_sequence: int
    cursor_seq: int
    cursor_issued_at: float
    last_heartbeat_at: float
    last_heartbeat_seq: int = 0
    delivered_upto: int = 0
    state: str = OBSERVING


@dataclass(frozen=True)
class ReadResult:
    outcome: str
    events: tuple[EventRecord, ...] = ()
    resync_required: bool = False


class GatewaySubscriptionStore:
    """Single-writer store: history, subscriptions, outbox, tombstones."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: list[EventRecord] = []
        self._event_ids: dict[str, int] = {}
        self._ingestion_cursor = 0
        self._retention_floor = 0
        self._subscriptions: dict[str, Subscription] = {}
        self._outbox: dict[str, list[int]] = {}
        self._tombstones: set[str] = set()
        self._audit: list[tuple[str, str]] = []

    # ── issuance ──
    def subscribe(
        self,
        *,
        subscriber_ref: str,
        association_ref: str,
        stream_epoch: str,
        boundary_ref: str,
        snapshot_sequence: int,
        now: float,
    ) -> Subscription | None:
        """Explicit association only (v1); no global/wildcard scope."""
        if not subscriber_ref or not association_ref or not stream_epoch or not boundary_ref:
            return None
        with self._lock:
            if subscriber_ref in self._tombstones:
                return None  # reassociation always emits new refs
            subscription = Subscription(
                subscriber_ref=subscriber_ref,
                association_ref=association_ref,
                stream_epoch=stream_epoch,
                boundary_ref=boundary_ref,
                snapshot_sequence=snapshot_sequence,
                cursor_seq=snapshot_sequence,
                cursor_issued_at=now,
                last_heartbeat_at=now,
            )
            self._subscriptions[subscriber_ref] = subscription
            self._outbox[subscriber_ref] = []
            return subscription

    # ── ingestion (contiguous; gaps block advancement) ──
    def append(self, sequence: int, event_id: str) -> bool:
        with self._lock:
            if sequence != self._ingestion_cursor + 1:
                return False  # gap or duplicate: never advance silently
            if sequence <= self._retention_floor:
                return False
            if event_id in self._event_ids:
                # event_id <-> sequence bijection: conflict blocks advancement
                self._audit.append((event_id, "invalid_provenance"))
                return False
            self._history.append(EventRecord(sequence=sequence, event_id=event_id))
            self._event_ids[event_id] = sequence
            self._ingestion_cursor = sequence
            return True

    def prune(self, up_to_sequence: int) -> None:
        """Retention purge; cursors below the floor get explicit `replay_gap`."""
        with self._lock:
            self._retention_floor = max(self._retention_floor, up_to_sequence)
            self._history = [e for e in self._history if e.sequence > self._retention_floor]

    # ── liveness (heartbeat/TTL are NOT authorization) ──
    def heartbeat(self, subscriber_ref: str, heartbeat_sequence: int, now: float) -> bool:
        with self._lock:
            subscription = self._subscriptions.get(subscriber_ref)
            if subscription is None or subscriber_ref in self._tombstones:
                self._audit.append((subscriber_ref, ASSOCIATION_REQUIRED))
                return False
            self._derive_state(subscription, now)
            if subscription.state not in (OBSERVING, RECONNECTING):
                self._audit.append((subscriber_ref, ASSOCIATION_STALE))
                return False
            if heartbeat_sequence <= subscription.last_heartbeat_seq:
                self._audit.append((subscriber_ref, INVALID_REQUEST))
                return False  # out-of-order/duplicate heartbeat
            subscription.last_heartbeat_seq = heartbeat_sequence
            subscription.last_heartbeat_at = now
            if subscription.state == RECONNECTING:
                subscription.state = OBSERVING  # resumed heartbeat = reconnected
            return True

    def _derive_state(self, subscription: Subscription, now: float) -> str:
        """Derive liveness from heartbeat TTLs immediately (idle → grace)."""
        idle = now - subscription.last_heartbeat_at
        if subscription.state == OBSERVING and idle > IDLE_TTL_S:
            subscription.state = RECONNECTING
        if subscription.state == RECONNECTING and idle > IDLE_TTL_S + GRACE_S:
            subscription.state = STALE
        return subscription.state

    def evaluate(self, subscriber_ref: str, now: float) -> str | None:
        with self._lock:
            subscription = self._subscriptions.get(subscriber_ref)
            if subscription is None:
                return None
            return self._derive_state(subscription, now)

    # ── delivery ──
    def read(self, subscriber_ref: str, stream_epoch: str, now: float) -> ReadResult:
        with self._lock:
            def deny(code: str, resync: bool = False) -> ReadResult:
                self._audit.append((subscriber_ref, code))
                return ReadResult(outcome=code, resync_required=resync)

            subscription = self._subscriptions.get(subscriber_ref)
            if subscription is None or subscriber_ref in self._tombstones:
                return deny(ASSOCIATION_REQUIRED)
            if stream_epoch != subscription.stream_epoch:
                return deny(CURSOR_STALE, resync=True)
            if self._derive_state(subscription, now) == STALE:
                return deny(ASSOCIATION_STALE)
            if now - subscription.cursor_issued_at > CURSOR_TTL_S:
                return deny(CURSOR_EXPIRED, resync=True)
            if subscription.cursor_seq < self._retention_floor:
                return deny(REPLAY_GAP, resync=True)
            events = tuple(e for e in self._history if e.sequence > subscription.cursor_seq)
            if not events:
                return ReadResult(outcome=NO_NEW_EVENTS)
            outbox = self._outbox.setdefault(subscriber_ref, [])
            for event in events:
                if event.sequence not in outbox:
                    outbox.append(event.sequence)
            subscription.delivered_upto = max(
                subscription.delivered_upto, events[-1].sequence
            )
            return ReadResult(outcome="ok", events=events)

    def ack(self, subscriber_ref: str, sequence: int) -> bool:
        """ACK is separate and retriable; cursor advances only contiguously."""
        with self._lock:
            subscription = self._subscriptions.get(subscriber_ref)
            outbox = self._outbox.get(subscriber_ref)
            if subscription is None or subscriber_ref in self._tombstones or outbox is None:
                self._audit.append((subscriber_ref, ASSOCIATION_REQUIRED))
                return False
            if sequence not in outbox:
                self._audit.append((subscriber_ref, INVALID_REQUEST))
                return False
            outbox.remove(sequence)
            while (
                subscription.cursor_seq < subscription.delivered_upto
                and subscription.cursor_seq + 1 not in outbox
            ):
                subscription.cursor_seq += 1
            return True

    def pending(self, subscriber_ref: str) -> tuple[int, ...]:
        """Outbox contents (delivered, not yet acked) — retriable, no loss."""
        with self._lock:
            return tuple(self._outbox.get(subscriber_ref, ()))

    def detach(self, subscriber_ref: str) -> bool:
        """Invalidate irreversibly; pending outbox is cancelled, not delivered."""
        with self._lock:
            subscription = self._subscriptions.get(subscriber_ref)
            if subscription is None:
                return False
            self._tombstones.add(subscriber_ref)
            subscription.state = DETACHED
            self._outbox[subscriber_ref] = []
            return True

    def audit_log(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(self._audit)
