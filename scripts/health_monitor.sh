#!/usr/bin/env bash
# ============================================================
# health_monitor.sh — PM2 process watchdog
#
# Checks that gmail-watcher is running under PM2.
# If stopped/errored, restarts it and logs the event.
#
# Cron line to install (run: crontab -e):
#   */5 * * * * /bin/bash $HOME/ai-employee-vault/scripts/health_monitor.sh >> $HOME/logs/health_monitor.log 2>&1
#
# To monitor multiple processes, add their names to WATCHED_PROCESSES.
# ============================================================
set -euo pipefail

# ── CONFIG ───────────────────────────────────────────────────
WATCHED_PROCESSES=("gmail-watcher")   # add more names as needed
VAULT_DIR="${VAULT_DIR:-$HOME/ai-employee-vault}"
LOG_DIR="$HOME/logs"
MAX_LOG_LINES=500
# ─────────────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
log()       { echo "[$(timestamp)] $*"; }

# Rotate log if too large
LOG_FILE="$LOG_DIR/health_monitor.log"
if [[ -f "$LOG_FILE" ]] && (( $(wc -l < "$LOG_FILE") > MAX_LOG_LINES )); then
  mv "$LOG_FILE" "${LOG_FILE}.bak"
fi

# Ensure PATH includes pm2 (installed globally via npm)
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

if ! command -v pm2 &>/dev/null; then
  log "ERROR: pm2 not found in PATH ($PATH). Install with: sudo npm install -g pm2"
  exit 1
fi

# ── Check each watched process ───────────────────────────────
for PROCESS_NAME in "${WATCHED_PROCESSES[@]}"; do

  # pm2 jlist outputs JSON array of all processes
  STATUS=$(pm2 jlist 2>/dev/null | python3 -c "
import sys, json
procs = json.load(sys.stdin)
for p in procs:
    if p.get('name') == '${PROCESS_NAME}':
        print(p.get('pm2_env', {}).get('status', 'unknown'))
        sys.exit(0)
print('not_found')
" 2>/dev/null || echo "pm2_error")

  log "[$PROCESS_NAME] status = $STATUS"

  case "$STATUS" in
    online)
      log "[$PROCESS_NAME] OK — process is healthy."
      ;;

    stopped|errored|stopping)
      log "[$PROCESS_NAME] ALERT — status=$STATUS. Restarting..."
      pm2 restart "$PROCESS_NAME" 2>&1 | while read -r line; do log "  pm2: $line"; done
      log "[$PROCESS_NAME] Restart issued."
      ;;

    not_found)
      log "[$PROCESS_NAME] ALERT — not registered in PM2. Attempting to start from $VAULT_DIR..."
      # Adjust the start command for your stack:
      #   python script  → pm2 start "uv run python gmail_watcher.py" --name gmail-watcher
      #   node script    → pm2 start server.js --name gmail-watcher
      cd "$VAULT_DIR/ai-employee" || { log "ERROR: $VAULT_DIR/ai-employee not found"; exit 1; }

      pm2 start \
        --name "$PROCESS_NAME" \
        --interpreter bash \
        -- -c "uv run python gmail_watcher.py" \
        2>&1 | while read -r line; do log "  pm2: $line"; done

      pm2 save 2>&1 | while read -r line; do log "  pm2 save: $line"; done
      log "[$PROCESS_NAME] Started and saved to PM2 registry."
      ;;

    pm2_error)
      log "[$PROCESS_NAME] WARNING — could not query PM2 status. Is PM2 running?"
      ;;

    *)
      log "[$PROCESS_NAME] WARNING — unexpected status '$STATUS'."
      ;;
  esac

done

log "--- health check done ---"
