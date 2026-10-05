#!/usr/bin/env python3
"""board_connector.py — Boardstate connector (stdio MCP, stdlib puro) do PD.

Expõe tools que o Board pode invocar por clique (abas pds/fleet/mc):
  - update_pds(mode)        → scripts/pd_studio_sync.py [--write]
  - update_fleet(mode)      → scripts/fleet_studio_sync.py
  - mc_publish(mission)     → scripts/plan_cockpit_sync.py --publish --mission <m>

MCP: JSON-RPC 2.0, newline-delimited, sobre stdio (logs em stderr).
Nada de rede; nada de segredos. Repo base: ~/project/project-development-skill.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path.home() / "project/project-development-skill"
PY = "/usr/bin/python3"
TIMEOUT = 240
TAIL = 1500

TOOLS = [
    {
        "name": "update_pds",
        "description": "Atualiza o snapshot do PD Studio (aba pds) rodando scripts/pd_studio_sync.py. mode=apply grava (.spec/pd-studio/snapshot.json); mode=preview só mostra.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["apply", "preview"], "default": "apply"}
            },
        },
    },
    {
        "name": "update_fleet",
        "description": "Atualiza o snapshot do Fleet (aba fleet) rodando scripts/fleet_studio_sync.py (captura read-only via RPC fleet.session.*).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["apply", "preview"], "default": "apply"}
            },
        },
    },
    {
        "name": "mc_publish",
        "description": "Publica o Mission Control (aba mc): plan_cockpit_sync.py --publish [--mission <m>]. Sem missão, usa a selecionada atualmente.",
        "inputSchema": {
            "type": "object",
            "properties": {"mission": {"type": "string", "description": "nome da missão (opcional)"}},
        },
    },
]


def log(*a) -> None:
    print("[pd-board-connector]", *a, file=sys.stderr, flush=True)


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def norm_mode(raw: str) -> str:
    v = (raw or "apply").strip().lower()
    if v.startswith("aplicar") or v.startswith("apply"):
        return "apply"
    if v.startswith("prévia") or v.startswith("previa") or v.startswith("preview"):
        return "preview"
    return "apply"


def run_cmd(cmd: list[str]) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"timeout ({TIMEOUT}s): {' '.join(cmd)}"
    except Exception as e:  # noqa: BLE001
        return False, f"erro ao executar: {e}"
    out = ((p.stdout or "") + ("\n" + p.stderr if p.stderr else "")).strip()
    header = f"[pd-board] exit={p.returncode} · {' '.join(cmd[1:])}"
    return p.returncode == 0, header + "\n" + out[-TAIL:]


def call_tool(name: str, args: dict) -> tuple[bool, str]:
    if name == "update_pds":
        mode = norm_mode(str(args.get("mode", "apply")))
        cmd = [PY, "scripts/pd_studio_sync.py"] + ([] if mode == "preview" else ["--write"])
        return run_cmd(cmd)
    if name == "update_fleet":
        return run_cmd([PY, "scripts/fleet_studio_sync.py"])
    if name == "mc_publish":
        mission = str(args.get("mission", "")).strip()
        cmd = [PY, "scripts/plan_cockpit_sync.py", "--publish"]
        if mission:
            cmd += ["--mission", mission]
        return run_cmd(cmd)
    return False, f"tool desconhecida: {name}"


def main() -> None:
    log("started; repo =", REPO)
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            pv = (msg.get("params") or {}).get("protocolVersion") or "2024-11-05"
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": pv,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "pd-board-connector", "version": "0.1.0"},
            }})
        elif method == "notifications/initialized":
            pass
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name", "")
            args = params.get("arguments") or {}
            log("tools/call", name, json.dumps(args, ensure_ascii=False))
            ok, text = call_tool(name, args)
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": text}],
                "isError": not ok,
            }})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})


if __name__ == "__main__":
    main()
