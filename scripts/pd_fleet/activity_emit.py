#!/usr/bin/env python3
"""Hermes-native activity emitter (control plane v1, T-201).

Reads the local Hermes state.db READ-ONLY, derives contract-v1 activity events
(see .spec/pd-fleet-control-plane-v1/ACTIVITY-CONTRACT.md) for recent sessions and
gateway heartbeats, and appends them to the local activity bus — redacted, no network.

Local transport v1: append-only JSONL at ~/.hermes/activity/events.jsonl with a
watermark state at ~/.hermes/activity/state.json (idempotent re-runs).

Usage:
  python3 scripts/pd_fleet/activity_emit.py            # emit new events
  python3 scripts/pd_fleet/activity_emit.py --dry-run  # print events, write nothing
  python3 scripts/pd_fleet/activity_emit.py --json     # machine-readable summary
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".hermes" / "state.db"
DEFAULT_OUT = Path.home() / ".hermes" / "activity"
WINDOW_HOURS = 48
RUNNING_FRESH_S = 20 * 60
MAX_META_STR = 80


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat(timespec="seconds")


def _clip(value: str) -> str:
    return value if len(value) <= MAX_META_STR else value[: MAX_META_STR - 1] + "\u2026"


def session_events(con: sqlite3.Connection, now: float) -> list[dict]:
    """Contract-v1 status events for recent sessions (redacted: no content, no user ids)."""
    cutoff = now - WINDOW_HOURS * 3600
    rows = con.execute(
        "select id, source, model, started_at, ended_at, message_count, tool_call_count "
        "from sessions where ended_at is null or coalesce(ended_at, started_at) >= ? "
        "order by coalesce(ended_at, started_at) desc limit 20",
        (cutoff,),
    ).fetchall()
    ids = [r[0] for r in rows]
    last_msg: dict[str, float] = {}
    last_tool: dict[str, str] = {}
    if ids:
        marks = ",".join("?" * len(ids))
        for sid, ts in con.execute(
            f"select session_id, max(timestamp) from messages where session_id in ({marks}) group by session_id",
            ids,
        ):
            last_msg[sid] = ts
        for sid, tool in con.execute(
            f"select session_id, tool_name from messages where session_id in ({marks}) "
            "and tool_name is not null order by id desc",
            ids,
        ):
            last_tool.setdefault(sid, tool)
    events = []
    for sid, source, model, started_at, ended_at, msg_count, tool_count in rows:
        stamps = [x for x in (last_msg.get(sid), started_at) if x is not None]
        if not stamps:
            continue
        last_ts = max(stamps)
        if last_ts < cutoff:  # window is about recent ACTIVITY, not a recent ended_at
            continue
        if ended_at is not None:
            status = "done"
        elif now - last_ts <= RUNNING_FRESH_S:
            status = "running"
        else:
            status = "waiting"
        meta: dict[str, object] = {}
        if model:
            meta["model"] = _clip(str(model))
        if msg_count is not None:
            meta["msgs"] = int(msg_count)
        if tool_count is not None:
            meta["tools"] = int(tool_count)
        events.append({
            "v": 1,
            "event_id": f"hermes:sess:{sid}:{int(last_ts)}",
            "ts": _iso(last_ts),
            "agent_id": f"hermes:{source or 'unknown'}",
            "run_id": str(sid),
            "mission": None,
            "source": "hermes",
            "fidelity": "high",
            "kind": "status",
            "action": (last_tool.get(sid) or None),
            "paths": [],
            "status": status,
            "meta": meta or None,
        })
    return events


def gateway_events(con: sqlite3.Connection, now: float) -> list[dict]:
    """Contract-v1 heartbeat events for the freshest gateway backend per profile."""
    rows = con.execute(
        "select backend_id, pid, profile, host, last_heartbeat from gateway_heartbeats "
        "order by last_heartbeat desc limit 8"
    ).fetchall()
    seen: set[str] = set()
    events = []
    for backend_id, pid, profile, host, hb in rows:
        key = str(profile or backend_id)
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "v": 1,
            "event_id": f"hermes:gw:{backend_id}:{int(hb)}",
            "ts": _iso(hb),
            "agent_id": f"gateway:{key}",
            "run_id": str(backend_id),
            "mission": None,
            "source": "hermes",
            "fidelity": "high",
            "kind": "heartbeat",
            "action": None,
            "paths": [],
            "status": None,
            "meta": {"host": _clip(str(host or ""))},
        })
    return events


def emit(db: Path, out_dir: Path, dry_run: bool = False) -> dict:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    try:
        now = datetime.now(timezone.utc).timestamp()
        candidates = session_events(con, now) + gateway_events(con, now)
    finally:
        con.close()
    state_path = out_dir / "state.json"
    state: dict = {"watermarks": {}}
    if state_path.exists():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("watermarks"), dict):
                state = loaded
        except (OSError, json.JSONDecodeError):
            pass
    wm: dict = state["watermarks"]
    fresh: list[dict] = []
    skipped = 0
    for ev in candidates:
        key = f"{ev['agent_id']}|{ev['run_id']}"
        ts_epoch = datetime.fromisoformat(ev["ts"]).timestamp()
        if ts_epoch <= float(wm.get(key, 0)):
            skipped += 1
            continue
        wm[key] = ts_epoch
        fresh.append(ev)
    if fresh and not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
            for ev in fresh:
                fh.write(json.dumps(ev, ensure_ascii=False, sort_keys=True) + "\n")
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"emitted": len(fresh), "skipped": skipped, "candidates": len(candidates),
            "bus": str(out_dir / "events.jsonl"), "events": fresh}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB), help="state.db path (read-only)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="activity bus directory")
    ap.add_argument("--dry-run", action="store_true", help="print events, write nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args()
    res = emit(Path(args.db).expanduser(), Path(args.out).expanduser(), dry_run=args.dry_run)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    verb = "would emit" if args.dry_run else "emitted"
    print(f"{verb} {res['emitted']} event(s); skipped {res['skipped']} (watermark); bus: {res['bus']}")
    for ev in res["events"]:
        print(f"  - {ev['agent_id']} | {ev['kind']} | {ev.get('status') or '-'} | {ev['ts']} | {ev.get('action') or '-'}")


if __name__ == "__main__":
    main()
