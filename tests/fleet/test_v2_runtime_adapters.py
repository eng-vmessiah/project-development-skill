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
        ("openai-codex", "hermes", "hermes chat -q inspect --provider openai-codex --model gpt-test -Q --safe-mode --ignore-rules --max-turns 1", {"model": "gpt-test"}),
        ("codex-cli", "codex-cli", "codex exec --json --ephemeral --sandbox read-only --skip-git-repo-check inspect", {}),
        ("opencode-go", "opencode", "opencode run --format json --pure inspect", {}),
        ("claude-code", "claude-code", "claude -p inspect --output-format json --no-session-persistence --tools '' --max-budget-usd 0.10", {}),
    ]
    for runtime, provider, expected, metadata in cases:
        envelope = __import__("pd_fleet.runtime_adapter", fromlist=["RuntimeTaskEnvelope"]).RuntimeTaskEnvelope("t", "inspect", profile(runtime, provider), ("workspace",), ("read",), metadata=metadata)
        adapter = create_runtime_adapter(runtime, envelope.provider_profile, CommandMetadata("/tools/" + provider))
        parts = tuple("" if part == "''" else part for part in expected.split()[1:])
        assert adapter.build_argv(envelope) == ("/tools/" + provider,) + parts


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
    # Claude's bounded smoke command uses a fixed budget, not a caller-
    # supplied turn count.


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


def test_result_parser_collects_jsonl_results_and_ignores_events() -> None:
    payload = '\n'.join((
        '{"type":"tool_use","status":"running","content":""}',
        '{"type":"assistant","text":"first"}',
        '{"event":"done","output":"second"}',
    ))
    result = parse_runtime_output(payload)
    assert result.status.value == "ok"
    assert result.output == "first\nsecond"


def test_result_parser_collects_codex_item_completed_agent_message() -> None:
    payload = "\n".join((
        '{"type":"thread.started","thread_id":"t"}',
        '{"type":"turn.started"}',
        '{"type":"item.completed","item":{"type":"agent_message","content":[{"type":"output_text","text":"final"}]}}',
        '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}',
    ))
    result = parse_runtime_output(payload)
    assert result.status.value == "ok"
    assert result.output == "final"


def test_result_parser_tool_or_usage_events_without_message_fail() -> None:
    payload = "\n".join((
        '{"type":"thread.started"}',
        '{"type":"item.completed","item":{"type":"function_call","text":"not output"}}',
        '{"type":"item.completed","item":{"type":"tool_result","content":"not output"}}',
        '{"type":"turn.completed","usage":{"output_tokens":99},"status":"completed"}',
    ))
    result = parse_runtime_output(payload)
    assert result.status.value == "failed"
    assert result.error_code == "sandbox_failed"


def test_plain_text_is_opt_in_for_hermes_only() -> None:
    assert parse_runtime_output("final answer", allow_plain_text=True).status.value == "ok"
    assert parse_runtime_output("final answer").status.value == "failed"


def test_result_parser_rejects_oversized_text_and_bytes_before_parsing() -> None:
    oversized_text = "x" * (64 * 1024 + 1)
    for payload in (oversized_text, oversized_text.encode("utf-8")):
        result = parse_runtime_output(payload, allow_plain_text=True)
        assert result.status.value == "failed"
        assert result.error_code == "sandbox_failed"


def test_result_parser_rejects_oversized_jsonl_combined_result() -> None:
    payload = "\n".join('{"output":"' + ("x" * 20000) + '"}' for _ in range(4))
    result = parse_runtime_output(payload)
    assert result.status.value == "failed"
    assert result.error_code == "sandbox_failed"
