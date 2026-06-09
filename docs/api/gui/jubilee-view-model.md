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
- Keeps UI-specific derived state (e.g. `wsConnected`)

!!! tip "Minimise re-renders"
    Subscribe to individual slices with selectors (`useJubileeStore((s) => s.telemetry)`) rather than destructuring the whole store in every component.

## Quick Start

```js
import { useJubileeStore } from '../store/jubileeStore'

const telemetry = useJubileeStore((s) => s.telemetry)
const submitJob = useJubileeStore((s) => s.submitJob)
```

---

=== "State Reference"

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

    ### `wsConnected`

    `true` when the WebSocket connection to `/ws` is open. Becomes `false` briefly
    during reconnect.

    ### `statusError` / `jobLogError`

    Error message strings from the most recent failed `loadStatus()` or `fetchJobLog()`
    call respectively. `null` on success.

=== "Actions Reference"

    ## Actions

    All async actions return `{ ok: true }` on success or `{ ok: false, error: string }`
    on failure. Components are expected to check `ok` and surface `error` to the user.

    ### WebSocket Lifecycle

    | Action | Description |
    |--------|-------------|
    | `connectWs()` | Opens `/ws`; reconnects after 1.5 s on close. Called once from `RootLayout`. |
    | `disconnectWs()` | Closes the socket and cancels pending reconnect. Called on unmount. |

    ### Status

    #### `loadStatus()`

    Fetches `GET /api/status` into `hardwareStatus`.

    ```js
    await store.loadStatus()
    ```

    ### Hardware Lifecycle

    #### `connectHardware(config)`

    `POST /api/hardware/connect` — returns `{ ok, error? }`. Connection progress appears
    in `telemetry.state`:

    ```
    disconnected → homing → idle    (success)
    disconnected → homing → error   (failure)
    ```

    ```js
    const { ok, error } = await store.connectHardware({
      num_dispensers:        2,
      pistons_per_dispenser: 10,
      machine_address:       'jubilee.local',  // null reads from system_config.json
      scale_port:            '/dev/ttyUSB0',
    })
    ```

    #### `disconnectHardware()`

    `POST /api/hardware/disconnect` — stops any running job and refreshes `hardwareStatus`.

    ### Job Actions

    === "Dispensing"
        ```js
        const { ok } = await store.submitJob('dispensing', [
          { well_id: '0', target_weight: 50.0 },
          { well_id: '3', target_weight: 45.0 },
        ])
        ```

    === "Hardness"
        ```js
        const { ok } = await store.submitJob('hardness', [
          { tray_index: 0, sample_index: 0, mode: 'shore_a' },
          { tray_index: 0, sample_index: 1, mode: 'shore_d' },
        ])
        ```

    Valid hardness modes: `shore_a`, `shore_a_d`, `shore_d`.

    | Action | Endpoint | Behaviour |
    |--------|----------|-----------|
    | `stopJob()` | `POST /api/job/stop` | Finish current well/sample, return to `idle` |
    | `cancelJob()` | `POST /api/job/cancel` | Same server semantics as stop; user-facing "cancel" |
    | `abortJob()` | `POST /api/job/abort` | Emergency M112; machine enters `error` |
    | `fetchJobLog()` | `GET /api/job/log` | Updates `jobLog` |

    The server validates machine state (`idle`) before accepting jobs. Invalid payloads
    return HTTP 422 (Pydantic validation).

---

## Data Flow

=== "WebSocket (4 Hz)"
    ```
    Server telemetry_loop()
        → ws.send_json(frame)
            → ws.onmessage in jubileeStore.connectWs()
                → set({ telemetry: { weight, state, connected, ... } })
                    → All subscribed components re-render
    ```

=== "REST (on demand)"
    Every action follows the same pattern:

    ```js
    async actionName(args) {
      try {
        const data = await apiFunction(args)
        return { ok: true }
      } catch (err) {
        return { ok: false, error: err.message }
      }
    }
    ```

    Errors from the server's `detail` field are extracted by the `request()` helper
    in `jubileeApi.js` and surfaced as `err.message`.

??? note "WebSocket reconnect"
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

| Function               | Method | Path                       |
|------------------------|--------|----------------------------|
| `fetchStatus()`        | GET    | `/api/status`              |
| `connectHardware(c)`   | POST   | `/api/hardware/connect`    |
| `disconnectHardware()` | POST   | `/api/hardware/disconnect` |
| `startJob(body)`       | POST   | `/api/job/start`           |
| `stopJob()`            | POST   | `/api/job/stop`            |
| `cancelJob()`          | POST   | `/api/job/cancel`          |
| `abortJob()`           | POST   | `/api/job/abort`           |
| `fetchJobLog()`        | GET    | `/api/job/log`             |
| `fetchDispensers()`    | GET    | `/api/dispensers`          |
| `updateDispenser(i,n)` | PUT    | `/api/dispensers/{index}`  |

---

## See Also

- [Web Frontend Reference](jubilee-gui.md) - FastAPI server, REST API, and React screens
- [Using the Automation UI](../../how-to/using-gui.md) - User guide
- [Architecture](../../concepts/architecture.md) - System architecture overview
