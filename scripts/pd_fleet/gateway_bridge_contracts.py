"""Pure, fail-closed contracts for the proposed Hermes Gateway Fleet Bridge.

This module deliberately contains no transport, runtime, credential, or filesystem
integration.  It validates and serializes only the bounded v1 observation surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
import unicodedata
from types import MappingProxyType
from typing import Any, ClassVar, Mapping
from datetime import datetime, timezone

SCHEMA_VERSION = "pd-fleet-gateway-bridge:v1"
MAX_STRING_BYTES = 256
MAX_REF_BYTES = 128
MAX_PAYLOAD_BYTES = 4096
MAX_PROVENANCE_REFS = 8
MAX_LIST_ITEMS = 32
MAX_SEQUENCE = 2**63 - 1
MAX_NESTING_DEPTH = 4
MAX_ENVELOPE_BYTES = 8192
MAX_REPLAY_BATCH = 100
RUNTIME_SURFACES = frozenset({"gateway", "gateway_bridge"})
STATUSES = frozenset({"observing", "active", "idle", "paused", "detached", "ended"})
REASON_CODES = frozenset({"user_requested", "timeout", "expired", "disconnected", "error", "reconciled"})
TERMINAL_STATES = frozenset({"completed", "cancelled", "failed", "disconnected"})
CHANGED_FIELDS = frozenset({"status", "metadata", "runtime_surface", "ownership_mode"})

LIFECYCLE_EVENT_TYPES = frozenset({
    "session.registered", "session.status_changed", "session.heartbeat",
    "session.metadata_changed", "session.detached", "session.ended",
})

class BridgeErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHENTICATED = "unauthenticated"
    OBSERVER_NOT_AUTHORIZED = "observer_not_authorized"
    ACTIVATION_INVALID = "activation_invalid"
    ACTIVATION_EXPIRED = "activation_expired"
    ACTIVATION_REPLAYED = "activation_replayed"
    ACTIVATION_BINDING_MISMATCH = "activation_binding_mismatch"
    FOREIGN_OWNER = "foreign_owner"
    ASSOCIATION_REQUIRED = "association_required"
    ASSOCIATION_STALE = "association_stale"
    INVALID_PROVENANCE = "invalid_provenance"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    UNSUPPORTED_EVENT = "unsupported_event"
    INVALID_EVENT = "invalid_event"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    CAPABILITY_DENIED = "capability_denied"
    CURSOR_EXPIRED = "cursor_expired"
    CURSOR_STALE = "cursor_stale"
    REPLAY_GAP = "replay_gap"
    RESYNC_REQUIRED = "resync_required"
    NO_NEW_EVENTS = "no_new_events"

class EventOrigin(str, Enum):
    GATEWAY_NATIVE = "gateway_native"
    FLEET_RECONCILED = "fleet_reconciled"

class OwnershipMode(str, Enum):
    USER_OWNED_SESSION = "user_owned_session"
    FLEET_OWNED_TASK = "fleet_owned_task"

class BridgeValidationError(ValueError):
    """Bounded validation error; external activation failures are uniform."""
    def __init__(self, code: BridgeErrorCode, *, audit_reason: str | None = None,
                 activation: bool = False):
        self.code = code
        self.external_code = BridgeErrorCode.ACTIVATION_INVALID
        self.audit_reason = audit_reason
        # Activation failures cross an intentionally opaque boundary. Keep the
        # precise reason available to trusted audit handling, but never expose
        # ticket/binding/expiry distinctions through exception text.
        activation_codes = {
            BridgeErrorCode.ACTIVATION_INVALID,
            BridgeErrorCode.ACTIVATION_EXPIRED,
            BridgeErrorCode.ACTIVATION_REPLAYED,
            BridgeErrorCode.ACTIVATION_BINDING_MISMATCH,
            BridgeErrorCode.CAPABILITY_DENIED,
        }
        external = (BridgeErrorCode.ACTIVATION_INVALID.value
                    if activation or code in activation_codes else code.value)
        super().__init__(external)

class _Contract:
    _fields: ClassVar[frozenset[str]] = frozenset()
    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)
    @classmethod
    def from_dict(cls, value: Any):
        if not isinstance(value, Mapping):
            _fail(BridgeErrorCode.INVALID_REQUEST)
        _unknown(value, cls._fields)
        try:
            return cls(**dict(value))
        except (KeyError, TypeError):
            _fail(BridgeErrorCode.INVALID_REQUEST, "missing_field")
    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())
    def fingerprint(self) -> str:
        return fingerprint(self)


def _fail(code: BridgeErrorCode, reason: str | None = None) -> None:
    raise BridgeValidationError(code, audit_reason=reason)

def _unknown(value: Mapping[Any, Any], allowed: frozenset[str]) -> None:
    if any(not isinstance(k, str) or k not in allowed for k in value):
        _fail(BridgeErrorCode.INVALID_REQUEST, "unknown_field")

def _string(value: Any, *, ref: bool = False, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        _fail(BridgeErrorCode.INVALID_EVENT)
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(BridgeErrorCode.INVALID_EVENT, "invalid_unicode")
    if len(encoded) > (MAX_REF_BYTES if ref else MAX_STRING_BYTES):
        _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE)
    if "\x00" in value or "\n" in value or "\r" in value:
        _fail(BridgeErrorCode.INVALID_EVENT)
    if ref and (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value)
                 or "/" in value or "\\" in value or "://" in value):
        _fail(BridgeErrorCode.INVALID_EVENT)
    return value

def _ref(value: Any) -> str:
    value = _string(value, ref=True)
    # References are opaque identifiers, never URI-like values.  In
    # particular, allowing a colon would turn ``urn:...`` or ``http:...``
    # into an accidental data-bearing reference.  Apply the same semantic
    # redaction rule used by mappings to reference values as well.
    if ":" in value or _SENSITIVE.search(value):
        _fail(BridgeErrorCode.INVALID_EVENT, "redaction_denied")
    return value

def _enum(value: Any, enum_type: type[Enum]) -> Enum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (ValueError, TypeError):
        _fail(BridgeErrorCode.INVALID_EVENT, "unknown_enum")

def _integer(value: Any, *, minimum: int = 0, maximum: int = MAX_SEQUENCE) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        _fail(BridgeErrorCode.INVALID_EVENT)
    return value

def _timestamp(value: Any) -> str:
    value = _string(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(BridgeErrorCode.INVALID_EVENT)
    if parsed.tzinfo is None:
        _fail(BridgeErrorCode.INVALID_EVENT)
    return value

_SENSITIVE = re.compile(r"(?:prompt|history|message|tool|provider|credential|secret|token|password|terminal|path|url|uri|authorization|cookie|api.?key)", re.I)
def _freeze(value: Any, *, depth: int = 0, provenance: bool = False) -> Any:
    """Recursively validate and detach caller-owned input graphs."""
    if depth > MAX_NESTING_DEPTH:
        _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE, "nesting_depth")
    if isinstance(value, Mapping):
        if len(value) > (MAX_PROVENANCE_REFS if provenance else MAX_LIST_ITEMS):
            _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE)
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(BridgeErrorCode.INVALID_EVENT, "invalid_key")
            _string(key)
            if _SENSITIVE.search(key) and key != "terminal_state":
                _fail(BridgeErrorCode.INVALID_EVENT, "redaction_denied")
            result[key] = _freeze(item, depth=depth + 1, provenance=provenance)
        return MappingProxyType(result)
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_LIST_ITEMS:
            _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE)
        return tuple(_freeze(item, depth=depth + 1, provenance=provenance) for item in value)
    if isinstance(value, (set, frozenset, bytes, bytearray)):
        _fail(BridgeErrorCode.INVALID_EVENT, "unsupported_input")
    if isinstance(value, str):
        _string(value, allow_empty=True)
        if (_SENSITIVE.search(value)
                or re.search(r"(?:https?://|ftp://|/[^ ]+|[A-Za-z]:\\\\)", value, re.I)):
            _fail(BridgeErrorCode.INVALID_EVENT, "redaction_denied")
        return value
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            _fail(BridgeErrorCode.INVALID_EVENT, "non_finite")
        return value
    _fail(BridgeErrorCode.INVALID_EVENT, "unsupported_input")

def _safe_mapping(value: Any, *, max_bytes: int = MAX_PAYLOAD_BYTES,
                  provenance: bool = False) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(BridgeErrorCode.INVALID_EVENT)
    frozen = _freeze(value, provenance=provenance)
    encoded = canonical_json(frozen)
    if len(encoded.encode("utf-8")) > max_bytes:
        _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE)
    return frozen

def _serialize(value: Any) -> Any:
    if isinstance(value, Enum): return value.value
    if isinstance(value, str): return unicodedata.normalize("NFC", value)
    if isinstance(value, float) and value == 0.0:
        # IEEE-754 signed zero has no semantic distinction in contract data.
        # Keep the JSON number a float while making both signs canonical.
        return 0.0
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str): _fail(BridgeErrorCode.INVALID_EVENT, "invalid_key")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in result:
                _fail(BridgeErrorCode.INVALID_EVENT, "duplicate_normalized_key")
            result[normalized_key] = _serialize(item)
        return result
    if isinstance(value, (tuple, list)): return [_serialize(v) for v in value]
    if isinstance(value, (frozenset, set, bytes, bytearray)):
        _fail(BridgeErrorCode.INVALID_EVENT, "unsupported_input")
    if hasattr(value, "__dataclass_fields__"):
        return {name: _serialize(getattr(value, name)) for name, field in value.__dataclass_fields__.items() if field._field_type.name == "_FIELD"}
    return value

def canonical_json(value: Any) -> str:
    """Strict deterministic JSON for validated wire data only.

    Contract objects are canonicalized through their public wire form.  Raw
    mappings and sequences are recursively validated first, so sensitive keys,
    sensitive/path-like values, non-finite numbers, and unsupported objects
    cannot be serialized by this public helper.
    """
    if isinstance(value, BridgeEvent):
        value = _bridge_event_wire(value)
    else:
        value = _freeze(value)
    try:
        result = json.dumps(_serialize(value), ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
        result.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        _fail(BridgeErrorCode.INVALID_EVENT, "invalid_json")
    return result


def _canonical_event_json(value: BridgeEvent) -> str:
    """Canonicalize an event without routing through ``BridgeEvent.to_dict``."""
    wire = _bridge_event_wire(value)
    try:
        result = json.dumps(_serialize(wire), ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
        result.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        _fail(BridgeErrorCode.INVALID_EVENT, "invalid_json")
    return result


def fingerprint(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class ActivationTicketRef(_Contract):
    activation_ref: str
    nonce_ref: str | None = None
    _fields: ClassVar[frozenset[str]] = frozenset({"activation_ref", "nonce_ref"})
    def __post_init__(self):
        _ref(self.activation_ref)
        if self.nonce_ref is not None: _ref(self.nonce_ref)

@dataclass(frozen=True)
class AssociationRef(_Contract):
    association_ref: str
    session_ref: str
    owner_ref: str | None = None
    profile_ref: str | None = None
    workspace_ref: str | None = None
    ownership_mode: OwnershipMode = OwnershipMode.USER_OWNED_SESSION
    _fields: ClassVar[frozenset[str]] = frozenset({"association_ref", "session_ref", "owner_ref", "profile_ref", "workspace_ref", "ownership_mode"})
    def __post_init__(self):
        for value in (self.association_ref, self.session_ref, self.owner_ref, self.profile_ref, self.workspace_ref):
            if value is not None: _ref(value)
        object.__setattr__(self, "ownership_mode", _enum(self.ownership_mode, OwnershipMode))

@dataclass(frozen=True)
class ObserverIdentity(_Contract):
    observer_ref: str
    owner_ref: str | None = None
    profile_ref: str | None = None
    _fields: ClassVar[frozenset[str]] = frozenset({"observer_ref", "owner_ref", "profile_ref"})
    def __post_init__(self):
        for value in (self.observer_ref, self.owner_ref, self.profile_ref):
            if value is not None: _ref(value)

@dataclass(frozen=True)
class BridgeCursor(_Contract):
    cursor_version: str
    association_ref: str
    subscriber_ref: str
    stream_epoch: str
    last_sequence: int
    issued_at: str
    expires_at: str
    _fields: ClassVar[frozenset[str]] = frozenset({"cursor_version", "association_ref", "subscriber_ref", "stream_epoch", "last_sequence", "issued_at", "expires_at"})
    def __post_init__(self):
        if self.cursor_version != SCHEMA_VERSION: _fail(BridgeErrorCode.UNSUPPORTED_SCHEMA)
        for value in (self.association_ref, self.subscriber_ref, self.stream_epoch): _ref(value)
        _integer(self.last_sequence); _timestamp(self.issued_at); _timestamp(self.expires_at)
        issued = datetime.fromisoformat(self.issued_at.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        if issued.tzinfo is None or expires.tzinfo is None or expires.astimezone(timezone.utc) < issued.astimezone(timezone.utc):
            _fail(BridgeErrorCode.INVALID_EVENT, "invalid_cursor_interval")

@dataclass(frozen=True)
class ReplayWindow(_Contract):
    association_ref: str
    stream_epoch: str
    after_sequence: int
    limit: int = 100
    _fields: ClassVar[frozenset[str]] = frozenset({"association_ref", "stream_epoch", "after_sequence", "limit"})
    def __post_init__(self):
        _ref(self.association_ref); _ref(self.stream_epoch); _integer(self.after_sequence)
        if isinstance(self.limit, int) and not isinstance(self.limit, bool) and self.limit > MAX_REPLAY_BATCH:
            _fail(BridgeErrorCode.INVALID_REQUEST, "invalid_replay_limit")
        _integer(self.limit, minimum=1, maximum=MAX_REPLAY_BATCH)

@dataclass(frozen=True)
class SessionSnapshot(_Contract):
    session_ref: str
    association_ref: str
    ownership_mode: OwnershipMode = OwnershipMode.USER_OWNED_SESSION
    status: str = "observing"
    stream_epoch: str | None = None
    sequence: int = 0
    metadata_version: int = 0
    _fields: ClassVar[frozenset[str]] = frozenset({"session_ref", "association_ref", "ownership_mode", "status", "stream_epoch", "sequence", "metadata_version"})
    def __post_init__(self):
        _ref(self.session_ref); _ref(self.association_ref); object.__setattr__(self, "ownership_mode", _enum(self.ownership_mode, OwnershipMode))
        _string(self.status)
        if self.status not in STATUSES: _fail(BridgeErrorCode.INVALID_EVENT, "unknown_enum")
        _integer(self.sequence); _integer(self.metadata_version, maximum=2**31 - 1)
        if self.stream_epoch is not None: _ref(self.stream_epoch)

@dataclass(frozen=True)
class BridgeEvent(_Contract):
    schema_version: str
    event_id: str
    event_type: str
    occurred_at: str
    source_system: str
    event_origin: EventOrigin
    session_ref: str
    association_ref: str
    ownership_mode: OwnershipMode
    stream_epoch: str
    sequence: int
    payload: Mapping[str, Any]
    provenance: Mapping[str, Any]
    source_instance_ref: str | None = None
    _fields: ClassVar[frozenset[str]] = frozenset({"schema_version", "event_id", "event_type", "occurred_at", "source", "event_origin", "session", "stream_epoch", "sequence", "payload", "provenance"})
    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION: _fail(BridgeErrorCode.UNSUPPORTED_SCHEMA)
        _ref(self.event_id); _timestamp(self.occurred_at); _ref(self.session_ref); _ref(self.association_ref); _ref(self.stream_epoch)
        if self.source_system != "hermes-gateway": _fail(BridgeErrorCode.INVALID_PROVENANCE)
        _string(self.event_type)
        if self.event_type not in LIFECYCLE_EVENT_TYPES: _fail(BridgeErrorCode.UNSUPPORTED_EVENT)
        object.__setattr__(self, "event_origin", _enum(self.event_origin, EventOrigin)); object.__setattr__(self, "ownership_mode", _enum(self.ownership_mode, OwnershipMode))
        _integer(self.sequence)
        if self.source_instance_ref is not None: _ref(self.source_instance_ref)
        payload = _safe_mapping(self.payload)
        payload_fields = {
            "session.registered": ({"runtime_surface", "metadata_version"}, {"runtime_surface", "metadata_version"}),
            "session.status_changed": ({"status", "reason_code", "metadata_version"}, {"status", "metadata_version"}),
            "session.heartbeat": ({"heartbeat_sequence", "observed_at", "ttl_ms"}, {"heartbeat_sequence", "observed_at", "ttl_ms"}),
            "session.metadata_changed": ({"metadata_version", "changed_fields"}, {"metadata_version", "changed_fields"}),
            "session.detached": ({"reason_code", "metadata_version"}, {"reason_code", "metadata_version"}),
            "session.ended": ({"terminal_state", "reason_code", "metadata_version"}, {"terminal_state", "reason_code", "metadata_version"}),
        }[self.event_type]
        allowed, required = payload_fields
        if set(payload) - allowed or not required <= set(payload): _fail(BridgeErrorCode.INVALID_EVENT, "payload_shape")
        for key, item in payload.items():
            if key == "runtime_surface":
                if not isinstance(item, str) or item not in RUNTIME_SURFACES: _fail(BridgeErrorCode.INVALID_EVENT, "unknown_enum")
            elif key == "status":
                if not isinstance(item, str) or item not in STATUSES: _fail(BridgeErrorCode.INVALID_EVENT, "unknown_enum")
            elif key == "reason_code":
                if not isinstance(item, str) or item not in REASON_CODES: _fail(BridgeErrorCode.INVALID_EVENT, "unknown_enum")
            elif key == "terminal_state":
                if not isinstance(item, str) or item not in TERMINAL_STATES: _fail(BridgeErrorCode.INVALID_EVENT, "unknown_enum")
            elif key.endswith("_version") or key.endswith("_sequence") or key == "ttl_ms": _integer(item, maximum=2**31 - 1)
            elif key == "observed_at": _timestamp(item)
            elif key == "changed_fields":
                if not isinstance(item, (list, tuple)) or len(item) > MAX_LIST_ITEMS:
                    _fail(BridgeErrorCode.INVALID_EVENT, "unknown_enum")
                for changed_field in item:
                    if not isinstance(changed_field, str) or changed_field not in CHANGED_FIELDS:
                        _fail(BridgeErrorCode.INVALID_EVENT, "unknown_enum")
            else: _string(item)
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "provenance", _safe_mapping(self.provenance, provenance=True))
        if self.ownership_mode is OwnershipMode.FLEET_OWNED_TASK: _fail(BridgeErrorCode.CAPABILITY_DENIED)
        # Enforce the bound while constructing the immutable event, rather
        # than deferring it until a caller happens to serialize it.
        if len(_canonical_event_json(self).encode("utf-8")) > MAX_ENVELOPE_BYTES:
            _fail(BridgeErrorCode.PAYLOAD_TOO_LARGE, "envelope_too_large")
    @classmethod
    def from_dict(cls, value: Any) -> "BridgeEvent":
        if not isinstance(value, Mapping): _fail(BridgeErrorCode.INVALID_EVENT)
        _unknown(value, cls._fields)
        required = ("schema_version", "event_id", "event_type", "occurred_at", "source", "event_origin", "session", "stream_epoch", "sequence", "payload", "provenance")
        if any(key not in value for key in required): _fail(BridgeErrorCode.INVALID_EVENT, "missing_field")
        source = value["source"]; session = value["session"]
        if not isinstance(source, Mapping) or not isinstance(session, Mapping): _fail(BridgeErrorCode.INVALID_EVENT)
        _unknown(source, frozenset({"system", "instance_ref"})); _unknown(session, frozenset({"session_ref", "association_ref", "ownership_mode"}))
        if "system" not in source or "session_ref" not in session or "association_ref" not in session or "ownership_mode" not in session: _fail(BridgeErrorCode.INVALID_EVENT, "missing_field")
        return cls(value["schema_version"], value["event_id"], value["event_type"], value["occurred_at"], source["system"], value["event_origin"], session["session_ref"], session["association_ref"], session["ownership_mode"], value["stream_epoch"], value["sequence"], value["payload"], value["provenance"], source.get("instance_ref"))
    def to_dict(self) -> dict[str, Any]:
        return _bridge_event_wire(self)


def _bridge_event_wire(value: BridgeEvent) -> dict[str, Any]:
    source = {"system": value.source_system}
    if value.source_instance_ref is not None: source["instance_ref"] = value.source_instance_ref
    return {"schema_version": value.schema_version, "event_id": value.event_id, "event_type": value.event_type, "occurred_at": value.occurred_at, "source": source, "event_origin": value.event_origin.value, "session": {"session_ref": value.session_ref, "association_ref": value.association_ref, "ownership_mode": value.ownership_mode.value}, "stream_epoch": value.stream_epoch, "sequence": value.sequence, "payload": _serialize(value.payload), "provenance": _serialize(value.provenance)}
