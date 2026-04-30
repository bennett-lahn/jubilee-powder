# Jubilee Store Reference

`jubileeStore.js` is the [Zustand](https://docs.pmnd.rs/zustand/getting-started/introduction)
store that acts as the ViewModel layer in the React frontend. It is the single source of
truth for all shared application state and exposes actions that wrap REST API calls to the
FastAPI backend.

## Architecture Role

```
View      — React screens and components
    ↕  useJubileeStore(selector)
ViewModel — Zustand store (jubileeStore.js)
    ↕  fetch (REST)   ↕  WebSocket /ws (4 Hz)
Model     — FastAPI server + HardwareManager (Python)
```

The store is not a thin data cache. It also:

- Owns the single `WebSocket` instance and handles reconnect logic
- Normalises REST error responses into a consistent `{ ok, error? }` return shape
- Keeps UI-specific derived state (e.g. `levelCameraActive`, `wsConnected`)

## Usage

```js
import { useJubileeStore } from '../store/jubileeStore'

// Read individual slices with selectors to minimise re-renders
const telemetry = useJubileeStore((s) => s.telemetry)
const submitJob = useJubileeStore((s) => s.submitJob)
```

---

## State Shape

### `telemetry`

Live snapshot received from the WebSocket at 4 Hz. Replaced wholesale on every
frame so stale fields from a previous server restart are never retained.

```js
{
  weight:     null,          // float | null  — scale reading in grams
  state:      null,          // MachineState string | null
  connected:  false,         // true when state is idle, running, or homing
  jubilee_ip: 'jubilee.local',
  job:        null,          // JobProgress object | null
  dispensers: [],            // DispenserStatus[]
  clients:    null,          // number of connected browser tabs
}
```

### `hardwareStatus`

Last full machine snapshot from `GET /api/status`. `null` until the first successful
fetch. Refreshed on mount and after hardware lifecycle actions.

### `jobLog`

Normalised most-recent job log from `GET /api/job/log`. Uses the same shape as
`telemetry.job`. `null` when no job has run in the current server session and no
log files exist.

`HomeScreen` uses `jobLog` to display the last completed job when no job is
currently running.

### `levelCameraActive`

`true` when `POST /api/camera/start` has succeeded. Set back to `false` by
`stopLevelCamera()`.

### `wsConnected`

`true` when the WebSocket connection to `/ws` is open. Becomes `false` briefly
during reconnect.

### `statusError` / `jobLogError`

Error message strings from the most recent failed `loadStatus()` or `fetchJobLog()`
call respectively. `null` on success.

---

## Actions

All async actions return `{ ok: true }` on success or `{ ok: false, error: string }`
on failure. Components are expected to check `ok` and surface `error` to the user.

### WebSocket Lifecycle

#### `connectWs()`

Opens a single WebSocket to `/ws`. No-op if a connection is already open or
connecting. On close or error, schedules a reconnect after 1.5 s.

Called once in the `RootLayout` mount effect so all screens share the same
persistent connection.

#### `disconnectWs()`

Closes the WebSocket and cancels any pending reconnect timer. Called in the
`RootLayout` unmount cleanup.

### Status

#### `loadStatus()`

Fetches `GET /api/status` and stores the result in `hardwareStatus`.

```js
await store.loadStatus()
// store.hardwareStatus is now populated (or store.statusError is set)
```

### Hardware Lifecycle

#### `connectHardware(config)`

`POST /api/hardware/connect` — returns `{ ok, error? }`.

The server responds with HTTP 202 immediately; actual connection progress is
reflected in `telemetry.state`:

```
disconnected → homing → idle    (success)
disconnected → homing → error   (failure)
```

```js
const { ok, error } = await store.connectHardware({
  num_dispensers:        2,
  pistons_per_dispenser: 10,
  machine_address:       'jubilee.local',  // null to read from system_config.json
  scale_port:            '/dev/ttyUSB0',
})
```

#### `disconnectHardware()`

`POST /api/hardware/disconnect` — returns `{ ok, error? }`. Also stops any
running job server-side. Calls `loadStatus()` after a successful disconnect to
refresh the REST snapshot.

### Job Actions

#### `submitJob(jobType, items)`

`POST /api/job/start` — returns `{ ok, error? }`.

```js
// Powder dispensing
const { ok } = await store.submitJob('dispensing', [
  { well_id: '0', target_weight: 50.0 },
  { well_id: '3', target_weight: 45.0 },
])

// Hardness testing
const { ok } = await store.submitJob('hardness', [
  { sample_id: '0', mode: 'shore_a' },
  { sample_id: '1', mode: 'shore_d' },
])
```

The server validates the machine state (`idle`) and job constraints before
accepting. HTTP 422 is returned for invalid payloads (Pydantic validation).

#### `stopJob()`

`POST /api/job/stop` — returns `{ ok, error? }`. The machine finishes the current
well/sample then exits the job loop and returns to `idle`.

#### `cancelJob()`

`POST /api/job/cancel` — returns `{ ok, error? }`. Finish the current mold, stow
the active tool, return to `idle`. Functionally equivalent to `stopJob()` from the
server's perspective; the distinction is user-facing (cancel implies intentional
early termination).

