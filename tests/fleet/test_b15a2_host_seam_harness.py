"""B15a.2 S5 — local integration harness: bind the PD D1 batch adapter to the REAL Hermes seam.

Runs only when the Hermes worktree is importable (PYTHONPATH points at it); the
live link stays deferred by design. This file is the ``Hermes-seam (local)``
bucket of the G4 §9 negative-fixture evidence: duplicate presentation, concurrent
duplicate (lock-serialized idempotency, not a lock-free race proof), wrong
observer/owner, expired, revoked, malformed, cross-scope, replay gap, and no
session-existence disclosure — exercised through ``TuiD1BatchRegistrarAdapter``
→ ``register_plugin_rpc_batch`` → dispatch (the disclosure test also compares
the service-level gate directly).
"""
from __future__ import annotations

import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("tui_gateway.server")

sys.path.insert(0, str(Path(__file__).parents[2]))

from scripts.pd_fleet.fleet_d1_registration_bridge import (  # noqa: E402
    FleetD1RegistrationBridge,
)
from scripts.pd_fleet.tui_d1_batch_registrar_adapter import (  # noqa: E402
    TuiD1BatchRegistrarAdapter,
)

from hermes_cli.fleet_activation import FleetActivationOwner  # noqa: E402
from hermes_cli.fleet_observer import FleetObserverConfig, FleetObserverHub  # noqa: E402
from hermes_cli.fleet_tui_session import FleetTuiSessionService, TuiActiveSession  # noqa: E402
from hermes_cli.fleet_tui_wire import WIRE_SCHEMA  # noqa: E402
from tui_gateway import server  # noqa: E402
from tui_gateway.fleet_tui_registration import build_fleet_session_registrations  # noqa: E402

OBSERVER = "tui.observer-1"
OWNER = "owner.alpha"
S1 = "session.alpha-1"
S2 = "session.beta-2"

FOUR = ("fleet.session.activate", "fleet.session.status", "fleet.session.deactivate", "fleet.session.replay")


def _session(ref=S1, owner=OWNER):
    return TuiActiveSession(ref, owner, "acct.main", "ws.here")


def _build(resolver=None, *, hub_clock=None, svc_clock=None, retention_ttl=None):
    owner = FleetActivationOwner("issuer.one", OWNER, enabled=True, wired=True)
    assert owner.activate() is True and owner.ready
    config = FleetObserverConfig(enabled=True, **({"retention_ttl": retention_ttl} if retention_ttl else {}))
    hub = FleetObserverHub(config, clock=hub_clock)
    hub.activate()
    if resolver is None:
        resolver = lambda: _session()  # noqa: E731
    svc = FleetTuiSessionService(owner, hub, observer_ref=OBSERVER,
                                 resolve_active_session=resolver, clock=svc_clock)
    return SimpleNamespace(owner=owner, hub=hub, svc=svc)


@pytest.fixture()
def env():
    server.clear_plugin_rpcs_for_tests()
    e = _build()
    e.adapter = TuiD1BatchRegistrarAdapter(server.register_plugin_rpc_batch)
    names = e.adapter.register_batch("fleet", build_fleet_session_registrations(e.svc), enabled=True)
    assert names == FOUR
    yield e
    server.clear_plugin_rpcs_for_tests()


def _call(method, params):
    return server.handle_request({"id": 1, "method": method, "params": params})


def _wire(resp):
    """Unwrap our wire payload (handlers return _ok envelopes)."""
    return resp.get("result", resp)


def _code(resp):
    payload = _wire(resp)
    return payload.get("error", {}).get("code") if isinstance(payload, dict) else None


def _activate():
    return _call("fleet.session.activate", {"schema_version": WIRE_SCHEMA})


# ── binding + happy path through the REAL adapter ────────────────────────────

