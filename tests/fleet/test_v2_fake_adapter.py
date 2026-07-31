"""F1.1 tests for the local-only PD Fleet adapter seam."""
from __future__ import annotations

from pathlib import Path
import ast
import json
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.fake_adapter import FakeAgentRuntime, FakeAdapterError, canonical_request_fingerprint


FP = "sha256:" + "a" * 64


def request(operation: str, *, handle: str | None = None, owner: str = "owner-001", generation: int = 0, key: str | None = None, fingerprint: str | None = None, **extra):
    lineage = {
        "run_id": "run-001",
        "task_id": "task-001",
        "attempt_id": "attempt-001",
        "session_handle_id": handle,
        "workspace_id": "ws-001",
    }
    body = {
        "schema_version": "pd-fleet-hermes-adapter:v0",
        "operation": operation,
        "lineage": lineage,
        "owner": owner,
        "expected_generation": generation,
        "idempotency_key": key or f"{operation}-key",
        "request_fingerprint": fingerprint or "",
    }
    if operation == "observe":
        body = {"schema_version": body["schema_version"], "operation": operation, "lineage": lineage}
    body.update(extra)
    if operation != "observe" and fingerprint is None:
        body["request_fingerprint"] = canonical_request_fingerprint(body)
    return body


def prepare_request(**kwargs):
    workspace = kwargs.pop("workspace", {
        "workspace_id": "ws-001",
        "root_ref": "test-root-001",
        "isolation": "dedicated",
        "cleanup_policy": "always",
    })
    return request("prepare", workspace=workspace, **kwargs)


def prepared(runtime: FakeAgentRuntime):
    result = runtime.prepare(prepare_request())
    assert result["status"] == "ready"
    return result


def test_prepare_is_fake_only_and_execute_produces_bounded_result():
    runtime = FakeAgentRuntime()
    result = prepared(runtime)

    assert result["dispatch_count"] == 0
    handle = result["session_handle_id"]
    lineage = dict(result["lineage_ref"])
    lineage["session_handle_id"] = handle
    executed = runtime.execute(request("execute", handle=handle, input={"goal_ref": "goal-001", "payload": "bounded"}))

    assert executed["status"] == "succeeded"
    assert executed["dispatch_count"] == 1
    assert "output" not in executed
    assert executed["lineage_ref"] == lineage
    assert runtime.dispatch_count == 1


