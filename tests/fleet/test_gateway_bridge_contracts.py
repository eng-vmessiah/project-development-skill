from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))
from scripts.pd_fleet.gateway_bridge_contracts import (
    SCHEMA_VERSION, LIFECYCLE_EVENT_TYPES, ActivationTicketRef, AssociationRef,
    BridgeCursor, BridgeErrorCode, BridgeEvent, BridgeValidationError, EventOrigin,
    ObserverIdentity, OwnershipMode, ReplayWindow, SessionSnapshot, canonical_json,
    fingerprint,
)


def event(**overrides):
    value = {
        "schema_version": SCHEMA_VERSION, "event_id": "evt-1", "event_type": "session.registered",
        "occurred_at": "2026-07-29T12:00:00Z", "source": {"system": "hermes-gateway"},
        "event_origin": "gateway_native", "session": {"session_ref": "sess-1", "association_ref": "assoc-1", "ownership_mode": "user_owned_session"},
        "stream_epoch": "epoch-1", "sequence": 1,
        "payload": {"runtime_surface": "gateway", "metadata_version": 1},
        "provenance": {"transport": "gateway-event-stream", "correlation_id": "corr-1"},
    }
    value.update(overrides)
    return value


def test_positive_types_are_immutable_and_serializable():
    assert ActivationTicketRef("act-1", "nonce-1").to_dict() == {"activation_ref": "act-1", "nonce_ref": "nonce-1"}
    assert AssociationRef("assoc-1", "sess-1").to_dict()["ownership_mode"] == "user_owned_session"
    assert ObserverIdentity("observer-1").to_dict() == {"observer_ref": "observer-1", "owner_ref": None, "profile_ref": None}
    assert BridgeCursor(SCHEMA_VERSION, "assoc-1", "observer-1", "epoch-1", 2, "2026-07-29T12:00:00Z", "2026-07-29T13:00:00Z").to_dict()["last_sequence"] == 2
    assert ReplayWindow("assoc-1", "epoch-1", 2).to_dict()["limit"] == 100
    assert SessionSnapshot("sess-1", "assoc-1").to_dict()["status"] == "observing"
    obj = BridgeEvent.from_dict(event())
    assert obj.to_dict()["source"] == {"system": "hermes-gateway"}
    with pytest.raises(FrozenInstanceError):
        obj.sequence = 3


def test_unknown_fields_and_bad_enums_fail_closed():
    bad = event(extra=1)
    with pytest.raises(BridgeValidationError) as exc: BridgeEvent.from_dict(bad)
    assert exc.value.code is BridgeErrorCode.INVALID_REQUEST
    with pytest.raises(BridgeValidationError): BridgeEvent.from_dict(event(event_origin="future"))
    with pytest.raises(BridgeValidationError): BridgeEvent.from_dict(event(event_type="message.created"))
    with pytest.raises(BridgeValidationError): BridgeEvent.from_dict(event(payload={"status": "x", "extra": 1}))


def test_oversize_invalid_ids_and_sensitive_fields():
    with pytest.raises(BridgeValidationError) as exc: BridgeEvent.from_dict(event(event_id="x" * 129))
    assert exc.value.code is BridgeErrorCode.PAYLOAD_TOO_LARGE
    with pytest.raises(BridgeValidationError): ActivationTicketRef("../secret")
    for key in ("prompt", "history", "tool_result", "provider_response", "credentials", "terminal_frame", "path", "url", "secret"):
        with pytest.raises(BridgeValidationError): BridgeEvent.from_dict(event(payload={key: "do not persist"}))


def test_opaque_refs_and_snapshot_status_are_fail_closed():
    for ref in ("urn:secret", "http:secret", "secret-token"):
        with pytest.raises(BridgeValidationError): ActivationTicketRef(ref)
    for status in ("future", "https://status", "secret"):
        with pytest.raises(BridgeValidationError): SessionSnapshot("sess-1", "assoc-1", status=status)
        with pytest.raises(BridgeValidationError): SessionSnapshot.from_dict({"session_ref": "sess-1", "association_ref": "assoc-1", "status": status})


def test_envelope_limit_is_enforced_during_construction(monkeypatch):
    monkeypatch.setattr("scripts.pd_fleet.gateway_bridge_contracts.MAX_ENVELOPE_BYTES", 100)
    with pytest.raises(BridgeValidationError) as exc:
        BridgeEvent.from_dict(event())
    assert exc.value.code is BridgeErrorCode.PAYLOAD_TOO_LARGE


def test_canonical_serialization_and_fingerprint_are_stable():
    a = BridgeEvent.from_dict(event(provenance={"correlation_id": "corr-1", "transport": "gateway-event-stream"}))
    b = BridgeEvent.from_dict(event(provenance={"transport": "gateway-event-stream", "correlation_id": "corr-1"}))
    assert canonical_json(a) == canonical_json(b)
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) == sha256(a.canonical_json().encode("utf-8")).hexdigest()
    assert "prompt" not in a.canonical_json()


def test_public_canonical_json_validates_raw_input():
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    for value in (
        {"prompt": "do not persist"},
        {"safe": "secret-token"},
        {"safe": "https://example.test/secret"},
        {"safe": {"token": "x"}},
        {"safe": {1: "bad"}},
        {"safe": {"nested": {"too": {"deep": {"far": {"more": 1}}}}}},
        {"safe": {"items": {1, 2}}},
    ):
        with pytest.raises(BridgeValidationError): canonical_json(value)


