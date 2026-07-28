"""E11 CLI tests for the bounded read-only readiness view."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd import PD  # noqa: E402
from pd_fleet.events import EventLog, FleetEvent, MAX_QUERY  # noqa: E402
from pd_fleet.run_store import FleetRunStore  # noqa: E402


CLI = Path(__file__).parents[2] / "scripts" / "pd.py"


def _event() -> FleetEvent:
    return FleetEvent(
        event_id="event-1", run_id="run-1", kind="test.event", ordering_key="event-1",
        sequence=1, owner_epoch=7, payload={}, created_at="2026-01-01T00:00:00+00:00",
    )


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    store_root, events_root = tmp_path / "store", tmp_path / "events"
    store = FleetRunStore(store_root)
    try:
        store.create("run-1", {"schema_version": "pd-fleet-plan:v2", "tasks": []}, "owner")
        store.append_event("run-1", {"event_id": "event-1", "ordering_key": "event-1"}, "owner")
    finally:
        store.close()
    EventLog(events_root, "run-1", owner_epoch=7).append(_event())
    return store_root, events_root


def test_json_is_sorted_and_contains_only_readiness_projection(tmp_path, capsys):
    store, events = _sources(tmp_path)
    before = sorted((p.relative_to(tmp_path), p.stat().st_mtime_ns, p.read_bytes())
                    for p in tmp_path.rglob("*") if p.is_file())
    PD().run(["fleet-supervisor-readiness", "--store", str(store), "--events", str(events),
              "--run-id", "run-1", "--owner-epoch", "7", "--json"])
    output = capsys.readouterr().out
    assert output == json.dumps(json.loads(output), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    report = json.loads(output)
    assert report == {
        "event_status": "healthy", "present_components": ["event", "reconciliation"],
        "reasons": [], "reconciliation_status": "consistent", "status": "ready",
        "supervisor_status": None,
    }
    assert "owner" not in output and "payload" not in output and "proposals" not in output
    after = sorted((p.relative_to(tmp_path), p.stat().st_mtime_ns, p.read_bytes())
                   for p in tmp_path.rglob("*") if p.is_file())
    assert after == before


def test_explicit_status_is_the_only_supervisor_component(tmp_path, capsys):
    store, events = tmp_path / "store", tmp_path / "events"
    PD().run(["fleet-supervisor-readiness", "--store", str(store), "--events", str(events),
              "--run-id", "run-1", "--supervisor-status", "blocked", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked"
    assert report["supervisor_status"] == "blocked"
    assert report["present_components"] == ["supervisor", "event", "reconciliation"]
    assert not store.exists() and not events.exists()


def test_subprocess_missing_roots_creates_no_artifacts(tmp_path):
    store, events = tmp_path / "missing-store", tmp_path / "missing-events"
    result = subprocess.run(
        [sys.executable, str(CLI), "fleet-supervisor-readiness", "--store", str(store),
         "--events", str(events), "--run-id", "run-1", "--json"],
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout)["status"] == "unknown"
    assert not store.exists() and not events.exists()


@pytest.mark.parametrize("args", [
    ["--run-id", "../bad"], ["--run-id", "run-1", "--limit", "0"],
    ["--run-id", "run-1", "--limit", str(MAX_QUERY + 1)],
    ["--run-id", "run-1", "--owner-epoch", "-1"],
    ["--run-id", "run-1", "--supervisor-status", "bogus"],
])
def test_invalid_arguments_fail_closed(tmp_path, args):
    with pytest.raises(SystemExit):
        PD().run(["fleet-supervisor-readiness", "--store", str(tmp_path / "store"),
                  "--events", str(tmp_path / "events")] + args)
    assert not (tmp_path / "store").exists() and not (tmp_path / "events").exists()


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="symlink unavailable")
def test_symlink_component_is_rejected_without_following(tmp_path, capsys):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "events"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(SystemExit):
        PD().run(["fleet-supervisor-readiness", "--store", str(tmp_path / "store"),
                  "--events", str(link), "--run-id", "run-1"])
    assert link.is_symlink()
    assert "symlink" in capsys.readouterr().out
