"""Live contract guard for plan-cockpit-v1.

The feature is closed; this test protects the surface it shipped from silent drift:
the derived snapshot must keep listing this feature and must stay deterministic.
It uses the real collector and a hermetic HOME so no ~/.hermes state leaks in.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import plan_cockpit_sync as sync  # noqa: E402


def test_snapshot_keeps_the_feature_and_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()

    first = sync.build(tmp_path / "runs")
    second = sync.build(tmp_path / "runs")

    rows_first = {row["feature"]: row for row in first["features"]}
    rows_second = {row["feature"]: row for row in second["features"]}

    assert "plan-cockpit-v1" in rows_first
    row = rows_first["plan-cockpit-v1"]
    assert row["source"] == "plan-yaml"
    assert row["tasks_total"] == len(row["tasks"])
    assert row["tasks_done"] == sum(
        1 for task in row["tasks"] if task["status"] in {"done", "completed"}
    )
    assert rows_first == rows_second
    assert first["meta"]["feature_count"] == len(rows_first)
