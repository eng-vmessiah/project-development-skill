"""Injected provider dispatch boundary tests; no real process or provider is used."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.provider import CommandMetadata, RuntimePolicy, RuntimeProviderProfile  # noqa: E402
from pd_fleet.provider_routing import ProviderRoutePolicy  # noqa: E402
from pd_fleet.runtime_adapter import RuntimeResult, RuntimeStatus, RuntimeTaskEnvelope  # noqa: E402
from pd_fleet.provider_dispatch import (  # noqa: E402
    DispatchStatus, ProviderDispatchBoundary, ProviderDispatchRequest,
)


def _profile(name: str) -> RuntimeProviderProfile:
    return RuntimeProviderProfile(
        name, "runtime", "env:TEST_KEY", ("read",), CommandMetadata("/tools/tool"),
        policy=RuntimePolicy(enabled=True, allowed_capabilities=("read",)),
    )


class _Adapter:
    def __init__(self, profile, result, capabilities=("read",)):
        self.name = profile_id = f"{profile.provider_name}/{profile.runtime_name}"
        self.profile = profile
        self.result = result
        self._capabilities = tuple(capabilities)
        self.calls = 0

    def capabilities(self):
        return frozenset(self._capabilities)

    def build_argv(self, envelope):
        return ("trusted", envelope.task_id)

    def execute(self, envelope, *, runner):
        self.calls += 1
        return self.result


def test_routes_and_executes_only_selected_adapter():
    profile = _profile("one")
    adapter = _Adapter(profile, RuntimeResult(RuntimeStatus.OK, output="done"))
    result = ProviderDispatchBoundary(
        catalog=(profile,), adapters={"one/runtime": adapter}, runners={"one/runtime": object()},
    ).dispatch(
        RuntimeTaskEnvelope("task", "prompt", profile, ("workspace",), ("read",)),
        ProviderRoutePolicy(preferred_ids=("one/runtime",), required_capabilities=("read",)),
        run_id="run",
    )
    assert result.status is DispatchStatus.OK
    assert result.output == "done"
    assert adapter.calls == 1
    assert result.audit.as_dict()["reason"] == "provider_executed"


def test_request_first_fallback_constructs_envelope_with_selected_profile():
    first, second = _profile("one"), _profile("two")
    object.__setattr__(first, "policy", RuntimePolicy(enabled=False, allowed_capabilities=("read",)))
    adapter = _Adapter(second, RuntimeResult(RuntimeStatus.OK, output="fallback"))
    result = ProviderDispatchBoundary(
        catalog=(first, second), adapters={"two/runtime": adapter}, runners={"two/runtime": object()},
    ).dispatch_request(
        ProviderDispatchRequest("task", "prompt", ("workspace",), ("read",)),
        ProviderRoutePolicy(preferred_ids=("one/runtime",), fallback_ids=("two/runtime",),
                            allow_fallback=True, required_capabilities=("read",)),
        run_id="run",
    )
    assert result.status is DispatchStatus.OK
    assert result.selected == second
    assert adapter.calls == 1


def test_execution_failure_does_not_fallback_to_another_adapter():
    first, second = _profile("one"), _profile("two")
    failing = _Adapter(first, RuntimeResult(RuntimeStatus.FAILED, "sandbox_failed"))
    fallback = _Adapter(second, RuntimeResult(RuntimeStatus.OK, output="must-not-run"))
    result = ProviderDispatchBoundary(
        catalog=(first, second), adapters={"one/runtime": failing, "two/runtime": fallback},
        runners={"one/runtime": object(), "two/runtime": object()},
    ).dispatch(
        RuntimeTaskEnvelope("task", "prompt", first, ("workspace",), ("read",)),
        ProviderRoutePolicy(preferred_ids=("one/runtime", "two/runtime"), required_capabilities=("read",)),
        run_id="run",
    )
    assert result.status is DispatchStatus.FAILED
    assert failing.calls == 1
    assert fallback.calls == 0


def test_runner_exception_metadata_uses_fixed_marker_without_reading_type_name():
    class SecretNameMeta(type):
        accesses = 0

        def __getattribute__(cls, name):
            if name == "__name__":
                type.__setattr__(cls, "accesses", cls.accesses + 1)
                return "SECRET\x00\r\nTYPE"
            return super().__getattribute__(name)

    class HostileError(Exception, metaclass=SecretNameMeta):
        pass

    profile = _profile("one")

    class FailingAdapter(_Adapter):
        def execute(self, envelope, *, runner):
            raise HostileError("secret/control\nvalue")

    adapter = FailingAdapter(profile, RuntimeResult(RuntimeStatus.OK, output="unused"))
    result = ProviderDispatchBoundary(
        catalog=(profile,), adapters={"one/runtime": adapter}, runners={"one/runtime": object()},
    ).dispatch(
        RuntimeTaskEnvelope("task", "prompt", profile, ("workspace",), ("read",)),
        ProviderRoutePolicy(preferred_ids=("one/runtime",), required_capabilities=("read",)),
        run_id="run",
    )

    assert result.status is DispatchStatus.FAILED
    assert result.runtime.metadata["exception"] == "[PROVIDER ERROR]"
    assert HostileError.accesses == 0


def test_effective_adapter_capability_blocks_before_runner_or_execution():
    profile = _profile("one")
    adapter = _Adapter(profile, RuntimeResult(RuntimeStatus.OK, output="must-not-run"), capabilities=())
    result = ProviderDispatchBoundary(
        catalog=(profile,), adapters={"one/runtime": adapter}, runners={"one/runtime": object()},
    ).dispatch_request(
        ProviderDispatchRequest("task", "prompt", ("workspace",), ("read",)),
        ProviderRoutePolicy(preferred_ids=("one/runtime",), required_capabilities=("read",)),
        run_id="run",
    )
    assert result.status is DispatchStatus.BLOCKED
    assert result.runtime is None
    assert result.audit.as_dict()["reason"] == "unsupported_runtime_capability"
    assert adapter.calls == 0


def test_legacy_adapter_without_capability_declaration_is_blocked_not_executed():
    profile = _profile("one")

    class LegacyAdapter:
        name = "one/runtime"
        def __init__(self): self.profile = profile; self.calls = 0
        def build_argv(self, envelope): return ("trusted", envelope.task_id)
        def execute(self, envelope, *, runner): self.calls += 1; return RuntimeResult(RuntimeStatus.OK)

    adapter = LegacyAdapter()
    result = ProviderDispatchBoundary(
        catalog=(profile,), adapters={"one/runtime": adapter}, runners={"one/runtime": object()},
    ).dispatch_request(
        ProviderDispatchRequest("task", "prompt", ("workspace",), ("read",)),
        ProviderRoutePolicy(preferred_ids=("one/runtime",), required_capabilities=("read",)),
        run_id="run",
    )
    assert result.status is DispatchStatus.BLOCKED
    assert result.audit.as_dict()["reason"] == "unsupported_runtime_capability"
    assert adapter.calls == 0


def test_adapter_overclaim_is_blocked_by_effective_profile_policy_before_runner():
    profile = _profile("one")
    adapter = _Adapter(profile, RuntimeResult(RuntimeStatus.OK, output="must-not-run"), capabilities=("read", "write"))
    result = ProviderDispatchBoundary(
        catalog=(profile,), adapters={"one/runtime": adapter}, runners={"one/runtime": object()},
    ).dispatch_request(
        ProviderDispatchRequest("task", "prompt", ("workspace",), ("write",)),
        ProviderRoutePolicy(preferred_ids=("one/runtime",), required_capabilities=("read",)),
        run_id="run",
    )
    assert result.status is DispatchStatus.BLOCKED
    assert result.audit.as_dict()["reason"] == "unsupported_runtime_capability"
    assert adapter.calls == 0


def test_malformed_adapter_capabilities_fail_closed_before_runner_or_execution():
    profile = _profile("one")
    adapter = _Adapter(profile, RuntimeResult(RuntimeStatus.OK, output="must-not-run"))
    adapter.capabilities = lambda: ("read",)  # type: ignore[method-assign]
    boundary = ProviderDispatchBoundary(
        catalog=(profile,), adapters={"one/runtime": adapter}, runners={"one/runtime": object()},
    )
    with pytest.raises(ValueError, match="adapter_capabilities_invalid"):
        boundary.dispatch_request(
            ProviderDispatchRequest("task", "prompt", ("workspace",), ("read",)),
            ProviderRoutePolicy(preferred_ids=("one/runtime",), required_capabilities=("read",)),
            run_id="run",
        )
    assert adapter.calls == 0
