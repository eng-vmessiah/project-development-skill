"""Tests for the local, injected Fleet-to-D1 session RPC bridge."""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Any, Callable, cast

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from scripts.pd_fleet.fleet_d1_registration_bridge import (  # noqa: E402
    FLEET_SESSION_ACTIVATE_NAME,
    FLEET_SESSION_ACTIVATE_SCHEMA_VERSION,
    FLEET_SESSION_DEACTIVATE_NAME,
    FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION,
    FLEET_SESSION_REPLAY_NAME,
    FLEET_SESSION_REPLAY_SCHEMA_VERSION,
    FLEET_SESSION_STATUS_NAME,
    FLEET_SESSION_STATUS_SCHEMA_VERSION,
    FleetD1RegistrationBridge,
    FleetD1RegistrationError,
)


class RecordingRegistrar:
    def __init__(self) -> None:
        self.batch_calls: list[tuple[str, tuple[tuple[str, object], ...], bool]] = []
        self.single_register_calls: list[tuple[object, ...]] = []

    def register(self, *args: object, **kwargs: object) -> str:
        self.single_register_calls.append((*args, kwargs))
        return "unexpected.single.register"

    def register_batch(
        self, namespace: str, registrations: tuple[tuple[str, object], ...], *, enabled: bool = False
    ) -> tuple[str, ...]:
        self.batch_calls.append((namespace, registrations, enabled))
        return tuple(f"{namespace}.{name}" for name, _handler in registrations)


def envelope(request_id: Any, status: str, code: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": {"status": status, "code": code}}


def invalid_request_id_error() -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32600, "message": "Invalid Request"},
    }


def registered_handlers(bridge: FleetD1RegistrationBridge, registrar: RecordingRegistrar) -> dict[str, Callable[[Any, Any], dict[str, object]]]:
    bridge.register()
    _namespace, registrations, _enabled = registrar.batch_calls[-1]
    return {
        name: cast(Callable[[Any, Any], dict[str, object]], handler)
        for name, handler in registrations
    }


def test_disabled_bridge_does_not_call_injected_registrar() -> None:
    registrar = RecordingRegistrar()

    assert FleetD1RegistrationBridge(registrar).register() == {
        "status": "not_ready", "code": "FLEET_SESSION_ACTIVATE_NOT_READY"
    }
    assert registrar.batch_calls == []
    assert registrar.single_register_calls == []


def test_enabled_bridge_without_batch_port_fails_closed_without_single_register_calls() -> None:
    class SingleRegisterOnlyPort:
        def __init__(self) -> None:
            self.single_register_calls = 0

        def register(self, *args: object, **kwargs: object) -> str:
            self.single_register_calls += 1
            return "fleet.unexpected"

    port = SingleRegisterOnlyPort()

    with pytest.raises(FleetD1RegistrationError) as raised:
        FleetD1RegistrationBridge(port, enabled=True).register()

    assert str(raised.value) == "invalid injected registrar"
    assert port.single_register_calls == 0


