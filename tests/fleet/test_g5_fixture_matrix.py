from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2]))
from scripts.pd_fleet.run_g5_fixture_matrix import _row, run


def test_g5_report_is_deterministic_fake_only_and_complete():
    first = run()
    second = run()
    assert first == second
    assert first["valid"] is True
    assert first["FAKE_ONLY"] is True
    assert first["hermes_live"] is False
    assert first["network"] is False
    assert first["subprocess"] is False
    assert first["hermes_state_db_access"] is False
    assert first["local_bridge_journal_access"] is True
    assert first["provider_access"] is False
    assert first["control_plane_access"] is False
    assert first["credentials_access"] is False
    assert first["summary"]["failed"] == 0
    ids = {row["scenario_id"] for row in first["negative"]}
    assert len(ids) >= 38
    for required in (
        "activation_malformed_ticket", "activation_expired_ticket", "activation_replayed_ticket",
        "activation_wrong_purpose", "activation_wrong_owner", "activation_wrong_profile",
        "activation_wrong_workspace", "activation_wrong_session", "activation_wrong_association",
        "fleet_owned_task", "wrong_observer", "forged_cursor_subscriber", "forged_cursor_association",
        "forged_cursor_epoch", "forged_cursor_epoch_replay", "expired_cursor", "replay_gap", "replay_out_of_order",
        "duplicate_event_id", "malformed_upstream_event", "malformed_upstream_result",
        "malformed_upstream_snapshot", "detach_malformed_provenance", "detach_wrong_provenance",
        "replay_bound_exceeded", "no_cursor_advance_on_failure", "stale_association",
        "gateway_reset", "store_schema_corruption", "store_ack_unknown", "store_commit_closed",
    ):
        assert required in ids
    assert first["positive"]["stages"][-1] == "reopen_store"
    assert first["positive"]["observed_persisted_status"] == "detached"
    assert first["positive"]["ack_persisted"] is True
    assert all(row["invariant_verified"] for row in first["negative"])


def test_g5_runner_has_no_live_or_control_imports_and_no_state_db_access():
    path = Path(__file__).parents[2] / "scripts/pd_fleet/run_g5_fixture_matrix.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports & {"hermes", "requests", "httpx", "aiohttp", "websockets", "socket", "subprocess"}
    assert "hermes_state_db_access" in source
    assert "FAKE_ONLY" in source


def test_report_rows_are_machine_readable():
    report = run()
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    decoded = json.loads(encoded)
    assert decoded["summary"]["scenario_count"] == 1 + len(decoded["negative"])
    assert all(set(row) >= {"scenario_id", "expected_error", "observed_error", "persisted_state_invariant"}
               for row in decoded["negative"])


def test_failure_mutation_is_not_hidden_by_successful_prelude():
    initial = {"digest": "initial", "counts": {"events": 0}}
    checkpoint = {"digest": "checkpoint", "counts": {"events": 1}}
    mutated = {"digest": "mutated", "counts": {"events": 2}}
    row = _row("synthetic", "invalid_provenance", "invalid_provenance", "reason", None,
               initial, checkpoint, mutated, "prelude checkpoint is unchanged by failed operation")
    assert row["state_initial"] == initial
    assert row["state_before_failure"] == checkpoint
    assert row["state_after"] == mutated
    assert row["invariant_verified"] is False
    assert row["passed"] is False
