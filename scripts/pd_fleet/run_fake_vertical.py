"""Standalone local fake-only vertical verification runner."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

try:  # Support both documented direct-script and package/module execution.
    from .fake_adapter import FakeAgentRuntime, SCHEMA_VERSION, canonical_request_fingerprint
except ImportError:  # pragma: no cover - exercised by direct-script invocation.
    from fake_adapter import FakeAgentRuntime, SCHEMA_VERSION, canonical_request_fingerprint


def _request(operation: str, *, lineage: dict[str, Any], key: str, **fields: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "operation": operation,
        "lineage": dict(lineage),
        "owner": "owner-001",
        "expected_generation": 0,
        "idempotency_key": key,
        "request_fingerprint": "",
    }
    request.update(fields)
    request["request_fingerprint"] = canonical_request_fingerprint(request)
    return request


def _event_projection(events: list[dict[str, Any]]) -> list[str]:
    return [str(event["status"]) for event in events]


def _result_refs(*results: Any) -> list[str]:
    refs: list[str] = []
    for result in results:
        values = result if isinstance(result, list) else [result]
        for item in values:
            if not isinstance(item, dict):
                continue
            for key in ("evidence_refs", "payload_ref", "artifact_id", "termination_ref"):
                value = item.get(key)
                if isinstance(value, list):
                    refs.extend(str(ref) for ref in value)
                elif isinstance(value, str):
                    refs.append(value)
    return refs


def _validate(value: Any, validator: Draft202012Validator) -> None:
    errors = list(validator.iter_errors(value))
    if errors:
        raise AssertionError("schema validation failed: " + "; ".join(error.message for error in errors))


def run(repo_root: Path) -> dict[str, Any]:
    schema_dir = repo_root / ".spec" / "pd-fleet-hermes-adapter-v0" / "contracts"
    result_validator = Draft202012Validator(json.loads((schema_dir / "result-schema.json").read_text(encoding="utf-8")))

    runtime = FakeAgentRuntime()
    lineage = {"run_id": "run-001", "task_id": "task-001", "attempt_id": "attempt-001", "session_handle_id": None, "workspace_id": "ws-001"}
    prepare = _request("prepare", lineage=lineage, key="prepare-vertical", workspace={"workspace_id": "ws-001", "root_ref": "test-root-001", "isolation": "dedicated", "cleanup_policy": "always"})
    prepared = runtime.prepare(prepare)
    if prepared["dispatch_count"] != 0:
        raise AssertionError("prepare dispatched")
    active_lineage = dict(prepared["lineage_ref"])
    execute = _request("execute", lineage=active_lineage, key="execute-vertical", input={"goal_ref": "goal-001", "payload": "bounded vertical"})
    executed = runtime.execute(execute)
    observed = runtime.observe({"schema_version": SCHEMA_VERSION, "operation": "observe", "lineage": active_lineage, "cursor": None})
    handoff = runtime.handoff(_request("handoff", lineage=active_lineage, key="handoff-vertical", handoff_reason="verification"))
    cleanup = runtime.cleanup(_request("cleanup", lineage=active_lineage, key="cleanup-vertical", cleanup_reason="verification"))
    for result in (prepared, executed, observed, handoff, cleanup):
        _validate(result, result_validator)

    cancel_runtime = FakeAgentRuntime()
    cancel_prepare = cancel_runtime.prepare(_request("prepare", lineage=lineage, key="prepare-cancel", workspace={"workspace_id": "ws-001", "root_ref": "test-root-001", "isolation": "dedicated", "cleanup_policy": "always"}))
    cancel_lineage = dict(cancel_prepare["lineage_ref"])
    cancelled = cancel_runtime.cancel(_request("cancel", lineage=cancel_lineage, key="cancel-vertical", cancel_reason="operator_requested"), confirm_termination=True)
    cancel_cleanup = cancel_runtime.cleanup(_request("cleanup", lineage=cancel_lineage, key="cleanup-cancel", cleanup_reason="verification"))
    for result in (cancel_prepare, cancelled, cancel_cleanup):
        _validate(result, result_validator)

    retry_runtime = FakeAgentRuntime()
    retry_prepare = retry_runtime.prepare(_request("prepare", lineage=lineage, key="prepare-retry", workspace={"workspace_id": "ws-001", "root_ref": "test-root-001", "isolation": "dedicated", "cleanup_policy": "always"}))
    retry_lineage = dict(retry_prepare["lineage_ref"])
    retry_execution = retry_runtime.execute(_request("execute", lineage=retry_lineage, key="execute-retry", input={"goal_ref": "goal-001", "payload": "bounded retry"}))
    failed_cleanup = retry_runtime.cleanup(_request("cleanup", lineage=retry_lineage, key="cleanup-failed", cleanup_reason="first"), succeed=False)
    successful_cleanup = retry_runtime.cleanup(_request("cleanup", lineage=retry_lineage, key="cleanup-retry", cleanup_reason="second"))
    for result in (retry_prepare, retry_execution, failed_cleanup, successful_cleanup):
        _validate(result, result_validator)

    timeout_runtime = FakeAgentRuntime(outcome="timed_out")
    timeout_prepare = timeout_runtime.prepare(_request("prepare", lineage=lineage, key="prepare-timeout", workspace={"workspace_id": "ws-001", "root_ref": "test-root-001", "isolation": "dedicated", "cleanup_policy": "always"}))
    timeout_lineage = dict(timeout_prepare["lineage_ref"])
    timeout_execution = timeout_runtime.execute(_request("execute", lineage=timeout_lineage, key="execute-timeout", input={"goal_ref": "goal-001", "payload": "bounded timeout"}))
    timeout_cleanup = timeout_runtime.cleanup(_request("cleanup", lineage=timeout_lineage, key="cleanup-timeout", cleanup_reason="verification"))
    for result in (timeout_prepare, timeout_execution, timeout_cleanup):
        _validate(result, result_validator)
    if timeout_execution["status"] != "timed_out" or timeout_cleanup["original_terminal_status"] != "timed_out":
        raise AssertionError("timeout terminal status was not preserved through cleanup")

    report = {
        "schema_version": SCHEMA_VERSION,
        "local_fake_only": True,
        "cases": [
            {"name": "happy_vertical", "lifecycle_statuses": _event_projection(observed), "dispatch_count": runtime.dispatch_count, "cleanup_marker": cleanup["cleanup_marker"], "evidence_refs": _result_refs(prepared, executed, observed, handoff, cleanup)},
            {"name": "confirmed_cancel", "lifecycle_statuses": _event_projection(cancel_runtime.observe({"schema_version": SCHEMA_VERSION, "operation": "observe", "lineage": cancel_lineage, "cursor": None})), "dispatch_count": cancel_runtime.dispatch_count, "cleanup_marker": cancel_cleanup["cleanup_marker"], "cancel_confirmed": cancelled["cancel_confirmed"], "termination_ref": cancelled["termination_ref"], "evidence_refs": _result_refs(cancel_prepare, cancelled, cancel_cleanup)},
            {"name": "cleanup_failure_retry", "lifecycle_statuses": _event_projection(retry_runtime.observe({"schema_version": SCHEMA_VERSION, "operation": "observe", "lineage": retry_lineage, "cursor": None})), "dispatch_count": retry_runtime.dispatch_count, "cleanup_attempts": [failed_cleanup["status"], successful_cleanup["status"]], "cleanup_marker": successful_cleanup["cleanup_marker"], "original_terminal_status": successful_cleanup["original_terminal_status"], "evidence_refs": _result_refs(retry_prepare, retry_execution, failed_cleanup, successful_cleanup)},
            {"name": "timed_out_cleanup", "lifecycle_statuses": _event_projection(timeout_runtime.observe({"schema_version": SCHEMA_VERSION, "operation": "observe", "lineage": timeout_lineage, "cursor": None})), "dispatch_count": timeout_runtime.dispatch_count, "cleanup_marker": timeout_cleanup["cleanup_marker"], "original_terminal_status": timeout_cleanup["original_terminal_status"], "execution_status": timeout_execution["status"], "evidence_refs": _result_refs(timeout_prepare, timeout_execution, timeout_cleanup)},
        ],
        "no_dispatch": {"external_effects": False, "prepare_dispatch_count": prepared["dispatch_count"], "execute_dispatch_count": executed["dispatch_count"], "post_cleanup_dispatch_count": runtime.dispatch_count, "cancel_dispatch_count": cancel_runtime.dispatch_count, "proof": "Only fake execute increments dispatch_count; prepare, observe, handoff, cleanup, and cancel do not dispatch."},
    }
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) >= 8192:
        raise AssertionError("vertical report exceeds 8192 bytes")
    return report


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    print(json.dumps(run(root), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
