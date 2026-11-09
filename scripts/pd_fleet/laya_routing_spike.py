#!/usr/bin/env python3
"""Laya routing spike (T-203) — advisory slots for activity routing, on real events.

Two typed slots evaluated over REAL bus events (~/.hermes/activity/events.jsonl):
  - sink (choice): stream_only | ledger | ledger_notify
  - notify (noul): P(this event should interrupt the human within the hour)
Compared against a deterministic baseline rule (code-owned). ADVISORY ONLY — zero wire:
nothing here routes, persists, or notifies; it measures and logs decisions
(calibration-dataset seed; thresholds must be re-derived per backend).

Run:  python3 scripts/pd_fleet/laya_routing_spike.py              # real Laya
      python3 scripts/pd_fleet/laya_routing_spike.py --backend stub   # tests only
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_BUS = Path.home() / ".hermes" / "activity" / "events.jsonl"
DEFAULT_OUT = REPO / ".spec" / "pd-fleet-control-plane-v1" / "spike-laya"

QUESTIONS = {
    "sink": {
        "type": "choice",
        "instructions": ("For the activity event described above, which persistence set fits "
                         "best? Answer from the facts given."),
        "criteria": {
            "stream_only": "Ephemeral: live surface only; nothing persisted beyond the stream.",
            "ledger": "Persist one durable ledger entry for audit or replay.",
            "ledger_notify": "Persist to the ledger and notify the human now (attention-worthy).",
        },
    },
    "notify": {
        "type": "noul",
        "instructions": "Should this event interrupt the human with a notification within the hour?",
    },
}


def baseline_sink(ev: dict) -> str:
    """Current deterministic rule (code-owned; the comparison anchor)."""
    if ev.get("kind") == "heartbeat":
        return "stream_only"
    st = ev.get("status")
    if st in ("failed", "blocked"):
        return "ledger_notify"
    if st == "done":
        return "ledger"
    return "stream_only"


def baseline_notify(ev: dict) -> float:
    return 1.0 if ev.get("status") in ("failed", "blocked") else 0.0


def features(ev: dict, now: datetime, similar: int | None = None) -> str:
    """All features computed in code (the model cannot count or do arithmetic)."""
    age_min = None
    try:
        age_min = max(0.0, (now - datetime.fromisoformat(str(ev.get("ts")))).total_seconds() / 60.0)
    except ValueError:
        pass
    meta = ev.get("meta") or {}
    bits = [f"kind={ev.get('kind')}", f"agent={ev.get('agent_id')}",
            f"status={ev.get('status') or '-'}", f"action={ev.get('action') or '-'}"]
    if age_min is not None:
        bits.append(f"age_min={age_min:.0f}")
    for key in ("msgs", "tools", "model", "host"):
        if meta.get(key) is not None:
            bits.append(f"{key}={meta[key]}")
    if similar and similar > 1:
        bits.append(f"similar_events_in_batch={similar}")
    return "Activity event: " + " | ".join(bits) + "."


def find_env_python() -> str:
    candidates = sorted(glob.glob(str(Path.home() / ".hermes/installs/*/environments/*/venv/bin/python")), reverse=True)
    probe = "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('hermes_laya') and importlib.util.find_spec('laya') else 1)"
    for cand in candidates:
        try:
            out = subprocess.run([cand, "-c", probe], capture_output=True, timeout=60, check=False)
            if out.returncode == 0:
                return cand
        # The routing probe records arbitrary backend failures instead of aborting the probe.
        except Exception:  # noqa: BLE001, S112
            continue
    raise SystemExit("nenhum env com laya+hermes_laya encontrado — use --env-python")


def run_backend_real(reqs: list[dict], env_python: str) -> tuple[list[dict], list[dict]]:
    with tempfile.TemporaryDirectory() as td:
        inp, out = Path(td) / "req.json", Path(td) / "res.json"
        payload = {"requests": [{"id": r["id"], "state": r["state"], "questions": r["questions"]}
                                for r in reqs]}
        inp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [env_python, str(Path(__file__).parent / "laya_backend.py"),
             "--in", str(inp), "--out", str(out)],
            capture_output=True, text=True, timeout=900, check=False,
            env={"PATH": "/usr/bin:/bin", "HF_HUB_OFFLINE": "1", "HOME": str(Path.home())},
        )
        if not out.exists():
            raise SystemExit(f"laya_backend falhou (rc={proc.returncode}): {proc.stderr[-500:]}")
        data = json.loads(out.read_text(encoding="utf-8"))
    return data.get("results", []), data.get("errors", [])


def run_backend_stub(reqs: list[dict]) -> tuple[list[dict], list[dict]]:
    """TEST-ONLY stub: echoes the baseline (pipeline validation, no model)."""
    results = []
    for r in reqs:
        ev = r["__ev"]
        results.append({"id": r["id"],
                        "answers": {"sink": {"choice": baseline_sink(ev), "answer_confidence": 1.0},
                                    "notify": {"noul": baseline_notify(ev), "confidence": 1.0}},
                        "latency_ms": 0.0, "backend": "stub", "model": "stub"})
    return results, []


def run(bus: Path, out_dir: Path, backend: str = "real", limit: int = 25,
        env_python: str | None = None) -> dict:
    events = []
    if bus.exists():
        for line in bus.read_text(encoding="utf-8").strip().splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("source") == "hermes":
                events.append(ev)
    events = events[-limit:]
    if not events:
        raise SystemExit("sem eventos no bus — rode scripts/pd_fleet/activity_emit.py primeiro")

    now = datetime.now(timezone.utc)
    counts: dict[str, int] = {}
    for ev in events:
        counts[str(ev.get("agent_id"))] = counts.get(str(ev.get("agent_id")), 0) + 1
    reqs = []
    for i, ev in enumerate(events):
        reqs.append({
            "id": str(ev.get("event_id") or f"ev{i}"),
            "state": features(ev, now, counts.get(str(ev.get("agent_id")))),
            "questions": QUESTIONS,
            "__ev": ev,
        })

    if backend == "stub":
        results, errors = run_backend_stub(reqs)
    else:
        results, errors = run_backend_real(reqs, env_python or find_env_python())
    by_id = {r["id"]: r for r in results}

    rows = []
    for r in reqs:
        res = by_id.get(r["id"])
        if res is None:
            continue
        ev = r["__ev"]
        ans = res.get("answers") or {}
        sink_ans = ans.get("sink") or {}
        notify_ans = ans.get("notify") or {}
        p_notify = notify_ans.get("noul")
        if p_notify is None:
            p_notify = notify_ans.get("probability")
        if p_notify is None:
            p_notify = notify_ans.get("p")
        laya_sink = sink_ans.get("choice")
        b_sink, b_notify = baseline_sink(ev), baseline_notify(ev)
        rows.append({
            "event_id": r["id"], "agent": ev.get("agent_id"), "ts": ev.get("ts"),
            "kind": ev.get("kind"), "status": ev.get("status"), "action": ev.get("action"),
            "similar_in_batch": counts.get(str(ev.get("agent_id"))),
            "baseline_sink": b_sink, "laya_sink": laya_sink,
            "laya_sink_confidence": sink_ans.get("answer_confidence"),
            "laya_sink_probabilities": sink_ans.get("probabilities"),
            "agree_sink": (laya_sink == b_sink) if laya_sink else None,
            "baseline_notify": b_notify, "laya_p_notify": p_notify,
            "laya_notify_confidence": notify_ans.get("confidence"),
            "agree_notify": ((float(p_notify) >= 0.5) == (b_notify >= 0.5)) if p_notify is not None else None,
            "latency_ms": res.get("latency_ms"), "backend": res.get("backend"), "model": res.get("model"),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decisions.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8")

    lat = [r["latency_ms"] for r in rows if isinstance(r["latency_ms"], (int, float))]
    sink_ok = [r for r in rows if r["agree_sink"] is not None]
    notif_ok = [r for r in rows if r["agree_notify"] is not None]
    pct = lambda ok, tot: f"{(100.0 * ok / tot):.0f}%" if tot else "n/a"
    meta0 = rows[0] if rows else {}
    summary = {
        "n_events": len(rows), "errors": errors,
        "backend": meta0.get("backend"), "model": meta0.get("model"),
        "sink_agreement": [sum(1 for r in sink_ok if r["agree_sink"]), len(sink_ok)],
        "notify_agreement": [sum(1 for r in notif_ok if r["agree_notify"]), len(notif_ok)],
        "latency_ms": {"min": min(lat), "median": statistics.median(lat), "max": max(lat)} if lat else None,
    }
    disagreements = [r for r in rows if r["agree_sink"] is False]
    lines = [
        "# Laya routing spike — RESULTS (T-203)",
        "",
        f"- **Run:** {now.isoformat(timespec='seconds')} · backend `{summary['backend']}` · model `{summary['model']}`",
        f"- **N events:** {summary['n_events']} (bus `~/.hermes/activity/events.jsonl`, fonte `hermes`)",
        (f"- **Sink agreement vs baseline:** {summary['sink_agreement'][0]}/{summary['sink_agreement'][1]} "
         f"({pct(summary['sink_agreement'][0], summary['sink_agreement'][1])})"),
        (f"- **Notify agreement vs baseline (p>=0.5):** {summary['notify_agreement'][0]}/{summary['notify_agreement'][1]} "
         f"({pct(summary['notify_agreement'][0], summary['notify_agreement'][1])})"),
        f"- **Latency:** {summary['latency_ms']}",
        "",
        "## Caveats (não negociáveis)",
        "- Laya é **zero-shot fraca** aqui (base de fine-tune) — concordância mede alinhamento com a regra atual, não verdade.",
        "- Threshold 0.5 **não calibrado** — re-derivar por backend antes de qualquer uso com qualidade.",
        "- **Zero wire:** nada roteia/persiste/notifica; isto é medição + dataset de calibração.",
        "",
        "## Disagreements (sink)",
        "",
    ]
    for r in disagreements[:15]:
        lines.append(f"- `{r['agent']}` {r['kind']}/{r['status']} · baseline=`{r['baseline_sink']}` · "
                     f"laya=`{r['laya_sink']}` (conf {r['laya_sink_confidence']})")
    if not disagreements:
        lines.append("- (nenhum)")
    elif len(disagreements) > 15:
        lines.append(f"- … e mais {len(disagreements) - 15} de {len(disagreements)} (lista capada em 15)")
    lines += ["", "## Artefatos", "", "- `decisions.jsonl` (1 linha por evento: baseline × laya × latência)"]
    (out_dir / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"rows": rows, "summary": summary, "disagreements": len(disagreements)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bus", default=str(DEFAULT_BUS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--env-python", default=None)
    ap.add_argument("--backend", choices=["real", "stub"], default="real")
    args = ap.parse_args()
    res = run(Path(args.bus).expanduser(), Path(args.out).expanduser(),
              backend=args.backend, limit=args.limit, env_python=args.env_python)
    s = res["summary"]
    print(f"spike: {s['n_events']} eventos · backend {s['backend']}/{s['model']}")
    print(f"  sink:   {s['sink_agreement'][0]}/{s['sink_agreement'][1]} concordam com baseline")
    print(f"  notify: {s['notify_agreement'][0]}/{s['notify_agreement'][1]} concordam (p>=0.5)")
    print(f"  latência: {s['latency_ms']}")
    print(f"  disagreements: {res['disagreements']} → ver RESULTS.md/decisions.jsonl")
    if s["errors"]:
        print(f"  erros: {s['errors']}")


if __name__ == "__main__":
    main()