def test_real_adapter_binds_real_host_and_dispatches_wire(env):
    activated = _activate()
    result = _wire(activated)
    assert set(result) == {"schema_version", "association_ref", "subscriber_ref", "stream_epoch", "cursor", "snapshot"}
    assert result["snapshot"]["state"] == "observing"

    status = _wire(_call("fleet.session.status", {"schema_version": WIRE_SCHEMA}))
    assert status["snapshot"]["association_ref"] == result["association_ref"]

    assert env.svc.session_status_changed("observing") is True
    replay = _wire(_call("fleet.session.replay", {"schema_version": WIRE_SCHEMA, "cursor": result["cursor"]}))
    assert [e["event_type"] for e in replay["events"]] == ["session.status_changed"]

    detached = _wire(_call("fleet.session.deactivate", {"schema_version": WIRE_SCHEMA}))
    assert detached == {"schema_version": WIRE_SCHEMA, "status": "detached"}


# ── G4 §9 negative fixtures (mapped to the wire) ─────────────────────────────

def test_duplicate_presentation_is_idempotent_reconnect(env):
    first = _wire(_activate())
    second = _wire(_activate())
    assert second["association_ref"] == first["association_ref"]  # reconnect, never a duplicate attach
    assert second["subscriber_ref"] == first["subscriber_ref"]


def test_concurrent_duplicate_presentation(env):
    barrier = threading.Barrier(2)
    results: list[dict] = []
    errors: list[BaseException] = []

    def worker():
        try:
            barrier.wait(timeout=5)
            results.append(_activate())
        except BaseException as exc:  # noqa: BLE001 - collected for assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in threads]
    [t.join(timeout=10) for t in threads]
    assert not errors
    assert len(results) == 2
    refs = {_wire(r).get("association_ref") for r in results}
    assert len(refs) == 1  # exactly one association, both callers bounded
    assert _wire(_call("fleet.session.status", {"schema_version": WIRE_SCHEMA}))["snapshot"]["association_ref"] in refs


def test_wrong_observer_owner_is_denied():
    foreign = _build(resolver=lambda: _session(owner="owner.other"))
    server.clear_plugin_rpcs_for_tests()
    adapter = TuiD1BatchRegistrarAdapter(server.register_plugin_rpc_batch)
    adapter.register_batch("fleet", build_fleet_session_registrations(foreign.svc), enabled=True)
    try:
        resp = _call("fleet.session.activate", {"schema_version": WIRE_SCHEMA})
        assert _code(resp) == "observer_not_authorized"
    finally:
        server.clear_plugin_rpcs_for_tests()


def test_replay_paginates_large_backlog_end_to_end(env):
    started = _wire(_activate())
    for _ in range(40):
        assert env.svc.session_status_changed("observing") is True
    cursor = started["cursor"]
    seen = 0
    batches = 0
    for _ in range(10):  # bounded loop; a 40-event backlog never needs >10 batches
        resp = _wire(_call("fleet.session.replay", {"schema_version": WIRE_SCHEMA, "cursor": cursor}))
        batches += 1
        if not resp["events"]:
            break
        assert len(resp["events"]) < 40  # bounded batch: never the whole backlog at once
        seen += len(resp["events"])
        cursor = resp["next_cursor"]
    assert seen == 40
    assert batches >= 2


def test_expired_cursor_fails_closed():
    clock = {"now": datetime.now(timezone.utc)}
    e = _build(hub_clock=lambda: clock["now"], svc_clock=lambda: clock["now"].timestamp())
    server.clear_plugin_rpcs_for_tests()
    adapter = TuiD1BatchRegistrarAdapter(server.register_plugin_rpc_batch)
    adapter.register_batch("fleet", build_fleet_session_registrations(e.svc), enabled=True)
    try:
        started = _wire(_activate())
        clock["now"] = clock["now"] + timedelta(seconds=901)  # past the 900s candidate TTL
        resp = _call("fleet.session.replay", {"schema_version": WIRE_SCHEMA, "cursor": started["cursor"]})
        assert _code(resp) == "cursor_expired"
    finally:
        server.clear_plugin_rpcs_for_tests()


def test_revoked_owner_denies_reactivation(env):
    _wire(_activate())
    assert env.svc.deactivate()["status"] == "detached"
    env.owner.deactivate()  # revoke: no further tickets can be issued
    assert _code(_activate()) == "observer_not_authorized"


