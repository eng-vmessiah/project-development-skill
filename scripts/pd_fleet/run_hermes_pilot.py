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
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # runnable as a plain script: python3 scripts/pd_fleet/run_hermes_pilot.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pd_fleet.dispatch import DispatchResult
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
from pd_fleet.runtime_adapters import create_runtime_adapter
from pd_fleet.sandbox import LocalSandboxRunner

REPO = Path(__file__).resolve().parents[2]
HERMES_EXECUTABLE = "/home/vitor/.local/bin/hermes"
PILOT_MODEL_DEFAULT = "deepseek-v4.1-flash"
PILOT_NAMESPACE = "workspace"
PILOT_TIMEOUT_SECONDS = 120
ADAPTER_NAME = "hermes/openai-codex"

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


def build_adapter(profile: RuntimeProviderProfile):
    return create_runtime_adapter("hermes", profile, CommandMetadata(executable=HERMES_EXECUTABLE))


def task_prompt(task: object, mission: str) -> str:
    objective = " ".join(str(getattr(task, "objective", "")).split())
    acceptance = " ".join(
        " ".join(str(item) for item in (getattr(task, "acceptance_criteria", ()) or ())).split()
    )
    prompt = (
        f"Missao {mission} tarefa {getattr(task, 'id', '?')} (piloto PD Fleet). "
        f"Objetivo: {objective}. Criterios: {acceptance}. "
        "Escreva os artefatos pedidos no diretorio atual e responda com um resumo curto."
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


def build_runner(plan: FleetPlan, profile: RuntimeProviderProfile, adapter: object,
                 model: str, mission: str, output_root: Path,
                 tool_root: Path = REPO) -> LocalSandboxRunner:
    output_root.mkdir(parents=True, exist_ok=True)
    argvs = [adapter.build_argv(build_envelope(task, profile, model, mission))
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
        path_roots={PILOT_NAMESPACE: output_root},
        trusted_executables=[HERMES_EXECUTABLE],
    )


class AdapterDispatchShim:
    """Duck-typed dispatcher: FleetOrchestrator -> named runtime adapter + runner."""

    def __init__(self, adapter: object, runner: LocalSandboxRunner,
                 profile: RuntimeProviderProfile, model: str, mission: str) -> None:
        self.adapter = adapter
        self.runner = runner
        self.profile = profile
        self.model = model
        self.mission = mission

    def dispatch(self, task: object, context: object) -> DispatchResult:
        attempt = context.get("attempt", 1) if isinstance(context, dict) else 1
        task_id = str(getattr(task, "id", "?"))
        try:
            envelope = build_envelope(task, self.profile, self.model, self.mission)
            result = self.adapter.execute(envelope, runner=self.runner)
        except (RuntimeAdapterError, OSError):
            return DispatchResult(task_id, ADAPTER_NAME, "failed", attempt, None,
                                  {"adapter": ADAPTER_NAME}, "pilot dispatch error")
        ok = result.status is RuntimeStatus.OK
        evidence = {
            "adapter": ADAPTER_NAME,
            "runtime_status": result.status.value,
            "error_code": result.error_code.value if result.error_code else None,
        }
        output = {"output": result.output} if ok else None
        return DispatchResult(task_id, ADAPTER_NAME, "completed" if ok else "failed", attempt,
                              output, evidence,
                              None if ok else (result.error_code.value if result.error_code else "failed"))


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
        argv = adapter.build_argv(envelope)
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

        inner = TemplateRuntimeAdapter(adapter.name, profile, adapter._template(envelope),
                                       adapter.command_metadata)  # same-package seam
        bridge_result = inner.dry_run(envelope, bridge=_bridge)
        if bridge_result.status is not RuntimeStatus.OK or captured.get("argv") != adapter._template(envelope):
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
    shim = AdapterDispatchShim(adapter, runner, profile, model, mission)
    run_id = f"pilot-hermes-{mission}"
    orchestrator = FleetOrchestrator(plan, dispatcher=shim, gates={}, run_id=run_id)
    result = orchestrator.run()
    summary = {
        "run_id": run_id,
        "plan": str(plan_path),
        "adapter": ADAPTER_NAME,
        "model": model,
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