def test_invalid_lineage_and_owner_fail_closed_without_mutation():
    runtime = FakeAgentRuntime()
    result = prepared(runtime)
    before = runtime.snapshot()

    with pytest.raises(FakeAdapterError) as exc:
        runtime.execute(request("execute", handle=result["session_handle_id"], owner="other-owner", input={"goal_ref": "goal-001", "payload": "x"}))
    assert exc.value.code == "owner_mismatch"
    assert runtime.snapshot() == before

    with pytest.raises(FakeAdapterError) as exc:
        runtime.execute(request("execute", handle=result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"}, lineage={**result["lineage_ref"], "task_id": "other-task"}))
    assert exc.value.code == "invalid_lineage"
    assert runtime.snapshot() == before


def test_observe_is_read_only_and_bounded():
    runtime = FakeAgentRuntime()
    result = prepared(runtime)
    before = runtime.snapshot()
    events = runtime.observe(request("observe", handle=result["session_handle_id"], cursor=None, lineage=result["lineage_ref"]))

    assert events
    assert len(events) <= 64
    assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)
    assert runtime.snapshot() == before


def test_cancel_with_different_key_returns_current_terminal_state_without_transition():
    runtime = FakeAgentRuntime()
    prepared_result = prepared(runtime)
    first = runtime.cancel(request("cancel", handle=prepared_result["session_handle_id"], key="cancel-one", cancel_reason="operator_requested"), confirm_termination=True)
    second = runtime.cancel(request("cancel", handle=prepared_result["session_handle_id"], key="cancel-two", cancel_reason="operator_requested"), confirm_termination=True)

    assert second["status"] == "cancelled"
    assert second["cancel_confirmed"] is True
    assert runtime.snapshot()["sequence"] == 4


def test_cancel_requires_fake_termination_confirmation():
    runtime = FakeAgentRuntime()
    result = prepared(runtime)
    cancel = runtime.cancel(request("cancel", handle=result["session_handle_id"], cancel_reason="operator_requested"), confirm_termination=True)

    assert cancel["status"] == "cancelled"
    assert cancel["cancel_confirmed"] is True
    assert cancel["termination_ref"]
    assert runtime.dispatch_count == 0


def test_handoff_is_bounded_and_cleanup_is_orthogonal_and_idempotent():
    runtime = FakeAgentRuntime()
    result = prepared(runtime)
    executed = runtime.execute(request("execute", handle=result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"}))
    handoff = runtime.handoff(request("handoff", handle=result["session_handle_id"], handoff_reason="resume"))

    assert set(handoff) <= {"schema_version", "artifact_id", "artifact_version", "lineage_ref", "status", "next_action", "evidence_refs"}
    cleanup = runtime.cleanup(request("cleanup", handle=result["session_handle_id"], cleanup_reason="done"))
    replay = runtime.cleanup(request("cleanup", handle=result["session_handle_id"], cleanup_reason="done"))
    assert cleanup["cleanup_marker"] == "cleaned"
    assert cleanup["original_terminal_status"] == executed["status"]
    assert replay == cleanup
    assert runtime.snapshot()["status"] == executed["status"]


def test_execute_rejects_before_prepare_and_non_execute_never_dispatches():
    runtime = FakeAgentRuntime()
    with pytest.raises(FakeAdapterError) as exc:
        runtime.execute(request("execute", handle="handle-001", input={"goal_ref": "goal-001", "payload": "x"}))
    assert exc.value.code == "invalid_lineage"
    assert runtime.dispatch_count == 0


def test_fake_module_has_no_external_effect_imports():
    source = Path(__file__).parents[2] / "scripts" / "pd_fleet" / "fake_adapter.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    forbidden = {"subprocess", "socket", "requests", "urllib", "httpx", "discord", "mcp"}
    imports = {node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for _ in [node]}
    imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not imports & forbidden


def test_operation_specific_and_unknown_fields_fail_closed():
    runtime = FakeAgentRuntime()
    for operation, kwargs in (
        ("prepare", {"secret": "nope"}),
        ("execute", {"input": {"goal_ref": "goal-001", "payload": "x"}, "secret": "nope"}),
        ("cancel", {"cancel_reason": "stop", "secret": "nope"}),
        ("handoff", {"handoff_reason": "resume", "secret": "nope"}),
        ("cleanup", {"cleanup_reason": "done", "secret": "nope"}),
    ):
        if operation != "prepare":
            prepared_result = prepared(runtime)
            kwargs["handle"] = prepared_result["session_handle_id"]
            runtime = FakeAgentRuntime()
        before = runtime.snapshot()
        with pytest.raises(FakeAdapterError) as exc:
            getattr(runtime, operation)(prepare_request(**kwargs) if operation == "prepare" else request(operation, **kwargs))
        assert exc.value.code == "unknown_field"
        assert runtime.snapshot() == before


def test_hostile_workspace_and_payload_are_rejected():
    for root_ref in ("/absolute", "../escape", "bad/root", "bad\nroot"):
        runtime = FakeAgentRuntime()
        with pytest.raises(FakeAdapterError):
            runtime.prepare(prepare_request(workspace={"workspace_id": "ws-001", "root_ref": root_ref, "isolation": "dedicated", "cleanup_policy": "always"}))
    runtime = FakeAgentRuntime()
    result = prepared(runtime)
    before = runtime.snapshot()
    with pytest.raises(FakeAdapterError) as exc:
        runtime.execute(request("execute", handle=result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "line\nbreak"}))
    assert exc.value.code == "forbidden_field"
    assert runtime.snapshot() == before


def test_idempotency_conflict_stale_generation_and_handle_fail_closed():
    runtime = FakeAgentRuntime()
    result = prepared(runtime)
    execute = request("execute", handle=result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"})
    runtime.execute(execute)
    with pytest.raises(FakeAdapterError) as exc:
        runtime.execute({**execute, "request_fingerprint": "sha256:" + "b" * 64})
    assert exc.value.code == "idempotency_conflict"
    with pytest.raises(FakeAdapterError) as exc:
        runtime.handoff(request("handoff", handle=result["session_handle_id"], expected_generation=1, handoff_reason="resume"))
    assert exc.value.code == "stale_generation"
    with pytest.raises(FakeAdapterError) as exc:
        runtime.handoff(request("handoff", handle="other-handle", handoff_reason="resume"))
    assert exc.value.code == "stale_handle"


def test_cleanup_failure_preserves_terminal_state_and_can_retry():
    runtime = FakeAgentRuntime()
    result = prepared(runtime)
    runtime.execute(request("execute", handle=result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"}))
    failed = runtime.cleanup(request("cleanup", handle=result["session_handle_id"], cleanup_reason="first", key="cleanup-first"), succeed=False)
    assert failed["error_code"] == "cleanup_failed"
    assert failed["cleanup_marker"] == "not_cleaned"
    assert runtime.snapshot()["status"] == "succeeded"
    retried = runtime.cleanup(request("cleanup", handle=result["session_handle_id"], cleanup_reason="retry", key="cleanup-retry"))
    assert retried["cleanup_marker"] == "cleaned"


def test_terminal_outcomes_do_not_use_cancellation_error():
    for outcome in ("failed", "timed_out"):
        runtime = FakeAgentRuntime(outcome=outcome)
        result = prepared(runtime)
        execution = runtime.execute(request("execute", handle=result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"}))
        assert execution["status"] == outcome
        assert execution["error_code"] != "cancel_not_confirmed"


def test_same_key_same_fingerprint_replays_without_dispatch():
    runtime = FakeAgentRuntime()
    result = prepared(runtime)
    execute = request("execute", handle=result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"})
    first = runtime.execute(execute)
    second = runtime.execute(execute)
    assert second == first
    assert runtime.dispatch_count == 1


def test_request_fingerprint_is_derived_from_redacted_canonical_request():
    from pd_fleet.fake_adapter import canonical_request_fingerprint
    safe = request("execute", handle="handle-001", input={"goal_ref": "goal-001", "payload": "x"})
    with_secret = {**safe, "metadata": {"token": "secret-value"}}
    assert canonical_request_fingerprint(safe) != canonical_request_fingerprint(with_secret)
    assert "secret-value" not in canonical_request_fingerprint(with_secret)


def test_recursive_hostile_values_fail_closed_without_leaking_details():
    runtime = FakeAgentRuntime()
    result = prepared(runtime)
    cyclic = {}
    cyclic["self"] = cyclic
    hostile = request("execute", handle=result["session_handle_id"], fingerprint=FP, input={"goal_ref": "goal-001", "payload": "x"}, metadata=cyclic)
    with pytest.raises(FakeAdapterError) as exc:
        runtime.execute(hostile)
    assert exc.value.code in {"forbidden_field", "input_too_large", "unknown_field"}
    assert "secret" not in str(exc.value)
    assert runtime.dispatch_count == 0


def test_concurrent_same_key_has_one_reservation_and_one_dispatch():
    gate = threading.Event()
    reserved = threading.Event()
    runtime = FakeAgentRuntime(execute_gate=gate, reservation_event=reserved)
    result = prepared(runtime)
    execute = request("execute", handle=result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"})
    first_result = []
    first = threading.Thread(target=lambda: first_result.append(runtime.execute(execute)))
    first.start()
    assert reserved.wait(timeout=1)
    with pytest.raises(FakeAdapterError) as exc:
        runtime.execute(execute)
    assert exc.value.code == "replay_in_progress"
    gate.set()
    first.join(timeout=1)
    assert first_result and first_result[0]["status"] == "succeeded"
    assert runtime.dispatch_count == 1


def test_valid_but_wrong_fingerprint_is_rejected_before_dispatch():
    runtime = FakeAgentRuntime()
    result = prepared(runtime)
    execute = request("execute", handle=result["session_handle_id"], fingerprint=FP, input={"goal_ref": "goal-001", "payload": "x"})
    with pytest.raises(FakeAdapterError) as exc:
        runtime.execute(execute)
    assert exc.value.code == "forbidden_field"
    assert runtime.dispatch_count == 0


def test_confirmed_cancel_wins_against_held_execute():
    gate = threading.Event()
    reserved = threading.Event()
    runtime = FakeAgentRuntime(execute_gate=gate, reservation_event=reserved)
    result = prepared(runtime)
    execute = request("execute", handle=result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"})
    first_result = []
    first_errors = []
    def run_execute():
        try:
            first_result.append(runtime.execute(execute))
        except FakeAdapterError as error:
            first_errors.append(error.code)
    first = threading.Thread(target=run_execute)
    first.start()
    assert reserved.wait(timeout=1)
    cancelled = runtime.cancel(request("cancel", handle=result["session_handle_id"], cancel_reason="operator_requested"), confirm_termination=True)
    assert cancelled["status"] == "cancelled"
    gate.set()
    first.join(timeout=1)
    assert first_errors == ["invalid_transition"]
    assert runtime.snapshot()["status"] == "cancelled"
    assert runtime.dispatch_count == 0


def test_ids_are_bounded_and_generation_rejects_bool():
    long_id = "a" * 129
    with pytest.raises(FakeAdapterError):
        FakeAgentRuntime().prepare(prepare_request(lineage={"run_id": long_id, "task_id": "task-001", "attempt_id": "attempt-001", "session_handle_id": None, "workspace_id": "ws-001"}))
    with pytest.raises(FakeAdapterError):
        FakeAgentRuntime().prepare(prepare_request(generation=True))


def test_prepare_replay_requires_null_session_handle():
    runtime = FakeAgentRuntime()
    prepared_result = prepared(runtime)
    replay = prepare_request(lineage={**prepared_result["lineage_ref"], "session_handle_id": prepared_result["session_handle_id"]})
    with pytest.raises(FakeAdapterError) as exc:
        runtime.prepare(replay)
    assert exc.value.code == "invalid_lineage"


def _run_concurrently(*calls):
    barrier = threading.Barrier(len(calls))
    results = []
    errors = []

    def invoke(call):
        try:
            barrier.wait(timeout=1)
            results.append(call())
        except FakeAdapterError as error:
            errors.append(error.code)

    threads = [threading.Thread(target=invoke, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=1)
    assert all(not thread.is_alive() for thread in threads)
    return results, errors


def test_mutating_operations_have_explicit_store_lock_boundary():
    source = Path(__file__).parents[2] / "scripts" / "pd_fleet" / "fake_adapter.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    runtime = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "FakeAgentRuntime")
    methods = {node.name: node for node in runtime.body if isinstance(node, ast.FunctionDef)}

    for name in ("prepare", "execute", "observe", "cancel", "handoff", "cleanup"):
        assert any(
            isinstance(node, ast.With)
            and any(isinstance(item.context_expr, ast.Attribute) and item.context_expr.attr == "_lock" for item in node.items)
            for node in ast.walk(methods[name])
        ), name


def test_concurrent_same_cancel_is_serialized_and_replays_one_result():
    runtime = FakeAgentRuntime()
    prepared_result = prepared(runtime)
    cancel = request("cancel", handle=prepared_result["session_handle_id"], key="cancel-race", cancel_reason="operator_requested")

    results, errors = _run_concurrently(
        lambda: runtime.cancel(cancel, confirm_termination=True),
        lambda: runtime.cancel(cancel, confirm_termination=True),
    )

    assert len(results) == 2
    assert not errors
    assert results[0] == results[1]
    assert results[0]["status"] == "cancelled"
    assert runtime.snapshot()["sequence"] == 4


def test_concurrent_cleanup_is_serialized_and_preserves_one_terminal_result():
    runtime = FakeAgentRuntime()
    prepared_result = prepared(runtime)
    runtime.execute(request("execute", handle=prepared_result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"}))
    cleanup = request("cleanup", handle=prepared_result["session_handle_id"], key="cleanup-race", cleanup_reason="done")

    results, errors = _run_concurrently(
        lambda: runtime.cleanup(cleanup),
        lambda: runtime.cleanup(cleanup),
    )

    assert len(results) == 2
    assert not errors
    assert results[0] == results[1]
    assert results[0]["cleanup_marker"] == "cleaned"
    assert runtime.snapshot()["status"] == "succeeded"


def test_handoff_and_cleanup_race_preserves_terminal_state_and_cleanup_marker():
    runtime = FakeAgentRuntime()
    prepared_result = prepared(runtime)
    runtime.execute(request("execute", handle=prepared_result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"}))
    handoff = request("handoff", handle=prepared_result["session_handle_id"], key="handoff-race", handoff_reason="resume")
    cleanup = request("cleanup", handle=prepared_result["session_handle_id"], key="cleanup-race", cleanup_reason="done")

    results, errors = _run_concurrently(
        lambda: runtime.handoff(handoff),
        lambda: runtime.cleanup(cleanup),
    )

    assert len(results) == 2
    assert not errors
    assert {result.get("cleanup_marker") for result in results} == {None, "cleaned"}
    assert runtime.snapshot()["status"] == "succeeded"


def test_concurrent_prepare_has_one_record_and_one_ready_result():
    runtime = FakeAgentRuntime()
    requests = [prepare_request(key="prepare-race") for _ in range(2)]

    results, errors = _run_concurrently(
        lambda: runtime.prepare(requests[0]),
        lambda: runtime.prepare(requests[1]),
    )

    assert len(results) == 2
    assert not errors
    assert results[0] == results[1]
    assert runtime.snapshot()["status"] == "ready"
    assert runtime.dispatch_count == 0


def test_every_emitted_result_validates_against_normative_result_schema():
    import json
    from jsonschema import Draft202012Validator

    schema_path = Path(__file__).parents[2] / ".spec" / "pd-fleet-hermes-adapter-v0" / "contracts" / "result-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    runtime = FakeAgentRuntime()
    prepared_result = runtime.prepare(prepare_request())
    execute_request = request("execute", handle=prepared_result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"})
    execution_result = runtime.execute(execute_request)
    observe_result = runtime.observe(request("observe", handle=prepared_result["session_handle_id"], cursor=None, lineage=prepared_result["lineage_ref"]))
    handoff_result = runtime.handoff(request("handoff", handle=prepared_result["session_handle_id"], handoff_reason="resume"))
    cleanup_result = runtime.cleanup(request("cleanup", handle=prepared_result["session_handle_id"], cleanup_reason="done"))
    for emitted in (prepared_result, execution_result, observe_result, handoff_result, cleanup_result):
        errors = sorted(validator.iter_errors(emitted), key=lambda error: list(error.path))
        assert not errors, errors

    cancel_runtime = FakeAgentRuntime()
    cancel_prepared = cancel_runtime.prepare(prepare_request())
    cancel_result = cancel_runtime.cancel(request("cancel", handle=cancel_prepared["session_handle_id"], cancel_reason="operator_requested"), confirm_termination=True)
    errors = sorted(validator.iter_errors(cancel_result), key=lambda error: list(error.path))
    assert not errors, errors
    unconfirmed_runtime = FakeAgentRuntime()
    unconfirmed_prepared = unconfirmed_runtime.prepare(prepare_request())
    unconfirmed = unconfirmed_runtime.cancel(request("cancel", handle=unconfirmed_prepared["session_handle_id"], key="cancel-unconfirmed", cancel_reason="operator_requested"), confirm_termination=False)
    errors = sorted(validator.iter_errors(unconfirmed), key=lambda error: list(error.path))
    assert not errors, errors

    for outcome in ("failed", "timed_out"):
        outcome_runtime = FakeAgentRuntime(outcome=outcome)
        outcome_prepared = outcome_runtime.prepare(prepare_request())
        outcome_result = outcome_runtime.execute(request("execute", handle=outcome_prepared["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"}))
        errors = sorted(validator.iter_errors(outcome_result), key=lambda error: list(error.path))
        assert not errors, errors

    failed_cleanup_runtime = FakeAgentRuntime()
    failed_cleanup_prepared = failed_cleanup_runtime.prepare(prepare_request())
    failed_cleanup_runtime.execute(request("execute", handle=failed_cleanup_prepared["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"}))
    failed_cleanup = failed_cleanup_runtime.cleanup(request("cleanup", handle=failed_cleanup_prepared["session_handle_id"], cleanup_reason="retry"), succeed=False)
    errors = sorted(validator.iter_errors(failed_cleanup), key=lambda error: list(error.path))
    assert not errors, errors


def test_redaction_covers_urls_paths_authorization_bearer_and_credentials_recursively():
    hostile_values = {
        "message": "visit https://example.test/private?token=secret and /home/vitor/private.txt",
        "nested": ["Authorization: Bearer very-secret", "credential=hidden", {"path": r"C:\Users\Vitor\secret.txt"}],
    }
    from pd_fleet.fake_adapter import _redacted

    sanitized = _redacted(hostile_values)
    rendered = json.dumps(sanitized, sort_keys=True)
    for leaked in ("https://example.test", "/home/vitor/private.txt", r"C:\Users\Vitor\secret.txt", "Bearer very-secret", "credential=hidden"):
        assert leaked not in rendered


def test_redaction_covers_private_access_and_client_key_credentials():
    from pd_fleet.fake_adapter import _redacted

    value = _redacted({
        "private_key": "TOPSECRET",
        "access-key": "TOPSECRET",
        "client_key": "TOPSECRET",
        "message": "private_key=TOPSECRET access_key=TOPSECRET client-key=TOPSECRET",
    })
    rendered = json.dumps(value, sort_keys=True)
    assert "TOPSECRET" not in rendered


def test_redaction_covers_unc_paths_and_recursive_cycles():
    from pd_fleet.fake_adapter import _redacted

    for path in (r"\\server\share\secret.txt", r"\\?\UNC\server\share\secret.txt"):
        assert "secret.txt" not in _redacted(path)
    cyclic = {}
    cyclic["self"] = cyclic
    with pytest.raises(FakeAdapterError) as exc:
        canonical_request_fingerprint({"metadata": cyclic})
    assert exc.value.code == "forbidden_field"


def test_redaction_rejects_non_string_and_control_character_mapping_keys():
    for value in ({1: "secret"}, {"bad\nkey": "secret"}):
        with pytest.raises(FakeAdapterError) as exc:
            canonical_request_fingerprint(value)
        assert exc.value.code == "forbidden_field"


def test_workspace_rejects_embedded_parent_marker():
    with pytest.raises(FakeAdapterError) as exc:
        FakeAgentRuntime().prepare(prepare_request(workspace={
            "workspace_id": "ws-001",
            "root_ref": "a..b",
            "isolation": "dedicated",
            "cleanup_policy": "always",
        }))
    assert exc.value.code == "invalid_lineage"


def test_redaction_rejects_deeply_nested_values_with_bounded_error():
    from pd_fleet.fake_adapter import _redacted

    value = "x"
    for _ in range(1000):
        value = [value]
    with pytest.raises(FakeAdapterError) as exc:
        _redacted(value)
    assert exc.value.code == "input_too_large"


def test_observe_accepts_only_canonical_non_negative_event_cursor():
    runtime = FakeAgentRuntime()
    prepared_result = prepared(runtime)
    lineage = prepared_result["lineage_ref"]
    for cursor in ("event--1", "bad-1", "event-x", "event-" + "1" * 129):
        with pytest.raises(FakeAdapterError) as exc:
            runtime.observe(request("observe", handle=prepared_result["session_handle_id"], cursor=cursor, lineage=lineage))
        assert exc.value.code == "invalid_cursor"


def test_execute_rejects_invalid_input_before_fingerprint_traversal():
    runtime = FakeAgentRuntime()
    prepared_result = prepared(runtime)
    oversized_nested = "x"
    for _ in range(1000):
        oversized_nested = [oversized_nested]
    with pytest.raises(FakeAdapterError) as exc:
        runtime.execute(request("execute", handle=prepared_result["session_handle_id"], fingerprint=FP, input={"goal_ref": "goal-001", "payload": "x", "extra": oversized_nested}))
    assert exc.value.code == "unknown_field"
    assert runtime.dispatch_count == 0


def test_handoff_rejects_execute_that_is_already_reserved():
    gate = threading.Event()
    reserved = threading.Event()
    runtime = FakeAgentRuntime(execute_gate=gate, reservation_event=reserved)
    prepared_result = prepared(runtime)
    execute = request("execute", handle=prepared_result["session_handle_id"], input={"goal_ref": "goal-001", "payload": "x"})
    execution_results = []
    execution_errors = []
    thread = threading.Thread(target=lambda: _capture(runtime.execute, execute, execution_results, execution_errors))
    thread.start()
    assert reserved.wait(timeout=1)

    with pytest.raises(FakeAdapterError) as exc:
        runtime.handoff(request("handoff", handle=prepared_result["session_handle_id"], key="handoff-pending", handoff_reason="resume"))
    assert exc.value.code == "replay_in_progress"
    gate.set()
    thread.join(timeout=1)
    assert execution_results and execution_results[0]["status"] == "succeeded"


def _capture(function, request_value, results, errors):
    try:
        results.append(function(request_value))
    except FakeAdapterError as error:
        errors.append(error.code)


def test_terminal_replay_is_retained_as_a_tombstone_after_cleanup():
    runtime = FakeAgentRuntime()
    prepared_result = prepared(runtime)
    execute = request("execute", handle=prepared_result["session_handle_id"], key="terminal-key", input={"goal_ref": "goal-001", "payload": "x"})
    first = runtime.execute(execute)
    runtime.cleanup(request("cleanup", handle=prepared_result["session_handle_id"], cleanup_reason="done"))

    replay = runtime.execute(execute)
    assert replay == first
    assert runtime.snapshot()["tombstone_count"] >= 1
    with pytest.raises(FakeAdapterError) as exc:
        runtime.execute({**execute, "input": {"goal_ref": "goal-001", "payload": "different"}, "request_fingerprint": "sha256:" + "b" * 64})
    assert exc.value.code == "idempotency_conflict"
