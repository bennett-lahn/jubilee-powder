#!/usr/bin/env bash
# update.sh - Apply pulled changes to a running Pi installation.
#
# Run after every `git pull`:
#   cd ~/jubilee-powder
#   bash deploy/update.sh
#
# What this script does:
#   1. Rebuilds the React frontend (frontend/dist/)
#   2. Upgrades Python dependencies if requirements.txt changed
#   3. Reloads systemd and restarts the backend service

set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${BLUE}[jubilee]${NC} $*"; }
ok()    { echo -e "${GREEN}[jubilee]${NC} $*"; }
die()   { echo -e "${RED}[jubilee] ERROR:${NC} $*" >&2; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURRENT_USER="${SUDO_USER:-$(whoami)}"
VENV="${REPO_DIR}/.venv"

[[ "$(id -u)" -eq 0 ]] || die "Run this script with sudo: sudo bash deploy/update.sh"

info "Repo: ${REPO_DIR}"
info "Updating as user: ${CURRENT_USER}"

# ---------------------------------------------------------------------------
# 1. Rebuild the React frontend
# ---------------------------------------------------------------------------
info "Rebuilding React frontend ..."
cd "${REPO_DIR}/frontend"
sudo -u "${CURRENT_USER}" npm install --silent
sudo -u "${CURRENT_USER}" npm run build
ok "Frontend rebuilt → frontend/dist/"

# ---------------------------------------------------------------------------
# 2. Upgrade Python dependencies
# ---------------------------------------------------------------------------
info "Upgrading Python dependencies ..."
[[ -d "${VENV}" ]] || die ".venv not found - run deploy/install.sh first."
sudo -u "${CURRENT_USER}" "${VENV}/bin/pip" install --quiet --upgrade pip
sudo -u "${CURRENT_USER}" "${VENV}/bin/pip" install --quiet -r "${REPO_DIR}/requirements.txt"
ok "Python dependencies up to date."

# ---------------------------------------------------------------------------
# 3. Reload systemd and restart the backend service
# ---------------------------------------------------------------------------
info "Restarting jubilee-backend service ..."
systemctl daemon-reload
systemctl restart "jubilee-backend@${CURRENT_USER}.service"
ok "jubilee-backend restarted."

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo
ok "Update complete."
echo -e "  Service status  : ${BLUE}systemctl status jubilee-backend@${CURRENT_USER}${NC}"
echo -e "  View logs       : ${BLUE}journalctl -u jubilee-backend@${CURRENT_USER} -f${NC}"
echo
