"""Local, injected, default-off registration bridge for Fleet session RPCs.

This Fleet-side seam neither imports nor discovers Hermes, resolves host sessions,
activates a runtime, persists data, nor dispatches work.  Host authority and the
one optional local bridge association are injected and deliberately opaque.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable, cast

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


class FleetD1RegistrationError(ValueError):
    """Stable local error for an invalid injected D1 registration port."""


def _result(status: str, code: str) -> dict[str, str]:
    """Return a fresh, bounded response without reflecting request data."""
    return {"status": status, "code": code}


def _not_ready(operation: str) -> dict[str, str]:
    return _result("not_ready", f"FLEET_SESSION_{operation}_NOT_READY")


def _denied(operation: str) -> dict[str, str]:
    return _result("denied", f"FLEET_SESSION_{operation}_DENIED")


class FleetD1RegistrationBridge:
    """Register approved Fleet session names through an injected, default-off port.

    Every handler has a closed request envelope.  In particular, no client-provided
    session, owner, principal, or capability field is accepted as identity or
    authority.  ``local_association`` is an optional *injected* bridge-only object;
    deactivate can call only its zero-argument ``detach`` method and never a host
    session API.  Status and replay are read-only not-ready seams.
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
        """Register the approved names, or remain locally not-ready when disabled.

        The activate method string remains the return value for compatibility with
        the original D1 seam; every registration is still independently injected.
        """
        if not self._enabled:
            return _not_ready("ACTIVATE")
        register = getattr(self._registrar, "register", None)
        if not callable(register):
            raise FleetD1RegistrationError("invalid injected registrar")

        registrations: tuple[tuple[str, Callable[[Any, Any], dict[str, str]]], ...] = (
            (FLEET_SESSION_ACTIVATE_NAME, self.handle_session_activate),
            (FLEET_SESSION_STATUS_NAME, self.handle_session_status),
            (FLEET_SESSION_DEACTIVATE_NAME, self.handle_session_deactivate),
            (FLEET_SESSION_REPLAY_NAME, self.handle_session_replay),
        )
        registered_names: list[str] = []
        try:
            for name, handler in registrations:
                registered = register(FLEET_RPC_NAMESPACE, name, handler, enabled=True)
                expected = f"{FLEET_RPC_NAMESPACE}.{name}"
                if registered != expected:
                    raise FleetD1RegistrationError("injected registrar returned invalid method")
                registered_names.append(cast(str, registered))
        except FleetD1RegistrationError:
            raise
        except Exception:
            raise FleetD1RegistrationError("injected registrar rejected registration") from None
        return registered_names[0]

    def handle_session_activate(self, _request_id: Any, params: Any) -> dict[str, str]:
        """Fail closed pending future host-side authority and activation semantics."""
        if not self._is_closed_request(params, FLEET_SESSION_ACTIVATE_SCHEMA_VERSION):
            return _denied("ACTIVATE")
        if self._host_authority is None:
            return _denied("ACTIVATE")
        return _not_ready("ACTIVATE")

    def handle_session_status(self, _request_id: Any, params: Any) -> dict[str, str]:
        """Expose no session data until a host-authorized read-only contract exists."""
        if not self._is_closed_request(params, FLEET_SESSION_STATUS_SCHEMA_VERSION):
            return _denied("STATUS")
        if self._host_authority is None:
            return _denied("STATUS")
        return _not_ready("STATUS")

    def handle_session_deactivate(self, _request_id: Any, params: Any) -> dict[str, str]:
        """Detach only an injected bridge association; never mutate a host session."""
        if not self._is_closed_request(params, FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION):
            return _denied("DEACTIVATE")
        if self._host_authority is None:
            return _denied("DEACTIVATE")
        detach = getattr(self._local_association, "detach", None)
        if not callable(detach):
            return _not_ready("DEACTIVATE")
        try:
            detach()
        except Exception:
            return _not_ready("DEACTIVATE")
        self._local_association = None
        return _result("deactivated", "FLEET_SESSION_DEACTIVATE_DETACHED")

    def handle_session_replay(self, _request_id: Any, params: Any) -> dict[str, str]:
        """Validate only an opaque cursor; replay is intentionally not implemented."""
        if not self._is_closed_replay_request(params):
            return _denied("REPLAY")
        if self._host_authority is None:
            return _denied("REPLAY")
        return _not_ready("REPLAY")

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
