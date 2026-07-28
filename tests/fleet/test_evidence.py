import sys
from hashlib import sha256
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.evidence import EvidenceError, EvidenceRecord, EvidenceStore, EvidenceValidationError

NOW = "2026-01-01T00:00:00Z"


def test_capture_success_and_sanitization(tmp_path):
    artifact = tmp_path / "report.txt"
    artifact.write_text("fresh", encoding="utf-8")
    store = EvidenceStore([tmp_path], clock=lambda: NOW)
    record = store.capture(
        "pytest -q",
        executor=lambda command: (0, "password=hunter2 https://example.test\nPASS", ""),
        artifacts=["report.txt"],
        sha256=sha256(b"fresh").hexdigest(),
        provenance="pytest",
    )
    assert record.exit_code == 0
    assert "hunter2" not in record.stdout
    assert "https://" not in record.stdout
    assert store.to_dict()[0]["artifacts"] == ["report.txt"]


def test_capture_is_fail_closed_without_injected_executor():
    with pytest.raises(EvidenceError, match="executor"):
        EvidenceStore().capture("pytest", provenance="pytest")


def test_failed_command_is_rejected(tmp_path):
    with pytest.raises(EvidenceValidationError, match="exit_code"):
        EvidenceStore([tmp_path]).capture("pytest", executor=lambda command: (1, "", "failed"), provenance="pytest")


def test_path_traversal_and_missing_artifact_are_rejected(tmp_path):
    with pytest.raises(EvidenceValidationError, match="inseguro"):
        EvidenceRecord(command="pytest", exit_code=0, artifacts=["../secret"], source="test", provenance="pytest", verified_at=NOW)
    with pytest.raises(EvidenceValidationError, match="ausente"):
        EvidenceStore([tmp_path], clock=lambda: NOW).add(EvidenceRecord(command="pytest", exit_code=0, artifacts=["missing"], source="test", provenance="pytest", verified_at=NOW))


def test_hash_mismatch_is_rejected(tmp_path):
    (tmp_path / "out.txt").write_text("actual", encoding="utf-8")
    record = EvidenceRecord(command="pytest", exit_code=0, artifacts=["out.txt"], sha256="0" * 64, source="test", provenance="pytest", verified_at=NOW)
    with pytest.raises(EvidenceValidationError, match="hash mismatch"):
        EvidenceStore([tmp_path], clock=lambda: NOW).add(record)


def test_declarative_empty_evidence_and_secret_metadata_are_rejected():
    with pytest.raises(EvidenceValidationError, match="comando ou artefato"):
        EvidenceRecord(source="test", provenance="pytest", verified_at=NOW)
    with pytest.raises(EvidenceValidationError, match="segredo"):
        EvidenceRecord(command="token=topsecret", exit_code=0, source="test", provenance="pytest", verified_at=NOW)
    with pytest.raises(EvidenceValidationError, match="URL"):
        EvidenceRecord(command="curl https://example.test", exit_code=0, source="test", provenance="pytest", verified_at=NOW)


@pytest.mark.parametrize("bad", ["token=topsecret", "pytest https://secret.example/x"])
def test_capture_rejects_unsafe_command_before_executor(bad):
    called = False

    def executor(_command):
        nonlocal called
        called = True
        return (0, "", "")

    with pytest.raises(EvidenceValidationError) as exc:
        EvidenceStore().capture(bad, executor=executor)
    assert not called
    assert "topsecret" not in str(exc.value)
    assert "secret.example" not in str(exc.value)


def test_capture_rejects_unsafe_source_before_executor():
    called = False

    def executor(_command):
        nonlocal called
        called = True
        return (0, "", "")

    with pytest.raises(EvidenceValidationError) as exc:
        EvidenceStore().capture("pytest", source="api_key='dont-leak'", executor=executor)
    assert not called
    assert "dont-leak" not in str(exc.value)


def test_executor_exception_is_sanitized():
    def executor(_command):
        raise RuntimeError("password=hunter2 https://private.example")

    with pytest.raises(EvidenceError) as exc:
        EvidenceStore().capture("pytest", executor=executor, provenance="pytest")
    assert str(exc.value) == "executor falhou"
    assert "hunter2" not in str(exc.value)
    assert "private.example" not in str(exc.value)


def test_hash_mapping_is_normalized_and_detached():
    hashes = {"b.txt": "B" * 64, "a.txt": "A" * 64}
    record = EvidenceRecord(command="pytest", exit_code=0, artifacts=["a.txt", "b.txt"], sha256=hashes, source="test", provenance="pytest", verified_at=NOW)
    output = record.to_dict()
    assert list(output["sha256"]) == ["a.txt", "b.txt"]
    output["sha256"]["a.txt"] = "0" * 64
    assert record.sha256["a.txt"] == "A" * 64


def test_provenance_and_verified_at_are_required_and_serialized():
    with pytest.raises(EvidenceValidationError) as missing_provenance:
        EvidenceRecord(command="pytest", exit_code=0, provenance="", verified_at=NOW)
    assert missing_provenance.value.code == "missing_provenance"
    with pytest.raises(EvidenceValidationError) as missing_verified:
        EvidenceRecord(command="pytest", exit_code=0, provenance="pytest")
    assert missing_verified.value.code == "missing_verified_at"
    record = EvidenceRecord(command="pytest", exit_code=0, provenance="pytest", verified_at=NOW)
    assert EvidenceRecord.from_dict(record.to_dict()).to_dict() == record.to_dict()


def test_freshness_rejects_stale_and_future_with_stable_codes():
    stale = EvidenceRecord(command="pytest", exit_code=0, provenance="pytest", verified_at="2025-12-30T23:59:59Z")
    with pytest.raises(EvidenceValidationError) as stale_error:
        EvidenceStore(clock=lambda: NOW).validate(stale)
    assert stale_error.value.code == "evidence_stale"
    future = EvidenceRecord(command="pytest", exit_code=0, provenance="pytest", verified_at="2026-01-01T00:00:01Z")
    with pytest.raises(EvidenceValidationError) as future_error:
        EvidenceStore(clock=lambda: NOW).validate(future)
    assert future_error.value.code == "verified_at_future"


def test_unknown_and_conflicting_legacy_fields_are_rejected():
    payload = {"command": "pytest", "exit_code": 0, "provenance": "pytest", "verified_at": NOW, "extra": True}
    with pytest.raises(EvidenceValidationError) as unknown:
        EvidenceRecord.from_dict(payload)
    assert unknown.value.code == "unknown_field"
    payload.pop("extra")
    payload["artifacts"] = []
    payload["artifact_paths"] = []
    with pytest.raises(EvidenceValidationError) as conflict:
        EvidenceRecord.from_dict(payload)
    assert conflict.value.code == "conflicting_alias"
