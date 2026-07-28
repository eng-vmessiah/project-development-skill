"""Adapter seam connecting :class:`ProviderDispatchBoundary` to Fleet V2.

This module is intentionally a narrow translation boundary.  It owns no provider
credentials, process invocation, environment lookup, networking, or failover;
the injected dispatch boundary remains the sole execution authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Callable, Mapping

from .contracts import AGENT_REPORT_V2_SCHEMA_VERSION, AgentReportV2, parse_agent_report_v2
from .models import TaskSpec
from .provider_dispatch import (
    DispatchStatus, ProviderDispatchBoundary, ProviderDispatchRequest,
)
from .provider_routing import ProviderRoutePolicy, profile_id

_FIXED_INSTANT = "1970-01-01T00:00:00Z"
_CANONICAL_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_URL_RE = re.compile(r"(?i)(?:https?|ftp|wss?)://[^\s\"'<>]+")
_PATH_RE = re.compile(r'''(?<![\w.])(?:[A-Za-z]:[\\/][^\s"'<>;,]+|/[^\s"'<>;,]+|\\\\[^\s"'<>;,]+)''')
_SECRET_RE = re.compile(r"(?i)\b(?:bearer\s+\S+|sk-[a-z0-9_-]+)")
_ASSIGN_RE = re.compile(r"(?i)\b(secret|token|password|credential|apikey|authorization)\s*[:=]\s*[^\s,;]+")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = value if type(value) is str else "[UNSUPPORTED TYPE]"
    text = _URL_RE.sub("[redacted-url]", text)
    text = _PATH_RE.sub("[redacted-path]", text)
    text = _SECRET_RE.sub("[redacted-secret]", text)
    return _ASSIGN_RE.sub(lambda m: f"{m.group(1)}=[redacted-secret]", text)


def _instant(clock: Callable[[], Any] | None) -> str:
    """Return a canonical UTC instant without consulting wall clock by default."""
    if clock is None:
        return _FIXED_INSTANT
    value = clock()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if type(value) is str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    raise ValueError("invalid clock")


def _lease_instant(value: Any) -> datetime:
    if type(value) is not str or not _CANONICAL_UTC_RE.fullmatch(value):
        raise ValueError("invalid lease expiry")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("invalid lease expiry") from exc


class ProviderDispatchAdapter:
    """Run Fleet ``TaskSpec`` values through one injected provider boundary."""

    def __init__(self, dispatch_boundary: ProviderDispatchBoundary,
                 policy: ProviderRoutePolicy, run_id: str, lease_owner: str,
                 *, clock: Callable[[], Any] | None = None) -> None:
        if not isinstance(dispatch_boundary, ProviderDispatchBoundary):
            raise TypeError("dispatch_boundary must be ProviderDispatchBoundary")
        if not isinstance(policy, ProviderRoutePolicy):
            raise TypeError("policy must be ProviderRoutePolicy")
        if type(run_id) is not str or not run_id:
            raise ValueError("run_id must be non-empty")
        if type(lease_owner) is not str or not lease_owner:
            raise ValueError("lease_owner must be non-empty")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self.dispatch = dispatch_boundary
        self.policy = policy
        self.run_id = run_id
        self.lease_owner = lease_owner
        self.clock = clock

    def _validate_lease(self, task: TaskSpec, lease: Mapping[str, Any]) -> int:
        if lease.get("task_id") != task.id:
            raise ValueError("invalid lease task")
        if lease.get("owner") != self.lease_owner:
            raise ValueError("invalid lease owner")
        lease_id = lease.get("lease_id")
        if (type(lease_id) is not str or not lease_id
                or "/" in lease_id or "\\" in lease_id
                or any(ord(char) < 32 or ord(char) == 127 for char in lease_id)):
            raise ValueError("invalid lease id")
        generation = lease.get("generation")
        if type(generation) is not int or generation < 0:
            raise ValueError("invalid lease generation")
        attempt = lease.get("attempt")
        if type(attempt) is not int or attempt < 1:
            raise ValueError("invalid lease attempt")
        if "run_id" in lease and lease.get("run_id") != self.run_id:
            raise ValueError("invalid lease run")
        expiry = _lease_instant(lease.get("expires_at"))
        if self.clock is not None:
            now = self.clock()
            if isinstance(now, datetime):
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)
            elif type(now) is str:
                try:
                    now = datetime.fromisoformat(now.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ValueError("invalid clock") from exc
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)
            else:
                raise ValueError("invalid clock")
            if expiry <= now.astimezone(timezone.utc):
                raise ValueError("expired lease")
        return attempt

    @staticmethod
    def _attempt(lease: Mapping[str, Any]) -> int:
        attempt = lease.get("attempt", 1)
        if type(attempt) is not int or attempt < 1:
            raise ValueError("invalid lease attempt")
        return attempt

    def run(self, task: TaskSpec, lease: Mapping[str, Any]) -> AgentReportV2:
        if not isinstance(task, TaskSpec) or not isinstance(lease, Mapping):
            raise TypeError("invalid task or lease")
        attempt = self._validate_lease(task, lease)
        started = _instant(self.clock)
        metadata = {"role": task.role, "wave": str(task.wave), "lease_attempt": attempt}
        request = ProviderDispatchRequest(
            task_id=task.id,
            prompt=task.objective,
            allowed_paths=tuple(task.allowed_paths),
            capabilities=tuple(task.capabilities or ("read",)),
            metadata=metadata,
        )
        result = self.dispatch.dispatch_request(request, self.policy, run_id=self.run_id)
        completed = _instant(self.clock)
        selected = result.selected
        agent_id = profile_id(selected) if selected is not None else "provider-dispatch"
        capabilities = tuple(task.capabilities or ("read",))
        route_audit = result.route_audit.as_dict()
        evidence = {
            "dispatch": result.audit.as_dict(),
            "route": route_audit,
            "status": result.status.value,
        }
        if result.status is DispatchStatus.OK:
            status = "completed"
            output = _safe_text(result.output) or "provider dispatch completed"
            payload = {
                "outputs": {"runtime_output": output},
                "tests": {"dispatch": "passed"},
                "validation": {"dispatch_status": "ok"},
                "decision": {"status": "completed", "provider": agent_id},
            }
        else:
            status = "blocked" if result.status in {DispatchStatus.BLOCKED, DispatchStatus.NO_PROVIDER} else "failed"
            reason = "provider dispatch blocked" if status == "blocked" else "provider execution failed"
            payload = {
                "reason": reason,
                "error": _safe_text(result.audit.reason),
                "blocker": {"dispatch_status": result.status.value},
            }
        report = {
            "schema_version": AGENT_REPORT_V2_SCHEMA_VERSION,
            "task_id": task.id,
            "attempt": attempt,
            "agent_id": agent_id,
            "role": task.role,
            "capabilities": list(capabilities),
            "status": status,
            "evidence": evidence,
            "started_at": started,
            "completed_at": completed,
            **payload,
        }
        return parse_agent_report_v2(report)


__all__ = ["ProviderDispatchAdapter"]
