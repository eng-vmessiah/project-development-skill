"""Tests for the explicit injected Fleet-to-Hermes D1 batch adapter."""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from scripts.pd_fleet.tui_d1_batch_registrar_adapter import TuiD1BatchRegistrarAdapter  # noqa: E402


def test_adapter_forwards_one_batch_and_enabled_as_a_keyword() -> None:
    received: list[tuple[str, object, bool]] = []
    registrations = (("session.activate", object()),)
    host_result = ("fleet.session.activate",)

    def register_plugin_rpc_batch(namespace: str, candidates: object, *, enabled: bool = False) -> object:
        received.append((namespace, candidates, enabled))
        return host_result

    adapter = TuiD1BatchRegistrarAdapter(register_plugin_rpc_batch)

    assert adapter.register_batch("fleet", registrations, enabled=True) is host_result
    assert received == [("fleet", registrations, True)]


def test_adapter_default_enabled_is_false_when_called_directly() -> None:
    received: list[bool] = []

    def register_plugin_rpc_batch(_namespace: str, _registrations: object, *, enabled: bool = False) -> None:
        received.append(enabled)

    TuiD1BatchRegistrarAdapter(register_plugin_rpc_batch).register_batch("fleet", ())

    assert received == [False]


@pytest.mark.parametrize("host", [None, object(), "not-a-callable"])
def test_adapter_rejects_non_callable_host_fail_closed(host: Any) -> None:
    with pytest.raises(TypeError, match="register_plugin_rpc_batch must be callable"):
        TuiD1BatchRegistrarAdapter(host)


def test_adapter_requires_host_callable() -> None:
    with pytest.raises(TypeError):
        TuiD1BatchRegistrarAdapter()  # type: ignore[call-arg]


def test_adapter_does_not_catch_host_errors() -> None:
    def register_plugin_rpc_batch(_namespace: str, _registrations: object, *, enabled: bool = False) -> None:
        raise RuntimeError("host failure")

    with pytest.raises(RuntimeError, match="host failure"):
        TuiD1BatchRegistrarAdapter(register_plugin_rpc_batch).register_batch("fleet", (), enabled=True)


def test_adapter_has_no_hermes_or_runtime_imports() -> None:
    path = Path(__file__).parents[2] / "scripts/pd_fleet/tui_d1_batch_registrar_adapter.py"
    tree = ast.parse(path.read_text())
    imports = {node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)}
    imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}

    assert "hermes" not in imports
    assert not imports & {"subprocess", "socket", "requests", "httpx", "aiohttp", "websockets"}
