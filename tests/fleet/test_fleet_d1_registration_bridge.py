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
)


class RecordingRegistrar:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object, bool]] = []

    def register(self, namespace: str, name: str, handler: object, *, enabled: bool = False) -> str:
        self.calls.append((namespace, name, handler, enabled))
        return f"{namespace}.{name}"


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
    return {
        name: cast(Callable[[Any, Any], dict[str, object]], handler)
        for _namespace, name, handler, _enabled in registrar.calls
    }


def test_disabled_bridge_does_not_call_injected_registrar() -> None:
    registrar = RecordingRegistrar()

    assert FleetD1RegistrationBridge(registrar).register() == {
        "status": "not_ready", "code": "FLEET_SESSION_ACTIVATE_NOT_READY"
    }
    assert registrar.calls == []


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


def test_enabled_bridge_registers_only_the_four_approved_names() -> None:
    registrar = RecordingRegistrar()

    assert FleetD1RegistrationBridge(registrar, enabled=True).register() == "fleet.session.activate"
    assert [(namespace, name, enabled) for namespace, name, _handler, enabled in registrar.calls] == [
        ("fleet", FLEET_SESSION_ACTIVATE_NAME, True),
        ("fleet", FLEET_SESSION_STATUS_NAME, True),
        ("fleet", FLEET_SESSION_DEACTIVATE_NAME, True),
        ("fleet", FLEET_SESSION_REPLAY_NAME, True),
    ]


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
