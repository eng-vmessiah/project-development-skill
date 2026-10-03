"""Local, injected, default-off registration bridge for Fleet session RPCs.

This Fleet-side seam neither imports nor discovers Hermes, resolves host sessions,
activates a runtime, persists data, nor dispatches work. Host authority and the
one optional local bridge association are injected and deliberately opaque.
"""
from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any, Callable

FLEET_RPC_NAMESPACE = "fleet"
FLEET_SESSION_ACTIVATE_NAME = "session.activate"
FLEET_SESSION_STATUS_NAME = "session.status"
FLEET_SESSION_DEACTIVATE_NAME = "session.deactivate"
FLEET_SESSION_REPLAY_NAME = "session.replay"

FLEET_SESSION_ACTIVATE_SCHEMA_VERSION = "pd-fleet-session-activate:v1"
FLEET_SESSION_STATUS_SCHEMA_VERSION = "pd-fleet-session-status:v1"
FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION = "pd-fleet-session-deactivate:v1"
FLEET_SESSION_REPLAY_SCHEMA_VERSION = "pd-fleet-session-replay:v1"

_MAX_OPAQUE_CURSOR_LENGTH = 256
_INVALID_REQUEST_ID_ERROR_CODE = -32600
_INVALID_REQUEST_ID_ERROR_MESSAGE = "Invalid Request"


class FleetD1RegistrationError(ValueError):
    """Stable local error for an invalid injected D1 registration port."""


def _result(status: str, code: str) -> dict[str, str]:
    """Return a fresh, bounded response without reflecting request data."""
    return {"status": status, "code": code}


def _response(request_id: Any, status: str, code: str) -> dict[str, Any]:
    """Return the JSON-RPC result envelope expected from a D1 raw handler."""
    if not _is_jsonrpc_request_id(request_id):
        return _invalid_request_id_error()
    return {"jsonrpc": "2.0", "id": request_id, "result": _result(status, code)}


def _is_jsonrpc_request_id(request_id: Any) -> bool:
    """Accept only JSON-RPC scalar identifiers and a finite numeric value."""
    return (
        request_id is None
        or isinstance(request_id, str)
        or (isinstance(request_id, int) and not isinstance(request_id, bool))
        or (isinstance(request_id, float) and isfinite(request_id))
    )


def _invalid_request_id_error() -> dict[str, Any]:
    """Return a static JSON-RPC error without reflecting invalid request data."""
    return {
        "jsonrpc": "2.0",
        "id": None,
        "error": {
            "code": _INVALID_REQUEST_ID_ERROR_CODE,
            "message": _INVALID_REQUEST_ID_ERROR_MESSAGE,
        },
    }


def _not_ready(operation: str) -> dict[str, str]:
    return _result("not_ready", f"FLEET_SESSION_{operation}_NOT_READY")


def _denied(operation: str) -> dict[str, str]:
    return _result("denied", f"FLEET_SESSION_{operation}_DENIED")


