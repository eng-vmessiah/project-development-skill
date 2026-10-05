"""B15b.2 — redaction validator (G-2 allowlist, `B15B-REDACTION-ALLOWLIST.md`).

Closed-schema validation for bridge events: allowlist-only fields, frozen
enums, frozen bounds. Unknown fields, unknown enums, oversized values,
malformed provenance, unsupported versions, denied categories, binary or
over-nested content all fail closed — rejected, never passed through.
Redaction precedes persistence/translation/replay/audit/log/metric/delivery.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

WIRE_SCHEMA = "pd-fleet-gateway-bridge:v1"
REF_MAX = 128
STRING_MAX = 512
PAYLOAD_MAX_BYTES = 4096
DEPTH_MAX = 8
CARDINALITY_MAX = 32
TTL_MS_MAX = 300_000

RUNTIME_SURFACES = frozenset({"cli", "gateway", "api", "tui"})
STATUSES = frozenset({"active", "idle", "stale", "ended"})
REASON_CODES = frozenset({"none", "timeout", "detached", "error", "closed"})
TERMINAL_STATES = frozenset({"ended", "error"})
CHANGED_FIELDS = frozenset({"status", "metadata_version"})
EVENT_ORIGINS = frozenset({"gateway_native", "fleet_reconciled"})
EVENT_TYPES = frozenset(
    {
        "session.registered",
        "session.status_changed",
        "session.heartbeat",
        "session.metadata_changed",
        "session.detached",
        "session.ended",
    }
)
OWNERSHIP_MODE = "user_owned_session"
SOURCE_SYSTEM = "hermes-gateway"
TRANSPORT = "gateway-event-stream"

#: Opaque refs: printable, no colon/slash/space/equals (blocks URLs, paths,
#: host:port and env-var shapes).
_REF_RE = re.compile(r"^[A-Za-z0-9._-]+$")

#: Closed envelope: exactly these paths — nothing else may appear.
ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "event_type",
        "occurred_at",
        "source.system",
        "source.instance_ref",
        "event_origin",
        "session.session_ref",
        "session.association_ref",
        "session.ownership_mode",
        "stream_epoch",
        "sequence",
        "payload",
        "provenance.transport",
        "provenance.correlation_id",
    }
)

#: Closed per-event payload schema (G-2 §2.2).
PAYLOAD_SCHEMA: dict[str, dict[str, tuple[str, object]]] = {
    "session.registered": {
        "runtime_surface": ("enum", RUNTIME_SURFACES),
        "metadata_version": ("int", None),
    },
    "session.status_changed": {
        "status": ("enum", STATUSES),
        "reason_code": ("enum", REASON_CODES),
        "metadata_version": ("int", None),
    },
    "session.heartbeat": {
        "heartbeat_sequence": ("int", None),
        "observed_at": ("ts", None),
        "ttl_ms": ("int", TTL_MS_MAX),
    },
    "session.metadata_changed": {
        "metadata_version": ("int", None),
        "changed_fields": ("list_enum", CHANGED_FIELDS),
    },
    "session.detached": {
        "reason_code": ("enum", REASON_CODES),
        "metadata_version": ("int", None),
    },
    "session.ended": {
        "terminal_state": ("enum", TERMINAL_STATES),
        "reason_code": ("enum", REASON_CODES),
        "metadata_version": ("int", None),
    },
}


@dataclass(frozen=True)
class RedactionVerdict:
    ok: bool
    reason: str | None = None


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _depth(value: object) -> int:
    if isinstance(value, Mapping):
        return 1 + max((_depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(v) for v in value), default=0)
    return 0


def _flatten(value: Mapping, prefix: str = "") -> dict[str, object]:
    flat: dict[str, object] = {}
    for key, child in value.items():
        path = f"{prefix}{key}"
        if isinstance(child, Mapping):
            flat.update(_flatten(child, prefix=f"{path}."))
        else:
            flat[path] = child
    return flat


def _valid_ts(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _valid_ref(value: object) -> bool:
    return isinstance(value, str) and len(value) <= REF_MAX and bool(_REF_RE.match(value))


def validate_event(event: object) -> RedactionVerdict:
    """Closed-schema validation; anything unexpected fails closed."""
    if not isinstance(event, Mapping):
        return RedactionVerdict(False, "malformed_envelope")
    if event.get("schema_version") != WIRE_SCHEMA:
        return RedactionVerdict(False, "unsupported_schema")
    if _depth(event) > DEPTH_MAX:
        return RedactionVerdict(False, "nested_beyond_depth")

    flat = _flatten({key: value for key, value in event.items() if key != "payload"})
    flat["payload"] = event.get("payload")
    unknown = set(flat) - ENVELOPE_FIELDS
    if unknown:
        return RedactionVerdict(False, "unknown_field")
    if set(flat) != ENVELOPE_FIELDS:
        return RedactionVerdict(False, "malformed_envelope")

    if not _valid_ref(flat["event_id"]):
        return RedactionVerdict(False, "invalid_field")
    if flat["event_type"] not in EVENT_TYPES:
        return RedactionVerdict(False, "unknown_enum")
    if not _valid_ts(flat["occurred_at"]):
        return RedactionVerdict(False, "invalid_field")
    if flat["source.system"] != SOURCE_SYSTEM:
        return RedactionVerdict(False, "malformed_provenance")
    if not _valid_ref(flat["source.instance_ref"]):
        return RedactionVerdict(False, "invalid_field")
    if flat["event_origin"] not in EVENT_ORIGINS:
        return RedactionVerdict(False, "unknown_enum")
    if not _valid_ref(flat["session.session_ref"]):
        return RedactionVerdict(False, "invalid_field")
    if not _valid_ref(flat["session.association_ref"]):
        return RedactionVerdict(False, "invalid_field")
    if flat["session.ownership_mode"] != OWNERSHIP_MODE:
        return RedactionVerdict(False, "unknown_enum")
    if not _valid_ref(flat["stream_epoch"]):
        return RedactionVerdict(False, "invalid_field")
    if not _is_int(flat["sequence"]) or flat["sequence"] < 0:
        return RedactionVerdict(False, "invalid_field")
    if flat["provenance.transport"] != TRANSPORT:
        return RedactionVerdict(False, "malformed_provenance")
    if not _valid_ref(flat["provenance.correlation_id"]):
        return RedactionVerdict(False, "invalid_field")

    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return RedactionVerdict(False, "invalid_field")
    try:
        size = len(json.dumps(payload, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return RedactionVerdict(False, "invalid_field")
    if size > PAYLOAD_MAX_BYTES:
        return RedactionVerdict(False, "oversized_payload")

    schema = PAYLOAD_SCHEMA[event["event_type"]]
    if set(payload) != set(schema):
        return RedactionVerdict(False, "unknown_field")
    for field, rule in schema.items():
        value = payload[field]
        kind = rule[0]
        if kind == "enum":
            if not isinstance(value, str) or value not in rule[1]:
                return RedactionVerdict(False, "unknown_enum")
        elif kind == "int":
            if not _is_int(value) or value < 0:
                return RedactionVerdict(False, "invalid_field")
            limit = rule[1]
            if isinstance(limit, int) and value > limit:
                return RedactionVerdict(False, "invalid_field")
        elif kind == "ts":
            if not _valid_ts(value):
                return RedactionVerdict(False, "invalid_field")
        elif kind == "list_enum":
            if not isinstance(value, list) or len(value) > CARDINALITY_MAX:
                return RedactionVerdict(False, "invalid_field")
            if any(not isinstance(item, str) or item not in rule[1] for item in value):
                return RedactionVerdict(False, "unknown_enum")
        else:  # pragma: no cover - schema is closed above
            return RedactionVerdict(False, "invalid_field")
    return RedactionVerdict(True)
