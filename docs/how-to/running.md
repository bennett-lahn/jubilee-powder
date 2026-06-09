# Building and Running the Web UI

The web UI has two operating modes. Use dev mode when actively changing frontend code; use production mode for normal lab operation and for the Raspberry Pi kiosk.

=== "Development"

    Vite dev server + uvicorn (two processes). Hot reload for frontend changes.

    **Open:** `http://localhost:5173` (Vite proxies `/api` and `/ws` to port 8000)

=== "Production"

    Single uvicorn process serves both the REST/WebSocket API and the built React app.

    **Open:** `http://localhost:8000`

!!! info "Prerequisites"
    - Python virtual environment with `requirements.txt` installed
    - Node.js 20.19+ or 22.12+ for frontend builds and dev server
    - `jubilee_api_config/` configured for your machine

---

## Development mode

Requires two terminals running simultaneously from the project root.

**Terminal 1 - backend:**
```bash
uvicorn frontend.server:app --host 0.0.0.0 --port 8000 --reload
```

To run without physical hardware, either set `"mock_hardware": true` under `server` in `jubilee_api_config/system_config.json`, or start the backend with:

```bash
JUBILEE_MOCK_HARDWARE=1 uvicorn frontend.server:app --host 0.0.0.0 --port 8000 --reload
```

When the env var is set, it overrides the JSON value. `GET /api/config` reports the effective mode in `mock_hardware`.

**Terminal 2 - frontend dev server:**
```bash
cd frontend
npm install   # only needed the first time
npm run dev
```

!!! note "Node.js version"
    Vite 8 requires **Node.js 20.19+ or 22.12+**. The version that ships with Raspberry Pi OS via `apt` (Node 18) is too old. `deploy/install.sh` handles this automatically by pulling Node 22 LTS from NodeSource. For local development on other machines, check your version with `node --version` and upgrade if needed.

