"""Red-first tests for the local/injected B15a lifecycle-only plugin contract."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.hermes_plugin_contract import (  # noqa: E402
    PluginContractError,
    PluginLoadStatus,
    load_lifecycle_plugin,
)


MANIFEST = {
    "name": "pd-fleet-hermes",
    "contract_version": "1.0",
    "enabled": True,
}


class Context:
    def __init__(self):
        self.hooks = []
        self.forbidden_calls = []

    def register_hook(self, event, handler):
        self.hooks.append((event, handler))

    def register_tool(self, *args, **kwargs):
        self.forbidden_calls.append(("tool", args, kwargs))
        raise AssertionError("model tools are forbidden in lifecycle-only loading")

    def register_rpc(self, *args, **kwargs):
        self.forbidden_calls.append(("rpc", args, kwargs))
        raise AssertionError("RPC registration belongs to the Hermes seam")


def plugin_register(ctx):
    ctx.register_hook("session_started", lambda: None)


def test_absent_plugin_is_a_noop_and_does_not_call_register():
    register_calls = []
    result = load_lifecycle_plugin(
        None, lambda ctx: register_calls.append(ctx), Context(), set(), set(), lambda _: None
    )
    assert result.status is PluginLoadStatus.ABSENT
    assert register_calls == []


def test_disabled_plugin_is_a_noop_and_does_not_call_register():
    register_calls = []
    result = load_lifecycle_plugin(
        MANIFEST, lambda ctx: register_calls.append(ctx), Context(), set(), set(), lambda _: None
    )
    assert result.status is PluginLoadStatus.DISABLED
    assert register_calls == []


def test_enabled_plugin_registers_lifecycle_hooks_only():
    context = Context()
    result = load_lifecycle_plugin(MANIFEST, plugin_register, context, {MANIFEST["name"]}, set(), lambda _: None)
    assert result.status is PluginLoadStatus.LOADED
    assert [event for event, _ in context.hooks] == ["session_started"]
    assert context.forbidden_calls == []


def test_malformed_manifest_fails_closed_before_register():
    register_calls = []
    malformed = {"name": "pd-fleet-hermes", "enabled": True}
    with pytest.raises(PluginContractError, match="contract_version"):
        load_lifecycle_plugin(
            malformed, lambda ctx: register_calls.append(ctx), Context(), {"pd-fleet-hermes"}, set(), lambda _: None
        )
    assert register_calls == []


def test_duplicate_load_is_rejected_without_second_register():
    register_calls = []
    context = Context()
    enabled = {MANIFEST["name"]}
    loaded = set()
    def register(ctx):
        register_calls.append(ctx)
        plugin_register(ctx)

    load_lifecycle_plugin(MANIFEST, register, context, enabled, loaded, lambda _: None)
    with pytest.raises(PluginContractError, match="duplicate"):
        load_lifecycle_plugin(MANIFEST, register, context, enabled, loaded, lambda _: None)
    assert len(context.hooks) == 1
    assert len(register_calls) == 1


def test_forbidden_tool_or_rpc_registration_fails_closed():
    def forbidden_register(ctx):
        ctx.register_tool("model-tool", lambda: None)

    with pytest.raises(PluginContractError, match="unsupported lifecycle context"):
        load_lifecycle_plugin(MANIFEST, forbidden_register, Context(), {MANIFEST["name"]}, set())


def test_failed_register_does_not_leave_plugin_marked_loaded():
    loaded = set()

    def failing_register(ctx):
        raise RuntimeError("plugin failure")

    with pytest.raises(RuntimeError, match="plugin failure"):
        load_lifecycle_plugin(MANIFEST, failing_register, Context(), {MANIFEST["name"]}, loaded)
    assert loaded == set()


def test_private_registration_callback_cannot_bypass_lifecycle_validation():
    def bypass_register(ctx):
        ctx._register_hook("not-validated", lambda: None)

    with pytest.raises((PluginContractError, AttributeError)):
        load_lifecycle_plugin(MANIFEST, bypass_register, Context(), {MANIFEST["name"]}, set())


def test_failed_register_rolls_back_staged_hooks():
    context = Context()

    def partially_failing_register(ctx):
        ctx.register_hook("session_started", lambda: None)
        raise RuntimeError("late plugin failure")

    with pytest.raises(RuntimeError, match="late plugin failure"):
        load_lifecycle_plugin(MANIFEST, partially_failing_register, context, {MANIFEST["name"]}, set())
    assert context.hooks == []


def test_opaque_target_is_rejected_before_publication():
    class OpaqueTarget:
        def __init__(self):
            self.calls = []

        def register_hook(self, event, handler):
            self.calls.append((event, handler))

    target = OpaqueTarget()
    with pytest.raises(PluginContractError, match="rollback boundary"):
        load_lifecycle_plugin(MANIFEST, plugin_register, target, {MANIFEST["name"]}, set())
    assert target.calls == []
