/**
 * Settings Screen.
 *
 * Ports the Kivy SettingsScreen.
 *
 * Connection state is driven entirely by telemetry.state from the WebSocket
 * rather than a separate REST poll, so the UI reflects hardware transitions
 * (DISCONNECTED → HOMING → IDLE/ERROR) in real time without polling.
 *
 * Input locking rules:
 *   - Locked when state is IDLE, RUNNING, or HOMING (hardware active).
 *   - Unlocked only when DISCONNECTED or ERROR.
 */

import { useEffect, useState } from 'react'
import { useJubileeStore } from '../store/jubileeStore'
import { fetchMachineConfig } from '../api/jubileeApi'
import { Button, Card, TextInput, StatusBadge } from '../components/ui'
import {
  HardnessProfilesSection,
  TricklerProfilesSection,
} from '../components/settings/ProfileConfigSections'

// ---------------------------------------------------------------------------
// Google Drive section
// ---------------------------------------------------------------------------

function GoogleDriveSection() {
  const driveStatus      = useJubileeStore((s) => s.driveStatus)
  const driveStatusError = useJubileeStore((s) => s.driveStatusError)
  const fetchDriveStatus = useJubileeStore((s) => s.fetchDriveStatus)

  useEffect(() => { fetchDriveStatus() }, [])

  // Hide only when the server explicitly reports the feature is disabled
  // (config has enabled=false). An init failure still sets enabled=true with
  // a last_error, so the panel renders showing what went wrong.
  if (driveStatus !== null && !driveStatus.enabled) return null

  // If the status fetch itself failed (network error, server down, etc.),
  // render a minimal error card rather than silently hiding.
  if (driveStatus === null && driveStatusError) {
    return (
      <Card className="flex flex-col gap-3 p-5">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
          Google Drive
        </h3>
        <p className="text-xs text-red-400 break-all">
          Could not load Drive status: {driveStatusError}
        </p>
        <Button size="sm" variant="outlined" onClick={fetchDriveStatus} className="self-start">
          Retry
        </Button>
      </Card>
    )
  }

  const folderOk   = driveStatus?.folder_configured ?? false
  const lastUpload = driveStatus?.last_upload ?? null
  const lastError  = driveStatus?.last_error ?? null
  const ready      = driveStatus?.enabled && folderOk && !lastError

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
          Google Drive Backup
        </h3>
        <div className="flex items-center gap-2">
          <span className={[
            'inline-block w-2 h-2 rounded-full',
            ready ? 'bg-green-500' : 'bg-slate-600',
          ].join(' ')} />
          <span className="text-xs text-slate-500">
            {ready ? 'Ready' : folderOk ? 'Check config' : 'Not configured'}
          </span>
        </div>
      </div>

      <p className="text-xs text-slate-500">
        Completed jobs upload automatically to the Drive folder in{' '}
        <code className="text-slate-400">google_drive.drive_folder_id</code>{' '}
        (JSON, CSV, and hardness images per job).
      </p>

      {!folderOk && driveStatus?.enabled && (
        <p className="text-xs text-amber-400">
          Set <code className="text-slate-400">google_drive.drive_folder_id</code> in system_config.json.
        </p>
      )}

      {lastUpload && (
        <p className="text-xs text-slate-500">
          Last upload: {new Date(lastUpload).toLocaleString()}
        </p>
      )}

      {(driveStatus?.pending_uploads ?? 0) > 0 && (
        <p className="text-xs text-amber-400">
          {driveStatus.pending_uploads} log{driveStatus.pending_uploads !== 1 ? 's' : ''} pending upload — will retry automatically.
        </p>
      )}

      {lastError && (
        <p className="text-xs text-red-400 break-all">Error: {lastError}</p>
      )}

      <Button
        size="sm"
        variant="outlined"
        onClick={fetchDriveStatus}
        className="self-start shrink-0"
      >
        Refresh status
      </Button>
    </Card>
  )
}

