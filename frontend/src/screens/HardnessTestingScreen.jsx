/**
 * Hardness Testing Screen.
 *
 * Ports the Kivy HardnessTestingScreen + HardnessSampleGrid.
 */

import { useMemo, useState } from 'react'
import { useJubileeStore } from '../store/jubileeStore'
import SampleTrayGrid from '../components/SampleTrayGrid'
import { Button, Card } from '../components/ui'

const MODES = [
  { key: 'none',      label: 'None',    variant: 'ghost'    },
  { key: 'shore_a',   label: 'Shore A', variant: 'outlined' },
  { key: 'shore_a_d', label: 'A + D',   variant: 'outlined' },
  { key: 'shore_d',   label: 'Shore D', variant: 'outlined' },
]

export default function HardnessTestingScreen() {
  const telemetry  = useJubileeStore((s) => s.telemetry)
  const submitJob  = useJubileeStore((s) => s.submitJob)
  const hardnessGrid = useJubileeStore((s) => s.hardnessGrid)
  const toggleHardnessSample = useJubileeStore((s) => s.toggleHardnessSample)
  const selectAllHardnessSamples = useJubileeStore((s) => s.selectAllHardnessSamples)
  const clearHardnessSelection = useJubileeStore((s) => s.clearHardnessSelection)
  const setHardnessModeForSelected = useJubileeStore((s) => s.setHardnessModeForSelected)
  const machineIdle = telemetry.state === 'idle' || telemetry.state === null

  const { rows, cols, trayCount, samples } = hardnessGrid
  const selectedIds = useMemo(
    () => Object.entries(samples).filter(([, sample]) => sample.selected).map(([id]) => id),
    [samples],
  )
  const eligibleIds = useMemo(
    () => Object.entries(samples).filter(([, sample]) => sample.mode !== 'none').map(([id]) => id),
    [samples],
  )
  const selectedCount = selectedIds.length
  const eligibleCount = eligibleIds.length

  const [statusText, setStatusText] = useState('Select samples and assign a test mode.')

  function assignMode(mode) {
    if (selectedCount === 0) { setStatusText('Select at least one sample first.'); return }
    setHardnessModeForSelected(mode)
    const label = MODES.find((m) => m.key === mode)?.label ?? mode
    setStatusText(`"${label}" assigned to ${selectedCount} ${selectedCount === 1 ? 'sample' : 'samples'}.`)
  }

  async function startTest() {
    if (!machineIdle) { setStatusText(`Cannot start: machine is ${telemetry.state}.`); return }
    const items = eligibleIds.map((id) => {
      const [trayIndex, localSampleIndex] = id.split(':')
      return {
        tray_index:   Number(trayIndex),
        sample_index: Number(localSampleIndex),
        mode:         samples[id].mode,
      }
    })
    console.log('[HardnessTesting] Submitting', items.length, 'items:', JSON.stringify(items))
    setStatusText('Submitting test…')
    const { ok, error } = await submitJob('hardness', items)
    if (!ok) console.error('[HardnessTesting] submitJob failed, error:', error)
    setStatusText(ok ? `Test started: ${items.length} samples.` : `Error: ${error}`)
  }

  return (
    <div className="flex flex-col gap-3 h-full">

      {/* ── Slim action toolbar ───────────────────────────────────────── */}
      <Card className="flex items-center gap-2 py-2 px-3 shrink-0">
        <Button size="sm" variant="outlined" onClick={selectAllHardnessSamples}>
          Select All
        </Button>
        <Button size="sm" variant="ghost" onClick={clearHardnessSelection} disabled={selectedCount === 0}>
          Clear
        </Button>

        {/* Thin divider */}
        <div className="w-px h-5 bg-slate-700 mx-1 shrink-0" />

        {/* Mode buttons — disabled until at least one sample is selected */}
        {MODES.map(({ key, label, variant }) => (
          <Button
            key={key}
            size="sm"
            variant={variant}
            onClick={() => assignMode(key)}
            disabled={selectedCount === 0}
          >
            {label}
          </Button>
        ))}

        <div className="flex-1" />

        {/* Start Test: enabled only when machine idle and samples with assigned modes exist */}
        <Button
          size="sm"
          onClick={startTest}
          disabled={!machineIdle || eligibleCount === 0}
        >
          Start Test
        </Button>
      </Card>

      {/* ── Sample grid — fills remaining height ──────────────────────── */}
      <Card className="flex-1 p-4 min-h-0">
        <SampleTrayGrid
          samples={samples}
          rows={rows}
          cols={cols}
          toggleSample={toggleHardnessSample}
          variant="hardness"
          trayCount={trayCount}
          className="h-full"
        />
      </Card>

      {/* ── Status line ──────────────────────────────────────────────── */}
      <p className="text-center text-sm text-slate-400 shrink-0 pb-1">
        {statusText}
      </p>
    </div>
  )
}