@pytest.mark.parametrize(
    "request_id",
    [
        {"attacker_controlled": "object-id"},
        ["attacker_controlled", "list-id"],
        True,
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
    ids=["object", "list", "bool", "nan", "infinity", "negative-infinity"],
)
def test_invalid_jsonrpc_request_ids_fail_closed_without_reflection(request_id: Any) -> None:
    registrar = RecordingRegistrar()
    handlers = registered_handlers(FleetD1RegistrationBridge(registrar, enabled=True), registrar)

    response = handlers[FLEET_SESSION_ACTIVATE_NAME](
        request_id, {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION}
    )

    assert response == invalid_request_id_error()
    assert "attacker_controlled" not in repr(response)
    assert "object-id" not in repr(response)
    assert "list-id" not in repr(response)


def test_invalid_request_id_prevents_deactivation_side_effect() -> None:
    class LocalAssociation:
        def __init__(self) -> None:
            self.detach_calls = 0

        def detach(self) -> None:
            self.detach_calls += 1

    registrar = RecordingRegistrar()
    association = LocalAssociation()
    handlers = registered_handlers(
        FleetD1RegistrationBridge(
            registrar,
            enabled=True,
            host_authority=object(),
            local_association=association,
        ),
        registrar,
    )

    response = handlers[FLEET_SESSION_DEACTIVATE_NAME](
        ["invalid-id"], {"schema_version": FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION}
    )

    assert response == invalid_request_id_error()
    assert association.detach_calls == 0


def test_enabled_bridge_submits_one_ordered_atomic_batch_without_single_register_fallback() -> None:
    registrar = RecordingRegistrar()

    assert FleetD1RegistrationBridge(registrar, enabled=True).register() == "fleet.session.activate"
    assert [
        (namespace, tuple(name for name, _handler in registrations), enabled)
        for namespace, registrations, enabled in registrar.batch_calls
    ] == [
        (
            "fleet",
            (
                FLEET_SESSION_ACTIVATE_NAME,
                FLEET_SESSION_STATUS_NAME,
                FLEET_SESSION_DEACTIVATE_NAME,
                FLEET_SESSION_REPLAY_NAME,
            ),
            True,
        )
    ]
    assert registrar.single_register_calls == []


@pytest.mark.parametrize(
    ("name", "schema_version", "operation"),
    [
        (FLEET_SESSION_ACTIVATE_NAME, FLEET_SESSION_ACTIVATE_SCHEMA_VERSION, "ACTIVATE"),
        (FLEET_SESSION_STATUS_NAME, FLEET_SESSION_STATUS_SCHEMA_VERSION, "STATUS"),
        (FLEET_SESSION_DEACTIVATE_NAME, FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION, "DEACTIVATE"),
    ],
)
def test_closed_request_denials_are_jsonrpc_envelopes_without_request_leakage(
    name: str, schema_version: str, operation: str
) -> None:
    registrar = RecordingRegistrar()
    handlers = registered_handlers(FleetD1RegistrationBridge(registrar, enabled=True), registrar)
    request_id = "denial-id"
    for params in (
        None,
        {},
        {"schema_version": "unknown"},
        {"schema_version": schema_version, "session_id": "client-session", "principal": "client-principal"},
    ):
        response = handlers[name](request_id, params)

        assert response == envelope(request_id, "denied", f"FLEET_SESSION_{operation}_DENIED")
        assert "client-session" not in repr(response)
        assert "client-principal" not in repr(response)
        assert schema_version not in repr(response)


def test_activate_and_status_not_ready_responses_are_jsonrpc_envelopes() -> None:
    registrar = RecordingRegistrar()
    handlers = registered_handlers(FleetD1RegistrationBridge(registrar, enabled=True, host_authority=object()), registrar)

    assert handlers[FLEET_SESSION_ACTIVATE_NAME](7, {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION}) == envelope(7, "not_ready", "FLEET_SESSION_ACTIVATE_NOT_READY")
    assert handlers[FLEET_SESSION_STATUS_NAME](None, {"schema_version": FLEET_SESSION_STATUS_SCHEMA_VERSION}) == envelope(None, "not_ready", "FLEET_SESSION_STATUS_NOT_READY")


def test_deactivate_returns_envelope_and_only_detaches_injected_association() -> None:
    class LocalAssociation:
        def __init__(self) -> None:
            self.detach_calls = 0

        def detach(self) -> None:
            self.detach_calls += 1

    registrar = RecordingRegistrar()
    association = LocalAssociation()
    handlers = registered_handlers(FleetD1RegistrationBridge(registrar, enabled=True, host_authority=object(), local_association=association), registrar)

    assert handlers[FLEET_SESSION_DEACTIVATE_NAME]("detach-1", {"schema_version": FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION}) == envelope("detach-1", "deactivated", "FLEET_SESSION_DEACTIVATE_DETACHED")
    assert association.detach_calls == 1
    assert handlers[FLEET_SESSION_DEACTIVATE_NAME]("detach-2", {"schema_version": FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION}) == envelope("detach-2", "not_ready", "FLEET_SESSION_DEACTIVATE_NOT_READY")


def test_replay_denials_and_not_ready_are_jsonrpc_envelopes_without_cursor_leakage() -> None:
    registrar = RecordingRegistrar()
    handlers = registered_handlers(FleetD1RegistrationBridge(registrar, enabled=True, host_authority=object()), registrar)
    handler = handlers[FLEET_SESSION_REPLAY_NAME]

    for params in (
        None,
        {},
        {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION},
        {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": 1},
        {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": "opaque-cursor", "session_id": "client-session"},
    ):
        denied = handler("replay-denied", params)
        assert denied == envelope("replay-denied", "denied", "FLEET_SESSION_REPLAY_DENIED")
        assert "opaque-cursor" not in repr(denied)
        assert "client-session" not in repr(denied)
    assert handler("replay-ready", {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": "opaque-cursor"}) == envelope("replay-ready", "not_ready", "FLEET_SESSION_REPLAY_NOT_READY")


def test_valid_requests_without_host_authority_are_denied_envelopes() -> None:
    registrar = RecordingRegistrar()
    handlers = registered_handlers(FleetD1RegistrationBridge(registrar, enabled=True), registrar)

    assert handlers[FLEET_SESSION_ACTIVATE_NAME]("a", {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION}) == envelope("a", "denied", "FLEET_SESSION_ACTIVATE_DENIED")
    assert handlers[FLEET_SESSION_STATUS_NAME]("s", {"schema_version": FLEET_SESSION_STATUS_SCHEMA_VERSION}) == envelope("s", "denied", "FLEET_SESSION_STATUS_DENIED")
    assert handlers[FLEET_SESSION_DEACTIVATE_NAME]("d", {"schema_version": FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION}) == envelope("d", "denied", "FLEET_SESSION_DEACTIVATE_DENIED")
    assert handlers[FLEET_SESSION_REPLAY_NAME]("r", {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": "opaque"}) == envelope("r", "denied", "FLEET_SESSION_REPLAY_DENIED")


def test_bridge_has_no_hermes_or_control_runtime_imports() -> None:
    path = Path(__file__).parents[2] / "scripts/pd_fleet/fleet_d1_registration_bridge.py"
    tree = ast.parse(path.read_text())
    imports = {node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)}
    imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}

    assert "hermes" not in imports
    assert not imports & {"subprocess", "socket", "requests", "httpx", "aiohttp", "websockets"}
