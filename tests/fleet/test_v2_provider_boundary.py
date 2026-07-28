"""T2-08: provider boundary is a future protocol, disabled by default."""
from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.provider import (  # noqa: E402
    DisabledProvider,
    ProviderAdapter,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderDisabledError,
    ProviderPolicy,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
    create_provider,
)


def test_factory_default_is_disabled_and_auditable() -> None:
    provider = create_provider()
    assert isinstance(provider, DisabledProvider)
    assert provider.name == "disabled"
    assert provider.audit_reason == "external providers disabled by policy"
    with pytest.raises(ProviderDisabledError, match="provider disabled"):
        provider.invoke(ProviderRequest(role="coder", capabilities=()))


def test_protocol_and_request_response_are_structured_and_versioned() -> None:
    assert isinstance(DisabledProvider(), ProviderAdapter)
    request = ProviderRequest(role="reviewer", capabilities=("read",), owner="team-a")
    assert request.version == "pd-provider:v1"
    assert request.role == "reviewer"
    assert request.capabilities == ("read",)
    assert request.owner == "team-a"
    with pytest.raises((TypeError, AttributeError)):
        request.capabilities += ("write",)


def test_capability_mismatch_is_rejected_without_provider_construction() -> None:
    policy = ProviderPolicy(allowed_provider_names=("disabled",), capabilities=("read",))
    with pytest.raises(ProviderCapabilityError, match="capability mismatch"):
        create_provider(required_capabilities=("network",), policy=policy)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"credentials": {"token": "secret-value"}},
        {"network": {"url": "https://provider.invalid"}},
        {"metadata": {"callback": lambda: None}},
    ],
)
def test_credential_network_and_callable_injection_rejected(kwargs) -> None:
    with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
        create_provider(**kwargs)


def test_external_provider_name_is_never_constructible_even_when_allowlisted() -> None:
    policy = ProviderPolicy(allowed_provider_names=("acme",))
    with pytest.raises(ProviderConfigurationError, match="external provider disabled"):
        create_provider(provider_name="acme", policy=policy)


def test_policy_and_metadata_are_defensively_copied_and_redacted() -> None:
    metadata = {"owner": "team-a", "token": "do-not-store", "path": "/home/alice/private"}
    original = copy.deepcopy(metadata)
    provider = create_provider(metadata=metadata)
    metadata["owner"] = "mutated"
    assert provider.metadata["owner"] == "team-a"
    assert provider.metadata["token"] == "[REDACTED]"
    assert "alice" not in str(provider.metadata)
    assert metadata == {**original, "owner": "mutated"}
    with pytest.raises(TypeError):
        provider.metadata["new"] = "value"


@pytest.mark.parametrize("path", [r"\\server\alice\secret.txt", "~/alice/secret"])
def test_provider_redacts_unc_and_tilde_paths_as_a_whole(path: str) -> None:
    provider = create_provider(metadata={"path": path})
    redacted = provider.metadata["path"]
    assert redacted == "[PATH REDACTED]"
    assert "alice" not in str(provider.metadata)


@pytest.mark.parametrize(
    "metadata",
    [
        {"owner": "token" + "=LEAKVALUE"},
        {"owner": "password" + ": LEAKVALUE"},
        {"owner": "Authorization" + ": Bearer " + "LEAKVALUE"},
        {"owner": "api_key" + "=LEAKVALUE"},
        {"owner": "token" + '=\"LEAKVALUE\"'},
        {"owner": "password" + ":\\n  LEAKVALUE"},
        {"nested": {"label": "token" + "=LEAKVALUE"}},
        {"items": ["api_key" + "='LEAKVALUE'"]},
    ],
)
def test_metadata_rejects_secret_assignments_before_storage(metadata) -> None:
    with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
        create_provider(metadata=metadata)


def test_metadata_preserves_inert_text_while_redacting_urls_and_paths() -> None:
    provider = create_provider(
        metadata={
            "owner": "tokenization is ordinary text",
            "description": "see https://provider.invalid/docs",
            "path_info": "/home/alice/private",
        }
    )
    assert provider.metadata["owner"] == "tokenization is ordinary text"
    assert provider.metadata["description"] == "see [URL REDACTED]"
    assert provider.metadata["path_info"] == "[PATH REDACTED]"


def test_provider_module_has_no_external_execution_or_dynamic_loading_imports() -> None:
    tree = ast.parse(Path(__file__).parents[2].joinpath("scripts/pd_fleet/provider.py").read_text())
    forbidden = {"socket", "subprocess", "importlib", "requests", "httpx", "urllib"}
    imports = {
        node.names[0].name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
    }
    imports |= {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not imports & forbidden
    assert not any(isinstance(node, ast.Call) and getattr(node.func, "id", None) in {"eval", "exec"} for node in ast.walk(tree))


@pytest.mark.parametrize("payload", [[], (), "not-a-mapping"])
def test_request_payload_is_mapping_only(payload) -> None:
    with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
        ProviderRequest(role="coder", payload=payload)


@pytest.mark.parametrize("value", ["disabled", b"disabled", [1], ("disabled", 1)])
def test_policy_sequences_reject_string_bytes_and_bad_members(value) -> None:
    with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
        ProviderPolicy(allowed_provider_names=value)


def test_response_contract_is_strict_and_audit_reason_is_canonical() -> None:
    response = ProviderResponse(
        status=ProviderStatus.DISABLED,
        provider_name="disabled",
        audit_reason="external providers disabled by policy",
        metadata={"token": "secret"},
    )
    assert response.status is ProviderStatus.DISABLED
    assert response.metadata["token"] == "[REDACTED]"
    for kwargs in (
        {"status": "unknown", "provider_name": "disabled", "audit_reason": response.audit_reason},
        {"status": "disabled", "provider_name": "", "audit_reason": response.audit_reason},
        {"status": "disabled", "provider_name": "disabled", "audit_reason": "https://secret.invalid"},
        {"status": "disabled", "provider_name": "disabled", "audit_reason": response.audit_reason, "metadata": []},
    ):
        with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
            ProviderResponse(**kwargs)


def test_factory_wrong_policy_is_stable_configuration_error() -> None:
    with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
        create_provider(policy=object())
    with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
        create_provider(metadata=[])


@pytest.mark.parametrize("bad_key", [lambda: None, object(), 7])
def test_mapping_keys_are_exact_strings_before_boundary_processing(bad_key) -> None:
    payload = {"nested": {bad_key: "value"}}
    with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
        ProviderRequest(role="coder", payload=payload)
    with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
        ProviderResponse(
            status=ProviderStatus.DISABLED,
            provider_name="disabled",
            audit_reason="external providers disabled by policy",
            metadata=payload,
        )


def test_disabled_provider_direct_construction_cannot_impersonate_another_name() -> None:
    for name in ("acme", ""):
        with pytest.raises(ProviderConfigurationError, match="configuration rejected"):
            DisabledProvider(name=name)
