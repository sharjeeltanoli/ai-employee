#!/usr/bin/env bash
# ============================================================
# vault_sync.sh — Bidirectional git sync for the AI Vault
#
# Called by cron every 5 minutes.
# Pulls remote changes first, then commits and pushes any
# local changes (new emails processed, logs, etc.).
#
# Cron line to install (run: crontab -e):
#   */5 * * * * /bin/bash $HOME/ai-employee-vault/scripts/vault_sync.sh >> $HOME/logs/vault_sync.log 2>&1
# ============================================================
set -euo pipefail

# ── CONFIG ───────────────────────────────────────────────────
VAULT_DIR="${VAULT_DIR:-$HOME/ai-employee-vault}"
LOG_DIR="$HOME/logs"
LOG_FILE="$LOG_DIR/vault_sync.log"
MAX_LOG_LINES=1000   # rotate log when it exceeds this
# ─────────────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

log() { echo "[$(timestamp)] $*"; }

# Rotate log if too large
if [[ -f "$LOG_FILE" ]] && (( $(wc -l < "$LOG_FILE") > MAX_LOG_LINES )); then
  mv "$LOG_FILE" "${LOG_FILE}.bak"
fi

# Ensure we're in the repo
if [[ ! -d "$VAULT_DIR/.git" ]]; then
  log "ERROR: $VAULT_DIR is not a git repo. Run cloud_setup.sh first."
  exit 1
fi

cd "$VAULT_DIR"

# ── 1. Pull remote changes ───────────────────────────────────
log "--- sync start ---"
log "Pulling from origin/main..."

# Stash any uncommitted changes before pull to avoid conflicts
if ! git diff --quiet || ! git diff --cached --quiet; then
  log "Stashing local changes before pull..."
  git stash push -m "auto-stash-$(date +%s)" --include-untracked 2>&1 | while read -r line; do log "  $line"; done
  STASHED=true
else
  STASHED=false
fi

PULL_OUTPUT=$(git pull --rebase origin main 2>&1) || {
  log "WARNING: git pull failed — $PULL_OUTPUT"
  log "Attempting to restore stash and continue..."
  $STASHED && git stash pop 2>/dev/null || true
}
log "Pull: $PULL_OUTPUT"

# Restore stash after pull
if $STASHED; then
  STASH_POP=$(git stash pop 2>&1) || log "WARNING: stash pop failed — $STASH_POP"
  log "Stash restored: $STASH_POP"
fi

# ── 2. Stage and commit any new local changes ─────────────────
# Stage everything except secrets/venv
git add \
  Done/ \
  Needs_Action/ \
  Logs/ \
  Plans/ \
  Pending_Approval/ \
  ai-employee/sessions/ \
  2>/dev/null || true

# Only commit if there is something staged
if ! git diff --cached --quiet; then
  CHANGED_COUNT=$(git diff --cached --numstat | wc -l)
  COMMIT_MSG="auto-sync: ${CHANGED_COUNT} file(s) updated at $(timestamp)"
  git commit -m "$COMMIT_MSG" 2>&1 | while read -r line; do log "  $line"; done
  log "Committed: $COMMIT_MSG"
else
  log "Nothing new to commit."
fi

# ── 3. Push ──────────────────────────────────────────────────
PUSH_OUTPUT=$(git push origin main 2>&1) || {
  log "WARNING: git push failed — $PUSH_OUTPUT"
  log "--- sync done (with warnings) ---"
  exit 0
}
log "Push: $PUSH_OUTPUT"
log "--- sync done ---"
