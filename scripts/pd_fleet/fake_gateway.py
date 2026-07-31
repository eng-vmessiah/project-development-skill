"""Deterministic in-memory Gateway protocol double for local G5/G6 validation.

This module is deliberately not a transport or Hermes runtime.  It models only the
bounded activation, association, snapshot, lifecycle event, replay, and heartbeat
semantics in ``gateway_bridge_contracts``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from hashlib import sha256
from threading import RLock
from typing import Callable, Iterator, Mapping, Protocol, cast

from .gateway_bridge_contracts import (
    SCHEMA_VERSION, MAX_REPLAY_BATCH, ActivationTicketRef, AssociationRef, BridgeCursor,
    BridgeErrorCode, BridgeEvent, BridgeValidationError, EventOrigin,
    ObserverIdentity, OwnershipMode, ReplayWindow, SessionSnapshot,
)


class GatewayClient(Protocol):
    def connect(self, observer: ObserverIdentity) -> "FakeConnection": ...
    def issue_activation(self, observer: ObserverIdentity, **binding: str) -> ActivationTicketRef: ...
    def consume_activation(self, ticket: str | ActivationTicketRef, observer: ObserverIdentity, **binding: str) -> AssociationRef: ...


@dataclass(frozen=True)
class ActivationBinding:
    observer_ref: str
    owner_ref: str | None
    profile_ref: str | None
    workspace_ref: str | None
    session_ref: str
    association_ref: str
    purpose: str


@dataclass(frozen=True)
class StreamResult:
    snapshot: SessionSnapshot
    boundary_ref: str
    cursor: BridgeCursor
    events: tuple[BridgeEvent, ...] = ()
    code: BridgeErrorCode | None = None

    @property
    def no_new_events(self) -> bool:
        return self.code is BridgeErrorCode.NO_NEW_EVENTS


@dataclass(frozen=True)
class HeartbeatResult:
    snapshot: SessionSnapshot
    event: BridgeEvent


@dataclass
class _Ticket:
    value: str
    binding: ActivationBinding
    issued_at: datetime
    expires_at: datetime
    consumed_operation: str | None = None
    association: AssociationRef | None = None


@dataclass
class _Association:
    ref: AssociationRef
    binding: ActivationBinding
    epoch: str
    status: str = "observing"
    sequence: int = 0
    metadata_version: int = 0
    heartbeat_at: datetime | None = None
    associated_at: datetime | None = None
    heartbeat_sequence: int = 0
    events: list[BridgeEvent] | None = None
    revoked: bool = False


def _activation_boundary(method):
    """Redact every validation failure crossing an activation API boundary."""
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except BridgeValidationError as error:
            raise BridgeValidationError(
                error.code, audit_reason=error.audit_reason, activation=True
            ) from None
    return wrapped


class FakeConnection:
    """Client-facing connection facade; all state remains owned by FakeGateway."""
    def __init__(self, gateway: "FakeGateway", observer: ObserverIdentity):
        self._gateway, self.observer = gateway, observer
        self._generation = gateway._generation(observer.observer_ref)
        self._closed = False

    def _check(self) -> None:
        if self._closed:
            self._gateway._uniform("disconnected")
        self._gateway._ensure_connected(self.observer, self._generation)

    def issue_activation(self, **binding: str) -> ActivationTicketRef:
        self._check()
        return self._gateway.issue_activation(self.observer, **binding)

    def consume_activation(self, ticket: str | ActivationTicketRef, **binding: object) -> AssociationRef:
        self._check()
        return self._gateway.consume_activation(ticket, self.observer, **binding)  # type: ignore[arg-type]

    def snapshot(self, association: str | AssociationRef) -> SessionSnapshot:
        self._check()
        return self._gateway.snapshot(self.observer, association)

    def subscribe(self, association: str | AssociationRef, cursor: BridgeCursor | None = None, *, limit: int | None = None) -> StreamResult:
        self._check()
        return self._gateway.subscribe(self.observer, association, cursor, limit=limit)

    def replay(self, window: ReplayWindow, cursor: BridgeCursor | None = None) -> StreamResult:
        self._check()
        return self._gateway.replay(self.observer, window, cursor)

    def heartbeat(self, association: str | AssociationRef) -> HeartbeatResult:
        self._check()
        return self._gateway.heartbeat(self.observer, association)

    def revoke(self, association: str | AssociationRef) -> BridgeEvent | None:
        self._check()
        return self._gateway.revoke(self.observer, association)

    def events(self, association: str | AssociationRef, *, limit: int | None = None) -> Iterator[BridgeEvent]:
        """Return the authenticated, directly bounded event view."""
        self._check()
        return self._gateway.events(self.observer, self._gateway._association_ref(association), limit=limit)

    def disconnect(self) -> None:
        if self._closed:
            self._gateway._uniform("disconnected")
        # Disconnect is the invalidating operation itself, so an otherwise
        # stale facade may still request it; the gateway then bumps the epoch.
        self._closed = True
        self._gateway.disconnect(self.observer)


class FakeGateway:
    """In-memory protocol double with deterministic time and bounded retention."""
    def __init__(self, *, clock: Callable[[], datetime] | None = None,
                 activation_ttl: timedelta = timedelta(minutes=5), heartbeat_ttl: timedelta = timedelta(seconds=30),
                 retention: int = 32):
        if retention < 1 or activation_ttl <= timedelta(0) or heartbeat_ttl <= timedelta(0):
            raise ValueError("invalid fake gateway bounds")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.activation_ttl, self.heartbeat_ttl, self.retention = activation_ttl, heartbeat_ttl, retention
        self._lock = RLock()
        self._counter = 0
        self._tickets: dict[str, _Ticket] = {}
        self._associations: dict[str, _Association] = {}
        self._connected: set[str] = set()
        self._generations: dict[str, int] = {}
        self._reset_generation = 0

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def _ref(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"

    def _uniform(self, reason: str) -> None:
        raise BridgeValidationError(BridgeErrorCode.ACTIVATION_INVALID, audit_reason=reason)

    def _generation(self, observer_ref: str) -> int:
        return self._generations.get(observer_ref, 0)

    @staticmethod
    def _observer(observer: object) -> ObserverIdentity:
        if not isinstance(observer, ObserverIdentity):
            raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="malformed_observer")
        return observer

    @staticmethod
    def _association_ref(association: object) -> str:
        if isinstance(association, AssociationRef):
            return association.association_ref
        if isinstance(association, str) and association:
            return association
        raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="malformed_association")

    def _ensure_connected(self, observer: ObserverIdentity, generation: int | None = None) -> None:
        observer = self._observer(observer)
        with self._lock:
            if (observer.observer_ref not in self._connected
                    or (generation is not None and generation != self._generation(observer.observer_ref))):
                self._uniform("disconnected")

    def connect(self, observer: ObserverIdentity) -> FakeConnection:
        if not isinstance(observer, ObserverIdentity):
            raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="malformed_observer")
        with self._lock:
            self._generations[observer.observer_ref] = self._generation(observer.observer_ref) + 1
            self._connected.add(observer.observer_ref)
        return FakeConnection(self, observer)

    def disconnect(self, observer: ObserverIdentity) -> None:
        observer = self._observer(observer)
        with self._lock:
            self._ensure_connected(observer)
            self._connected.discard(observer.observer_ref)
            self._generations[observer.observer_ref] = self._generation(observer.observer_ref) + 1

    @_activation_boundary
    def issue_activation(self, observer: ObserverIdentity, *, owner_ref: str | None = None,
                         profile_ref: str | None = None, workspace_ref: str | None = None,
                         session_ref: str, association_ref: str | None = None, purpose: str) -> ActivationTicketRef:
        if not isinstance(observer, ObserverIdentity) or not isinstance(purpose, str) or not purpose:
            raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="malformed_activation")
        with self._lock:
            self._ensure_connected(observer)
            if purpose != "pd_observation":
                raise BridgeValidationError(BridgeErrorCode.CAPABILITY_DENIED, audit_reason="capability_denied")
            association_ref = association_ref or self._ref("assoc")
            binding = ActivationBinding(observer.observer_ref, owner_ref, profile_ref, workspace_ref, session_ref, association_ref, purpose)
            # Constructing the public ref validates all caller-controlled identifiers.
            requested = AssociationRef(association_ref, session_ref, owner_ref, profile_ref, workspace_ref)
            existing = self._associations.get(association_ref)
            if existing is not None and (existing.ref != requested or existing.binding != binding):
                self._uniform("association_collision")
            now = self._now(); value = self._ref("ticket")
            opaque = sha256(f"{value}|{self._reset_generation}".encode()).hexdigest()[:32]
            self._tickets[opaque] = _Ticket(opaque, binding, now, now + self.activation_ttl)
            return ActivationTicketRef(opaque)

    def _ticket(self, ticket: str | ActivationTicketRef) -> _Ticket:
        value = ticket.activation_ref if isinstance(ticket, ActivationTicketRef) else ticket
        if not isinstance(value, str): self._uniform("malformed_ticket")
        item = self._tickets.get(value)
        if item is None: self._uniform("unknown_ticket")
        return cast(_Ticket, item)

    @staticmethod
    def _binding(observer: ObserverIdentity, binding: Mapping[str, str | None], item: ActivationBinding) -> bool:
        return (observer.observer_ref == item.observer_ref
                and observer.owner_ref == item.owner_ref
                and observer.profile_ref == item.profile_ref
                and all(binding.get(k) == getattr(item, k) for k in
                ("owner_ref", "profile_ref", "workspace_ref", "session_ref", "association_ref", "purpose")))

    @_activation_boundary
    def consume_activation(self, ticket: str | ActivationTicketRef, observer: ObserverIdentity, *,
                           owner_ref: str | None = None, profile_ref: str | None = None,
                           workspace_ref: str | None = None, session_ref: str, association_ref: str,
                           purpose: str, operation_key: str,
                           ownership_mode: OwnershipMode = OwnershipMode.USER_OWNED_SESSION) -> AssociationRef:
        if not isinstance(observer, ObserverIdentity) or not isinstance(operation_key, str) or not operation_key:
            raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="malformed_consume")
        with self._lock:
            self._ensure_connected(observer)
            if purpose != "pd_observation":
                raise BridgeValidationError(BridgeErrorCode.CAPABILITY_DENIED, audit_reason="capability_denied")
            item = self._ticket(ticket); now = self._now()
            candidate = {"owner_ref": owner_ref, "profile_ref": profile_ref, "workspace_ref": workspace_ref,
                         "session_ref": session_ref, "association_ref": association_ref, "purpose": purpose}
            if not self._binding(observer, candidate, item.binding): self._uniform("binding_mismatch")
            if now >= item.expires_at: self._uniform("expired")
            if item.consumed_operation is not None:
                if item.consumed_operation == operation_key and item.association is not None: return item.association
                self._uniform("replayed")
            assoc = AssociationRef(association_ref, session_ref, owner_ref, profile_ref, workspace_ref, ownership_mode)
            if assoc.ownership_mode is OwnershipMode.FLEET_OWNED_TASK: raise BridgeValidationError(BridgeErrorCode.CAPABILITY_DENIED, audit_reason="fleet_owned_task")
            existing = self._associations.get(assoc.association_ref)
            if existing is not None:
                if existing.ref != assoc or existing.binding != item.binding:
                    self._uniform("association_collision")
                item.consumed_operation, item.association = operation_key, existing.ref
                return existing.ref
            epoch = self._ref("epoch")
            state = _Association(assoc, item.binding, epoch, associated_at=now, events=[])
            self._associations[assoc.association_ref] = state
            item.consumed_operation, item.association = operation_key, assoc
            self._append(state, "session.registered", {"runtime_surface": "gateway", "metadata_version": 0})
            return assoc

    def _state(self, observer: ObserverIdentity, association: str | AssociationRef) -> _Association:
        observer = self._observer(observer)
        ref = self._association_ref(association)
        state = self._associations.get(ref) if isinstance(ref, str) else None
        if state is None: raise BridgeValidationError(BridgeErrorCode.ASSOCIATION_REQUIRED, audit_reason="unknown_association")
        if (state.binding.observer_ref != observer.observer_ref
                or state.binding.owner_ref != observer.owner_ref
                or state.binding.profile_ref != observer.profile_ref):
            raise BridgeValidationError(BridgeErrorCode.FOREIGN_OWNER, audit_reason="observer_binding_mismatch")
        if state.revoked: raise BridgeValidationError(BridgeErrorCode.ASSOCIATION_STALE, audit_reason="revoked")
        return state

    def snapshot(self, observer: ObserverIdentity, association: str | AssociationRef) -> SessionSnapshot:
        with self._lock:
            self._ensure_connected(observer)
            s = self._state(observer, association)
            return SessionSnapshot(s.ref.session_ref, s.ref.association_ref, s.ref.ownership_mode, s.status, s.epoch, s.sequence, s.metadata_version)

    def _cursor(self, s: _Association, last_sequence: int | None = None) -> BridgeCursor:
        now = self._now()
        if last_sequence is None:
            last_sequence = s.sequence
        return BridgeCursor(SCHEMA_VERSION, s.ref.association_ref, s.binding.observer_ref, s.epoch, last_sequence,
                            now.isoformat().replace("+00:00", "Z"), (now + self.activation_ttl).isoformat().replace("+00:00", "Z"))

    def _append(self, s: _Association, event_type: str, payload: dict[str, object]) -> BridgeEvent:
        s.sequence += 1; now = self._now(); occurred = now.isoformat().replace("+00:00", "Z")
        identity = f"{s.ref.association_ref}|{s.epoch}|{s.sequence}|{event_type}|{occurred}|{payload}"
        event_id = "evt-" + sha256(identity.encode()).hexdigest()[:24]
        event = BridgeEvent(SCHEMA_VERSION, event_id, event_type, occurred, "hermes-gateway", EventOrigin.GATEWAY_NATIVE,
                            s.ref.session_ref, s.ref.association_ref, s.ref.ownership_mode, s.epoch, s.sequence, payload,
                            {"transport": "gateway-event-stream", "correlation_id": "corr-" + s.ref.association_ref})
        assert s.events is not None
        s.events.append(event)
        del s.events[:-self.retention]
        return event

    def subscribe(self, observer: ObserverIdentity, association: str | AssociationRef, cursor: BridgeCursor | None = None, *, limit: int | None = None) -> StreamResult:
        with self._lock:
            self._ensure_connected(observer)
            s = self._state(observer, association); snapshot = self.snapshot(observer, association)
            boundary = "boundary-" + str(s.sequence)
            requested_limit = MAX_REPLAY_BATCH if limit is None else limit
            if (isinstance(requested_limit, bool) or not isinstance(requested_limit, int)
                    or not 1 <= requested_limit <= MAX_REPLAY_BATCH):
                raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="invalid_replay_limit")
            events = tuple(s.events or ()) if cursor is None else self._replay(s, ReplayWindow(s.ref.association_ref, s.epoch, cursor.last_sequence, limit=requested_limit), cursor)
            events = events[:requested_limit]
            last_sequence = events[-1].sequence if events else (cursor.last_sequence if cursor else s.sequence)
            return StreamResult(snapshot, boundary, self._cursor(s, last_sequence), events)

    def _replay(self, s: _Association, window: ReplayWindow, cursor: BridgeCursor | None) -> tuple[BridgeEvent, ...]:
        now = self._now()
        if cursor is not None and (
            window.association_ref != cursor.association_ref
            or window.stream_epoch != cursor.stream_epoch
            or window.after_sequence != cursor.last_sequence
        ):
            self._uniform("cursor_window_mismatch")
        if window.stream_epoch != s.epoch:
            raise BridgeValidationError(BridgeErrorCode.RESYNC_REQUIRED, audit_reason="epoch_changed")
        if cursor is not None:
            if cursor.association_ref != s.ref.association_ref or cursor.subscriber_ref != s.binding.observer_ref: self._uniform("cursor_binding_mismatch")
            if cursor.stream_epoch != s.epoch: raise BridgeValidationError(BridgeErrorCode.RESYNC_REQUIRED, audit_reason="epoch_changed")
            try:
                issued_at = datetime.fromisoformat(cursor.issued_at.replace("Z", "+00:00"))
                expires_at = datetime.fromisoformat(cursor.expires_at.replace("Z", "+00:00"))
            except ValueError:
                raise BridgeValidationError(BridgeErrorCode.CURSOR_STALE, audit_reason="invalid_cursor_time")
            if issued_at.tzinfo is None or expires_at.tzinfo is None:
                raise BridgeValidationError(BridgeErrorCode.CURSOR_STALE, audit_reason="invalid_cursor_time")
            if issued_at.astimezone(timezone.utc) > now:
                raise BridgeValidationError(BridgeErrorCode.CURSOR_STALE, audit_reason="future_cursor")
            if now >= expires_at.astimezone(timezone.utc): raise BridgeValidationError(BridgeErrorCode.CURSOR_EXPIRED, audit_reason="cursor_expired")
            if cursor.last_sequence > s.sequence: raise BridgeValidationError(BridgeErrorCode.CURSOR_STALE, audit_reason="future_cursor")
        if s.events and window.after_sequence < s.events[0].sequence - 1:
            raise BridgeValidationError(BridgeErrorCode.REPLAY_GAP, audit_reason="retention_gap")
        result = tuple(e for e in (s.events or ()) if e.sequence > window.after_sequence)[:window.limit]
        if not result: raise BridgeValidationError(BridgeErrorCode.NO_NEW_EVENTS, audit_reason="no_new_events")
        return result

    def replay(self, observer: ObserverIdentity, window: ReplayWindow, cursor: BridgeCursor | None = None) -> StreamResult:
        if not isinstance(window, ReplayWindow): raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="malformed_window")
        if isinstance(window.limit, bool) or not isinstance(window.limit, int) or not 1 <= window.limit <= MAX_REPLAY_BATCH:
            raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="invalid_replay_limit")
        with self._lock:
            self._ensure_connected(observer)
            s = self._state(observer, window.association_ref); snapshot = self.snapshot(observer, s.ref.association_ref)
            events = self._replay(s, window, cursor)
            return StreamResult(snapshot, "boundary-" + str(s.sequence), self._cursor(s, events[-1].sequence), events)

    def heartbeat(self, observer: ObserverIdentity, association: str | AssociationRef) -> HeartbeatResult:
        with self._lock:
            self._ensure_connected(observer)
            s = self._state(observer, association)
            if s.revoked: raise BridgeValidationError(BridgeErrorCode.ASSOCIATION_STALE, audit_reason="revoked")
            now = self._now(); s.heartbeat_at = now; s.heartbeat_sequence += 1
            event = self._append(s, "session.heartbeat", {"heartbeat_sequence": s.heartbeat_sequence, "observed_at": now.isoformat().replace("+00:00", "Z"), "ttl_ms": int(self.heartbeat_ttl.total_seconds() * 1000)})
            return HeartbeatResult(self.snapshot(observer, association), event)

    def revoke(self, observer: ObserverIdentity, association: str | AssociationRef) -> BridgeEvent | None:
        with self._lock:
            self._ensure_connected(observer)
            ref = association.association_ref if isinstance(association, AssociationRef) else association
            s = self._associations.get(ref) if isinstance(ref, str) else None
            if s is None: raise BridgeValidationError(BridgeErrorCode.ASSOCIATION_REQUIRED, audit_reason="unknown_association")
            if (s.binding.observer_ref != observer.observer_ref
                    or s.binding.owner_ref != observer.owner_ref
                    or s.binding.profile_ref != observer.profile_ref):
                raise BridgeValidationError(BridgeErrorCode.FOREIGN_OWNER, audit_reason="observer_binding_mismatch")
            if not s.revoked:
                s.revoked, s.status = True, "detached"
                return self._append(s, "session.detached", {"reason_code": "user_requested", "metadata_version": s.metadata_version})
            return None

    def expire_stale(self) -> int:
        """Expire associations without inventing continuity after a missed heartbeat."""
        with self._lock:
            now = self._now(); changed = 0
            for s in self._associations.values():
                last_seen = s.heartbeat_at or s.associated_at
                if not s.revoked and last_seen is not None and now - last_seen >= self.heartbeat_ttl:
                    s.revoked, s.status = True, "ended"; self._append(s, "session.ended", {"terminal_state": "disconnected", "reason_code": "timeout", "metadata_version": s.metadata_version}); changed += 1
            return changed

    def reset(self) -> None:
        """Explicit restart simulation: all tickets/associations become unknowable."""
        with self._lock:
            self._reset_generation += 1; self._tickets.clear(); self._associations.clear(); self._connected.clear()
            for observer_ref in tuple(self._generations):
                self._generations[observer_ref] += 1

    def events(self, observer: ObserverIdentity, association: str, *, limit: int | None = None) -> Iterator[BridgeEvent]:
        with self._lock:
            self._ensure_connected(observer)
            requested_limit = MAX_REPLAY_BATCH if limit is None else limit
            if (isinstance(requested_limit, bool) or not isinstance(requested_limit, int)
                    or not 1 <= requested_limit <= MAX_REPLAY_BATCH):
                raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="invalid_replay_limit")
            state = self._associations.get(self._association_ref(association))
            if state is None: return iter(())
            if (state.binding.observer_ref != observer.observer_ref
                    or state.binding.owner_ref != observer.owner_ref
                    or state.binding.profile_ref != observer.profile_ref):
                raise BridgeValidationError(BridgeErrorCode.FOREIGN_OWNER, audit_reason="observer_binding_mismatch")
            events = state.events or []
            if len(events) > requested_limit:
                raise BridgeValidationError(BridgeErrorCode.INVALID_EVENT, audit_reason="malformed_event_batch")
            # The retained source is already bounded; copy only the requested
            # bounded view and never tuple(materialize) the complete source.
            return iter(events[:requested_limit])
