#!/usr/bin/env python3
"""Tests for the Laya routing spike (T-203) — features/baseline/pipeline (stub backend)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pd_fleet.laya_routing_spike as spike  # noqa: E402


EV = {"event_id": "e1", "source": "hermes", "ts": "2026-10-09T22:53:27+00:00", "agent_id": "hermes:desktop",
      "kind": "status", "status": "running", "action": "terminal",
      "meta": {"model": "m", "msgs": 14, "tools": 9}}


def test_baseline_rules() -> None:
    assert spike.baseline_sink({"kind": "heartbeat", "status": None}) == "stream_only"
    assert spike.baseline_sink({"kind": "status", "status": "failed"}) == "ledger_notify"
    assert spike.baseline_sink({"kind": "status", "status": "done"}) == "ledger"
    assert spike.baseline_sink({"kind": "status", "status": "running"}) == "stream_only"
    assert spike.baseline_notify({"status": "blocked"}) == 1.0
    assert spike.baseline_notify({"status": "done"}) == 0.0


def test_features_are_computed_in_code() -> None:
    txt = spike.features(EV, datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc), similar=5)
    assert "kind=status" in txt and "status=running" in txt
    assert "age_min=7" in txt  # 22:53:27 → 23:00 = 6.55 → 7
    assert "msgs=14" in txt and "tools=9" in txt
    assert "similar_events_in_batch=5" in txt


def test_question_schema() -> None:
    q = spike.QUESTIONS
    assert q["sink"]["type"] == "choice"
    assert set(q["sink"]["criteria"]) == {"stream_only", "ledger", "ledger_notify"}
    assert q["notify"]["type"] == "noul"


def test_stub_pipeline_writes_artifacts(tmp_path: Path) -> None:
    bus = tmp_path / "events.jsonl"
    events = [
        {**EV},
        {**EV, "event_id": "e2", "kind": "heartbeat", "status": None, "action": None,
         "agent_id": "gateway:default", "ts": "2026-10-09T22:52:37+00:00", "meta": {"host": "H"}},
        {**EV, "event_id": "e3", "status": "failed", "agent_id": "hermes:cron"},
    ]
    bus.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    out = tmp_path / "spike"
    res = spike.run(bus, out, backend="stub")
    assert res["summary"]["n_events"] == 3
    assert res["summary"]["backend"] == "stub"
    # stub ecoa o baseline → 100% de concordância por construção (valida o pipeline)
    assert res["summary"]["sink_agreement"] == [3, 3]
    assert res["summary"]["notify_agreement"] == [3, 3]
    rows = [json.loads(l) for l in (out / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3
    assert rows[2]["laya_sink"] == "ledger_notify"
    assert rows[2]["laya_p_notify"] == 1.0 and rows[2]["agree_notify"] is True
    assert "RESULTS (T-203)" in (out / "RESULTS.md").read_text(encoding="utf-8")


def test_run_requires_events(tmp_path: Path) -> None:
    import pytest
    with pytest.raises(SystemExit):
        spike.run(tmp_path / "missing.jsonl", tmp_path / "out", backend="stub")
