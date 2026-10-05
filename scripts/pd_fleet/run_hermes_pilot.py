#!/usr/bin/env python3
"""Thin Hermes pilot runner — explicit, opt-in real dispatch for the PD Fleet.

SMOKE (default): builds profile/command/envelopes/argv for every task of a
FleetPlan and proves the fail-closed boundary — executing without an injected
sandbox runner raises ``RuntimeRunnerRequiredError``, and the test-only bridge
returns the exact argv.  No subprocess is ever spawned in smoke mode.

LIVE (``--live --authorized``): requires the owner's explicit authorization (G2).
Builds the ``LocalSandboxRunner`` (exact-argv allowlist, pinned trusted hermes
executable, provider network on) and runs the plan through ``FleetOrchestrator``
with a real dispatch shim that executes each task via the named runtime adapter.

Usage:
  python3 scripts/pd_fleet/run_hermes_pilot.py --smoke [--plan PATH] [--model M]
  python3 scripts/pd_fleet/run_hermes_pilot.py --live --authorized --plan PATH --output DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):  # runnable as a plain script: python3 scripts/pd_fleet/run_hermes_pilot.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pd_fleet.dispatch import DispatchResult
from pd_fleet.gates import HumanVerificationGate
from pd_fleet.models import FleetPlan
from pd_fleet.orchestrator import FleetOrchestrator
from pd_fleet.provider import CommandMetadata, RuntimePolicy, RuntimeProviderProfile
from pd_fleet.runtime_adapter import (
    RuntimeAdapterError,
    RuntimeRunnerRequiredError,
    RuntimeStatus,
    RuntimeTaskEnvelope,
    TemplateRuntimeAdapter,
)
from pd_fleet.sandbox import LocalSandboxRunner

REPO = Path(__file__).resolve().parents[2]
HERMES_EXECUTABLE = "/home/vitor/.local/bin/hermes"
PILOT_MODEL_DEFAULT = "deepseek-v4.1-flash"
PILOT_PROVIDER = "opencode-go"
PILOT_NAMESPACE = "workspace"
PILOT_TIMEOUT_SECONDS = 120
ADAPTER_NAME = f"hermes/{PILOT_PROVIDER}"
PILOT_TEMPLATE = (
    "hermes", "chat", "-q", "{prompt}", "--provider", PILOT_PROVIDER, "--model",
    "{model}", "-Q", "--safe-mode", "--ignore-rules", "--max-turns", "8",
)

_META_CHARS = ";&|<>$`\n\r"


def build_profile() -> RuntimeProviderProfile:
    """READY profile: policy on, auth ref declared, provider network opt-in."""
    return RuntimeProviderProfile(
        provider_name="hermes",
        runtime_name="openai-codex",
        auth_ref="runtime:default",
        capabilities=("provider_network",),
        command=CommandMetadata(executable=HERMES_EXECUTABLE),
        policy=RuntimePolicy(enabled=True, allow_provider_network=True,
                             allowed_capabilities=("provider_network",)),
    )


def build_adapter(profile: RuntimeProviderProfile) -> TemplateRuntimeAdapter:
    """Pilot command contract: hermes CLI pinned to the cheap provider (opencode-go)."""
    return TemplateRuntimeAdapter(ADAPTER_NAME, profile, PILOT_TEMPLATE,
                                  CommandMetadata(executable=HERMES_EXECUTABLE))


def executed_argv(adapter: TemplateRuntimeAdapter,
                  envelope: RuntimeTaskEnvelope) -> tuple[str, ...]:
    """The exact argv the sandbox runner will receive (executable substituted)."""
    return (HERMES_EXECUTABLE,) + adapter.build_argv(envelope)[1:]


def _enum_value(value: object) -> str | None:
    """Enum-or-str-or-None -> plain string (RuntimeResult fields are unions)."""
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def task_prompt(task: object, mission: str) -> str:
    objective = " ".join(str(getattr(task, "objective", "")).split())
    acceptance = " ".join(
        " ".join(str(item) for item in (getattr(task, "acceptance_criteria", ()) or ())).split()
    )
    paths = [str(path) for path in (getattr(task, "allowed_paths", ()) or ())]
    names = [str(getattr(spec, "name", "")) for spec in (getattr(task, "outputs", ()) or ())]
    if paths:
        target = paths[0].replace("\\", "/").rsplit("/", 1)[-1]
    else:
        target = f"{names[0]}.md" if names else "artefato.md"
    prompt = (
        f"Missao {mission} tarefa {getattr(task, 'id', '?')} (piloto PD Fleet). "
        f"Objetivo: {objective}. Criterios: {acceptance}. "
        f"Acao obrigatoria AGORA: use a ferramenta de escrita para criar o arquivo {target} "
        "no diretorio atual com um conteudo curto e honesto que atenda aos criterios. "
        "Nao leia arquivos. Responda com um resumo de uma linha."
    )
    # The sandbox and the adapter both reject shell metacharacters in argv.
    return prompt.translate(str.maketrans({c: " " for c in _META_CHARS}))


def build_envelope(task: object, profile: RuntimeProviderProfile, model: str,
                   mission: str) -> RuntimeTaskEnvelope:
    return RuntimeTaskEnvelope(
        str(getattr(task, "id", "?")),
        task_prompt(task, mission),
        profile,
        (f"{PILOT_NAMESPACE}/",),
        ("provider_network",),
        metadata={"model": model, "timeout_seconds": PILOT_TIMEOUT_SECONDS},
    )


def load_plan(plan_path: Path) -> FleetPlan:
    raw = plan_path.read_text(encoding="utf-8")
    if plan_path.suffix.lower() == ".json":
        data = json.loads(raw)
    else:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - environment check
            raise SystemExit("PyYAML é necessário para ler o FleetPlan (.yaml)") from exc
        data = yaml.safe_load(raw)
    return FleetPlan.from_dict(data)


def mission_name(plan_path: Path) -> str:
    return plan_path.parent.name or plan_path.stem


def build_runner(plan: FleetPlan, profile: RuntimeProviderProfile,
                 adapter: TemplateRuntimeAdapter,
                 model: str, mission: str, output_root: Path,
                 tool_root: Path = REPO) -> LocalSandboxRunner:
    output_root.mkdir(parents=True, exist_ok=True)
    argvs = [executed_argv(adapter, build_envelope(task, profile, model, mission))
             for task in plan.tasks]
    env = {
        "PATH": "/home/vitor/.local/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/home/vitor",
        "LANG": "C.UTF-8",
    }
    return LocalSandboxRunner(
        tool_root,
        allowlist=argvs,
        env=env,
        network=True,
        path_roots={PILOT_NAMESPACE: str(output_root)},
        trusted_executables=[HERMES_EXECUTABLE],
    )


class AdapterDispatchShim:
    """Duck-typed dispatcher: FleetOrchestrator -> named runtime adapter + runner."""

    def __init__(self, adapter: TemplateRuntimeAdapter, runner: LocalSandboxRunner,
                 profile: RuntimeProviderProfile, model: str, mission: str,
                 output_root: Path | None = None) -> None:
        self.adapter = adapter
        self.runner = runner
        self.profile = profile
        self.model = model
        self.mission = mission
        self.output_root = output_root

    def _dir_snapshot(self) -> set[str]:
        if self.output_root is None or not self.output_root.exists():
            return set()
        return {entry.name for entry in self.output_root.iterdir() if entry.is_file()}

    def _log_entry(self, entry: dict[str, object]) -> None:
        if self.output_root is None:
            return
        try:
            with (self.output_root / "dispatch-log.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def dispatch(self, task: object, context: object) -> DispatchResult:
        attempt = context.get("attempt", 1) if isinstance(context, dict) else 1
        task_id = str(getattr(task, "id", "?"))
        started_at = datetime.now(timezone.utc).isoformat()
        before = self._dir_snapshot()
        try:
            envelope = build_envelope(task, self.profile, self.model, self.mission)
            result = self.adapter.execute(envelope, runner=self.runner)
        except (RuntimeAdapterError, OSError) as exc:
            self._log_entry({"task_id": task_id, "attempt": attempt, "ok": False, "model": self.model,
                             "error": f"{type(exc).__name__}: {exc}", "started_at": started_at,
                             "completed_at": datetime.now(timezone.utc).isoformat()})
            return DispatchResult(task_id, ADAPTER_NAME, "failed", attempt, None,
                                  {"adapter": ADAPTER_NAME,
                                   "acceptance": {"passed": False, "method": "runtime-exit-ok"}},
                                  "pilot dispatch error")
        ok = result.status is RuntimeStatus.OK
        error_value = _enum_value(result.error_code)
        new_files = sorted(self._dir_snapshot() - before)
        output_text = result.output if isinstance(result.output, str) else ""
        self._log_entry({"task_id": task_id, "attempt": attempt, "ok": ok, "model": self.model,
                         "runtime_status": _enum_value(result.status),
                         "error_code": error_value, "artifacts": new_files,
                         "output": output_text[:4000], "started_at": started_at,
                         "completed_at": datetime.now(timezone.utc).isoformat()})
        evidence = {
            "adapter": ADAPTER_NAME,
            "runtime_status": _enum_value(result.status),
            "error_code": error_value,
            "model": self.model,
            "artifacts": new_files,
            "acceptance": {"passed": bool(ok), "method": "runtime-exit-ok",
                           "note": "pilot acceptance proxy; artifacts recorded for review"},
        }
        names = [str(getattr(spec, "name", "")) for spec in (getattr(task, "outputs", ()) or ())]
        if ok and len(names) == 1:
            output: object = {names[0]: result.output}
        else:
            output = result.output if ok else None
        return DispatchResult(task_id, ADAPTER_NAME, "completed" if ok else "failed", attempt,
                              output, evidence,
                              None if ok else (error_value or "failed"))


def run_smoke(plan_path: Path, model: str) -> int:
    plan = load_plan(plan_path)
    mission = mission_name(plan_path)
    profile = build_profile()
    adapter = build_adapter(profile)
    print(f"plan: {plan_path} ({len(plan.tasks)} tasks) | adapter: {adapter.name} "
          f"| readiness: {profile.readiness_status.value}")
    failures = 0
    for task in plan.tasks:
        envelope = build_envelope(task, profile, model, mission)
        argv = executed_argv(adapter, envelope)
        try:
            adapter.execute(envelope, runner=None)
        except RuntimeRunnerRequiredError:
            pass
        else:
            print(f"  {task.id}: ERRO — executou sem runner (esperado fail-closed)")
            failures += 1
            continue
        captured: dict[str, object] = {}

        def _bridge(value: object, envelope: object = None,
                    _captured: dict[str, object] = captured) -> str:
            _captured["argv"] = value
            return "ok"

        bridge_result = adapter.dry_run(envelope, bridge=_bridge)
        if (bridge_result.status is not RuntimeStatus.OK
                or captured.get("argv") != adapter.build_argv(envelope)):
            print(f"  {task.id}: ERRO — bridge não reproduziu o argv")
            failures += 1
            continue
        print(f"  {task.id}: fail-closed OK | argv[0]={argv[0]} | prompt {len(argv[3])} chars "
              f"| model {model}")
    if failures:
        print(f"❌ smoke: {failures} falha(s)")
        return 1
    print("✅ smoke OK — nenhum subprocesso executado")
    return 0


def run_live(plan_path: Path, model: str, output_root: Path) -> int:
    plan = load_plan(plan_path)
    mission = mission_name(plan_path)
    profile = build_profile()
    adapter = build_adapter(profile)
    runner = build_runner(plan, profile, adapter, model, mission, output_root)
    shim = AdapterDispatchShim(adapter, runner, profile, model, mission, output_root=output_root)
    run_id = f"pilot-hermes-{mission}"
    orchestrator = FleetOrchestrator(plan, dispatcher=shim, gates={}, run_id=run_id)
    now = datetime.now(timezone.utc)
    gate = HumanVerificationGate(
        owner="vitor",
        identity="vitor",
        decision="APPROVED",
        scope={"schema_version": "pd-fleet-gate-scope:v1",
               "plan_hash": orchestrator.plan_hash(),
               "tasks": sorted(task.id for task in plan.tasks),
               "waves": sorted({str(task.wave) for task in plan.tasks})},
        run=orchestrator.run_id,
        evidence_digest=hashlib.sha256(
            (REPO / ".spec/plan-cockpit-v1/PILOT-PLAN.md").read_bytes()).hexdigest(),
        artifact_digest=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        created_at=now, updated_at=now, freshness_window=timedelta(hours=1),
    )
    orchestrator.gates = {"G1": gate}
    result = orchestrator.run()
    summary = {
        "run_id": run_id,
        "plan": str(plan_path),
        "adapter": ADAPTER_NAME,
        "model": model,
        "gates": {"G1": "pre-approved for the pilot run (owner G2 authorization)"},
        "statuses": {key: result.statuses[key] for key in sorted(result.statuses)},
        "completed": sorted(result.completed),
        "blocked": sorted(result.blocked),
        "failed": sorted(result.failed),
    }
    out = output_root / "summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"🚁 pilot run {run_id}: {summary['statuses']}")
    print(f"wrote {out}")
    return 0 if not result.failed and not result.blocked else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", default=str(REPO / "examples/pd-fleet/plan.yaml"))
    ap.add_argument("--model", default=PILOT_MODEL_DEFAULT)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--smoke", action="store_true",
                      help="build + prove argv, no execution (default)")
    mode.add_argument("--live", action="store_true",
                      help="real dispatch — requires --authorized (G2)")
    ap.add_argument("--authorized", action="store_true",
                    help="explicit owner authorization marker for --live")
    ap.add_argument("--output", default=str(REPO / ".spec/pilot-runs/hermes"))
    args = ap.parse_args(argv)
    plan_path = Path(args.plan).expanduser()
    if not plan_path.is_absolute():
        plan_path = (REPO / plan_path).resolve()
    if args.live:
        if not args.authorized:
            print("❌ --live exige --authorized (G2: autorização explícita do owner com custo declarado)")
            return 2
        return run_live(plan_path, args.model, Path(args.output).expanduser())
    return run_smoke(plan_path, args.model)


if __name__ == "__main__":
    sys.exit(main())
