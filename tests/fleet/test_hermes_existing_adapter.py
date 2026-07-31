"""Focused safety and seam tests for the honest Hermes adapter."""
from __future__ import annotations

import ast
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.gateway_bridge_contracts import MAX_REPLAY_BATCH, ReplayWindow, SessionSnapshot  # noqa: E402
from pd_fleet.hermes_existing_adapter import (  # noqa: E402
    HermesAdapterError,
    HermesExistingReadOnlyAdapter,
    NOT_READY,
    NOT_READY_HERMES_SEAM,
)


class Client:
    capabilities = {"session_snapshot", "session_replay", "session_heartbeat"}

    def __init__(self):
        self.calls = []

    def snapshot(self, session_ref):
        self.calls.append(("snapshot", session_ref))
        return {"session_ref": session_ref, "association_ref": "assoc-1", "stream_epoch": "epoch-1"}

    def replay(self, window, cursor):
        self.calls.append(("replay", window, cursor))
        return []

    def heartbeat(self, session_ref):
        self.calls.append(("heartbeat", session_ref))
        return {"session_ref": session_ref, "association_ref": "assoc-1", "stream_epoch": "epoch-1"}


def test_default_adapter_does_not_network_or_discover():
    adapter = HermesExistingReadOnlyAdapter(None)
    assert adapter.probe()["code"] == NOT_READY_HERMES_SEAM
    assert adapter.capability_report()["production"] == NOT_READY


def test_capability_report_is_explicit_and_machine_readable():
    report = HermesExistingReadOnlyAdapter(Client()).capability_report()
    assert report["existing_hermes_read_only"]["session_snapshot"] == "READY"
    for key in ("fleet_observer_activation", "global_subscription", "opaque_activation_ticket",
                "issuer_verification", "production"):
        assert report[key] == NOT_READY


def test_probe_stops_at_missing_fleet_seam_without_calling_client():
    client = Client()
    result = HermesExistingReadOnlyAdapter(client).probe()
    assert result["code"] == NOT_READY_HERMES_SEAM
    assert client.calls == []


def test_declared_read_only_operations_delegate_through_contracts():
    client = Client()
    adapter = HermesExistingReadOnlyAdapter(client)
    snapshot = adapter.session_snapshot("session-1")
    assert isinstance(snapshot, SessionSnapshot)
    window = ReplayWindow("assoc-1", "epoch-1", 0)
    assert adapter.session_replay(window) == ()
    assert isinstance(adapter.session_heartbeat("session-1"), SessionSnapshot)
    assert [call[0] for call in client.calls] == ["snapshot", "replay", "heartbeat"]


def test_undeclared_operations_and_controls_are_rejected():
    adapter = HermesExistingReadOnlyAdapter(object())
    with pytest.raises(HermesAdapterError) as error:
        adapter.session_snapshot("session-1")
    assert error.value.code == NOT_READY_HERMES_SEAM
    with pytest.raises(AttributeError):
        adapter.dispatch
    with pytest.raises(AttributeError):
        adapter.cancel


def test_malformed_transport_result_is_bounded():
    class Bad(Client):
        def snapshot(self, session_ref):
            return {"secret": "token=super-secret", "path": "/private/file"}

    with pytest.raises(HermesAdapterError) as error:
        HermesExistingReadOnlyAdapter(Bad()).session_snapshot("session-1")
    assert error.value.code == "MALFORMED_TRANSPORT_RESULT"
    assert "super-secret" not in str(error.value)


def test_no_state_db_or_forbidden_runtime_imports():
    source = Path(__file__).parents[2] / "scripts" / "pd_fleet" / "hermes_existing_adapter.py"
    tree = ast.parse(source.read_text())
    imported = {node.names[0].name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.Import) and node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.module}
    assert not imported & {"requests", "httpx", "urllib", "subprocess", "sqlite3", "os", "socket"}
    assert "state.db" not in source.read_text()


@pytest.mark.parametrize("session_ref", [
    "", None, 123, "a/b", r"a\\b", "http://session", "urn:session",
    "session\nref", "session\tref", "x" * 129,
])
def test_session_ref_is_validated_before_injected_client_call(session_ref):
    client = Client()
    with pytest.raises(HermesAdapterError) as error:
        HermesExistingReadOnlyAdapter(client).session_snapshot(session_ref)
    assert error.value.code == "INVALID_REQUEST"
    assert client.calls == []


def test_session_ref_validation_applies_to_heartbeat():
    client = Client()
    with pytest.raises(HermesAdapterError) as error:
        HermesExistingReadOnlyAdapter(client).session_heartbeat("bad/ref")
    assert error.value.code == "INVALID_REQUEST"
    assert client.calls == []


def test_replay_batch_limit_is_checked_before_materialization():
    class Oversized(Client):
        def replay(self, window, cursor):
            return [None] * (MAX_REPLAY_BATCH + 1)

    client = Oversized()
    with pytest.raises(HermesAdapterError) as error:
        HermesExistingReadOnlyAdapter(client).session_replay(ReplayWindow("assoc-1", "epoch-1", 0))
    assert error.value.code == "REPLAY_BATCH_LIMIT"


def test_replay_requested_limit_is_checked_at_adapter_boundary():
    client = Client()
    window = object.__new__(ReplayWindow)
    object.__setattr__(window, "limit", MAX_REPLAY_BATCH + 1)
    with pytest.raises(HermesAdapterError) as error:
        HermesExistingReadOnlyAdapter(client).session_replay(window)
    assert error.value.code == "REPLAY_BATCH_LIMIT"
    assert client.calls == []


def test_transport_exception_is_bounded_and_does_not_leak_exception_text():
    class Failing(Client):
        def snapshot(self, session_ref):
            raise RuntimeError("secret transport details / token=abc")

    with pytest.raises(HermesAdapterError) as error:
        HermesExistingReadOnlyAdapter(Failing()).session_snapshot("session-1")
    assert error.value.code == "TRANSPORT_ERROR"
    assert str(error.value) == "TRANSPORT_ERROR"
    assert error.value.args == ("TRANSPORT_ERROR",)
