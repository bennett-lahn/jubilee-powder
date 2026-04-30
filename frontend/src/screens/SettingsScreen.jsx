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

import { useState, useEffect } from 'react'
import { ArrowLeft, Camera } from 'lucide-react'
import { useJubileeStore } from '../store/jubileeStore'
import { Button, Card, TextInput, StatusBadge } from '../components/ui'

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

function LevelCameraView({ onClose }) {
  const startLevelCamera = useJubileeStore((s) => s.startLevelCamera)
  const stopLevelCamera  = useJubileeStore((s) => s.stopLevelCamera)
  const [ready, setReady]   = useState(false)
  const [error, setError]   = useState(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const result = await startLevelCamera()
      if (cancelled) return
      if (!result.ok) {
        setError(result.error)
      } else {
        setReady(true)
      }
    })()
    return () => {
      cancelled = true
      stopLevelCamera()
    }
  }, [startLevelCamera, stopLevelCamera])

  return (
    <div className="flex flex-col gap-4 h-full">
      <Card className="flex items-center gap-3 p-3 shrink-0">
        <Button variant="ghost" size="sm" onClick={onClose} className="shrink-0">
          <ArrowLeft size={16} className="mr-1" />
          Back to Settings
        </Button>
        <div className="w-px h-4 bg-slate-700 shrink-0" />
        <Camera size={16} className="text-slate-400" />
        <span className="text-slate-300 font-medium">Scale Bubble Level</span>
      </Card>

      <Card className="flex-1 flex items-center justify-center p-4 min-h-0 overflow-hidden">
        {error ? (
          <div className="text-center">
            <StatusBadge status="error" label="Camera Error" />
            <p className="text-xs text-slate-500 mt-2">{error}</p>
          </div>
        ) : !ready ? (
          <p className="text-slate-500 text-sm">Starting camera...</p>
        ) : (
          <img
            src="/api/camera/stream"
            alt="Scale bubble level"
            className="max-w-full max-h-full rounded-lg object-contain"
          />
        )}
      </Card>
    </div>
  )
}

export default function SettingsScreen() {
  const telemetry          = useJubileeStore((s) => s.telemetry)
  const connectHardware    = useJubileeStore((s) => s.connectHardware)
  const disconnectHardware = useJubileeStore((s) => s.disconnectHardware)
  const updateDispenser    = useJubileeStore((s) => s.updateDispenser)

  const [showLevelCamera, setShowLevelCamera] = useState(false)

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

  // Form state
  const [numDispensers,       setNumDispensers]       = useState('2')
  const [pistonsPerDispenser, setPistonsPerDispenser] = useState('10')
  const [jubileeIp,           setJubileeIp]           = useState('jubilee.local')
  const [scalePort,           setScalePort]           = useState('/dev/ttyUSB0')
  const [statusMsg,           setStatusMsg]           = useState('')

  const numD = parseInt(numDispensers,       10)
  const numP = parseInt(pistonsPerDispenser, 10)
  const totalPistons = (!isNaN(numD) && !isNaN(numP)) ? numD * numP : null
  const inputsValid  = !isNaN(numD) && numD > 0 && !isNaN(numP) && numP > 0

  async function handleConnect() {
    if (!inputsValid || inputsLocked) return
    setStatusMsg('')
    const result = await connectHardware({
      num_dispensers:        numD,
      pistons_per_dispenser: numP,
      machine_address:       jubileeIp.trim() || null,
      scale_port:            scalePort.trim() || '/dev/ttyUSB0',
    })
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

  if (showLevelCamera) {
    return <LevelCameraView onClose={() => setShowLevelCamera(false)} />
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

        {/* Scale level camera */}
        <Card className="flex items-center justify-between p-4">
          <div>
            <p className="text-slate-200 font-semibold">Scale Level Camera</p>
            <p className="text-xs text-slate-500 mt-0.5">
              View the bubble level to help level the scale.
            </p>
          </div>
          <Button onClick={() => setShowLevelCamera(true)}>
            <Camera size={16} className="mr-2" />
            Open Camera
          </Button>
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

      </div>
    </div>
  )
}
