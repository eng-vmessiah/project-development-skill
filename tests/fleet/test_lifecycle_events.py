from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.checkpoint import Checkpoint  # noqa: E402
from pd_fleet.events import EventError, EventLog  # noqa: E402
from pd_fleet.lifecycle import TaskLifecycle  # noqa: E402
from pd_fleet.lifecycle_events import LifecycleEventRecorder  # noqa: E402


STAMP = "2026-01-01T00:00:00+00:00"


def recorder(tmp_path, *, epoch=3):
    log = EventLog(tmp_path, "run-1", owner_epoch=epoch)
    return LifecycleEventRecorder(log), log


def test_transition_projection_is_bounded_and_replayable(tmp_path):
    recorder_, log = recorder(tmp_path)
    life = TaskLifecycle("task-1", attempt=2, max_attempts=3)
    before = deepcopy(life)

    event = recorder_.record_transition(life, "ready", "running", 1, reason="dispatch", created_at=STAMP)

    assert event.kind == "lifecycle.transition"
    assert event.event_id == recorder_.record_transition(life, "ready", "running", 1, reason="dispatch", created_at=STAMP).event_id
    assert event.ordering_key == "task-1"
    assert event.task_id == "task-1"
    assert event.owner_epoch == 3
    assert dict(event.payload) == {"from": "ready", "to": "running", "attempt": 2, "reason": "dispatch"}
    assert life == before
    assert log.replay() == (event,)
    assert recorder_.query(task_id="task-1") == (event,)


def test_checkpoint_is_summary_only_and_does_not_mutate_input(tmp_path):
    recorder_, _ = recorder(tmp_path)
    checkpoint = Checkpoint.create(
        "feature-x", 4,
        tasks={"done": {"id": "done"}, "todo": {"id": "todo"}},
        lifecycle={"done": {"task_id": "done", "status": "completed"}, "todo": {"task_id": "todo", "status": "ready"}},
        reports=[{"secret": "raw report"}],
        evidence=[{"token": "raw evidence"}],
        blockers=["do not serialize this blocker"],
        created_at=STAMP,
    )
    before = deepcopy(checkpoint)

    event = recorder_.record_checkpoint(checkpoint, 2, created_at=STAMP)
    payload = dict(event.payload)

    assert event.kind == "checkpoint.committed"
    assert event.ordering_key == "checkpoint"
    assert event.task_id is None
    assert payload["feature"] == "feature-x"
    assert payload["wave"] == 4
    assert list(payload["completed_task_ids"]) == ["done"]
    assert list(payload["resume_task_ids"]) == ["todo"]
    assert payload["blocker_count"] == 1
    assert payload["report_count"] == 1
    assert payload["evidence_count"] == 1
    assert len(payload["digest"]) == 64
    serialized = json.dumps(event.to_dict(), sort_keys=True)
    for forbidden in ("raw report", "raw evidence", "do not serialize", "secret", "token"):
        assert forbidden not in serialized
    assert checkpoint == before


def test_projection_is_idempotent_and_conflicts_fail_closed(tmp_path):
    recorder_, log = recorder(tmp_path)
    life = TaskLifecycle("task-1", attempt=1)
    first = recorder_.record_transition(life, "pending", "ready", 1, reason="one", created_at=STAMP)
    assert recorder_.record_transition(life, "pending", "ready", 1, reason="one", created_at=STAMP) == first
    with pytest.raises(EventError, match="colisão|sequence"):
        recorder_.record_transition(life, "pending", "ready", 1, reason="different", created_at=STAMP)
    assert len(log.replay()) == 1


def test_stale_owner_and_sequence_fail_closed(tmp_path):
    log = EventLog(tmp_path, "run-1", owner_epoch=2)
    with pytest.raises(ValueError):
        LifecycleEventRecorder(log, owner_epoch=1)
    recorder_ = LifecycleEventRecorder(log)
    life = TaskLifecycle("task-1")
    recorder_.record_transition(life, "pending", "ready", 2, created_at=STAMP)
    with pytest.raises(EventError, match="monotônica|duplicada"):
        recorder_.record_transition(life, "pending", "ready", 1, created_at=STAMP)


def test_replay_query_ordering_and_passthrough(tmp_path):
    recorder_, _ = recorder(tmp_path)
    life = TaskLifecycle("b")
    first = recorder_.record_transition(life, "pending", "ready", 1, created_at=STAMP)
    checkpoint = Checkpoint.create("f", 1, created_at=STAMP)
    committed = recorder_.record_checkpoint(checkpoint, 2, created_at=STAMP)
    second = recorder_.record_transition(TaskLifecycle("a"), "pending", "ready", 3, created_at=STAMP)

    assert [event.event_id for event in recorder_.replay()] == [first.event_id, committed.event_id, second.event_id]
    assert [event.task_id for event in recorder_.query()] == ["a", "b", None]
    assert recorder_.query(ordering_key="checkpoint") == (committed,)


def test_no_forbidden_integration_or_side_effect_imports():
    source = inspect.getsource(LifecycleEventRecorder)
    module = inspect.getsource(sys.modules["pd_fleet.lifecycle_events"])
    for forbidden in ("orchestrator", "subprocess", "requests", "socket", "pd.py"):
        assert forbidden not in source
        assert forbidden not in module


class InfiniteInvalidIds:
    def __iter__(self):
        while True:
            yield object()


class HostileLen:
    def __len__(self):
        raise OverflowError("hostile length")


