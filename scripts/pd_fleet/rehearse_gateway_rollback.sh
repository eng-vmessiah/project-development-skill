#!/usr/bin/env bash
# T-501 — rollback rehearsal for the isis-gateway.service procedure
# (stop → verify → start → verify), executed ONLY against a scratch user
# unit in a controlled environment. NEVER touches the live isis-gateway.
#
# Usage: bash scripts/pd_fleet/rehearse_gateway_rollback.sh [evidence-log]
set -euo pipefail

UNIT="pd-gateway-rehearsal.service"
UNIT_PATH="$HOME/.config/systemd/user/$UNIT"
EVIDENCE="${1:-$HOME/.hermes/cache/scratch/rollback-rehearsal-evidence.log}"

# Hard guard: this rehearsal must never operate on the live gateway unit.
if [[ "$UNIT" == "isis-gateway.service" ]]; then
  echo "refusing to rehearse against the live unit" >&2
  exit 99
fi

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$EVIDENCE"; }

cleanup() {
  systemctl --user stop "$UNIT" >/dev/null 2>&1 || true
  rm -f "$UNIT_PATH"
  systemctl --user daemon-reload >/dev/null 2>&1 || true
}
trap cleanup EXIT

: > "$EVIDENCE"
log "=== rollback rehearsal (controlled) — unit=$UNIT ==="

# 0. scratch unit mirroring the isis-gateway shape (Type=simple, Restart=on-failure)
mkdir -p "$(dirname "$UNIT_PATH")"
cat > "$UNIT_PATH" <<'EOF'
[Unit]
Description=pd rollback rehearsal (scratch; never the live gateway)
[Service]
Type=simple
ExecStart=/usr/bin/sleep infinity
Restart=on-failure
RestartSec=2
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
log "scratch unit installed"

# 1. baseline: start
systemctl --user start "$UNIT"
sleep 1
state=$(systemctl --user is-active "$UNIT" || true)
log "start -> is-active: $state"
[ "$state" = "active" ] || { log "FAIL: rehearsal unit not active"; exit 1; }

# 2. rollback step: stop
systemctl --user stop "$UNIT"
state=$(systemctl --user is-active "$UNIT" || true)
log "stop -> is-active: $state"
[ "$state" != "active" ] || { log "FAIL: unit still active after stop"; exit 1; }

# 3. verify stopped (no active process, no orphans)
if systemctl --user is-active --quiet "$UNIT"; then
  log "FAIL: orphan process after stop"
  exit 1
fi
log "verify stopped: no active process"

# 4. rollback step: start again
systemctl --user start "$UNIT"
sleep 1
state=$(systemctl --user is-active "$UNIT" || true)
log "restart -> is-active: $state"
[ "$state" = "active" ] || { log "FAIL: unit did not return active"; exit 1; }

# 5. verify healthy
main_pid=$(systemctl --user show "$UNIT" -p MainPID --value)
[ -n "$main_pid" ] && [ "$main_pid" != "0" ] || { log "FAIL: no MainPID"; exit 1; }
log "verify healthy: MainPID=$main_pid"
log "=== REHEARSAL PASS (controlled environment; live isis-gateway untouched) ==="
