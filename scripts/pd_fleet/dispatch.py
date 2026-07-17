"""Dispatch local, determinístico e seguro para tasks da fleet.

Este módulo é deliberadamente independente do CLI, de subprocessos e da rede.
Somente o adapter ``simulated`` é habilitado por padrão; adapters de providers,
URLs e credenciais são recusados explicitamente (fail closed).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, fields
from hashlib import sha256
import json
import re
import inspect
from copy import deepcopy
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable



class DispatchError(ValueError):
    """Erro acionável ao selecionar ou executar um dispatch."""


class UnknownAdapterError(DispatchError):
    """O adapter solicitado não está registrado."""


class AdapterDeniedError(DispatchError):
    """Adapter externo ou input potencialmente inseguro recusado."""


@runtime_checkable
class DispatchAdapter(Protocol):
    """Contrato mínimo: adapters não alteram a task e retornam um resultado."""

    @property
    def name(self) -> str: ...

    def dispatch(self, task: Any, context: Mapping[str, Any]) -> "DispatchResult": ...


@dataclass(frozen=True)
class DispatchResult:
    task_id: str
    adapter: str
    status: str
    attempt: int
    result: Any = None
    evidence: Any = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        # ``frozen`` only protects the dataclass attributes; nested payloads are
        # deliberately copied so a report cannot mutate dispatcher state.
        return deepcopy(asdict(self))

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


@dataclass(frozen=True)
class DispatchRecord:
    task_id: str
    adapter: str
    attempt: int
    status: str
    result: DispatchResult
    evidence: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "adapter": self.adapter,
            "attempt": self.attempt,
            "status": self.status,
            "result": self.result.to_dict(),
            "evidence": deepcopy(self.evidence),
        }


class SimulatedAdapter:
    """Adapter puro: produz sempre o mesmo output para o mesmo input."""

    __slots__ = ()

    @property
    def name(self) -> str:
        # No instance dictionary or setter means this can never be shadowed.
        return "simulated"

    def dispatch(self, task: Any, context: Mapping[str, Any]) -> DispatchResult:
        task_id = _task_value(task, "id", "task_id")
        payload = {"task": _jsonable(task), "context": _jsonable(context)}
        digest = sha256(_canonical(payload).encode("utf-8")).hexdigest()
        attempt = context.get("attempt", 1)
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            attempt = 1
        result: dict[str, Any] = {"output": f"simulated:{task_id}:{digest[:16]}", "fingerprint": digest}
        evidence = {"adapter": self.name, "deterministic": True, "fingerprint": digest}
        # Opt-in V2 report keeps the legacy result shape unchanged by default.
        if context.get("report_v2") is True:
            result["report"] = {
                "schema_version": "pd-fleet-report:v2", "task_id": task_id,
                "attempt": attempt, "agent_id": str(_value(task, "owner", None) or _value(task, "role", "local")),
                "role": str(_value(task, "role", "worker")), "capabilities": list(_value(task, "capabilities", []) or []),
                "status": "completed", "outputs": {str((_value(task, "outputs", ["output"]) or ["output"])[0]): result["output"]}, "evidence": evidence,
                "tests": [{"name": "local", "status": "passed"}], "validation": {"status": "passed", "fingerprint": digest},
                "decision": {"decision": "accept"}, "started_at": "1970-01-01T00:00:00Z", "completed_at": "1970-01-01T00:00:00Z",
            }
        return DispatchResult(task_id, self.name, "completed", attempt, result, evidence)


# Friendly aliases for consumers that use the plan terminology.
LocalDispatchAdapter = SimulatedAdapter
AdapterProtocol = DispatchAdapter


def _mapping_copy(value: Mapping[Any, Any], message: str) -> dict[Any, Any]:
    try:
        # Validate keys before insertion: arbitrary keys can run hostile __hash__.
        pairs = list(value.items())
        copied: dict[Any, Any] = {}
        for key, item in pairs:
            if type(key) is not str or not key.strip():
                raise ValueError
            copied[key] = item
        return copied
    except Exception:
        raise DispatchError(message) from None


def _native_nonempty_string(value: Any, message: str) -> str:
    if type(value) is not str or not value.strip():
        raise DispatchError(message)
    return value.strip()


def _task_value(task: Any, *names: str) -> str:
    for name in names:
        value = _value(task, name, None)
        if type(value) is str and value.strip():
            return value.strip()
    raise DispatchError("task exige um id string não vazio")


def _value(task: Any, name: str, default: Any = None) -> Any:
    try:
        if isinstance(task, Mapping):
            return task.get(name, default)
        descriptor = inspect.getattr_static(task, name, default)
        if isinstance(descriptor, property):
            raise DispatchError("campo de task inacessível")
        return getattr(task, name, default)
    except DispatchError:
        raise
    except Exception:
        raise DispatchError("campo de task inacessível") from None


def _jsonable(value: Any) -> Any:
    """Convert values without invoking arbitrary reprs (or leaking addresses)."""
    return _jsonable_inner(value, set())


def _jsonable_inner(value: Any, seen: set[int]) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    marker = id(value)
    if marker in seen:
        return {"__cycle__": _type_name(value)}
    seen.add(marker)
    try:
        if isinstance(value, Mapping):
            try:
                pairs = [(_jsonable_inner(k, seen), _jsonable_inner(v, seen))
                         for k, v in value.items()]
                pairs.sort(key=lambda p: _canonical(p[0]))
                return {str(k): v for k, v in pairs}
            except DispatchError:
                raise
            except Exception:
                raise DispatchError("entrada mapping inacessível") from None
        if isinstance(value, (list, tuple)):
            return [_jsonable_inner(v, seen) for v in value]
        if isinstance(value, (set, frozenset)):
            values = [_jsonable_inner(v, seen) for v in value]
            return {"__set__": sorted(values, key=_canonical)}
        if is_dataclass(value) and not isinstance(value, type):
            return {f.name: _jsonable_inner(getattr(value, f.name), seen) for f in fields(value)}
        converter = getattr(value, "to_dict", None)
        if callable(converter):
            try:
                return _jsonable_inner(converter(), seen)
            except Exception:
                pass
        attrs = _safe_attrs(value)
        if isinstance(attrs, dict):
            public_attrs = {}
            try:
                for key, child in attrs.items():
                    label = str(key)
                    if label.startswith("_"):
                        continue
                    public_attrs[label] = _jsonable_inner(child, seen)
            except Exception:
                raise DispatchError("atributos de entrada inacessíveis") from None
            return {"__object_type__": _type_name(value), "attributes": public_attrs}
        # Do not use repr: the default repr contains a process-dependent address.
        return {"__object_type__": _type_name(value)}
    finally:
        seen.discard(marker)


def _type_name(value: Any) -> str:
    typ = type(value)
    return f"{typ.__module__}.{typ.__qualname__}"


def _canonical(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


_URL_RE = re.compile(r"(?i)(?:https?|ftp|wss?)://[^\s\"'<>]+")
_SECRET_VALUE_RE = re.compile(
    r"(?i)(?:\bbearer\s+\S+|\bsk-[a-z0-9_-]+)"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![a-z0-9])([a-z][a-z0-9_. -]{1,80})\s*[:=]\s*\S+"
)


def _safe_attrs(value: Any) -> Any:
    try:
        attrs = getattr(value, "__dict__", None)
        return attrs if isinstance(attrs, dict) else None
    except Exception:
        return None


def _denied_key(label: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", label.lower())
    return any(word in normalized for word in (
        "credential", "secret", "token", "password", "apikey", "accesskey",
        "privatekey", "clientsecret", "authorization", "bearer",
    ))


def _contains_secret_assignment(value: str) -> bool:
    return any(_denied_key(match.group(1)) for match in _SECRET_ASSIGNMENT_RE.finditer(value))


def _public_properties(value: Any) -> tuple[str, ...]:
    """Find properties without invoking descriptors or user ``__dir__``."""
    found: list[str] = []
    try:
        for cls in type(value).__mro__:
            for name in vars(cls):
                if name.startswith("_") or name in found:
                    continue
                if isinstance(inspect.getattr_static(value, name, None), property):
                    found.append(name)
    except Exception:
        raise AdapterDeniedError("dispatch recusado: entrada não pode ser inspecionada") from None
    return tuple(found)


def _contains_denied(value: Any, path: str = "input", _seen: set[int] | None = None,
                     _depth: int = 0) -> str | None:
    """Retorna a primeira chave/URL proibida, sem tentar acessar seu conteúdo."""
    if _seen is None:
        _seen = set()
    if _depth > 64:
        raise AdapterDeniedError("dispatch recusado: estrutura de entrada profunda demais")
    if value is None or isinstance(value, (int, float, bool)):
        return None
    if value is not None and not isinstance(value, str):
        marker = id(value)
        if marker in _seen:
            raise AdapterDeniedError("dispatch recusado: estrutura cíclica não permitida")
        _seen.add(marker)
    if isinstance(value, Mapping):
        try:
            items = value.items()
            iterator = iter(items)
            for key, child in iterator:
                try:
                    label = str(key)
                except Exception:
                    raise AdapterDeniedError("dispatch recusado: chave de entrada inválida") from None
                if _denied_key(label):
                    return "credencial proibida na entrada"
                found = _contains_denied(child, path, _seen, _depth + 1)
                if found:
                    return found
        except AdapterDeniedError:
            raise
        except Exception:
            raise AdapterDeniedError("dispatch recusado: mapping de entrada inacessível") from None
    elif isinstance(value, (list, tuple, set, frozenset)):
        for index, child in enumerate(value):
            found = _contains_denied(child, path, _seen, _depth + 1)
            if found:
                return found
    elif isinstance(value, str):
        if _SECRET_VALUE_RE.search(value) or _contains_secret_assignment(value):
            return "valor potencialmente secreto na entrada"
        if _URL_RE.search(value):
            return f"URL externa proibida em {path}"
    elif is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            if _denied_key(item.name):
                return "credencial proibida na entrada"
            try:
                child = getattr(value, item.name)
            except Exception:
                raise AdapterDeniedError("dispatch recusado: campo de entrada inacessível") from None
            found = _contains_denied(child, path, _seen, _depth + 1)
            if found:
                return found
    else:
        properties = _public_properties(value)
        if properties:
            for name in properties:
                if _denied_key(name) or re.search(r"(?i)(?:endpoint|url)", name):
                    return "propriedade sensível proibida na entrada"
            raise AdapterDeniedError("dispatch recusado: propriedades de entrada não permitidas")
        try:
            converter = getattr(value, "to_dict", None)
        except Exception:
            raise AdapterDeniedError("dispatch recusado: entrada não pode ser inspecionada") from None
        if callable(converter):
            try:
                found = _contains_denied(converter(), path, _seen, _depth + 1)
                if found:
                    return found
            except AdapterDeniedError:
                raise
            except Exception:
                raise AdapterDeniedError("dispatch recusado: conversão da entrada falhou") from None
        attrs = _safe_attrs(value)
        if attrs is not None:
            try:
                for key, child in attrs.items():
                    try:
                        label = str(key)
                    except Exception:
                        raise AdapterDeniedError("dispatch recusado: chave de entrada inválida") from None
                    # Inspect private names, but never access private values.
                    if label.startswith("_"):
                        if _denied_key(label):
                            return "credencial proibida na entrada"
                        continue
                    if _denied_key(label):
                        return "credencial proibida na entrada"
                    found = _contains_denied(child, path, _seen, _depth + 1)
                    if found:
                        return found
            except AdapterDeniedError:
                raise
            except Exception:
                raise AdapterDeniedError("dispatch recusado: atributos de entrada inacessíveis") from None
        else:
            raise AdapterDeniedError("dispatch recusado: entrada opaca não permitida")
    return None


class Dispatcher:
    """Seleciona adapter por capability/role e mantém histórico de dispatches."""

    def __init__(self, adapters: Mapping[str, DispatchAdapter] | None = None,
                 routes: Mapping[str, str] | None = None, *, dry_run: bool = False) -> None:
        routes_map = _mapping_copy(routes if routes is not None else {}, "routes mapping inacessível")
        for key, value in routes_map.items():
            try:
                valid = (type(key) is str and bool(key.strip()) and
                         type(value) is str and bool(value.strip()))
            except Exception:
                valid = False
            if not valid:
                raise DispatchError("routes exige chaves e valores string não vazios")
        supplied = _mapping_copy(adapters if adapters is not None else {}, "adapters mapping inacessível")
        self._simulated_override = "simulated" in supplied and not isinstance(supplied["simulated"], SimulatedAdapter)
        registry = {"simulated": SimulatedAdapter()}
        registry.update({k: v for k, v in supplied.items() if k != "simulated"})
        self._adapters = MappingProxyType(registry)
        self._routes = MappingProxyType(routes_map)
        if not isinstance(dry_run, bool):
            raise DispatchError("dry_run deve ser booleano")
        self.dry_run = dry_run
        self._records: list[DispatchRecord] = []
        self._by_request: dict[tuple[str, str, str, int], DispatchRecord] = {}

    @property
    def adapters(self) -> Mapping[str, DispatchAdapter]:
        """Read-compatible, immutable view of the adapter registry."""
        return self._adapters

    @property
    def routes(self) -> Mapping[str, str]:
        return self._routes

    @staticmethod
    def _copy_result(result: DispatchResult) -> DispatchResult:
        return DispatchResult(result.task_id, result.adapter, result.status,
                              result.attempt, deepcopy(result.result),
                              deepcopy(result.evidence), result.error)

    @staticmethod
    def _copy_record(record: DispatchRecord) -> DispatchRecord:
        result = Dispatcher._copy_result(record.result)
        return DispatchRecord(record.task_id, record.adapter, record.attempt,
                              record.status, result, deepcopy(record.evidence))

    def select_adapter(self, task: Any, context: Mapping[str, Any] | None = None) -> str:
        if context is None:
            context_map: Mapping[str, Any] = {}
        else:
            if not isinstance(context, Mapping):
                raise DispatchError("context deve ser um mapping")
            context_map = _mapping_copy(context, "context mapping inacessível")
        explicit = _value(task, "adapter", None)
        if explicit is None:
            explicit = context_map.get("adapter")
        if explicit is not None:
            return _native_nonempty_string(explicit, "adapter explícito inválido")
        capabilities = _value(task, "capabilities", None)
        if capabilities is None:
            capabilities = []
        if (not isinstance(capabilities, (list, tuple, set, frozenset)) or
                any(type(c) is not str or not c.strip() for c in capabilities)):
            raise DispatchError("capabilities deve ser uma sequência de strings")
        for capability in capabilities:
            if capability in self._routes:
                return self._routes[capability]
        role = _value(task, "role")
        if role is not None:
            role = _native_nonempty_string(role, "role inválido")
            if role in self._routes:
                return self._routes[role]
        return "simulated"

    def dispatch(self, task: Any, context: Mapping[str, Any] | None = None) -> DispatchResult:
        if context is not None and not isinstance(context, Mapping):
            raise DispatchError("context deve ser um mapping")
        context = _mapping_copy(context if context is not None else {}, "context mapping inacessível")
        task_id = _task_value(task, "id", "task_id")
        # Validation deliberately precedes idempotency lookup.
        denied = _contains_denied(task) or _contains_denied(context, "context")
        if denied:
            raise AdapterDeniedError(f"dispatch recusado: {denied}; remova o dado externo e tente novamente")
        if "dry_run" in context and not isinstance(context["dry_run"], bool):
            raise DispatchError("dry_run deve ser booleano")
        attempt = context.get("attempt", 1)
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise DispatchError("attempt deve ser um inteiro positivo")
        adapter_name = self.select_adapter(task, context)
        fingerprint = sha256(_canonical({"task": task, "context": context}).encode("utf-8")).hexdigest()
        request_key = (task_id, fingerprint, adapter_name, attempt)
        if request_key in self._by_request:
            return self._copy_result(self._by_request[request_key].result)
        if self._simulated_override:
            raise AdapterDeniedError("adapter simulated fornecido externamente recusado; use o adapter interno")
        if adapter_name not in self.adapters:
            raise UnknownAdapterError("adapter desconhecido; disponível: simulated")
        if adapter_name != "simulated":
            raise AdapterDeniedError("adapter externo recusado por default-deny; use simulated")
        if self.dry_run or context.get("dry_run", False):
            result = DispatchResult(task_id, adapter_name, "dry_run", 0,
                                    {"would_dispatch": True}, {"fingerprint": fingerprint, "dry_run": True})
        else:
            try:
                result = self.adapters[adapter_name].dispatch(deepcopy(task), deepcopy(context))
                if not isinstance(result, DispatchResult):
                    raise TypeError("invalid adapter result")
            except Exception as exc:
                # Exception text is intentionally omitted: it can contain secrets.
                result = DispatchResult(task_id, adapter_name, "failed", attempt,
                                        None, {"fingerprint": fingerprint},
                                        "adapter falhou; detalhes não são expostos")
        stored_result = self._copy_result(result)
        record = DispatchRecord(task_id, adapter_name, stored_result.attempt, stored_result.status,
                                stored_result, deepcopy(stored_result.evidence))
        self._records.append(record)
        self._by_request[request_key] = record
        return self._copy_result(stored_result)

    @property
    def history(self) -> list[DispatchRecord]:
        return [self._copy_record(record) for record in self._records]

    def reports(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self._records]

    @property
    def records(self) -> list[DispatchRecord]:
        """Backward-compatible defensive history view."""
        return self.history
