#!/usr/bin/env bash
# Run Claude with /process-files skill non-interactively
# Logs output to /mnt/c/AI_Employee_Vault/Logs/cron.log with timestamp

LOG_FILE="/mnt/c/AI_Employee_Vault/Logs/cron.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Timestamp function
timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

{
    echo "=========================================="
    echo "[$(timestamp)] Starting Claude /process-files run"
    echo "=========================================="

    # GMAIL_APP_PASSWORD must be set in the calling environment (e.g. cron, systemd)
    if [ -z "${GMAIL_APP_PASSWORD}" ]; then
        echo "[$(timestamp)] ERROR: GMAIL_APP_PASSWORD is not set. Aborting."
        exit 1
    fi
    export GMAIL_APP_PASSWORD

    # Run claude non-interactively: --print sends prompt and exits
    # --dangerously-skip-permissions avoids interactive permission prompts
    # Working directory is set to the vault so project context is loaded
    cd "$SCRIPT_DIR" || exit 1

    /root/.local/bin/claude \
        --print \
        --dangerously-skip-permissions \
        "/process-files"

    EXIT_CODE=$?

    echo "[$(timestamp)] Claude exited with code: $EXIT_CODE"
    echo "=========================================="
    echo ""
} >> "$LOG_FILE" 2>&1
