/**
 * Powder Dispensing Screen.
 *
 * Ports the Kivy PowderDispensingScreen + BedVisualization.
 */

import { useState } from 'react'
import { useJubileeStore } from '../store/jubileeStore'
import WellGrid, { useWellGrid } from '../components/WellGrid'
import { Button, Card, TextInput, Dialog } from '../components/ui'

const ROWS = 4
const COLS = 6

function isValidWeight(v) {
  const n = parseFloat(v)
  return !isNaN(n) && n > 0
}

export default function PowderDispensingScreen() {
  const telemetry   = useJubileeStore((s) => s.telemetry)
  const submitJob   = useJubileeStore((s) => s.submitJob)
  // Machine is ready when the state machine reports idle
  const machineIdle = telemetry.state === 'idle' || telemetry.state === null

  const grid = useWellGrid(ROWS, COLS)

  // Derived selection state — recomputed each render, cheap for 24 wells
  const { selectedIds } = grid
  const selectedCount   = selectedIds.length
  const allHaveWeights  = selectedCount > 0 &&
    selectedIds.every((id) => (grid.wells[id]?.targetWeight ?? 0) > 0)

  // Weight dialog
  const [weightOpen,  setWeightOpen]  = useState(false)
  const [weightInput, setWeightInput] = useState('')

  // Status line
  const [statusText, setStatusText] = useState('Select wells and configure weights to begin.')

  // --- Weight dialog ---

  function openWeightDialog() {
    setWeightInput('')
    setWeightOpen(true)
  }

  function applyWeight() {
    const w = parseFloat(weightInput)
    grid.setWeightForSelected(w)
    setWeightOpen(false)
    setStatusText(`Target weight set to ${w} g for ${selectedCount} wells.`)
  }

  // --- Job ---

  async function startJob() {
    if (!machineIdle) { setStatusText(`Cannot start: machine is ${telemetry.state}.`); return }
    const items = selectedIds.map((id) => ({
      well_id:       id,
      target_weight: grid.wells[id].targetWeight,
    }))
    setStatusText('Submitting job…')
    const { ok, error } = await submitJob('dispensing', items)
    setStatusText(ok ? `Job started: ${items.length} wells.` : `Error: ${error}`)
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

        {/* Selection count badge */}
        <span className="text-sm text-slate-400 px-1 tabular-nums">
          {selectedCount > 0 ? `${selectedCount} selected` : ''}
        </span>

        <div className="flex-1" />

        {/* Set Weights: enabled only when wells are selected */}
        <Button
          size="sm"
          variant="outlined"
          onClick={openWeightDialog}
          disabled={selectedCount === 0}
        >
          Set Weights
        </Button>

        {/* Start Job: enabled only when machine idle + wells selected + weights set */}
        <Button
          size="sm"
          onClick={startJob}
          disabled={!machineIdle || selectedCount === 0 || !allHaveWeights}
        >
          Start Job
        </Button>
      </Card>

      {/* ── Bed visualisation — fills remaining height ────────────────── */}
      <Card className="flex-1 p-4 min-h-0">
        <WellGrid
          wells={grid.wells}
          rows={grid.rows}
          cols={grid.cols}
          toggleWell={grid.toggleWell}
          selectRow={grid.selectRow}
          selectCol={grid.selectCol}
          variant="dispensing"
          className="h-full"
        />
      </Card>

      {/* ── Status line ──────────────────────────────────────────────── */}
      <p className="text-center text-sm text-slate-400 shrink-0 pb-1">
        {statusText}
      </p>

      {/* ── Weight dialog ─────────────────────────────────────────────── */}
      <Dialog
        open={weightOpen}
        title="Set Target Weights"
        onClose={() => setWeightOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setWeightOpen(false)}>Cancel</Button>
            {/* Apply is disabled until a valid positive number is entered */}
            <Button onClick={applyWeight} disabled={!isValidWeight(weightInput)}>
              Apply
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-400 mb-4">
          Applies to {selectedCount} selected {selectedCount === 1 ? 'well' : 'wells'}.
        </p>
        <TextInput
          label="Target Weight"
          unit="g"
          type="number"
          placeholder="e.g. 50.0"
          value={weightInput}
          onChange={(v) => setWeightInput(v)}
          autoFocus
        />
      </Dialog>
    </div>
  )
}