!!! warning "WSL: use Linux Node and npm"
    If `which npm` points at `/mnt/c/Program Files/nodejs/npm`, or `npm run dev` fails with **Cannot find native binding** / `@rolldown/binding-linux-x64-gnu`, dependencies were installed for the wrong OS. Install Node 22 inside WSL (for example [fnm](https://github.com/Schniz/fnm)), ensure `node -v` is 22+ and `which npm` is under your Linux home (not `/mnt/c`), then reinstall:

    ```bash
    cd frontend
    rm -rf node_modules package-lock.json
    npm install
    ```

Open `http://localhost:5173` in your browser. The Vite dev server proxies `/api` and `/ws` requests to the uvicorn backend on port 8000, so both processes must be running at the same time. Hot-module replacement means frontend changes are reflected in the browser immediately without restarting anything.

---

## Production mode

In production a single uvicorn process serves both the REST/WebSocket API and the compiled React app. There is no Vite dev server.

### Step 1 - build the frontend

Run once (and again after any frontend code change):

```bash
cd frontend
npm install   # only needed the first time or after package.json changes
npm run build
```

This writes static files to `frontend/dist/`. The backend detects that directory on startup and begins serving it automatically.

### Step 2 - start the backend

```bash
uvicorn frontend.server:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. Both the UI and the API are served from the same port. If `frontend/dist/` does not exist the server still starts, but navigating to the root returns a 404 until you run `npm run build`.

!!! note "No --reload in production"
    Omit `--reload` in production. It watches the filesystem and adds unnecessary overhead.

---

## Raspberry Pi kiosk (auto-launch)

The `deploy/` directory contains everything needed to run the system as a polished auto-launching kiosk on Raspberry Pi OS (Bullseye / X11).

### One-time install

```bash
cd ~/jubilee-powder
sudo bash deploy/install.sh
sudo reboot
```

`install.sh` does the following in order:

1. Installs system packages (`chromium-browser`, `unclutter`, Node.js, Python venv tools)
2. Builds the React frontend (`npm run build`)
3. Creates `.venv/` and installs all Python dependencies
4. Installs and enables the `jubilee-backend` systemd service (auto-restarts on failure)
5. Writes an LXDE autostart config that opens Chromium in kiosk mode after login
6. Enables desktop auto-login via `raspi-config`

After the reboot the Pi follows this sequence automatically:

- Desktop auto-login fires
- systemd starts `jubilee-backend` (uvicorn on port 8000), waits for the network
- LXDE autostart runs `deploy/kiosk.sh`, which polls `GET /api/status` until the backend is ready, then opens Chromium full-screen on `http://localhost:8000`

The result is a touch-friendly full-screen UI with no visible desktop, browser chrome, or terminal.

### Updating after a git pull

Run this script after every `git pull` on the Pi - it rebuilds the frontend, updates Python dependencies, and restarts the backend service:

```bash
cd ~/jubilee-powder
sudo bash deploy/update.sh
```

If you only changed Python files and want to skip the frontend rebuild, you can restart the service directly:

```bash
sudo systemctl restart jubilee-backend@pi
```

If you only changed frontend files and want to skip the service restart, rebuild without sudo:

```bash
cd ~/jubilee-powder/frontend
npm run build
```

uvicorn serves files directly from `frontend/dist/` so the next browser refresh picks up the new build without a restart.

### Managing the backend service

```bash
# Check service health
systemctl status jubilee-backend@pi

# Follow live logs
journalctl -u jubilee-backend@pi -f

# Restart (e.g. after a Python code change)
sudo systemctl restart jubilee-backend@pi
```

Replace `pi` with your username if the account name differs.

---

## Manual launch and troubleshooting (Pi)

If the automatic kiosk does not come up after reboot, diagnose and recover one layer at a time.

### 1. Check and start the backend manually

```bash
# See why the service failed
systemctl status jubilee-backend@pi
journalctl -u jubilee-backend@pi -n 50

# If it is stopped, start it
sudo systemctl start jubilee-backend@pi

# Or bypass systemd entirely and run uvicorn directly
cd ~/jubilee-powder
.venv/bin/uvicorn frontend.server:app --host 0.0.0.0 --port 8000
```

Confirm the backend is up before doing anything else:

```bash
curl http://localhost:8000/api/status
```

A JSON response means the backend is healthy. A "connection refused" error means uvicorn is not running.

### 2. Open the browser manually

Once the backend is running, open a terminal on the Pi desktop and run:

```bash
chromium-browser http://localhost:8000
```

To test full kiosk mode manually (exits with Alt+F4 or closing the window is blocked - use Ctrl+Alt+T to open a terminal):

```bash
chromium-browser --kiosk http://localhost:8000
```

### 3. Re-run the kiosk script manually

`deploy/kiosk.sh` is the same script that autostart calls. Running it from a terminal on the desktop reproduces exactly what autostart would do:

```bash
bash ~/jubilee-powder/deploy/kiosk.sh
```

It will print "Waiting for backend..." and then open Chromium once the backend responds.

### 4. Check the autostart configuration

If the backend works fine but Chromium never opens automatically at login:

```bash
# Verify the autostart file exists and has the right content
cat ~/.config/lxsession/LXDE-pi/autostart

# Re-run install.sh to regenerate it
cd ~/jubilee-powder
sudo bash deploy/install.sh
```

The autostart file should contain a line like `@/home/pi/jubilee-powder/deploy/kiosk.sh`. If the path does not match where the repo was cloned, edit the line to match.

### 5. Check that the frontend was built

If the backend starts but navigating to `http://localhost:8000` returns a 404:

```bash
ls ~/jubilee-powder/frontend/dist/
```

If the directory is missing or empty, the build was never run. Build it now:

```bash
cd ~/jubilee-powder/frontend
npm run build
```

No backend restart is needed - uvicorn picks up the new `dist/` on the next request.

---

## Quick reference

| Task | Command |
|------|---------|
| Start dev backend | `uvicorn frontend.server:app --port 8000 --reload` |
| Start dev frontend | `cd frontend && npm run dev` |
| Build for production | `cd frontend && npm run build` |
| Start production server | `uvicorn frontend.server:app --host 0.0.0.0 --port 8000` |
| First-time Pi install | `sudo bash deploy/install.sh` |
| Update after git pull (Pi) | `sudo bash deploy/update.sh` |
| Rebuild UI on Pi | `cd frontend && npm run build` |
| View backend logs (Pi) | `journalctl -u jubilee-backend@pi -f` |
| Restart backend (Pi) | `sudo systemctl restart jubilee-backend@pi` |

## See Also

- [Using the Jubilee Powder UI](using-gui.md)
- [Configuration Guide](configuration.md)
- [Best Practices](../concepts/best-practices.md)
