/**
 * WellGrid — interactive bed visualisation.
 *
 * Sizing strategy
 *   Wells are height-driven: each data row takes an equal share of the
 *   container height (flex-1), and each well button is h-full with
 *   aspectRatio:1 so it becomes a circle sized by its row's height.
 *   This means the grid fills whatever vertical space the parent gives it —
 *   typically most of the kiosk screen — without any hardcoded pixel sizes.
 *
 * Row / column axis buttons
 *   Clicking a row or column button toggles the entire row/column:
 *   if every well in it is already selected the click deselects all of them;
 *   otherwise it selects all of them.
 *
 * Variants
 *   'dispensing'  — shows target weight label inside selected wells
 *   'hardness'    — shows Shore mode label (A / A+D / D)
 *   'result'      — read-only; colors wells by status field (pending/active/complete/error/excluded)
 *                   used on the Home screen to display live job progress and completed job results
 */

import { useState, useCallback, useMemo } from 'react'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SHORE_LABELS = {
  shore_a:   'A',
  shore_a_d: 'A+D',
  shore_d:   'D',
  none:      '',
}

// ---------------------------------------------------------------------------
// useWellGrid hook
// ---------------------------------------------------------------------------

function initWells(rows, cols) {
  const wells = {}
  for (let i = 0; i < rows * cols; i++) {
    wells[String(i)] = {
      selected:      false,
      targetWeight:  0,
      currentWeight: 0,
      mode:          'none',
    }
  }
  return wells
}

export function useWellGrid(rows = 4, cols = 6) {
  const [wells, setWells] = useState(() => initWells(rows, cols))

  // Derived: IDs of currently selected wells (memoised for stable identity)
  const selectedIds = useMemo(
    () => Object.entries(wells).filter(([, w]) => w.selected).map(([id]) => id),
    [wells],
  )

  const toggleWell = useCallback((id) => {
    setWells((prev) => ({
      ...prev,
      [id]: { ...prev[id], selected: !prev[id].selected },
    }))
  }, [])

  const selectAll = useCallback(() => {
    setWells((prev) => {
      const next = {}
      for (const id in prev) next[id] = { ...prev[id], selected: true }
      return next
    })
  }, [])

  const clearSelection = useCallback(() => {
    setWells((prev) => {
      const next = {}
      for (const id in prev) next[id] = { ...prev[id], selected: false }
      return next
    })
  }, [])

  // Toggle: if every well in the row is selected → deselect all; else select all.
  const selectRow = useCallback((rowIndex) => {
    setWells((prev) => {
      const ids = Array.from({ length: cols }, (_, c) => String(rowIndex * cols + c))
      const allSelected = ids.every((id) => prev[id].selected)
      const next = { ...prev }
      for (const id of ids) next[id] = { ...next[id], selected: !allSelected }
      return next
    })
  }, [cols])

  // Toggle: if every well in the column is selected → deselect all; else select all.
  const selectCol = useCallback((colIndex) => {
    setWells((prev) => {
      const ids = Array.from({ length: rows }, (_, r) => String(r * cols + colIndex))
      const allSelected = ids.every((id) => prev[id].selected)
      const next = { ...prev }
      for (const id of ids) next[id] = { ...next[id], selected: !allSelected }
      return next
    })
  }, [rows, cols])

  const setWeight = useCallback((id, targetWeight) => {
    setWells((prev) => ({ ...prev, [id]: { ...prev[id], targetWeight } }))
  }, [])

  const setWeightForSelected = useCallback((targetWeight) => {
    setWells((prev) => {
      const next = {}
      for (const id in prev)
        next[id] = prev[id].selected ? { ...prev[id], targetWeight } : prev[id]
      return next
    })
  }, [])

  const setMode = useCallback((id, mode) => {
    setWells((prev) => ({ ...prev, [id]: { ...prev[id], mode } }))
  }, [])

  const setModeForSelected = useCallback((mode) => {
    setWells((prev) => {
      const next = {}
      for (const id in prev)
        next[id] = prev[id].selected ? { ...prev[id], mode } : prev[id]
      return next
    })
  }, [])

  const setCurrentWeight = useCallback((id, currentWeight) => {
    setWells((prev) => ({ ...prev, [id]: { ...prev[id], currentWeight } }))
  }, [])

  // Legacy helper kept for callers that do getSelected()
  const getSelected = useCallback(() => selectedIds, [selectedIds])

  return {
    wells,
    rows,
    cols,
    selectedIds,
    toggleWell,
    selectAll,
    clearSelection,
    selectRow,
    selectCol,
    setWeight,
    setWeightForSelected,
    setMode,
    setModeForSelected,
    setCurrentWeight,
    getSelected,
  }
}

