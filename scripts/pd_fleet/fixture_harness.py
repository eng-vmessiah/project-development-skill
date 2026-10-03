"""Offline, implementation-independent contract fixture harness."""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

HARNESS = "pd-fleet-fixture-harness:v1"
SCENARIO_ONLY = {
    "lifecycle-transitions.json", "hostile-inputs.json", "workspace-invalid.json",
    "redaction-before-fingerprint.json", "no-dispatch-boundary.json",
    "replay-same-fingerprint.json", "replay-concurrent-reservation.json",
    "replay-terminal-tombstone.json",
}
RESULT_FILES = {
    "result-execution-succeeded.json", "result-harness-event.json",
    "result-cancellation-confirmed.json", "result-handoff.json", "result-cleanup.json",
}
REASON_FIELDS = {"cancel": "cancel_reason", "handoff": "handoff_reason", "cleanup": "cleanup_reason"}
MUTATING_FIELDS = {"schema_version", "operation", "lineage", "owner", "expected_generation", "idempotency_key", "request_fingerprint"}
OPERATION_FIELDS = {
    "prepare": MUTATING_FIELDS | {"workspace"},
    "execute": MUTATING_FIELDS | {"input"},
    "cancel": MUTATING_FIELDS | {"cancel_reason"},
    "handoff": MUTATING_FIELDS | {"handoff_reason"},
    "cleanup": MUTATING_FIELDS | {"cleanup_reason"},
    "observe": {"schema_version", "operation", "lineage", "cursor"},
}


def _errors(validator: Draft202012Validator, value: Any) -> list[dict[str, Any]]:
    return [{"path": "/".join(str(part) for part in error.path), "message": error.message}
            for error in sorted(validator.iter_errors(value), key=lambda item: list(item.path))]


def _bundle_components(declared: str) -> tuple[str, ...]:
    if not isinstance(declared, str) or not declared or Path(declared).is_absolute():
        raise ValueError(f"path escapes fixture bundle: {declared}")
    parts = tuple(Path(declared).parts)
    if any(part in ("", ".", "..") or "\\" in part for part in parts):
        raise ValueError(f"path escapes fixture bundle: {declared}")
    return parts


def _read_bundle_json(root: Path, declared: str) -> Any:
    """Read a bundle member through pinned descriptors, rejecting symlinks."""
    parts = _bundle_components(declared)
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(root, flags)
    current_fd = root_fd
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, flags, dir_fd=current_fd)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        file_flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open(parts[-1], file_flags, dir_fd=current_fd)
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise ValueError(f"bundle member is not a regular file: {declared}")
            with os.fdopen(file_fd, "r", encoding="utf-8") as handle:
                file_fd = -1
                return json.load(handle)
        finally:
            if file_fd >= 0:
                os.close(file_fd)
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _projection(fixture: dict[str, Any], *, scenario_mode: bool) -> tuple[dict[str, Any], bool]:
    operation = fixture.get("operation")
    if not isinstance(operation, str):
        operation = ""
    allowed = OPERATION_FIELDS.get(operation, set())
    request = {key: value for key, value in fixture.items() if key in allowed}
    synthetic = False
    reason_field = REASON_FIELDS.get(operation)
    if scenario_mode and reason_field and reason_field not in request:
        request[reason_field] = "fixture-reason"
        synthetic = True
    if scenario_mode and operation == "execute":
        input_value = request.get("input")
        if not isinstance(input_value, dict) or set(input_value) != {"goal_ref", "payload"}:
            request["input"] = {"goal_ref": "fixture-goal", "payload": "fixture-payload"}
            synthetic = True
    return request, synthetic


def _expected_errors(fixture: dict[str, Any], stable: set[str]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    expected = fixture.get("expected")
    if expected is not None and not isinstance(expected, dict):
        errors.append({"path": "expected", "message": "must be an object"})
    for case in fixture.get("cases", []):
        if isinstance(case, dict) and case.get("error_code") not in (None, *stable):
            errors.append({"path": "cases[].error_code", "message": "unstable error code"})
    return errors


def validate_bundle(manifest_path: str | Path, *, fixture: str | None = None, mode: str = "scenario") -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent
    manifest = _read_bundle_json(manifest_path.parent, manifest_path.name)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("fixture_files"), list):
        raise ValueError("manifest must contain a fixture_files array")
    if not all(isinstance(name, str) for name in manifest["fixture_files"]):
        raise ValueError("manifest fixture_files must contain strings")
    for field in ("request_schema", "result_schema"):
        if not isinstance(manifest.get(field), str):
            raise ValueError(f"manifest {field} must be a string")

    request_schema = _read_bundle_json(root, manifest["request_schema"])
    result_schema = _read_bundle_json(root, manifest["result_schema"])
    request_validator = Draft202012Validator(request_schema)
    result_validator = Draft202012Validator(result_schema)
    listed = list(manifest["fixture_files"])
    if fixture:
        listed = [name for name in listed if name == fixture or Path(name).stem == fixture]
        if not listed:
            raise KeyError(fixture)
    stable = set(manifest.get("stable_error_codes", []))
    rows = []
    missing = []
    for name in listed:
        try:
            data = _read_bundle_json(root, name)
        except FileNotFoundError:
            missing.append(name)
            continue
        if not isinstance(data, dict):
            raise ValueError(f"fixture must be an object: {name}")
        row: dict[str, Any] = {"file": name}
        if name in RESULT_FILES:
            errors = _errors(result_validator, data)
            row.update({"kind": "result", "result_validation": {"valid": not errors, "errors": errors}})
        elif name in SCENARIO_ONLY:
            errors = _expected_errors(data, stable)
            row.update({"fixture_id": data.get("fixture_id", Path(name).stem), "kind": "scenario_only", "scenario_validation": {"valid": not errors, "errors": errors}})
        else:
            projection, synthetic = _projection(data, scenario_mode=mode == "scenario")
            operation_fields = OPERATION_FIELDS.get(str(data.get("operation")), set())
            excluded = sorted(set(data) - operation_fields - {"fixture_id", "expected"})
            errors = _errors(request_validator, projection)
            if mode == "strict" and excluded:
                errors.append({"path": "<fixture>", "message": "scenario fields are not wire fields: " + ", ".join(excluded)})
            expected_errors = _expected_errors(data, stable)
            row.update({"fixture_id": data.get("fixture_id", Path(name).stem), "kind": "request", "operation": data.get("operation"), "request_projection": {"valid": not errors, "synthetic_projection": synthetic, "excluded_scenario_fields": excluded, "errors": errors}, "expected_metadata": {"valid": not expected_errors, "errors": expected_errors}})
        rows.append(row)
    failures = sum(1 for row in rows if any(not section.get("valid", True) for section in row.values() if isinstance(section, dict) and "valid" in section))
    return {"harness": HARNESS, "manifest": {"path": manifest_path.name, "valid": not missing, "fixture_count": len(manifest["fixture_files"]), "missing": missing}, "fixtures": rows, "summary": {"selected": len(rows), "passed": len(rows) - failures, "failed": failures}, "valid": not missing and failures == 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--fixture")
    parser.add_argument("--mode", choices=("strict", "scenario"), default="scenario")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = validate_bundle(args.manifest, fixture=args.fixture, mode=args.mode)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"harness": HARNESS, "valid": False, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
