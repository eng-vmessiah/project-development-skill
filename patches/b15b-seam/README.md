# B15b.1 — Série replayable: plugin observer seam (default-off)

**Base pinada:** `dc50153faf` (live tip do checkout Hermes).
**Série:** `0001-feat-fleet-add-default-off-plugin-observer-seam-B15b.patch` (1 patch) — adiciona `tui_gateway/plugin_observer.py` + `tests/tui_gateway/test_plugin_observer.py`.
**Escopo:** seam read-only (`B15B-SEAM-CONTRACT.md` v0.3 §2): registry irmão do `PluginRpcRegistry` (namespace **exato** `fleet`; `enabled` obrigatório; batch **atômico**; colisão/duplicata ⇒ erro; callable obrigatório) + publish **outbound** com isolamento de exceção (contido; log redigido) e fail-closed por versão (`pd-fleet-gateway-bridge:v1`). **0 call sites** — nada registra nem consome o seam ainda.

**Prova de replay (05/10):** `git am` limpo em worktree descartável @ `dc50153faf` → tree **`39dd54e4be8af609e996a0bca84107e98157a599`** idêntico ao branch `b15b-seam` (worktree `~/project/hermes-agent-b15b-seam`, commit `c9c09b666e`).

**Fixtures (7/7 ✓):** `default_off_no_handlers` · `config_absent_disabled_invalid` · `namespace_rejections` · `batch_is_atomic_on_failure` · `handler_exception_isolated` · `version_unsupported_fails_closed` · `golden_non_fleet_registry_untouched`. Vizinhos (sem regressão): 12/12 (`test_fleet_tui_registration` + `test_fleet_tui_boot`).

**Não incluído (fases futuras):** wiring de boot/composition root (ativação) · principal resolution real (B15b.2) · publisher de eventos do gateway (B15b.3/.4) · instalação/ativação no checkout vivo (pedido separado) · live validation (B15b.5).
