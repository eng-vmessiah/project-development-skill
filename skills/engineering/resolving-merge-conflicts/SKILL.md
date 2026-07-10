---
name: resolving-merge-conflicts
description: Resolver conflitos de merge/rebase de forma estruturada. Inspirado por mattpocock/skills.
version: 1.0.0
metadata:
  source: github.com/mattpocock/skills
---

# Resolving Merge Conflicts

## Passo a passo

1. **Veja o estado atual** do merge/rebase. Confira git history e os arquivos conflitantes.

2. **Encontre as fontes primárias** de cada conflito. Entenda por que cada change foi feita. Leia commit messages, PRs, issues originais.

3. **Resolva cada hunk.** Preserve ambas as intenções onde possível. Onde incompatível, escolha a que melhor atende o objetivo do merge e documente o trade-off. **Nunca invente comportamento novo.** Sempre resolva; nunca `--abort`.

4. **Descubra e execute os checks automáticos** do projeto — typecheck, tests, linter. Corrija o que o merge quebrou.

5. **Finalize o merge/rebase.** Stage tudo e commit. Se for rebase, continue até todos os commits serem rebaseados.

## Completion criterion

Merge concluído com sucesso, todos os checks passando, e cada decisão de conflito documentada no commit message.
