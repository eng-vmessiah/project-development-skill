"""Local/injected lifecycle-only contract for the future Hermes plugin.

This module deliberately does not import Hermes, discover plugins, load files,
open transports, or register real RPCs. It is a deterministic Fleet-side test
seam for validating the B15a plugin contract before a supported Hermes seam
exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from collections.abc import Callable, Mapping, MutableSet, Set
from typing import Any

PLUGIN_NAME = "pd-fleet-hermes"
CONTRACT_VERSION = "1.0"
MAX_NAME_BYTES = 128
MAX_EVENT_BYTES = 128


class PluginContractError(ValueError):
    """Stable fail-closed error for local plugin contract violations."""


class PluginLoadStatus(Enum):
    ABSENT = "absent"
    DISABLED = "disabled"
    LOADED = "loaded"


@dataclass(frozen=True)
class PluginLoadResult:
    status: PluginLoadStatus
    name: str | None = None
    contract_version: str | None = None


class LifecycleOnlyContext:
    """Restricted, staging-only context exposed to plugin registration.

    The target callback is deliberately not stored on this object.  A plugin can
    only stage validated lifecycle hooks; the loader publishes them after
    ``register()`` returns successfully.
    """

    __slots__ = ("_staged_hooks",)

    def __init__(self) -> None:
        self._staged_hooks: list[tuple[str, Callable[..., Any]]] = []

    @staticmethod
    def _validate_hook(event: Any, handler: Any) -> tuple[str, Callable[..., Any]]:
        if type(event) is not str or not event or len(event.encode("utf-8")) > MAX_EVENT_BYTES:
            raise PluginContractError("invalid lifecycle event")
        if not callable(handler):
            raise PluginContractError("lifecycle handler must be callable")
        return event, handler

    def register_hook(self, event: Any, handler: Any) -> None:
        self._staged_hooks.append(self._validate_hook(event, handler))

    def _commit(self, target: Any) -> None:
        register_hook = getattr(target, "register_hook", None)
        if not callable(register_hook):
            raise PluginContractError("lifecycle context missing register_hook")
        before = getattr(target, "hooks", None)
        if not isinstance(before, list):
            raise PluginContractError("lifecycle context missing rollback boundary")
        # Revalidate the staged list at the publication boundary so direct
        # mutation of the private staging list cannot widen the contract.
        staged = [self._validate_hook(event, handler) for event, handler in self._staged_hooks]
        before_len = len(before)
        try:
            for event, handler in staged:
                register_hook(event, handler)
        except Exception:
            # The local/injected target convention exposes a hooks list. Restore
            # it when publication fails midway; opaque targets are rejected above.
            del before[before_len:]
            raise
        finally:
            self._staged_hooks.clear()

    def __getattr__(self, name: str) -> Any:
        raise PluginContractError("unsupported lifecycle context")


def _bounded_string(value: Any, field: str, maximum: int) -> str:
    if type(value) is not str or not value:
        raise PluginContractError(f"{field} must be a non-empty string")
    if len(value.encode("utf-8")) > maximum:
        raise PluginContractError(f"{field} exceeds bound")
    return value


def _validate_manifest(manifest: Mapping[str, Any]) -> tuple[str, str, bool]:
    if not isinstance(manifest, Mapping):
        raise PluginContractError("manifest must be a mapping")
    name = _bounded_string(manifest.get("name"), "name", MAX_NAME_BYTES)
    version = _bounded_string(manifest.get("contract_version"), "contract_version", 32)
    if version != CONTRACT_VERSION:
        raise PluginContractError("unsupported contract_version")
    enabled = manifest.get("enabled")
    if type(enabled) is not bool:
        raise PluginContractError("enabled must be boolean")
    return name, version, enabled


def load_lifecycle_plugin(
    manifest: Mapping[str, Any] | None,
    register: Callable[[LifecycleOnlyContext], Any],
    target_context: Any,
    enabled_plugins: Set[str],
    loaded_plugins: MutableSet[str],
    report: Callable[[PluginLoadResult], Any] | None = None,
) -> PluginLoadResult:
    """Load one local plugin only when every lifecycle-only gate passes.

    ``enabled_plugins`` is configuration/allow-list state. ``loaded_plugins``
    is caller-owned process state used to reject duplicate registration. No
    mutation occurs until manifest validation and registration succeed.
    """
    if manifest is None:
        result = PluginLoadResult(PluginLoadStatus.ABSENT)
        if report is not None:
            report(result)
        return result

    name, version, enabled = _validate_manifest(manifest)
    if not enabled or name not in enabled_plugins:
        result = PluginLoadResult(PluginLoadStatus.DISABLED, name, version)
        if report is not None:
            report(result)
        return result
    if name in loaded_plugins:
        raise PluginContractError("duplicate plugin load")
    if not callable(register):
        raise PluginContractError("register must be callable")

    restricted_context = LifecycleOnlyContext()
    register(restricted_context)
    restricted_context._commit(target_context)
    loaded_plugins.add(name)
    result = PluginLoadResult(PluginLoadStatus.LOADED, name, version)
    if report is not None:
        report(result)
    return result


__all__ = [
    "CONTRACT_VERSION",
    "LifecycleOnlyContext",
    "PLUGIN_NAME",
    "PluginContractError",
    "PluginLoadResult",
    "PluginLoadStatus",
    "load_lifecycle_plugin",
]
