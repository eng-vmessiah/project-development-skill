"""RED-first tests for the local/injected Fleet-to-D1 session seam."""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Callable, cast

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

    def register(self, namespace, name, handler, *, enabled=False):
        self.calls.append((namespace, name, handler, enabled))
        return f"{namespace}.{name}"


def test_disabled_bridge_does_not_call_injected_registrar():
    registrar = RecordingRegistrar()

    result = FleetD1RegistrationBridge(registrar).register()

    assert result == {"status": "not_ready", "code": "FLEET_SESSION_ACTIVATE_NOT_READY"}
    assert registrar.calls == []


def test_enabled_bridge_delegates_only_approved_segmented_activate_name():
    registrar = RecordingRegistrar()

    result = FleetD1RegistrationBridge(registrar, enabled=True).register()

    assert result == "fleet.session.activate"
    assert len(registrar.calls) == 4
    namespace, name, handler, enabled = registrar.calls[0]
    assert (namespace, name, enabled) == ("fleet", FLEET_SESSION_ACTIVATE_NAME, True)
    assert callable(handler)
    assert [(namespace, name, enabled) for namespace, name, _handler, enabled in registrar.calls] == [
        ("fleet", FLEET_SESSION_ACTIVATE_NAME, True),
        ("fleet", FLEET_SESSION_STATUS_NAME, True),
        ("fleet", FLEET_SESSION_DEACTIVATE_NAME, True),
        ("fleet", FLEET_SESSION_REPLAY_NAME, True),
    ]


def test_new_session_operations_are_default_off_without_registrar_calls():
    registrar = RecordingRegistrar()

    result = FleetD1RegistrationBridge(registrar).register()

    assert result == {"status": "not_ready", "code": "FLEET_SESSION_ACTIVATE_NOT_READY"}
    assert registrar.calls == []


def test_status_and_deactivate_reject_closed_envelopes_client_session_identity_and_missing_authority():
    registrar = RecordingRegistrar()
    bridge = FleetD1RegistrationBridge(registrar, enabled=True)
    bridge.register()
    handlers = {name: cast(Callable[[object, object], dict[str, str]], handler) for _ns, name, handler, _enabled in registrar.calls}

    cases = (
        (FLEET_SESSION_STATUS_NAME, FLEET_SESSION_STATUS_SCHEMA_VERSION, "FLEET_SESSION_STATUS_DENIED"),
        (FLEET_SESSION_DEACTIVATE_NAME, FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION, "FLEET_SESSION_DEACTIVATE_DENIED"),
    )
    for name, schema_version, denied_code in cases:
        handler = handlers[name]
        for request in (
            {},
            {"schema_version": "unknown"},
            {"schema_version": schema_version, "session_id": "client-session"},
            {"schema_version": schema_version, "session_ref": "client-session"},
            {"schema_version": schema_version, "owner_ref": "client-owner"},
            {"schema_version": schema_version, "principal": "client-principal"},
        ):
            assert handler("request-1", request) == {"status": "denied", "code": denied_code}
        assert handler("request-1", {"schema_version": schema_version}) == {
            "status": "denied", "code": denied_code
        }


def test_deactivate_only_detaches_an_injected_local_association():
    class LocalAssociation:
        def __init__(self) -> None:
            self.detach_calls = 0

        def detach(self) -> None:
            self.detach_calls += 1

    registrar = RecordingRegistrar()
    association = LocalAssociation()
    bridge = FleetD1RegistrationBridge(
        registrar,
        enabled=True,
        host_authority=object(),
        local_association=association,
    )
    bridge.register()
    handler = cast(Callable[[object, object], dict[str, str]], registrar.calls[2][2])

    assert handler("request-1", {"schema_version": FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION}) == {
        "status": "deactivated",
        "code": "FLEET_SESSION_DEACTIVATE_DETACHED",
    }
    assert association.detach_calls == 1
    assert handler("request-2", {"schema_version": FLEET_SESSION_DEACTIVATE_SCHEMA_VERSION}) == {
        "status": "not_ready",
        "code": "FLEET_SESSION_DEACTIVATE_NOT_READY",
    }


