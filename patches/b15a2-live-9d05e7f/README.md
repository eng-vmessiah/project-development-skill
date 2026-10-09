# B15a.2 — série re-basada na `9d05e7f` (08/10/2026)

24 patches, replayable via `git am` sobre `9d05e7ff92d3edd9abdf20fe3d04551905cb995e`:

- **0001–0022** — série B15a.2 + início B15b (replay fiel da série verificada de 04/10; base original `ea81748579`).
- **0023** — B15b.1 (observer seam) — exportado do ref de backup do update (`966a079d`).
- **0024** — adaptação do re-base: teste de packaging PyYAML → `hermes_yaml` (upstream unificou YAML em ruamel).

**Verificação:** ver `HANDOFF.md` — 14 arquivos da série 235✓/0✗; canônica base×recovery = delta zero real
(30 falhas pré-existentes idênticas; flake `change_watcher*` em ambos os lados, classe pré-existente).
Tip final: `704f229a40b275275b7934083b7a219ad1c5b4b0`.

**Ativação:** `run-recovery-activate.sh` (`--check` → run). **Rollback:** R1/R2 no HANDOFF ou
`git reset --hard 9d05e7ff92d3edd9abdf20fe3d04551905cb995e` + restart.
