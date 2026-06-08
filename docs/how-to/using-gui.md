# Using the Jubilee Powder UI

This guide walks through using the Jubilee Powder web interface for powder dispensing
and hardness testing operations.

## Overview

The Jubilee Powder UI is a browser-based interface that provides:

- Hardware configuration and connection management
- Powder dispensing job setup and real-time monitoring
- Hardness testing job setup and monitoring
- Historical job log browsing

## Choose Your Depth

=== "Operator Workflow"

    Follow this page top-to-bottom for setup, job execution, monitoring, and troubleshooting.

=== "Developer Notes"

    - Backend API contract: [Web Frontend Reference](../api/gui/jubilee-gui.md)
    - Frontend state model: [Jubilee Store Reference](../api/gui/jubilee-view-model.md)
    - System design context: [Architecture](../concepts/architecture.md)

## Starting the UI

Use [Building and Running the Web UI](running.md) for the exact startup commands.

Quick summary:

- Dev mode: run backend (`uvicorn`) and frontend (`npm run dev`) in two terminals.
- Production mode: run backend only; it serves the built frontend.
- Mock hardware: set `server.mock_hardware: true` in `system_config.json`, or use `JUBILEE_MOCK_HARDWARE=1`.

---

## Interface Layout

Every screen shares the same persistent layout:

```
┌─────────────────────────────────────────────────────┐
│  NavRail  │   Screen content                        │
│           │                                         │
│  Home     │   (active screen fills this area)       │
│  Dispense │                                         │
│  Hardness │                                         │
│  Data     │                                         │
│  Manual   │                                         │
│  Settings │                                         │
├───────────┴─────────────────────────────────────────┤
│  BottomBar: weight  |  state badge  |  screen name  │
└─────────────────────────────────────────────────────┘
```

The **NavRail** on the left provides navigation between screens. The **BottomBar** at the
bottom always shows the live scale weight and machine connection state.

### Machine State Colors

| State          | Badge  | Meaning                          |
|----------------|--------|----------------------------------|
| Disconnected   | Gray   | No hardware connection           |
| Connecting...  | Yellow | Homing sequence in progress      |
| Connected      | Green  | Ready for a job                  |
| Running        | Yellow | Job executing                    |
| Error          | Red    | Failure — must reconnect         |

---

## Initial Setup

### 1. Configure Hardware

Open the **Settings** screen (bottom of the NavRail).

Enter your hardware configuration:

- **Number of Powder Dispensers** — how many piston dispenser trays are loaded
- **Pistons per Dispenser** — piston capacity of each tray (total is shown as a hint)
- **Jubilee IP Address or Hostname** — e.g. `jubilee.local` or `192.168.1.100`
- **Scale Serial Port** — e.g. `/dev/ttyUSB0` (Linux) or `COM3` (Windows)

!!! note
    Settings fields are locked while hardware is connected. Reconfiguration requires
    disconnecting first.

### 2. Connect

Click **Connect to Jubilee**.

The server returns immediately and begins the connection sequence in the background.
Watch the state badge in the BottomBar:

- `Connecting…` (yellow) — homing sequence running
- `Connected` (green) — ready for a job
- `Error` (red) — connection failed; check the IP address, serial port, and hardware power

Connection typically takes 30-60 seconds due to homing.

---

## Running a Powder Dispensing Job

Navigate to the **Dispensing** screen.

### Step 1: Select Wells

Click individual wells in the 4×6 grid to select them. Click again to deselect.

Toolbar shortcuts:

- **Select All** — select all 24 wells
- **Clear** — deselect everything

The selection count is shown in the toolbar.

### Step 2: Set Target Weights

Click **Set Weights** (only enabled when wells are selected).

Enter the target weight in grams. The same weight is applied to all currently selected
wells. Repeat the process with a different selection to assign different weights to
different wells.

Well colours in the grid reflect their state:

| Colour        | Meaning                          |
|---------------|----------------------------------|
| Dark (default)| Not selected                     |
| Highlighted   | Selected, no weight set          |
| With label    | Selected, target weight assigned |

### Step 3: Start Job

Click **Start Job** (enabled only when the machine is idle and all selected wells have
a target weight set).

The job is submitted to the server and begins immediately. The screen transitions to the
**Home** screen automatically — or you can navigate there to monitor progress.

!!! tip
    To assign different weights to different wells, select a subset, set the weight,
    then select a different subset and set a different weight before clicking Start Job.

---

## Running a Hardness Test

Navigate to the **Hardness** screen.

### Step 1: Select Samples

Click wells in the 4×6 grid to select the sample positions to test. Use **Select All**
or **Clear** in the toolbar as needed.

### Step 2: Assign Test Mode

With samples selected, click one of the mode buttons:

| Button  | Mode       | Description                       |
|---------|------------|-----------------------------------|
| Shore A | `shore_a`  | Standard Shore A hardness test    |
| A + D   | `shore_a_d`| Combined Shore A and D measurement|
| Shore D | `shore_d`  | Standard Shore D hardness test    |

