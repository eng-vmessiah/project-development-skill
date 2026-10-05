"""B15b.2 fixtures — redaction (G-2 allowlist; 23 named fixtures).

Per-field allowed fixtures, per-category denied fixtures (sensitive
material), structural fail-closed fixtures and the closed-envelope fixture.
Anything unexpected is rejected — never passed through.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.gateway_redaction import (
    OWNERSHIP_MODE,
    SOURCE_SYSTEM,
    TRANSPORT,
    WIRE_SCHEMA,
    validate_event,
)


def _event(event_type="session.status_changed", payload=None, **overrides):
    base = {
        "schema_version": WIRE_SCHEMA,
        "event_id": "evt-abc123",
        "event_type": event_type,
        "occurred_at": "2026-10-05T14:20:00Z",
        "source": {"system": SOURCE_SYSTEM, "instance_ref": "inst-1"},
        "event_origin": "gateway_native",
        "session": {
            "session_ref": "sess-1",
            "association_ref": "assoc-1",
            "ownership_mode": OWNERSHIP_MODE,
        },
        "stream_epoch": "epoch-1",
        "sequence": 1,
        "payload": payload
        if payload is not None
        else {"status": "active", "reason_code": "none", "metadata_version": 1},
        "provenance": {"transport": TRANSPORT, "correlation_id": "corr-1"},
    }
    base.update(overrides)
    return base


# ── per-field allowed (passa íntegro) ────────────────────────────────────────


def test_redaction_status_changed_status_allowed():
    assert validate_event(_event()).ok


def test_redaction_heartbeat_ttl_ms_allowed():
    event = _event(
        "session.heartbeat",
        payload={"heartbeat_sequence": 7, "observed_at": "2026-10-05T14:20:00Z", "ttl_ms": 300000},
    )
    assert validate_event(event).ok


def test_redaction_metadata_changed_changed_fields_allowed():
    event = _event(
        "session.metadata_changed",
        payload={"metadata_version": 2, "changed_fields": ["status", "metadata_version"]},
    )
    assert validate_event(event).ok


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("session.registered", {"runtime_surface": "cli", "metadata_version": 1}),
        ("session.status_changed", {"status": "idle", "reason_code": "timeout", "metadata_version": 3}),
        ("session.heartbeat", {"heartbeat_sequence": 1, "observed_at": "2026-10-05T14:20:00Z", "ttl_ms": 30000}),
        ("session.metadata_changed", {"metadata_version": 4, "changed_fields": []}),
        ("session.detached", {"reason_code": "detached", "metadata_version": 5}),
        ("session.ended", {"terminal_state": "ended", "reason_code": "closed", "metadata_version": 6}),
    ],
    ids=["registered", "status_changed", "heartbeat", "metadata_changed", "detached", "ended"],
)
def test_all_six_event_types_valid(event_type, payload):
    assert validate_event(_event(event_type, payload=payload)).ok


# ── per-category denied (fixtures sensíveis) ─────────────────────────────────


def test_redaction_deny_prompt():
    verdict = validate_event(_event(payload={"status": "active", "prompt": "user text"}))
    assert not verdict.ok and verdict.reason == "unknown_field"


def test_redaction_deny_history():
    verdict = validate_event(_event(payload={"status": "active", "history": ["turn"]}))
    assert not verdict.ok and verdict.reason == "unknown_field"


def test_redaction_deny_message_content():
    verdict = validate_event(_event(payload={"status": "active", "message": "hello"}))
    assert not verdict.ok and verdict.reason == "unknown_field"


def test_redaction_deny_tool_material():
    verdict = validate_event(
        _event(payload={"status": "active", "tool_name": "bash", "tool_result": "ok"})
    )
    assert not verdict.ok and verdict.reason == "unknown_field"


def test_redaction_deny_provider_response():
    verdict = validate_event(_event(payload={"status": "active", "provider_output": "..."}))
    assert not verdict.ok and verdict.reason == "unknown_field"


def test_redaction_deny_approval_payload():
    verdict = validate_event(_event(payload={"status": "active", "approval": {"cmd": "rm"}}))
    assert not verdict.ok


def test_redaction_deny_credentials():
    verdict = validate_event(_event(event_id="Bearer sk-live-abc123"))
    assert not verdict.ok and verdict.reason == "invalid_field"


def test_redaction_deny_paths():
    verdict = validate_event(_event(event_id="/home/vitor/secret.txt"))
    assert not verdict.ok and verdict.reason == "invalid_field"


def test_redaction_deny_terminal_frames():
    verdict = validate_event(_event(payload={"status": "active", "terminal": "\x1b[2Jframe"}))
    assert not verdict.ok and verdict.reason == "unknown_field"


def test_redaction_deny_env_vars():
    verdict = validate_event(_event(stream_epoch="PATH=/usr/bin:/bin"))
    assert not verdict.ok and verdict.reason == "invalid_field"


def test_redaction_deny_network_address():
    verdict = validate_event(
        _event(source={"system": SOURCE_SYSTEM, "instance_ref": "http://10.0.0.1:9119"})
    )
    assert not verdict.ok and verdict.reason == "invalid_field"


# ── estruturais (fail-closed) ────────────────────────────────────────────────


def test_redaction_unknown_field_fail_closed():
    verdict = validate_event(_event(extra_field="anything"))
    assert not verdict.ok and verdict.reason == "unknown_field"


def test_redaction_unknown_enum_fail_closed():
    verdict = validate_event(_event(payload={"status": "weird", "reason_code": "none", "metadata_version": 1}))
    assert not verdict.ok and verdict.reason == "unknown_enum"


def test_redaction_oversized_payload_rejected():
    verdict = validate_event(_event(payload={"status": "x" * 5000, "reason_code": "none", "metadata_version": 1}))
    assert not verdict.ok and verdict.reason == "oversized_payload"


def test_redaction_arbitrary_map_rejected():
    verdict = validate_event(_event(payload={"status": {"nested": 1}, "reason_code": "none", "metadata_version": 1}))
    assert not verdict.ok


def test_redaction_binary_rejected():
    verdict = validate_event(_event(event_id=b"raw-bytes"))
    assert not verdict.ok


def test_redaction_nested_beyond_depth_rejected():
    deep = current = {}
    for _ in range(12):
        current["n"] = {}
        current = current["n"]
    verdict = validate_event(_event(payload={"status": "active", "deep": deep}))
    assert not verdict.ok and verdict.reason == "nested_beyond_depth"


def test_redaction_malformed_provenance_fail_closed():
    verdict = validate_event(
        _event(provenance={"transport": "http", "correlation_id": "corr-1"})
    )
    assert not verdict.ok and verdict.reason == "malformed_provenance"


def test_redaction_unsupported_schema_fail_closed():
    verdict = validate_event(_event(schema_version="pd-fleet-gateway-bridge:v2"))
    assert not verdict.ok and verdict.reason == "unsupported_schema"


def test_redaction_envelope_closed_fields():
    # the full 15-field envelope passes one by one (closed set)
    assert validate_event(_event()).ok
    missing = _event()
    del missing["stream_epoch"]
    assert validate_event(missing).reason == "malformed_envelope"
    extra = _event()
    extra["surprise"] = 1
    assert validate_event(extra).reason == "unknown_field"
