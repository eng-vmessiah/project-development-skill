from __future__ import annotations

import threading
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.parallel import BoundedParallelExecutor


def test_barrier_proves_real_overlap_and_workers_are_bounded():
    entered = 0
    peak = 0
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def run(task_id):
        nonlocal entered, peak
        with lock:
            entered += 1
            peak = max(peak, entered)
        barrier.wait(timeout=2)
        with lock:
            entered -= 1
        return task_id

    results = BoundedParallelExecutor(max_workers=2).run(["b", "a"], run)
    assert [r.task_id for r in results] == ["a", "b"]
    assert [r.status for r in results] == ["completed", "completed"]
    assert peak == 2


def test_exception_becomes_result_and_callback_isolation():
    callbacks = []
    def run(task_id):
        if task_id == "bad":
            raise ValueError("secret detail")
        return task_id.upper()
    def callback(result):
        callbacks.append(result.task_id)
        raise RuntimeError("callback failure")

    results = BoundedParallelExecutor(max_workers=2).run(["bad", "ok"], run, callback=callback)
    assert results[0].status == "failed"
    assert results[0].error == "ValueError"
    assert results[1].value == "OK"
    assert callbacks == ["bad", "ok"]


def test_timeout_and_cancellation_are_fail_closed():
    started = threading.Event()
    release = threading.Event()
    def run(task_id):
        started.set()
        release.wait(2)
        return task_id

    executor = BoundedParallelExecutor(max_workers=1)
    results = executor.run(["a", "b"], run, timeout=0.03)
    assert results[0].status == "timeout"
    assert results[1].status == "cancelled"
    release.set()

    cancel = threading.Event()
    cancel.set()
    assert all(r.status == "cancelled" for r in executor.run(["a", "b"], run, cancel_event=cancel))


def test_cancellation_polls_blocked_runner_and_fences_pool():
    started = threading.Event()
    cancel = threading.Event()
    release = threading.Event()
    holder = {}

    def run(_task):
        started.set()
        release.wait(2)
        return "late"

    executor = BoundedParallelExecutor(max_workers=1)
    thread = threading.Thread(
        target=lambda: holder.setdefault("results", executor.run(["blocked"], run, cancel_event=cancel))
    )
    thread.start()
    assert started.wait(1)
    cancel_at = time.monotonic()
    cancel.set()
    thread.join(0.5)
    elapsed = time.monotonic() - cancel_at
    try:
        assert not thread.is_alive()
        assert elapsed < 0.5
        assert holder["results"][0].status == "cancelled"
        assert executor.poisoned
    finally:
        release.set()
        thread.join(1)
        executor.close()


def test_no_duplicate_tasks_and_no_unbounded_threads():
    results = BoundedParallelExecutor(max_workers=2).run(["a", "b", "a"], lambda x: x)
    assert [r.task_id for r in results] == ["a", "b"]
    assert len(threading.enumerate()) < 100


def test_inputs_and_result_values_are_detached_from_runner_and_caller():
    task = {"id": "a", "nested": {"items": [1]}}

    def run(value):
        value["nested"]["items"].append(2)
        return {"items": value["nested"]["items"]}

    executor = BoundedParallelExecutor()
    results = executor.run([task], run)
    assert task["nested"]["items"] == [1]
    first = results[0].value
    first["items"].append(99)
    assert results[0].value == {"items": [1, 2]}
    assert results[0].to_dict()["value"] == {"items": [1, 2]}
    executor.close()


def test_worker_and_callback_baseexceptions_are_bounded_and_isolated():
    seen = []

    def run(_task):
        raise KeyboardInterrupt()

    def callback(item):
        seen.append(item.status)
        raise SystemExit()

    executor = BoundedParallelExecutor()
    results = executor.run(["a"], run, callback=callback)
    assert results[0].status == "failed"
    assert results[0].error == "KeyboardInterrupt"
    assert seen == ["failed"]
    executor.close()


def test_timeout_poisons_and_reuses_no_new_pool():
    release = threading.Event()

    def run(_task):
        release.wait(2)

    executor = BoundedParallelExecutor(max_workers=1)
    first_pool = None
    try:
        results = executor.run(["a"], run, timeout=0.01)
        first_pool = executor._executor
        assert results[0].status == "timeout"
        assert executor.poisoned
        try:
            executor.run(["b"], run, timeout=0.01)
        except RuntimeError as exc:
            assert "poisoned" in str(exc)
        else:
            raise AssertionError("poisoned executor accepted another run")
        assert executor._executor is first_pool
    finally:
        release.set()
        executor.close()
