"""Regression tests for the final local fake-only G3 closure debts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
HARNESS = ROOT / "scripts" / "pd_fleet" / "fixture_harness.py"


def test_vertical_runner_supports_module_execution() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.pd_fleet.run_fake_vertical"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["local_fake_only"] is True
    assert [case["name"] for case in report["cases"]] == [
        "happy_vertical",
        "confirmed_cancel",
        "cleanup_failure_retry",
        "timed_out_cleanup",
    ]


def test_bundle_reader_rejects_in_bundle_symlink(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("fixture_harness", HARNESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    target = tmp_path / "target.json"
    target.write_text('{"safe": true}', encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises((OSError, ValueError)):
        module._read_bundle_json(tmp_path, "link.json")


def test_bundle_reader_rejects_symlinked_intermediate_directory(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("fixture_harness_nested", HARNESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file.json").write_text('{"escaped": true}', encoding="utf-8")
    link = tmp_path / "nested"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises((OSError, ValueError)):
        module._read_bundle_json(tmp_path, "nested/file.json")
