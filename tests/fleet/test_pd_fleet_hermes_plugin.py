"""Red-first tests for the PD-side lifecycle-only plugin package."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.hermes_plugin_contract import load_lifecycle_plugin, PluginLoadStatus  # noqa: E402


PLUGIN_DIR = Path(__file__).parents[2] / "plugins" / "pd-fleet-hermes"


def _load_plugin_module():
    init_file = PLUGIN_DIR / "__init__.py"
    spec = importlib.util.spec_from_file_location("pd_fleet_hermes_test", init_file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plugin_manifest_is_versioned_and_default_off():
    manifest = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text())
    assert manifest["name"] == "pd-fleet-hermes"
    assert manifest["fleet_contract_version"] == "1.0"
    assert manifest["default_enabled"] is False
    assert manifest["provides_hooks"] == ["on_session_start", "on_session_end"]


def test_enabled_plugin_registers_only_lifecycle_hooks():
    module = _load_plugin_module()
    manifest = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text())
    context = type("Context", (), {"hooks": []})()
    context.register_hook = lambda event, handler: context.hooks.append((event, handler))

    result = load_lifecycle_plugin(
        {"name": manifest["name"], "contract_version": manifest["fleet_contract_version"], "enabled": True},
        module.register,
        context,
        {manifest["name"]},
        set(),
    )

    assert result.status is PluginLoadStatus.LOADED
    assert [event for event, _ in context.hooks] == ["on_session_start", "on_session_end"]


def test_plugin_register_does_not_expose_tools_rpc_or_external_effects():
    module = _load_plugin_module()
    source = (PLUGIN_DIR / "__init__.py").read_text()
    assert "register_tool" not in source
    assert "register_rpc" not in source
    assert "subprocess" not in source
    assert "requests" not in source
    assert "httpx" not in source
