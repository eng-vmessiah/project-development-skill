"""Pure local/injected contract for the first B15a read-only TUI RPC.

This module defines the boundary only. It does not resolve sessions, inspect
Hermes state, authenticate transports, or perform any external effect.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .gateway_bridge_contracts import (
    MAX_ENVELOPE_BYTES,
    OwnershipMode,
    SessionSnapshot,
    canonical_json,
)

TUI_SNAPSHOT_METHOD = "pd-fleet.session.snapshot"
TUI_SCHEMA_VERSION = "pd-fleet-tui-session:v1"
_OBSERVE_CAPABILITY = "observe_session_metadata"
MAX_CAPABILITIES = 16
MAX_CAPABILITY_BYTES = 64
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SENSITIVE = re.compile(
    r"(?:prompt|history|message|tool|provider|credential|secret|token|password|terminal|path|url|uri|authorization|cookie|api.?key)",
    re.IGNORECASE,
)


class TuiContractError(ValueError):
    """Stable bounded error for the local TUI contract boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code[:128])


def _ref(value: Any) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value) or _SENSITIVE.search(value):
        raise TuiContractError("INVALID_REQUEST")
    return value


@dataclass(frozen=True)
class TuiSnapshotRequest:
    session_id: str
    schema_version: str = TUI_SCHEMA_VERSION

    @property
    def method(self) -> str:
        return TUI_SNAPSHOT_METHOD

    def __post_init__(self) -> None:
        _ref(self.session_id)
        if self.schema_version != TUI_SCHEMA_VERSION:
            raise TuiContractError("UNSUPPORTED_SCHEMA")

    @classmethod
    def from_dict(cls, value: Any) -> "TuiSnapshotRequest":
        if not isinstance(value, Mapping):
            raise TuiContractError("INVALID_REQUEST")
        allowed = {"session_id", "schema_version"}
        if set(value) - allowed or set(value) != allowed:
            raise TuiContractError("INVALID_REQUEST")
        return cls(value["session_id"], value["schema_version"])


@dataclass(frozen=True)
class TuiHostBinding:
    """Host-resolved identity/capability facts; never client-supplied."""

    session_ref: str
    authenticated: bool
    capabilities: frozenset[str]
    ownership_mode: OwnershipMode = OwnershipMode.USER_OWNED_SESSION

    def __post_init__(self) -> None:
        _ref(self.session_ref)
        if type(self.authenticated) is not bool:
            raise TuiContractError("INVALID_BINDING")
        if not isinstance(self.capabilities, frozenset) or len(self.capabilities) > MAX_CAPABILITIES or any(
            type(value) is not str
            or not value
            or len(value.encode("utf-8")) > MAX_CAPABILITY_BYTES
            or _SENSITIVE.search(value)
            for value in self.capabilities
        ):
            raise TuiContractError("INVALID_BINDING")
        try:
            mode = OwnershipMode(self.ownership_mode)
        except (TypeError, ValueError):
            raise TuiContractError("INVALID_BINDING") from None
        if mode is not OwnershipMode.USER_OWNED_SESSION:
            raise TuiContractError("CAPABILITY_DENIED")
        object.__setattr__(self, "ownership_mode", mode)


def build_snapshot_response(
    request: TuiSnapshotRequest,
    binding: TuiHostBinding,
    snapshot: SessionSnapshot,
) -> dict[str, Any]:
    """Build a closed, redacted response after host-side authorization."""
    if not isinstance(request, TuiSnapshotRequest) or not isinstance(binding, TuiHostBinding):
        raise TuiContractError("INVALID_REQUEST")
    if not isinstance(snapshot, SessionSnapshot):
        raise TuiContractError("MALFORMED_HOST_RESULT")
    if not binding.authenticated or _OBSERVE_CAPABILITY not in binding.capabilities:
        raise TuiContractError("CAPABILITY_DENIED")
    if request.session_id != binding.session_ref or snapshot.session_ref != binding.session_ref:
        raise TuiContractError("SESSION_BINDING_MISMATCH")
    if snapshot.ownership_mode is not OwnershipMode.USER_OWNED_SESSION:
        raise TuiContractError("CAPABILITY_DENIED")

    session = snapshot.to_dict()
    allowed = {
        "session_ref",
        "association_ref",
        "ownership_mode",
        "status",
        "stream_epoch",
        "sequence",
        "metadata_version",
    }
    if set(session) != allowed:
        raise TuiContractError("MALFORMED_HOST_RESULT")
    response = {
        "method": TUI_SNAPSHOT_METHOD,
        "schema_version": TUI_SCHEMA_VERSION,
        "redacted": True,
        "capability": _OBSERVE_CAPABILITY,
        "session": session,
    }
    if len(canonical_json(response).encode("utf-8")) > MAX_ENVELOPE_BYTES:
        raise TuiContractError("PAYLOAD_TOO_LARGE")
    return response


__all__ = [
    "TUI_SCHEMA_VERSION",
    "TUI_SNAPSHOT_METHOD",
    "TuiContractError",
    "TuiHostBinding",
    "TuiSnapshotRequest",
    "build_snapshot_response",
]
