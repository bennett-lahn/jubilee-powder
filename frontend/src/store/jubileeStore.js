/**
 * Zustand store — single source of truth for the Jubilee UI.
 *
 * Architecture role (MVVM)
 * ------------------------
 *   Model      — FastAPI server + HardwareManager (Python, backend)
 *   ViewModel  — this store  (holds derived state, exposes actions)
 *   View       — React components (read from store, call actions)
 *
 * Data flow
 * ---------
 *   WebSocket frames (4 Hz) → telemetry slice  (live, high-frequency)
 *   REST responses          → hardwareStatus   (on-demand snapshots)
 *
 * WebSocket lifecycle
 * -------------------
 * A single WebSocket connection is opened by connectWs() and kept alive with
 * auto-reconnect.  Only one connection is ever open; all components read the
 * shared telemetry state from the store rather than opening their own sockets.
 *
 * Sections
 *   telemetry      — live frames from the server WebSocket at 4 Hz
 *                    { weight, state, connected, jubilee_ip, job, dispensers, clients }
 *   hardwareStatus — last REST snapshot from GET /api/status
 *   ws             — WebSocket lifecycle (connect / disconnect / auto-reconnect)
 *   hardware       — connectHardware / disconnectHardware actions
 *   job            — submitJob / stopJob actions
 *   dispensers     — updateDispenser action
 */

import { create } from 'zustand'
import {
  DISPENSING_LAYOUT,
  DISPENSING_ROWS,
  DISPENSING_COLS,
  DISPENSING_WELL_COUNT,
} from '../constants/dispensingBed'
import {
  fetchStatus,
  connectHardware as apiConnectHardware,
  disconnectHardware as apiDisconnectHardware,
  startJob,
  stopJob as apiStopJob,
  cancelJob as apiCancelJob,
  abortJob as apiAbortJob,
  clearJam as apiClearJam,
  fetchJobLog as apiFetchJobLog,
  updateDispenser as apiUpdateDispenser,
  fetchDriveStatus as apiFetchDriveStatus,
} from '../api/jubileeApi'

function wsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}/ws`
}

const RECONNECT_DELAY_MS = 1500

const HARDNESS_ROWS = 5
const HARDNESS_COLS = 7
const HARDNESS_TRAY_COUNT = 2

function initDispensingWells() {
  const wells = {}
  for (let i = 0; i < DISPENSING_WELL_COUNT; i++) {
    wells[String(i)] = {
      selected: false,
      targetWeight: 0,
      currentWeight: 0,
      mode: 'none',
    }
  }
  return wells
}

function hardnessSampleKey(trayIndex, sampleId) {
  return `${trayIndex}:${sampleId}`
}

function initHardnessSamples(rows, cols, trayCount) {
  const samples = {}
  const trayCapacity = rows * cols
  for (let trayIndex = 0; trayIndex < trayCount; trayIndex++) {
    for (let sampleIndex = 0; sampleIndex < trayCapacity; sampleIndex++) {
      samples[hardnessSampleKey(trayIndex, sampleIndex)] = {
        selected: false,
        mode: 'none',
      }
    }
  }
  return samples
}

export const useJubileeStore = create((set, get) => ({

  // -------------------------------------------------------------------------
  // Telemetry  (replaced wholesale on every WebSocket frame)
  // -------------------------------------------------------------------------
  telemetry: {
    weight:     null,   // float | null  — live scale reading in grams
    state:      null,   // MachineState string | null
    connected:  false,  // bool — hw.connected (IDLE, RUNNING, HOMING are all "connected")
    jubilee_ip: 'jubilee.local',
    job:        null,   // job-progress object | null
    dispensers: [],     // DispenserStatus[] — updated alongside job progress
    clients:    null,   // number of connected browser tabs
  },

  // -------------------------------------------------------------------------
  // Hardware status  (REST snapshot — refreshed on mount and after actions)
  // -------------------------------------------------------------------------
  hardwareStatus: null,
  statusError:    null,

  // -------------------------------------------------------------------------
  // Job log  (most recent completed or in-progress job, populated via REST)
  // -------------------------------------------------------------------------
  jobLog:     null,
  jobLogError: null,

  // -------------------------------------------------------------------------
  // UI prep state (persists across route navigation)
  // -------------------------------------------------------------------------
  dispensingGrid: {
    rows: DISPENSING_ROWS,
    cols: DISPENSING_COLS,
    wells: initDispensingWells(),
  },

  hardnessGrid: {
    rows: HARDNESS_ROWS,
    cols: HARDNESS_COLS,
    trayCount: HARDNESS_TRAY_COUNT,
    samples: initHardnessSamples(HARDNESS_ROWS, HARDNESS_COLS, HARDNESS_TRAY_COUNT),
  },

  // -------------------------------------------------------------------------
  // Error dialog  (shown whenever telemetry.state transitions into 'error')
  // -------------------------------------------------------------------------
  errorDialog: { open: false, message: null },

  dismissErrorDialog() {
    set({ errorDialog: { open: false, message: null } })
  },

  // -------------------------------------------------------------------------
  // WebSocket connection state
  // -------------------------------------------------------------------------
  wsConnected:          false,
  _ws:                  null,
  _reconnectTimer:      null,
  _prevTelemetryState:  null,

  // -------------------------------------------------------------------------
  // WebSocket lifecycle
  // -------------------------------------------------------------------------

  connectWs() {
    const { _ws } = get()
    if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    const ws = new WebSocket(wsUrl())

    ws.onopen = () => {
      set({ wsConnected: true, _ws: ws })
      const { _reconnectTimer } = get()
      if (_reconnectTimer) {
        clearTimeout(_reconnectTimer)
        set({ _reconnectTimer: null })
      }
    }

    ws.onmessage = (e) => {
      try {
        // Each frame is the full telemetry snapshot — replace entirely so stale
        // fields from a previous server restart are never retained.
        const { weight, state, connected, jubilee_ip, job, dispensers, clients } =
          JSON.parse(e.data)

        // Detect a transition INTO the error state and surface a popup once.
        const prevState = get()._prevTelemetryState
        if (state === 'error' && prevState !== 'error') {
          const message = job?.error ?? 'An unexpected error occurred.'
          set({ errorDialog: { open: true, message } })
        }

        set({
          telemetry: {
            weight,
            state,
            connected:  connected  ?? false,
            jubilee_ip: jubilee_ip ?? 'jubilee.local',
            job,
            dispensers: dispensers ?? [],
            clients,
          },
          _prevTelemetryState: state,
        })
      } catch {
        // ignore malformed frames
      }
    }

    ws.onclose = () => {
      set({ wsConnected: false, _ws: null })
      const timer = setTimeout(() => get().connectWs(), RECONNECT_DELAY_MS)
      set({ _reconnectTimer: timer })
    }

    ws.onerror = () => ws.close()

    set({ _ws: ws })
  },

  disconnectWs() {
    const { _ws, _reconnectTimer } = get()
    if (_reconnectTimer) clearTimeout(_reconnectTimer)
    if (_ws) _ws.close()
    set({ _ws: null, wsConnected: false, _reconnectTimer: null })
  },

  // -------------------------------------------------------------------------
  // REST — status snapshot
  // -------------------------------------------------------------------------

  async loadStatus() {
    try {
      const data = await fetchStatus()
      set({ hardwareStatus: data, statusError: null })
    } catch (err) {
      set({ statusError: err.message })
    }
  },

  // -------------------------------------------------------------------------
  // Hardware lifecycle actions
  //
  // Connection progress is visible via telemetry.state transitions:
  //   DISCONNECTED → HOMING → IDLE   (success)
  //   DISCONNECTED → HOMING → ERROR  (failure)
  // -------------------------------------------------------------------------

  /**
   * POST /api/hardware/connect
   *
   * @param {{ num_dispensers: number, pistons_per_dispenser: number,
   *           machine_address?: string, scale_port?: string }} config
   * @returns {{ ok: boolean, error?: string }}
   */
  async connectHardware(config) {
    try {
      await apiConnectHardware(config)
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err.message }
    }
  },

  /**
   * POST /api/hardware/disconnect
   * Also stops any running job server-side before disconnecting.
   *
   * @returns {{ ok: boolean, error?: string }}
   */
  async disconnectHardware() {
    try {
      await apiDisconnectHardware()
      get().loadStatus()
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err.message }
    }
  },

  // -------------------------------------------------------------------------
  // Job actions
  // -------------------------------------------------------------------------

  /**
   * POST /api/job/start
   *
   * @param {'dispensing'|'hardness'} jobType
   * @param {Array} items  — array of PowderWell or HardnessSample objects
   * @returns {{ ok: boolean, error?: string }}
   */
  async submitJob(jobType, items) {
    try {
      const body =
        jobType === 'dispensing'
          ? { job_type: 'dispensing', wells:   items }
          : { job_type: 'hardness',   samples: items }

      await startJob(body)
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err.message }
    }
  },

  /**
   * POST /api/job/stop
   * Signals the running job to exit after the current well/sample.
   *
   * @returns {{ ok: boolean, error?: string }}
   */
  async stopJob() {
    try {
      await apiStopJob()
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err.message }
    }
  },

  /**
   * POST /api/job/cancel
   * Graceful cancel: finishes the current mold then stows the tool.
   *
   * @returns {{ ok: boolean, error?: string }}
   */
  async cancelJob() {
    try {
      await apiCancelJob()
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err.message }
    }
  },

  /**
   * POST /api/job/abort
   * Emergency stop: immediately halts all motion and sets ERROR state.
   *
   * @returns {{ ok: boolean, error?: string }}
   */
  async abortJob() {
    try {
      await apiAbortJob()
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err.message }
    }
  },

  /**
   * POST /api/job/clear_jam
   * Resumes a dispensing job that is paused due to a powder jam.
   *
   * @returns {{ ok: boolean, error?: string }}
   */
  async clearJam() {
    try {
      await apiClearJam()
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err.message }
    }
  },

  /**
   * GET /api/job/log
   * Fetch the most recent job log and store it.
   *
   * @returns {{ ok: boolean, error?: string }}
   */
  async fetchJobLog() {
    try {
      const data = await apiFetchJobLog()
      set({ jobLog: data.log ?? null, jobLogError: null })
      return { ok: true }
    } catch (err) {
      set({ jobLogError: err.message })
      return { ok: false, error: err.message }
    }
  },

  // -------------------------------------------------------------------------
  // Dispenser actions
  // -------------------------------------------------------------------------

  /**
   * PUT /api/dispensers/{index} — update piston count for one dispenser.
   * Can be called while connected (IDLE) without disconnecting.
   *
   * @param {number} index
   * @param {number} numPistons
   * @returns {{ ok: boolean, error?: string }}
   */
  async updateDispenser(index, numPistons) {
    try {
      await apiUpdateDispenser(index, numPistons)
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err.message }
    }
  },

  // -------------------------------------------------------------------------
  // Google Drive job log backup
  // -------------------------------------------------------------------------

  /**
   * Null when not yet fetched.  Shape mirrors GET /api/drive/status.
   */
  driveStatus: null,
  driveStatusError: null,

  /**
   * GET /api/drive/status — fetch and cache Drive backup status.
   *
   * @returns {{ ok: boolean, error?: string }}
   */
  async fetchDriveStatus() {
    try {
      const data = await apiFetchDriveStatus()
      set({ driveStatus: data, driveStatusError: null })
      return { ok: true }
    } catch (err) {
      set({ driveStatusError: err.message })
      return { ok: false, error: err.message }
    }
  },

  // -------------------------------------------------------------------------
  // UI prep actions - dispensing
  // -------------------------------------------------------------------------
  toggleDispensingWell(id) {
    set((state) => ({
      dispensingGrid: {
        ...state.dispensingGrid,
        wells: {
          ...state.dispensingGrid.wells,
          [id]: {
            ...state.dispensingGrid.wells[id],
            selected: !state.dispensingGrid.wells[id].selected,
          },
        },
      },
    }))
  },

  selectAllDispensingWells() {
    set((state) => {
      const nextWells = {}
      for (const id in state.dispensingGrid.wells) {
        nextWells[id] = { ...state.dispensingGrid.wells[id], selected: true }
      }
      return {
        dispensingGrid: {
          ...state.dispensingGrid,
          wells: nextWells,
        },
      }
    })
  },

  clearDispensingSelection() {
    set((state) => {
      const nextWells = {}
      for (const id in state.dispensingGrid.wells) {
        nextWells[id] = { ...state.dispensingGrid.wells[id], selected: false }
      }
      return {
        dispensingGrid: {
          ...state.dispensingGrid,
          wells: nextWells,
        },
      }
    })
  },

  selectDispensingRow(rowIndex) {
    const row = DISPENSING_LAYOUT[rowIndex]
    if (!row) return
    set((state) => {
      const { wells } = state.dispensingGrid
      const ids = row.filter((id) => id !== null).map(String)
      const allSelected = ids.every((id) => wells[id].selected)
      const nextWells = { ...wells }
      for (const id of ids) nextWells[id] = { ...nextWells[id], selected: !allSelected }
      return { dispensingGrid: { ...state.dispensingGrid, wells: nextWells } }
    })
  },

  selectDispensingCol(colIndex) {
    set((state) => {
      const { wells } = state.dispensingGrid
      const ids = DISPENSING_LAYOUT
        .map((row) => row[colIndex])
        .filter((id) => id !== null)
        .map(String)
      if (!ids.length) return {}
      const allSelected = ids.every((id) => wells[id].selected)
      const nextWells = { ...wells }
      for (const id of ids) nextWells[id] = { ...nextWells[id], selected: !allSelected }
      return { dispensingGrid: { ...state.dispensingGrid, wells: nextWells } }
    })
  },

  setDispensingWeightForSelected(targetWeight) {
    set((state) => {
      const nextWells = {}
      for (const id in state.dispensingGrid.wells) {
        const well = state.dispensingGrid.wells[id]
        nextWells[id] = well.selected ? { ...well, targetWeight } : well
      }
      return {
        dispensingGrid: {
          ...state.dispensingGrid,
          wells: nextWells,
        },
      }
    })
  },

  resetDispensingGrid() {
    set((state) => ({
      dispensingGrid: {
        ...state.dispensingGrid,
        wells: initDispensingWells(),
      },
    }))
  },

  // -------------------------------------------------------------------------
  // UI prep actions - hardness
  // -------------------------------------------------------------------------
  toggleHardnessSample(id) {
    set((state) => ({
      hardnessGrid: {
        ...state.hardnessGrid,
        samples: {
          ...state.hardnessGrid.samples,
          [id]: {
            ...state.hardnessGrid.samples[id],
            selected: !state.hardnessGrid.samples[id].selected,
          },
        },
      },
    }))
  },

  selectAllHardnessSamples() {
    set((state) => {
      const nextSamples = {}
      for (const id in state.hardnessGrid.samples) {
        nextSamples[id] = { ...state.hardnessGrid.samples[id], selected: true }
      }
      return {
        hardnessGrid: {
          ...state.hardnessGrid,
          samples: nextSamples,
        },
      }
    })
  },

  clearHardnessSelection() {
    set((state) => {
      const nextSamples = {}
      for (const id in state.hardnessGrid.samples) {
        nextSamples[id] = { ...state.hardnessGrid.samples[id], selected: false }
      }
      return {
        hardnessGrid: {
          ...state.hardnessGrid,
          samples: nextSamples,
        },
      }
    })
  },

  setHardnessModeForSelected(mode) {
    set((state) => {
      const nextSamples = {}
      for (const id in state.hardnessGrid.samples) {
        const sample = state.hardnessGrid.samples[id]
        nextSamples[id] = sample.selected ? { ...sample, mode } : sample
      }
      return {
        hardnessGrid: {
          ...state.hardnessGrid,
          samples: nextSamples,
        },
      }
    })
  },

  resetHardnessGrid() {
    set((state) => ({
      hardnessGrid: {
        ...state.hardnessGrid,
        samples: initHardnessSamples(
          state.hardnessGrid.rows,
          state.hardnessGrid.cols,
          state.hardnessGrid.trayCount,
        ),
      },
    }))
  },

}))
