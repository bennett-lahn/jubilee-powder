/**
 * Hardness Testing Screen.
 *
 * Ports the Kivy HardnessTestingScreen + HardnessSampleGrid.
 */

import { useState } from 'react'
import { useJubileeStore } from '../store/jubileeStore'
import SampleTrayGrid, { useSampleTrayGrid } from '../components/SampleTrayGrid'
import { Button, Card } from '../components/ui'

const TRAY_ROWS = 5
const TRAY_COLS = 5
const TRAY_COUNT = 2

const MODES = [
  { key: 'none',      label: 'None',    variant: 'ghost'    },
  { key: 'shore_a',   label: 'Shore A', variant: 'outlined' },
  { key: 'shore_a_d', label: 'A + D',   variant: 'outlined' },
  { key: 'shore_d',   label: 'Shore D', variant: 'outlined' },
]

export default function HardnessTestingScreen() {
  const telemetry  = useJubileeStore((s) => s.telemetry)
  const submitJob  = useJubileeStore((s) => s.submitJob)
  const machineIdle = telemetry.state === 'idle' || telemetry.state === null

  const grid = useSampleTrayGrid(TRAY_ROWS, TRAY_COLS, TRAY_COUNT)
  const { selectedIds } = grid
  const selectedCount = selectedIds.length

  const [statusText, setStatusText] = useState('Select samples and assign a test mode.')

  function assignMode(mode) {
    if (selectedCount === 0) { setStatusText('Select at least one sample first.'); return }
    grid.setModeForSelected(mode)
    const label = MODES.find((m) => m.key === mode)?.label ?? mode
    setStatusText(`"${label}" assigned to ${selectedCount} ${selectedCount === 1 ? 'sample' : 'samples'}.`)
  }

  async function startTest() {
    if (!machineIdle) { setStatusText(`Cannot start: machine is ${telemetry.state}.`); return }
    const items = selectedIds.map((id) => {
      const [trayIndex, localSampleIndex] = id.split(':')
      return {
        tray_index: Number(trayIndex),
        sample_id: String(localSampleIndex),
        mode:      grid.samples[id].mode,
      }
    })
    setStatusText('Submitting test…')
    const { ok, error } = await submitJob('hardness', items)
    setStatusText(ok ? `Test started: ${items.length} samples.` : `Error: ${error}`)
  }

  return (
    <div className="flex flex-col gap-3 h-full">

      {/* ── Slim action toolbar ───────────────────────────────────────── */}
      <Card className="flex items-center gap-2 py-2 px-3 shrink-0">
        <Button size="sm" variant="outlined" onClick={grid.selectAll}>
          Select All
        </Button>
        <Button size="sm" variant="ghost" onClick={grid.clearSelection} disabled={selectedCount === 0}>
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

        {/* Start Test: enabled only when machine idle and samples with modes selected */}
        <Button
          size="sm"
          onClick={startTest}
          disabled={!machineIdle || selectedCount === 0}
        >
          Start Test
        </Button>
      </Card>

      {/* ── Sample grid — fills remaining height ──────────────────────── */}
      <Card className="flex-1 p-4 min-h-0">
        <SampleTrayGrid
          samples={grid.samples}
          rows={grid.rows}
          cols={grid.cols}
          toggleSample={grid.toggleSample}
          variant="hardness"
          trayCount={grid.trayCount}
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
