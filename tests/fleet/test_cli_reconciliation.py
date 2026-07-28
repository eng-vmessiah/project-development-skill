"""E8 CLI tests for read-only run/event reconciliation."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from pd import PD  # noqa: E402
from pd_fleet.events import EventLog, FleetEvent, MAX_QUERY  # noqa: E402
from pd_fleet.run_store import FleetRunStore  # noqa: E402


def _event(sequence: int = 1) -> FleetEvent:
    return FleetEvent(
        event_id=f"event-{sequence}", run_id="run-1", kind="test.event",
        ordering_key=f"event-{sequence}", sequence=sequence, owner_epoch=7,
        payload={}, created_at="2026-01-01T00:00:00+00:00",
    )


def _matching_sources(tmp_path: Path) -> tuple[Path, Path]:
    store_root, events_root = tmp_path / "store", tmp_path / "events"
    store = FleetRunStore(store_root)
    try:
        store.create("run-1", {"schema_version": "pd-fleet-plan:v2", "tasks": []}, "owner")
        store.append_event("run-1", {"event_id": "event-1", "ordering_key": "event-1"}, "owner")
    finally:
        store.close()
    EventLog(events_root, "run-1", owner_epoch=7).append(_event())
    return store_root, events_root


def test_matching_json_is_exact_sorted_report_without_feature_discovery(tmp_path, monkeypatch, capsys):
    store, events = _matching_sources(tmp_path)
    cli = PD()
    monkeypatch.setattr(cli, "_find_feature_dir", lambda *_: pytest.fail("feature discovery invoked"))
    cli.run(["fleet-supervisor-reconcile", "--store", str(store), "--events", str(events),
             "--run-id", "run-1", "--owner-epoch", "7", "--json"])
    payload = capsys.readouterr().out
    assert payload == json.dumps(json.loads(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert json.loads(payload) == {
        "event_log_count": 1, "event_log_last_sequence": 1, "reasons": [],
        "run_id": "run-1", "snapshot_generation": 1, "snapshot_status": "created",
        "status": "consistent", "store_event_sequence": 1,
    }


def test_absent_sources_are_unknown_and_not_created(tmp_path, capsys):
    store, events = tmp_path / "missing-store", tmp_path / "missing-events"
    PD().run(["fleet-supervisor-reconcile", "--store", str(store), "--events", str(events),
              "--run-id", "run-1"])
    output = capsys.readouterr().out
    assert output.splitlines() == [
        "Fleet supervisor reconciliation", "Status: unknown", "Run: run-1",
        "Snapshot status: none", "Generation: none", "Store sequence: none",
        "Log count: 0", "Last sequence: none", "Reasons: none",
    ]
    assert not store.exists() and not events.exists()


def test_missing_store_with_empty_existing_log_is_degraded_without_store_writes(tmp_path, capsys, monkeypatch):
    store = tmp_path / "missing-store"
    events = tmp_path / "events" / "run-1"
    events.mkdir(parents=True)
    (events / "events.jsonl").touch()

    def fail_constructor(*args, **kwargs):
        pytest.fail("FleetRunStore must not be instantiated for an absent root")

    monkeypatch.setattr("pd.FleetRunStore", fail_constructor)
    PD().run(["fleet-supervisor-reconcile", "--store", str(store), "--events", str(tmp_path / "events"),
              "--run-id", "run-1", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "degraded"
    assert report["reasons"] == ["missing_store_snapshot"]
    assert report["event_log_count"] == 0
    assert not store.exists()


def test_missing_store_race_content_is_never_cleaned_up(tmp_path, capsys, monkeypatch):
    store = tmp_path / "missing-store"
    events = tmp_path / "missing-events"

    def raced_absence(path):
        store.mkdir()
        (store / "raced-content").write_text("keep", encoding="utf-8")
        return False

    monkeypatch.setattr(PD, "_path_exists_without_following", staticmethod(raced_absence))
    PD().run(["fleet-supervisor-reconcile", "--store", str(store), "--events", str(events),
              "--run-id", "run-1"])
    capsys.readouterr()
    assert (store / "raced-content").read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unavailable")
@pytest.mark.parametrize("which", ["store", "events"])
def test_reconcile_rejects_symlink_root_without_following_or_writing(tmp_path, which, capsys):
    real = tmp_path / f"real-{which}"
    real.mkdir()
    link = tmp_path / which
    link.symlink_to(real, target_is_directory=True)
    store = link if which == "store" else tmp_path / "store"
    events = link if which == "events" else tmp_path / "events"

    with pytest.raises(SystemExit):
        PD().run(["fleet-supervisor-reconcile", "--store", str(store), "--events", str(events),
                  "--run-id", "run-1"])
    assert link.is_symlink()
    assert not (real / ".run_store.lock").exists()
    assert "symlink" in capsys.readouterr().out


def test_parser_defaults_and_completion_entries():
    parsed = PD().parser.parse_args(["fleet-supervisor-reconcile", "--run-id", "run-1"])
    assert parsed.store_root == ".pd-fleet-store"
    assert parsed.events_root == ".pd-fleet-events"
    assert parsed.limit == MAX_QUERY
    for shell in ("bash", "zsh", "fish"):
        # Completion output is generated without feature discovery.
        PD().run(["completion", shell])


@pytest.mark.parametrize("args", [
    ["--run-id", "../bad"], ["--run-id", "run", "--limit", "0"],
    ["--run-id", "run", "--limit", str(MAX_QUERY + 1)],
    ["--run-id", "run", "--owner-epoch", "-1"],
])
def test_invalid_arguments_fail_closed(tmp_path, args):
    with pytest.raises(SystemExit):
        PD().run(["fleet-supervisor-reconcile", "--store", str(tmp_path / "store"),
                  "--events", str(tmp_path / "events")] + args)
    assert not (tmp_path / "store").exists()
    assert not (tmp_path / "events").exists()
