"""Regression tests for pd_studio_sync's malformed-state handling.

A STATE.json that parses to a non-dict (array/number) or whose ``tasks`` is not
length-delimited must skip that feature, not abort the whole snapshot. The broad
catch was narrowed; this test keeps the behavior pinned.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pd_studio_sync as sync


def _write_state(spec: Path, name: str, payload) -> None:
    feature_dir = spec / name
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "STATE.json").write_text(json.dumps(payload), encoding="utf-8")


def test_pd_features_skips_malformed_state_records(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "REPO", tmp_path)
    spec = tmp_path / ".spec"
    _write_state(spec, "array", [])
    _write_state(spec, "scalar", 42)
    _write_state(
        spec,
        "null_tasks",
        {"feature": "null_tasks", "phase": 0, "status": "initialized", "tasks": None},
    )
    _write_state(
        spec,
        "valid",
        {"feature": "valid", "phase": 1, "status": "initialized", "tasks": [1, 2]},
    )

    rows = sync.pd_features()

    assert [row["feature"] for row in rows] == ["valid"]
    assert rows[0]["tasks"] == 2
