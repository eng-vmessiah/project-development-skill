#!/usr/bin/env bash
# B15a.2 3b-ii — ativar o fleet TUI canary no serve vivo (fail-safe, logado)
# Uso:  bash run-3bii.sh          # executa (derruba Desktop/bots ~1-2 min)
#       bash run-3bii.sh --check  # pré-checagens read-only
#
# O que faz: stop serviços → git am do patch 0022 (default-off; só adiciona o
# gate de boot) → drop-in systemd com HERMES_FLEET_TUI_CANARY=1 SÓ no
# hermes-serve → daemon-reload → start → smoke (serve HTTP + "[fleet-canary]
# enabled" no journal).
#
# Rollback: R1 (fleet off, código fica): rm do drop-in + daemon-reload + restart serve.
#           R2 (reverter tudo): R1 + git reset --hard 6b5d888382 + restart serve.
# Sem backup de DB: nenhuma migração de schema neste patch (toca só tui_gateway/web_server).
set -uo pipefail
BK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HOME/.hermes/hermes-agent"
PATCH="$HOME/project/project-development-skill/patches/b15a2-live/0022-feat-fleet-explicit-env-gated-boot-enable.patch"
DROPIN_DIR="$HOME/.config/systemd/user/hermes-serve.service.d"
DROPIN="$DROPIN_DIR/fleet-canary.conf"
PRE_TIP="6b5d888382"
LOG="$BK/run.log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
die() {
  log "✗ FALHOU: $*"
  log "→ restaurando (drop-in removido + serviços)..."
  rm -f "$DROPIN" 2>/dev/null || true
  systemctl --user daemon-reload 2>/dev/null || true
  systemctl --user start hermes-serve isis-gateway 2>/dev/null || true
  log "→ git agora em: $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)"
  log "→ rollback R1/R2 documentado no cabeçalho deste script"
  exit 1
}

if [[ "${1:-}" == "--check" ]]; then
  echo "== PRÉ-CHECAGENS (read-only) =="
  cd "$REPO" || exit 1
  echo "repo: $(git rev-parse --short HEAD) (esperado $PRE_TIP) | alterações: $(git status --porcelain | wc -l)"
  echo "patch existe: $(test -f "$PATCH" && echo sim || echo NÃO)"
  echo "patch já aplicado: $(git log -1 --format=%s | grep -q b15a2-3bii && echo sim || echo não)"
  echo "patch aplica (--check): $(git apply --check "$PATCH" 2>/dev/null && echo sim || echo NÃO)"
  echo "drop-in atual: $(test -f "$DROPIN" && echo presente || echo ausente)"
  echo "serviços: serve=$(systemctl --user is-active hermes-serve) gateway=$(systemctl --user is-active isis-gateway)"
  exit 0
fi

cd "$REPO" || die "repo inacessível"

log "1/6 STOP serviços"
systemctl --user stop hermes-serve isis-gateway || die "stop"

log "2/6 PATCH (git am 0022 — gate de boot default-off)"
if git log -1 --format=%s | grep -q "b15a2-3bii"; then
  log "  (já aplicado — pulando git am)"
else
  git am "$PATCH" || { git am --abort 2>/dev/null || true; die "git am"; }
fi
git log --oneline -1 | tee -a "$LOG"
git log -1 --format=%s | grep -q "b15a2-3bii" || die "verify do patch (subject)"

log "3/6 DROP-IN systemd (flag só no hermes-serve)"
mkdir -p "$DROPIN_DIR"
cat > "$DROPIN" <<'EOF'
[Service]
# B15a.2 · 3b-ii — fleet TUI canary (local, read-only). Rollback: remover este
# arquivo + daemon-reload + restart do hermes-serve.
Environment=HERMES_FLEET_TUI_CANARY=1
EOF
systemctl --user daemon-reload || die "daemon-reload"

log "4/6 START"
systemctl --user start hermes-serve isis-gateway || die "start"

log "5/6 SMOKE"
sleep 8
log "serve: $(systemctl --user is-active hermes-serve) | gateway: $(systemctl --user is-active isis-gateway)"
curl -s -o /dev/null -w "serve HTTP %{http_code}\n" --max-time 10 http://127.0.0.1:9119/ | tee -a "$LOG" || log "⚠ HTTP inconclusivo"

log "6/6 VERIFY (canário ligado?)"
FOUND=""
for i in 1 2 3 4 5 6; do
  if journalctl --user -u hermes-serve --since "5 min ago" --no-pager 2>/dev/null | grep -qF "[fleet-canary] enabled"; then FOUND=1; break; fi
  sleep 5
done
if [ -n "$FOUND" ]; then
  journalctl --user -u hermes-serve --since "5 min ago" --no-pager 2>/dev/null | grep -F "[fleet-canary] enabled" | tail -1 | tee -a "$LOG"
  log "✓ fleet TUI canary LIGADO no serve"
else
  log "⚠ '[fleet-canary] enabled' não visto no journal ainda — conferir: journalctl --user -u hermes-serve | grep fleet-canary"
fi
log "✓ 3b-ii CONCLUÍDO — Desktop deve reconectar em instantes. Log: $LOG"
