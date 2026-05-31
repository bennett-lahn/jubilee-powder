#!/usr/bin/env bash
# install.sh - Set up Jubilee Automation for auto-launch on Raspberry Pi.
#
# Run once after cloning the repo:
#   cd ~/jubilee-powder
#   bash deploy/install.sh
#
# What this script does:
#   1. Installs system packages (Node.js, Chromium, unclutter)
#   2. Builds the React frontend into frontend/dist/
#   3. Creates a Python virtual environment and installs Python dependencies
#   4. Installs and enables the jubilee-backend systemd service
#   5. Configures LXDE autostart so Chromium opens at login in kiosk mode
#   6. Enables auto-login for the current user

set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${BLUE}[jubilee]${NC} $*"; }
ok()    { echo -e "${GREEN}[jubilee]${NC} $*"; }
die()   { echo -e "${RED}[jubilee] ERROR:${NC} $*" >&2; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="${REPO_DIR}/deploy"
CURRENT_USER="${SUDO_USER:-$(whoami)}"
USER_HOME="/home/${CURRENT_USER}"

[[ "$(id -u)" -eq 0 ]] || die "Run this script with sudo: sudo bash deploy/install.sh"

info "Repo: ${REPO_DIR}"
info "Installing as user: ${CURRENT_USER}"

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
info "Installing system packages ..."
apt-get update -qq

# Install everything except Node.js first so curl is available for NodeSource
apt-get install -y --no-install-recommends \
    chromium-browser \
    unclutter \
    curl \
    python3-venv \
    python3-pip

# Raspberry Pi OS ships Node.js 18 via apt, which is too old for Vite 8
# (requires Node 20.19+ or 22.12+).  Install Node.js 22 LTS from NodeSource.
NODE_MAJOR=22
if ! node --version 2>/dev/null | grep -q "^v${NODE_MAJOR}\."; then
    info "Installing Node.js ${NODE_MAJOR} LTS from NodeSource ..."
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
    apt-get install -y nodejs
    ok "Node.js $(node --version) installed."
else
    ok "Node.js $(node --version) already satisfies requirement (>= ${NODE_MAJOR})."
fi

# ---------------------------------------------------------------------------
# 2. Build the React frontend
# ---------------------------------------------------------------------------
info "Building React frontend ..."
cd "${REPO_DIR}/frontend"
sudo -u "${CURRENT_USER}" npm install --silent
sudo -u "${CURRENT_USER}" npm run build
ok "Frontend built → frontend/dist/"

# ---------------------------------------------------------------------------
# 3. Python virtual environment
# ---------------------------------------------------------------------------
VENV="${REPO_DIR}/.venv"
if [[ ! -d "${VENV}" ]]; then
    info "Creating Python virtual environment ..."
    sudo -u "${CURRENT_USER}" python3 -m venv "${VENV}"
fi

info "Installing Python dependencies ..."
sudo -u "${CURRENT_USER}" "${VENV}/bin/pip" install --quiet --upgrade pip
sudo -u "${CURRENT_USER}" "${VENV}/bin/pip" install --quiet -r "${REPO_DIR}/requirements.txt"
ok "Python environment ready at ${VENV}"

# ---------------------------------------------------------------------------
# 4. Systemd service
# ---------------------------------------------------------------------------
info "Installing jubilee-backend systemd service ..."
SERVICE_SRC="${DEPLOY_DIR}/jubilee-backend.service"
SERVICE_DST="/etc/systemd/system/jubilee-backend@.service"

# Symlink so pulling the repo updates the service definition automatically
ln -sf "${SERVICE_SRC}" "${SERVICE_DST}"
systemctl daemon-reload
systemctl enable --now "jubilee-backend@${CURRENT_USER}.service"
ok "jubilee-backend service enabled and started."

# ---------------------------------------------------------------------------
# 5. LXDE autostart (kiosk browser)
# ---------------------------------------------------------------------------
info "Configuring LXDE autostart ..."
AUTOSTART_DIR="${USER_HOME}/.config/lxsession/LXDE-pi"
AUTOSTART_FILE="${AUTOSTART_DIR}/autostart"
KIOSK_SCRIPT="${DEPLOY_DIR}/kiosk.sh"

mkdir -p "${AUTOSTART_DIR}"
chmod +x "${KIOSK_SCRIPT}"

# Write the autostart file with the correct path for this install
cat > "${AUTOSTART_FILE}" <<EOF
@xset s off
@xset -dpms
@xset s noblank
@${KIOSK_SCRIPT}
EOF

chown -R "${CURRENT_USER}:${CURRENT_USER}" "${AUTOSTART_DIR}"
ok "LXDE autostart configured → ${AUTOSTART_FILE}"

# ---------------------------------------------------------------------------
# 6. Auto-login (raspi-config non-interactive)
# ---------------------------------------------------------------------------
if command -v raspi-config &>/dev/null; then
    info "Enabling desktop auto-login for ${CURRENT_USER} ..."
    raspi-config nonint do_boot_behaviour B4   # Desktop auto-login
    ok "Auto-login enabled."
else
    info "raspi-config not found - skipping auto-login setup."
    info "Enable desktop auto-login manually in raspi-config > System Options > Boot."
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo
ok "Installation complete."
echo -e "  Backend service : ${BLUE}systemctl status jubilee-backend@${CURRENT_USER}${NC}"
echo -e "  View logs       : ${BLUE}journalctl -u jubilee-backend@${CURRENT_USER} -f${NC}"
echo -e "  Rebuild UI      : ${BLUE}cd ${REPO_DIR}/frontend && npm run build${NC}"
echo
info "Reboot to start in kiosk mode: sudo reboot"
