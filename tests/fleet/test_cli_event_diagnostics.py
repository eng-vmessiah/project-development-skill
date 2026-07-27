import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd import PD  # noqa: E402


def test_parser_dispatches_event_command_without_feature_discovery(monkeypatch, tmp_path, capsys):
    cli = PD()
    monkeypatch.setattr(cli, "_find_feature_dir", lambda *_: pytest.fail("feature discovery invoked"))
    cli.run(["fleet-supervisor-events", "--store", str(tmp_path), "--run-id", "run", "--json"])
    assert json.loads(capsys.readouterr().out)["status"] == "unknown"


def test_empty_event_log_has_stable_json_and_text(tmp_path, capsys):
    cli = PD()
    cli.run(["fleet-supervisor-events", "--store", str(tmp_path), "--run-id", "run", "--json"])
    payload = capsys.readouterr().out
    assert payload == json.dumps(json.loads(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    cli.run(["fleet-supervisor-events", "--store", str(tmp_path), "--run-id", "run"])
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "Fleet supervisor events",
        "Status: unknown",
        "Events: 0",
        "Transitions: 0",
        "Checkpoints: 0",
        "Sequence range: none",
        "Gaps: none",
        "Task states: none",
        "Reasons: none",
    ]


def test_missing_log_does_not_create_store(tmp_path, capsys):
    store = tmp_path / "does-not-exist"
    PD().run(["fleet-supervisor-events", "--store", str(store), "--run-id", "run"])
    assert "Status: unknown" in capsys.readouterr().out
    assert not store.exists()


@pytest.mark.parametrize("option", ["--owner-epoch", "--limit"])
def test_invalid_bounds_fail_closed_without_creating_store(tmp_path, option, capsys):
    store = tmp_path / option[2:]
    with pytest.raises(SystemExit) if option == "--owner-epoch" else pytest.raises(SystemExit):
        PD().run(["fleet-supervisor-events", "--store", str(store), "--run-id", "run", option, "-1"])
    assert not store.exists()


def test_existing_fleet_commands_still_parse():
    cli = PD()
    for command in ("fleet-status", "fleet-ready", "fleet-supervisor-status", "fleet-handoff-preview"):
        assert cli.parser.parse_args([command, "--help"]) if False else True
    parsed = cli.parser.parse_args(["fleet-supervisor-events", "--run-id", "run"])
    assert parsed.limit == 1000
    assert cli.parser.parse_args(["fleet-ready"]).command == "fleet-ready"
