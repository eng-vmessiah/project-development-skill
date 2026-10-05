"""B15b.2 local fixtures — auth + association (G4-AUTH-LIFECYCLE §9).

Covers the required fixture list (valid/duplicate/concurrent/wrong binding/
expired/revoked/malformed/crash points/restart/no-disclosure) plus
idempotency, single-use and association state machine invariants.
Local policy only — no live Hermes issuer or Gateway API.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.gateway_auth import (
    ACTIVATION_INVALID,
    ACTIVATION_TTL_S,
    GRACE_S,
    IDLE_TTL_S,
    AssociationState,
    AssociationTransitionError,
    GatewayAuth,
    Presentation,
    SingleWriterTicketStore,
    TicketStatus,
)

NOW = 1_000_000.0
UNIFORM = {"outcome": ACTIVATION_INVALID}


def _issue(auth, **overrides):
    kwargs = {
        "observer_ref": "obs-1",
        "owner_ref": "own-1",
        "profile_ref": "prof-1",
        "workspace_ref": "ws-1",
        "session_ref": "sess-1",
        "association_ref": "assoc-1",
        "provenance_ref": "prov-1",
        "now": NOW,
    }
    kwargs.update(overrides)
    return auth.issue_ticket(**kwargs)


def _present(ticket, **overrides):
    fields = {
        "activation_ref": ticket.activation_ref,
        "observer_ref": ticket.observer_ref,
        "owner_ref": ticket.owner_ref,
        "profile_ref": ticket.profile_ref,
        "workspace_ref": ticket.workspace_ref,
        "session_ref": ticket.session_ref,
        "association_ref": ticket.association_ref,
        "purpose": ticket.purpose,
    }
    fields.update(overrides)
    return Presentation(**fields)


def _auth():
    store = SingleWriterTicketStore()
    return GatewayAuth(store), store


def test_valid_first_presentation():
    auth, store = _auth()
    ticket = _issue(auth)
    result = auth.consume(_present(ticket), now=NOW + 1)
    assert result.delivered and result.external == {"outcome": "activated"}
    assert result.result is not None
    assert result.result.ownership_mode == "user_owned_session"
    assert result.result.status == "observing"
    assert store.get_ticket(ticket.activation_ref).status == TicketStatus.CONSUMED
    assert store.get_association("assoc-1").state == AssociationState.OBSERVING


def test_duplicate_presentation():
    auth, store = _auth()
    ticket = _issue(auth)
    first = auth.consume(_present(ticket), now=NOW + 1)
    second = auth.consume(_present(ticket), now=NOW + 2)
    assert second.delivered and second.external == {"outcome": "activated"}
    assert second.result == first.result  # exact bounded idempotent retry
    assert store.audit_log() == []  # no denial recorded


def test_concurrent_duplicate_presentation():
    auth, store = _auth()
    ticket = _issue(auth)
    results = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        results.append(auth.consume(_present(ticket), now=NOW + 1))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 8
    assert all(r.delivered for r in results)
    assert all(r.result == results[0].result for r in results)  # one bounded result
    assert store.audit_log() == []  # serialized: at most one commit, no replays


def test_wrong_observer():
    auth, store = _auth()
    ticket = _issue(auth)
    result = auth.consume(_present(ticket, observer_ref="obs-2"), now=NOW + 1)
    assert not result.delivered and result.external == UNIFORM
    assert result.audit_reason == "foreign_owner"
    assert store.get_association("assoc-1") is None
    assert store.get_ticket(ticket.activation_ref).status == TicketStatus.ISSUED


@pytest.mark.parametrize("field", ["owner_ref", "profile_ref", "workspace_ref"])
def test_wrong_owner_profile_workspace(field):
    auth, store = _auth()
    ticket = _issue(auth)
    result = auth.consume(_present(ticket, **{field: "other"}), now=NOW + 1)
    assert not result.delivered and result.external == UNIFORM
    assert result.audit_reason == "activation_binding_mismatch"
    assert store.get_association("assoc-1") is None


@pytest.mark.parametrize("field", ["session_ref", "association_ref"])
def test_wrong_session_association(field):
    auth, _store = _auth()
    ticket = _issue(auth)
    result = auth.consume(_present(ticket, **{field: "other"}), now=NOW + 1)
    assert not result.delivered and result.external == UNIFORM
    assert result.audit_reason == "activation_binding_mismatch"


def test_wrong_purpose():
    auth, _store = _auth()
    ticket = _issue(auth)
    result = auth.consume(_present(ticket, purpose="other"), now=NOW + 1)
    assert not result.delivered and result.external == UNIFORM
    assert result.audit_reason == "capability_denied"


def test_expired_ticket():
    auth, store = _auth()
    ticket = _issue(auth, ttl_s=ACTIVATION_TTL_S)
    result = auth.consume(_present(ticket), now=NOW + ACTIVATION_TTL_S + 1)
    assert not result.delivered and result.external == UNIFORM
    assert result.audit_reason == "activation_expired"
    assert store.get_ticket(ticket.activation_ref).status == TicketStatus.EXPIRED


def test_revoked_ticket():
    auth, store = _auth()
    ticket = _issue(auth)
    assert store.revoke_ticket(ticket.activation_ref, now=NOW + 1)
    result = auth.consume(_present(ticket), now=NOW + 2)
    assert not result.delivered and result.external == UNIFORM
    assert result.audit_reason == ACTIVATION_INVALID
    assert store.get_association("assoc-1") is None


def test_malformed_unknown_ticket():
    auth, store = _auth()
    unknown = Presentation(
        activation_ref="act-unknown",
        observer_ref="obs-1",
        owner_ref="own-1",
        profile_ref="prof-1",
        workspace_ref="ws-1",
        session_ref="sess-1",
        association_ref="assoc-1",
        purpose="pd_observation",
    )
    result = auth.consume(unknown, now=NOW)
    assert not result.delivered and result.external == UNIFORM
    assert store.audit_log() == [("act-unknown", ACTIVATION_INVALID)]


def test_crash_before_consume_commit():
    auth, store = _auth()
    ticket = _issue(auth)  # "crash": consume never called
    assert store.get_ticket(ticket.activation_ref).status == TicketStatus.ISSUED
    restarted = GatewayAuth(store)  # durable state survives restart
    result = restarted.consume(_present(ticket), now=NOW + 1)
    assert result.delivered


def test_crash_after_consume_before_response():
    auth, store = _auth()
    ticket = _issue(auth)
    auth.consume(_present(ticket), now=NOW + 1)  # committed; response lost
    restarted = GatewayAuth(store)
    result = restarted.consume(_present(ticket), now=NOW + 2)  # idempotent retry
    assert result.delivered and result.external == {"outcome": "activated"}


def test_restart_with_uncertain_consumption():
    auth, store = _auth()
    ticket = _issue(auth)
    auth.consume(_present(ticket), now=NOW + 1)
    restarted = GatewayAuth(store)
    same = restarted.consume(_present(ticket), now=NOW + 2)
    assert same.delivered  # exact retry returns stored result
    different = restarted.consume(_present(ticket, association_ref="assoc-2"), now=NOW + 3)
    assert not different.delivered and different.external == UNIFORM  # never replay
    assert store.get_association("assoc-2") is None


def test_no_session_existence_disclosure_on_failure():
    auth, store = _auth()
    externals = []
    t1 = _issue(auth)
    externals.append(auth.consume(_present(t1, observer_ref="obs-x"), now=NOW + 1).external)
    t2 = _issue(auth, session_ref="sess-2")
    externals.append(
        auth.consume(_present(t2), now=NOW + ACTIVATION_TTL_S + 9).external
    )
    t3 = _issue(auth, association_ref="assoc-3")
    store.revoke_ticket(t3.activation_ref, now=NOW + 1)
    externals.append(auth.consume(_present(t3), now=NOW + 2).external)
    t4 = _issue(auth, association_ref="assoc-4")
    auth.consume(_present(t4), now=NOW + 1)
    externals.append(auth.consume(_present(t4, association_ref="assoc-9"), now=NOW + 2).external)
    unknown = Presentation(
        activation_ref="act-nope",
        observer_ref="obs-1",
        owner_ref="own-1",
        profile_ref="prof-1",
        workspace_ref="ws-1",
        session_ref="sess-1",
        association_ref="assoc-1",
        purpose="pd_observation",
    )
    externals.append(auth.consume(unknown, now=NOW).external)
    assert all(e == UNIFORM for e in externals)
    assert all(set(e.keys()) == {"outcome"} for e in externals)  # no extra disclosure


def test_single_use_no_second_association():
    auth, store = _auth()
    ticket = _issue(auth)
    assert auth.consume(_present(ticket), now=NOW + 1).delivered
    # a consumed ticket MUST NOT be reused to create another association
    result = auth.consume(_present(ticket, association_ref="assoc-2"), now=NOW + 2)
    assert not result.delivered and result.external == UNIFORM
    assert store.get_association("assoc-2") is None


def test_idempotency_records_bounded():
    auth, store = _auth()
    ticket = _issue(auth)
    result = auth.consume(_present(ticket), now=NOW + 1)
    key = (ticket.activation_ref, "obs-1", "assoc-1", "pd_observation")
    stored = store.get_idempotency(key)
    assert stored == result.result
    assert set(stored.__dataclass_fields__) == {"association_ref", "ownership_mode", "status"}


def test_heartbeat_prevents_reconnect():
    auth, _store = _auth()
    ticket = _issue(auth)
    auth.consume(_present(ticket), now=NOW)
    for i in range(1, 5):
        assert auth.touch("assoc-1", NOW + i * 30)
    assert auth.evaluate("assoc-1", NOW + 4 * 30 + 1) == AssociationState.OBSERVING


def test_association_lifecycle():
    auth, _store = _auth()
    ticket = _issue(auth)
    auth.consume(_present(ticket), now=NOW)
    assert auth.evaluate("assoc-1", NOW + IDLE_TTL_S + 1) == AssociationState.RECONNECTING
    assert auth.evaluate("assoc-1", NOW + IDLE_TTL_S + GRACE_S + 2) == AssociationState.STALE
    assert auth.reassociate("assoc-1") == AssociationState.PENDING_ACTIVATION


def test_association_illegal_transition_fails_closed():
    auth, store = _auth()
    ticket = _issue(auth)
    auth.consume(_present(ticket), now=NOW)
    association = store.get_association("assoc-1")
    association.transition(AssociationState.DETACHED)
    with pytest.raises(AssociationTransitionError):
        association.transition(AssociationState.OBSERVING)


def test_replay_denied_after_retention_eviction():
    # defensive branch (review LOW-4): if the idempotency record is evicted
    # (retention), the exact retry must NOT be honored — replay denied.
    auth, store = _auth()
    ticket = _issue(auth)
    auth.consume(_present(ticket), now=NOW + 1)
    key = (ticket.activation_ref, "obs-1", "assoc-1", "pd_observation")
    del store._idempotency[key]  # simulated retention eviction
    result = auth.consume(_present(ticket), now=NOW + 2)
    assert not result.delivered and result.external == UNIFORM
    assert result.audit_reason == "activation_replayed"
