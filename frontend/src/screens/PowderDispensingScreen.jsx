/**
 * Powder Dispensing Screen.
 *
 * Ports the Kivy PowderDispensingScreen + BedVisualization.
 */

import { useMemo, useState } from 'react'
import { useJubileeStore } from '../store/jubileeStore'
import WellGrid from '../components/WellGrid'
import { Button, Card, TextInput, Dialog } from '../components/ui'

function isValidWeight(v) {
  const n = parseFloat(v)
  return !isNaN(n) && n > 0
}

export default function PowderDispensingScreen() {
  const telemetry   = useJubileeStore((s) => s.telemetry)
  const submitJob   = useJubileeStore((s) => s.submitJob)
  const dispensingGrid = useJubileeStore((s) => s.dispensingGrid)
  const toggleDispensingWell = useJubileeStore((s) => s.toggleDispensingWell)
  const selectAllDispensingWells = useJubileeStore((s) => s.selectAllDispensingWells)
  const clearDispensingSelection = useJubileeStore((s) => s.clearDispensingSelection)
  const selectDispensingRow = useJubileeStore((s) => s.selectDispensingRow)
  const selectDispensingCol = useJubileeStore((s) => s.selectDispensingCol)
  const setDispensingWeightForSelected = useJubileeStore((s) => s.setDispensingWeightForSelected)
  // Machine is ready when the state machine reports idle
  const machineIdle = telemetry.state === 'idle' || telemetry.state === null

  const { rows, cols, wells } = dispensingGrid
  const selectedIds = useMemo(
    () => Object.entries(wells).filter(([, w]) => w.selected).map(([id]) => id),
    [wells],
  )
  const eligibleIds = useMemo(
    () => Object.entries(wells).filter(([, w]) => (w.targetWeight ?? 0) > 0).map(([id]) => id),
    [wells],
  )
  const selectedCount   = selectedIds.length
  const eligibleCount = eligibleIds.length

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
    setDispensingWeightForSelected(w)
    setWeightOpen(false)
    setStatusText(`Target weight set to ${w} g for ${selectedCount} wells.`)
  }

  // --- Job ---

  async function startJob() {
    if (!machineIdle) { setStatusText(`Cannot start: machine is ${telemetry.state}.`); return }
    const items = eligibleIds.map((id) => ({
      well_id:       id,
      target_weight: wells[id].targetWeight,
    }))
    setStatusText('Submitting job…')
    const { ok, error } = await submitJob('dispensing', items)
    setStatusText(ok ? `Job started: ${items.length} wells.` : `Error: ${error}`)
  }

  return (
    <div className="flex flex-col gap-3 h-full">

      {/* ── Slim action toolbar ───────────────────────────────────────── */}
      <Card className="flex items-center gap-2 py-2 px-3 shrink-0">
        <Button size="sm" variant="outlined" onClick={selectAllDispensingWells}>
          Select All
        </Button>
        <Button size="sm" variant="ghost" onClick={clearDispensingSelection} disabled={selectedCount === 0}>
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

        {/* Start Job: enabled only when machine idle + at least one configured target weight */}
        <Button
          size="sm"
          onClick={startJob}
          disabled={!machineIdle || eligibleCount === 0}
        >
          Start Job
        </Button>
      </Card>

      {/* ── Bed visualisation — fills remaining height ────────────────── */}
      <Card className="flex-1 p-4 min-h-0">
        <WellGrid
          wells={wells}
          rows={rows}
          cols={cols}
          toggleWell={toggleDispensingWell}
          selectRow={selectDispensingRow}
          selectCol={selectDispensingCol}
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
