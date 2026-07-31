"""Honest adapter for the Hermes read-only session surfaces.

This is an adapter around an *already injected* Hermes client.  It does not
construct a URL, open a socket, start a process, read Hermes state, or discover
credentials.  Hermes currently exposes explicit-session read-only operations,
but no supported Fleet observer activation/global subscription/issuer-ticket
seam; those capabilities therefore remain explicitly ``NOT_READY``.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Mapping, Protocol, cast, runtime_checkable

from .gateway_bridge_contracts import (
    MAX_REPLAY_BATCH, BridgeCursor, BridgeEvent, ReplayWindow,
    SessionSnapshot,
)

SCHEMA_VERSION = "pd-fleet-hermes-existing-readonly:v1"
NOT_READY = "NOT_READY"
NOT_READY_HERMES_SEAM = "NOT_READY_HERMES_SEAM"
MAX_ERROR_BYTES = 256
_READ_ONLY = frozenset({"session_snapshot", "session_replay", "session_heartbeat"})
_FORBIDDEN_NAMES = frozenset({
    "prompt", "tool", "provider", "cancel", "mutate", "credentials", "filesystem",
    "dispatch", "execute", "send", "write", "delete", "activate", "subscribe",
})


class HermesAdapterError(ValueError):
    """Stable, bounded adapter error; transport details never cross this seam."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        text = message or code
        super().__init__(text.encode("utf-8", "replace")[:MAX_ERROR_BYTES].decode("utf-8", "ignore"))


@runtime_checkable
class ExistingHermesReadOnlyClient(Protocol):
    """Minimal injected protocol. ``capabilities`` is an explicit declaration."""

    capabilities: Any


