from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.contracts import (
    AGENT_REPORT_V2_SCHEMA_VERSION,
    AgentReport,
    AgentReportV2,
    ContractValidationError,
    parse_agent_report_v2,
)


def report(**overrides):
    value = {
        "schema_version": AGENT_REPORT_V2_SCHEMA_VERSION,
        "task_id": "T-06", "attempt": 1, "agent_id": "agent-1", "role": "worker",
        "capabilities": ["python"], "status": "completed",
        "outputs": {"result": "ok"}, "evidence": [{"kind": "diff", "digest": "abc"}],
        "tests": [{"name": "unit", "status": "passed"}], "validation": {"status": "passed"},
        "decision": {"decision": "accept"}, "started_at": "2026-07-17T10:00:00Z",
        "completed_at": "2026-07-17T10:01:00Z",
    }
    value.update(overrides)
    return value


def test_agent_report_rejects_unknown_fields_and_incomplete_terminal_states():
    with pytest.raises(ContractValidationError):
        parse_agent_report_v2(report(unexpected="ignored by V1"))
    for field in ("outputs", "evidence", "tests", "validation", "decision", "started_at", "completed_at"):
        broken = report()
        broken.pop(field)
        with pytest.raises(ContractValidationError):
            parse_agent_report_v2(broken)


def test_terminal_statuses_and_identity_are_strict():
    for status in ("pending", "running", "skipped", "bogus"):
        with pytest.raises(ContractValidationError):
            parse_agent_report_v2(report(status=status))
    for attempt in (0, -1, True, 1.0):
        with pytest.raises(ContractValidationError):
            parse_agent_report_v2(report(attempt=attempt))


def test_failed_and_blocked_require_diagnosis():
    for status in ("failed", "blocked"):
        with pytest.raises(ContractValidationError):
            parse_agent_report_v2(report(status=status, outputs={}, evidence=[]))
        parsed = parse_agent_report_v2(report(status=status, reason={"code": "DEPENDENCY"},
                                              evidence=[{"diagnosis": "upstream failed"}], outputs={}))
        assert parsed.status == status


def test_retry_is_bounded_and_nested_fields_are_allowlisted():
    with pytest.raises(ContractValidationError):
        parse_agent_report_v2(report(retry={"max_attempts": 101}))
    with pytest.raises(ContractValidationError):
        parse_agent_report_v2(report(retry={"max_attempts": 2, "surprise": True}))


def test_redaction_json_safety_and_no_aliasing():
    source = report(outputs={"log": "token=secret-value https://example.test/x /home/vitor/private.txt"})
    original = deepcopy(source)
    parsed = parse_agent_report_v2(source)
    source["outputs"]["log"] = "changed"
    source["capabilities"].append("mutated")
    stored = parsed.to_dict()
    assert "secret-value" not in json.dumps(stored)
    assert "example.test" not in json.dumps(stored)
    assert "/home/vitor" not in json.dumps(stored)
    assert parsed.outputs["log"] != "changed"
    assert original["outputs"]["log"] != parsed.outputs["log"]
    assert json.loads(parsed.to_json()) == stored


def test_version_and_v1_compatibility():
    with pytest.raises(ContractValidationError):
        parse_agent_report_v2(report(schema_version="1"))
    legacy = AgentReport.from_dict({"task_id": "t", "agent_id": "a", "status": "running"})
    assert legacy.status == "running"
    assert isinstance(parse_agent_report_v2(report()), AgentReportV2)


def test_direct_v2_construction_is_validated_and_detached():
    value = report()
    parsed = AgentReportV2(
        schema_version=value["schema_version"], task_id=value["task_id"], attempt=1,
        agent_id=value["agent_id"], role=value["role"], capabilities=value["capabilities"],
        status=value["status"], outputs=value["outputs"], evidence=value["evidence"],
        tests=value["tests"], validation=value["validation"], decision=value["decision"],
        started_at=value["started_at"], completed_at=value["completed_at"],
    )
    detached = parsed.outputs
    detached["result"] = "mutated"
    assert parsed.outputs["result"] == "ok"
    for bad in ("2026-02-30T10:00:00Z", "not-a-status"):
        kwargs = dict(value)
        if bad.startswith("2026"):
            kwargs["started_at"] = bad
        else:
            kwargs["status"] = bad
        with pytest.raises(ContractValidationError):
            parse_agent_report_v2(kwargs)


def test_identity_timestamp_retry_and_diagnostics_boundaries():
    with pytest.raises(ContractValidationError):
        parse_agent_report_v2(report(agent="different"))
    with pytest.raises(ContractValidationError):
        parse_agent_report_v2(report(timestamps={"started_at": "2026-07-17T10:02:00Z", "completed_at": "2026-07-17T10:01:00Z"}))
    for backoff in (True, "1", -1, float("nan"), float("inf")):
        with pytest.raises(ContractValidationError):
            parse_agent_report_v2(report(retry={"backoff_seconds": backoff}))
    parsed = parse_agent_report_v2(report(error="Traceback (most recent call last):\n  File '/home/vitor/private.py', line 9\nRuntimeError: token=secret"))
    assert "/home/vitor" not in parsed.to_json()
    assert "private.py" not in parsed.to_json()
    assert "secret" not in parsed.to_json()


def test_direct_constructor_rejects_type_and_retry_errors_as_contract_errors():
    value = report()
    for status in ([], {}, True):
        with pytest.raises(ContractValidationError):
            AgentReportV2(**{**value, "status": status})
    for attempts in (0, 101, True):
        with pytest.raises(ContractValidationError):
            AgentReportV2(**{**value, "retry": {"max_attempts": attempts}})


def test_extensions_roundtrip_and_are_detached():
    extensions = {"vendor": {"nested": ["value"]}}
    parsed = parse_agent_report_v2(report(extensions=extensions))
    extensions["vendor"]["nested"].append("source mutation")
    assert parsed.extensions == {"vendor": {"nested": ["value"]}}
    assert json.loads(parsed.to_json())["extensions"] == parsed.extensions
    reparsed = AgentReportV2.from_json(parsed.to_json())
    assert reparsed.extensions == parsed.extensions


def test_unknown_field_flag_preserves_safe_extensions_but_rejects_sensitive_names():
    parsed = parse_agent_report_v2(report(vendor_field={"url": "https://example.test/x"}), reject_unknown_fields=False)
    assert parsed.extensions == {"vendor_field": {"url": "[URL REDACTED]"}}
    with pytest.raises(ContractValidationError):
        parse_agent_report_v2(report(api_key="must reject"), reject_unknown_fields=False)


def test_direct_constructor_rejects_completed_before_started():
    value = report()
    with pytest.raises(ContractValidationError):
        AgentReportV2(**{**value, "started_at": "2026-07-17T10:02:00Z", "completed_at": "2026-07-17T10:01:00Z"})
