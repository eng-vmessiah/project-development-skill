"""TDD coverage for the explicit local HandoffStore persistence boundary."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.handoff import HandoffArtifact, HandoffStore, create_handoff  # noqa: E402


def _artifact(*, epoch: int = 3, task: str = "T-001") -> HandoffArtifact:
    return create_handoff(
        mission_id="mission-1", mission_run_id="run-1", task_id=task,
        source_lane_id="lane-1", attempt_id="attempt-1", session_id="session-1",
        target_role="builder", owner_epoch=epoch, reason="handoff",
        summary="Continue the bounded implementation", completed=["contract review"],
        remaining=["persistence"], decisions=["local only"], risks=["restart"],
        evidence_refs=["tests/fleet/test_handoff.py"], next_action="Run focused tests",
    )


def test_round_trip_survives_fresh_store_and_preserves_status_evidence(tmp_path):
    store = HandoffStore(tmp_path, run_id="run-1", owner_epoch=3)
    saved = store.save(_artifact(), status="ready", evidence_refs=["artifact.log"])

    loaded = HandoffStore(tmp_path, run_id="run-1", owner_epoch=3).load(saved.handoff_id)
    assert loaded == saved
    assert loaded.artifact == _artifact()
    assert loaded.status == "ready"
    assert loaded.evidence_refs == ("artifact.log",)
    assert isinstance(loaded.artifact, HandoffArtifact)


def test_replay_is_idempotent_and_does_not_replace_existing_record(tmp_path):
    store = HandoffStore(tmp_path, run_id="run-1", owner_epoch=3)
    artifact = _artifact()
    first = store.save(artifact, status="ready", evidence_refs=["artifact.log"])
    path = tmp_path / "run-1" / f"{first.handoff_id}.json"
    original = path.read_bytes()

    assert store.save(artifact, status="ready", evidence_refs=["artifact.log"]) == first
    assert path.read_bytes() == original


def test_same_id_with_conflicting_content_fails_closed(tmp_path):
    store = HandoffStore(tmp_path, run_id="run-1", owner_epoch=3)
    artifact = _artifact()
    store.save(artifact, status="ready", evidence_refs=["artifact.log"])
    conflict = HandoffArtifact(
        artifact.handoff_id, artifact.reason, "Different summary", artifact.completed,
        artifact.remaining, artifact.decisions, artifact.risks, artifact.evidence_refs,
        artifact.next_action, artifact.lineage, artifact.safety,
    )
    with pytest.raises(ValueError, match="conflicting"):
        store.save(conflict, status="ready", evidence_refs=["artifact.log"])


def test_malformed_and_checksum_invalid_records_fail_closed(tmp_path):
    store = HandoffStore(tmp_path, run_id="run-1", owner_epoch=3)
    saved = store.save(_artifact(), status="ready", evidence_refs=[])
    path = tmp_path / "run-1" / f"{saved.handoff_id}.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        store.load(saved.handoff_id)

    saved = store.save(_artifact(task="T-002"), status="ready", evidence_refs=[])
    path = tmp_path / "run-1" / f"{saved.handoff_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        store.load(saved.handoff_id)


def test_symlink_and_traversal_segments_are_rejected(tmp_path):
    (tmp_path / "run-1").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        HandoffStore(tmp_path, run_id="run-1", owner_epoch=3).save(_artifact(), status="ready", evidence_refs=[])
    with pytest.raises(ValueError, match="safe"):
        HandoffStore(tmp_path, run_id="../escape", owner_epoch=3)


def test_nested_symlink_component_under_store_root_is_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    nested = tmp_path / "nested"
    nested.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        HandoffStore(nested / "store", run_id="run-1", owner_epoch=3).save(
            _artifact(), status="ready", evidence_refs=[]
        )


def test_stale_or_mismatched_owner_lineage_is_rejected_on_save_and_load(tmp_path):
    with pytest.raises(ValueError, match="stale"):
        HandoffStore(tmp_path, run_id="run-1", owner_epoch=4).save(_artifact(), status="ready", evidence_refs=[])

    store = HandoffStore(tmp_path, run_id="run-1", owner_epoch=3)
    saved = store.save(_artifact(), status="ready", evidence_refs=[])
    with pytest.raises(ValueError, match="stale"):
        HandoffStore(tmp_path, run_id="run-1", owner_epoch=4).load(saved.handoff_id)
