"""Run the PD fleet example locally, without shell, network, or credentials.

The only side effect is writing deterministic JSON files below the explicitly
provided ``--output`` directory.  The module is also importable: ``main``
returns a process-style exit code instead of calling ``sys.exit``.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

# Keep this example runnable directly from a source checkout.
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pd_fleet.contracts import AgentContract, AgentReport  # noqa: E402
from pd_fleet.dispatch import Dispatcher  # noqa: E402
from pd_fleet.evidence import EvidenceRecord  # noqa: E402
from pd_fleet.gates import GatePolicy, GateResult, GateStatus, GateType  # noqa: E402
from pd_fleet.models import FleetPlan  # noqa: E402
from pd_fleet.orchestrator import FleetOrchestrator  # noqa: E402
from pd_fleet.validation import validate_plan  # noqa: E402


def _load_manifest(path: Path) -> Mapping[str, Any]:
    """Load local JSON or YAML; never fetch or execute a manifest."""
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
    elif path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError("YAML exige PyYAML; use um manifest .json") from exc
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ValueError("YAML inválido") from exc
    else:
        raise ValueError("manifest deve ter extensão .json, .yaml ou .yml")
    if not isinstance(data, Mapping):
        raise ValueError("manifest deve ser um objeto")
    return data


def _json_write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _output_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("saída fora do diretório --output") from exc
    return candidate


def _validate_output_root(output_dir: Path) -> Path:
    if output_dir.exists() and output_dir.is_symlink():
        raise ValueError("--output não pode ser um symlink existente")
    return output_dir.resolve(strict=False)


def _identity(prefix: str, key: str) -> str:
    return f"{prefix}:{key}"


def _validated_gate(gate: GateResult, evidence_by_id: Mapping[str, EvidenceRecord],
                    reports_by_id: Mapping[str, AgentReport]) -> GateResult:
    """Validate a GateResult and resolve every referenced record, fail closed."""
    if not isinstance(gate, GateResult):
        raise ValueError("gate deve ser um GateResult validado")
    gate = GateResult.from_dict(gate.to_dict())
    for ref in gate.evidence:
        if type(ref) is not str or ref not in evidence_by_id:
            raise ValueError(f"referência de evidência não resolvida: {ref!r}")
        EvidenceRecord.from_dict(evidence_by_id[ref])
    for ref in gate.reports:
        if type(ref) is not str or ref not in reports_by_id:
            raise ValueError(f"referência de relatório não resolvida: {ref!r}")
        AgentReport.from_dict(reports_by_id[ref])
    return gate


def _contract(plan: FleetPlan, task: Any) -> AgentContract:
    agent_id = task.owner
    if not agent_id:
        owners = [a.id for a in plan.agents if a.role == task.role]
        agent_id = owners[0] if owners else task.role
    return AgentContract(
        task_id=task.id,
        agent_id=agent_id,
        role=task.role,
        capabilities=list(task.capabilities),
        context={"objective": task.objective, "inputs": task.inputs},
        constraints={"acceptance_criteria": list(task.acceptance_criteria)},
        allowed_paths=list(task.allowed_paths),
        forbidden_paths=list(task.forbidden_paths),
        expected_outputs=[asdict(output) for output in task.outputs],
        validation_commands=list(task.validation_commands),
        retry_policy={
            "max_attempts": task.retry_policy.max_attempts,
            "backoff_seconds": task.retry_policy.backoff_seconds,
            "retryable_errors": list(task.retry_policy.retryable_errors),
        },
    )


def _local_evidence(task_id: str, fingerprint: str) -> EvidenceRecord:
    # Declarative evidence: no command is executed. Timestamp is fixed to make
    # repeated runs byte-for-byte reproducible.
    return EvidenceRecord(
        artifacts=[f"results/{task_id}.json"],
        timestamp="2026-01-01T00:00:00Z",
        source="local-simulated",
        stdout=f"simulated result {task_id} {fingerprint[:16]}",
    )


def run(plan_path: Path, output_dir: Path) -> int:
    manifest = _load_manifest(plan_path)
    plan = FleetPlan.from_dict(manifest)
    validation = validate_plan(plan)
    if not validation.valid:
        return 1
    output_dir = _validate_output_root(output_dir)
    if any(not _SAFE_TASK_ID.fullmatch(task.id) for task in plan.tasks):
        raise ValueError("task IDs devem ser um único segmento seguro")
    # Build and validate G1 before the first mkdir: malformed gate data cannot
    # cause writes, and the orchestrator receives a GateResult, never a mapping.
    preflight_ev = _local_evidence("preflight", "plan")
    preflight_report = AgentReport(
        task_id="preflight", agent_id="local-simulated", status="completed",
        outputs={"plan": "validated"}, evidence=[preflight_ev.to_dict()],
        tests=["local-simulated"], decisions=["preflight review"],
        timestamps={"started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:00:00Z"},
    )
    preflight_evidence = {_identity("evidence", "preflight"): preflight_ev}
    preflight_reports = {_identity("report", "preflight"): preflight_report}
    g1 = GateResult(
        gate_id="G1", gate_type=GateType.REVIEW.value, status=GateStatus.PASSED,
        owner="local-simulated", decision="approved", blockers=[],
        evidence=list(preflight_evidence), reports=list(preflight_reports),
        details={"source": "local-preflight"},
    )
    g1 = _validated_gate(g1, preflight_evidence, preflight_reports)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Every file below output_dir is created by this example; input is read-only.
    results_dir = _output_path(output_dir, "results")
    results_dir.mkdir(exist_ok=True)

    contracts = [_contract(plan, task) for task in sorted(plan.tasks, key=lambda t: t.id)]
    _json_write(_output_path(output_dir, "contracts.json"), [c.to_dict() for c in contracts])
    orchestrator = FleetOrchestrator(plan, dispatcher=Dispatcher(), gates={"G1": g1})
    execution = orchestrator.run()

    evidence: list[EvidenceRecord] = []
    reports: list[AgentReport] = []
    by_task = {task.id: task for task in plan.tasks}
    by_contract = {contract.task_id: contract for contract in contracts}
    for task_id in sorted(by_task):
        task = by_task[task_id]
        task_reports = [r for r in execution.reports if r.get("task_id") == task_id]
        raw = task_reports[-1] if task_reports else {"status": execution.statuses[task_id]}
        fingerprint = str((raw.get("evidence") or {}).get("fingerprint", "none"))
        ev = _local_evidence(task_id, fingerprint)
        evidence.append(ev)
        result_payload = {"task_id": task_id, "status": execution.statuses[task_id], "report": raw}
        _json_write(_output_path(output_dir, f"results/{task_id}.json"), result_payload)
        contract = by_contract[task_id]
        reports.append(AgentReport(
            task_id=task_id,
            agent_id=contract.agent_id,
            status=execution.statuses[task_id],
            outputs=(raw.get("output") or {}),
            evidence=[ev.to_dict()],
            tests=["local-simulated"],
            blockers=[] if execution.statuses[task_id] == "completed" else ["task-not-completed"],
            decisions=["simulated dispatcher; no external calls"],
            timestamps={"started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:00:00Z"},
        ))
    report_dicts = [r.to_dict() for r in reports]
    _json_write(_output_path(output_dir, "reports.json"), report_dicts)
    _json_write(_output_path(output_dir, "evidence.json"), [e.to_dict() for e in evidence])

    all_completed = all(status == "completed" for status in execution.statuses.values())
    gate_results: list[GateResult] = []
    for gate_type in GateType:
        passed = all_completed and bool(reports) and all(r.status == "completed" for r in reports)
        gate_results.append(GateResult(
            gate_id=f"local-{gate_type.value}", gate_type=gate_type.value,
            status=GateStatus.PASSED if passed else GateStatus.FAILED,
            owner="local-simulated", decision="passed" if passed else "failed",
            blockers=[] if passed else ["execution-not-completed"],
            evidence=[_identity("evidence", task_id) for task_id in sorted(by_task)],
            reports=[_identity("report", task_id) for task_id in sorted(by_task)],
            details={"source": "local-results", "tasks": sorted(by_task)},
        ))
    evidence_by_id = {_identity("evidence", task_id): ev for task_id, ev in zip(sorted(by_task), evidence)}
    reports_by_id = {_identity("report", task_id): report for task_id, report in zip(sorted(by_task), reports)}
    gate_results = [_validated_gate(gate, evidence_by_id, reports_by_id) for gate in gate_results]
    policy = GatePolicy()
    gate_dicts = [g.to_dict() for g in gate_results]
    _json_write(_output_path(output_dir, "gates.json"), gate_dicts)
    summary = {"statuses": execution.to_dict(), "gates": gate_dicts,
               "gate_statuses": {g.gate_id: policy.evaluate(g).value for g in gate_results}}
    _json_write(_output_path(output_dir, "summary.json"), summary)
    return 0 if all(policy.allows(g) for g in gate_results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executa o exemplo PD fleet somente localmente")
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("plan.yaml"))
    parser.add_argument("--output", type=Path, required=True, help="diretório de saída explícito")
    args = parser.parse_args(argv)
    try:
        return run(args.plan, args.output)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
