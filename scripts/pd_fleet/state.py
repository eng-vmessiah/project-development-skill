"""Estado versionado da fleet, independente do estado legado do PD.

As funções de normalização e validação não mutam o payload recebido.  O bloco
``fleet_state`` é deliberadamente um namespace separado: a lista ``tasks`` no
nível raiz continua sendo a lista legada de strings concluídas.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

FLEET_STATE_SCHEMA_VERSION = 1
FLEET_STATE_FIELDS = (
    "schema_version", "agents", "waves", "tasks", "gates", "reports",
    "attempts", "blockers", "evidence", "updated_at",
)
_COLLECTION_FIELDS = FLEET_STATE_FIELDS[1:-1]


class FleetStateError(ValueError):
    """Payload de fleet_state inválido."""


def default_fleet_state(*, updated_at: str = "") -> dict[str, Any]:
    """Retorna um novo bloco vazio; nunca compartilha listas entre chamadas."""
    return {
        "schema_version": FLEET_STATE_SCHEMA_VERSION,
        **{name: [] for name in _COLLECTION_FIELDS},
        "updated_at": updated_at,
    }


def normalize_fleet_state(value: Any) -> dict[str, Any]:
    """Normaliza um bloco opcional, preservando campos desconhecidos.

    Tipos inválidos nos campos conhecidos são tratados como ausentes (o estado
    antigo continua legível), enquanto valores e chaves desconhecidos são
    copiados sem alteração.  Tasks legadas nunca são consultadas nem mescladas.
    """
    source: Mapping[str, Any] = value if isinstance(value, Mapping) else {}
    result = deepcopy(dict(source))
    result.setdefault("schema_version", FLEET_STATE_SCHEMA_VERSION)
    if not isinstance(result["schema_version"], (int, str)) or isinstance(result["schema_version"], bool):
        result["schema_version"] = FLEET_STATE_SCHEMA_VERSION
    for name in _COLLECTION_FIELDS:
        item = result.get(name)
        if isinstance(item, list):
            result[name] = deepcopy(item)
        elif isinstance(item, tuple):
            result[name] = deepcopy(list(item))
        else:
            result[name] = []
    if "updated_at" not in result or result["updated_at"] is None:
        result["updated_at"] = ""
    elif not isinstance(result["updated_at"], str):
        result["updated_at"] = str(result["updated_at"])
    return result


def validate_fleet_state(value: Any) -> tuple[str, ...]:
    """Valida sem modificar e retorna erros determinísticos (vazio = válido)."""
    if not isinstance(value, Mapping):
        return ("fleet_state deve ser um objeto",)
    errors: list[str] = []
    version = value.get("schema_version", FLEET_STATE_SCHEMA_VERSION)
    if isinstance(version, bool) or not isinstance(version, (int, str)):
        errors.append("fleet_state.schema_version deve ser inteiro ou string")
    for name in _COLLECTION_FIELDS:
        if name in value and not isinstance(value[name], (list, tuple)):
            errors.append(f"fleet_state.{name} deve ser uma lista")
    if "updated_at" in value and value["updated_at"] is not None and not isinstance(value["updated_at"], str):
        errors.append("fleet_state.updated_at deve ser uma string")
    return tuple(errors)


def migrate_fleet_state(root: Mapping[str, Any]) -> dict[str, Any]:
    """Copia um estado raiz e garante o namespace novo, sem migrar root.tasks."""
    result = deepcopy(dict(root))
    result["fleet_state"] = normalize_fleet_state(result.get("fleet_state"))
    return result


# Compatibility names for callers that used the generic state terminology.
SCHEMA_VERSION = FLEET_STATE_SCHEMA_VERSION
DEFAULT_FLEET_STATE = default_fleet_state
normalize = normalize_fleet_state
validate = validate_fleet_state
normalize_state = normalize_fleet_state
validate_state = validate_fleet_state
