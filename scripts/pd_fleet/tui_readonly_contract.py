"""Pure local/injected contract for the first B15a read-only TUI RPC.

This module defines the boundary only. It does not resolve sessions, inspect
Hermes state, authenticate transports, or perform any external effect.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import re
import threading
from typing import Any, Callable, Mapping

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
MAX_BINDING_TTL = 300.0
MAX_BINDINGS = 128
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_CAPABILITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
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

    observer_ref: str
    owner_ref: str
    profile_ref: str
    workspace_ref: str
    association_ref: str
    session_ref: str
    authenticated: bool
    capabilities: frozenset[str]
    ownership_mode: OwnershipMode = OwnershipMode.USER_OWNED_SESSION

    def __post_init__(self) -> None:
        for value in (
            self.observer_ref,
            self.owner_ref,
            self.profile_ref,
            self.workspace_ref,
            self.association_ref,
            self.session_ref,
        ):
            try:
                _ref(value)
            except TuiContractError:
                raise TuiContractError("INVALID_BINDING") from None
        if type(self.authenticated) is not bool:
            raise TuiContractError("INVALID_BINDING")
        if not isinstance(self.capabilities, frozenset) or len(self.capabilities) > MAX_CAPABILITIES or any(
            type(value) is not str
            or not _CAPABILITY.fullmatch(value)
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


@dataclass(frozen=True)
class TuiBindingLease:
    binding: TuiHostBinding
    epoch: int
    issued_at: float
    expires_at: float
    status: str = "active"

    def __post_init__(self) -> None:
        try:
            issued_at = float(self.issued_at)
            expires_at = float(self.expires_at)
            valid_numbers = (
                type(self.issued_at) in (int, float)
                and type(self.expires_at) in (int, float)
                and math.isfinite(issued_at)
                and math.isfinite(expires_at)
                and issued_at >= 0
                and expires_at >= 0
            )
        except (TypeError, ValueError, OverflowError):
            valid_numbers = False
            issued_at = expires_at = -1.0
        duration = expires_at - issued_at if valid_numbers else -1.0
        if (
            not isinstance(self.binding, TuiHostBinding)
            or type(self.epoch) is not int
            or self.epoch <= 0
            or not valid_numbers
            or duration <= 0
            or duration > MAX_BINDING_TTL
            or type(self.status) is not str
            or self.status not in {"active", "expired", "revoked"}
        ):
            raise TuiContractError("INVALID_LEASE")


class TuiBindingRegistry:
    """Bounded in-memory lifecycle registry for injected host bindings."""

    def __init__(self, *, clock: Callable[[], float], max_bindings: int = MAX_BINDINGS):
        if not callable(clock) or type(max_bindings) is not int or not 0 < max_bindings <= MAX_BINDINGS:
            raise TuiContractError("INVALID_REGISTRY")
        self._clock = clock
        self._max_bindings = max_bindings
        self._lock = threading.RLock()
        self._last_now: float | None = None
        self._records: dict[str, TuiBindingLease] = {}

    @staticmethod
    def _time(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TuiContractError("INVALID_TIME")
        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError):
            raise TuiContractError("INVALID_TIME") from None
        if not math.isfinite(value) or value < 0:
            raise TuiContractError("INVALID_TIME")
        return value

    def _now(self) -> float:
        try:
            raw = self._clock()
        except Exception:
            raise TuiContractError("INVALID_CLOCK") from None
        now = self._time(raw)
        if self._last_now is not None and now < self._last_now:
            raise TuiContractError("CLOCK_ROLLBACK")
        self._last_now = now
        return now

    def issue(self, binding: TuiHostBinding, *, ttl: float) -> TuiBindingLease:
        with self._lock:
            return self._issue(binding, ttl=ttl)

    def _issue(self, binding: TuiHostBinding, *, ttl: float) -> TuiBindingLease:
        if not isinstance(binding, TuiHostBinding):
            raise TuiContractError("INVALID_BINDING")
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)):
            raise TuiContractError("INVALID_TTL")
        try:
            ttl = float(ttl)
        except (TypeError, ValueError, OverflowError):
            raise TuiContractError("INVALID_TTL") from None
        if not math.isfinite(ttl) or not 0 < ttl <= MAX_BINDING_TTL:
            raise TuiContractError("INVALID_TTL")
        if binding.session_ref not in self._records and len(self._records) >= self._max_bindings:
            raise TuiContractError("REGISTRY_FULL")
        now = self._now()
        prior = self._records.get(binding.session_ref)
        epoch = 1 if prior is None else prior.epoch + 1
        lease = TuiBindingLease(binding, epoch, now, now + ttl)
        self._records[binding.session_ref] = lease
        return lease

    def resolve(self, session_ref: str, observer_ref: str, epoch: int) -> TuiBindingLease:
        with self._lock:
            return self._resolve(session_ref, observer_ref, epoch)

    def _resolve(self, session_ref: str, observer_ref: str, epoch: int) -> TuiBindingLease:
        session_ref = _ref(session_ref)
        observer_ref = _ref(observer_ref)
        if type(epoch) is not int or epoch <= 0:
            raise TuiContractError("STALE_EPOCH")
        lease = self._records.get(session_ref)
        if lease is None:
            raise TuiContractError("BINDING_NOT_FOUND")
        if lease.epoch != epoch:
            raise TuiContractError("STALE_EPOCH")
        if lease.binding.observer_ref != observer_ref:
            raise TuiContractError("BINDING_MISMATCH")
        if lease.status == "revoked":
            raise TuiContractError("BINDING_REVOKED")
        if lease.status == "expired":
            raise TuiContractError("BINDING_EXPIRED")
        if self._now() >= lease.expires_at:
            self._records[session_ref] = replace(lease, status="expired")
            raise TuiContractError("BINDING_EXPIRED")
        return lease

    def revoke(self, session_ref: str) -> bool:
        with self._lock:
            return self._revoke(session_ref)

    def _revoke(self, session_ref: str) -> bool:
        session_ref = _ref(session_ref)
        lease = self._records.get(session_ref)
        if lease is None:
            return False
        if lease.status != "revoked":
            self._records[session_ref] = replace(lease, status="revoked")
        return True


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
    if snapshot.association_ref != binding.association_ref:
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
    "TuiBindingLease",
    "TuiBindingRegistry",
    "TuiContractError",
    "TuiHostBinding",
    "TuiSnapshotRequest",
    "build_snapshot_response",
]