Repeat to assign different modes to different samples.

### Step 3: Start Test

Click **Start Test**. Progress is monitored on the **Home** screen.

---

## Monitoring a Running Job

Navigate to the **Home** screen during a job.

### Display Layout

```
┌────────────────┬──────────────────────────────────┐
│  Arc progress  │  Well/sample result grid         │
│                │                                  │
│  Completed/    │  Color per cell:                 │
│  Total         │    Gray    = excluded            │
│  Elapsed time  │    Blue    = pending             │
│                │    Amber   = active (current)    │
│  [Cancel]      │    Green   = complete            │
│  [Abort]       │                                  │
└────────────────┴──────────────────────────────────┘
│  Status line                                      │
└───────────────────────────────────────────────────┘
```

### Stopping a Job

Two stop options are available while a job is running:

- **Cancel** — graceful stop. The machine finishes the current mold, stows the active
  tool, and returns to `idle`. Cancellation is applied only after the current mold
  or sample completes. A confirmation dialog is shown before proceeding.
- **Abort** — emergency stop. Sends an M112 signal to the controller. The machine halts
  immediately and enters `error` state. Use only when necessary; the machine must be
  fully reconnected before starting a new job.

!!! warning
    The Abort button requires two presses to confirm. On the first press the button
    highlights red and changes to "Press Again!". A second press within 3 seconds fires
    the emergency stop. If not confirmed within 3 seconds the button disarms itself.

---

## Browsing Historical Data

Navigate to the **Data** screen.

The file list shows all job log files in `frontend/api/files/`, sorted newest-first.
Each row shows the filename, size, and last-modified date.

Click any `.json` file to open a read-only job result view identical in layout to the
Home screen, showing the arc progress and per-well/sample result grid with outcome
colour coding.

Click **Back** in the header to return to the file list. The **Refresh** button reloads
the file list from the server.

---

## Settings Screen Reference

| Field                        | Default         | Description                             |
|------------------------------|-----------------|-----------------------------------------|
| Number of Powder Dispensers  | 2               | Number of piston dispenser trays        |
| Pistons per Dispenser        | 10              | Pistons per tray                        |
| Jubilee IP / Hostname        | `jubilee.local` | Machine network address                 |
| Scale Serial Port            | `/dev/ttyUSB0`  | Serial port for the A&D FX-120i scale   |

---

## Manual Control

!!! warning
    Manual control is for advanced users only. Using the Jubilee's built-in web interface
    (Duet Web Control) moves the hardware outside the positions tracked by the automation
    state machine. Recalibration is required before running automated jobs afterward.

Navigate to the **Manual** screen and click **Open Jubilee Web UI**. A confirmation
dialog explains the implications. On confirmation:

1. The automation system disconnects cleanly (state machine reset)
2. The Jubilee web UI opens in a new browser tab at `http://{jubilee_ip}`

After using manual control:

1. Return to **Settings**
2. Disconnect then reconnect
3. Verify hardware positions are correct before starting a new job

---

## Troubleshooting

### Connection fails immediately

- Verify the IP address or hostname in Settings
- Confirm the Jubilee is powered on and reachable (`ping jubilee.local`)
- Check the scale serial port is correct and the cable is connected
- Look at the server terminal output for more detail

### Machine stuck in `homing` state

The homing sequence runs until all axes are found. If it never transitions to `idle`:

- Check for physical obstructions on the axes
- Review the server logs for `JubileeManager.connect()` errors
- Disconnect and reconnect to retry

### Job fails to start

`Start Job` is disabled unless:

- Machine state is `idle`
- At least one well is selected
- All selected wells have a target weight set

If the button click produces an error message in the status line, it will show the
server's rejection reason (e.g. "Machine is not idle").

### Out of pistons

The server does not currently enforce piston count before job submission. If a
dispenser runs out of pistons mid-job, the job will fail at that well.

To update piston counts after a manual reload, use the REST endpoint directly:

```bash
curl -X PUT http://localhost:8000/api/dispensers/0 \
     -H "Content-Type: application/json" \
     -d '{"num_pistons": 10}'
```

### Scale shows `---` in BottomBar

Scale weight is only read when hardware is connected. Confirm the machine state is
`idle` or `running`. If connected but reading zero, check the serial connection.

### Browser tab shows stale data after server restart

The WebSocket reconnects automatically within 1.5 s of a server restart. If the screen
still looks stale after a few seconds, reload the browser tab.

---

## See Also

- [Web Frontend Reference](../api/gui/jubilee-gui.md) — REST API and architecture details
- [Jubilee Store Reference](../api/gui/jubilee-view-model.md) — ViewModel state and actions
- [Architecture](../concepts/architecture.md) — Full system architecture
- [Using the Jubilee Web UI](web-ui.md) — Duet Web Control guide