// ---------------------------------------------------------------------------
// Internal sub-components
// ---------------------------------------------------------------------------

// ── Result-variant status colours ────────────────────────────────────────────
// Used when variant === 'result'.  Non-interactive divs — no hover or focus states.
const RESULT_STATUS_CLASS = {
  excluded: 'bg-slate-800 border border-slate-700',
  pending:  'bg-slate-950 border border-slate-800',
  active:   'bg-amber-500 ring-2 ring-amber-400/60',
  complete: 'bg-green-700 border border-green-600',
  error:    'bg-red-800 border border-red-700',
}

/**
 * Format a weight in grams to a compact string that fits inside a well circle.
 * Uses more decimal places for small values so differences are visible.
 */
function fmtWeight(g) {
  if (g == null) return ''
  if (g >= 100) return `${g.toFixed(0)}g`
  if (g >= 10)  return `${g.toFixed(1)}g`
  if (g >= 1)   return `${g.toFixed(2)}g`
  return `${g.toFixed(3)}g`
}

function WellCircle({ id, well, onClick, variant }) {
  // ── Result variant (read-only job display) ────────────────────────────────
  if (variant === 'result') {
    const { status = 'excluded', actualWeight = null, targetWeight = 0, mode = 'none' } = well
    const shoreLabel = SHORE_LABELS[mode] ?? ''

    // Dispensing result: both target and actual weight are available.
    // Show target (dim, small) above actual (bright, larger) so the operator
    // can immediately compare requested vs delivered without a checkmark.
    const isDispensingResult = status === 'complete' && actualWeight !== null && targetWeight > 0

    let innerContent = null
    if (isDispensingResult) {
      innerContent = (
        <div className="flex flex-col items-center leading-tight gap-px">
          <span className="text-[9px] font-medium text-slate-300 select-none">
            {fmtWeight(targetWeight)}
          </span>
          <span className="text-[11px] font-semibold text-white select-none">
            {fmtWeight(actualWeight)}
          </span>
        </div>
      )
    } else if (status === 'complete') {
      const label = actualWeight !== null ? fmtWeight(actualWeight)
                  : shoreLabel           ? shoreLabel
                  : '✓'
      innerContent = (
        <span className="text-xs font-semibold leading-none select-none text-white">
          {label}
        </span>
      )
    } else if (status === 'active') {
      innerContent = (
        <span className="text-xs font-semibold leading-none select-none text-white">···</span>
      )
    }

    return (
      <div className="flex-1 flex items-center justify-center">
        <div
          aria-label={`Well ${id} — ${status}`}
          style={{ aspectRatio: '1' }}
          className={[
            'h-full max-w-full rounded-full flex items-center justify-center',
            status === 'active' ? 'animate-pulse' : '',
            RESULT_STATUS_CLASS[status] ?? RESULT_STATUS_CLASS.excluded,
          ].join(' ')}
        >
          {innerContent}
        </div>
      </div>
    )
  }

  // ── Interactive variants (dispensing / hardness) ──────────────────────────
  const { selected, targetWeight, mode } = well
  const shoreLabel = SHORE_LABELS[mode] ?? ''

  // "Has data" definition per variant:
  //   dispensing → a target weight has been configured
  //   hardness   → a Shore mode has been assigned
  const hasData = variant === 'hardness' ? shoreLabel !== '' : targetWeight > 0

  // ── Inner label ──────────────────────────────────────────────────────────
  // Shown whenever data exists, regardless of selection.
  //   • not selected + data  → white text on dark bg      (19:1 contrast)
  //   • selected + data      → slate-900 text on amber-300 (9.5:1 contrast)
  //   • selected + no data   → no label rendered
  const labelColor = selected ? 'text-slate-900' : 'text-white'
  let innerLabel = null
  if (variant === 'hardness' && shoreLabel) {
    innerLabel = (
      <span className={`text-sm font-bold leading-none pointer-events-none select-none ${labelColor}`}>
        {shoreLabel}
      </span>
    )
  } else if (variant === 'dispensing' && targetWeight > 0) {
    innerLabel = (
      <span className={`text-xs font-semibold leading-none pointer-events-none select-none ${labelColor}`}>
        {targetWeight}g
      </span>
    )
  }

  // ── Background / ring ────────────────────────────────────────────────────
  // Three visual states:
  //   1. Not selected       → near-black, subtle border; white text if label
  //   2. Selected, no data  → darker amber (amber-600); signals "selected but
  //                           not yet configured" — no label needed
  //   3. Selected, has data → brighter amber (amber-300) + dark label; signals
  //                           "ready" — highest-priority state
  // Hover is always one step lighter than the resting state.
  let stateClass
  if (!selected) {
    stateClass = 'bg-slate-900 border-2 border-slate-700 hover:bg-slate-700 hover:border-slate-500'
  } else if (hasData) {
    stateClass = 'bg-amber-300 ring-2 ring-amber-300/50 hover:bg-amber-200'
  } else {
    stateClass = 'bg-amber-400 ring-2 ring-amber-500/40 hover:bg-amber-400'
  }

  return (
    <div className="flex-1 flex items-center justify-center">
      <button
        onClick={() => onClick(id)}
        aria-pressed={selected}
        aria-label={`Well ${id}${selected ? ' selected' : ''}`}
        style={{ aspectRatio: '1' }}
        className={[
          'h-full max-w-full rounded-full',
          'flex items-center justify-center',
          'transition-[background-color,border-color,box-shadow] duration-100',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-white',
          stateClass,
        ].join(' ')}
      >
        {innerLabel}
      </button>
    </div>
  )
}

