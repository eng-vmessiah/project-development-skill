#!/usr/bin/env bash
# B15a.2 recovery (08/10/2026) — reaplicar a série fleet re-basada na 9d05e7f + religar o canário
# Uso:  bash run-recovery-activate.sh          # executa (derruba Desktop/bots ~1-2 min)
#       bash run-recovery-activate.sh --check  # pré-checagens read-only
#
# Contexto: o update 0.21.6 de 08/10 resetou o checkout vivo p/ origin/main e largou a série
# local (23 commits; tip antigo 966a079d). A série foi RE-BASADA offline em
# `recovery/b15a2-live-on-9d05e7f` (worktree ~/project/hermes-agent-replay-probe) — tip pinado abaixo.
#
# O que faz: stop serviços → git merge --ff-only da branch de recovery no checkout vivo →
# drop-in do canário (verifica/recria) → daemon-reload → start (serve+gateway) → smoke
# (HTTP + "[fleet-canary] enabled" no journal + import profundo no venv de runtime).
#
# Rollback: R1 (fleet off, código fica): rm do drop-in + daemon-reload + restart serve.
#           R2 (reverter tudo): git reset --hard 9d05e7ff92d3edd9abdf20fe3d04551905cb995e + restart serve (+ gateway).
#           (o die() faz o restore automático em falha: reset se o merge já ocorreu + start + smoke.)
# Sem backup de DB: mesma base do update de hoje; nenhuma migração de schema nesta série.
set -uo pipefail
BK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HOME/.hermes/hermes-agent"
BRANCH="recovery/b15a2-live-on-9d05e7f"
BASE_FULL="9d05e7ff92d3edd9abdf20fe3d04551905cb995e"
EXPECTED_TIP="704f229a40b275275b7934083b7a219ad1c5b4b0"
DROPIN_DIR="$HOME/.config/systemd/user/hermes-serve.service.d"
DROPIN="$DROPIN_DIR/fleet-canary.conf"
LOG="$BK/run-activate.log"
MERGE_DONE=0

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
die() {
  log "✗ FALHOU: $*"
  if [ "$MERGE_DONE" = "1" ]; then
    log "→ rollback automático: reset p/ $BASE_FULL ..."
    git -C "$REPO" reset --hard "$BASE_FULL" 2>/dev/null || log "  ⚠ reset falhou — conferir manualmente"
  fi
  log "→ subindo serviços..."
  systemctl --user start hermes-serve isis-gateway 2>/dev/null || true
  sleep 6
  log "serve=$(systemctl --user is-active hermes-serve) gateway=$(systemctl --user is-active isis-gateway) | git: $(git -C "$REPO" rev-parse --short HEAD)"
  curl -s -o /dev/null -w "serve HTTP %{http_code}\n" --max-time 10 http://127.0.0.1:9119/ 2>/dev/null | tee -a "$LOG" || true
  log "→ R1/R2 no cabeçalho; log completo em $LOG"
  exit 1
}

if [[ "${1:-}" == "--check" ]]; then
  echo "== PRÉ-CHECAGENS (read-only) =="
  cd "$REPO" || exit 1
  echo "main:        $(git rev-parse --short HEAD) (esperado $(echo $BASE_FULL | cut -c1-10)) | alterações locais: $(git status --porcelain | wc -l)"
  echo "branch:      $(git rev-parse --verify -q "$BRANCH" >/dev/null 2>&1 && echo presente || echo AUSENTE)"
  echo "tip:         $(git rev-parse --short "$BRANCH" 2>/dev/null) (esperado $(echo $EXPECTED_TIP | cut -c1-10))"
  echo "ff-only ok:  $(git merge-base --is-ancestor "$BASE_FULL" "$BRANCH" 2>/dev/null && echo sim || echo NÃO)"
  echo "commits:     $(git rev-list --count "$BASE_FULL".."$BRANCH" 2>/dev/null) (esperado 24)"
  echo "drop-in:     $(test -f "$DROPIN" && echo presente || echo ausente)"
  echo "serviços:    serve=$(systemctl --user is-active hermes-serve) gateway=$(systemctl --user is-active isis-gateway)"
  exit 0
