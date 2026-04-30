# Web Frontend Reference

The Jubilee Automation web frontend is a browser-based interface for powder dispensing and
hardness testing operations. It replaces the former Kivy GUI with a React single-page
application backed by a FastAPI server.

## Overview

The frontend provides:

- Six navigation screens covering home/dashboard, dispensing, hardness testing, data
  browser, manual control, and settings
- A 4 Hz WebSocket telemetry feed keeping every screen up to date without polling
- REST API endpoints for discrete commands (connect, start job, stop, abort)
- A mock hardware mode (`MOCK_HARDWARE = True`) for UI development without physical hardware

## Technology Stack

| Layer    | Technology                        |
|----------|-----------------------------------|
| Frontend | React 19, Vite 8, Tailwind CSS 4  |
| State    | Zustand 5                         |
| Routing  | React Router v7                   |
| Backend  | FastAPI (Python 3.12+), uvicorn   |
| Transport | REST HTTP + WebSocket            |
| Storage  | JSON job log files                |

## Architecture

The frontend follows an MVVM pattern split across the browser and server:

```
┌──────────────────────────────────────────────────┐
│  Browser                                         │
│                                                  │
│  View      ── React screens + components         │
│  ViewModel ── Zustand store (jubileeStore.js)    │
│                 │ REST (HTTP)    │ WebSocket /ws  │
└──────────────────────────────────────────────────┘
                  │                │
┌──────────────────────────────────────────────────┐
│  FastAPI Server (server.py)                      │
│  Model     ── HardwareManager / MockHardwareManager│
│                 │                                │
│  JubileeManager ─── Scale, Dispensers, Jubilee   │
└──────────────────────────────────────────────────┘
```

| MVVM Layer | Component                        | Responsibility                        |
|------------|----------------------------------|---------------------------------------|
| View       | React screens and components     | Render state, capture user input      |
| ViewModel  | Zustand store (`jubileeStore.js`)| Derived state, REST/WebSocket actions |
| Model      | FastAPI + `HardwareManager`      | Hardware state, physical operations   |

## Starting the Server

From the `frontend/` directory:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

From the project root:

```bash
uvicorn frontend.server:app --host 0.0.0.0 --port 8000 --reload
```

During development, also start the Vite dev server in a second terminal:

```bash
cd frontend
npm install   # first time only
npm run dev
```

Then navigate to `http://localhost:5173`. The Vite dev server proxies all `/api/*`
requests to the FastAPI server on port 8000.

## Mock vs Real Hardware

Set `MOCK_HARDWARE` at the top of `server.py`:

```python
MOCK_HARDWARE: bool = True   # UI development — no physical hardware needed
MOCK_HARDWARE: bool = False  # Production — real Jubilee machine + scale
```

`MockHardwareManager` and `HardwareManager` expose an identical public API so no
other code needs to change when switching modes. The mock simulates realistic weight
readings (sine-wave drift + Gaussian noise) and job timing (`asyncio.sleep()`).

---

## REST API Reference

All endpoints are prefixed with `/api`.

### Status

| Method | Path          | Description                |
|--------|---------------|----------------------------|
| `GET`  | `/api/status` | Full machine state snapshot |

**Response:**

```json
{
  "connected":   true,
  "state":       "idle",
  "jubilee_ip":  "jubilee.local",
  "job":         { ... },
  "dispensers":  [ { "index": 0, "pistons_remaining": 8 } ],
  "clients":     1
}
```

### Hardware Lifecycle

| Method | Path                       | Status | Description                               |
|--------|----------------------------|--------|-------------------------------------------|
| `POST` | `/api/hardware/connect`    | 202    | Begin hardware connection asynchronously  |
| `POST` | `/api/hardware/disconnect` | 200    | Stop any running job and disconnect       |

**`POST /api/hardware/connect` request body:**

```json
{
  "num_dispensers":        2,
  "pistons_per_dispenser": 10,
  "machine_address":       "jubilee.local",
  "scale_port":            "/dev/ttyUSB0"
}
```

