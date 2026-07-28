"""Validações puras para DAG, contrato e ownership de um :mod:`pd_fleet`.

O módulo não altera ``FleetPlan`` nem conhece lifecycle de execução.  Todas as
mensagens são ordenadas para que erros e a saída de readiness sejam reproduzíveis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .models import FleetPlan, TaskSpec
from .safe_rendering import safe_repr


class FleetValidationError(ValueError):
    """Plano inválido; ``errors`` contém mensagens acionáveis e determinísticas."""

    def __init__(self, errors: str | Iterable[str]):
        self.errors = tuple(sorted({errors} if isinstance(errors, str) else set(errors)))
        super().__init__("; ".join(self.errors))


# Nome curto útil para consumidores que não querem importar o nome Fleet.
ValidationError = FleetValidationError


@dataclass(frozen=True)
class ValidationReport:
    """Resultado imutável de uma validação bem-sucedida."""

    task_ids: tuple[str, ...]
    ready_ids: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return True


def _path_overlap(left: str, right: str) -> bool:
    """Retorna se paths iguais ou em relação pai/filho (sem falsos ``foo``/``foobar``)."""
    a, b = left.strip("/"), right.strip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _parallel(a: TaskSpec, b: TaskSpec, by_id: Mapping[str, TaskSpec]) -> bool:
    if a.wave != b.wave:
        return False
    # Uma dependência (direta ou transitiva) impõe ordem; todo o resto da mesma
    # wave é potencialmente paralelo, inclusive grupos diferentes.
    def reaches(start: str, target: str, seen: set[str]) -> bool:
        if start in seen:
            return False
        seen.add(start)
        if start == target:
            return True
        current = by_id.get(start)
        if current is None:
            return False
        return any(reaches(dep, target, seen) for dep in current.depends_on)
    return not reaches(a.id, b.id, set()) and not reaches(b.id, a.id, set())


def validate_task_contract(task: TaskSpec) -> tuple[str, ...]:
    """Valida o mínimo para uma task poder ficar ``ready``.

    T1 mantém defaults permissivos para carregar planos antigos; readiness exige
    objetivo, critério, output e comando de validação explícitos.
    """
    errors: list[str] = []
    if not task.id.strip():
        errors.append("task sem id: informe um identificador não vazio")
    if not task.role.strip():
        errors.append(f"task {task.id}: role obrigatório")
    if not task.objective.strip():
        errors.append(f"task {task.id}: objective obrigatório")
    if not task.acceptance_criteria:
        errors.append(f"task {task.id}: contrato incompleto; informe acceptance_criteria")
    if not task.outputs:
        errors.append(f"task {task.id}: contrato incompleto; informe outputs")
    if not task.validation_commands:
        errors.append(f"task {task.id}: contrato incompleto; informe validation_commands")
    return tuple(errors)


def validate_dag(plan: FleetPlan) -> tuple[str, ...]:
    """Retorna erros de referências e ciclos do DAG, em ordem estável."""
    by_id = {task.id: task for task in plan.tasks}
    errors: list[str] = []
    for task in sorted(plan.tasks, key=lambda item: item.id):
        for dep in sorted(set(task.depends_on)):
            if dep not in by_id:
                errors.append(f"task {task.id}: dependência inexistente {safe_repr(dep)}; crie-a ou remova-a")
    # Não tenta percorrer arestas inválidas: a referência já tem diagnóstico melhor.
    color: dict[str, int] = {}
    stack: list[str] = []
    cycles: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        color[node] = 1
        stack.append(node)
        for dep in sorted(by_id[node].depends_on):
            if dep not in by_id:
                continue
            if color.get(dep, 0) == 0:
                visit(dep)
            elif color.get(dep) == 1:
                cycle = tuple(stack[stack.index(dep):] + [dep])
                # Rotação dá representação canônica independente do ponto de entrada.
                rotations = [cycle[i:-1] + cycle[:i] + (cycle[i],) for i in range(len(cycle) - 1)]
                cycles.add(min(rotations))
        stack.pop()
        color[node] = 2

    for task_id in sorted(by_id):
        if color.get(task_id, 0) == 0:
            visit(task_id)
    errors.extend("ciclo no DAG: " + " -> ".join(cycle) for cycle in sorted(cycles))
    return tuple(sorted(errors))


def validate_wave_gates(plan: FleetPlan) -> tuple[str, ...]:
    """Valida que todo gate usado por uma wave exista no plano."""
    gate_ids = {gate.id for gate in plan.gates}
    errors: list[str] = []
    for wave in sorted(plan.waves, key=lambda item: item.id):
        for gate_id in sorted(set(wave.gates)):
            if gate_id not in gate_ids:
                errors.append(
                    f"wave {wave.id}: gate inexistente {safe_repr(gate_id)}; "
                    "adicione-o a FleetPlan.gates ou remova-o de wave.gates"
                )
    return tuple(sorted(errors))


def validate_ownership(plan: FleetPlan) -> tuple[str, ...]:
    """Retorna inconsistências de allowed/forbidden e colisões paralelas."""
    errors: list[str] = []
    tasks = sorted(plan.tasks, key=lambda item: item.id)
    for task in tasks:
        allowed, forbidden = sorted(set(task.allowed_paths)), sorted(set(task.forbidden_paths))
        for a in allowed:
            for f in forbidden:
                if _path_overlap(a, f):
                    errors.append(f"task {task.id}: allowed_path {safe_repr(a)} conflita com forbidden_path {safe_repr(f)}; ajuste um dos paths")
    by_id = {task.id: task for task in plan.tasks}
    for index, left in enumerate(tasks):
        for right in tasks[index + 1:]:
            if not _parallel(left, right, by_id):
                continue
            for path_left in sorted(set(left.allowed_paths)):
                for path_right in sorted(set(right.allowed_paths)):
                    if _path_overlap(path_left, path_right):
                        errors.append(f"ownership conflitante: tasks {left.id} e {right.id} podem rodar em paralelo e sobrepõem {safe_repr(path_left)}/{safe_repr(path_right)}; serialize ou separe os paths")
    return tuple(sorted(errors))


def validate_plan(plan: FleetPlan | Mapping) -> ValidationReport:
    """Valida plano completo e retorna relatório imutável; inválido gera erro."""
    normalized = FleetPlan.from_dict(plan) if not isinstance(plan, FleetPlan) else plan
    errors = list(validate_dag(normalized))
    errors.extend(validate_wave_gates(normalized))
    for task in sorted(normalized.tasks, key=lambda item: item.id):
        errors.extend(validate_task_contract(task))
    errors.extend(validate_ownership(normalized))
    if errors:
        raise FleetValidationError(errors)
    return ValidationReport(tuple(sorted(task.id for task in normalized.tasks)))


def compute_ready_tasks(plan: FleetPlan | Mapping, *, completed: Iterable[str] = (), skipped: Iterable[str] = (), gates_passed: Iterable[str] = ()) -> tuple[str, ...]:
    """Calcula IDs ready deterministicamente, sem mutar statuses do plano.

    Waves são uma barreira: uma task só pode ser liberada depois que todas as
    tasks das waves anteriores estiverem em ``completed``/``skipped`` (ou forem
    informadas nos argumentos correspondentes). Os gates são os IDs declarados
    na ``WaveSpec`` da task, nunca o número da wave. ``blocked_when`` é texto
    descritivo do contrato e não é interpretado aqui.
    """
    normalized = FleetPlan.from_dict(plan) if not isinstance(plan, FleetPlan) else plan
    validate_plan(normalized)
    done = set(completed) | set(skipped)
    passed = set(gates_passed)
    terminal = done | {task.id for task in normalized.tasks if task.status in {"completed", "skipped"}}

    def canonical_wave_id(value: object) -> str:
        """Converte aliases (por exemplo, ``1`` e ``wave-1``) num único ID."""
        text = str(value).strip().lower()
        candidate = text[5:] if text.startswith("wave-") else text
        try:
            return f"wave-{int(candidate)}"
        except ValueError:
            return f"wave-{candidate}"

    def wave_key(value: str) -> tuple[int, object]:
        candidate = value.removeprefix("wave-")
        try:
            return (0, int(candidate))
        except ValueError:
            return (1, value)

    def wave_matches(wave_id: str, task_wave: object) -> bool:
        return canonical_wave_id(wave_id) == canonical_wave_id(task_wave)

    def required_gates(task: TaskSpec) -> frozenset[str]:
        required: set[str] = set()
        for wave in normalized.waves:
            if wave_matches(wave.id, task.wave):
                required.update(wave.gates)
        return frozenset(required)

    ordered_tasks = sorted(normalized.tasks, key=lambda item: item.id)
    wave_values = sorted({canonical_wave_id(task.wave) for task in normalized.tasks}, key=wave_key)
    wave_index = {value: index for index, value in enumerate(wave_values)}
    ready: list[str] = []
    for task in ordered_tasks:
        if task.status not in {"pending", "ready"} or set(task.depends_on) - terminal:
            continue
        index = wave_index[canonical_wave_id(task.wave)]
        if any(other.id not in terminal for other in normalized.tasks
               if wave_index[canonical_wave_id(other.wave)] < index):
            continue
        gates = required_gates(task)
        if gates and not gates <= passed:
            continue
        ready.append(task.id)
    return tuple(ready)


# API aliases kept small and explicit for callers/tests.
validate = validate_plan
ready_tasks = compute_ready_tasks
