"""T2-03 model-facing V2 normalization contracts."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.models import CanonicalOutput, FleetPlan, normalize_output  # noqa: E402


BASE = {
    "schema_version": "pd-fleet-plan:v2",
    "name": "café",
    "tasks": [
        {"taskId": "b", "capabilities": ("z", "a"), "result": None},
        {"task_id": "a", "capabilities": ["b", "a"], "result": None},
    ],
    "dependencies": ["z", "a"],
    "context": None,
}


def test_permutations_have_golden_utf8_json_bytes() -> None:
    first = dict(BASE)
    second = {
        "context": None,
        "dependencies": ["a", "z"],
        "tasks": [
            {"capabilities": ["a", "z"], "result": None, "taskId": "b"},
            {"capabilities": ["a", "b"], "result": None, "task_id": "a"},
        ],
        "name": "café",
        "schemaVersion": "pd-fleet-plan:v2",
    }
    expected = (
        '{"context":null,"dependencies":["a","z"],"name":"café",'
        '"schema_version":"pd-fleet-plan:v2","tasks":[{"capabilities":["a","z"],'
        '"result":null,"task_id":"b"},{"capabilities":["a","b"],"result":null,'
        '"task_id":"a"}]}'
    ).encode("utf-8")
    # Task order is meaningful; field and set-like collection order is not.
    assert CanonicalOutput.from_value(first).json_bytes == expected
    assert CanonicalOutput.from_value(second).json_bytes == expected
    assert normalize_output(first) == normalize_output(second)


def test_runtime_metadata_is_removed_without_clock_or_mutation() -> None:
    value = dict(BASE, timestamp="2026-07-17T00:00:00Z", runtime={"wall_time": 9}, updated_at="later")
    before = dict(value)
    result = normalize_output(value)
    assert "timestamp" not in result and "runtime" not in result and "updated_at" not in result
    assert value == before


@pytest.mark.parametrize("path", [
    "/home/alice/project/out.txt",
    r"C:\Users\alice\project\out.txt",
    r"\\wsl$\Ubuntu\home\alice\project\out.txt",
    "~/project/out.txt",
])
def test_posix_windows_and_wsl_absolute_paths_are_redacted(path: str) -> None:
    result = normalize_output(dict(BASE, description=f"failure at {path}"))
    assert "alice" not in json.dumps(result, ensure_ascii=False)
    assert "[PATH REDACTED]" in result["description"]


def test_secrets_are_redacted_before_persistence_and_hashing() -> None:
    result = normalize_output(dict(BASE, description="token: unique-secret-123 password=unique-password-123"))
    encoded = CanonicalOutput(result).json_bytes
    assert b"unique-secret" not in encoded and b"unique-password" not in encoded


def test_aliases_types_and_none_are_preserved() -> None:
    result = normalize_output({
        "schemaVersion": "pd-fleet-plan:v2",
        "tasks": ({"taskId": "t", "value": None},),
        "capabilities": ("z", "a"),
        "context": None,
    })
    assert result["tasks"] == [{"task_id": "t", "value": None}]
    assert result["capabilities"] == ["a", "z"]
    assert result["context"] is None


def test_no_arbitrary_serialization_fallback() -> None:
    class NotJson:
        pass

    with pytest.raises(ValueError):
        normalize_output(dict(BASE, payload=NotJson()))


def test_output_normalization_is_idempotent_and_v1_unchanged() -> None:
    once = normalize_output(BASE)
    assert normalize_output(once) == once
    assert FleetPlan.from_dict({"tasks": [], "agents": [], "waves": [], "gates": []}).schema_version == "1"


def test_canonical_output_is_a_stable_json_facade() -> None:
    output = CanonicalOutput.from_value(BASE)
    assert output.to_dict() == normalize_output(BASE)
    assert output.to_json().encode("utf-8") == output.json_bytes


def test_direct_constructor_canonicalizes_secrets_and_paths() -> None:
    value = dict(BASE, description="token: unique-secret-123", path="/home/alice/private.txt")
    output = CanonicalOutput(value=value)
    encoded = output.json_bytes
    assert b"unique-secret-123" not in encoded
    assert b"/home/alice/private.txt" not in encoded
    assert output["description"] == "token: [REDACTED]"
    assert output["path"] == "[PATH REDACTED]"


def test_constructor_and_accessors_do_not_expose_nested_aliases() -> None:
    nested = {"items": [{"name": "original"}]}
    value = dict(BASE, context=nested)
    output = CanonicalOutput(value)
    before = output.json_bytes

    nested["items"][0]["name"] = "changed through input"
    returned_value = output.value
    returned_value["context"]["items"][0]["name"] = "changed through value"
    returned_dict = output.to_dict()
    returned_dict["context"]["items"][0]["name"] = "changed through dict"
    returned_item = output["context"]
    returned_item["items"][0]["name"] = "changed through item"

    assert output.json_bytes == before
    assert output["context"]["items"][0]["name"] == "original"


def test_from_value_matches_direct_constructor() -> None:
    direct = CanonicalOutput(BASE)
    factory = CanonicalOutput.from_value(BASE)
    assert direct.to_dict() == factory.to_dict()
    assert direct.json_bytes == factory.json_bytes
    assert direct.value == factory.value