The server returns HTTP 202 immediately. Monitor the WebSocket `state` field for
connection progress:

```
DISCONNECTED → HOMING → IDLE    (success)
DISCONNECTED → HOMING → ERROR   (failure — inspect job.error for reason)
```

### Jobs

| Method | Path              | Status | Description                                   |
|--------|-------------------|--------|-----------------------------------------------|
| `POST` | `/api/job/start`  | 202    | Enqueue a dispensing or hardness job          |
| `POST` | `/api/job/stop`   | 200    | Graceful stop after the current well/sample   |
| `POST` | `/api/job/cancel` | 200    | Finish current mold then stow the tool        |
| `POST` | `/api/job/abort`  | 200    | Emergency stop (M112), enters ERROR state     |
| `GET`  | `/api/job/log`    | 200    | Most recent job log (in-memory or from file)  |

**`POST /api/job/start` — dispensing job:**

```json
{
  "job_type": "dispensing",
  "wells": [
    { "well_id": "0", "target_weight": 50.0 },
    { "well_id": "3", "target_weight": 45.0 }
  ]
}
```

**`POST /api/job/start` — hardness job:**

```json
{
  "job_type": "hardness",
  "samples": [
    { "sample_id": "0", "mode": "shore_a" },
    { "sample_id": "1", "mode": "shore_d" }
  ]
}
```

Valid hardness modes: `shore_a`, `shore_a_d`, `shore_d`.

The server returns HTTP 202; track progress via the WebSocket `job` field.

**Stop vs Cancel vs Abort:**

| Action | Behaviour |
|--------|-----------|
| `stop`   | Signal job to exit at the next well boundary. Machine stays at current well, returns to IDLE. |
| `cancel` | Finish the current mold, then stow the active tool and return to IDLE. |
| `abort`  | Immediate M112 emergency stop. Machine enters ERROR state and must be reconnected before a new job. |

### Dispensers

| Method | Path                       | Description                              |
|--------|----------------------------|------------------------------------------|
| `GET`  | `/api/dispensers`          | List all dispenser statuses              |
| `PUT`  | `/api/dispensers/{index}`  | Update remaining piston count            |

`PUT` body: `{ "num_pistons": 10 }`

### Job Log Files

| Method | Path                    | Description                              |
|--------|-------------------------|------------------------------------------|
| `GET`  | `/api/files`            | List all job log files (newest-first)    |
| `GET`  | `/api/files/{filename}` | Return full JSON content of one log file |

File names follow the pattern `{id}_{date}_{job_type}_{n}.json`,
e.g. `0012_2026-04-12_dispensing_1.json`. Files are stored in
`frontend/api/files/`.

---

## WebSocket Protocol

### Endpoint

```
ws://<host>/ws
```

### Telemetry Frame (4 Hz)

The server pushes a JSON frame to every connected browser four times per second. Each
frame is a complete snapshot — the client replaces its state wholesale so no stale
fields from a previous server restart are retained.

```json
{
  "weight":     50.123,
  "state":      "idle",
  "connected":  true,
  "jubilee_ip": "jubilee.local",
  "job": {
    "running":      false,
    "job_type":     "dispensing",
    "completed":    6,
    "total":        6,
    "current_item": null,
    "error":        null,
    "started_at":   "2026-04-16T14:30:00Z",
    "items":        [ ... ]
  },
  "dispensers": [
    { "index": 0, "pistons_remaining": 4 },
    { "index": 1, "pistons_remaining": 10 }
  ],
  "clients": 1
}
```

`weight` is `null` when hardware is disconnected. The frame is only sent when at
least one browser is connected; the server skips the broadcast when `clients == 0`.

### Machine States

| State          | Meaning                                                     |
|----------------|-------------------------------------------------------------|
| `disconnected` | No hardware connection                                      |
| `homing`       | Connection sequence or homing in progress                   |
| `idle`         | Connected and ready for a job                               |
| `running`      | Job is executing                                            |
| `error`        | Emergency stop or failure — reconnect required              |