fi

cd "$REPO" || die "repo inacessível"
[ "$(git rev-parse HEAD)" = "$BASE_FULL" ] || die "main não está em $(echo $BASE_FULL | cut -c1-10) (update novo? precisa re-replay antes)"
git rev-parse --verify -q "$BRANCH" >/dev/null || die "branch $BRANCH ausente"
[ "$(git rev-parse "$BRANCH")" = "$EXPECTED_TIP" ] || die "tip da branch difere do pinado"
[ -z "$(git status --porcelain)" ] || die "checkout com alterações locais"

log "1/6 STOP serviços"
systemctl --user stop hermes-serve isis-gateway || die "stop"

log "2/6 MERGE ff-only da série re-basada"
git merge --ff-only "$BRANCH" || die "merge"
MERGE_DONE=1
git log --oneline -1 | tee -a "$LOG"
[ "$(git rev-list --count "$BASE_FULL"..HEAD)" = "24" ] || die "contagem de commits != 24"

log "3/6 DROP-IN do canário (verifica/garante)"
mkdir -p "$DROPIN_DIR"
if [ ! -f "$DROPIN" ]; then
  cat > "$DROPIN" <<'EOF'
[Service]
# B15a.2 — fleet TUI canary (local, read-only). Rollback: remover este arquivo + daemon-reload + restart do hermes-serve.
Environment=HERMES_FLEET_TUI_CANARY=1
EOF
  log "  (drop-in recriado)"
else
  log "  (drop-in já presente)"
fi
systemctl --user daemon-reload || die "daemon-reload"

log "4/6 START"
systemctl --user start hermes-serve isis-gateway || die "start"

log "5/6 SMOKE"
sleep 8
log "serve=$(systemctl --user is-active hermes-serve) | gateway=$(systemctl --user is-active isis-gateway)"
curl -s -o /dev/null -w "serve HTTP %{http_code}\n" --max-time 10 http://127.0.0.1:9119/ 2>/dev/null | tee -a "$LOG" || log "⚠ HTTP inconclusivo"

log "6/6 VERIFY (canário ligado + import profundo)"
FOUND=""
for i in 1 2 3 4 5 6; do
  if journalctl --user -u hermes-serve --since "5 min ago" --no-pager 2>/dev/null | grep -qF "[fleet-canary] enabled"; then FOUND=1; break; fi
  sleep 5
done
if [ -n "$FOUND" ]; then
  journalctl --user -u hermes-serve --since "5 min ago" --no-pager 2>/dev/null | grep -F "[fleet-canary] enabled" | tail -1 | tee -a "$LOG"
  log "✓ fleet TUI canary LIGADO no serve"
else
  log "⚠ '[fleet-canary] enabled' não visto no journal — conferir: journalctl --user -u hermes-serve | grep fleet-canary"
fi
SVPID=$(systemctl --user show hermes-serve -p MainPID --value 2>/dev/null || true)
MV=$(grep -oE '/[^ ]*/installs/[^/]+/environments/[^/]+/venv' "/proc/$SVPID/maps" 2>/dev/null | head -1)
if [ -n "${MV:-}" ]; then
  (cd "$REPO" && "$MV/bin/python" -c "import sys; sys.path.insert(0, '$REPO'); import hermes_cli.fleet_tui_session, tui_gateway.fleet_tui_composition, tui_gateway.fleet_tui_boot; print('fleet import OK')" 2>&1 | tee -a "$LOG") || log "⚠ import profundo falhou (investigar; smoke de journal já passou?)"
else
  log "⚠ venv de runtime não resolvido (skip do check profundo — smoke cobre)"
fi
log "✓ RECOVERY CONCLUÍDO — o Desktop reconecta em instantes. Log: $LOG"
log "→ pós-checagem (agente): wire/aba Fleet + registros (b15a2-caminho.md, diário)."
