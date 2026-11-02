#!/usr/bin/env python3
"""Walkthrough ponta-a-ponta do PD, executavel por qualquer pessoa, sem o autor.

Prova, num diretorio descartavel dentro do repo, que o ciclo do CLI fecha:
init -> spec/plan/context -> manifesto com gate de revisao -> bloqueio honesto ->
gate humano com escopo amarrado -> execucao -> complete-task -> checkpoint ->
VERIFICATION.md -> validate 12/12 -> verify.

Uso:
    /usr/bin/python3 examples/walkthrough/run_walkthrough.py [--keep]

Saida: uma linha por passo com PASS/FAIL e o comando equivalente. Exit 0 = ciclo fechou.
O que ele NAO prova esta no README (dispatcher simulado, sem merge/publish/cockpit).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PD = REPO / "scripts" / "pd.py"
PYTHON = "/usr/bin/python3"
WORK = REPO / ".walkthrough"
FEATURE = "demo-walkthrough"

STEPS: list[tuple[str, str]] = []


def run(args: list[str], cwd: Path, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([PYTHON, str(PD), *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != expect:
        raise SystemExit(
            f"comando falhou ({result.returncode}, esperado {expect}): pd {' '.join(args)}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    return result


def check(step: str, ok: bool, detail: str) -> None:
    STEPS.append((step, f"{'PASS' if ok else 'FAIL'}  {detail}"))
    if not ok:
        raise SystemExit(f"passo falhou: {step} — {detail}")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


MANIFEST = """\
schema_version: "1"
agents:
  - id: walkthrough-agent
    role: orchestrator
    capabilities: [planning]
    status: available
waves:
  - id: wave-1
    tasks: [T-001]
    status: pending
    gates: [G1]
tasks:
  - id: T-001
    wave: 1
    role: orchestrator
    objective: deliver the walkthrough artifact
    depends_on: []
    inputs: []
    outputs:
      - name: artifact
        description: a file proving the task ran
        required: true
    acceptance_criteria:
      - artifact exists after the run
    validation_commands:
      - /usr/bin/true
    blocked_when: []
    retry_policy:
      max_attempts: 1
      backoff_seconds: 0
      retryable_errors: []
    owner: walkthrough-agent
    status: pending
gates:
  - id: G1
    kind: review
    scope: plan
    owner: vitor
    status: pending
    required_evidence: [spec]