class HostileMapping(dict):
    def keys(self):
        while True:
            yield "task"


class HostileGet(dict):
    def get(self, *args, **kwargs):
        raise RuntimeError("hostile get")


class HostileAttribute:
    def __deepcopy__(self, memo):
        raise RuntimeError("hostile deepcopy")


class HostileBool:
    def __bool__(self):
        raise RuntimeError("hostile bool")


def test_adversarial_inputs_fail_closed_and_stay_bounded(tmp_path):
    recorder_, _ = recorder(tmp_path)
    with pytest.raises(EventError):
        recorder_.record_checkpoint({"feature": "f", "wave": 1, "tasks": {},
                                     "lifecycle": {}, "completed_task_ids": InfiniteInvalidIds()}, 1,
                                    created_at=STAMP)
    with pytest.raises(EventError):
        recorder_.record_checkpoint({"feature": "f", "wave": 1, "tasks": HostileMapping(),
                                     "lifecycle": {}, "reports": HostileLen()}, 1,
                                    created_at=STAMP)


def test_transition_state_and_reason_validation(tmp_path):
    recorder_, _ = recorder(tmp_path)
    life = TaskLifecycle("task-1")
    for kwargs in ({"from_state": "bogus", "to_state": "ready"},
                   {"from_state": "pending", "to_state": "bogus"},
                   {"from_state": "pending", "to_state": "ready", "reason": "token leaked"},
                   {"from_state": "pending", "to_state": "ready", "reason": " "}):
        with pytest.raises(EventError):
            recorder_.record_transition(life, sequence=1, created_at=STAMP, **kwargs)


def test_omitted_created_at_is_stable(tmp_path):
    recorder_, _ = recorder(tmp_path)
    life = TaskLifecycle("task-1")
    first = recorder_.record_transition(life, "pending", "ready", 1)
    assert first.created_at == "1970-01-01T00:00:00+00:00"
    assert recorder_.record_transition(life, "pending", "ready", 1) == first


@pytest.mark.parametrize("bad_id", ["bad id", "bad/id", "secret-token", 42])
def test_nonempty_invalid_ids_are_rejected(tmp_path, bad_id):
    recorder_, _ = recorder(tmp_path)
    with pytest.raises(EventError):
        recorder_.record_checkpoint(
            {"feature": "f", "wave": 1, "tasks": {}, "lifecycle": {},
             "completed_task_ids": [bad_id]}, 1, created_at=STAMP
        )


@pytest.mark.parametrize("mapping_name", ["tasks", "lifecycle"])
@pytest.mark.parametrize("bad_key", ["bad id", "bad/id", "secret-token", 42])
def test_checkpoint_mapping_keys_use_strict_id_policy_even_with_explicit_lists(
    tmp_path, mapping_name, bad_key
):
    recorder_, _ = recorder(tmp_path)
    checkpoint = {
        "feature": "f",
        "wave": 1,
        "tasks": {"valid-task": {}},
        "lifecycle": {"valid-task": {"status": "ready"}},
        "completed_task_ids": ["valid-task"],
        "resume_task_ids": [],
    }
    checkpoint[mapping_name][bad_key] = {}
    with pytest.raises(EventError):
        recorder_.record_checkpoint(checkpoint, 1, created_at=STAMP)


def test_checkpoint_bogus_status_is_rejected_even_with_explicit_lists(tmp_path):
    recorder_, _ = recorder(tmp_path)
    with pytest.raises(EventError):
        recorder_.record_checkpoint(
            {"feature": "f", "wave": 1, "tasks": {"task-1": {}},
             "lifecycle": {"task-1": {"status": "bogus"}},
             "completed_task_ids": [], "resume_task_ids": []}, 1, created_at=STAMP
        )


@pytest.mark.parametrize("invalid_mapping", ["tasks", "lifecycle"])
def test_invalid_status_in_either_mapping_is_not_masked_by_other_snapshot(
    tmp_path, invalid_mapping
):
    recorder_, _ = recorder(tmp_path)
    checkpoint = {
        "feature": "f",
        "wave": 1,
        "tasks": {"task-1": {"status": "ready"}},
        "lifecycle": {"task-1": {"status": "ready"}},
        "completed_task_ids": ["task-1"],
        "resume_task_ids": [],
    }
    checkpoint[invalid_mapping]["task-1"]["status"] = "bogus"
    with pytest.raises(EventError):
        recorder_.record_checkpoint(checkpoint, 1, created_at=STAMP)


def test_empty_or_malformed_explicit_created_at_is_rejected(tmp_path):
    recorder_, _ = recorder(tmp_path)
    life = TaskLifecycle("task-1")
    for stamp in ("", "not-a-timestamp"):
        with pytest.raises(EventError):
            recorder_.record_transition(life, "pending", "ready", 1, created_at=stamp)


def test_hostile_access_is_normalized_to_event_error(tmp_path):
    recorder_, _ = recorder(tmp_path)
    with pytest.raises(EventError):
        recorder_.record_checkpoint(HostileGet(), 1, created_at=STAMP)
    with pytest.raises(EventError):
        recorder_.record_checkpoint(HostileAttribute(), 1, created_at=STAMP)
    with pytest.raises(EventError):
        recorder_.record_checkpoint(
            {"feature": "f", "wave": 1, "tasks": {}, "lifecycle": {},
             "completed_task_ids": HostileBool()}, 1, created_at=STAMP
        )
