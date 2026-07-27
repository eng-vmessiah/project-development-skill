# Tests — pd-fleet-supervisor-handoff

Os testes canônicos desta feature vivem no repositório compartilhado:

- `tests/fleet/test_supervision.py` — RED/GREEN para sinais e diagnóstico read-only;
- `tests/fleet/test_handoff.py` — RED/GREEN para artefato bounded/redacted.

Comandos:

```bash
python -m pytest -q tests/fleet/test_supervision.py tests/fleet/test_handoff.py
python -m pytest -q
```
