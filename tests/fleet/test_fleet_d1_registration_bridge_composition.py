"""Cross-contract composition canaries for Fleet's Hermes D1 batch adapter.

The fake below implements only the injected public Hermes callable and a raw D1
method dispatcher.  It neither imports nor substitutes for a Hermes runtime.
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
from scripts.pd_fleet.tui_d1_batch_registrar_adapter import TuiD1BatchRegistrarAdapter

RawD1Handler = Callable[[Any, Any], Any]


class FakeHermesD1PublicDispatcher:
    """Atomic fake of Hermes's injected ``register_plugin_rpc_batch`` callable."""

    def __init__(self) -> None:
        self._handlers: dict[str, RawD1Handler] = {}
        self.batch_calls: list[tuple[str, tuple[tuple[str, RawD1Handler], ...], bool]] = []

    def registered_methods(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def register_plugin_rpc_batch(
        self, namespace: str, registrations: tuple[tuple[str, RawD1Handler], ...], *, enabled: bool = False
    ) -> tuple[str, ...]:
        self.batch_calls.append((namespace, registrations, enabled))
        candidates = {f"{namespace}.{name}": handler for name, handler in registrations}
        self._handlers.update(candidates)
        return tuple(candidates)

    def dispatch(self, method: str, request_id: Any, params: Any) -> Any:
        return self._handlers[method](request_id, params)


class RejectingBatchFakeHermesD1PublicDispatcher(FakeHermesD1PublicDispatcher):
    """Reject all candidates before publishing any route."""

    def register_plugin_rpc_batch(
        self, namespace: str, registrations: tuple[tuple[str, RawD1Handler], ...], *, enabled: bool = False
    ) -> tuple[str, ...]:
        self.batch_calls.append((namespace, registrations, enabled))
        raise RuntimeError("host-candidate-rejection-must-not-leak")


def _adapter(host: FakeHermesD1PublicDispatcher) -> TuiD1BatchRegistrarAdapter:
    return TuiD1BatchRegistrarAdapter(host.register_plugin_rpc_batch)


def jsonrpc_result(request_id: Any, status: str, code: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": {"status": status, "code": code}}


def test_disabled_bridge_composes_without_any_dispatchable_d1_methods() -> None:
    host = FakeHermesD1PublicDispatcher()

    assert FleetD1RegistrationBridge(_adapter(host)).register() == {
        "status": "not_ready",
        "code": "FLEET_SESSION_ACTIVATE_NOT_READY",
    }
    assert host.batch_calls == []
    assert host.registered_methods() == ()


def test_bridge_adapter_host_composition_publishes_and_dispatches_all_four_routes() -> None:
    host = FakeHermesD1PublicDispatcher()

    assert FleetD1RegistrationBridge(_adapter(host), enabled=True, host_authority=object()).register() == "fleet.session.activate"
    assert [(namespace, tuple(name for name, _handler in registrations), enabled) for namespace, registrations, enabled in host.batch_calls] == [
        ("fleet", ("session.activate", "session.status", "session.deactivate", "session.replay"), True)
    ]
    assert host.registered_methods() == (
        "fleet.session.activate",
        "fleet.session.status",
        "fleet.session.deactivate",
        "fleet.session.replay",
    )
    assert host.dispatch(
        "fleet.session.activate", "activate-id", {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION}
    ) == jsonrpc_result("activate-id", "not_ready", "FLEET_SESSION_ACTIVATE_NOT_READY")
    assert host.dispatch(
        "fleet.session.status", "status-id", {"schema_version": FLEET_SESSION_STATUS_SCHEMA_VERSION}
    ) == jsonrpc_result("status-id", "not_ready", "FLEET_SESSION_STATUS_NOT_READY")
    assert host.dispatch(
        "fleet.session.deactivate", "deactivate-id", {"schema_version": FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION}
    ) == jsonrpc_result("deactivate-id", "not_ready", "FLEET_SESSION_DEACTIVATE_NOT_READY")
    assert host.dispatch(
        "fleet.session.replay", "replay-id", {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": "opaque"}
    ) == jsonrpc_result("replay-id", "not_ready", "FLEET_SESSION_REPLAY_NOT_READY")


def test_adapter_preserves_d1_raw_handler_arity_and_return_value() -> None:
    host = FakeHermesD1PublicDispatcher()
    raw_return = {"unwrapped": object()}
    received: list[tuple[Any, Any]] = []

    def raw_handler(request_id: Any, params: Any) -> Any:
        received.append((request_id, params))
        return raw_return

    assert _adapter(host).register_batch("test", (("raw", raw_handler),), enabled=True) == ("test.raw",)
    request_id = {"opaque": "id"}
    params = {"opaque": "params"}

    assert host.dispatch("test.raw", request_id, params) is raw_return
    assert received == [(request_id, params)]


@pytest.mark.parametrize("authority_field", ["session_id", "owner", "principal", "capability"])
def test_client_authority_fields_are_denied_at_dispatch_boundary(authority_field: str) -> None:
    host = FakeHermesD1PublicDispatcher()
    FleetD1RegistrationBridge(_adapter(host), enabled=True, host_authority=object()).register()

    response = host.dispatch(
        "fleet.session.deactivate",
        "deny-id",
        {"schema_version": FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION, authority_field: "client-controlled-authority"},
    )

    assert response == jsonrpc_result("deny-id", "denied", "FLEET_SESSION_DEACTIVATE_DENIED")
    assert "client-controlled-authority" not in repr(response)


def test_host_candidate_rejection_is_normalized_by_bridge_and_publishes_no_routes() -> None:
    host = RejectingBatchFakeHermesD1PublicDispatcher()

    with pytest.raises(FleetD1RegistrationError) as raised:
        FleetD1RegistrationBridge(_adapter(host), enabled=True).register()

    assert str(raised.value) == "injected registrar rejected registration"
    assert "host-candidate-rejection-must-not-leak" not in repr(raised.value)
    assert len(host.batch_calls) == 1
    assert host.registered_methods() == ()
