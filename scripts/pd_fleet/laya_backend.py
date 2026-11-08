#!/usr/bin/env python3
"""Laya backend shim for the routing spike (T-203).

Runs under the Hermes composed-env python (has laya + torch). Reads a batch of
decision requests and writes answers — one model load per batch, local only.

  <env>/bin/python laya_backend.py --in req.json --out res.json

Input:  {"requests": [{"id": str, "state": str, "questions": {...}}, ...]}
Output: {"results": [{"id", "answers", "latency_ms", "backend", "model"}, ...], "errors": [...]}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    args = ap.parse_args()

    from hermes_laya import backend  # type: ignore

    requests = json.loads(Path(args.inp).read_text(encoding="utf-8"))["requests"]
    results, errors = [], []
    for req in requests:
        try:
            raw, latency_ms, backend_name, model = backend.predict(req["state"], req["questions"])
            answers = raw.get("answers", raw) if isinstance(raw, dict) else raw
            results.append({"id": req["id"], "answers": answers, "latency_ms": latency_ms,
                            "backend": backend_name, "model": model})
        # Each request is isolated so arbitrary backend failures become per-request errors.
        except Exception as exc:  # noqa: BLE001
            errors.append({"id": req.get("id"), "error": f"{type(exc).__name__}: {exc}"})
    Path(args.out).write_text(
        json.dumps({"results": results, "errors": errors}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"laya_backend: {len(results)} ok, {len(errors)} errors")
    sys.exit(0 if results else 2)


if __name__ == "__main__":
    main()
