#!/usr/bin/env bash
# ============================================================
# setup_pm2.sh — Register all AI-Employee processes with PM2
# Run ONCE after cloud_setup.sh.
# ============================================================
set -euo pipefail

VAULT_DIR="${VAULT_DIR:-$HOME/ai-employee-vault}"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$VAULT_DIR/ai-employee"

echo "==> Starting gmail-watcher under PM2..."
pm2 delete gmail-watcher 2>/dev/null || true
pm2 start \
  --name gmail-watcher \
  --interpreter bash \
  -- -c "uv run python gmail_watcher.py"

echo "==> Saving PM2 process list..."
pm2 save

echo "==> Enabling PM2 startup on reboot..."
# Generates a command you need to run as root — copy/paste it
pm2 startup | tail -1

echo ""
echo "Run the sudo command printed above, then:"
echo "  pm2 status   — to verify all processes are online"
