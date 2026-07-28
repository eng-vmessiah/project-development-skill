"""Deterministic, lease-backed task selection for local fleet runs.

The scheduler is deliberately small: it never executes a task and never writes
state outside :class:`FleetRunStore`.  A claim is persisted before it is
returned, so separate scheduler instances (including processes) contend on the
store's lock rather than on an in-memory semaphore.
"""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Callable, Mapping

from .run_store import FleetRunStore, GenerationConflictError, LeaseError, RunStoreError


class SchedulerError(RunStoreError):
    """Invalid scheduler input or an unsafe scheduling decision."""


class OwnershipConflict(SchedulerError):
    """Two runnable tasks would own overlapping paths."""


class CapacityExceeded(SchedulerError):
    """The requested claim would exceed bounded capacity."""


def _paths(task: Mapping[str, Any]) -> frozenset[str]:
    result: set[str] = set()
    for key in ("allowed_paths", "paths"):
        values = task.get(key, ())
        if isinstance(values, str) or values is None:
            values = (values,) if values else ()
        if not isinstance(values, (list, tuple, set, frozenset)):
            raise SchedulerError("task paths must be a list")
        for value in values:
            if not isinstance(value, str) or not value or value.startswith(("/", "\\")):
                raise SchedulerError("task paths must be relative")
            p = PurePosixPath(value.replace("\\", "/"))
            if ".." in p.parts:
                raise SchedulerError("task paths must not traverse")
            result.add(str(p))
    return frozenset(result)


def _overlap(left: frozenset[str], right: frozenset[str]) -> bool:
    return any(a == b or a.startswith(b + "/") or b.startswith(a + "/") for a in left for b in right)


