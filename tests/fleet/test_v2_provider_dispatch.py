"""Injected provider dispatch boundary tests; no real process or provider is used."""
from __future__ import annotations

from pathlib import Path
import sys

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
    def __init__(self, profile, result):
        self.name = profile_id = f"{profile.provider_name}/{profile.runtime_name}"
        self.profile = profile
        self.result = result
        self.calls = 0

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
