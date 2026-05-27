#!/usr/bin/env bash
# Kiosk launcher for the Jubilee Automation UI.
#
# Waits until the FastAPI backend is accepting connections on port 8000, then
# opens Chromium in full-screen kiosk mode.  Intended to be called from the
# LXDE autostart file (see deploy/autostart).

set -euo pipefail

TARGET_URL="http://localhost:8000"
TIMEOUT_SEC=60

# ---------------------------------------------------------------------------
# Display / screensaver settings
# ---------------------------------------------------------------------------
# Disable DPMS (Energy Star) power-saving and screen blanking so the display
# stays on while the machine is running.
xset s off
xset -dpms
xset s noblank

# Hide the mouse cursor after a brief period of inactivity (requires unclutter)
if command -v unclutter &>/dev/null; then
    unclutter -idle 5 -root &
fi

# ---------------------------------------------------------------------------
# Wait for the backend to be ready
# ---------------------------------------------------------------------------
echo "Waiting for backend on ${TARGET_URL} ..."
elapsed=0
until curl -sf "${TARGET_URL}/api/status" >/dev/null 2>&1; do
    sleep 1
    elapsed=$((elapsed + 1))
    if [[ $elapsed -ge $TIMEOUT_SEC ]]; then
        echo "Backend did not start within ${TIMEOUT_SEC}s — launching anyway."
        break
    fi
done
echo "Backend ready (${elapsed}s)."

# ---------------------------------------------------------------------------
# Launch Chromium in kiosk mode
# ---------------------------------------------------------------------------
chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-restore-session-state \
    --disable-session-crashed-bubble \
    --disable-features=TranslateUI \
    --check-for-update-interval=31536000 \
    "${TARGET_URL}"