function AxisButton({ label, onClick, className = '', readOnly = false }) {
  if (readOnly) {
    return (
      <div className={['flex items-center justify-center text-sm font-semibold text-slate-600', className].join(' ')}>
        {label}
      </div>
    )
  }
  return (
    <button
      onClick={onClick}
      className={[
        'flex items-center justify-center',
        'rounded-lg text-sm font-semibold',
        'text-slate-300 hover:bg-slate-700 hover:text-slate-100',
        'transition-colors',
        className,
      ].join(' ')}
    >
      {label}
    </button>
  )
}

// ---------------------------------------------------------------------------
// WellGrid component
// ---------------------------------------------------------------------------

// Height of the column-header row (axis buttons above each column).
const HEADER_H = 'h-8'
// Width of the row-label column (axis buttons left of each row).
const AXIS_W   = 'w-8'

export default function WellGrid({
  wells,
  rows,
  cols,
  toggleWell,
  selectRow,
  selectCol,
  variant = 'dispensing',
  className = '',
}) {
  const readOnly = variant === 'result'

  return (
    // h-full fills whatever space the parent gives; min-h-0 lets it shrink
    // in a flex column without overflowing.
    <div className={['flex flex-col gap-2 h-full w-full min-h-0', className].join(' ')}>

      {/* Column header row */}
      <div className={['flex gap-2 shrink-0', HEADER_H].join(' ')}>
        <div className={[AXIS_W, 'shrink-0'].join(' ')} /> {/* top-left spacer */}
        {Array.from({ length: cols }, (_, c) => (
          <AxisButton
            key={c}
            label={c + 1}
            onClick={() => !readOnly && selectCol(c)}
            readOnly={readOnly}
            className="flex-1 h-full"
          />
        ))}
      </div>

      {/* Data rows — each takes an equal share of remaining height */}
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex gap-2 flex-1 min-h-0">
          <AxisButton
            label={r + 1}
            onClick={() => !readOnly && selectRow(r)}
            readOnly={readOnly}
            className={[AXIS_W, 'h-full shrink-0'].join(' ')}
          />
          {Array.from({ length: cols }, (_, c) => {
            const id = String(r * cols + c)
            return (
              <WellCircle
                key={id}
                id={id}
                well={wells[id]}
                onClick={toggleWell}
                variant={variant}
              />
            )
          })}
        </div>
      ))}

    </div>
  )
}
