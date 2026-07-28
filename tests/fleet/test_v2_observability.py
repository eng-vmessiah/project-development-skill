import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd_fleet.observability import AuditSink, ObservabilityError


def test_append_only_order_counters_and_correlation_ids():
    sink = AuditSink()
    sink.record("task.started", run_id="run-1", task_id="task-1", fields={"status": "running"})
    sink.record("task.completed", run_id="run-1", task_id="task-1", fields={"status": "completed"})
    exported = sink.export()
    assert [event["sequence"] for event in exported["events"]] == [1, 2]
    assert exported["events"][0]["correlation_id"] == exported["events"][1]["correlation_id"]
    assert exported["events"][0]["run_id"] == "run-1"
    assert exported["counters"] == {"task.completed": 1, "task.started": 1}
    exported["events"][0]["fields"]["status"] = "changed"
    assert sink.export()["events"][0]["fields"]["status"] == "running"


def test_redacts_secret_path_url_and_export_is_deterministic():
    sink = AuditSink()
    sink.record("diagnostic", run_id="r", task_id="t", correlation_id="corr",
                fields={"message": "token=super-secret https://example.test/a /home/vitor/private.txt",
                        "nested": {"source": "/mnt/c/private", "api_key": "never"}})
    output = sink.export()
    text = json.dumps(output, sort_keys=True)
    assert "super-secret" not in text and "example.test" not in text
    assert "/home/vitor" not in text and "/mnt/c" not in text and "never" not in text
    assert "[URL REDACTED]" in text and "[PATH REDACTED]" in text
    assert sink.export() == output


@pytest.mark.parametrize("key", ["accesskey", "access_key", "access-key"])
def test_redacts_all_access_key_spellings(key):
    sink = AuditSink()
    sink.record("diagnostic", fields={key: "must-not-leak"})
    assert sink.export()["events"][0]["fields"][key] == "[SECRET REDACTED]"


def test_rejected_record_does_not_consume_sequence():
    sink = AuditSink()
    sink.record("first")
    with pytest.raises(ObservabilityError):
        sink.record("rejected", fields={1: "invalid key"})
    assert sink.record("second").sequence == 2


def test_deep_immutability_and_bounded_fields():
    sink = AuditSink(max_fields=2, max_string_length=12, max_events=2)
    fields = {"z": {"value": ["original"]}, "a": "0123456789abcdef", "extra": "drop"}
    sink.record("event", run_id="r", task_id="t", fields=fields)
    fields["z"]["value"].append("mutated")
    event = sink.events()[0]
    assert event["fields"]["a"] == "0123456789ab"
    assert len(event["fields"]) <= 2
    with pytest.raises(TypeError):
        event["fields"]["a"] = "x"
    sink.record("event2", run_id="r", task_id="t")
    with pytest.raises(ObservabilityError):
        sink.record("event3", run_id="r", task_id="t")


def test_invalid_ids_and_external_sinks_are_not_supported():
    sink = AuditSink()
    with pytest.raises(ObservabilityError):
        sink.record("x", run_id="../secret", task_id="t")
    with pytest.raises(ObservabilityError):
        sink.record("x", run_id="r", task_id="t", correlation_id="")


class _HostileObject:
    renders = 0

    def __repr__(self):
        type(self).renders += 1
        raise AssertionError("repr must not be called")

    def __str__(self):
        type(self).renders += 1
        raise AssertionError("str must not be called")


def test_unknown_objects_are_marked_without_rendering_them():
    _HostileObject.renders = 0
    sink = AuditSink()

    sink.record("diagnostic", fields={"value": _HostileObject()})

    assert sink.export()["events"][0]["fields"]["value"] == "[UNSUPPORTED TYPE]"
    assert _HostileObject.renders == 0


def test_mapping_keys_are_validated_before_sorting_without_stringifying_them():
    _HostileObject.renders = 0
    sink = AuditSink()

    with pytest.raises(ObservabilityError, match="field keys must be non-empty strings"):
        sink.record("diagnostic", fields={_HostileObject(): "value", "valid": "ok"})

    assert _HostileObject.renders == 0


def test_sets_are_deterministic_without_repr_or_string_conversion():
    _HostileObject.renders = 0
    first = AuditSink()
    second = AuditSink()
    values = {"z", _HostileObject(), 3}

    first.record("diagnostic", fields={"values": values})
    second.record("diagnostic", fields={"values": set(values)})

    assert first.export_json() == second.export_json()
    assert "[UNSUPPORTED TYPE]" in first.export_json()
    assert _HostileObject.renders == 0


def test_unsupported_type_marker_never_reads_hostile_type_name():
    class RaisingNameMeta(type):
        def __getattribute__(cls, name):
            if name == "__name__":
                raise AssertionError("type name must not be read")
            return super().__getattribute__(name)

    class Hostile(metaclass=RaisingNameMeta):
        pass

    sink = AuditSink()
    sink.record("diagnostic", fields={"value": Hostile()})

    assert sink.export()["events"][0]["fields"]["value"] == "[UNSUPPORTED TYPE]"
