"""Read-only Fleet observation bridge with an independent SQLite journal.

The bridge intentionally depends only on the injected Gateway protocol.  It is not a
Hermes adapter: no Hermes state database, transport, provider, process, or credential
surface is imported here.  Cryptographic issuer verification is deliberately not
implemented in this local fake/injected protocol; the real Hermes adapter remains
NOT_READY and this bridge does not invent JWT or signature validation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import inspect
from dataclasses import replace
from itertools import islice
from threading import RLock
from typing import Any, Mapping

from .gateway_bridge_contracts import (
    SCHEMA_VERSION, MAX_REPLAY_BATCH, ActivationTicketRef, AssociationRef, BridgeCursor,
    BridgeErrorCode, BridgeEvent, BridgeValidationError, ObserverIdentity,
    OwnershipMode, ReplayWindow, SessionSnapshot, canonical_json, _ref, _string,
)

_MAX_STORE_BYTES = 64 * 1024
_STORE_USER_VERSION = 1
_TERMINAL_STATUSES = frozenset({"detached", "ended"})
def _fail(code: BridgeErrorCode, reason: str | None = None) -> None:
    raise BridgeValidationError(code, audit_reason=reason)


def _json(value: Any) -> str:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    text = canonical_json(value)
    if len(text.encode("utf-8")) > _MAX_STORE_BYTES:
        _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE, "store_record_too_large")
    return text


class _Store:
    """Small, namespaced, transactional journal owned exclusively by this bridge."""
    def __init__(self, path: str | None, *, max_events: int = 1024, max_pending_events: int = 1024):
        if (isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 1
                or isinstance(max_pending_events, bool) or not isinstance(max_pending_events, int)
                or max_pending_events < 1):
            raise ValueError("invalid journal bounds")
        self.max_events = max_events
        self.max_pending_events = max_pending_events
        self.lock = RLock()
        try:
            self.db = sqlite3.connect(path or ":memory:", check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, _STORE_USER_VERSION):
                _fail(BridgeErrorCode.INVALID_REQUEST, "incompatible_store_schema")
            existing = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fleet_bridge_%'")}
            required = {"fleet_bridge_associations", "fleet_bridge_events", "fleet_bridge_outbox", "fleet_bridge_cursors"}
            if existing and existing != required:
                _fail(BridgeErrorCode.INVALID_REQUEST, "incompatible_store_schema")
            existing_complete = existing == required
            if existing_complete:
                self._validate_schema()
            self.db.executescript("""
        CREATE TABLE IF NOT EXISTS fleet_bridge_associations (
          association_ref TEXT PRIMARY KEY, record_json TEXT NOT NULL,
          status TEXT NOT NULL, stream_epoch TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fleet_bridge_events (
          association_ref TEXT NOT NULL, stream_epoch TEXT NOT NULL,
          sequence INTEGER NOT NULL, event_id TEXT NOT NULL, record_json TEXT NOT NULL,
          PRIMARY KEY (association_ref, stream_epoch, sequence, event_id),
          UNIQUE (association_ref, stream_epoch, sequence),
          CHECK (sequence >= 0),
          FOREIGN KEY (association_ref) REFERENCES fleet_bridge_associations(association_ref)
        );
        CREATE TABLE IF NOT EXISTS fleet_bridge_outbox (
          event_id TEXT PRIMARY KEY, association_ref TEXT NOT NULL,
          record_json TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0,
          CHECK (acknowledged IN (0, 1)),
          FOREIGN KEY (association_ref) REFERENCES fleet_bridge_associations(association_ref)
        );
        CREATE TABLE IF NOT EXISTS fleet_bridge_cursors (
          association_ref TEXT NOT NULL, subscriber_ref TEXT NOT NULL,
          record_json TEXT NOT NULL, last_sequence INTEGER NOT NULL,
          PRIMARY KEY (association_ref, subscriber_ref)
        );
        """)
            expected_tables = {
                "fleet_bridge_associations": {"association_ref", "record_json", "status", "stream_epoch", "updated_at"},
                "fleet_bridge_events": {"association_ref", "stream_epoch", "sequence", "event_id", "record_json"},
                "fleet_bridge_outbox": {"event_id", "association_ref", "record_json", "acknowledged"},
                "fleet_bridge_cursors": {"association_ref", "subscriber_ref", "record_json", "last_sequence"},
            }
            for table, columns in expected_tables.items():
                actual = {row[1] for row in self.db.execute(f"PRAGMA table_info({table})")}
                if not columns <= actual:
                    _fail(BridgeErrorCode.INVALID_REQUEST, "incompatible_store_schema")
            self.db.execute(f"PRAGMA user_version={_STORE_USER_VERSION}")
            self.db.commit()
        except BridgeValidationError:
            raise
        except sqlite3.Error:
            raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="store_unavailable") from None

    def _validate_schema(self) -> None:
        expected = {
            "fleet_bridge_associations": [("association_ref", "TEXT", 0, None, 1), ("record_json", "TEXT", 1, None, 0), ("status", "TEXT", 1, None, 0), ("stream_epoch", "TEXT", 1, None, 0), ("updated_at", "TEXT", 1, None, 0)],
            "fleet_bridge_events": [("association_ref", "TEXT", 1, None, 1), ("stream_epoch", "TEXT", 1, None, 2), ("sequence", "INTEGER", 1, None, 3), ("event_id", "TEXT", 1, None, 4), ("record_json", "TEXT", 1, None, 0)],
            "fleet_bridge_outbox": [("event_id", "TEXT", 0, None, 1), ("association_ref", "TEXT", 1, None, 0), ("record_json", "TEXT", 1, None, 0), ("acknowledged", "INTEGER", 1, "0", 0)],
            "fleet_bridge_cursors": [("association_ref", "TEXT", 1, None, 1), ("subscriber_ref", "TEXT", 1, None, 2), ("record_json", "TEXT", 1, None, 0), ("last_sequence", "INTEGER", 1, None, 0)],
        }
        for table, columns in expected.items():
            rows = [tuple(row) for row in self.db.execute(f"PRAGMA table_info({table})")]
            if rows != [(i, *spec) for i, spec in enumerate(columns)]:
                _fail(BridgeErrorCode.INVALID_REQUEST, "incompatible_store_schema")
        fks = {table: {(row[3], row[2], row[4]) for row in self.db.execute(f"PRAGMA foreign_key_list({table})")} for table in ("fleet_bridge_events", "fleet_bridge_outbox")}
        wanted = {"fleet_bridge_events": {("association_ref", "fleet_bridge_associations", "association_ref")}, "fleet_bridge_outbox": {("association_ref", "fleet_bridge_associations", "association_ref")}}
        if fks != wanted:
            _fail(BridgeErrorCode.INVALID_REQUEST, "incompatible_store_schema")
        sql = {row[0]: row[4] or "" for row in self.db.execute("SELECT name,type,tbl_name,rootpage,sql FROM sqlite_master WHERE type='table' AND name LIKE 'fleet_bridge_%'")}
        if "CHECK (sequence >= 0)" not in sql.get("fleet_bridge_events", "") or "CHECK (acknowledged IN (0, 1))" not in sql.get("fleet_bridge_outbox", ""):
            _fail(BridgeErrorCode.INVALID_REQUEST, "incompatible_store_schema")
        unique = [tuple(r[2] for r in self.db.execute(f"PRAGMA index_info('{row[1]}')")) for row in self.db.execute("PRAGMA index_list('fleet_bridge_events')") if row[2]]
        if ("association_ref", "stream_epoch", "sequence") not in unique:
            _fail(BridgeErrorCode.INVALID_REQUEST, "incompatible_store_schema")

    def close(self) -> None:
        with self.lock:
            try:
                self.db.close()
            except sqlite3.Error:
                raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="store_unavailable") from None

    def _association(self, snapshot: SessionSnapshot) -> None:
        if not snapshot.stream_epoch:
            _fail(BridgeErrorCode.RESYNC_REQUIRED, "missing_epoch")
        record = _json(snapshot)
        now = datetime.now(timezone.utc).isoformat()
        row = self.db.execute("SELECT record_json FROM fleet_bridge_associations WHERE association_ref=?", (snapshot.association_ref,)).fetchone()
        if row is not None:
            try: old = SessionSnapshot.from_dict(json.loads(row[0]))
            except (ValueError, TypeError, json.JSONDecodeError): _fail(BridgeErrorCode.INVALID_EVENT, "corrupt_association")
            if (not old.stream_epoch or old.session_ref != snapshot.session_ref
                    or old.ownership_mode != snapshot.ownership_mode
                    or old.stream_epoch != snapshot.stream_epoch):
                _fail(BridgeErrorCode.INVALID_EVENT, "association_conflict")
            # The local journal is monotonic: a stale response (especially one
            # arriving after revoke) must not regress terminal state.
            effective = snapshot
            if old.sequence > snapshot.sequence or (
                old.status in _TERMINAL_STATUSES and snapshot.status not in _TERMINAL_STATUSES
            ):
                effective = old
                record = _json(effective)
            self.db.execute("UPDATE fleet_bridge_associations SET record_json=?,status=?,stream_epoch=?,updated_at=? WHERE association_ref=?", (record, effective.status, effective.stream_epoch, now, snapshot.association_ref))
        else:
            if snapshot.ownership_mode is OwnershipMode.FLEET_OWNED_TASK: _fail(BridgeErrorCode.CAPABILITY_DENIED)
            if not snapshot.stream_epoch: _fail(BridgeErrorCode.RESYNC_REQUIRED, "missing_epoch")
            self.db.execute("INSERT INTO fleet_bridge_associations VALUES (?,?,?,?,?)", (snapshot.association_ref, record, snapshot.status, snapshot.stream_epoch, now))

    def _outbox_event(self, event: BridgeEvent, encoded: str) -> None:
        row = self.db.execute("SELECT association_ref, record_json FROM fleet_bridge_outbox WHERE event_id=?", (event.event_id,)).fetchone()
        if row is not None:
            if row[0] != event.association_ref or row[1] != encoded:
                _fail(BridgeErrorCode.INVALID_PROVENANCE, "event_id_conflict")
            return
        self.db.execute("INSERT INTO fleet_bridge_outbox(event_id,association_ref,record_json) VALUES(?,?,?)", (event.event_id, event.association_ref, encoded))

    def ingest(self, snapshot: SessionSnapshot, events: tuple[BridgeEvent, ...], cursor: BridgeCursor | None) -> None:
        if not isinstance(events, (tuple, list)) or len(events) > MAX_REPLAY_BATCH:
            _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event_batch")
        with self.lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                self._association(snapshot)
                for event in events:
                    encoded = _json(event)
                    sequence_identity = self.db.execute(
                        "SELECT stream_epoch, event_id, record_json FROM fleet_bridge_events WHERE association_ref=? AND sequence=?",
                        (event.association_ref, event.sequence),
                    ).fetchone()
                    if sequence_identity is not None and (
                        sequence_identity[0] != event.stream_epoch
                        or sequence_identity[1] != event.event_id
                        or sequence_identity[2] != encoded
                    ):
                        _fail(BridgeErrorCode.INVALID_PROVENANCE, "sequence_identity_conflict")
                    row = self.db.execute("SELECT event_id, record_json FROM fleet_bridge_events WHERE association_ref=? AND stream_epoch=? AND sequence=?", (event.association_ref, event.stream_epoch, event.sequence)).fetchone()
                    if row is not None:
                        if row[0] != event.event_id or row[1] != encoded: _fail(BridgeErrorCode.INVALID_PROVENANCE, "sequence_identity_conflict")
                        continue
                    by_id = self.db.execute("SELECT association_ref, stream_epoch, sequence, record_json FROM fleet_bridge_events WHERE event_id=?", (event.event_id,)).fetchone()
                    if by_id is not None and (tuple(by_id[:3]) != (event.association_ref, event.stream_epoch, event.sequence) or by_id[3] != encoded): _fail(BridgeErrorCode.INVALID_PROVENANCE, "event_id_conflict")
                    if by_id is None:
                        event_count = self.db.execute("SELECT COUNT(*) FROM fleet_bridge_events").fetchone()[0]
                        pending_count = self.db.execute("SELECT COUNT(*) FROM fleet_bridge_outbox WHERE acknowledged=0").fetchone()[0]
                        if event_count >= self.max_events:
                            _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE, "journal_event_limit")
                        if pending_count >= self.max_pending_events:
                            _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE, "journal_pending_limit")
                    self.db.execute("INSERT INTO fleet_bridge_events VALUES (?,?,?,?,?)", (event.association_ref, event.stream_epoch, event.sequence, event.event_id, encoded))
                    self._outbox_event(event, encoded)
                if cursor is not None:
                    encoded_cursor = _json(cursor)
                    prior = self.db.execute("SELECT last_sequence,record_json FROM fleet_bridge_cursors WHERE association_ref=? AND subscriber_ref=?", (cursor.association_ref, cursor.subscriber_ref)).fetchone()
                    if prior is not None and prior[0] >= cursor.last_sequence:
                        # Equal-sequence redelivery is idempotent; retain the
                        # first cursor metadata rather than weakening it.
                        encoded_cursor = prior[1]
                        cursor = BridgeCursor.from_dict(json.loads(encoded_cursor))
                    self.db.execute("INSERT INTO fleet_bridge_cursors VALUES(?,?,?,?) ON CONFLICT(association_ref,subscriber_ref) DO UPDATE SET record_json=excluded.record_json,last_sequence=excluded.last_sequence", (cursor.association_ref, cursor.subscriber_ref, encoded_cursor, cursor.last_sequence))
                self.db.commit()
            except sqlite3.Error:
                self.db.rollback()
                raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="store_unavailable") from None
            except Exception:
                self.db.rollback()
                raise

    def ingest_events(self, events: tuple[BridgeEvent, ...]) -> None:
        """Persist revoke events when the gateway no longer exposes a snapshot."""
        if not events:
            _fail(BridgeErrorCode.ASSOCIATION_STALE, "detach_event_unavailable")
        if not isinstance(events, (tuple, list)) or len(events) > MAX_REPLAY_BATCH:
            _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event_batch")
        if any(not isinstance(event, BridgeEvent) for event in events):
            _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event")
        with self.lock:
            try:
                # Validate all terminal provenance before opening a write
                # transaction.  The revoke response must extend the durable
                expected_by_association: dict[str, int] = {}
                encoded_events: dict[str, str] = {}
                for event in events:
                    encoded = _json(event)
                    # Exact terminal redelivery is a no-op before gap checks.
                    by_id = self.db.execute("SELECT association_ref, stream_epoch, sequence, record_json FROM fleet_bridge_events WHERE event_id=?", (event.event_id,)).fetchone()
                    if by_id is not None:
                        if tuple(by_id[:3]) != (event.association_ref, event.stream_epoch, event.sequence) or by_id[3] != encoded:
                            _fail(BridgeErrorCode.INVALID_PROVENANCE, "event_id_conflict")
                        encoded_events[event.event_id] = encoded
                        continue
                    row = self.db.execute("SELECT record_json FROM fleet_bridge_associations WHERE association_ref=?", (event.association_ref,)).fetchone()
                    if row is None:
                        _fail(BridgeErrorCode.ASSOCIATION_REQUIRED, "unknown_association")
                    try:
                        old = SessionSnapshot.from_dict(json.loads(row[0]))
                    except (ValueError, TypeError, json.JSONDecodeError):
                        _fail(BridgeErrorCode.INVALID_EVENT, "corrupt_association")
                    if (old.association_ref != event.association_ref
                            or old.session_ref != event.session_ref
                            or not old.stream_epoch
                            or old.stream_epoch != event.stream_epoch):
                        _fail(BridgeErrorCode.INVALID_PROVENANCE, "terminal_provenance_mismatch")
                    if event.event_type != "session.detached":
                        _fail(BridgeErrorCode.INVALID_EVENT, "invalid_terminal_event")
                    if event.association_ref not in expected_by_association:
                        event_row = self.db.execute("SELECT MAX(sequence) FROM fleet_bridge_events WHERE association_ref=? AND stream_epoch=?", (event.association_ref, old.stream_epoch)).fetchone()
                        cursor_row = self.db.execute("SELECT MAX(last_sequence) FROM fleet_bridge_cursors WHERE association_ref=?", (event.association_ref,)).fetchone()
                        expected_by_association[event.association_ref] = max(old.sequence, event_row[0] or 0, cursor_row[0] or 0) + 1
                    terminal_snapshot = replace(old, status="detached", sequence=event.sequence)
                    FleetGatewayBridge._validate_stream(terminal_snapshot, (event,), expected_by_association[event.association_ref] - 1, None)
                    encoded = _json(event)
                    encoded_events[event.event_id] = encoded
                    sequence_identity = self.db.execute("SELECT stream_epoch, event_id, record_json FROM fleet_bridge_events WHERE association_ref=? AND sequence=?", (event.association_ref, event.sequence)).fetchone()
                    if sequence_identity is not None and (sequence_identity[0] != event.stream_epoch or sequence_identity[1] != event.event_id or sequence_identity[2] != encoded):
                        _fail(BridgeErrorCode.INVALID_PROVENANCE, "sequence_identity_conflict")
                    by_id = self.db.execute("SELECT association_ref, stream_epoch, sequence, record_json FROM fleet_bridge_events WHERE event_id=?", (event.event_id,)).fetchone()
                    if by_id is not None and (tuple(by_id[:3]) != (event.association_ref, event.stream_epoch, event.sequence) or by_id[3] != encoded):
                        _fail(BridgeErrorCode.INVALID_PROVENANCE, "event_id_conflict")
                self.db.execute("BEGIN IMMEDIATE")
                for event in events:
                    row = self.db.execute("SELECT record_json FROM fleet_bridge_associations WHERE association_ref=?", (event.association_ref,)).fetchone()
                    if row is None:
                        _fail(BridgeErrorCode.ASSOCIATION_REQUIRED, "unknown_association")
                    old = SessionSnapshot.from_dict(json.loads(row[0]))
                    if not old.stream_epoch or old.stream_epoch != event.stream_epoch:
                        _fail(BridgeErrorCode.RESYNC_REQUIRED, "epoch_conflict")
                    encoded = encoded_events[event.event_id]
                    existing = self.db.execute("SELECT event_id, record_json FROM fleet_bridge_events WHERE association_ref=? AND stream_epoch=? AND sequence=?", (event.association_ref, event.stream_epoch, event.sequence)).fetchone()
                    if existing is None:
                        event_count = self.db.execute("SELECT COUNT(*) FROM fleet_bridge_events").fetchone()[0]
                        pending_count = self.db.execute("SELECT COUNT(*) FROM fleet_bridge_outbox WHERE acknowledged=0").fetchone()[0]
                        if event_count >= self.max_events:
                            _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE, "journal_event_limit")
                        if pending_count >= self.max_pending_events:
                            _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE, "journal_pending_limit")
                        self.db.execute("INSERT INTO fleet_bridge_events VALUES (?,?,?,?,?)", (event.association_ref, event.stream_epoch, event.sequence, event.event_id, encoded))
                        self._outbox_event(event, encoded)
                    elif existing[0] != event.event_id or existing[1] != encoded:
                        _fail(BridgeErrorCode.INVALID_PROVENANCE, "sequence_identity_conflict")
                    updated = SessionSnapshot(old.session_ref, old.association_ref, old.ownership_mode, "detached", old.stream_epoch, max(old.sequence, event.sequence), old.metadata_version)
                    self.db.execute("UPDATE fleet_bridge_associations SET record_json=?,status=?,updated_at=? WHERE association_ref=?", (_json(updated), updated.status, datetime.now(timezone.utc).isoformat(), event.association_ref))
                self.db.commit()
            except BridgeValidationError:
                self.db.rollback(); raise
            except sqlite3.Error:
                self.db.rollback(); raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="store_unavailable") from None

    def cursor(self, association_ref: str, subscriber_ref: str) -> BridgeCursor | None:
        with self.lock:
            try:
                row = self.db.execute("SELECT record_json FROM fleet_bridge_cursors WHERE association_ref=? AND subscriber_ref=?", (association_ref, subscriber_ref)).fetchone()
            except sqlite3.Error:
                raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="store_unavailable") from None
            if not row: return None
            try: return BridgeCursor.from_dict(json.loads(row[0]))
            except (ValueError, TypeError, json.JSONDecodeError): _fail(BridgeErrorCode.CURSOR_STALE, "corrupt_cursor")

    def events(self, association_ref: str) -> tuple[BridgeEvent, ...]:
        with self.lock:
            try:
                rows = self.db.execute("SELECT record_json FROM fleet_bridge_events WHERE association_ref=? ORDER BY sequence", (association_ref,)).fetchall()
            except sqlite3.Error:
                raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="store_unavailable") from None
            result = []
            for row in rows:
                try: result.append(BridgeEvent.from_dict(json.loads(row[0])))
                except (ValueError, TypeError, json.JSONDecodeError): _fail(BridgeErrorCode.INVALID_EVENT, "corrupt_event")
            return tuple(result)

    def ack(self, event_id: str) -> None:
        with self.lock:
            try:
                row = self.db.execute("SELECT record_json FROM fleet_bridge_outbox WHERE event_id=?", (event_id,)).fetchone()
            except sqlite3.Error:
                raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="store_unavailable") from None
            if not row: _fail(BridgeErrorCode.INVALID_EVENT, "unknown_outbox_event")
            try: BridgeEvent.from_dict(json.loads(row[0]))
            except (ValueError, TypeError, json.JSONDecodeError): _fail(BridgeErrorCode.INVALID_EVENT, "corrupt_outbox")
            try:
                self.db.execute("UPDATE fleet_bridge_outbox SET acknowledged=1 WHERE event_id=?", (event_id,))
                self.db.commit()
            except sqlite3.Error:
                try: self.db.rollback()
                except sqlite3.Error: pass
                raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="store_unavailable") from None

    def pending(self) -> tuple[BridgeEvent, ...]:
        with self.lock:
            try:
                rows = self.db.execute("SELECT record_json FROM fleet_bridge_outbox WHERE acknowledged=0 ORDER BY rowid").fetchall()
            except sqlite3.Error:
                raise BridgeValidationError(BridgeErrorCode.INVALID_REQUEST, audit_reason="store_unavailable") from None
            result = []
            for row in rows:
                try: result.append(BridgeEvent.from_dict(json.loads(row[0])))
                except (ValueError, TypeError, json.JSONDecodeError): _fail(BridgeErrorCode.INVALID_EVENT, "corrupt_outbox")
            return tuple(result)


class FleetGatewayBridge:
    """Read-only observer facade over an injected GatewayClient/connection."""
    def __init__(self, gateway_client: Any, observer: ObserverIdentity, *, store_path: str | None = None, in_memory: bool = False, store: Any | None = None, journal_event_limit: int = 1024, journal_pending_limit: int = 1024):
        if not isinstance(observer, ObserverIdentity): _fail(BridgeErrorCode.INVALID_REQUEST, "malformed_observer")
        if store_path and in_memory: raise ValueError("choose store_path or in_memory")
        self.gateway = gateway_client; self.observer = observer
        self._store = store or _Store(None if in_memory or store_path is None else store_path, max_events=journal_event_limit, max_pending_events=journal_pending_limit)
        self._connection = None; self._closed = False; self._lock = RLock()

    def connect(self) -> "FleetGatewayBridge":
        with self._lock:
            if self._closed: _fail(BridgeErrorCode.ASSOCIATION_STALE, "closed")
            self._connection = self.gateway.connect(self.observer)
            return self

    @property
    def connection(self):
        if self._connection is None or self._closed: _fail(BridgeErrorCode.ASSOCIATION_REQUIRED, "not_connected")
        return self._connection

    def _stored_snapshot(self, association: str | AssociationRef) -> SessionSnapshot | None:
        ref = association.association_ref if isinstance(association, AssociationRef) else association
        row = self._store.db.execute("SELECT record_json FROM fleet_bridge_associations WHERE association_ref=?", (ref,)).fetchone()
        if row is None:
            return None
        try:
            return SessionSnapshot.from_dict(json.loads(row[0]))
        except (ValueError, TypeError, json.JSONDecodeError):
            _fail(BridgeErrorCode.INVALID_EVENT, "corrupt_association")

    def _validate_binding(self, requested: str | AssociationRef, snapshot: SessionSnapshot, events: tuple[BridgeEvent, ...] = ()) -> None:
        expected = requested if isinstance(requested, AssociationRef) else self._stored_snapshot(requested)
        if expected is None or snapshot.association_ref != expected.association_ref or snapshot.session_ref != expected.session_ref or snapshot.ownership_mode != expected.ownership_mode:
            _fail(BridgeErrorCode.INVALID_PROVENANCE, "requested_binding_mismatch")
        for event in events:
            if (event.association_ref != snapshot.association_ref or event.session_ref != snapshot.session_ref
                    or event.ownership_mode != snapshot.ownership_mode):
                _fail(BridgeErrorCode.INVALID_PROVENANCE, "requested_binding_mismatch")

    def _validate_cursor_binding(
        self, cursor: BridgeCursor | None, association_ref: str, stream_epoch: str | None = None,
    ) -> None:
        if cursor is None:
            return
        if cursor.association_ref != association_ref:
            _fail(BridgeErrorCode.INVALID_PROVENANCE, "cursor_association_mismatch")
        if stream_epoch is not None and cursor.stream_epoch != stream_epoch:
            _fail(BridgeErrorCode.INVALID_PROVENANCE, "cursor_epoch_mismatch")
        if cursor.subscriber_ref != self.observer.observer_ref:
            _fail(BridgeErrorCode.INVALID_PROVENANCE, "cursor_subscriber_mismatch")
        try:
            expires = datetime.fromisoformat(cursor.expires_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if expires.astimezone(timezone.utc) <= now:
                _fail(BridgeErrorCode.RESYNC_REQUIRED, "cursor_expired")
        except BridgeValidationError:
            raise
        except (AttributeError, TypeError, ValueError, OverflowError):
            _fail(BridgeErrorCode.INVALID_REQUEST, "cursor_expired")

    def attach(self, activation_ref: str | ActivationTicketRef, binding: Mapping[str, Any], *, operation_key: str | None = None) -> AssociationRef:
        """Consume one activation using a deliberately closed binding boundary.

        The injected connection is not trusted to filter keyword arguments or to
        provide useful exception text.  Validate and copy the complete binding
        before making either upstream call, and expose only fixed, bounded errors.
        """
        allowed = frozenset({
            "owner_ref", "profile_ref", "workspace_ref", "session_ref",
            "association_ref", "purpose", "ownership_mode",
        })
        required = allowed - {"ownership_mode"}
        if not isinstance(binding, Mapping):
            _fail(BridgeErrorCode.INVALID_REQUEST, "malformed_binding")
        try:
            values = dict(binding)
        except Exception:
            _fail(BridgeErrorCode.INVALID_REQUEST, "malformed_binding")
        if any(not isinstance(key, str) or key not in allowed for key in values):
            _fail(BridgeErrorCode.INVALID_REQUEST, "unknown_binding_field")
        if not required <= values.keys():
            _fail(BridgeErrorCode.INVALID_REQUEST, "malformed_binding")

        # Validate the activation before deriving any operation identifier.  In
        # particular, never call str() on an untrusted activation object.
        if isinstance(activation_ref, ActivationTicketRef):
            activation_value = activation_ref.activation_ref
        elif isinstance(activation_ref, str):
            activation_value = activation_ref
        else:
            _fail(BridgeErrorCode.INVALID_REQUEST, "malformed_activation_ref")
        _ref(activation_value)

        validated: dict[str, Any] = {}
        for name in required - {"purpose"}:
            value = values[name]
            _ref(value)
            validated[name] = value
        purpose = values["purpose"]
        _string(purpose)
        if purpose != "pd_observation":
            _fail(BridgeErrorCode.CAPABILITY_DENIED, "unsupported_attach_purpose")
        validated["purpose"] = purpose
        mode = values.get("ownership_mode", OwnershipMode.USER_OWNED_SESSION)
        if not isinstance(mode, (str, OwnershipMode)):
            _fail(BridgeErrorCode.INVALID_REQUEST, "malformed_ownership_mode")
        if mode != OwnershipMode.USER_OWNED_SESSION and mode != OwnershipMode.USER_OWNED_SESSION.value:
            _fail(BridgeErrorCode.CAPABILITY_DENIED, "fleet_owned_task")
        validated["ownership_mode"] = OwnershipMode.USER_OWNED_SESSION

        # A caller may choose a bounded idempotency key for compatibility, but
        # it can never contain arbitrary transport/data-bearing text.
        if operation_key is None:
            bounded_operation_key = "fleet-attach-" + activation_value
        else:
            _ref(operation_key)
            bounded_operation_key = operation_key
        validated["operation_key"] = bounded_operation_key

        try:
            assoc = self.connection.consume_activation(activation_ref, **validated)
        except BridgeValidationError:
            raise
        except Exception:
            _fail(BridgeErrorCode.INVALID_REQUEST, "upstream_attach_failed")
        if not isinstance(assoc, AssociationRef) or assoc.ownership_mode is OwnershipMode.FLEET_OWNED_TASK:
            _fail(BridgeErrorCode.CAPABILITY_DENIED)
        requested_association = validated["association_ref"]
        requested_session = validated["session_ref"]
        if requested_association != assoc.association_ref or requested_session != assoc.session_ref:
            _fail(BridgeErrorCode.INVALID_PROVENANCE, "requested_binding_mismatch")
        try:
            snap = self.connection.snapshot(assoc)
        except BridgeValidationError:
            raise
        except Exception:
            _fail(BridgeErrorCode.INVALID_REQUEST, "upstream_attach_failed")
        self._validate_binding(assoc, snap)
        self._store.ingest(snap, (), None)
        return assoc

    def snapshot(self, association: str | AssociationRef) -> SessionSnapshot:
        try:
            snap = self.connection.snapshot(association)
        except (AttributeError, TypeError):
            _fail(BridgeErrorCode.INVALID_EVENT, "malformed_snapshot")
        self._validate_stream(snap, (), 0, None)
        self._validate_binding(association, snap)
        self._store.ingest(snap, (), None)
        return snap

    def subscribe(self, association: str | AssociationRef, cursor: BridgeCursor | None = None, *, limit: int | None = None):
        if cursor is not None and not isinstance(cursor, BridgeCursor):
            _fail(BridgeErrorCode.RESYNC_REQUIRED, "malformed_cursor")
        requested_ref = association.association_ref if isinstance(association, AssociationRef) else association
        requested_snapshot = self._stored_snapshot(requested_ref)
        if cursor is not None and (
            requested_snapshot is None or not requested_snapshot.stream_epoch
        ):
            _fail(BridgeErrorCode.INVALID_PROVENANCE, "cursor_epoch_unavailable")
        self._validate_cursor_binding(
            cursor, requested_ref, requested_snapshot.stream_epoch if requested_snapshot is not None else None,
        )
        requested_limit = MAX_REPLAY_BATCH if limit is None else limit
        if (isinstance(requested_limit, bool) or not isinstance(requested_limit, int)
                or not 1 <= requested_limit <= MAX_REPLAY_BATCH):
            _fail(BridgeErrorCode.INVALID_REQUEST, "invalid_limit")
        try:
            signature = inspect.signature(self.connection.subscribe)
            supports_limit = "limit" in signature.parameters or any(
                p.kind is inspect.Parameter.VAR_KEYWORD
                for p in signature.parameters.values()
            )
        except (TypeError, ValueError):
            supports_limit = False
        if not supports_limit:
            _fail(BridgeErrorCode.INVALID_REQUEST, "unbounded_source")
        # Always transmit the bound; never rely on an upstream implicit default.
        try:
            result = self.connection.subscribe(association, cursor, limit=requested_limit)
            snapshot, events, result_cursor = self._stream_parts(result)
            expected = cursor.last_sequence if cursor is not None else 0
            self._validate_stream(snapshot, events, expected, result_cursor)
            self._validate_binding(association, snapshot, events)
            self._validate_cursor_binding(
                result_cursor, snapshot.association_ref, snapshot.stream_epoch,
            )
        except (AttributeError, TypeError):
            _fail(BridgeErrorCode.INVALID_EVENT, "malformed_upstream_result")
        self._store.ingest(snapshot, events, result_cursor)
        return result

    def replay(self, window: ReplayWindow, cursor: BridgeCursor | None = None):
        self._validate_window(window)
        if cursor is not None and not isinstance(cursor, BridgeCursor):
            _fail(BridgeErrorCode.RESYNC_REQUIRED, "malformed_cursor")
        self._validate_cursor_binding(cursor, window.association_ref, window.stream_epoch)
        try:
            result = self.connection.replay(window, cursor)
            snapshot, events, result_cursor = self._stream_parts(result)
            expected = cursor.last_sequence if cursor is not None else window.after_sequence
            self._validate_stream(snapshot, events, expected, result_cursor)
            self._validate_binding(window.association_ref, snapshot, events)
            self._validate_cursor_binding(
                result_cursor, snapshot.association_ref, snapshot.stream_epoch,
            )
        except (AttributeError, TypeError):
            _fail(BridgeErrorCode.INVALID_EVENT, "malformed_upstream_result")
        self._store.ingest(snapshot, events, result_cursor)
        return result

    def heartbeat(self, association: str | AssociationRef):
        result: Any = None
        snapshot: Any = None
        event: Any = None
        try:
            result = self.connection.heartbeat(association)
            snapshot = getattr(result, "snapshot")
            event = getattr(result, "event")
        except (AttributeError, TypeError, ValueError):
            _fail(BridgeErrorCode.INVALID_EVENT, "malformed_heartbeat_result")
        if not isinstance(snapshot, SessionSnapshot):
            _fail(BridgeErrorCode.RESYNC_REQUIRED, "malformed_snapshot")
        if not isinstance(event, BridgeEvent):
            _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event")
        self._validate_stream(snapshot, (event,), max(0, snapshot.sequence - 1), None)
        self._validate_binding(association, snapshot, (event,))
        self._store.ingest(snapshot, (event,), None)
        return result

    def reconcile(self, association: str | AssociationRef):
        snap = self.snapshot(association)
        return self.subscribe(association, self._store.cursor(snap.association_ref, self.observer.observer_ref))

    def detach(self, association: str | AssociationRef):
        result = self.connection.revoke(association)
        # Revoke can invalidate snapshot access immediately. Prefer its
        # authenticated terminal event, then use the bounded connection event
        # path; never snapshot a revoked association as a substitute.
        detached = (result,) if isinstance(result, BridgeEvent) and result.event_type == "session.detached" else ()
        event_path = getattr(self.connection, "events", None)
        if not detached and event_path is not None:
            source: Any = None
            try:
                # Request the cap explicitly where supported.  Compatibility
                # fallbacks remain bounded locally by islice below.
                try:
                    source = event_path(association, limit=MAX_REPLAY_BATCH)
                except TypeError:
                    source = event_path(association)
            except (TypeError, AttributeError):
                # Compatibility with pre-Wave-3 injected connections.
                try:
                    source = event_path(self.observer, association.association_ref if isinstance(association, AssociationRef) else association)
                except (TypeError, AttributeError):
                    _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event_source")
            try:
                events = tuple(islice(source, MAX_REPLAY_BATCH + 1))
            except Exception:
                _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event_source")
            if len(events) > MAX_REPLAY_BATCH:
                _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event_batch")
            if any(not isinstance(event, BridgeEvent) for event in events):
                _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event")
            detached = tuple(event for event in events if event.event_type == "session.detached")
        if not detached:
            raise BridgeValidationError(BridgeErrorCode.ASSOCIATION_STALE, audit_reason="detach_event_unavailable")
        self._store.ingest_events(detached)
        return result

    def status(self, association: str | AssociationRef | None = None):
        if association is None: return {"connected": self._connection is not None and not self._closed, "observer_ref": self.observer.observer_ref}
        return self.snapshot(association)

    def pending(self) -> tuple[BridgeEvent, ...]:
        return self._store.pending()

    def ack(self, event_id: str) -> None: self._store.ack(event_id)

    def close(self) -> None:
        with self._lock:
            if self._closed: return
            try:
                if self._connection is not None:
                    self._connection.disconnect()
            finally:
                self._closed = True
                self._store.close()

    @staticmethod
    def _validate_stream(snapshot: SessionSnapshot, events: tuple[BridgeEvent, ...], expected_sequence: int, cursor: BridgeCursor | None) -> None:
        try:
            if not isinstance(snapshot, SessionSnapshot): _fail(BridgeErrorCode.RESYNC_REQUIRED, "malformed_snapshot")
            if not isinstance(events, (tuple, list)) or len(events) > MAX_REPLAY_BATCH:
                _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event_batch")
            if cursor is not None and not isinstance(cursor, BridgeCursor): _fail(BridgeErrorCode.RESYNC_REQUIRED, "malformed_cursor")
            if isinstance(expected_sequence, bool) or not isinstance(expected_sequence, int) or expected_sequence < 0:
                _fail(BridgeErrorCode.RESYNC_REQUIRED, "invalid_boundary")
            if snapshot.ownership_mode is OwnershipMode.FLEET_OWNED_TASK or not snapshot.stream_epoch: _fail(BridgeErrorCode.RESYNC_REQUIRED, "invalid_snapshot")
            if snapshot.sequence < expected_sequence: _fail(BridgeErrorCode.RESYNC_REQUIRED, "invalid_boundary")
            previous = expected_sequence
            for event in events:
                if not isinstance(event, BridgeEvent): _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event")
                if event.schema_version != SCHEMA_VERSION or event.association_ref != snapshot.association_ref or event.stream_epoch != snapshot.stream_epoch or event.sequence <= 0: _fail(BridgeErrorCode.INVALID_EVENT, "stream_mismatch")
                if event.ownership_mode is OwnershipMode.FLEET_OWNED_TASK: _fail(BridgeErrorCode.CAPABILITY_DENIED)
                if event.sequence != previous + 1: _fail(BridgeErrorCode.REPLAY_GAP, "non_contiguous_stream")
                previous = event.sequence
            if events and snapshot.sequence < previous: _fail(BridgeErrorCode.RESYNC_REQUIRED, "snapshot_before_delivery")
            if cursor is not None:
                if cursor.association_ref != snapshot.association_ref or cursor.stream_epoch != snapshot.stream_epoch: _fail(BridgeErrorCode.RESYNC_REQUIRED, "cursor_boundary_mismatch")
                if events and cursor.last_sequence != events[-1].sequence: _fail(BridgeErrorCode.CURSOR_STALE, "cursor_ahead_of_delivery")
                if not events and cursor.last_sequence > expected_sequence: _fail(BridgeErrorCode.CURSOR_STALE, "cursor_ahead_of_delivery")
        except (AttributeError, TypeError, ValueError, KeyError, IndexError):
            _fail(BridgeErrorCode.INVALID_EVENT, "malformed_upstream")

    @staticmethod
    def _stream_parts(result: Any) -> tuple[SessionSnapshot, tuple[BridgeEvent, ...], BridgeCursor | None]:
        try:
            snapshot, events, cursor = result.snapshot, result.events, result.cursor
            # Consume only the bounded prefix plus one sentinel item.  Never
            # materialize an untrusted upstream iterable in full.
            bounded = tuple(islice(events, MAX_REPLAY_BATCH + 1))
            if len(bounded) > MAX_REPLAY_BATCH:
                _fail(BridgeErrorCode.INVALID_EVENT, "malformed_event_batch")
            return snapshot, bounded, cursor
        except BridgeValidationError:
            raise
        except Exception:
            _fail(BridgeErrorCode.INVALID_EVENT, "malformed_upstream_result")

    @staticmethod
    def _validate_window(window: ReplayWindow) -> None:
        try:
            if not isinstance(window, ReplayWindow): _fail(BridgeErrorCode.INVALID_REQUEST, "malformed_window")
            if isinstance(window.limit, bool) or not isinstance(window.limit, int) or not 1 <= window.limit <= MAX_REPLAY_BATCH:
                _fail(BridgeErrorCode.INVALID_REQUEST, "invalid_replay_limit")
        except (AttributeError, TypeError, ValueError):
            _fail(BridgeErrorCode.INVALID_REQUEST, "malformed_window")