---

## Backend Module Reference

### `server.py`

FastAPI application entry point. Responsible for:

- Defining all REST and WebSocket endpoints
- Running the 4 Hz `telemetry_loop` background task
- Instantiating `HardwareManager` (or `MockHardwareManager`), `ConnectionManager`,
  and `JobProgress` as module-level singletons
- Writing and reading job log files in `frontend/api/files/`

### `hardware_manager.py`

Provides two classes with identical public APIs, selected by `MOCK_HARDWARE`:

- **`MockHardwareManager`** — standalone simulation; scale readings use a sine-wave
  drift plus Gaussian noise to mimic the A&D FX-120i; job execution advances
  `JobProgress` via `asyncio.sleep()` for realistic per-well timing.
- **`HardwareManager`** — production wrapper around `JubileeManager`; all blocking
  serial/network calls are offloaded to `asyncio.to_thread()` so the uvicorn event
  loop is never stalled; `JubileeManager` is imported lazily inside `connect()` so
  the server starts cleanly on machines without `science_jubilee`.

### `models.py`

Shared Pydantic models and enums imported by both `server.py` and
`hardware_manager.py`:

- **`MachineState`** — string enum for the five hardware states
- **`HardwareConfig`** — settings posted by the Settings screen on connect
- **`DispenserStatus`** — per-dispenser index and remaining piston count
- **`JobProgress`** — mutable in-memory job state threaded through server endpoints
  and hardware managers

---

## React Application

### Screens

| Route         | Component                 | Description                                       |
|---------------|---------------------------|---------------------------------------------------|
| `/`           | `HomeScreen`              | Live job dashboard; shows running or last job     |
| `/dispensing` | `PowderDispensingScreen`  | Well selection, target weights, job submission    |
| `/hardness`   | `HardnessTestingScreen`   | Sample selection, test mode assignment, job start |
| `/data`       | `DataScreen`              | Browse and inspect historical job log files       |
| `/manual`     | `ManualControlScreen`     | Gateway to the Jubilee machine web UI (DWC)       |
| `/settings`   | `SettingsScreen`          | Hardware configuration and connect/disconnect     |

### Persistent Layout

Every route is wrapped in `RootLayout`, which renders:

- **`NavRail`** — left-side vertical navigation, always visible
- **`BottomBar`** — live weight display, machine state badge, and active tab label;
  reads directly from the Zustand store
- The active screen fills the remaining area

On mount, `RootLayout` calls `connectWs()` and `loadStatus()` so all screens have
live telemetry and an initial REST snapshot from the first render.

### Key Components

| Component     | Purpose                                                        |
|---------------|----------------------------------------------------------------|
| `WellGrid`    | Interactive 4×6 grid; variants: `dispensing`, `hardness`, `result` |
| `ArcProgress` | Circular arc showing completion percentage, count, elapsed time |
| `NavRail`     | Navigation bar with route links and connection status          |
| `BottomBar`   | Persistent status strip with live weight and machine state     |

### `useWellGrid` Hook

`WellGrid.jsx` exports a `useWellGrid(rows, cols)` hook used by the dispensing and
hardness screens to manage per-well state locally before submitting a job:

```js
const grid = useWellGrid(4, 6)

grid.wells          // { [id]: { selected, targetWeight, mode, status, ... } }
grid.selectedIds    // string[]
grid.toggleWell(id) // toggle selection of one well
grid.selectAll()    // select all wells
grid.clearSelection()
grid.setWeightForSelected(weight)
grid.setModeForSelected(mode)
```

---

## See Also

- [Jubilee Store](jubilee-view-model.md) — Zustand ViewModel reference
- [Using the Automation UI](../../how-to/using-gui.md) — User guide
- [Architecture](../../concepts/architecture.md) — System architecture overview
- [JubileeManager](../jubilee-manager.md) — Hardware coordination layer
