"""T2-01: freeze the V2 starting point without changing runtime behavior."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


# This is an intentional, explicit handoff fixture.  A later test-count drift must
# be reported in the handoff, not make this baseline contract fail.
BASELINE_METADATA = {
    "schema_version": "pd-fleet-baseline:v2",
    "baseline_test_count": 278,
    "verification_command": "pytest -q",
}

V1_TO_V2_STATUS = {
    "baseline_compatibility": "verified",
    "dag_readiness_ownership": "partial",
    "deterministic_output": "partial",
    "run_store": "open",
    "checkpoint_persistence": "partial",
    "validation_commands": "partial",
    "agent_report": "partial",
    "parallelism": "open",
    "provider_boundary": "open",
    "metrics_audit": "partial",
    "human_verification": "open",
}

_SAFE_GIT_VALUE = re.compile(r"^[A-Za-z0-9._/@+-]+$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_SHORT_COMMIT_HEX = re.compile(r"^[0-9a-f]{7,40}$")


def _sanitized_git_value(value: str) -> str:
    """Return a single safe git identifier, refusing terminal/control text."""
    candidate = value.strip()
    if not candidate or not _SAFE_GIT_VALUE.fullmatch(candidate):
        raise ValueError("unsafe git metadata")
    return candidate


def _capture_git_metadata(repo_root: Path) -> dict[str, str]:
    def git(*args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("git metadata capture timed out") from exc
        return _sanitized_git_value(result.stdout)

    try:
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("git metadata capture timed out") from exc
    branch = branch_result.stdout.strip() or "HEAD"
    return {"branch": _sanitized_git_value(branch), "commit": git("rev-parse", "HEAD")}


def _global_pass_claim_allowed(metadata: dict[str, Any]) -> bool:
    """A PASS claim needs an explicit, approved human gate and evidence."""
    if metadata.get("status") != "PASS":
        return False
    gate = metadata.get("gate")
    return bool(
        isinstance(gate, dict)
        and gate.get("decision") == "approved"
        and isinstance(gate.get("evidence_digest"), str)
        and _SHA256_HEX.fullmatch(gate["evidence_digest"]) is not None
    )


def test_baseline_metadata_is_explicit_and_reproducible() -> None:
    assert BASELINE_METADATA == {
        "schema_version": "pd-fleet-baseline:v2",
        "baseline_test_count": 278,
        "verification_command": "pytest -q",
    }
    assert BASELINE_METADATA["verification_command"] == "pytest -q"


def test_global_pass_claim_is_rejected_without_approved_gate() -> None:
    assert not _global_pass_claim_allowed({"status": "PASS"})
    assert not _global_pass_claim_allowed(
        {"status": "PASS", "gate": {"decision": "pending", "evidence_digest": "a" * 64}}
    )
    for digest in ("", " " * 64, "a" * 63, "a" * 65, "A" * 64, "sha256:" + "a" * 64):
        assert not _global_pass_claim_allowed(
            {"status": "PASS", "gate": {"decision": "approved", "evidence_digest": digest}}
        )
    assert _global_pass_claim_allowed(
        {"status": "PASS", "gate": {"decision": "approved", "evidence_digest": "a" * 64}}
    )


def test_branch_and_commit_capture_is_sanitized() -> None:
    captured = _capture_git_metadata(Path(__file__).parents[2])
    assert captured["branch"]
    assert _SAFE_GIT_VALUE.fullmatch(captured["branch"])
    assert captured["branch"] == "HEAD" or not captured["branch"].startswith("-")
    assert _SHORT_COMMIT_HEX.fullmatch(captured["commit"])


def test_v1_findings_are_classified_for_v2_without_claiming_completion() -> None:
    allowed = {"verified", "partial", "open", "superseded"}
    assert V1_TO_V2_STATUS
    assert set(V1_TO_V2_STATUS.values()) <= allowed
    assert "open" in V1_TO_V2_STATUS.values()
    assert "superseded" not in V1_TO_V2_STATUS.values()
    assert all(status != "PASS" for status in V1_TO_V2_STATUS.values())
