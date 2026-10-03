"""Opt-in, lifecycle-only PD Fleet adapter plugin.

This package intentionally has no Hermes imports. The host owns the context,
configuration gate, identity, transport and all external-effect policy.
"""
from __future__ import annotations


def _on_session_start(**_kwargs):
    """Reserved lifecycle callback; observation is not enabled in this slice."""
    return None


def _on_session_end(**_kwargs):
    """Reserved lifecycle callback; cleanup is host-owned in later slices."""
    return None


def register(ctx) -> None:
    """Register only the lifecycle hooks approved for the first plugin slice."""
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