class LeaseScheduler:
    """Select and exclusively claim ready tasks with a durable bounded lease."""

    def __init__(self, store: FleetRunStore, run_id: str, owner: str, *, max_parallel: int = 1,
                 clock: Callable[[], str] | None = None) -> None:
        if not all(hasattr(store, name) for name in ("load", "claim", "renew", "_mutate")):
            raise TypeError("store must provide FleetRunStore lease operations")
        if type(max_parallel) is not int or max_parallel < 1:
            raise SchedulerError("max_parallel must be positive")
        self.store, self.run_id, self.owner = store, run_id, owner
        self.max_parallel, self.clock = max_parallel, clock
        self._worker_claims: dict[str, dict[str, Any]] = {}

    def _snapshot(self) -> dict[str, Any]:
        return self.store.load(self.run_id)

    @staticmethod
    def _validate_task_dependencies(task: Mapping[str, Any]) -> None:
        deps = task.get("depends_on", task.get("dependencies", ()))
        if isinstance(deps, str) or not isinstance(deps, (list, tuple, set, frozenset)):
            raise SchedulerError("task dependencies must be a list")
        for dep in deps:
            if type(dep) is not str:
                raise SchedulerError("dependency elements must be exact strings")

    @classmethod
    def _task_map(cls, state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        plan = state.get("plan", {})
        tasks = plan.get("tasks", []) if isinstance(plan, Mapping) else []
        result = {}
        for task in tasks:
            if isinstance(task, Mapping):
                # Validate the complete plan before indexing/filtering tasks. In
                # particular, terminal tasks must not hide malformed dependencies
                # from a read or claim of an otherwise runnable sibling.
                cls._validate_task_dependencies(task)
                if isinstance(task.get("id"), str):
                    result[task["id"]] = task
        return result

    @classmethod
    def _ready_ids_from_state(cls, state: Mapping[str, Any], *, now: str | None = None) -> list[str]:
        """Compute ready IDs from one state snapshot without mutating it.

        When ``now`` is supplied, expired leases are not readiness barriers.
        Omitting it preserves the static snapshot behavior for existing callers.
        """
        tasks = cls._task_map(state)
        task_state = state.get("tasks", {})
        reports = state.get("reports", {})
        completed = {tid for tid, value in task_state.items()
                     if isinstance(value, Mapping) and value.get("status") == "completed"}
        completed.update(tid for tid, value in reports.items()
                        if isinstance(value, Mapping) and value.get("status") == "completed")
        result = []
        for task_id in sorted(tasks):
            task = tasks[task_id]
            value = task_state.get(task_id, {})
            status = value.get("status", task.get("status", "pending")) if isinstance(value, Mapping) else task.get("status", "pending")
            lease = state.get("leases", {}).get(task_id)
            # A caller that has an authoritative clock can distinguish an
            # active lease from a stale one without mutating this snapshot.
            # Keep the no-clock behavior for static callers: any persisted
            # lease remains a barrier when its age cannot be established.
            active = lease is not None and (now is None or lease.get("expires_at", "") > now)
            if status in {"completed", "failed", "blocked", "orphaned"} or active:
                continue
            deps = task.get("depends_on", task.get("dependencies", ()))
            if all(dep in completed for dep in deps):
                result.append(task_id)
        return result

    def ready_ids(self) -> list[str]:
        """Return ready IDs in canonical lexical order without mutating state."""
        now = self.clock() if self.clock else None
        return self._ready_ids_from_state(self._snapshot(), now=now)

    # Explicit aliases make the read-only selection API convenient to adapters.
    select_ready = ready_ids
    ready_task_ids = ready_ids

    def active_claims(self) -> dict[str, Mapping[str, Any]]:
        state = self._snapshot()
        # Expired leases do not consume capacity; claim() will atomically
        # replace them, while this view remains read-only.
        now = self.clock() if self.clock else None
        leases = state.get("leases", {})
        if now is None:
            return dict(leases)
        return {k: v for k, v in leases.items() if v.get("expires_at", "") > now}

    def claim(self, worker_id: str, *, limit: int | None = None, lease_seconds: float = 60) -> list[dict[str, Any]]:
        if not isinstance(worker_id, str) or not worker_id:
            raise SchedulerError("worker_id required")
        requested = self.max_parallel if limit is None else limit
        if type(requested) is not int or requested < 0:
            raise SchedulerError("limit must be non-negative")
        if requested > self.max_parallel:
            # An oversized request is invalid, not an empty scheduling result.
            # Check before ready_ids() so this remains stable with no ready work.
            raise CapacityExceeded("bounded capacity exceeded")
        candidates = self.ready_ids()

        def select(state: Mapping[str, Any], available: list[str], capacity: int, *, now: str) -> list[str]:
            if requested > capacity:
                raise CapacityExceeded("bounded capacity exceeded")
            tasks = self._task_map(state)
            # ``now`` is sampled by claim_many while holding the store lock;
            # use that same authoritative instant for the re-check.
            ready = set(self._ready_ids_from_state(state, now=now))
            occupied = [_paths(tasks[tid]) for tid, lease in state.get("leases", {}).items()
                        if tid in tasks and lease.get("expires_at", "") > now]
            selected: list[str] = []
            for task_id in sorted(available):
                if len(selected) >= requested:
                    break
                if task_id not in ready:
                    continue
                paths = _paths(tasks[task_id])
                if any(_overlap(paths, other) for other in occupied) or any(_overlap(paths, _paths(tasks[tid])) for tid in selected):
                    raise OwnershipConflict("task paths overlap")
                selected.append(task_id)
            return selected

        try:
            claimed = self.store.claim_many(self.run_id, candidates, self.owner,
                                            max_parallel=self.max_parallel,
                                            lease_seconds=lease_seconds, select=select)
        except RunStoreError as exc:
            if "bounded capacity exceeded" in str(exc):
                # A competing scheduler may have consumed the candidates
                # between the read and the atomic operation.  That is a
                # normal no-op; a stable empty ready set remains an explicit
                # capacity error for callers requesting more work.
                if candidates:
                    return []
                raise CapacityExceeded("bounded capacity exceeded") from exc
            raise
        for token in claimed:
            self._worker_claims[token["lease_id"]] = {"worker_id": worker_id, **token}
        return claimed

    claim_ready = claim

    def renew(self, token: Mapping[str, Any], *, lease_seconds: float = 60) -> dict[str, Any]:
        try:
            return self.store.renew(self.run_id, token["task_id"], token, self.owner, lease_seconds=lease_seconds)
        except GenerationConflictError as exc:
            raise LeaseError("stale or expired lease") from exc

    def release(self, token: Mapping[str, Any]) -> None:
        """Atomically drop a still-valid lease without creating a terminal report."""
        task_id = token.get("task_id") if isinstance(token, Mapping) else None
        def remove(state: dict[str, Any]) -> None:
            self.store._check_token(state, task_id, token)
            state["leases"].pop(task_id, None)
        self.store._mutate(self.run_id, self.owner, None, remove)
        self._worker_claims.pop(token.get("lease_id"), None)

    def recover_stale(self) -> list[str]:
        state = self._snapshot()
        now = self.clock() if self.clock else None
        if now is None:
            return []
        stale = sorted(tid for tid, lease in state.get("leases", {}).items() if lease.get("expires_at", "") <= now)
        for task_id in stale:
            current = self._snapshot()
            if task_id not in current.get("leases", {}):
                continue
            def remove(s: dict[str, Any], tid=task_id) -> None:
                lease = s["leases"].get(tid)
                if lease and lease.get("expires_at", "") <= now:
                    s["leases"].pop(tid, None)
            self.store._mutate(self.run_id, self.owner, current["generation"], remove)
        return stale


Scheduler = LeaseScheduler
__all__ = ["LeaseScheduler", "Scheduler", "SchedulerError", "OwnershipConflict", "CapacityExceeded"]
