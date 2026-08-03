"""Explicit, injected adapter from Fleet's batch port to Hermes's D1 batch callable.

This module intentionally does not import Hermes or discover a runtime.  The host
callable is supplied by the composition root that owns Hermes lifecycle.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class TuiD1BatchRegistrarAdapter:
    """Expose Fleet's ``register_batch`` port over an injected Hermes callable."""

    def __init__(self, register_plugin_rpc_batch: Callable[..., Any]) -> None:
        if not callable(register_plugin_rpc_batch):
            raise TypeError("register_plugin_rpc_batch must be callable")
        self._register_plugin_rpc_batch = register_plugin_rpc_batch

    def register_batch(self, namespace: str, registrations: Any, *, enabled: bool = False) -> Any:
        """Forward one candidate batch unchanged to the injected host callable."""
        return self._register_plugin_rpc_batch(namespace, registrations, enabled=enabled)


__all__ = ["TuiD1BatchRegistrarAdapter"]
