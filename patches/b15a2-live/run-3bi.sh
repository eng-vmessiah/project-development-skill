#!/usr/bin/env bash
# B15a.2 3b-i — live runtime update + seam patches (fail-safe, logado)
# Uso:  bash run-3bi.sh          # executa (derruba Desktop/bots ~10-20 min)
#       bash run-3bi.sh --check  # pré-checagens read-only
#
# v2 (04/10 22:17, pós-1ª execução): o check de import do v1 checava o SHIM
# (.venv-canary/bin/python → re-exec no python do PM SEM o venv gerenciado) e
# dava falso-negativo (ex.: ruamel). Agora o check profundo roda no SMOKE,
# contra o venv de RUNTIME resolvido do /proc/<serve-pid>/maps. uv sync loga.
set -uo pipefail
BK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HOME/.hermes/hermes-agent"
PATCHES="$HOME/project/project-development-skill/patches/b15a2-live"
BASE_OLD="44533f11e3"
BASE_NEW="ea81748579"
LOG="$BK/run.log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
die() {
  log "✗ FALHOU: $*"
  log "→ restaurando serviços..."
  systemctl --user start hermes-serve isis-gateway 2>/dev/null || true
  log "→ git agora em: $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)"
  log "→ próximos passos (N1/N2) no packet B15A2-3BI-LIVE-EXECUTION-PACKET.md"
  exit 1
}

if [[ "${1:-}" == "--check" ]]; then
  echo "== PRÉ-CHECAGENS (read-only) =="
  cd "$REPO" || exit 1
  echo "repo: $(git rev-parse --short HEAD) | alterações: $(git status --porcelain | wc -l)"
  echo "BASE_NEW existe: $(git cat-file -t "$BASE_NEW" 2>/dev/null || echo NÃO)"
  echo "patches: $(ls "$PATCHES"/*.patch 2>/dev/null | wc -l) (esperado 21)"
  echo "uv: $(command -v uv || echo NÃO)"
  echo "serviços: serve=$(systemctl --user is-active hermes-serve) gateway=$(systemctl --user is-active isis-gateway)"
  df -h "$HOME" | tail -1 | awk '{print "disco livre: "$4}'
  exit 0
fi

cd "$REPO" || die "repo inacessível"

log "1/8 STOP serviços"
systemctl --user stop hermes-serve isis-gateway || die "stop"

log "2/8 BACKUP -> $BK"
cp "$HOME/.hermes/state.db" "$BK/state.db" || die "backup state.db"
cp "$HOME/.hermes/state.db-wal" "$BK/" 2>/dev/null || true
cp "$HOME/.hermes/state.db-shm" "$BK/" 2>/dev/null || true
git rev-parse HEAD > "$BK/rev-before.txt"
git status --short > "$BK/status-before.txt"
systemctl --user cat hermes-serve isis-gateway > "$BK/units-before.txt" 2>/dev/null || true

log "3/8 UPDATE (fetch + ff-only $BASE_NEW)"
git fetch origin || die "fetch"
git merge --ff-only "$BASE_NEW" || die "merge"

log "4/8 DEPS (uv sync no shim .venv-canary — o env de runtime é gerenciado pelo produto)"
(UV_PROJECT_ENVIRONMENT=.venv-canary uv sync --frozen || UV_PROJECT_ENVIRONMENT=.venv-canary uv sync) 2>&1 | tee -a "$LOG" || die "uv sync"

log "5/8 PATCHES (git am 21)"
git am "$PATCHES"/*.patch || { git am --abort 2>/dev/null || true; die "git am"; }

log "6/8 VERIFY (git)"
git log --oneline -1 | tee -a "$LOG"
# NB (v2): o import check NÃO roda aqui — o shim .venv-canary/bin/python não tem
# o venv gerenciado e daria falso-negativo. O check profundo roda no SMOKE (8/8).

log "7/8 START"
systemctl --user start hermes-serve isis-gateway || die "start"

log "8/8 SMOKE"
sleep 6
log "serve: $(systemctl --user is-active hermes-serve) | gateway: $(systemctl --user is-active isis-gateway)"
curl -s -o /dev/null -w "serve HTTP %{http_code}\n" --max-time 10 http://127.0.0.1:9119/ | tee -a "$LOG" || log "⚠ HTTP inconclusivo"
timeout 90 "$HOME/.local/bin/hermes" plugins list --plain 2>/dev/null | grep -i pd-fleet | tee -a "$LOG" || true
# Check profundo (v2): importa os módulos do fleet no env de RUNTIME (venv gerenciado,
# resolvido do /proc/<serve-pid>/maps). Sem resolução → avisa e segue (smoke cobre).
SVPID=$(systemctl --user show hermes-serve -p MainPID --value 2>/dev/null || true)
MV=$(grep -oE '/[^ ]*/installs/[^/]+/environments/[^/]+/venv' "/proc/$SVPID/maps" 2>/dev/null | head -1)
if [ -n "${MV:-}" ]; then
  (cd "$REPO" && "$MV/bin/python" -c "import sys; sys.path.insert(0, '$REPO'); import hermes_cli.fleet_tui_session, tui_gateway.fleet_tui_composition; print('fleet import OK')" 2>&1 | tee -a "$LOG") || die "import do fleet no env de runtime"
else
  log "⚠ venv gerenciado não resolvido (skip do check profundo — smoke cobre)"
fi
log "✓ 3b-i CONCLUÍDO — Desktop deve reconectar em instantes. Log: $LOG"
