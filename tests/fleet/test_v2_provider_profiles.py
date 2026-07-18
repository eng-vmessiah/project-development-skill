"""Pure contract tests for runtime profiles and readiness."""
from __future__ import annotations

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.provider import (  # noqa: E402
    CommandMetadata,
    ProviderConfigurationError,
    ReadinessStatus,
    RuntimePolicy,
    RuntimeProviderProfile,
    RuntimeReadiness,
    assess_readiness,
    default_runtime_profiles,
)


def test_initial_runtime_catalog_is_metadata_only_and_disabled() -> None:
    profiles = default_runtime_profiles()
    assert [(p.provider_name, p.runtime_name) for p in profiles] == [
        ("hermes", "openai-codex"),
        ("codex-cli", "codex-cli"),
        ("opencode", "opencode-go"),
        ("claude-code", "claude-code"),
    ]
    assert all(p.auth_ref is None and p.command is None for p in profiles)
    assert all(assess_readiness(p).status is ReadinessStatus.BLOCKED for p in profiles)


def test_profile_keeps_auth_as_opaque_reference_and_serializes_redacted_deterministically() -> None:
    profile = RuntimeProviderProfile(
        provider_name="hermes",
        runtime_name="openai-codex",
        auth_ref="env:OPENAI_API_KEY",
        capabilities=("write", "read"),
        command=CommandMetadata("codex", ("--model", "gpt"), working_directory="/home/vitor/work"),
        policy=RuntimePolicy(enabled=True, allowed_capabilities=("read", "write")),
        metadata={"owner": "team-a", "token": "secret", "path": "/home/vitor/private"},
    )
    encoded = profile.serialize()
    assert encoded == profile.serialize()
    data = json.loads(encoded)
    assert data["auth_ref"] == "[AUTH REF]"
    assert "OPENAI_API_KEY" not in encoded
    assert "vitor" not in encoded
    assert data["metadata"]["token"] == "[REDACTED]"
    assert data["command"]["working_directory"] == "[PATH REDACTED]"
    assert list(data) == sorted(data)


def test_readiness_is_declarative_and_enforces_policy_and_auth_reference() -> None:
    base = dict(
        provider_name="opencode",
        runtime_name="opencode-go",
        auth_ref="runtime:default",
        command=CommandMetadata("opencode"),
        capabilities=("read",),
    )
    assert assess_readiness(
        RuntimeProviderProfile(**base, policy=RuntimePolicy(enabled=True, allowed_capabilities=("read",)))
    ).status is ReadinessStatus.READY
    assert assess_readiness(
        RuntimeProviderProfile(**base, policy=RuntimePolicy(enabled=False, allowed_capabilities=("read",)))
    ).status is ReadinessStatus.BLOCKED
    assert assess_readiness(
        RuntimeProviderProfile(**base, policy=RuntimePolicy(enabled=True))
    ).status is ReadinessStatus.BLOCKED
    no_auth = RuntimeProviderProfile(
        provider_name="opencode", runtime_name="opencode-go",
        command=CommandMetadata("opencode"), policy=RuntimePolicy(enabled=True)
    )
    assert assess_readiness(no_auth).status is ReadinessStatus.NOT_READY


def test_claude_nested_subagents_are_denied_by_default() -> None:
    profile = RuntimeProviderProfile(
        provider_name="claude-code", runtime_name="claude-code", auth_ref="runtime:claude",
        command=CommandMetadata("claude"), policy=RuntimePolicy(enabled=True)
    )
    assert assess_readiness(profile).status is ReadinessStatus.BLOCKED
    assert "nested subagents" in assess_readiness(profile).reason


@pytest.mark.parametrize("bad", ["token\nvalue", "", 42, "sk-live-secret", "https://auth.example/key", "/tmp/secret"])
def test_auth_ref_is_not_a_credential_value_or_command_injection_surface(bad) -> None:
    with pytest.raises(ProviderConfigurationError):
        RuntimeProviderProfile(provider_name="x", runtime_name="x", auth_ref=bad)



def test_runtime_capabilities_are_allowlisted_and_command_view_is_redacted_immutable() -> None:
    with pytest.raises(ProviderConfigurationError):
        RuntimeProviderProfile(provider_name="x", runtime_name="x", capabilities=("future-power",))
    profile = RuntimeProviderProfile(
        provider_name="x", runtime_name="x", auth_ref="runtime:default",
        command=CommandMetadata("/opt/private/tool", ("https://secret.example/x",)),
    )
    view = profile.command_metadata
    assert view is not None
    assert view["executable"] == "[PATH REDACTED]"
    assert view["arguments"] == ("[URL REDACTED]",)
    with pytest.raises(TypeError):
        view["transport"] = "remote"  # type: ignore[index]


@pytest.mark.parametrize("conflict", ["write", "execute", "shell", "network", "nested_agents"])
def test_provider_network_profile_capability_cannot_be_combined_with_conflicting_capability(conflict: str) -> None:
    with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
        RuntimeProviderProfile(
            provider_name="x", runtime_name="x",
            capabilities=("provider_network", conflict),
        )