function DispenserRow({ dispenser, disabled, onUpdate }) {
  const [value,  setValue]  = useState(String(dispenser.pistons_remaining))
  const [status, setStatus] = useState(null)   // null | 'ok' | 'error'
  const [msg,    setMsg]    = useState('')

  // Keep local value in sync when telemetry updates (e.g. after a successful PUT)
  useEffect(() => {
    setValue(String(dispenser.pistons_remaining))
  }, [dispenser.pistons_remaining])

  async function handleUpdate() {
    const n = parseInt(value, 10)
    if (isNaN(n) || n < 0) {
      setStatus('error')
      setMsg('Enter a valid number >= 0')
      return
    }
    setStatus(null)
    setMsg('')
    const result = await onUpdate(dispenser.index, n)
    if (result.ok) {
      setStatus('ok')
      setMsg('Updated')
      setTimeout(() => setStatus(null), 2000)
    } else {
      setStatus('error')
      setMsg(result.error ?? 'Update failed')
    }
  }

  return (
    <div className="flex items-center gap-3">
      <span className="text-slate-400 text-sm w-28 shrink-0">
        Dispenser {dispenser.index}
      </span>
      <TextInput
        type="number"
        value={value}
        onChange={setValue}
        disabled={disabled}
        placeholder="0"
        className="flex-1"
      />
      <Button
        size="sm"
        onClick={handleUpdate}
        disabled={disabled}
        className="shrink-0"
      >
        Update
      </Button>
      {status === 'ok'    && <span className="text-xs text-green-400 shrink-0">{msg}</span>}
      {status === 'error' && <span className="text-xs text-red-400 shrink-0">{msg}</span>}
    </div>
  )
}

const STATE_LABEL = {
  idle:         'Connected',
  running:      'Running',
  homing:       'Connecting…',
  error:        'Error',
  disconnected: 'Disconnected',
}

const STATE_BADGE = {
  idle:         'ok',
  running:      'warn',
  homing:       'warn',
  error:        'error',
  disconnected: 'idle',
}