class FleetD1RegistrationBridge:
    """Register approved Fleet session names through an injected, default-off port.

    Every handler has a closed request envelope. In particular, no client-provided
    session, owner, principal, or capability field is accepted as identity or
    authority. ``local_association`` is an optional *injected* bridge-only object;
    deactivate can call only its zero-argument ``detach`` method and never a host
    session API. Status and replay are read-only not-ready seams.
    """

    def __init__(
        self,
        registrar: Any,
        *,
        enabled: bool = False,
        host_authority: Any | None = None,
        local_association: Any | None = None,
    ):
        self._registrar = registrar
        self._enabled = enabled is True
        self._host_authority = host_authority
        self._local_association = local_association

    def register(self) -> str | dict[str, str]:
        """Atomically publish approved names, or remain locally not-ready when disabled.

        An enabled bridge requires an injected ``register_batch`` port.  The port
        owns atomicity: it must publish all candidates together or none of them.
        This bridge intentionally never degrades to individual ``register`` calls.
        """
        if not self._enabled:
            return _not_ready("ACTIVATE")
        register_batch = getattr(self._registrar, "register_batch", None)
        if not callable(register_batch):
            raise FleetD1RegistrationError("invalid injected registrar")

        registrations: tuple[tuple[str, Callable[[Any, Any], dict[str, Any]]], ...] = (
            (FLEET_SESSION_ACTIVATE_NAME, self.handle_session_activate),
            (FLEET_SESSION_STATUS_NAME, self.handle_session_status),
            (FLEET_SESSION_DEACTIVATE_NAME, self.handle_session_deactivate),
            (FLEET_SESSION_REPLAY_NAME, self.handle_session_replay),
        )
        expected = tuple(f"{FLEET_RPC_NAMESPACE}.{name}" for name, _handler in registrations)
        try:
            registered = register_batch(FLEET_RPC_NAMESPACE, registrations, enabled=True)
            if registered != expected:
                raise FleetD1RegistrationError("injected registrar returned invalid methods")
        except FleetD1RegistrationError:
            raise
        except Exception:
            raise FleetD1RegistrationError("injected registrar rejected registration") from None
        return expected[0]

    def handle_session_activate(self, request_id: Any, params: Any) -> dict[str, Any]:
        """Fail closed pending future host-side authority and activation semantics."""
        if not _is_jsonrpc_request_id(request_id):
            return _invalid_request_id_error()
        if not self._is_closed_request(params, FLEET_SESSION_ACTIVATE_SCHEMA_VERSION):
            return _response(request_id, "denied", "FLEET_SESSION_ACTIVATE_DENIED")
        if self._host_authority is None:
            return _response(request_id, "denied", "FLEET_SESSION_ACTIVATE_DENIED")
        return _response(request_id, "not_ready", "FLEET_SESSION_ACTIVATE_NOT_READY")

    def handle_session_status(self, request_id: Any, params: Any) -> dict[str, Any]:
        """Expose no session data until a host-authorized read-only contract exists."""
        if not _is_jsonrpc_request_id(request_id):
            return _invalid_request_id_error()
        if not self._is_closed_request(params, FLEET_SESSION_STATUS_SCHEMA_VERSION):
            return _response(request_id, "denied", "FLEET_SESSION_STATUS_DENIED")
        if self._host_authority is None:
            return _response(request_id, "denied", "FLEET_SESSION_STATUS_DENIED")
        return _response(request_id, "not_ready", "FLEET_SESSION_STATUS_NOT_READY")

    def handle_session_deactivate(self, request_id: Any, params: Any) -> dict[str, Any]:
        """Detach only an injected bridge association; never mutate a host session."""
        if not _is_jsonrpc_request_id(request_id):
            return _invalid_request_id_error()
        if not self._is_closed_request(params, FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION):
            return _response(request_id, "denied", "FLEET_SESSION_DEACTIVATE_DENIED")
        if self._host_authority is None:
            return _response(request_id, "denied", "FLEET_SESSION_DEACTIVATE_DENIED")
        detach = getattr(self._local_association, "detach", None)
        if not callable(detach):
            return _response(request_id, "not_ready", "FLEET_SESSION_DEACTIVATE_NOT_READY")
        try:
            detach()
        except Exception:
            return _response(request_id, "not_ready", "FLEET_SESSION_DEACTIVATE_NOT_READY")
        self._local_association = None
        return _response(request_id, "deactivated", "FLEET_SESSION_DEACTIVATE_DETACHED")

    def handle_session_replay(self, request_id: Any, params: Any) -> dict[str, Any]:
        """Validate only an opaque cursor; replay is intentionally not implemented."""
        if not _is_jsonrpc_request_id(request_id):
            return _invalid_request_id_error()
        if not self._is_closed_replay_request(params):
            return _response(request_id, "denied", "FLEET_SESSION_REPLAY_DENIED")
        if self._host_authority is None:
            return _response(request_id, "denied", "FLEET_SESSION_REPLAY_DENIED")
        return _response(request_id, "not_ready", "FLEET_SESSION_REPLAY_NOT_READY")

    @staticmethod
    def _is_closed_request(params: Any, schema_version: str) -> bool:
        if not isinstance(params, Mapping):
            return False
        try:
            return set(params) == {"schema_version"} and params["schema_version"] == schema_version
        except Exception:
            return False

    @staticmethod
    def _is_closed_replay_request(params: Any) -> bool:
        if not isinstance(params, Mapping):
            return False
        try:
            cursor = params["cursor"]
            return (
                set(params) == {"schema_version", "cursor"}
                and params["schema_version"] == FLEET_SESSION_REPLAY_SCHEMA_VERSION
                and isinstance(cursor, str)
                and 0 < len(cursor) <= _MAX_OPAQUE_CURSOR_LENGTH
            )
        except Exception:
            return False


__all__ = [
    "FLEET_RPC_NAMESPACE",
    "FLEET_SESSION_ACTIVATE_NAME",
    "FLEET_SESSION_ACTIVATE_SCHEMA_VERSION",
    "FLEET_SESSION_STATUS_NAME",
    "FLEET_SESSION_STATUS_SCHEMA_VERSION",
    "FLEET_SESSION_DEACTIVATE_NAME",
    "FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION",
    "FLEET_SESSION_REPLAY_NAME",
    "FLEET_SESSION_REPLAY_SCHEMA_VERSION",
    "FleetD1RegistrationBridge",
    "FleetD1RegistrationError",
]
