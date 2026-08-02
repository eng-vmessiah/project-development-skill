"""Local composition canaries for the injected Fleet-to-D1 registration seam.

The in-memory port below deliberately models only the D1 registration boundary:
handlers are registered by fully-qualified method name and invoked as
``handler(request_id, params)``.  It is not a Hermes runtime substitute.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from scripts.pd_fleet.fleet_d1_registration_bridge import (
    FLEET_SESSION_ACTIVATE_SCHEMA_VERSION,
    FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION,
    FLEET_SESSION_REPLAY_SCHEMA_VERSION,
    FLEET_SESSION_STATUS_SCHEMA_VERSION,
    FleetD1RegistrationBridge,
    FleetD1RegistrationError,
)


RawD1Handler = Callable[[Any, Any], Any]


class InMemoryD1RegistrarDispatcher:
    """Test-only D1-compatible registration and raw-dispatch port."""

    def __init__(self) -> None:
        self._handlers: dict[str, RawD1Handler] = {}
        self.registration_calls: list[tuple[str, str, bool]] = []

    @property
    def method_names(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def register(self, namespace: str, name: str, handler: RawD1Handler, *, enabled: bool = False) -> str:
        method = f"{namespace}.{name}"
        self.registration_calls.append((namespace, name, enabled))
        self._handlers[method] = handler
        return method

    def dispatch(self, method: str, request_id: Any, params: Any) -> Any:
        """Call the registered D1 raw handler with its real two-argument shape."""
        return self._handlers[method](request_id, params)


class ExplodingInMemoryD1Registrar(InMemoryD1RegistrarDispatcher):
    """Test-only injected port failure; no handler execution semantics are implied."""

    def register(self, namespace: str, name: str, handler: RawD1Handler, *, enabled: bool = False) -> str:
        raise RuntimeError("registrar-secret-must-not-leak")


def jsonrpc_result(request_id: Any, status: str, code: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": {"status": status, "code": code}}


def invalid_request_id_error() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32600, "message": "Invalid Request"},
    }


def test_disabled_bridge_composes_without_any_dispatchable_d1_methods() -> None:
    port = InMemoryD1RegistrarDispatcher()

    assert FleetD1RegistrationBridge(port).register() == {
        "status": "not_ready",
        "code": "FLEET_SESSION_ACTIVATE_NOT_READY",
    }
    assert port.registration_calls == []
    assert port.method_names == ()


def test_enabled_bridge_composes_with_exact_approved_d1_method_order() -> None:
    port = InMemoryD1RegistrarDispatcher()

    assert FleetD1RegistrationBridge(port, enabled=True).register() == "fleet.session.activate"
    assert port.registration_calls == [
        ("fleet", "session.activate", True),
        ("fleet", "session.status", True),
        ("fleet", "session.deactivate", True),
        ("fleet", "session.replay", True),
    ]
    assert port.method_names == (
        "fleet.session.activate",
        "fleet.session.status",
        "fleet.session.deactivate",
        "fleet.session.replay",
    )


def test_in_memory_port_preserves_d1_handler_arity_and_raw_return_value() -> None:
    port = InMemoryD1RegistrarDispatcher()
    raw_return = {"unwrapped": object()}
    received: list[tuple[Any, Any]] = []

    def raw_handler(request_id: Any, params: Any) -> Any:
        received.append((request_id, params))
        return raw_return

    port.register("test", "raw", raw_handler, enabled=True)
    request_id = {"opaque": "id"}
    params = {"opaque": "params"}

    assert port.dispatch("test.raw", request_id, params) is raw_return
    assert received == [(request_id, params)]


def test_valid_requests_cross_raw_d1_boundary_with_jsonrpc_result_envelopes() -> None:
    class LocalAssociation:
        def __init__(self) -> None:
            self.detach_calls = 0

        def detach(self) -> None:
            self.detach_calls += 1

    port = InMemoryD1RegistrarDispatcher()
    association = LocalAssociation()
    FleetD1RegistrationBridge(
        port,
        enabled=True,
        host_authority=object(),
        local_association=association,
    ).register()

    assert port.dispatch(
        "fleet.session.activate", "activate-id", {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION}
    ) == jsonrpc_result("activate-id", "not_ready", "FLEET_SESSION_ACTIVATE_NOT_READY")
    assert port.dispatch(
        "fleet.session.status", 12, {"schema_version": FLEET_SESSION_STATUS_SCHEMA_VERSION}
    ) == jsonrpc_result(12, "not_ready", "FLEET_SESSION_STATUS_NOT_READY")
    assert port.dispatch(
        "fleet.session.deactivate", None, {"schema_version": FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION}
    ) == jsonrpc_result(None, "deactivated", "FLEET_SESSION_DEACTIVATE_DETACHED")
    assert association.detach_calls == 1
    assert port.dispatch(
        "fleet.session.replay",
        {"opaque": "request-id"},
        {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": "opaque-cursor"},
    ) == invalid_request_id_error()


@pytest.mark.parametrize("authority_field", ["session_id", "owner", "principal", "capability"])
def test_client_authority_fields_are_denied_at_dispatch_boundary_without_detach(authority_field: str) -> None:
    class LocalAssociation:
        def __init__(self) -> None:
            self.detach_calls = 0

        def detach(self) -> None:
            self.detach_calls += 1

    port = InMemoryD1RegistrarDispatcher()
    association = LocalAssociation()
    FleetD1RegistrationBridge(
        port,
        enabled=True,
        host_authority=object(),
        local_association=association,
    ).register()
    params = {
        "schema_version": FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION,
        authority_field: "client-controlled-authority",
    }

    response = port.dispatch("fleet.session.deactivate", "deny-id", params)

    assert response == jsonrpc_result("deny-id", "denied", "FLEET_SESSION_DEACTIVATE_DENIED")
    assert association.detach_calls == 0
    assert "client-controlled-authority" not in repr(response)


def test_exploding_injected_registration_is_normalized_without_secret_leakage() -> None:
    port = ExplodingInMemoryD1Registrar()

    with pytest.raises(FleetD1RegistrationError) as raised:
        FleetD1RegistrationBridge(port, enabled=True).register()

    assert str(raised.value) == "injected registrar rejected registration"
    assert "registrar-secret-must-not-leak" not in repr(raised.value)
    assert port.method_names == ()
