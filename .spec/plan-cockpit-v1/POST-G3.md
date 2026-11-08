# POST-G3 — plan-cockpit-v1 (manutenção)

## 2026-11-08 — P2: guard test + contagem

- `.spec/plan-cockpit-v1/tests/test_plan_cockpit_contract.py`: guard do coletor — a feature continua no snapshot, `source: plan-yaml`, contagem coerente e determinismo com `HOME` hermético. **1 passed**.
- `T-000` registrada retroativamente no `STATE.json` (intake 04/10) ⇒ `pd status` 13/14.
- O 14º checkbox é `G1` (gate de aprovação); `task_stats` conta gates como task. O placar honesto é **13 tasks + G1 aprovado**; não logar gate em `STATE.tasks`.
- `pd validate --deep` **13/13**.
- O `VERIFICATION.md` assinado no G3 não foi reescrito; este adendo registra o trabalho posterior.
