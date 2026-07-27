"""RED/GREEN contract tests for the local fleet event log."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from collections.abc import Mapping
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.events import EventLog, FleetEvent, MAX_COLLECTION, MAX_LOG_BYTES, MAX_LOG_LINE_BYTES  # noqa: E402


def event(**overrides):
    values = dict(
        event_id="evt-1", run_id="run-1", task_id="task-1", kind="task.started",
        ordering_key="task-1", sequence=0, owner_epoch=2,
        payload={"state": "running"}, created_at="2026-07-27T00:00:00+00:00",
    )
    values.update(overrides)
    return FleetEvent(**values)


def test_r1_event_envelope_is_frozen_and_json_safe():
    value = event()
    assert value.schema_version == 1
    assert value.to_dict()["payload"] == {"state": "running"}
    assert json.loads(value.to_json())["event_id"] == "evt-1"
    with pytest.raises((AttributeError, TypeError)):
        value.kind = "changed"
    with pytest.raises(TypeError):
        value.payload["new"] = "value"


def test_r2_rejects_unbounded_or_sensitive_values():
    for payload in ({"prompt": "secret"}, {"token": "secret-value"}, {"url": "https://example.test"}, {"pid": 42}, {"path": "/tmp/x"}, {"x": float("nan")}):
        with pytest.raises(ValueError):
            event(payload=payload)
    with pytest.raises(ValueError):
        event(kind="bad\nkind")
    with pytest.raises(ValueError):
        event(payload={"x": "a" * 70000})


def test_r3_sequence_is_append_order_and_query_uses_logical_order(tmp_path):
    log = EventLog(tmp_path, "run-1", owner_epoch=2)
    log.append(event(event_id="b", ordering_key="z", sequence=0))
    log.append(event(event_id="a", ordering_key="a", sequence=1))
    assert [item.event_id for item in log.query()] == ["a", "b"]


def test_r4_duplicate_is_idempotent_and_conflict_fails_closed(tmp_path):
    log = EventLog(tmp_path, "run-1")
    first = event()
    assert log.append(first) == first
    assert log.append(first) == first
    with pytest.raises(ValueError):
        log.append(event(kind="task.finished", payload={"state": "done"}))
    assert len(log.replay()) == 1


def test_r5_replay_and_query_are_read_only_detached_and_missing_read_does_not_mkdir(tmp_path):
    log = EventLog(tmp_path, "run-1")
    assert not (tmp_path / "run-1").exists()
    assert log.replay() == ()
    assert log.query() == ()
    assert not (tmp_path / "run-1").exists()
    log.append(event())
    result = log.replay()
    assert result[0].to_dict() == event().to_dict()
    with pytest.raises(TypeError):
        result[0].payload["x"] = 1


def test_r6_owner_epoch_and_numeric_ids_are_validated(tmp_path):
    log = EventLog(tmp_path, "run-1", owner_epoch=3)
    with pytest.raises(ValueError):
        log.append(event(owner_epoch=2))
    with pytest.raises(ValueError):
        event(sequence=-1)
    with pytest.raises(ValueError):
        event(sequence=float("inf"))
    with pytest.raises(ValueError):
        EventLog(tmp_path, "../escape")


def test_r7_append_and_query_are_bounded(tmp_path):
    log = EventLog(tmp_path, "run-1")
    with pytest.raises(ValueError):
        log.append(event(payload={str(i): i for i in range(300)}))
    log.append(event())
    with pytest.raises(ValueError):
        log.query(limit=0)
    with pytest.raises(ValueError):
        log.replay(limit=0)


def test_r8_concurrent_same_event_is_stored_once_and_has_checksum(tmp_path):
    log = EventLog(tmp_path, "run-1")
    errors = []
    barrier = threading.Barrier(8)

    def writer():
        try:
            barrier.wait()
            log.append(event())
        except Exception as exc:  # pragma: no cover - assertion below reports it
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(log.replay()) == 1
    record = (tmp_path / "run-1" / "events.jsonl").read_text().splitlines()
    assert len(record) == 1
    assert len(json.loads(record[0])["checksum"]) == 64


class InfiniteItems(Mapping):
    def __init__(self):
        self.consumed = 0

    def __getitem__(self, key):
        return key

    def __iter__(self):
        while True:
            self.consumed += 1
            yield f"key-{self.consumed}"

    def __len__(self):
        return 1

    def items(self):
        owner = self

        def stream():
            while True:
                owner.consumed += 1
                yield (f"key-{owner.consumed}", 1)

        return stream()


def test_e1r_custom_mapping_is_bounded_at_collection_plus_one():
    value = InfiniteItems()
    with pytest.raises(ValueError):
        event(payload=value)
    assert value.consumed <= 257


class HostileList(list):
    def __init__(self, values):
        super().__init__(values)
        self.consumed = 0

    def __len__(self):
        return 1

    def __iter__(self):
        for value in super().__iter__():
            self.consumed += 1
            yield value


class HostileTuple(tuple):
    def __new__(cls, values):
        return super().__new__(cls, values)

    def __init__(self, values):
        self.consumed = 0

    def __len__(self):
        return 1

    def __iter__(self):
        for value in super().__iter__():
            self.consumed += 1
            yield value


@pytest.mark.parametrize("sequence_type", [HostileList, HostileTuple])
def test_e1r_hostile_sequences_are_bounded_without_trusting_len(sequence_type):
    value = sequence_type([1] * (MAX_COLLECTION + 44))
    with pytest.raises(ValueError):
        event(payload=value)
    assert value.consumed <= MAX_COLLECTION + 1


@pytest.mark.parametrize(
    "created_at",
    [
        "2026-02-29T00:00:00Z",
        "2026-01-01T24:00:00+00:00",
        "2026-01-01T00:00:00+24:00",
        "2026-01-01T00:00:00+00:60",
    ],
)
def test_e1r_created_at_rejects_impossible_iso_timestamps(created_at):
    with pytest.raises(ValueError):
        event(created_at=created_at)


@pytest.mark.parametrize(
    "created_at",
    [
        "2024-02-29T12:34:56Z",
        "2026-07-27T12:34:56.123456Z",
        "2026-07-27T12:34:56+05:30",
        "2026-07-27T12:34:56.123456-03:00",
    ],
)
def test_e1r_created_at_accepts_supported_iso_timestamp_forms(created_at):
    assert event(created_at=created_at).created_at == created_at


@pytest.mark.parametrize("field", ["event_id", "run_id", "task_id", "kind", "ordering_key"])
def test_e1r_envelope_metadata_rejects_secret_and_assignment_forms(field):
    for value in ("token:secret", "password=secret", "prompt:show cot", "pid:123", "native-handle=7"):
        overrides = {field: value}
        if field == "run_id":
            overrides["event_id"] = "evt-2"
        with pytest.raises(ValueError):
            event(**overrides)


def test_e1r_created_at_rejects_sensitive_form_but_accepts_iso_timestamp():
    assert event(created_at="2026-07-27T00:00:00+00:00").created_at.startswith("2026-")
    for value in ("token:secret", "authorization=bad", "pid:42"):
        with pytest.raises(ValueError):
            event(created_at=value)


def test_e1r_unknown_envelope_field_is_rejected_and_not_checksum_covered(tmp_path):
    record = event().to_dict()
    record["unexpected"] = "must-reject"
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    record["checksum"] = hashlib.sha256(canonical).hexdigest()
    path = tmp_path / "run-1" / "events.jsonl"
    path.parent.mkdir()
    path.write_bytes(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    with pytest.raises(ValueError):
        EventLog(tmp_path, "run-1").replay()


def test_e1r_oversized_log_is_rejected_before_read_allocation(tmp_path):
    log = EventLog(tmp_path, "run-1")
    path = tmp_path / "run-1" / "events.jsonl"
    path.parent.mkdir()
    with path.open("wb") as handle:
        handle.truncate(MAX_LOG_BYTES + 1)
    with pytest.raises(ValueError):
        log.replay()


def test_e1r_oversized_and_partial_lines_are_rejected(tmp_path):
    log = EventLog(tmp_path, "run-1")
    path = tmp_path / "run-1" / "events.jsonl"
    path.parent.mkdir()
    path.write_bytes(b"{" + b"x" * MAX_LOG_LINE_BYTES + b"}\n")
    with pytest.raises(ValueError):
        log.replay()
    path.write_bytes(b"partial-record")
    with pytest.raises(ValueError):
        log.replay()


def test_e1r_nested_symlink_components_fail_closed(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    nested = tmp_path / "nested"
    try:
        nested.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    log = EventLog(nested, "run-1")
    with pytest.raises(ValueError):
        log.append(event())
    assert not (target / "run-1").exists()
