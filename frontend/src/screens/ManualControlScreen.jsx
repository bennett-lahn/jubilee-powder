/**
 * Manual Control Screen.
 *
 * Ports the Kivy ManualControlScreen.
 * Warns the user about state implications before opening the Jubilee web UI.
 * On confirmation, disconnects the automation system via the API before
 * opening the browser so the hardware state machine is cleanly reset.
 */

import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Button, Card, Dialog } from '../components/ui'
import { useJubileeStore } from '../store/jubileeStore'

const WARNING_POINTS = [
  'Invalidates the current automation system state.',
  'Requires system recalibration after use.',
  'May interrupt any running jobs.',
  'Moves hardware outside of tracked positions.',
]

const RECONNECT_STEPS = [
  'Return to Settings.',
  'Disconnect then reconnect the system.',
  'Verify all hardware positions are correct.',
]

export default function ManualControlScreen() {
  const telemetry          = useJubileeStore((s) => s.telemetry)
  const disconnectHardware = useJubileeStore((s) => s.disconnectHardware)

  // jubilee_ip is broadcast in every telemetry frame once hardware is connected
  const jubileeIp = telemetry.jubilee_ip ?? 'Not connected'

  const [confirmOpen, setConfirmOpen] = useState(false)
  const [resultOpen,  setResultOpen]  = useState(false)
  const [resultMsg,   setResultMsg]   = useState('')
  const [proceeding,  setProceeding]  = useState(false)

  async function handleProceed() {
    setConfirmOpen(false)
    setProceeding(true)
    try {
      // Disconnect the automation system so the state machine is cleanly reset
      // before the user makes manual moves via the Jubilee web UI.
      await disconnectHardware()
      window.open(`http://${jubileeIp}`, '_blank', 'noopener,noreferrer')
      setResultMsg(
        `Jubilee web UI opened at http://${jubileeIp}.\n\n` +
        'The automation system has been disconnected.\n' +
        'Remember to reconnect in Settings after using manual control.'
      )
    } catch (e) {
      setResultMsg(`Could not complete: ${e.message}`)
    } finally {
      setProceeding(false)
      setResultOpen(true)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 max-w-2xl mx-auto">

      {/* Warning card */}
      <Card variant="highlight" className="w-full p-6 flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <AlertTriangle size={28} className="text-jubilee shrink-0" />
          <h2 className="text-lg font-bold text-slate-100 uppercase tracking-wide">
            Manual Control — Advanced Users Only
          </h2>
        </div>

        <div>
          <p className="text-sm font-semibold text-slate-300 mb-2">
            Using the Jubilee web UI will:
          </p>
          <ul className="space-y-1">
            {WARNING_POINTS.map((pt) => (
              <li key={pt} className="flex items-start gap-2 text-sm text-slate-400">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-jubilee shrink-0" />
                {pt}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="text-sm font-semibold text-slate-300 mb-2">
            After using manual control you must:
          </p>
          <ol className="space-y-1">
            {RECONNECT_STEPS.map((step, i) => (
              <li key={step} className="flex items-start gap-2 text-sm text-slate-400">
                <span className="shrink-0 font-mono text-jubilee">{i + 1}.</span>
                {step}
              </li>
            ))}
          </ol>
        </div>
      </Card>

      <Button size="lg" onClick={() => setConfirmOpen(true)} disabled={proceeding}>
        Open Jubilee Web UI
      </Button>

      {/* Confirmation dialog */}
      <Dialog
        open={confirmOpen}
        title="Confirm Manual Control"
        onClose={() => setConfirmOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleProceed}>I Understand — Proceed</Button>
          </>
        }
      >
        <p className="text-sm text-slate-400">
          Are you sure? This will disconnect the automation system and require
          manual recalibration afterward.
        </p>
      </Dialog>

      {/* Result dialog */}
      <Dialog
        open={resultOpen}
        title="Web UI Opened"
        onClose={() => setResultOpen(false)}
        footer={<Button onClick={() => setResultOpen(false)}>OK</Button>}
      >
        <p className="text-sm text-slate-400 whitespace-pre-line">{resultMsg}</p>
      </Dialog>

    </div>
  )
}
