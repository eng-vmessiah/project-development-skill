import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.contracts import (  # noqa: E402
    AgentContract,
    AgentReport,
    ContractValidationError,
    MAX_RETRY_ATTEMPTS,
    RetryPolicy,
)


MIN = {"task_id": "T-10", "agent_id": "a1", "role": "coder"}


def test_contract_defaults_are_default_deny_and_versioned():
    contract = AgentContract.from_dict(MIN)
    assert contract.schema_version == "1"
    assert contract.allowed_paths == []
    assert contract.forbidden_paths == []
    assert contract.retry_policy == RetryPolicy()


def test_contract_round_trip_and_deterministic_json():
    value = {**MIN, "context": {"z": 2, "a": "ok"}, "allowed_paths": ["scripts"], "validation_commands": ["python -m pytest"], "expected_outputs": ["patch"]}
    contract = AgentContract.from_dict(value)
    assert AgentContract.from_json(contract.to_json()).to_dict() == contract.to_dict()
    assert contract.to_json() == AgentContract.from_dict({**value, "context": {"a": "ok", "z": 2}}).to_json()
    assert contract.to_json() == json.dumps(contract.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize("field", ["task_id", "agent_id", "role"])
def test_contract_required_fields(field):
    value = dict(MIN)
    del value[field]
    with pytest.raises(ContractValidationError, match="obrigatório"):
        AgentContract.from_dict(value)


@pytest.mark.parametrize("allowed,forbidden", [(["src/a.py"], ["src/a.py"]), (["src"], ["src/private"]), (["src/*"], ["src"])])
def test_conflicting_paths_are_rejected(allowed, forbidden):
    with pytest.raises(ContractValidationError, match="conflito"):
        AgentContract.from_dict({**MIN, "allowed_paths": allowed, "forbidden_paths": forbidden})


def test_glob_prefix_conflict_is_rejected():
    with pytest.raises(ContractValidationError, match="conflito"):
        AgentContract.from_dict({**MIN, "allowed_paths": ["foo*"], "forbidden_paths": ["foobar"]})


def test_internal_glob_conflict_is_rejected():
    with pytest.raises(ContractValidationError, match="conflito"):
        AgentContract.from_dict({**MIN, "allowed_paths": ["foo/*.py"], "forbidden_paths": ["foo/bar.py"]})


def test_retry_attempts_have_operational_bound():
    assert RetryPolicy(max_attempts=MAX_RETRY_ATTEMPTS).max_attempts == MAX_RETRY_ATTEMPTS
    with pytest.raises(ContractValidationError, match="max_attempts"):
        RetryPolicy.from_dict({"max_attempts": MAX_RETRY_ATTEMPTS + 1})


@pytest.mark.parametrize("payload", [{"api_key": "secret"}, {"credentials": {"token": "x"}}, {"endpoint": "https://example.test"}])
def test_contract_rejects_secrets_and_external_context(payload):
    with pytest.raises(ContractValidationError):
        AgentContract.from_dict({**MIN, "context": payload})


def test_contract_rejects_non_json_safe_values():
    with pytest.raises(ContractValidationError):
        AgentContract.from_dict({**MIN, "context": {"value": object()}})
    with pytest.raises(ContractValidationError):
        AgentContract.from_dict({**MIN, "context": {"value": math.nan}})


def test_report_completed_requires_evidence():
    for evidence in (None, False, 0, " \t", [], {}, [None], {"x": None}, [" \t"], {"x": False}):
        with pytest.raises(ContractValidationError, match="evidence"):
            AgentReport("T-10", "a1", "completed", evidence=evidence)


def test_report_round_trip_and_evidence_gate():
    report = AgentReport("T-10", "a1", "completed", outputs={"artifact": "ok"}, evidence=[{"command": "pytest", "passed": True}], tests=["pytest"], timestamps={"finished_at": "2026-01-01T00:00:00Z"})
    assert AgentReport.from_json(report.to_json()).to_dict() == report.to_dict()
    assert report.to_json() == json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_report_error_is_sanitized_without_secret_leak():
    report = AgentReport("T-10", "a1", "failed", error="Authorization: Bearer super-secret-token; password=hunter2 https://secret.example/x\nTraceback (most recent call last):\n  File \"/home/vitor/private.py\", line 3")
    assert "super-secret-token" not in report.error
    assert "hunter2" not in report.error
    assert "https://" not in report.error
    assert "/home/vitor" not in report.error
    assert "REDACTED" in report.error


@pytest.mark.parametrize("label", ["credential", "access_key", "private_key", "client_secret", "bearer"])
def test_report_error_sanitizes_all_sensitive_assignment_labels(label):
    report = AgentReport("T-10", "a1", "failed", error=f"oops {label}: top-secret-value")
    assert "top-secret-value" not in report.error
    assert "REDACTED" in report.error


def test_report_multiline_traceback_is_one_safe_line_without_exception_or_path():
    report = AgentReport("T-10", "a1", "failed", error="operation failed\nTraceback (most recent call last):\n  File \"/home/vitor/private.py\", line 3\nValueError: password=hunter2")
    assert "\n" not in report.error
    assert "/home/vitor" not in report.error
    assert "ValueError" not in report.error
    assert report.error == "operation failed"


@pytest.mark.parametrize("error", [
    "token top-secret",
    "access_token    top-secret",
    "private_key: top-secret",
    "credential = top-secret",
    "authorization Bearer top-secret",
    "Bearer top-secret",
])
def test_report_error_redacts_whitespace_sensitive_values_and_bearer(error):
    report = AgentReport("T-10", "a1", "failed", error=error)
    assert "top-secret" not in report.error
    assert "REDACTED" in report.error


def test_report_error_drops_urls_file_records_and_source_path_assignments():
    report = AgentReport(
        "T-10", "a1", "failed",
        error="safe message source=/home/user/a.py path=relative.py https://secret.test\nFile \"relative.py\", line 2\nValueError: password=hunter2",
    )
    assert report.error == "safe message [URL REDACTED]"
    assert "/home/user" not in report.error
    assert "relative.py" not in report.error
    assert "ValueError" not in report.error


def test_report_rejects_non_json_safe_payload():
    with pytest.raises(ContractValidationError):
        AgentReport("T-10", "a1", "failed", outputs={"bad": object()})


def test_constructor_and_serialization_are_defensive_and_instance_parse_copies():
    context = {"nested": ["before"]}
    contract = AgentContract("T-10", "a1", "coder", context=context)
    context["nested"].append("after")
    payload = contract.to_dict()
    payload["context"]["nested"].append("mutated")
    assert contract.context == {"nested": ["before"]}
    clone = AgentContract.from_dict(contract)
    assert clone is not contract
    clone.context["nested"].append("clone-only")
    assert "clone-only" not in contract.context["nested"]


def test_report_outputs_are_defensive_and_instance_parse_copies():
    outputs = {"nested": [1]}
    report = AgentReport("T-10", "a1", "failed", outputs=outputs)
    outputs["nested"].append(2)
    payload = report.to_dict()
    payload["outputs"]["nested"].append(3)
    assert report.outputs == {"nested": [1]}
    clone = AgentReport.from_dict(report)
    assert clone is not report
    clone.outputs["nested"].append(4)
    assert report.outputs == {"nested": [1]}