class HermesExistingReadOnlyAdapter:
    """Delegate only declared explicit-session read-only Hermes operations."""

    name = "hermes-existing-read-only"

    def __init__(self, client: ExistingHermesReadOnlyClient | Any):
        # None is useful for a safe capability/probe report and must not cause
        # implicit client discovery or network construction.
        self._client = client
        self._capabilities = self._declared_capabilities(client)

    @staticmethod
    def _declared_capabilities(client: Any) -> frozenset[str]:
        if client is None:
            return frozenset()
        try:
            values = getattr(client, "capabilities", ())
            if isinstance(values, Mapping):
                values = [key for key, enabled in values.items() if enabled is True]
            if isinstance(values, (str, bytes, bytearray)):
                return frozenset()
            return frozenset(value for value in values if type(value) is str)
        except Exception:
            return frozenset()

    def capability_report(self) -> dict[str, Any]:
        """Return a machine-readable report without probing or side effects."""
        existing = {
            operation: ("READY" if operation in self._capabilities else NOT_READY)
            for operation in sorted(_READ_ONLY)
        }
        fleet = {
            "fleet_observer_activation": NOT_READY,
            "global_subscription": NOT_READY,
            "opaque_activation_ticket": NOT_READY,
            "issuer_verification": NOT_READY,
            "production": NOT_READY,
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "adapter": self.name,
            "capabilities": {**existing, **fleet},
            "existing_hermes_read_only": existing,
            **fleet,
        }

    def probe(self) -> dict[str, Any]:
        """Side-effect-free readiness result; never calls the injected client."""
        missing = sorted(_READ_ONLY - self._capabilities)
        if missing or self._client is None:
            return {"status": NOT_READY, "code": NOT_READY_HERMES_SEAM,
                    "error_code": NOT_READY_HERMES_SEAM,
                    "missing": missing or ["injected_client"]}
        return {"status": NOT_READY, "code": NOT_READY_HERMES_SEAM,
                "error_code": NOT_READY_HERMES_SEAM,
                "missing": ["fleet_observer_activation", "global_subscription",
                            "opaque_activation_ticket", "issuer_verification"]}

    def _call(self, capability: str, method: str, *args: Any, **kwargs: Any) -> Any:
        if capability not in self._capabilities:
            raise HermesAdapterError(NOT_READY_HERMES_SEAM)
        if method in _FORBIDDEN_NAMES or any(word in method.lower() for word in _FORBIDDEN_NAMES):
            raise HermesAdapterError("CAPABILITY_DENIED")
        try:
            function = getattr(self._client, method)
        except Exception:
            raise HermesAdapterError(NOT_READY_HERMES_SEAM) from None
        if not callable(function):
            raise HermesAdapterError(NOT_READY_HERMES_SEAM)
        try:
            return function(*args, **kwargs)
        except Exception:
            raise HermesAdapterError("TRANSPORT_ERROR") from None

    @staticmethod
    def _session_ref(value: Any) -> str:
        """Validate a session reference before invoking injected transport."""
        if not isinstance(value, str) or not value:
            raise HermesAdapterError("INVALID_REQUEST")
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError:
            raise HermesAdapterError("INVALID_REQUEST") from None
        if len(encoded) > 128 or "/" in value or "\\" in value or "://" in value:
            raise HermesAdapterError("INVALID_REQUEST")
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise HermesAdapterError("INVALID_REQUEST")
        if not value[0].isascii() or not value[0].isalnum():
            raise HermesAdapterError("INVALID_REQUEST")
        if any(not char.isascii() or not (char.isalnum() or char in "._:-")
               for char in value[1:]) or ":" in value:
            raise HermesAdapterError("INVALID_REQUEST")
        return value

    @staticmethod
    def _snapshot(value: Any) -> SessionSnapshot:
        try:
            return cast(SessionSnapshot, value if isinstance(value, SessionSnapshot) else SessionSnapshot.from_dict(value))
        except Exception:
            raise HermesAdapterError("MALFORMED_TRANSPORT_RESULT") from None

    @staticmethod
    def _events(value: Any) -> tuple[BridgeEvent, ...]:
        if not isinstance(value, (list, tuple)):
            raise HermesAdapterError("MALFORMED_TRANSPORT_RESULT")
        if len(value) > MAX_REPLAY_BATCH:
            raise HermesAdapterError("REPLAY_BATCH_LIMIT")
        try:
            return tuple(item if isinstance(item, BridgeEvent) else BridgeEvent.from_dict(item) for item in value)
        except Exception:
            raise HermesAdapterError("MALFORMED_TRANSPORT_RESULT") from None

    def session_snapshot(self, session_ref: str) -> SessionSnapshot:
        session_ref = self._session_ref(session_ref)
        return self._snapshot(self._call("session_snapshot", "snapshot", session_ref))

    def session_replay(self, window: ReplayWindow, cursor: BridgeCursor | None = None) -> tuple[BridgeEvent, ...]:
        if not isinstance(window, ReplayWindow) or (cursor is not None and not isinstance(cursor, BridgeCursor)):
            raise HermesAdapterError("INVALID_REQUEST")
        if window.limit > MAX_REPLAY_BATCH:
            raise HermesAdapterError("REPLAY_BATCH_LIMIT")
        return self._events(self._call("session_replay", "replay", window, cursor))

    def session_heartbeat(self, session_ref: str) -> SessionSnapshot:
        session_ref = self._session_ref(session_ref)
        return self._snapshot(self._call("session_heartbeat", "heartbeat", session_ref))

    # Deliberately explicit aliases for callers that use the contract names.
    snapshot = session_snapshot
    replay = session_replay
    heartbeat = session_heartbeat

    def __getattr__(self, name: str) -> Any:
        # Do not expose arbitrary client controls through the adapter.
        raise AttributeError(name)


__all__ = [
    "ExistingHermesReadOnlyClient", "HermesExistingReadOnlyAdapter", "HermesAdapterError",
    "NOT_READY", "NOT_READY_HERMES_SEAM", "SCHEMA_VERSION",
]
