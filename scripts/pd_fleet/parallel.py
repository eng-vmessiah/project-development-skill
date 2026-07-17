"""Small, fail-closed bounded in-process parallel executor.

The executor owns one lazily-created, bounded thread pool for its lifetime.
A running Python thread cannot be forcibly stopped safely.  Consequently, a
run-level timeout returns promptly, cancels work that has not started, and
*poisons* the pool while a non-cooperative worker may finish in the background.
No replacement pool is created: subsequent runs are rejected until ``close``
is called.  Applications should explicitly close the executor (usually in a
``finally`` block); ``close(wait=False)`` is non-blocking for poisoned pools.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from copy import deepcopy
import time
from typing import Any, Callable, Iterable, Mapping


def _copy(value: Any) -> Any:
    """Return a detached value, preserving the public value API."""
    return deepcopy(value)


@dataclass(frozen=True, init=False)
class TaskResult:
    """A result whose mutable value is detached on construction and access.

    ``value`` remains a normal-looking public attribute, but each access and
    ``to_dict`` gets a fresh deep copy.  Thus a runner, callback, or caller
    cannot mutate the result retained by the executor (or another observer).
    """

    task_id: str
    status: str
    _value: Any = field(default=None, repr=False, compare=True)
    error: str | None = None

    def __init__(self, task_id: str, status: str, value: Any = None,
                 error: str | None = None) -> None:
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "_value", _copy(value))
        object.__setattr__(self, "error", error)

    @property
    def value(self) -> Any:
        return _copy(self._value)

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "status": self.status,
                "value": self.value, "error": self.error}


class BoundedParallelExecutor:
    """Execute unique tasks with at most ``max_workers`` live submissions.

    The pool is lazy and reused across successful calls.  If a timeout occurs,
    the pool is poisoned because Python cannot terminate a running thread;
    ``run`` then rejects later calls rather than leaking one pool per timeout.
    Call :meth:`close`/``shutdown`` explicitly.  ``close(wait=False)`` never
    waits for a non-cooperative timed-out worker, which may finish in the
    background; no result from it is retained.
    """

    def __init__(self, max_workers: int = 1, *, runner: Callable[[Any], Any] | None = None,
                 clock: Callable[[], float] | None = None, max_output: int = 65536) -> None:
        if type(max_workers) is not int or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        if type(max_output) is not int or max_output < 1:
            raise ValueError("max_output must be positive")
        self.max_workers = max_workers
        self.runner = runner
        self.clock = clock or time.monotonic
        self.max_output = max_output
        self._executor: ThreadPoolExecutor | None = None
        self._poisoned = False
        self._closed = False

    # A finite wait is required to observe cancellation when no run timeout
    # was supplied.  Keep polling bounded without busy-spinning.
    _CANCEL_POLL_INTERVAL = 0.05

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @property
    def closed(self) -> bool:
        return self._closed

    def _pool(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers,
                                                 thread_name_prefix="pd-fleet")
        return self._executor

    def run(self, tasks: Iterable[Any], runner: Callable[[Any], Any] | None = None, *,
            timeout: float | None = None, cancel_event: Any | None = None,
            callback: Callable[[TaskResult], Any] | None = None) -> list[TaskResult]:
        if self._closed:
            raise RuntimeError("executor is closed")
        # An already-set cancellation can be answered without touching the
        # poisoned pool; this preserves fail-closed cancellation semantics.
        if self._poisoned and not (cancel_event is not None and cancel_event.is_set()):
            raise RuntimeError("executor pool is poisoned after a non-cooperative timeout")
        if runner is None:
            runner = self.runner
        if not callable(runner):
            raise TypeError("runner must be callable")
        if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0):
            raise ValueError("timeout must be non-negative")

        entries: dict[str, Any] = {}
        for task in tasks:
            task_id = task.get("id") if isinstance(task, Mapping) else getattr(task, "id", task)
            if not isinstance(task_id, str) or not task_id:
                raise ValueError("tasks must have non-empty string IDs")
            entries.setdefault(task_id, task)
        ordered = sorted(entries)
        if not ordered:
            return []

        results: dict[str, TaskResult] = {}
        copied: dict[str, Any] = {}
        for task_id in ordered:
            try:
                copied[task_id] = _copy(entries[task_id])
            except BaseException as exc:
                results[task_id] = TaskResult(task_id, "failed", error=type(exc).__name__[:self.max_output])

        def result(task_id: str, status: str, value: Any = None,
                   error: str | None = None) -> TaskResult:
            if isinstance(error, str):
                error = error[: self.max_output]
            try:
                return TaskResult(task_id, status, value, error)
            except BaseException as exc:
                return TaskResult(task_id, "failed", error=type(exc).__name__[:self.max_output])

        pending_ids = iter(task_id for task_id in ordered if task_id in copied)
        futures: dict[Future[Any], str] = {}
        # Do not create (or touch) a pool for an already-cancelled run.  This
        # also permits a cancelled retry after a poisoned run without submitting
        # to its shut-down pool.
        cancelled = bool(cancel_event is not None and cancel_event.is_set())
        executor = None if cancelled else self._pool()
        deadline = None if timeout is None else self.clock() + timeout

        def submit_one() -> None:
            try:
                task_id = next(pending_ids)
            except StopIteration:
                return
            assert executor is not None
            futures[executor.submit(runner, copied[task_id])] = task_id

        timed_out = False
        try:
            if not cancelled:
                for _ in range(min(self.max_workers, len(copied))):
                    submit_one()
            while futures:
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                remaining = None if deadline is None else max(0.0, deadline - self.clock())
                if cancelled or (remaining is not None and remaining <= 0):
                    status = "cancelled" if cancelled else "timeout"
                    timed_out = not cancelled
                    # ``Future.cancel`` cannot stop running threads.  Fence
                    # the pool if any running work remains after cancellation.
                    non_cooperative = False
                    for future, task_id in list(futures.items()):
                        future.cancel()
                        results[task_id] = result(task_id, status, error=status)
                        non_cooperative |= not future.done()
                    futures.clear()
                    if cancelled and non_cooperative:
                        self._poisoned = True
                        assert executor is not None
                        executor.shutdown(wait=False, cancel_futures=True)
                    break
                wait_timeout = self._CANCEL_POLL_INTERVAL
                if remaining is not None:
                    wait_timeout = min(wait_timeout, remaining)
                done, _ = wait(tuple(futures), timeout=wait_timeout, return_when=FIRST_COMPLETED)
                if not done:
                    # A polling interval is not a timeout; only the deadline
                    # makes timeout terminal.
                    if deadline is None or self.clock() < deadline:
                        continue
                    timed_out = True
                    for future, task_id in list(futures.items()):
                        future.cancel()
                        results[task_id] = result(task_id, "timeout", error="timeout")
                    futures.clear()
                    break
                for future in done:
                    task_id = futures.pop(future)
                    try:
                        results[task_id] = result(task_id, "completed", value=future.result())
                    except BaseException as exc:
                        status = "timeout" if isinstance(exc, TimeoutError) else "failed"
                        results[task_id] = result(task_id, status, error=type(exc).__name__)
                    if not cancelled and (deadline is None or self.clock() < deadline):
                        submit_one()
        finally:
            if timed_out:
                self._poisoned = True
                executor.shutdown(wait=False, cancel_futures=True)
                self._executor = executor

        output = [results.get(task_id, result(task_id, "cancelled", error="cancelled")) for task_id in ordered]
        if callback is not None:
            for item in output:
                try:
                    callback(item)
                except BaseException:
                    pass
        return output

    def close(self, *, wait: bool = False, cancel_futures: bool = True) -> None:
        """Release the pool; ``wait=False`` is safe for poisoned pools."""
        if self._closed:
            return
        self._closed = True
        if self._executor is not None:
            self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    shutdown = close
    execute = run


ParallelExecutor = BoundedParallelExecutor
__all__ = ["TaskResult", "BoundedParallelExecutor", "ParallelExecutor"]
