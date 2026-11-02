#!/usr/bin/python3
"""Executable example of STEERING-CONTRACT section 4 canonicalization."""
import hashlib
import json


def idempotency_key(value: dict) -> str:
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> int:
    first = {"v": 1, "verb": "steer", "target": {"run_id": "r1", "owner_epoch": 7},
             "payload": {"text": "continue"}, "tier": "T1"}
    same = {"tier": "T1", "payload": {"text": "continue"},
            "target": {"owner_epoch": 7, "run_id": "r1"}, "verb": "steer", "v": 1}
    changed = {**first, "payload": {"text": "stop"}}
    key_first = idempotency_key(first)
    key_repeat = idempotency_key(first.copy())
    key_reordered = idempotency_key(same)
    key_changed = idempotency_key(changed)
    passed = key_first == key_repeat == key_reordered and key_first != key_changed
    print(f"first={key_first}")
    print(f"repeat={key_repeat}")
    print(f"reordered={key_reordered}")
    print(f"changed_payload={key_changed}")
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
