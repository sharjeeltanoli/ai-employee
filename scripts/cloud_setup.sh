#!/usr/bin/env bash
# ============================================================
# cloud_setup.sh — Run ONCE on Oracle Cloud VM after SSH in
# Usage: bash cloud_setup.sh
#
# What it does:
#   1. Installs git, python3, pip, uv, nodejs, pm2
#   2. Clones the vault repo using a GitHub PAT
#   3. Configures git credential storage so future pulls/pushes
#      don't ask for a password
# ============================================================
set -euo pipefail

# ── EDIT THESE BEFORE RUNNING ────────────────────────────────
GITHUB_USER="sharjeeltanoli"
GITHUB_REPO="ai-employee"
GITHUB_PAT=""          # paste your PAT here (classic, repo scope)
CLONE_DIR="$HOME/ai-employee-vault"
# ─────────────────────────────────────────────────────────────

if [[ -z "$GITHUB_PAT" ]]; then
  echo "ERROR: set GITHUB_PAT at the top of this script before running."
  exit 1
fi

echo "==> Updating package list..."
sudo apt-get update -qq

echo "==> Installing system dependencies..."
sudo apt-get install -y git python3 python3-pip curl unzip

echo "==> Installing uv (fast Python package manager)..."
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Add uv to PATH for this session
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "==> Installing Node.js (LTS) + PM2..."
if ! command -v node &>/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
if ! command -v pm2 &>/dev/null; then
  sudo npm install -g pm2
fi

echo "==> Configuring git identity..."
git config --global user.name  "$GITHUB_USER"
git config --global user.email "$GITHUB_USER@users.noreply.github.com"

echo "==> Storing GitHub PAT in git credential store..."
git config --global credential.helper store
# Write creds file that git credential store reads
echo "https://${GITHUB_USER}:${GITHUB_PAT}@github.com" > "$HOME/.git-credentials"
chmod 600 "$HOME/.git-credentials"

echo "==> Cloning repo..."
REPO_URL="https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git"
if [[ -d "$CLONE_DIR/.git" ]]; then
  echo "    Repo already cloned at $CLONE_DIR — skipping clone."
else
  git clone "$REPO_URL" "$CLONE_DIR"
fi

echo "==> Installing Python dependencies..."
cd "$CLONE_DIR/ai-employee"
uv sync || uv pip install -r requirements.txt 2>/dev/null || true

echo ""
echo "✓ Setup complete!"
echo "  Repo cloned to: $CLONE_DIR"
echo "  git credential store: $HOME/.git-credentials"
echo ""
echo "Next steps:"
echo "  1. Copy your Gmail token/credentials into $CLONE_DIR/ai-employee/"
echo "  2. Run:  bash $CLONE_DIR/scripts/vault_sync.sh   (manual test)"
echo "  3. Run:  crontab -e   and add the cron line from vault_sync.sh"
echo "  4. Run:  bash $CLONE_DIR/scripts/setup_pm2.sh   to start gmail-watcher"
