"""Crash-safe, local persistence for fleet runs.

Event ``sequence`` is the append-only audit sequence assigned while holding
the store lock.  It describes persistence order, not scheduler completion
order.  Queries of ``events`` use the deterministic canonical key
``(ordering_key, sequence)``; callers may provide a stable string
``ordering_key`` (or ``event_id``), otherwise one is derived from the
redacted event payload.

``renew`` fences the previous lease token and returns a refreshed token
mapping (``run_id``, ``task_id``, ``lease_id``, ``generation``, and
``expires_at``), rather than the mutated snapshot.
"""
from __future__ import annotations
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import errno, hashlib, inspect, json, math, os, re, secrets, stat, threading
try:
    import fcntl
except ImportError:  # pragma: no cover - exercised by portability tests
    fcntl = None
from pathlib import Path
from typing import Any, Callable, Mapping
from .contracts import canonicalize, plan_hash

class RunStoreError(RuntimeError): pass
class RunNotFoundError(RunStoreError): pass
class OwnerMismatchError(RunStoreError): pass
class GenerationConflictError(RunStoreError): pass
class LeaseError(RunStoreError): pass
class DuplicateCommitError(RunStoreError): pass
class PathContainmentError(RunStoreError): pass
class CorruptSnapshotError(RunStoreError): pass
Clock = Callable[[], str]

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_STATUSES = frozenset(("created", "running", "completed", "failed", "cancelled", "blocked"))
_TASK_STATUSES = _STATUSES | frozenset(("pending", "ready", "blocked", "orphaned", "skipped"))
_TERMINAL_TASK_STATUSES = frozenset(("completed", "skipped", "failed", "blocked"))
_REPORT_STATUSES = frozenset(("completed", "failed", "blocked"))
_REPORT_FIELDS = frozenset(("status", "outputs", "evidence", "tests", "validation", "decision", "started_at", "completed_at", "reason", "error", "blocker"))
_SENSITIVE = re.compile(r"(?i)(token|secret|password|credential|api[_ -]?key|authorization|private[_ -]?key)")
_SECRET_TEXT = re.compile(r"(?i)(bearer\s+|(?:token|secret|password|api[_ -]?key|authorization)\s*[:=]\s*)\S+")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

def _clock_value(clock: Clock) -> str:
    value = clock()
    if type(value) is not str:
        raise RunStoreError("clock must return an ISO-8601 UTC string")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0): raise ValueError
    except (TypeError, ValueError):
        raise RunStoreError("clock must return an ISO-8601 UTC string")
    return value

def _plus_seconds(value: str, seconds: float) -> str:
    if type(seconds) not in (int, float) or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0: raise LeaseError("lease duration must be positive")
    try: stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc: raise RunStoreError("invalid clock") from exc
    return (stamp + timedelta(seconds=seconds)).isoformat(timespec="microseconds").replace("+00:00", "Z")

def _safe_id(value: str) -> str:
    if type(value) is not str or not value or value in {".", ".."} or not _ID.fullmatch(value): raise PathContainmentError("unsafe run identifier")
    return value

def _redact(value: Any, root: Path | None = None, _active: set[int] | None = None) -> Any:
    """Redact a JSON-safe copy, rejecting non-string keys and cycles."""
    active = set() if _active is None else _active
    if isinstance(value, Mapping):
        marker = id(value)
        if marker in active: raise RunStoreError("payload contains a cycle")
        active.add(marker)
        try:
            result = {}
            for k, v in value.items():
                if type(k) is not str: raise RunStoreError("payload mapping keys must be strings")
                result[k] = "[REDACTED]" if _SENSITIVE.search(k) else _redact(v, root, active)
            return result
        finally:
            active.remove(marker)
    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in active: raise RunStoreError("payload contains a cycle")
        active.add(marker)
        try: return [_redact(v, root, active) for v in value]
        finally: active.remove(marker)
    if isinstance(value, str):
        # Redact complete embedded absolute/home/Windows paths, URLs, and credentials.
        value = re.sub(r"(?i)(?:https?|ftp|wss?)://[^\s\"'<>]+", "[URL REDACTED]", value)
        value = re.sub(r"(?<![\w.])(?:~[/\\][^\s,;]+|/[^\s,;]+|[A-Za-z]:[/\\][^\s,;]+|\\\\[^\s,;]+)", "[PATH REDACTED]", value)
        return _SECRET_TEXT.sub(lambda m: m.group(1) + "[REDACTED]", value)
    try: json.dumps(value, allow_nan=False)
    except (TypeError, ValueError): raise RunStoreError("payload is not JSON-safe")
    return value

