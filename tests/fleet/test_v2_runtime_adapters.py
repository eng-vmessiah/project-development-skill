"""Named runtime adapter factory tests; no provider executable is invoked."""
from __future__ import annotations

from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.provider import CommandMetadata, RuntimePolicy, RuntimeProviderProfile
from pd_fleet.runtime_adapters import (
    FACTORY_COMMAND_ARGUMENTS_UNSUPPORTED, FACTORY_COMMAND_REQUIRED,
    FACTORY_INVALID_EXECUTABLE, FACTORY_INVALID_MAX_TURNS, FACTORY_INVALID_MODEL,
    FACTORY_PROFILE_MISMATCH,
    FACTORY_UNKNOWN_RUNTIME, RuntimeFactoryError,
    create_runtime_adapter, parse_runtime_output,
)


def profile(runtime: str, provider: str) -> RuntimeProviderProfile:
    return RuntimeProviderProfile(provider, runtime, capabilities=("read",), policy=RuntimePolicy(enabled=True, allowed_capabilities=("read",)))


def test_named_templates_are_exact_and_data_only() -> None:
    cases = [
        ("openai-codex", "hermes", "hermes chat -q inspect --provider openai-codex --model gpt-test", {"model": "gpt-test"}),
        ("codex-cli", "codex-cli", "codex exec inspect", {}),
        ("opencode-go", "opencode", "opencode run inspect --format json", {}),
        ("claude-code", "claude-code", "claude -p inspect --output-format json --max-turns 3", {"max_turns": 3}),
    ]
    for runtime, provider, expected, metadata in cases:
        envelope = __import__("pd_fleet.runtime_adapter", fromlist=["RuntimeTaskEnvelope"]).RuntimeTaskEnvelope("t", "inspect", profile(runtime, provider), ("workspace",), ("read",), metadata=metadata)
        adapter = create_runtime_adapter(runtime, envelope.provider_profile, CommandMetadata("/tools/" + provider))
        assert adapter.build_argv(envelope) == ("/tools/" + provider,) + tuple(expected.split()[1:])


def test_factory_rejects_unknown_mismatch_and_missing_command() -> None:
    with pytest.raises(RuntimeFactoryError) as exc:
        create_runtime_adapter("unknown", profile("unknown", "unknown"), CommandMetadata("/x"))
    assert exc.value.code == FACTORY_UNKNOWN_RUNTIME
    with pytest.raises(RuntimeFactoryError) as exc:
        create_runtime_adapter("openai-codex", profile("openai-codex", "wrong"), CommandMetadata("/x"))
    assert exc.value.code == FACTORY_PROFILE_MISMATCH
    with pytest.raises(RuntimeFactoryError) as exc:
        create_runtime_adapter("codex-cli", profile("codex-cli", "codex-cli"))
    assert exc.value.code == FACTORY_COMMAND_REQUIRED


def test_model_and_turns_are_required_and_validated() -> None:
    from pd_fleet.runtime_adapter import RuntimeTaskEnvelope
    p = profile("openai-codex", "hermes")
    a = create_runtime_adapter("openai-codex", p, CommandMetadata("/hermes"))
    with pytest.raises(RuntimeFactoryError) as exc:
        a.build_argv(RuntimeTaskEnvelope("t", "x", p, ("workspace",), ("read",)))
    assert exc.value.code == FACTORY_INVALID_MODEL
    p = profile("claude-code", "claude-code")
    a = create_runtime_adapter("claude-code", p, CommandMetadata("/claude"))
    with pytest.raises(RuntimeFactoryError) as exc:
        a.build_argv(RuntimeTaskEnvelope("t", "x", p, ("workspace",), ("read",), metadata={"max_turns": 0}))
    assert exc.value.code == FACTORY_INVALID_MAX_TURNS


def test_result_parser_ignores_provider_claimed_status_and_redacts() -> None:
    result = parse_runtime_output('{"status":"error","output":"ok /home/vitor/private"}')
    assert result.status.value == "ok"
    assert result.output == "ok [PATH REDACTED]"


def test_result_parser_fails_closed_without_runner_evidence() -> None:
    for payload in ("", "garbage", "{}", '{"status":"passed"}', '{"output":""}'):
        result = parse_runtime_output(payload)
        assert result.status.value == "failed"
        assert result.error_code == "sandbox_failed"


def test_factory_rejects_unsafe_executable_and_unsupported_arguments() -> None:
    p = profile("codex-cli", "codex-cli")
    for executable in ("relative", "/bin/codex\t"):
        with pytest.raises(RuntimeFactoryError) as exc:
            create_runtime_adapter("codex-cli", p, CommandMetadata(executable))
        assert exc.value.code == FACTORY_INVALID_EXECUTABLE
    for metacharacter in (";", "&", "|", "<", ">", "$", "`"):
        with pytest.raises(RuntimeFactoryError) as exc:
            create_runtime_adapter("codex-cli", p, CommandMetadata(f"/bin/codex{metacharacter}suffix"))
        assert exc.value.code == FACTORY_INVALID_EXECUTABLE
    for control in ("\x01", "\x7f"):
        with pytest.raises(RuntimeFactoryError) as exc:
            create_runtime_adapter("codex-cli", p, CommandMetadata(f"/bin/codex{control}suffix"))
        assert exc.value.code == FACTORY_INVALID_EXECUTABLE
    with pytest.raises(ValueError):
        CommandMetadata("/bin/codex\x00")
    with pytest.raises(RuntimeFactoryError) as exc:
        create_runtime_adapter("codex-cli", p, CommandMetadata("/bin/codex", ("--unsafe",)))
    assert exc.value.code == FACTORY_COMMAND_ARGUMENTS_UNSUPPORTED


def test_runner_error_and_blocked_states_are_preserved() -> None:
    assert parse_runtime_output('{"output":"x"}', runner_status="error").status.value == "error"
    assert parse_runtime_output('{"output":"x"}', runner_status="blocked").status.value == "blocked"