export default function SettingsScreen() {
  const telemetry          = useJubileeStore((s) => s.telemetry)
  const connectHardware    = useJubileeStore((s) => s.connectHardware)
  const disconnectHardware = useJubileeStore((s) => s.disconnectHardware)
  const updateDispenser    = useJubileeStore((s) => s.updateDispenser)

  const hwState    = telemetry.state ?? 'disconnected'
  const isIdle     = hwState === 'idle'
  const isRunning  = hwState === 'running'
  const isHoming   = hwState === 'homing'
  const isError    = hwState === 'error'

  // Connection config inputs are locked whenever hardware is active.
  // Only editable when fully disconnected or in an error state.
  const inputsLocked = isIdle || isRunning || isHoming

  // Dispenser piston counts can be updated while idle (not during a job or homing).
  const dispenserEditsLocked = !isIdle
  const dispensers = telemetry.dispensers ?? []

  // Form state (hydrated from GET /api/config on mount)
  const [numDispensers,       setNumDispensers]       = useState('')
  const [pistonsPerDispenser, setPistonsPerDispenser] = useState('')
  const [jubileeIp,           setJubileeIp]           = useState('')
  const [scalePort,           setScalePort]           = useState('')
  const [statusMsg,           setStatusMsg]           = useState('')
  const [configError,         setConfigError]         = useState(null)
  const [profileEditsLocked,  setProfileEditsLocked]  = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchMachineConfig()
      .then((cfg) => {
        if (cancelled) return
        setNumDispensers(String(cfg.num_dispensers ?? ''))
        setPistonsPerDispenser(String(cfg.pistons_per_dispenser ?? ''))
        setJubileeIp(cfg.duet_ip ?? '')
        setScalePort(cfg.scale_port ?? '')
        setProfileEditsLocked(Boolean(cfg.profile_edits_locked))
        setConfigError(null)
      })
      .catch((err) => {
        if (!cancelled) setConfigError(err.message)
      })
    return () => { cancelled = true }
  }, [])

  const numD = parseInt(numDispensers,       10)
  const numP = parseInt(pistonsPerDispenser, 10)
  const totalPistons = (!isNaN(numD) && !isNaN(numP)) ? numD * numP : null
  const inputsValid  = !isNaN(numD) && numD > 0 && !isNaN(numP) && numP > 0

  async function handleConnect() {
    if (!inputsValid || inputsLocked) return
    setStatusMsg('')
    const body = {
      num_dispensers:        numD,
      pistons_per_dispenser: numP,
      machine_address:       jubileeIp.trim() || null,
    }
    const scale = scalePort.trim()
    if (scale) body.scale_port = scale
    const result = await connectHardware(body)
    if (!result.ok) {
      setStatusMsg(`Request failed: ${result.error}`)
    }
    // Connection progress is reflected via telemetry.state (HOMING → IDLE/ERROR)
    // No need to poll; the WebSocket frame updates the UI automatically.
  }

  async function handleDisconnect() {
    setStatusMsg('')
    const result = await disconnectHardware()
    if (!result.ok) {
      setStatusMsg(`Disconnect failed: ${result.error}`)
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="flex flex-col gap-4 max-w-xl mx-auto py-2">

        {/* Connection status */}
        <Card className="flex items-center justify-between p-4 shrink-0">
          <div>
            <p className="text-slate-200 font-semibold">System Status</p>
            <p className="text-xs text-slate-500 mt-0.5">
              {inputsLocked
                ? 'Settings are locked while hardware is active.'
                : isError
                  ? 'Connection error — settings unlocked for reconfiguration.'
                  : 'Settings can be modified while disconnected.'}
            </p>
          </div>
          <StatusBadge
            status={STATE_BADGE[hwState] ?? 'idle'}
            label={STATE_LABEL[hwState] ?? hwState}
          />
        </Card>

        {/* Hardware configuration */}
        <Card className="flex flex-col gap-5 p-5">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
            Hardware Configuration
          </h3>

          <TextInput
            label="Number of Powder Dispensers"
            placeholder="e.g. 2"
            type="number"
            value={numDispensers}
            onChange={setNumDispensers}
            disabled={inputsLocked}
            hint={totalPistons !== null ? `Total pistons available: ${totalPistons}` : undefined}
          />

          <TextInput
            label="Pistons per Dispenser"
            placeholder="e.g. 10"
            type="number"
            value={pistonsPerDispenser}
            onChange={setPistonsPerDispenser}
            disabled={inputsLocked}
          />
        </Card>

        {/* Per-dispenser piston counts — only visible when connected */}
        {dispensers.length > 0 && (
          <Card className="flex flex-col gap-4 p-5">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
                Dispenser Pistons
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                Update remaining pistons after reloading the dispensers.
                {isRunning && ' Locked while a job is running.'}
              </p>
            </div>
            {dispensers.map((d) => (
              <DispenserRow
                key={d.index}
                dispenser={d}
                disabled={dispenserEditsLocked}
                onUpdate={updateDispenser}
              />
            ))}
          </Card>
        )}

        {/* Network / serial configuration */}
        <Card className="flex flex-col gap-5 p-5">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
            Connection Configuration
          </h3>

          {configError && (
            <p className="text-xs text-amber-400">
              Could not load defaults from server: {configError}
            </p>
          )}

          <TextInput
            label="Jubilee IP Address or Hostname"
            placeholder="192.168.1.2"
            value={jubileeIp}
            onChange={setJubileeIp}
            disabled={inputsLocked}
          />

          <TextInput
            label="Scale Serial Port"
            placeholder="/dev/ttyUSB0"
            value={scalePort}
            onChange={setScalePort}
            disabled={inputsLocked}
            hint="Linux: /dev/ttyUSB0   Windows: COM3"
          />
        </Card>

        {/* Connect / Disconnect */}
        <Card className="flex items-center gap-4 p-4">
          <Button
            className="flex-1"
            onClick={handleConnect}
            disabled={inputsLocked || !inputsValid}
          >
            {isHoming ? 'Connecting…' : 'Connect to Jubilee'}
          </Button>
          <Button
            className="flex-1"
            variant="danger"
            onClick={handleDisconnect}
            disabled={!isIdle && !isRunning && !isHoming}
          >
            Disconnect
          </Button>
        </Card>

        {statusMsg && (
          <p className="text-center text-xs text-slate-500 pb-2">{statusMsg}</p>
        )}

        <TricklerProfilesSection locked={profileEditsLocked || inputsLocked} />
        <HardnessProfilesSection locked={profileEditsLocked || inputsLocked} />

        <GoogleDriveSection />

      </div>
    </div>
  )
}