def test_allowlist_is_exact():
    assert LIFECYCLE_EVENT_TYPES == frozenset({"session.registered", "session.status_changed", "session.heartbeat", "session.metadata_changed", "session.detached", "session.ended"})


def test_replay_window_rejects_limits_above_normative_batch_cap():
    with pytest.raises(BridgeValidationError) as exc:
        ReplayWindow("assoc-1", "epoch-1", 0, limit=101)
    assert exc.value.code is BridgeErrorCode.INVALID_REQUEST


def test_uniform_external_activation_error_and_audit_reason():
    error = BridgeValidationError(BridgeErrorCode.ACTIVATION_EXPIRED, audit_reason="expired")
    assert error.external_code is BridgeErrorCode.ACTIVATION_INVALID
    assert error.code is BridgeErrorCode.ACTIVATION_EXPIRED
    assert error.audit_reason == "expired"


def test_ast_import_boundary():
    path = Path(__file__).parents[2] / "scripts/pd_fleet/gateway_bridge_contracts.py"
    tree = ast.parse(path.read_text())
    forbidden = {"socket", "requests", "httpx", "aiohttp", "websockets", "subprocess", "providers"}
    imports = {node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)}
    imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not imports & forbidden
    assert not any(isinstance(node, ast.Attribute) and node.attr == "environ" for node in ast.walk(tree))


def test_required_fields_and_source_instance_ref_round_trip():
    value = event(source={"system": "hermes-gateway", "instance_ref": "gw-1"})
    obj = BridgeEvent.from_dict(value)
    assert obj.to_dict()["source"]["instance_ref"] == "gw-1"
    assert BridgeEvent.from_dict(obj.to_dict()).to_dict() == obj.to_dict()
    for field in ("schema_version", "event_id", "event_type", "occurred_at", "source", "event_origin", "session", "stream_epoch", "sequence", "payload", "provenance"):
        missing = event()
        del missing[field]
        with pytest.raises(BridgeValidationError): BridgeEvent.from_dict(missing)


def test_recursive_immutability_and_bounded_provenance():
    nested = {"outer": [{"value": "before"}]}
    value = event(provenance=nested)
    obj = BridgeEvent.from_dict(value)
    nested["outer"][0]["value"] = "after"
    assert obj.to_dict()["provenance"]["outer"][0]["value"] == "before"
    with pytest.raises((TypeError, BridgeValidationError)):
        obj.provenance["outer"][0]["value"] = "changed"
    with pytest.raises(BridgeValidationError):
        BridgeEvent.from_dict(event(provenance={"a": {"b": {"c": {"d": {"e": "too deep"}}}}}))


def test_payload_enums_unicode_and_unsupported_inputs_fail_closed():
    cases = (
        ("session.registered", {"runtime_surface": "future", "metadata_version": 1}),
        ("session.status_changed", {"status": "future", "metadata_version": 1}),
        ("session.status_changed", {"status": "active", "reason_code": "future", "metadata_version": 1}),
        ("session.ended", {"terminal_state": "future", "reason_code": "error", "metadata_version": 1}),
        ("session.metadata_changed", {"metadata_version": 1, "changed_fields": ["future"]}),
    )
    for event_type, payload in cases:
        with pytest.raises(BridgeValidationError): BridgeEvent.from_dict(event(event_type=event_type, payload=payload))
    with pytest.raises(BridgeValidationError): BridgeEvent.from_dict(event(event_id="\\ud800"))
    with pytest.raises(BridgeValidationError): BridgeEvent.from_dict(event(provenance={"nested": [{"token_ref": "x"}]}))
    with pytest.raises(BridgeValidationError): BridgeEvent.from_dict(event(provenance={"items": {1, 2}}))


def test_malformed_unhashable_event_values_are_validation_errors():
    for event_type in ([], {}, {"not": "a type"}):
        with pytest.raises(BridgeValidationError):
            BridgeEvent.from_dict(event(event_type=event_type))
    for changed_fields in ([{}], [[]], [{"field": "status"}]):
        with pytest.raises(BridgeValidationError):
            BridgeEvent.from_dict(event(
                event_type="session.metadata_changed",
                payload={"metadata_version": 1, "changed_fields": changed_fields},
            ))


def test_canonicalization_normalizes_unicode_and_signed_zero():
    nfc = event(provenance={"label": "caf\N{LATIN SMALL LETTER E WITH ACUTE}"})
    nfd = event(provenance={"label": "cafe\N{COMBINING ACUTE ACCENT}"})
    assert canonical_json(nfc) == canonical_json(nfd)
    assert fingerprint(BridgeEvent.from_dict(nfc)) == fingerprint(BridgeEvent.from_dict(nfd))

    negative_zero = canonical_json({"value": -0.0})
    positive_zero = canonical_json({"value": 0.0})
    assert negative_zero == positive_zero == '{"value":0.0}'


def test_total_envelope_is_canonical_and_bounded():
    obj = BridgeEvent.from_dict(event(source={"system": "hermes-gateway", "instance_ref": "gw-1"}))
    encoded = obj.canonical_json().encode("utf-8")
    assert len(encoded) <= 8192
    assert obj.canonical_json() == canonical_json(obj.to_dict())
