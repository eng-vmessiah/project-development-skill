"""Deterministic, fake-only G5 vertical canary and negative fixture matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

# Direct ``python scripts/pd_fleet/run_g5_fixture_matrix.py`` has no package
# context.  Put the repository root on sys.path before importing package modules.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.pd_fleet.fake_gateway import FakeGateway
from scripts.pd_fleet.fleet_gateway_bridge import FleetGatewayBridge
from scripts.pd_fleet.gateway_bridge_contracts import (
    MAX_REPLAY_BATCH, BridgeEvent, BridgeValidationError, BridgeCursor,
    ObserverIdentity, OwnershipMode, ReplayWindow, SCHEMA_VERSION, SessionSnapshot,
)

REPORT_VERSION = "pd-fleet-g5-fixture-report:v2"
FIXED_NOW = datetime(2099, 7, 29, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None: self.value = FIXED_NOW
    def __call__(self) -> datetime: return self.value
    def advance(self, **kwargs: int) -> None: self.value += timedelta(**kwargs)


def _setup(*, retention: int = 32, heartbeat_seconds: int = 30):
    clock = Clock()
    gateway = FakeGateway(clock=clock, retention=retention,
                          heartbeat_ttl=timedelta(seconds=heartbeat_seconds))
    observer = ObserverIdentity("observer-1", "owner-1", "profile-1")
    binding = {"owner_ref": "owner-1", "profile_ref": "profile-1", "workspace_ref": "workspace-1",
               "session_ref": "session-1", "association_ref": "association-1", "purpose": "pd_observation"}
    connection = gateway.connect(observer)
    ticket = connection.issue_activation(**binding)
    return clock, gateway, observer, binding, ticket


def _bridge(tmp: str, *, retention: int = 32):
    clock, gateway, observer, binding, ticket = _setup(retention=retention)
    path = str(Path(tmp) / "fleet-bridge.sqlite")
    bridge = FleetGatewayBridge(gateway, observer, store_path=path).connect()
    association = bridge.attach(ticket, binding)
    return clock, gateway, observer, binding, ticket, bridge, association, tmp


def _durable_state(bridge: FleetGatewayBridge) -> dict[str, Any]:
    """Return all durable bridge facts used by G5 invariants, not a slogan."""
    db = bridge._store.db
    tables = ("fleet_bridge_associations", "fleet_bridge_events",
              "fleet_bridge_outbox", "fleet_bridge_cursors")
    state: dict[str, Any] = {}
    for table in tables:
        try:
            rows = [list(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()]
            # updated_at is operational bookkeeping, not bridge state; exclude
            # it so a redelivery cannot look like a durable mutation.
            if table == "fleet_bridge_associations":
                for row in rows:
                    row[4] = "<volatile-updated-at>"
            state[table] = rows
        except sqlite3.Error as exc:
            state[table] = {"error": type(exc).__name__}
    encoded = json.dumps(state, sort_keys=True, default=str, separators=(",", ":"))
    state["counts"] = {table: len(value) if isinstance(value, list) else None
                        for table, value in state.items() if table in tables}
    state["digest"] = hashlib.sha256(encoded.encode()).hexdigest()
    return state


def _error(call: Callable[[], Any]) -> tuple[str, str | None, str | None]:
    try:
        call()
    except BridgeValidationError as exc:
        return exc.code.value, exc.audit_reason, None
    except (ValueError, TypeError, sqlite3.Error) as exc:
        # Bounded implementation errors are observable as failures, never as
        # expected bridge validation.  The caller compares this exact outcome.
        return type(exc).__name__.lower(), None, type(exc).__name__
    raise AssertionError("fixture unexpectedly succeeded")


def _row(scenario_id: str, expected: str, observed: str, audit: str | None,
         exception_type: str | None, initial: dict[str, Any],
         before_failure: dict[str, Any], after: dict[str, Any], invariant: str,
         *, invariant_check: Callable[[dict[str, Any], dict[str, Any]], bool] | None = None) -> dict[str, Any]:
    # The checkpoint, rather than the fixture's original state, is the baseline.
    # This is important for negative fixtures with a successful setup/prelude:
    # comparing with ``initial`` can hide a mutation made by the failing call.
    unchanged = before_failure["digest"] == after["digest"]
    invariant_verified = (invariant_check(before_failure, after)
                          if invariant_check is not None else unchanged)
    passed = expected == observed and invariant_verified and exception_type is None
    return {"scenario_id": scenario_id, "expected_error": expected,
            "observed_error": observed, "audit_reason": audit,
            "unexpected_exception_type": exception_type,
            "persisted_state_invariant": invariant, "state_initial": initial,
            "state_before_failure": before_failure,
            # Keep state_before for consumers of the v2 report; it now means
            # the exact pre-failure checkpoint (not the fixture initial state).
            "state_before": before_failure,
            "state_after": after, "invariant_verified": invariant_verified,
            "passed": passed}


def run_canary(tmp: str) -> dict[str, Any]:
    _, gateway, observer, binding, ticket, bridge, association, _ = _bridge(tmp)
    stages = ["connect", "issue_opaque_activation", "attach_user_owned_session"]
    baseline = _durable_state(bridge)
    snapshot = bridge.snapshot(association); stages.append("snapshot")
    initial = bridge.subscribe(association, limit=1); stages.append("subscribe")
    heartbeat = bridge.heartbeat(association); stages.append("heartbeat")
    first = bridge.replay(ReplayWindow(association.association_ref, snapshot.stream_epoch, 0, 1)); stages.append("replay_page_1")
    second = bridge.replay(ReplayWindow(association.association_ref, snapshot.stream_epoch, first.cursor.last_sequence, 1), first.cursor); stages.append("replay_page_2")
    durable_before_duplicate = _durable_state(bridge)
    duplicate = bridge.subscribe(association, cursor=initial.cursor, limit=1); stages.append("duplicate_idempotent")
    durable_after_duplicate = _durable_state(bridge)
    if durable_before_duplicate["digest"] != durable_after_duplicate["digest"]:
        raise AssertionError("duplicate subscribe changed durable rows")
    pending_before_ack = tuple(bridge.pending())
    if not pending_before_ack: raise AssertionError("positive canary produced no outbox event")
    ack_id = pending_before_ack[0].event_id
    bridge.ack(ack_id); stages.append("ack_outbox")
    if ack_id in {event.event_id for event in bridge.pending()}:
        raise AssertionError("ack did not remove event from pending view")
    bridge.close(); stages.append("reconnect_store_close")
    reopened = FleetGatewayBridge(gateway, observer, store_path=str(Path(tmp) / "fleet-bridge.sqlite")).connect(); stages.append("reconnect_store_open")
    reopened_state = _durable_state(reopened)
    if reopened_state["digest"] == baseline["digest"] or reopened_state["fleet_bridge_outbox"] is None:
        raise AssertionError("reopen lost durable stream state")
    if any(row[3] == ack_id and row[4] != 1 for row in reopened_state["fleet_bridge_outbox"]):
        raise AssertionError("ack state did not persist across reopen")
    duplicate_again = reopened.subscribe(association, cursor=initial.cursor, limit=1)
    if [e.event_id for e in duplicate_again.events] != [e.event_id for e in duplicate.events]:
        raise AssertionError("reconnect cursor redelivery changed event identity")
    reopened.detach(association); stages.append("detach")
    reopened.close()
    final = FleetGatewayBridge(gateway, observer, store_path=str(Path(tmp) / "fleet-bridge.sqlite")).connect(); stages.append("reopen_store")
    stored = final._store.db.execute("SELECT status FROM fleet_bridge_associations WHERE association_ref=?", (association.association_ref,)).fetchone()[0]
    final_events = final._store.events(association.association_ref)
    final_cursor = final._store.cursor(association.association_ref, observer.observer_ref)
    final.close()
    all_events = list(initial.events) + [heartbeat.event] + list(first.events) + list(second.events) + list(duplicate.events)
    expected_types = {"session.registered", "session.heartbeat", "session.detached"}
    passed = (stored == "detached" and final_events[-1].event_type == "session.detached"
              and [event.sequence for event in final_events] == list(range(1, len(final_events) + 1))
              and {event.event_type for event in final_events} == expected_types
              and final_cursor is not None and final_cursor.last_sequence == 2
              and [event.sequence for event in all_events[:2]] == [1, 2]
              and reopened_state["digest"] != baseline["digest"])
    return {"scenario_id": "positive_full_vertical", "name": "positive_full_vertical", "stages": stages,
            "event_sequences": [e.sequence for e in all_events],
            "event_types": [e.event_type for e in final_events],
            "duplicate_event_ids": [e.event_id for e in duplicate.events],
            "ack_persisted": True, "reopened_cursor_sequence": final_cursor.last_sequence if final_cursor else None,
            "observed_persisted_status": stored, "persisted_state_invariant": "durable stream, ack, cursor, and detached terminal state survive reopen",
            "passed": passed}


def run_negative(tmp: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    def case(sid: str, expected: str, fn: Callable[[Any], Any], invariant: str = "durable bridge journal unchanged", *,
             prepare: Callable[[Any], Any] | None = None,
             invariant_check: Callable[[dict[str, Any], dict[str, Any]], bool] | None = None) -> None:
        with tempfile.TemporaryDirectory(dir=tmp) as local:
            fixture = _bridge(local)
            initial = _durable_state(fixture[5])
            if prepare is not None:
                prepare(fixture)
            before_failure = _durable_state(fixture[5])
            try:
                observed, audit, exc_type = _error(lambda: fn(fixture))
            except AssertionError as exc:
                observed, audit, exc_type = "unexpected_success", None, type(exc).__name__
            after = _durable_state(fixture[5])
            rows.append(_row(sid, expected, observed, audit, exc_type, initial,
                             before_failure, after, invariant,
                             invariant_check=invariant_check))
            try: fixture[5]._store.close()
            except (BridgeValidationError, sqlite3.Error): pass

    case("activation_malformed_ticket", "activation_invalid", lambda x: x[5].attach("malformed", x[3]))
    case("activation_expired_ticket", "activation_invalid", lambda x: x[5].attach(x[4], x[3]), prepare=lambda x: x[0].advance(minutes=6))
    case("activation_replayed_ticket", "activation_invalid", lambda x: x[5].attach(x[4], x[3], operation_key="other"), prepare=lambda x: x[5].attach(x[4], x[3]))
    case("activation_wrong_purpose", "capability_denied", lambda x: x[5].attach(x[4], {**x[3], "purpose": "admin"}))
    case("activation_wrong_owner", "activation_invalid", lambda x: x[5].attach(x[4], {**x[3], "owner_ref": "other-owner"}))
    case("activation_wrong_profile", "activation_invalid", lambda x: x[5].attach(x[4], {**x[3], "profile_ref": "other-profile"}))
    case("activation_wrong_workspace", "activation_invalid", lambda x: x[5].attach(x[4], {**x[3], "workspace_ref": "other-workspace"}))
    case("activation_wrong_session", "activation_invalid", lambda x: x[5].attach(x[4], {**x[3], "session_ref": "other-session"}))
    case("activation_wrong_association", "activation_invalid", lambda x: x[5].attach(x[4], {**x[3], "association_ref": "other-association"}))
    case("fleet_owned_task", "capability_denied", lambda x: x[5].attach(x[4], {**x[3], "ownership_mode": "fleet_owned_task"}))
    case("wrong_observer", "foreign_owner", lambda x: FleetGatewayBridge(x[1], ObserverIdentity("other-observer"), in_memory=True).connect().snapshot(x[6]))
    def prepare_cursor(x: Any) -> None:
        x[5]._g5_cursor = x[5].subscribe(x[6]).cursor
    def cursor_case(x: Any, field: str) -> None:
        x[5].subscribe(x[6], replace(x[5]._g5_cursor, **{field: "forged-value"}))
    for field, label in (("subscriber_ref", "subscriber"), ("association_ref", "association"), ("stream_epoch", "epoch")):
        case("forged_cursor_" + label, "invalid_provenance", lambda x, f=field: cursor_case(x, f), "successful prelude is retained; forged cursor adds no rows", prepare=prepare_cursor)
    def prepare_expired(x: Any) -> None:
        x[5]._g5_cursor = x[5].subscribe(x[6]).cursor
        x[0].advance(minutes=6)
    case("expired_cursor", "cursor_expired", lambda x: x[5].subscribe(x[6], replace(x[5]._g5_cursor, issued_at="2099-07-29T11:59:00Z", expires_at="2099-07-29T12:00:01Z")), prepare=prepare_expired)
    def prepare_replay_gap(x: Any) -> None:
        clock, gateway, observer, binding, ticket = _setup(retention=2); small = FleetGatewayBridge(gateway, observer, in_memory=True).connect(); assoc = small.attach(ticket, binding); small.subscribe(assoc); small.heartbeat(assoc); small.heartbeat(assoc)
        x[5]._g5_small = small
        stream_epoch = small.snapshot(assoc).stream_epoch
        assert stream_epoch is not None
        x[5]._g5_gap_window = ReplayWindow(assoc.association_ref, stream_epoch, 0, 1)
    case("replay_gap", "replay_gap", lambda x: x[5]._g5_small.replay(x[5]._g5_gap_window), prepare=prepare_replay_gap)
    def replay_out_of_order(x: Any) -> Any:
        original = x[5]._connection
        class Forged:
            def subscribe(self, association: Any, cursor: Any = None, *, limit: int | None = None) -> Any:
                result = x[5]._g5_stream
                return replace(result, events=(replace(result.events[0], sequence=result.events[0].sequence + 2),))
            def __getattr__(self, name: str) -> Any: return getattr(original, name)
        x[5]._connection = Forged(); return x[5].subscribe(x[6])
    case("replay_out_of_order", "invalid_event", replay_out_of_order,
         prepare=lambda x: setattr(x[5], "_g5_stream", x[5].subscribe(x[6])))
    def prepare_duplicate(x: Any) -> None:
        x[5]._g5_event = x[5].subscribe(x[6]).events[0]
    case("duplicate_event_id", "invalid_provenance", lambda x: x[5]._store.ingest(x[5].snapshot(x[6]), (replace(x[5]._g5_event, sequence=2),), None), prepare=prepare_duplicate)
    def prepare_epoch_replay(x: Any) -> None:
        x[5]._g5_stream = x[5].subscribe(x[6])
    case("forged_cursor_epoch_replay", "invalid_provenance", lambda x: x[5].replay(ReplayWindow(x[6].association_ref, x[5]._g5_stream.snapshot.stream_epoch, 0, 1), replace(x[5]._g5_stream.cursor, stream_epoch="other-epoch")), prepare=prepare_epoch_replay)
    case("malformed_upstream_snapshot", "invalid_event", lambda x: (setattr(x[5], "_connection", type("C", (), {"snapshot": lambda *_: object(), "__getattr__": lambda self, n: getattr(x[5]._connection, n)})()), x[5].snapshot(x[6])))
    case("malformed_upstream_result", "invalid_event", lambda x: (setattr(x[5], "_connection", type("C", (), {"subscribe": lambda *_args, **_kw: object(), "__getattr__": lambda self, n: getattr(x[5]._connection, n)})()), x[5].subscribe(x[6])))
    case("malformed_upstream_event", "invalid_event", lambda x: x[5]._store.ingest(x[5].snapshot(x[6]), (object(),), None))
    def prepare_detach(x: Any) -> None:
        x[5]._g5_detach_event = x[5]._connection.revoke(x[6])
    case("detach_malformed_provenance", "association_required", lambda x: x[5]._store.ingest_events((replace(x[5]._g5_detach_event, association_ref="other-association"),)), prepare=prepare_detach)
    case("detach_wrong_provenance", "invalid_provenance", lambda x: x[5]._store.ingest_events((replace(x[5]._g5_detach_event, session_ref="other-session"),)), prepare=prepare_detach)
    for forbidden in ("prompt", "history", "credentials", "tool", "provider"):
        case("redaction_" + forbidden, "invalid_event", lambda x, f=forbidden: SessionSnapshot("session-1", "association-1", status=f))
    case("replay_bound_exceeded", "invalid_request", lambda x: x[5].subscribe(x[6], limit=MAX_REPLAY_BATCH + 1))
    def prepare_no_cursor(x: Any) -> None:
        x[5]._g5_cursor = x[5].subscribe(x[6]).cursor
    case("no_cursor_advance_on_failure", "invalid_provenance", lambda x: x[5].subscribe(x[6], replace(x[5]._g5_cursor, subscriber_ref="forged")), "successful prelude is retained; failed request does not advance cursor", prepare=prepare_no_cursor)
    case("stale_association", "association_stale", lambda x: x[5].snapshot(x[6]), prepare=lambda x: x[5]._connection.revoke(x[6]))
    case("revoke_disconnect", "association_required", lambda x: x[5].connection.snapshot(x[6]), "bridge close is durable-resource invalidation; no committed journal mutation", prepare=lambda x: x[5].close())
    case("gateway_reset", "activation_invalid", lambda x: x[5].snapshot(x[6]), prepare=lambda x: x[1].reset())
    def prepare_schema_corruption(x: Any) -> None:
        x[5].close()
        db = sqlite3.connect(x[7] + "/fleet-bridge.sqlite")
        try:
            db.execute("DROP TABLE fleet_bridge_events")
            db.commit()
        finally:
            db.close()
    case("store_schema_corruption", "invalid_request", lambda x: FleetGatewayBridge(x[1], x[2], store_path=x[7] + "/fleet-bridge.sqlite"), "external corruption is detected and changes the local journal", prepare=prepare_schema_corruption)
    case("store_ack_unknown", "invalid_event", lambda x: x[5].ack("unknown-event"))
    case("store_commit_closed", "invalid_request", lambda x: x[5].ack("unknown-event"), prepare=lambda x: x[5]._store.close())
    case("unknown_association", "association_required", lambda x: x[5].snapshot("unknown-association"))
    case("malformed_cursor_type", "resync_required", lambda x: x[5].subscribe(x[6], cursor=object()))
    case("invalid_limit_type", "invalid_request", lambda x: x[5].subscribe(x[6], limit="one"))
    case("replay_malformed_window", "invalid_request", lambda x: x[5].replay(object()))
    case("heartbeat_after_revoke", "invalid_event", lambda x: x[5].heartbeat(x[6]), prepare=lambda x: x[5]._connection.revoke(x[6]))
    def no_detach_event(x: Any) -> Any:
        original = x[5]._connection
        class NoDetach:
            def revoke(self, association: Any) -> None: return None
            def events(self, association: Any, *, limit: int | None = None): return iter(())
            def __getattr__(self, name: str) -> Any: return getattr(original, name)
        x[5]._connection = NoDetach(); return x[5].detach(x[6])
    case("detach_unknown_event_source", "association_stale", no_detach_event)
    case("activation_non_mapping", "invalid_request", lambda x: x[5].attach(x[4], object()))
    return rows


def run() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pd-fleet-g5-") as tmp:
        positive = run_canary(tmp); negative = run_negative(tmp)
    rows = [positive, *negative]; ids = [r["scenario_id"] for r in negative]
    unique = len(ids) == len(set(ids))
    return {"report": REPORT_VERSION, "FAKE_ONLY": True, "hermes_live": False,
            "network": False, "subprocess": False, "provider_access": False,
            "control_plane_access": False, "credentials_access": False,
            "hermes_state_db_access": False, "local_bridge_journal_access": True,
            "positive": positive, "negative": negative,
            "summary": {"scenario_count": len(rows), "negative_scenario_count": len(negative),
                        "distinct_negative_scenario_ids": len(set(ids)),
                        "passed": sum(bool(r["passed"]) for r in rows),
                        "failed": sum(not bool(r["passed"]) for r in rows),
                        "at_least_38_distinct_negatives": len(set(ids)) >= 38 and unique},
            "valid": len(set(ids)) >= 38 and unique and all(bool(r["passed"]) for r in rows)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--pretty", action="store_true"); args = parser.parse_args(argv)
    report = run(); print(json.dumps(report, sort_keys=True, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
    return 0 if report["valid"] else 1


if __name__ == "__main__": raise SystemExit(main())