"""


def main() -> int:
    keep = "--keep" in sys.argv
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    print(f"workspace: {WORK}\n")

    # 1. init
    run(["init", FEATURE], WORK)
    fd = WORK / ".spec" / FEATURE
    check("init", (fd / "STATE.json").exists(), f"pd init {FEATURE}")

    # 2. documentos reais (o que o PD exige para validar)
    write(fd / "SPEC.md", (
        "# SPEC.md — demo-walkthrough\n\n## Problem\n\nProvar que o CLI fecha o ciclo.\n\n"
        "## Requirements (checkable)\n\n"
        "- **R1.** O gate de revisao bloqueia ate existir decisao humana amarrada ao run.\n"
        "- **R2.** Com o gate valido, a task executa e o estado persiste.\n\n"
        "## Success criteria\n\n- [ ] R1 provado pelo bloqueio\n- [ ] R2 provado pela execucao\n"
    ))
    write(fd / "PLAN.md", (
        "# PLAN.md — demo-walkthrough\n\n## Wave 1\n\n"
        "- [ ] T-001 · orchestrator · deliver the walkthrough artifact · deps: G1\n"
        "- [ ] **G1 — revisao humana (owner: quem executa)** — pending.\n"
    ))
    write(fd / "CONTEXT.md", (
        "# Context — demo-walkthrough\n\n## Decisions\n\n"
        "- **D-001** — o gate de revisao e humano e amarrado ao run; nada de bypass.\n"
        "- **D-002** — o criterio de sucesso so vira `[x]` depois da evidencia, nunca antes.\n"
    ))
    write(fd / "plan.yaml", MANIFEST)
    check("docs+manifesto", True, "SPEC/PLAN/CONTEXT/plan.yaml escritos")

    # 3. validate enxerga o manifesto
    out = run(["validate", "--deep", "-f", FEATURE], WORK).stdout
    check("validate le plan.yaml", "plan.yaml manifest" in out, "check de manifesto presente")
    check("validate aponta o que falta", "VERIFICATION.md" in out, "acusa VERIFICATION.md ausente (esperado)")

    # 4. sem gate, a wave bloqueia — e diz como sair
    dry = json.loads(run(["fleet-run", "-f", FEATURE, "--dry-run", "--json", "--run-id", "wt-run-1"], WORK, expect=1).stdout)
    check("gate bloqueia sem decisao", dry["blocked"] == ["T-001"], f"blocked={dry['blocked']}")
    check("o CLI ensina o proximo passo", bool(dry.get("hint")) and "G1" in dry["gate_templates"],
          "hint + gate_template emitidos")

    # 5. decisao humana: o template vira o gate assinado (mesmo run, mesmo escopo)
    gates = dry["gate_templates"]
    gates["G1"]["owner"] = "quem-executa"
    gates["G1"]["identity"] = "quem-executa@local"
    write(fd / "gate.json", json.dumps(gates, indent=2, sort_keys=True))
    check("gate escrito", True, "gate.json com escopo e run do template")

    # 6. gate de outro run continua bloqueado (o escopo vale)
    other = json.loads(run(["fleet-run", "-f", FEATURE, "--dry-run", "--json",
                            "--run-id", "wt-run-2", "--human-gate", str(fd / "gate.json")],
                           WORK, expect=1).stdout)
    check("gate nao serve para outro run", other["blocked"] == ["T-001"], "binding por run respeitado")

    # 7. execucao real
    ran = json.loads(run(["fleet-run", "-f", FEATURE, "--json", "--run-id", "wt-run-1",
                          "--human-gate", str(fd / "gate.json")], WORK).stdout)
    check("execucao com gate valido", ran["status"] == "completed" and ran["completed"] == ["T-001"],
          f"status={ran['status']} completed={ran['completed']}")
    state = json.loads((fd / "STATE.json").read_text())
    persisted = [t.get("status") for t in state.get("fleet_state", {}).get("tasks", [])]
    check("estado persistido", persisted == ["completed"], f"fleet_state={persisted}")

    # 8. fechamento do registro
    run(["complete-task", "-f", FEATURE, "T-001 — walkthrough entregue"], WORK)
    run(["checkpoint", "-f", FEATURE, "--note", "walkthrough executado"], WORK)
    write(fd / "VERIFICATION.md", (
        "# VERIFICATION — demo-walkthrough\n\n## Verified\n\n"
        "- R1: gate bloqueou sem decisao (`blocked=['T-001']`) e recusou gate de outro run.\n"
        "- R2: com gate valido a task completou e `fleet_state` persistiu `completed`.\n"
    ))
    write(fd / "tests" / "test_smoke.py", "def test_walkthrough_artifact():\n    assert True\n")
    # criterios viram [x] so depois da evidencia — a ordem importa
    spec = (fd / "SPEC.md").read_text().replace("- [ ]", "- [x]")
    (fd / "SPEC.md").write_text(spec)

    # 9. portoes finais
    final = run(["validate", "--deep", "-f", FEATURE], WORK).stdout
    check("validate final", "All checks passed (12/12)" in final, "12/12")
    verified = run(["verify", "-f", FEATURE], WORK).stdout
    check("verify final", "All checks passed" in verified, "todos os requisitos fechados")

    print("\n".join(f"{step:28} {status}" for step, status in STEPS))
    print(f"\nCICLO FECHADO — artefatos em {fd}")
    if not keep:
        shutil.rmtree(WORK)
        print("workspace removido (use --keep para inspecionar)")
    return 0


if __name__ == "__main__":
    os.chdir(REPO)
    sys.exit(main())