class FleetRunStore:
    schema_version = "pd-fleet-run:v2"
    _STRUCTURAL = frozenset(("schema_version","run_id","plan_hash","plan","generation","owner","event_sequence","updated_at","checksum"))
    _FIELDS = frozenset(("schema_version","run_id","plan_hash","plan","generation","owner","status","waves","tasks","leases","attempts","checkpoints","reports","events","gates","metrics","audit","event_sequence","updated_at","checksum"))
    def __init__(self, root: str | Path, *, clock: Clock | None = None) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._clock = clock or _now
        self._lock = threading.RLock()
        self._lock_path = self.root / ".run_store.lock"
        self._lock_fd = -1
        try:
            if self._lock_path.is_symlink(): raise PathContainmentError("lock path is symlink")
            self._lock_fd = os.open(self._lock_path, os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
            lock_stat = os.fstat(self._lock_fd)
            if not stat.S_ISREG(lock_stat.st_mode):
                raise OSError(errno.ELOOP, "lock is not regular")
            os.fchmod(self._lock_fd, 0o600)
        except OSError as exc:
            if self._lock_fd >= 0:
                try: os.close(self._lock_fd)
                except OSError: pass
                self._lock_fd = -1
            raise RunStoreError("cannot create store lock") from exc
        if fcntl is None or not hasattr(fcntl, "flock"):
            os.close(self._lock_fd); self._lock_fd = -1
            raise RunStoreError("inter-process locking unavailable")
    def close(self) -> None:
        """Release this store's lock descriptor (safe to call repeatedly)."""
        with self._lock:
            if self._lock_fd >= 0:
                try: os.close(self._lock_fd)
                except OSError: pass
                finally: self._lock_fd = -1
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): self.close()
    @contextmanager
    def _guard(self):
        with self._lock:
            if self._lock_fd < 0 or fcntl is None: raise RunStoreError("inter-process locking unavailable")
            try: fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
            except OSError as exc: raise RunStoreError("cannot lock store") from exc
            try: yield
            finally:
                try: fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                except OSError: pass
    def _dir(self, run_id: str) -> Path:
        rid = _safe_id(run_id); p = self.root / rid
        if p.parent != self.root or (p.exists() and p.is_symlink()): raise PathContainmentError("run path escapes root")
        return p
    def _path(self, run_id: str, suffix: str = "") -> Path: return self._dir(run_id) / ("snapshot.json" + suffix)
    def _ensure_dir(self, rid: str) -> Path:
        d = self._dir(rid); d.mkdir(parents=True, exist_ok=True)
        if d.is_symlink(): raise PathContainmentError("run directory is symlink")
        return d
    def create(self, run_id: str, plan: Mapping[str, Any], owner: str, *, initial: Mapping[str, Any] | None = None) -> dict[str, Any]:
        rid = _safe_id(run_id)
        try: _safe_id(owner)
        except PathContainmentError as exc: raise OwnerMismatchError("owner required") from exc
        if not isinstance(plan, Mapping): raise RunStoreError("plan must be an object")
        canonical = canonicalize(plan); now = _clock_value(self._clock)
        with self._guard():
            d = self._ensure_dir(rid)
            # Never overwrite forensic evidence, including malformed or
            # checksum-invalid candidates.  Repair is deliberately not part
            # of this API.
            for suffix in ("", ".bak"):
                candidate = self._path(rid, suffix)
                try:
                    os.lstat(candidate)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise RunStoreError("cannot inspect existing snapshot") from exc
                raise RunStoreError("run snapshot artifact already exists")
            state = {"schema_version":self.schema_version,"run_id":rid,"plan_hash":plan_hash(plan),"plan":canonical,"generation":0,"owner":owner,"status":"created","waves":[],"tasks":{},"leases":{},"attempts":{},"checkpoints":{},"reports":{},"events":[],"gates":{},"metrics":{},"audit":[],"event_sequence":0,"updated_at":now}
            if initial is not None:
                if not isinstance(initial, Mapping): raise RunStoreError("initial state must be an object")
                if self._STRUCTURAL.intersection(initial): raise RunStoreError("initial state contains structural fields")
                unknown = set(initial) - (self._FIELDS - self._STRUCTURAL)
                if unknown: raise RunStoreError("initial state contains unknown fields")
                for k,v in _redact(dict(initial), self.root).items():
                    if k in state: state[k] = v
            self._write(rid, state); return deepcopy(self._seal(state))
    def _validate(self, data: Any, rid: str) -> bool:
        if not isinstance(data, dict): return False
        req = ("schema_version","run_id","plan_hash","plan","generation","owner","status","waves","tasks","leases","attempts","checkpoints","reports","events","gates","metrics","audit","event_sequence","updated_at","checksum")
        if any(k not in data for k in req): return False
        if set(data) != self._FIELDS: return False
        if data["schema_version"] != self.schema_version or data["run_id"] != rid or type(data["generation"]) is not int or data["generation"] < 0 or type(data["event_sequence"]) is not int or data["event_sequence"] < 0: return False
        if type(data["owner"]) is not str or not _ID.fullmatch(data["owner"]) or data["status"] not in _STATUSES or type(data["updated_at"]) is not str: return False
        if not isinstance(data["plan"], dict) or type(data["plan_hash"]) is not str or not all(isinstance(data[k], (dict,list)) for k in req[7:17]): return False
        try:
            if plan_hash(data["plan"]) != data["plan_hash"]: return False
            _clock_value(lambda: data["updated_at"])
            if self._checksum(data) != data["checksum"]: return False
        except (RunStoreError, TypeError, ValueError, KeyError): return False
        if any(not isinstance(w, dict) for w in data["waves"]): return False
        if any(not isinstance(t, dict) or ("status" in t and t["status"] not in _TASK_STATUSES) for t in data["tasks"].values()): return False
        for task_id, lease in data["leases"].items():
            if type(task_id) is not str or not _ID.fullmatch(task_id) or not isinstance(lease, dict): return False
            if set(lease) != {"owner", "lease_id", "expires_at", "generation"}: return False
            if type(lease.get("owner")) is not str or not _ID.fullmatch(lease["owner"]): return False
            if type(lease.get("lease_id")) is not str or not _ID.fullmatch(lease["lease_id"]): return False
            if type(lease.get("expires_at")) is not str or type(lease.get("generation")) is not int or lease["generation"] < 0: return False
            try: _clock_value(lambda: lease["expires_at"])
            except RunStoreError: return False
        if any(type(v) is not int or v < 0 for v in data["attempts"].values()): return False
        if any(not isinstance(v, dict) for v in data["checkpoints"].values()): return False
        if any(type(k) is not str or not _ID.fullmatch(k) or not self._valid_report_record(v) for k, v in data["reports"].items()): return False
        events=data["events"]
        if any(not self._valid_event(e) for e in events): return False
        seq=[e["sequence"] for e in events]
        return seq == list(range(1, data["event_sequence"]+1))
    @staticmethod
    def _checksum(data: Mapping[str, Any]) -> str:
        body = {k: v for k, v in data.items() if k != "checksum"}
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    @classmethod
    def _seal(cls, state: Mapping[str, Any]) -> dict[str, Any]:
        sealed = deepcopy(dict(state)); sealed["checksum"] = cls._checksum(sealed); return sealed
    @staticmethod
    def _valid_report(report: Any, status: str) -> bool:
        if not isinstance(report, Mapping) or set(report) - _REPORT_FIELDS: return False
        if report.get("status") != status: return False
        for key in ("started_at", "completed_at"):
            if key in report:
                try: _clock_value(lambda: report[key])
                except RunStoreError: return False
        if status == "completed":
            return report.get("outputs") not in (None, "", [], {}) and report.get("evidence") not in (None, "", [], {}) and (report.get("tests") not in (None, "", [], {}) or report.get("validation") not in (None, "", [], {})) and report.get("decision") not in (None, "", [], {}) and all(k in report for k in ("started_at", "completed_at"))
        return any(report.get(k) not in (None, "", [], {}) for k in ("reason", "error", "blocker"))
    @classmethod
    def _valid_report_record(cls, value: Any) -> bool:
        if not isinstance(value, dict) or set(value) != {"status", "report", "digest", "attempt", "lease_id", "lease_generation"} or value.get("status") not in _REPORT_STATUSES: return False
        if not isinstance(value.get("report"), dict) or set(value["report"]) - _REPORT_FIELDS: return False
        if type(value.get("attempt")) is not int or value["attempt"] < 1 or type(value.get("lease_id")) is not str or not _ID.fullmatch(value["lease_id"]): return False
        if type(value.get("lease_generation")) is not int or value["lease_generation"] < 0 or type(value.get("digest")) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["digest"]): return False
        try: digest = hashlib.sha256(json.dumps(value["report"], sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        except (TypeError, ValueError): return False
        return digest == value["digest"] and cls._valid_report(value["report"], value["status"])
    @staticmethod
    def _valid_event(event: Any) -> bool:
        if not isinstance(event, dict) or type(event.get("sequence")) is not int or event["sequence"] < 1: return False
        if type(event.get("event_id")) is not str or not _ID.fullmatch(event["event_id"]): return False
        if type(event.get("ordering_key")) is not str or not event["ordering_key"]: return False
        if "generation" in event and (type(event["generation"]) is not int or event["generation"] < 0): return False
        if "metadata" in event and not isinstance(event["metadata"], dict): return False
        return True
    def _valid_snapshot(self, run_id: str) -> dict[str, Any] | None:
        found=[]
        for suffix in ("", ".bak"):
            p=self._path(run_id,suffix)
            try:
                if p.is_symlink(): continue
                data=self._read_snapshot_fd(p)
                if self._validate(data,run_id): found.append(data)
            except (OSError, json.JSONDecodeError, UnicodeError): pass
        return max(found,key=lambda x:x["generation"]) if found else None
    def load(self, run_id: str) -> dict[str, Any]:
        with self._guard():
            data=self._valid_snapshot(run_id)
            if data is None:
                # If either on-disk candidate exists but cannot be parsed or
                # validated, the run is corrupt (as opposed to simply absent).
                existing = False
                for suffix in ("", ".bak"):
                    path = self._path(run_id, suffix)
                    try:
                        if path.is_symlink():
                            raise PathContainmentError("snapshot path is symlink")
                        candidate = json.loads(path.read_text(encoding="utf-8"))
                        existing = True
                    except PathContainmentError:
                        raise
                    except (OSError, json.JSONDecodeError, UnicodeError):
                        if path.exists(): existing = True
                        continue
                    if not isinstance(candidate, dict) or "checksum" in candidate:
                        existing = True
                if existing:
                    raise CorruptSnapshotError("run snapshot malformed or no valid candidate")
                raise RunNotFoundError("run snapshot unavailable")
            return deepcopy(data)
    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        while view:
            n = os.write(fd, view)
            if n <= 0: raise OSError(errno.EIO, "short write")
            view = view[n:]

    def _read_snapshot_fd(self, path: Path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode): raise OSError(errno.ELOOP, "snapshot is not regular")
            chunks=[]
            while True:
                chunk=os.read(fd, 1024*1024)
                if not chunk: break
                chunks.append(chunk)
            return json.loads(b"".join(chunks).decode("utf-8"))
        finally: os.close(fd)

    def _write(self, run_id: str, state: Mapping[str, Any]) -> None:
        try: d=self._ensure_dir(run_id)
        except OSError as exc: raise RunStoreError("cannot prepare run directory") from exc
        target=self._path(run_id); backup=self._path(run_id,".bak")
        payload=json.dumps(self._seal(state),sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
        fd=-1; temp=None; bfd=-1; btmp=None; dfd=-1
        try:
            if target.is_symlink() or backup.is_symlink():
                raise PathContainmentError("snapshot path is symlink")
            name=f"snapshot.json.tmp-{secrets.token_hex(12)}"; temp=d/name
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            self._write_all(fd,payload); os.fsync(fd); os.close(fd); fd=-1
            # Copy the old primary only after opening it with O_NOFOLLOW. A
            # malformed primary is deliberately not promoted to the backup.
            try: old=self._read_snapshot_fd(target)
            except (OSError, json.JSONDecodeError, UnicodeError): old=None
            if old is not None and self._validate(old,run_id):
                btmp=d/f"snapshot.json.bak-{secrets.token_hex(12)}"
                bfd=os.open(btmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                src=os.open(target,os.O_RDONLY|os.O_NOFOLLOW)
                try:
                    while True:
                        chunk=os.read(src,1024*1024)
                        if not chunk: break
                        self._write_all(bfd,chunk)
                finally: os.close(src)
                os.fsync(bfd); os.close(bfd); bfd=-1
                os.replace(btmp,backup); btmp=None
            os.replace(temp,target); temp=None
            dfd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try: os.fsync(dfd)
            finally: os.close(dfd); dfd=-1
        except (PathContainmentError, RunStoreError): raise
        except OSError as exc: raise RunStoreError("cannot persist run snapshot") from exc
        finally:
            for f in (fd,bfd,dfd):
                if f >= 0:
                    try: os.close(f)
                    except OSError: pass
            for p in (temp,btmp):
                if p is not None:
                    try: os.unlink(p)
                    except OSError: pass
    def _mutate(self, run_id, owner, expected_generation, fn):
        with self._guard():
            state=self._valid_snapshot(run_id)
            if state is None: raise RunNotFoundError("run snapshot unavailable")
            if state["owner"] != owner: raise OwnerMismatchError("run owner mismatch")
            if expected_generation is not None and (type(expected_generation) is not int or state["generation"] != expected_generation): raise GenerationConflictError("generation mismatch")
            candidate=deepcopy(state); fn(candidate); candidate["generation"] += 1
            # Lease fencing is scoped to the lease operation itself.  A
            # generation bump caused by an unrelated event, transition, or
            # release must not invalidate leases belonging to other tasks.
            # ``claim``/``renew`` explicitly assign their changed lease's
            # generation and token, while ``commit`` removes its lease.
            candidate["updated_at"]=_clock_value(self._clock); self._write(run_id,candidate); return deepcopy(candidate)
    def transition(self, run_id, status, owner, *, expected_generation=None):
        def change(s):
            if type(status) is not str or status not in _STATUSES: raise RunStoreError("invalid status")
            s["status"] = status
        return self._mutate(run_id,owner,expected_generation,change)
    def append_event(self, run_id,event,owner,*,expected_generation=None):
        if not isinstance(event,Mapping): raise RunStoreError("event must be an object")
        def add(s):
            item=_redact(dict(event),self.root)
            supplied = item.get("ordering_key", item.get("event_id"))
            if "event_id" in item and (type(item["event_id"]) is not str or not item["event_id"]):
                raise RunStoreError("event event_id must be a nonempty string")
            if supplied is not None and (type(supplied) is not str or not supplied):
                raise RunStoreError("event ordering_key must be a nonempty string")
            if supplied is None:
                body = {k: v for k, v in item.items() if k not in {"sequence", "event_id", "ordering_key"}}
                supplied = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            item.setdefault("event_id", supplied)
            item["ordering_key"] = supplied
            item["sequence"]=s["event_sequence"]+1; s["events"].append(item); s["event_sequence"]+=1
        return self._mutate(run_id,owner,expected_generation,add)
    def claim(self,run_id,task_id,owner,*,lease_seconds=60,expected_generation=None):
        _safe_id(task_id); expiry=_plus_seconds(_clock_value(self._clock),lease_seconds); token=secrets.token_hex(16)
        def add(s):
            plan_tasks = s["plan"].get("tasks", [])
            known = {item.get("id") for item in plan_tasks if isinstance(item, Mapping)}
            if task_id not in known: raise RunStoreError("unknown task id")
            old=s["leases"].get(task_id)
            if old and old["expires_at"] > _clock_value(self._clock): raise LeaseError("task already leased")
            s["leases"][task_id]={"owner":owner,"lease_id":token,"expires_at":expiry,"generation":s["generation"]+1}; s["attempts"][task_id]=s["attempts"].get(task_id,0)+1
        state=self._mutate(run_id,owner,expected_generation,add); return {"run_id":run_id,"task_id":task_id,"lease_id":token,"generation":state["generation"],"expires_at":expiry}

    def claim_many(self, run_id, task_ids, owner, *, max_parallel, lease_seconds: float = 60,
                   select: Callable[..., list[str]] | None = None):
        """Atomically select and install bounded leases under the store lock.

        ``select`` runs while the filesystem lock is held, allowing the
        scheduler to perform path-overlap checks against the same snapshot
        used for the capacity check.  A selector accepting the optional
        ``now`` keyword receives the authoritative store time used for lease
        activity and installation. It must return a deterministic subset of
        the supplied IDs and never mutate the snapshot.
        """
        if type(max_parallel) is not int or max_parallel < 1:
            raise RunStoreError("max_parallel must be positive")
        if type(lease_seconds) not in (int, float) or isinstance(lease_seconds, bool) or not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise LeaseError("lease duration must be positive")
        ids = list(task_ids)
        if any(type(tid) is not str or not _ID.fullmatch(tid) for tid in ids) or len(set(ids)) != len(ids):
            raise RunStoreError("invalid task id")
        with self._guard():
            state = self._valid_snapshot(run_id)
            if state is None: raise RunNotFoundError("run snapshot unavailable")
            if state["owner"] != owner: raise OwnerMismatchError("run owner mismatch")
            known = {item.get("id") for item in state["plan"].get("tasks", []) if isinstance(item, Mapping)}
            if any(tid not in known for tid in ids): raise RunStoreError("unknown task id")
            # Re-check lifecycle state while holding the same lock used for
            # capacity and lease installation. A task can become terminal
            # after ready_ids() and must never be replay-claimed.
            terminal = {
                tid for tid, value in state["tasks"].items()
                if isinstance(value, Mapping) and value.get("status") in _TERMINAL_TASK_STATUSES
            }
            terminal.update(
                tid for tid, value in state["reports"].items()
                if isinstance(value, Mapping) and value.get("status") in _TERMINAL_TASK_STATUSES
            )
            if any(tid in terminal for tid in ids):
                raise RunStoreError("cannot claim terminal task")
            now = _clock_value(self._clock)
            # Expired leases are reclaimed as part of the locked claim
            # transaction. This keeps the selector's snapshot authoritative
            # and prevents stale leases from surviving beside a replacement.
            reclaimed = False
            for tid, lease in list(state["leases"].items()):
                if lease.get("expires_at", "") <= now:
                    state["leases"].pop(tid, None)
                    reclaimed = True
            active = set(state["leases"])
            capacity = max_parallel - len(active)
            if capacity <= 0:
                raise RunStoreError("bounded capacity exceeded")
            available = [tid for tid in ids if tid not in active]
            # Keep the authoritative post-reclamation state separate from the
            # selector's input. Selectors are extension code and must not be
            # able to persist arbitrary changes by mutating their snapshot.
            selector_state = deepcopy(state)
            available_for_validation = frozenset(available)
            if select:
                # Keep the original three-argument selector contract while
                # allowing lease-aware selectors to use the exact clock value
                # that was evaluated under this lock.
                try:
                    parameters = tuple(inspect.signature(select).parameters.values())
                except (TypeError, ValueError):
                    parameters = ()
                now_parameter = next(
                    (parameter for parameter in parameters if parameter.name == "now"),
                    None,
                )
                accepts_kwargs = any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in parameters
                )
                if now_parameter is not None and now_parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                    # A positional-only ``now`` cannot be supplied as a
                    # keyword, despite being discoverable by name.
                    chosen = select(selector_state, available, capacity, now)
                elif now_parameter is not None or accepts_kwargs:
                    chosen = select(selector_state, available, capacity, now=now)
                else:
                    # Preserve the original three-argument selector contract.
                    chosen = select(selector_state, available, capacity)
            else:
                chosen = available[:capacity]
            if not isinstance(chosen, list) or len(chosen) > capacity or any(tid not in available_for_validation for tid in chosen) or len(set(chosen)) != len(chosen):
                raise RunStoreError("invalid claim selection")
            if not chosen:
                if reclaimed:
                    candidate = deepcopy(state)
                    candidate["generation"] += 1
                    candidate["updated_at"] = now
                    self._write(run_id, candidate)
                return []
            expiry = _plus_seconds(now, lease_seconds)
            generation = state["generation"] + 1
            tokens = []
            candidate = deepcopy(state)
            for tid in chosen:
                token = secrets.token_hex(16)
                candidate["leases"][tid] = {"owner": owner, "lease_id": token, "expires_at": expiry, "generation": generation}
                candidate["attempts"][tid] = candidate["attempts"].get(tid, 0) + 1
                tokens.append({"run_id": run_id, "task_id": tid, "lease_id": token, "generation": generation, "expires_at": expiry})
            candidate["generation"] = generation
            candidate["updated_at"] = _clock_value(self._clock)
            self._write(run_id, candidate)
            return tokens
    def _check_token(self,s,task_id,token):
        if not isinstance(token,Mapping) or type(token.get("generation")) is not int or type(token.get("lease_id")) is not str: raise LeaseError("invalid lease")
        lease=s["leases"].get(task_id)
        if not lease or lease.get("lease_id")!=token["lease_id"] or lease.get("generation")!=token["generation"] or lease.get("expires_at","")<=_clock_value(self._clock): raise LeaseError("stale or expired lease")
        return lease
    def use(self,run_id,task_id,token,owner):
        with self._guard():
            s=self._valid_snapshot(run_id)
            if s is None: raise RunNotFoundError("run snapshot unavailable")
            if s["owner"]!=owner: raise OwnerMismatchError("run owner mismatch")
            self._check_token(s,task_id,token); return deepcopy(s)
    def renew(self,run_id,task_id,token,owner,*,lease_seconds=60):
        if type(lease_seconds) not in (int,float) or isinstance(lease_seconds,bool) or not math.isfinite(lease_seconds) or lease_seconds<=0: raise LeaseError("lease duration must be positive")
        refreshed = {}
        def change(s):
            lease = self._check_token(s,task_id,token)
            new_id = secrets.token_hex(16)
            expiry = _plus_seconds(_clock_value(self._clock), lease_seconds)
            # _mutate increments the snapshot generation immediately after
            # this callback; bind the new lease to that next generation.
            lease.update(lease_id=new_id, expires_at=expiry, generation=s["generation"] + 1)
            refreshed.update(run_id=run_id, task_id=task_id, lease_id=new_id,
                             generation=s["generation"] + 1, expires_at=expiry)
        self._mutate(run_id,owner,None,change)
        return refreshed
    def commit(self,run_id,task_id,token,owner,report,*,status="completed"):
        if type(status) is not str or status not in _REPORT_STATUSES: raise RunStoreError("commit status must be terminal")
        safe=_redact(dict(report),self.root) if isinstance(report,Mapping) else (_ for _ in ()).throw(RunStoreError("report must be an object"))
        if not self._valid_report(safe, status): raise RunStoreError("incomplete or invalid terminal report")
        digest=hashlib.sha256(json.dumps(safe,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()).hexdigest()
        with self._guard():
            s=self._valid_snapshot(run_id)
            if s is None: raise RunNotFoundError("run snapshot unavailable")
            if s["owner"]!=owner: raise OwnerMismatchError("run owner mismatch")
            if not isinstance(token,Mapping): raise LeaseError("invalid lease")
            existing=s["reports"].get(task_id)
            if existing is not None:
                if existing.get("lease_id")!=token.get("lease_id") or existing.get("lease_generation")!=token.get("generation"): raise LeaseError("stale or invalid lease")
                if existing.get("digest")==digest and existing.get("status")==status: return deepcopy(s)
                raise DuplicateCommitError("task already committed")
            self._check_token(s,task_id,token)
            candidate=deepcopy(s); candidate["reports"][task_id]={"status":status,"report":safe,"digest":digest,"attempt":candidate["attempts"].get(task_id,1),"lease_id":token["lease_id"],"lease_generation":token["generation"]}; candidate["tasks"].setdefault(task_id,{})["status"]=status; candidate["leases"].pop(task_id,None); candidate["generation"]+=1; candidate["updated_at"]=_clock_value(self._clock); self._write(run_id,candidate); return deepcopy(candidate)
    def query(self,run_id,key=None):
        state=self.load(run_id)
        if key == "events":
            return sorted(deepcopy(state["events"]), key=lambda event: (event["ordering_key"], event["sequence"]))
        return deepcopy(state if key is None else state.get(key))

__all__=["FleetRunStore","RunStoreError","RunNotFoundError","OwnerMismatchError","GenerationConflictError","LeaseError","DuplicateCommitError","PathContainmentError","CorruptSnapshotError"]
