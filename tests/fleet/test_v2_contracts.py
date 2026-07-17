"""T2-02 executable contracts: canonical identity and reconciliation fail-closed."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.contracts import (  # noqa: E402
    ContractValidationError,
    ReconciliationInput,
    AgentContract,
    AgentReport,
    canonical_json_bytes,
    canonicalize,
    plan_hash,
    reconcile,
)


def test_canonical_json_and_golden_hash_bytes() -> None:
    plan = {"schema_version": "pd-fleet-plan:v2", "name": "café", "tasks": [{"task_id": "T1"}], "timestamp": "2026-01-01T00:00:00Z"}
    expected = '{"name":"café","schema_version":"pd-fleet-plan:v2","tasks":[{"task_id":"T1"}]}' .encode("utf-8")
    assert canonical_json_bytes(plan) == expected
    assert plan_hash(plan) == hashlib.sha256(b"pd-fleet-plan:v2\0" + expected).hexdigest()


def test_aliases_and_mapping_order_are_equivalent() -> None:
    first = {"schema_version": "pd-fleet-plan:v2", "run_id": "r", "tasks": [{"task_id": "a"}], "capabilities": ["z", "a"]}
    second = {"capabilities": ["a", "z"], "tasks": [{"taskId": "a"}], "runId": "r", "schemaVersion": "pd-fleet-plan:v2"}
    assert canonicalize(first) == canonicalize(second)
    assert plan_hash(first) == plan_hash(second)


@pytest.mark.parametrize("plan", [
    {"schemaVersion": "pd-fleet-plan:v2", "unknownField": 1},
    {"schema_version": "pd-fleet-plan:v2", "tasks": [{"taskId": "a", "task_id": "b"}]},
])
def test_aliases_reject_unknown_and_conflicts_at_any_mapping_level(plan) -> None:
    with pytest.raises(ContractValidationError):
        canonicalize(plan)


def test_schema_alias_is_canonical_and_wrong_version_fails_closed() -> None:
    assert canonicalize({"schemaVersion": "pd-fleet-plan:v2", "tasks": []})["schema_version"] == "pd-fleet-plan:v2"
    with pytest.raises(ContractValidationError, match="unsupported schema"):
        canonicalize({"schemaVersion": "1", "tasks": []})


def test_none_is_preserved_but_embedded_paths_are_redacted() -> None:
    result = canonicalize({"schemaVersion": "pd-fleet-plan:v2", "description": "see /home/alice/x and C:\\Users\\bob\\x", "context": None, "tasks": []})
    assert result["context"] is None
    assert "alice" not in json.dumps(result)
    assert "bob" not in json.dumps(result)
    assert "[PATH REDACTED]" in result["description"]


def test_none_list_members_are_preserved() -> None:
    result = canonicalize({"schema_version": "pd-fleet-plan:v2", "tasks": [None, {"value": None}]})
    assert result["tasks"] == [None, {"value": None}]


@pytest.mark.parametrize("path", ["bad\x00name", "https:/host/file", r"http:\\host\file", "file:/tmp/x", "C:relative", "src/./file", "src//file", "src/../file"])
def test_legacy_paths_reject_nul_schemes_drive_relative_and_symlink_risk(path) -> None:
    with pytest.raises(ContractValidationError):
        AgentContract("T", "a", "coder", allowed_paths=[path])


def test_compact_sensitive_assignments_are_redacted_before_hash() -> None:
    one = {"schema_version": "pd-fleet-plan:v2", "description": "password:abc123 api_key=def456", "tasks": []}
    two = {"schema_version": "pd-fleet-plan:v2", "description": "password:xyz999 api_key=other", "tasks": []}
    assert plan_hash(one) == plan_hash(two)
    encoded = canonical_json_bytes(one)
    assert b"abc123" not in encoded and b"def456" not in encoded


@pytest.mark.parametrize("assignment", [
    '{"token":"json-token-unique-7f31"}',
    '{"password": "json-password-unique-8a42"}',
    'api_key: "colon-api-key-unique-9b53"',
    'authorization: "Bearer json-bearer-unique-ac64"',
    'Authorization: Bearer "header-bearer-unique-bd75"',
])
def test_quoted_sensitive_assignments_are_fully_consumed_everywhere(assignment: str) -> None:
    plan = {"schema_version": "pd-fleet-plan:v2", "description": assignment, "tasks": []}
    canonical = canonical_json_bytes(plan)
    alternate = {**plan, "description": assignment.replace("unique", "different")}
    assert b"unique" not in canonical
    assert plan_hash(plan) == plan_hash(alternate)

    with pytest.raises(ContractValidationError) as exc:
        AgentContract("T", "a", "coder", context={"message": assignment})
    assert "unique" not in str(exc.value)

    report = AgentReport("T", "a", "failed", error=assignment)
    assert "unique" not in (report.error or "")


def test_safe_json_text_and_normal_keys_are_not_redacted() -> None:
    safe = '{"normal":"keep-this-unique", "nested": {"value": 3}}'
    result = canonicalize({"schema_version": "pd-fleet-plan:v2", "description": safe, "tasks": []})
    assert result["description"] == safe


@pytest.mark.parametrize("text", [
    r'token: "abc\"secret" trailing',
    'token: "unterminated-secret trailing text',
])
def test_sensitive_quote_scanner_is_escape_aware_and_fail_closed(text: str) -> None:
    result = canonicalize({"schema_version": "pd-fleet-plan:v2", "description": text, "tasks": []})
    assert "secret" not in result["description"]


@pytest.mark.parametrize("assignment", [
    "token: [canonical-unique-bracket-1a2b, other]",
    "token: {canonical-unique-brace-3c4d: x}",
    "token: canonical-unique-close-5e6f]",
    "token: canonical-unique-comment-7g8h # comment",
    "token: |\n  canonical-unique-block-9i0j\nnext: ok",
    "token: >\n  canonical-unique-folded-k1l2\nnext: ok",
])
def test_sensitive_assignment_forms_never_enter_canonical_bytes_or_hash(assignment: str) -> None:
    plan = {"schema_version": "pd-fleet-plan:v2", "description": assignment, "tasks": []}
    encoded = canonical_json_bytes(plan)
    assert b"canonical-unique" not in encoded
    assert "canonical-unique" not in plan_hash(plan)
    if "next: ok" in assignment:
        assert "next: ok" in canonicalize(plan)["description"]


def test_sensitive_assignment_consumes_yaml_comment_but_preserves_ordinary_prose() -> None:
    sensitive = {"schema_version": "pd-fleet-plan:v2", "description": "token: [canonical-unique-comment-xyz, other] # canonical-unique-tail", "tasks": []}
    ordinary = {"schema_version": "pd-fleet-plan:v2", "description": "A token:ization example remains ordinary prose.", "tasks": []}
    assert b"canonical-unique" not in canonical_json_bytes(sensitive)
    assert canonicalize(ordinary)["description"] == ordinary["description"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("header", ["|", ">", "|2", ">2", "|+2", "|-2", ">+2", ">-2"])
def test_block_scalar_scanner_preserves_nested_siblings_and_redacts_content(newline: str, header: str) -> None:
    secret = "nested-secret-unique-7f31"
    text = newline.join((
        "outer:",
        f"  token: {header}",
        f"    {secret}",
        "  keep: value",
        "tail: mapping",
        "",
    ))
    result = canonicalize({"schema_version": "pd-fleet-plan:v2", "description": text, "tasks": []})
    description = result["description"]
    assert secret not in description
    assert "  keep: value" in description
    assert "tail: mapping" in description


def test_block_scalar_hash_changes_when_sibling_changes() -> None:
    prefix = "outer:\n  token: |2\n    secret-value\n"
    one = {"schema_version": "pd-fleet-plan:v2", "description": prefix + "  keep: one\ntail: mapping", "tasks": []}
    two = {"schema_version": "pd-fleet-plan:v2", "description": prefix + "  keep: two\ntail: mapping", "tasks": []}
    assert plan_hash(one) != plan_hash(two)
    assert "  keep: one" in canonicalize(one)["description"]


def test_explicit_block_scalar_indent_underflow_fails_closed_and_preserves_siblings() -> None:
    secret = "underflow-secret-unique-7f31"
    text = "\n".join((
        "outer:", "  token: |9", f"    {secret}",
        "  sibling: keep-me", "tail: keep-me-too",
    ))
    description = canonicalize({"schema_version": "pd-fleet-plan:v2", "description": text, "tasks": []})["description"]
    assert secret not in description
    assert "  sibling: keep-me" in description
    assert "tail: keep-me-too" in description


def test_block_scalar_tab_indented_secret_is_absent_without_losing_siblings() -> None:
    secret = "tab-secret-unique-7f31"
    text = "\n".join((
        "outer:",
        "  token: |",
        f"\t{secret}",
        "  keep: value",
        "tail: mapping",
    ))
    description = canonicalize({"schema_version": "pd-fleet-plan:v2", "description": text, "tasks": []})["description"]
    assert secret not in description
    assert "  keep: value" in description
    assert "tail: mapping" in description


def test_malformed_block_scalar_indicator_redacts_owned_region_and_preserves_sibling() -> None:
    prefix = "outer:\n  token: |oops\n"
    one = {"schema_version": "pd-fleet-plan:v2", "description": prefix + "    keep: one\n    sibling: one\n  tail: mapping", "tasks": []}
    two = {"schema_version": "pd-fleet-plan:v2", "description": prefix + "    keep: one\n    sibling: two\n  tail: mapping", "tasks": []}
    assert plan_hash(one) == plan_hash(two)
    assert "    keep: one" not in canonicalize(one)["description"]
    assert "    sibling: one" not in canonicalize(one)["description"]
    assert "  tail: mapping" in canonicalize(one)["description"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_malformed_block_scalar_consumes_nested_secret_but_preserves_dedented_sibling(newline: str) -> None:
    secret = "malformed-nested-secret-unique-7f31"
    text = newline.join((
        "outer:", "  token: |oops", f"    nested: {secret}",
        "  sibling: keep-me", "tail: keep-me-too", "",
    ))
    description = canonicalize({"schema_version": "pd-fleet-plan:v2", "description": text, "tasks": []})["description"]
    assert secret not in description
    assert "  sibling: keep-me" in description
    assert "tail: keep-me-too" in description


@pytest.mark.parametrize("header", ["|+2", "|-2", ">+2", ">-2"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_block_scalar_indicator_order_redacts_content_and_preserves_sibling(header: str, newline: str) -> None:
    secret = "ordered-indicator-secret-unique-7f31"
    text = newline.join((
        "outer:", f"  token: {header}", f"    nested: {secret}",
        "  sibling: keep-me", "tail: keep-me-too", "",
    ))
    description = canonicalize({"schema_version": "pd-fleet-plan:v2", "description": text, "tasks": []})["description"]
    assert secret not in description
    assert "  sibling: keep-me" in description
    assert "tail: keep-me-too" in description


@pytest.mark.parametrize("text", ["token:ization", "authorization: policy", "bearer: market", "api_key:word"])
def test_sensitive_prose_is_not_a_credential_assignment(text: str) -> None:
    assert canonicalize({"schema_version": "pd-fleet-plan:v2", "description": text, "tasks": []})["description"] == text


@pytest.mark.parametrize("label", ["apiKey", "accessToken", "clientSecret", "privateKey", "apikey", "accesstoken", "clientsecret", "privatekey"])
def test_sensitive_camel_case_and_compact_labels_are_dropped(label: str) -> None:
    result = canonicalize({"schema_version": "pd-fleet-plan:v2", label: "do-not-hash", "tasks": []})
    assert label not in result
    assert b"do-not-hash" not in canonical_json_bytes({"schema_version": "pd-fleet-plan:v2", label: "do-not-hash", "tasks": []})


@pytest.mark.parametrize("path", ["/équipe/秘密/file.py", r"C:\Users\équipe\秘密\file.py", r"\\serveur\équipe\秘密\file.py"])
def test_unicode_absolute_paths_are_redacted_as_a_whole(path: str) -> None:
    result = canonicalize({"schema_version": "pd-fleet-plan:v2", "description": f"failure at {path}", "tasks": []})
    assert "équipe" not in json.dumps(result, ensure_ascii=False)
    assert "秘密" not in json.dumps(result, ensure_ascii=False)
    assert result["description"].count("[PATH REDACTED]") == 1


def test_url_is_redacted_before_path_scanning() -> None:
    report = AgentReport("T", "a", "failed", error="request failed: https://secret.example/private/file")
    assert report.error == "request failed: [URL REDACTED]"
    assert "https:" not in report.error


@pytest.mark.parametrize("factory,value", [(AgentContract, "../../secret/schema"), (AgentReport, "../../secret/status")])
def test_legacy_version_and_status_diagnostics_do_not_echo_values(factory, value: str) -> None:
    if factory is AgentContract:
        with pytest.raises(ContractValidationError) as exc:
            factory("T", "a", "coder", schema_version=value)
    else:
        with pytest.raises(ContractValidationError) as exc:
            factory("T", "a", value, schema_version=value)
    assert value not in str(exc.value)
    assert "repr" not in str(exc.value)


def test_legacy_diagnostics_redact_embedded_absolute_paths() -> None:
    with pytest.raises(ContractValidationError) as exc:
        AgentContract("T", "a", "coder", allowed_paths=["/home/alice/private"])
    assert "/home/alice" not in str(exc.value)
    report = AgentReport("T", "a", "failed", error="failed at /home/alice/private.py")
    assert "/home/alice" not in (report.error or "")


def test_runtime_paths_and_secret_fields_are_excluded_without_leaking() -> None:
    one = {"schema_version": "pd-fleet-plan:v2", "path": "/home/alice/private", "token": "secret-one", "tasks": []}
    two = {"schema_version": "pd-fleet-plan:v2", "path": r"C:\Users\bob\other", "token": "secret-two", "tasks": [], "updated_at": "later"}
    assert plan_hash(one) == plan_hash(two)
    assert b"alice" not in canonical_json_bytes(one)
    assert b"secret" not in canonical_json_bytes(one)


@pytest.mark.parametrize("value", [{"schema_version": "pd-fleet-plan:v2", "unknown": 1}, {"schema_version": "pd-fleet-plan:v2", "x": {"y": 1}}])
def test_unknown_fields_are_rejected(value) -> None:
    with pytest.raises(ContractValidationError, match="unknown field"):
        canonicalize(value)


def test_nan_and_cycles_rejected_with_safe_diagnostics() -> None:
    with pytest.raises(ContractValidationError, match="non-finite"):
        canonicalize({"schema_version": "pd-fleet-plan:v2", "tasks": [math.nan]})
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ContractValidationError, match="cyclic") as exc:
        canonicalize({"schema_version": "pd-fleet-plan:v2", "tasks": cycle})
    assert "/home" not in str(exc.value) and "secret" not in str(exc.value)


def _tokens(**changes) -> ReconciliationInput:
    valid_hash = "a" * 64
    values = dict(expected_plan_hash=valid_hash, actual_plan_hash=valid_hash, expected_generation=2, actual_generation=2,
                  expected_run_id="run", actual_run_id="run", expected_checkpoint=3, actual_checkpoint=3,
                  expected_lease="lease", actual_lease="lease", expected_event_sequence=7, actual_event_sequence=7)
    values.update(changes)
    return ReconciliationInput(**values)


def test_reconciliation_matching_tokens_allows() -> None:
    result = reconcile(_tokens())
    assert result.allowed and not result.blocked and result.errors == ()


def test_reconciliation_both_absent_leases_are_a_valid_match() -> None:
    result = reconcile(_tokens(expected_lease=None, actual_lease=None))
    assert result.allowed


@pytest.mark.parametrize("expected,actual", [(None, "lease"), ("lease", None)])
def test_reconciliation_one_absent_lease_blocks_closed(expected, actual) -> None:
    result = reconcile(_tokens(expected_lease=expected, actual_lease=actual))
    assert result.blocked
    assert any(error.code == "invalid_lease" for error in result.errors)


@pytest.mark.parametrize(("field", "expected"), [
    ("actual_plan_hash", "plan_hash_drift"), ("actual_generation", "generation_drift"),
    ("actual_run_id", "run_drift"), ("actual_checkpoint", "checkpoint_drift"),
    ("actual_lease", "lease_stale"), ("actual_event_sequence", "event_sequence_drift"),
])
def test_reconciliation_drift_blocks_before_claim(field, expected) -> None:
    drift_value = "f" * 64 if field == "actual_plan_hash" else ("different" if "id" in field or field == "actual_lease" else 99)
    result = reconcile(_tokens(**{field: drift_value}))
    assert result.blocked and not result.allowed
    assert [error.code for error in result.errors] == [expected]
    assert all("different" not in error.message and "/" not in error.message for error in result.errors)


@pytest.mark.parametrize("field,value", [
    ("expected_plan_hash", "H" * 64), ("expected_plan_hash", "short"),
    ("expected_generation", True), ("expected_generation", -1),
    ("expected_checkpoint", True), ("expected_event_sequence", -1),
    ("expected_run_id", ""), ("expected_lease", "../unsafe"),
])
def test_reconciliation_invalid_tokens_fail_closed_without_values(field, value) -> None:
    result = reconcile(_tokens(**{field: value}))
    assert result.blocked and not result.allowed
    assert all((not str(value)) or str(value) not in error.message for error in result.errors)
