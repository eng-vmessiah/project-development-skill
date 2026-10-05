#!/usr/bin/env python3
"""Fleet studio snapshot — captura read-only ao vivo do fleet TUI canary (B15a.2 · 3b-ii).

Fonte: RPC `fleet.session.*` via /api/ws do serve vivo (loopback + token do
`~/.hermes/.env`; o token NUNCA é impresso). Gera `.spec/pd-studio/fleet-snapshot.json`
para a aba Fleet do Board (padrão pd-studio: capturar → reaplicar bindings estáticos).

Uso:
  python3 scripts/fleet_studio_sync.py            # activate → status → replay (cursor persistido)
  python3 scripts/fleet_studio_sync.py --cycle    # + ciclo real: deactivate → activate → replay do
                                                  #   cursor antigo (expõe `session.detached` no wire)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import websockets

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / ".spec/pd-studio/fleet-snapshot.json"
STATE = REPO / ".spec/pd-studio/fleet-cursor.json"
ENV = Path.home() / ".hermes/.env"
WS_URL = "ws://127.0.0.1:9119/api/ws"
WIRE = "pd-fleet-tui:v1"


def read_token() -> str:
    token = ""
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("HERMES_DASHBOARD_SESSION_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not token:
        sys.exit("HERMES_DASHBOARD_SESSION_TOKEN ausente no ~/.hermes/.env")
    return token


async def call(ws, mid, method, params):
    await ws.send(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, "params": params}))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=20)
        msg = json.loads(raw)
        if isinstance(msg, dict) and msg.get("id") == mid:
            return msg


def result_or_error(msg):
    if "result" in msg:
        return msg["result"], None
    return None, (msg.get("error") or {})


async def capture(cycle: bool) -> dict:
    token = read_token()
    out: dict[str, object] = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "source": "fleet.session.* via /api/ws (serve vivo :9119)", "wire": WIRE}
    events: list[dict] = []
    persisted: dict = {}
    if STATE.exists():
        try:
            persisted = json.loads(STATE.read_text())
        except Exception:
            persisted = {}
    async with websockets.connect(f"{WS_URL}?token={token}", max_size=8 * 1024 * 1024, open_timeout=15) as ws:
        act, err = result_or_error(await call(ws, 1, "fleet.session.activate", {"schema_version": WIRE}))
        out["activate"] = act or {"error": err}
        if cycle and act:
            deact, err = result_or_error(await call(ws, 2, "fleet.session.deactivate", {"schema_version": WIRE}))
            out["cycle_deactivate"] = deact or {"error": err}
            act2, err = result_or_error(await call(ws, 3, "fleet.session.activate", {"schema_version": WIRE}))
            out["cycle_reactivate"] = act2 or {"error": err}
            if act.get("cursor"):
                rep, err = result_or_error(await call(ws, 4, "fleet.session.replay", {"schema_version": WIRE, "cursor": act["cursor"]}))
                out["cycle_replay_from_first_cursor"] = rep or {"error": err}
                if rep and rep.get("events"):
                    events.extend(rep["events"])
            if act2:
                act = act2
        st, err = result_or_error(await call(ws, 5, "fleet.session.status", {"schema_version": WIRE}))
        out["status"] = st or {"error": err}
        cursor = persisted.get("cursor") or (act or {}).get("cursor")
        rep, err = result_or_error(await call(ws, 6, "fleet.session.replay", {"schema_version": WIRE, "cursor": cursor}))
        if err and persisted.get("cursor"):
            out["replay_fallback"] = {"from": "persisted", "error": err}
            cursor = (act or {}).get("cursor")
            rep, err = result_or_error(await call(ws, 7, "fleet.session.replay", {"schema_version": WIRE, "cursor": cursor}))
        out["replay"] = rep or {"error": err}
        if rep and rep.get("events"):
            events.extend(rep["events"])
        if rep and rep.get("next_cursor"):
            STATE.write_text(json.dumps(
                {"cursor": rep["next_cursor"], "updated_at": out["generated_at"]}, indent=2) + "\n")
    out["events_observed"] = events
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cycle", action="store_true", help="ciclo real deactivate→activate→replay")
    args = ap.parse_args()
    out = asyncio.run(capture(cycle=args.cycle))
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
