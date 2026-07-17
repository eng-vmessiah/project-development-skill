import sys
from hashlib import sha256
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.evidence import EvidenceError, EvidenceRecord, EvidenceStore, EvidenceValidationError


def test_capture_success_and_sanitization(tmp_path):
    artifact = tmp_path / "report.txt"
    artifact.write_text("fresh", encoding="utf-8")
    store = EvidenceStore([tmp_path])
    record = store.capture(
        "pytest -q",
        executor=lambda command: (0, "password=hunter2 https://example.test\nPASS", ""),
        artifacts=["report.txt"],
        sha256=sha256(b"fresh").hexdigest(),
    )
    assert record.exit_code == 0
    assert "hunter2" not in record.stdout
    assert "https://" not in record.stdout
    assert store.to_dict()[0]["artifacts"] == ["report.txt"]


def test_capture_is_fail_closed_without_injected_executor():
    with pytest.raises(EvidenceError, match="executor"):
        EvidenceStore().capture("pytest")


def test_failed_command_is_rejected(tmp_path):
    with pytest.raises(EvidenceValidationError, match="exit_code"):
        EvidenceStore([tmp_path]).capture("pytest", executor=lambda command: (1, "", "failed"))


def test_path_traversal_and_missing_artifact_are_rejected(tmp_path):
    with pytest.raises(EvidenceValidationError, match="inseguro"):
        EvidenceRecord(command="pytest", exit_code=0, artifacts=["../secret"], source="test")
    with pytest.raises(EvidenceValidationError, match="ausente"):
        EvidenceStore([tmp_path]).add(EvidenceRecord(command="pytest", exit_code=0, artifacts=["missing"], source="test"))


def test_hash_mismatch_is_rejected(tmp_path):
    (tmp_path / "out.txt").write_text("actual", encoding="utf-8")
    record = EvidenceRecord(command="pytest", exit_code=0, artifacts=["out.txt"], sha256="0" * 64, source="test")
    with pytest.raises(EvidenceValidationError, match="hash mismatch"):
        EvidenceStore([tmp_path]).add(record)


def test_declarative_empty_evidence_and_secret_metadata_are_rejected():
    with pytest.raises(EvidenceValidationError, match="comando ou artefato"):
        EvidenceRecord(source="test")
    with pytest.raises(EvidenceValidationError, match="segredo"):
        EvidenceRecord(command="token=topsecret", exit_code=0, source="test")
    with pytest.raises(EvidenceValidationError, match="URL"):
        EvidenceRecord(command="curl https://example.test", exit_code=0, source="test")


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
        EvidenceStore().capture("pytest", executor=executor)
    assert str(exc.value) == "executor falhou"
    assert "hunter2" not in str(exc.value)
    assert "private.example" not in str(exc.value)


def test_hash_mapping_is_normalized_and_detached():
    hashes = {"b.txt": "B" * 64, "a.txt": "A" * 64}
    record = EvidenceRecord(command="pytest", exit_code=0, artifacts=["a.txt", "b.txt"], sha256=hashes, source="test")
    output = record.to_dict()
    assert list(output["sha256"]) == ["a.txt", "b.txt"]
    output["sha256"]["a.txt"] = "0" * 64
    assert record.sha256["a.txt"] == "A" * 64
