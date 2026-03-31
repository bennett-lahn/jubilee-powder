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
 */

import { create } from 'zustand'
import {
  fetchStatus,
  connectHardware as apiConnectHardware,
  disconnectHardware as apiDisconnectHardware,
  startJob,
  stopJob as apiStopJob,
} from '../api/jubileeApi'

function wsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}/ws`
}

const RECONNECT_DELAY_MS = 1500

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
  // WebSocket connection state
  // -------------------------------------------------------------------------
  wsConnected:     false,
  _ws:             null,
  _reconnectTimer: null,

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

}))
