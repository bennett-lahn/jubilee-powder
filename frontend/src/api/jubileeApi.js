/**
 * Thin HTTP wrapper for the Jubilee FastAPI backend.
 *
 * All functions return the parsed JSON body on success and throw an Error
 * whose message is the server's detail string on non-2xx responses.
 *
 * The Vite dev-server proxy forwards /api/* → http://localhost:8000, so the
 * base URL works identically in development and in the production FastAPI build.
 */

const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      console.error('[API] Non-2xx response', res.status, path, body)
      if (body?.detail) {
        detail = Array.isArray(body.detail)
          ? body.detail.map((e) => e.msg ?? JSON.stringify(e)).join('; ')
          : String(body.detail)
      }
    } catch (parseErr) {
      console.error('[API] Could not parse error body:', parseErr)
    }
    throw new Error(detail)
  }

  return res.json()
}

/** GET /api/config — machine settings from system_config.json */
export function fetchMachineConfig() {
  return request('/config')
}

// ---------------------------------------------------------------------------
// Hardware lifecycle
// ---------------------------------------------------------------------------

/**
 * POST /api/hardware/connect — begin connection with the given config.
 * Returns 202 immediately; monitor WebSocket state for HOMING → IDLE/ERROR.
 *
 * @param {{ num_dispensers: number, pistons_per_dispenser: number,
 *           machine_address?: string, scale_port?: string }} config
 */
export function connectHardware(config) {
  return request('/hardware/connect', {
    method: 'POST',
    body:   JSON.stringify(config),
  })
}

/**
 * POST /api/hardware/disconnect — stop any running job and disconnect.
 * Awaits server-side completion before resolving.
 */
export function disconnectHardware() {
  return request('/hardware/disconnect', { method: 'POST' })
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

/**
 * POST /api/job/start — enqueue a dispensing or hardness job.
 *
 * @param {{ job_type: 'dispensing', wells: Array }
 *        |{ job_type: 'hardness',  samples: Array }} body
 */
export function startJob(body) {
  return request('/job/start', {
    method: 'POST',
    body:   JSON.stringify(body),
  })
}

/**
 * POST /api/job/cancel — graceful cancel: finish current mold, stow tool, return to idle.
 */
export function cancelJob() {
  return request('/job/cancel', { method: 'POST' })
}

/**
 * POST /api/job/abort — emergency stop: immediately halt all motion (sets ERROR state).
 */
export function abortJob() {
  return request('/job/abort', { method: 'POST' })
}

/**
 * POST /api/job/clear_jam — resume a dispensing job paused by a powder jam.
 * Returns { cleared: true } on success; 400 if no jam is active.
 */
export function clearJam() {
  return request('/job/clear_jam', { method: 'POST' })
}

/**
 * GET /api/job/log — most recent job log, or { log: null } if none exists.
 */
export function fetchJobLog() {
  return request('/job/log')
}

/**
 * PUT /api/dispensers/{index} — update remaining piston count.
 *
 * @param {number} index
 * @param {number} numPistons
 */
export function updateDispenser(index, numPistons) {
  return request(`/dispensers/${index}`, {
    method: 'PUT',
    body:   JSON.stringify({ num_pistons: numPistons }),
  })
}

// ---------------------------------------------------------------------------
// Google Drive job log backup
// ---------------------------------------------------------------------------

/**
 * GET /api/drive/status — Drive backup status for Settings.
 * Returns { enabled, folder_configured, last_upload, last_error, pending_uploads }.
 */
export function fetchDriveStatus() {
  return request('/drive/status')
}
