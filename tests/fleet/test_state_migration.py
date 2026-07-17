import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd import PDState
from pd import TransactionRecoveryError


def feature(tmp_path):
    path = tmp_path / "feature"
    path.mkdir()
    return path


def test_legacy_md_only_migrates_without_losing_tasks(tmp_path):
    path = feature(tmp_path)
    (path / "STATE.md").write_text("# STATE.md\n## Phase\n2 (Planning)\n## Status\nready\n## Completed Tasks\n- [x] old task\n")
    state = PDState(path)
    assert state.state["tasks"] == ["old task"]
    assert state.state["fleet_state"]["tasks"] == []
    assert (path / "STATE.json").exists()


def test_legacy_json_only_gets_default_fleet_state(tmp_path):
    path = feature(tmp_path)
    (path / "STATE.json").write_text(json.dumps({"feature": "feature", "tasks": ["legacy"]}))
    state = PDState(path)
    assert state.state["tasks"] == ["legacy"]
    assert set(("schema_version", "agents", "waves", "tasks", "gates", "reports", "attempts", "blockers", "evidence", "updated_at")) <= set(state.state["fleet_state"])


def test_partial_json_and_unknown_fields_are_preserved(tmp_path):
    path = feature(tmp_path)
    payload = {"feature": "feature", "tasks": ["legacy"], "fleet_state": {"tasks": [{"id": "f"}], "x_future": {"v": 1}}}
    (path / "STATE.json").write_text(json.dumps(payload))
    state = PDState(path)
    state.save()
    saved = json.loads((path / "STATE.json").read_text())
    assert saved["tasks"] == ["legacy"]
    assert saved["fleet_state"]["tasks"] == [{"id": "f"}]
    assert saved["fleet_state"]["x_future"] == {"v": 1}


def test_json_md_round_trip_keeps_fleet_state(tmp_path):
    path = feature(tmp_path)
    state = PDState(path)
    state.state["fleet_state"] = {"evidence": ["report.log"], "custom": "kept"}
    state.save()
    (path / "STATE.json").unlink()
    loaded = PDState(path)
    assert loaded.state["fleet_state"]["evidence"] == ["report.log"]
    assert loaded.state["fleet_state"]["custom"] == "kept"


def test_failed_atomic_write_keeps_previous_json_and_evidence(tmp_path):
    path = feature(tmp_path)
    state = PDState(path)
    state.state["fleet_state"] = {"evidence": ["proof.txt"]}
    state.save()
    before = (path / "STATE.json").read_bytes()
    state.state["fleet_state"]["evidence"].append("new-proof.txt")
    with patch("pd.os.replace", side_effect=OSError("simulated disk failure")):
        with pytest.raises(OSError):
            state.save()
    assert (path / "STATE.json").read_bytes() == before
    assert json.loads((path / "STATE.json").read_text())["fleet_state"]["evidence"] == ["proof.txt"]


def test_markdown_generation_failure_does_not_mutate_memory_or_disk(tmp_path):
    path = feature(tmp_path)
    state = PDState(path)
    state.save()
    before_json = (path / "STATE.json").read_bytes()
    before_md = (path / "STATE.md").read_bytes()
    state.state["status"] = "candidate"
    with patch.object(state, "_generate_state_md", side_effect=RuntimeError("render failed")):
        with pytest.raises(RuntimeError):
            state.save()
    assert state.state["status"] == "candidate"
    assert (path / "STATE.json").read_bytes() == before_json
    assert (path / "STATE.md").read_bytes() == before_md


def test_strict_serialization_reports_invalid_value_without_mutation(tmp_path):
    path = feature(tmp_path)
    state = PDState(path)
    state.save()
    before_json = (path / "STATE.json").read_bytes()
    before = state.state.copy()
    state.state["not_json"] = object()
    with pytest.raises(TypeError, match="não serializável"):
        state.save()
    assert state.state["not_json"] is not None
    assert (path / "STATE.json").read_bytes() == before_json
    assert before["status"] == "initialized"


def test_markdown_replace_failure_rolls_back_json_and_markdown(tmp_path):
    path = feature(tmp_path)
    state = PDState(path)
    state.save()
    before_json = (path / "STATE.json").read_bytes()
    before_md = (path / "STATE.md").read_bytes()
    state.state["status"] = "candidate"
    calls = []
    original_replace = __import__("os").replace

    def fail_on_markdown(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError("markdown replace failed")
        return original_replace(source, target)

    with patch("pd.os.replace", side_effect=fail_on_markdown):
        with pytest.raises(OSError):
            state.save()
    assert (path / "STATE.json").read_bytes() == before_json
    assert (path / "STATE.md").read_bytes() == before_md
    assert (path / "STATE.json.bak").read_bytes() == before_json
    assert (path / "STATE.md.bak").read_bytes() == before_md
    assert state.state["status"] == "candidate"


def test_failed_second_replace_does_not_restore_stale_backup_for_absent_primary(tmp_path):
    path = feature(tmp_path)
    state = PDState(path)
    state.save()
    primary = path / "STATE.json"
    backup = path / "STATE.json.bak"
    stale_backup = b"stale backup that must remain untouched\n"
    primary.unlink()
    backup.write_bytes(stale_backup)
    before_md = (path / "STATE.md").read_bytes()
    state.state["status"] = "candidate"
    calls = []
    original_replace = __import__("os").replace

    def fail_on_second_replace(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError("markdown replace failed")
        return original_replace(source, target)

    with patch("pd.os.replace", side_effect=fail_on_second_replace):
        with pytest.raises(OSError, match="markdown replace failed"):
            state.save()
    assert not primary.exists()
    assert backup.read_bytes() == stale_backup
    assert (path / "STATE.md").read_bytes() == before_md


def test_rollback_failure_raises_recovery_error_chained_from_transaction_failure(tmp_path):
    path = feature(tmp_path)
    state = PDState(path)
    state.save()
    state.state["status"] = "candidate"
    calls = []
    original_replace = __import__("os").replace
    original_copy2 = __import__("shutil").copy2

    def fail_on_second_replace(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError("markdown replace failed")
        return original_replace(source, target)

    copy_calls = []

    def fail_during_rollback(source, target):
        copy_calls.append(target)
        if len(copy_calls) == 3:
            raise OSError("rollback copy failed")
        return original_copy2(source, target)

    with patch("pd.os.replace", side_effect=fail_on_second_replace), patch(
        "pd.shutil.copy2", side_effect=fail_during_rollback
    ):
        with pytest.raises(TransactionRecoveryError) as caught:
            state.save()
    assert isinstance(caught.value.__cause__, OSError)
    assert "markdown replace failed" in str(caught.value.__cause__)
    assert "recuperação" in str(caught.value)