def test_replay_requires_only_closed_schema_and_opaque_cursor_and_is_bounded_not_ready():
    registrar = RecordingRegistrar()
    bridge = FleetD1RegistrationBridge(registrar, enabled=True, host_authority=object())
    bridge.register()
    handlers = {name: cast(Callable[[object, object], dict[str, str]], handler) for _ns, name, handler, _enabled in registrar.calls}
    handler = handlers[FLEET_SESSION_REPLAY_NAME]

    for request in (
        {},
        {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION},
        {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": 1},
        {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": "x", "session_id": "client-session"},
        {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": "x", "principal": "client-principal"},
    ):
        assert handler("request-1", request) == {
            "status": "denied",
            "code": "FLEET_SESSION_REPLAY_DENIED",
        }

    assert handler("request-1", {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": "opaque-cursor"}) == {
        "status": "not_ready",
        "code": "FLEET_SESSION_REPLAY_NOT_READY",
    }


def test_replay_denies_missing_authority_without_using_client_session_identity():
    registrar = RecordingRegistrar()
    bridge = FleetD1RegistrationBridge(registrar, enabled=True)
    bridge.register()
    handler = cast(Callable[[object, object], dict[str, str]], registrar.calls[3][2])

    assert handler("request-1", {"schema_version": FLEET_SESSION_REPLAY_SCHEMA_VERSION, "cursor": "opaque"}) == {
        "status": "denied",
        "code": "FLEET_SESSION_REPLAY_DENIED",
    }


def test_handler_rejects_closed_request_and_never_accepts_client_authority_fields():
    registrar = RecordingRegistrar()
    bridge = FleetD1RegistrationBridge(registrar, enabled=True, host_authority=object())
    bridge.register()
    handler = cast(Callable[[object, object], dict[str, str]], registrar.calls[0][2])

    for request in (
        {},
        {"schema_version": "unknown"},
        {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION, "session_id": "client-session"},
        {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION, "session_ref": "client-session"},
        {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION, "owner_ref": "client-owner"},
        {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION, "principal": "client-principal"},
        {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION, "capability": "activate"},
    ):
        assert handler("request-1", request) == {
            "status": "denied",
            "code": "FLEET_SESSION_ACTIVATE_DENIED",
        }


def test_handler_denies_when_host_authority_is_missing_without_session_effects():
    registrar = RecordingRegistrar()
    bridge = FleetD1RegistrationBridge(registrar, enabled=True)
    bridge.register()
    handler = cast(Callable[[object, object], dict[str, str]], registrar.calls[0][2])

    assert handler("request-1", {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION}) == {
        "status": "denied",
        "code": "FLEET_SESSION_ACTIVATE_DENIED",
    }


def test_handler_is_bounded_not_ready_even_when_authority_is_present():
    registrar = RecordingRegistrar()
    authority = object()
    bridge = FleetD1RegistrationBridge(registrar, enabled=True, host_authority=authority)
    bridge.register()
    handler = cast(Callable[[object, object], dict[str, str]], registrar.calls[0][2])

    assert handler("request-1", {"schema_version": FLEET_SESSION_ACTIVATE_SCHEMA_VERSION}) == {
        "status": "not_ready",
        "code": "FLEET_SESSION_ACTIVATE_NOT_READY",
    }


def test_bridge_has_no_hermes_or_control_runtime_imports():
    path = Path(__file__).parents[2] / "scripts/pd_fleet/fleet_d1_registration_bridge.py"
    tree = ast.parse(path.read_text())
    imports = {node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)}
    imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}

    assert "hermes" not in imports
    assert not imports & {"subprocess", "socket", "requests", "httpx", "aiohttp", "websockets"}
