"""Deterministic provider routing contract tests."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

import pytest
from pd_fleet.provider import CommandMetadata, RuntimePolicy, RuntimeProviderProfile
from pd_fleet.provider_routing import (
    AuditReason, ProviderAuditEvent, ProviderRoutePolicy, RouteStatus,
    RoutingConfigurationError, route_provider,
)


def profile(provider: str, runtime: str, *, enabled: bool = True, auth: bool = True, caps=("read",)):
    return RuntimeProviderProfile(provider, runtime, auth_ref="runtime:test" if auth else None,
        capabilities=caps, command=CommandMetadata("tool"),
        policy=RuntimePolicy(enabled=enabled, allowed_capabilities=caps))


def test_ordered_exact_selection_and_explicit_fallback():
    preferred = profile("one", "r", enabled=False)
    fallback = profile("two", "r")
    no_fallback = route_provider("task-1", "run-1", ProviderRoutePolicy(("one/r",), ("two/r",), ("read",)), (preferred, fallback))
    assert no_fallback.status is RouteStatus.BLOCKED
    yes_fallback = route_provider("task-1", "run-1", ProviderRoutePolicy(("one/r",), ("two/r",), ("read",), True), (preferred, fallback))
    assert yes_fallback.selected is fallback


def test_policy_rejects_duplicates_and_forbidden_capabilities():
    with pytest.raises(RoutingConfigurationError):
        ProviderRoutePolicy(("one/r", "one/r"))
    with pytest.raises(RoutingConfigurationError):
        ProviderRoutePolicy(required_capabilities=("network",))


def test_audit_is_stable_and_redacts_unsafe_identity():
    p = profile("one", "r")
    result = route_provider("task-1", "run-1", ProviderRoutePolicy(("one/r",), required_capabilities=("read",)), (p,))
    assert result.audit.serialize() == result.audit.serialize()
    assert "/" not in result.audit.task_id
    assert "token" not in result.audit.serialize()


def test_unknown_catalog_reference_is_rejected():
    with pytest.raises(RoutingConfigurationError):
        route_provider("task-1", "run-1", ProviderRoutePolicy(("missing/r",)), ())


@pytest.mark.parametrize("field", ["task_id", "run_id"])
@pytest.mark.parametrize("value", ["", "../task", "task/run", "task-token", "secret-run", "A-task"])
def test_audit_identity_is_nonempty_strict_slug_and_non_sensitive(field, value):
    values = {"task_id": "task-1", "run_id": "run-1", field: value}
    with pytest.raises(RoutingConfigurationError, match="invalid audit identity"):
        ProviderAuditEvent(**values, candidates=("one/r",), selected=None,
                           status=RouteStatus.BLOCKED, reason=AuditReason.NO_ELIGIBLE_PROVIDER)


def test_audit_reason_and_selection_are_closed_contracts():
    with pytest.raises(RoutingConfigurationError, match="invalid audit reason"):
        ProviderAuditEvent("task-1", "run-1", ("one/r",), None, RouteStatus.BLOCKED, "because")
    with pytest.raises(RoutingConfigurationError, match="not a candidate"):
        ProviderAuditEvent("task-1", "run-1", ("one/r",), "two/r", RouteStatus.SELECTED,
                           AuditReason.PREFERRED_SELECTED)
    audit = ProviderAuditEvent("task-1", "run-1", (), None, RouteStatus.NO_PROVIDER,
                               AuditReason.NO_PROVIDER_CONFIGURED)
    assert audit.candidates == ()
    with pytest.raises(RoutingConfigurationError, match="cannot be empty"):
        ProviderAuditEvent("task-1", "run-1", (), None, RouteStatus.BLOCKED,
                           AuditReason.NO_ELIGIBLE_PROVIDER)


def test_empty_route_returns_stable_no_provider_audit():
    result = route_provider("task-1", "run-1", ProviderRoutePolicy(), ())

    assert result.status is RouteStatus.NO_PROVIDER
    assert result.selected is None
    assert result.audit.candidates == ()
    assert result.audit.selected is None
    assert result.audit.reason == AuditReason.NO_PROVIDER_CONFIGURED.value


def test_disallowed_fallback_without_preferred_is_blocked_with_fallback_candidates():
    fallback = profile("two", "r")
    result = route_provider(
        "task-1", "run-1",
        ProviderRoutePolicy(fallback_ids=("two/r",)),
        (fallback,),
    )

    assert result.status is RouteStatus.BLOCKED
    assert result.selected is None
    assert result.audit.candidates == ("two/r",)
    assert result.audit.selected is None
    assert result.audit.reason == AuditReason.FALLBACK_NOT_PERMITTED.value


@pytest.mark.parametrize(
    ("status", "reason", "selected"),
    [
        (RouteStatus.SELECTED, AuditReason.PREFERRED_SELECTED, None),
        (RouteStatus.SELECTED, AuditReason.NO_ELIGIBLE_PROVIDER, "one/r"),
        (RouteStatus.BLOCKED, AuditReason.NO_ELIGIBLE_PROVIDER, "one/r"),
        (RouteStatus.BLOCKED, AuditReason.PREFERRED_SELECTED, None),
        (RouteStatus.NO_PROVIDER, AuditReason.NO_ELIGIBLE_PROVIDER, None),
    ],
)
def test_audit_status_reason_and_selection_are_consistent(status, reason, selected):
    with pytest.raises(RoutingConfigurationError):
        ProviderAuditEvent("task-1", "run-1", ("one/r",), selected, status, reason)