@pytest.mark.parametrize("conflict", ["write", "execute", "shell", "network", "nested_agents"])
def test_provider_network_policy_cannot_allow_conflicting_capability(conflict: str) -> None:
    with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
        RuntimePolicy(
            enabled=True,
            allow_provider_network=True,
            allowed_capabilities=("provider_network", conflict),
        )


def test_provider_network_profile_can_only_be_ready_with_safe_policy() -> None:
    profile = RuntimeProviderProfile(
        provider_name="x", runtime_name="x", auth_ref="runtime:default",
        capabilities=("provider_network",), command=CommandMetadata("tool"),
        policy=RuntimePolicy(
            enabled=True, allow_provider_network=True,
            allowed_capabilities=("provider_network",),
        ),
    )
    assert assess_readiness(profile).status is ReadinessStatus.READY


def test_readiness_is_derived_and_copy_safe() -> None:
    profile = RuntimeProviderProfile(
        provider_name="x", runtime_name="x", auth_ref="runtime:default",
        command=CommandMetadata("tool"),
        policy=RuntimePolicy(enabled=True),
        readiness=RuntimeReadiness(ReadinessStatus.ERROR, "stale"),
    )
    assert profile.readiness_status is ReadinessStatus.READY
    assert copy.copy(profile) is profile
    assert copy.deepcopy(profile) is profile
    assert "runtime:default" not in repr(profile)


def test_claude_nested_gate_requires_provider_and_runtime_identity() -> None:
    profile = RuntimeProviderProfile(
        provider_name="other", runtime_name="claude-code", auth_ref="runtime:default",
        command=CommandMetadata("claude"), policy=RuntimePolicy(enabled=True),
    )
    assert assess_readiness(profile).status is ReadinessStatus.READY


def test_command_arguments_reject_all_control_characters() -> None:
    with pytest.raises(ProviderConfigurationError):
        CommandMetadata("tool", ("--model\tunsafe",))


@pytest.mark.parametrize(
    "field,bad",
    [
        ("provider_name", "https://evil.example/provider"),
        ("runtime_name", "/home/vitor/runtime"),
        ("provider_name", "api-key"),
        ("runtime_name", "runtime\\nunsafe"),
        ("provider_name", "UpperCase"),
        ("runtime_name", "../runtime"),
    ],
)
def test_runtime_identities_are_safe_lowercase_slugs(field: str, bad: str) -> None:
    values = {"provider_name": "safe", "runtime_name": "safe"}
    values[field] = bad
    with pytest.raises(ProviderConfigurationError):
        RuntimeProviderProfile(**values)


def test_profile_command_property_never_exposes_raw_command_metadata() -> None:
    profile = RuntimeProviderProfile(
        provider_name="safe", runtime_name="safe",
        command=CommandMetadata("private-tool", ("--secret-value", "https://secret.example/x")),
    )
    assert profile.command is not None
    assert profile.command["executable"] == "[EXECUTABLE REDACTED]"
    assert profile.command["arguments"] == ("[ARGUMENT REDACTED]", "[URL REDACTED]")
    assert "private-tool" not in repr(profile)
    assert "--secret-value" not in profile.serialize()
    with pytest.raises(TypeError):
        profile.command["executable"] = "private-tool"  # type: ignore[index]


def test_command_metadata_public_accessors_are_redacted_and_immutable() -> None:
    command = CommandMetadata(
        "/private/bin/provider",
        ("--api-key=super-secret", "--workspace", "/home/vitor/private"),
        working_directory="C:\\Users\\vitor\\workspace",
    )
    view = command.as_dict()
    assert view["executable"] == "[EXECUTABLE REDACTED]"
    assert view["arguments"] == (
        "[ARGUMENT REDACTED]",
        "[ARGUMENT REDACTED]",
        "[ARGUMENT REDACTED]",
    )
    assert view["working_directory"] == "[PATH REDACTED]"
    assert "/private/bin/provider" not in repr(command)
    assert "super-secret" not in repr(command)
    assert "/home/vitor/private" not in repr(command)
    with pytest.raises(TypeError):
        view["executable"] = "provider"  # type: ignore[index]
    with pytest.raises(TypeError):
        view["arguments"][0] = "provider"  # type: ignore[index]


def test_runtime_readiness_repr_does_not_disclose_free_form_diagnostics() -> None:
    readiness = RuntimeReadiness(
        ReadinessStatus.ERROR,
        reason="token=super-secret at /home/vitor/private",
        checked_by="https://internal.example/check?token=secret",
    )
    rendered = repr(readiness)
    assert "super-secret" not in rendered
    assert "/home/vitor/private" not in rendered
    assert "internal.example" not in rendered
    assert rendered == "RuntimeReadiness(status='error')"


def test_profile_contract_has_no_execution_or_environment_discovery_imports() -> None:
    tree = ast.parse(Path(__file__).parents[2].joinpath("scripts/pd_fleet/provider.py").read_text())
    forbidden = {"socket", "subprocess", "importlib", "requests", "httpx", "urllib", "os", "pathlib"}
    imports = {
        node.names[0].name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, ast.Import)
    }
    imports |= {
        node.module.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not imports & forbidden
    assert not any(
        isinstance(node, ast.Call) and getattr(node.func, "id", None) in {"eval", "exec"}
        for node in ast.walk(tree)
    )