#### `abortJob()`

`POST /api/job/abort` — returns `{ ok, error? }`. Emergency stop. Sends M112 to
the Duet controller (real hardware) and immediately sets machine state to `error`.
Hardware must be restarted and reconnected before starting a new job.

#### `fetchJobLog()`

`GET /api/job/log` — returns `{ ok, error? }`. Updates `jobLog` in the store.

### Level Camera

#### `startLevelCamera()`

`POST /api/camera/start` — returns `{ ok, error? }`. Sets `levelCameraActive: true`
on success. The MJPEG stream is then available at `GET /api/camera/stream`.

#### `stopLevelCamera()`

`POST /api/camera/stop` — returns `{ ok, error? }`. Sets `levelCameraActive: false`.

---

## Data Flow

### WebSocket Path (high-frequency, 4 Hz)

```
Server telemetry_loop()
    → ws.send_json(frame)
        → ws.onmessage in jubileeStore.connectWs()
            → set({ telemetry: { weight, state, connected, ... } })
                → All subscribed components re-render
```

### REST Path (on-demand)

Every action follows the same pattern:

```js
async actionName(args) {
  try {
    const data = await apiFunction(args)
    // optionally update store state
    return { ok: true }
  } catch (err) {
    return { ok: false, error: err.message }
  }
}
```

Errors from the server's `detail` field are automatically extracted by the
`request()` helper in `jubileeApi.js` and surfaced as the `err.message`.

### WebSocket Reconnect

```
ws.onclose / ws.onerror
    → set({ wsConnected: false })
    → setTimeout(connectWs, 1500)
```

---

## `jubileeApi.js`

Thin HTTP wrapper consumed by the store. All functions return the parsed JSON body
on success and throw an `Error` with the server's `detail` string on non-2xx
responses. The Vite dev-server proxy forwards `/api/*` to `http://localhost:8000`,
so the same `BASE = '/api'` URL works identically in development and production.

Key exported functions:

| Function              | Method | Path                       |
|-----------------------|--------|----------------------------|
| `fetchStatus()`       | GET    | `/api/status`              |
| `connectHardware(c)`  | POST   | `/api/hardware/connect`    |
| `disconnectHardware()`| POST   | `/api/hardware/disconnect` |
| `startJob(body)`      | POST   | `/api/job/start`           |
| `stopJob()`           | POST   | `/api/job/stop`            |
| `cancelJob()`         | POST   | `/api/job/cancel`          |
| `abortJob()`          | POST   | `/api/job/abort`           |
| `fetchJobLog()`       | GET    | `/api/job/log`             |
| `fetchDispensers()`   | GET    | `/api/dispensers`          |
| `updateDispenser(i,n)`| PUT    | `/api/dispensers/{index}`  |
| `startLevelCamera()`  | POST   | `/api/camera/start`        |
| `stopLevelCamera()`   | POST   | `/api/camera/stop`         |

---

## See Also

- [Web Frontend Reference](jubilee-gui.md) — FastAPI server, REST API, and React screens
- [Using the Automation UI](../../how-to/using-gui.md) — User guide
- [Architecture](../../concepts/architecture.md) — System architecture overview