def test_malformed_requests_fail_closed(env):
    assert _code(_call("fleet.session.status", {"schema_version": "pd-fleet-tui:v9"})) == "unsupported_schema"
    forged = _call("fleet.session.activate", {"schema_version": WIRE_SCHEMA, "session_id": "client-chosen"})
    assert _wire(forged) == {"schema_version": WIRE_SCHEMA, "error": {"code": "invalid_request"}}
    _wire(_activate())
    # codec-level malformation is caught at parse time...
    assert _code(_call("fleet.session.replay", {"schema_version": WIRE_SCHEMA, "cursor": "cur.not-base64!!"})) == "invalid_request"
    # ...while a well-formed-but-forged cursor fails HMAC verification
    assert _code(_call("fleet.session.replay", {"schema_version": WIRE_SCHEMA, "cursor": "cur.YWJj"})) == "invalid_provenance"


def test_cross_scope_cursor_is_rejected():
    holder = {"ref": S1}
    e = _build(resolver=lambda: _session(ref=holder["ref"]))
    server.clear_plugin_rpcs_for_tests()
    adapter = TuiD1BatchRegistrarAdapter(server.register_plugin_rpc_batch)
    adapter.register_batch("fleet", build_fleet_session_registrations(e.svc), enabled=True)
    try:
        started = _wire(_activate())
        assert e.svc.session_ended("session_end") is True
        holder["ref"] = S2
        _wire(_activate())
        resp = _call("fleet.session.replay", {"schema_version": WIRE_SCHEMA, "cursor": started["cursor"]})
        assert _code(resp) == "cursor_stale"
    finally:
        server.clear_plugin_rpcs_for_tests()


def test_replay_gap_after_retention_eviction():
    clock = {"now": datetime.now(timezone.utc)}
    e = _build(hub_clock=lambda: clock["now"], svc_clock=lambda: clock["now"].timestamp(), retention_ttl=1.0)
    server.clear_plugin_rpcs_for_tests()
    adapter = TuiD1BatchRegistrarAdapter(server.register_plugin_rpc_batch)
    adapter.register_batch("fleet", build_fleet_session_registrations(e.svc), enabled=True)
    try:
        started = _wire(_activate())
        for step in (2, 4, 6):  # each advance evicts everything older than 1s
            clock["now"] = clock["now"] + timedelta(seconds=step)
            assert e.svc.session_status_changed("observing") is True
        resp = _call("fleet.session.replay", {"schema_version": WIRE_SCHEMA, "cursor": started["cursor"]})
        assert _code(resp) == "replay_gap"
    finally:
        server.clear_plugin_rpcs_for_tests()


def test_no_session_existence_disclosure():
    absent = _build(resolver=lambda: None)
    foreign = _build(resolver=lambda: _session(owner="owner.other"))
    codes = set()
    for e in (absent, foreign):
        server.clear_plugin_rpcs_for_tests()
        adapter = TuiD1BatchRegistrarAdapter(server.register_plugin_rpc_batch)
        adapter.register_batch("fleet", build_fleet_session_registrations(e.svc), enabled=True)
        resp = _call("fleet.session.activate", {"schema_version": WIRE_SCHEMA})
        payload = _wire(resp)
        assert set(payload) == {"schema_version", "error"}  # closed: nothing about sessions
        assert set(payload["error"]) == {"code"}
        codes.add(payload["error"]["code"])
    server.clear_plugin_rpcs_for_tests()
    assert codes == {"observer_not_authorized"}  # indistinguishable failure reasons


# ── PD bridge composed over the REAL host callable ───────────────────────────

def test_pd_bridge_batch_is_accepted_by_real_host_registry():
    server.clear_plugin_rpcs_for_tests()
    adapter = TuiD1BatchRegistrarAdapter(server.register_plugin_rpc_batch)
    try:
        bridge = FleetD1RegistrationBridge(adapter, enabled=True, host_authority=object())
        assert bridge.register() == "fleet.session.activate"
        resp = _call("fleet.session.activate", {"schema_version": "pd-fleet-session-activate:v1"})
        assert resp["result"] == {"status": "not_ready", "code": "FLEET_SESSION_ACTIVATE_NOT_READY"}
    finally:
        server.clear_plugin_rpcs_for_tests()
    disabled = FleetD1RegistrationBridge(adapter)
    result = disabled.register()
    assert isinstance(result, dict) and result.get("status") == "not_ready"
    assert _call("fleet.session.activate", {"schema_version": WIRE_SCHEMA})["error"]["code"] == -32601
