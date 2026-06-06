/**
 * SampleTrayGrid - interactive hardness sample tray visualisation.
 *
 * Samples are rendered as square cells in packed trays. Adjacent samples within
 * a tray are separated only by the black grid line, while trays have visible
 * spacing between them.
 */

import { useCallback, useMemo, useState } from 'react'
import {
  HARDNESS_ROWS,
  HARDNESS_COLS,
  HARDNESS_TRAY_COUNT,
} from '../constants/hardnessTray'

const SHORE_LABELS = {
  shore_a:   'A',
  shore_a_d: 'A+D',
  shore_d:   'D',
  none:      '',
}

const RESULT_STATUS_CLASS = {
  excluded:   'bg-slate-950 border border-slate-800',
  incomplete: 'bg-sky-900 border border-sky-700',
  active:     'bg-amber-500 border border-amber-400',
  complete:   'bg-green-700 border border-green-600',
  error:      'bg-red-800 border border-red-700',
}

function formatHardnessValue(value) {
  return Number.isFinite(value) ? value.toFixed(1) : '—'
}

/** Per-pass hardness values; A and D render on separate lines for shore_a_d. */
function HardnessResultLines({ mode, resultShoreA, resultShoreD }) {
  const lineClass = 'text-[9px] font-semibold whitespace-nowrap leading-none'

  if (mode === 'shore_a_d') {
    return (
      <>
        <span className={lineClass}>A {formatHardnessValue(resultShoreA)}</span>
        <span className={lineClass}>D {formatHardnessValue(resultShoreD)}</span>
      </>
    )
  }
  if (mode === 'shore_a') {
    return <span className={lineClass}>{formatHardnessValue(resultShoreA)}</span>
  }
  if (mode === 'shore_d') {
    return <span className={lineClass}>{formatHardnessValue(resultShoreD)}</span>
  }
  return <span className={lineClass}>—</span>
}

export function sampleKeyForTray(trayIndex, sampleId) {
  return `${trayIndex}:${sampleId}`
}

function initSamples(rows, cols, trayCount) {
  const samples = {}
  const trayCapacity = rows * cols
  for (let trayIndex = 0; trayIndex < trayCount; trayIndex++) {
    for (let sampleIndex = 0; sampleIndex < trayCapacity; sampleIndex++) {
      const id = sampleKeyForTray(trayIndex, sampleIndex)
      samples[id] = {
        selected: false,
        mode: 'none',
      }
    }
  }
  return samples
}

export function useSampleTrayGrid(
  rows = HARDNESS_ROWS,
  cols = HARDNESS_COLS,
  trayCount = HARDNESS_TRAY_COUNT,
) {
  const [samples, setSamples] = useState(() => initSamples(rows, cols, trayCount))

  const selectedIds = useMemo(
    () => Object.entries(samples).filter(([, sample]) => sample.selected).map(([id]) => id),
    [samples],
  )

  const toggleSample = useCallback((id) => {
    setSamples((prev) => ({
      ...prev,
      [id]: { ...prev[id], selected: !prev[id].selected },
    }))
  }, [])

  const selectAll = useCallback(() => {
    setSamples((prev) => {
      const next = {}
      for (const id in prev) next[id] = { ...prev[id], selected: true }
      return next
    })
  }, [])

  const clearSelection = useCallback(() => {
    setSamples((prev) => {
      const next = {}
      for (const id in prev) next[id] = { ...prev[id], selected: false }
      return next
    })
  }, [])

  const setModeForSelected = useCallback((mode) => {
    setSamples((prev) => {
      const next = {}
      for (const id in prev) {
        next[id] = prev[id].selected ? { ...prev[id], mode } : prev[id]
      }
      return next
    })
  }, [])

  return {
    samples,
    rows,
    cols,
    trayCount,
    selectedIds,
    toggleSample,
    selectAll,
    clearSelection,
    setModeForSelected,
  }
}

function SampleCell({ id, sample, onClick, onSampleClick, variant }) {
  if (variant === 'result') {
    const {
      status = 'excluded',
      mode = 'none',
      result = null,
      resultShoreA = null,
      resultShoreD = null,
      sampleError = null,
    } = sample
    const shoreLabel = SHORE_LABELS[mode] ?? ''
    const isClickable = !!onSampleClick && (status === 'complete' || status === 'error')

    let innerContent = null
    if (status === 'complete' || status === 'incomplete') {
      innerContent = (
        <div className="flex flex-col items-center justify-center leading-none select-none text-white gap-0.5">
          <HardnessResultLines mode={mode} resultShoreA={resultShoreA} resultShoreD={resultShoreD} />
          <span className="text-[9px] uppercase tracking-wide opacity-70">
            {status === 'incomplete' ? 'PARTIAL' : (shoreLabel || 'OK')}
          </span>
        </div>
      )
    } else if (status === 'error') {
      innerContent = (
        <div className="flex flex-col items-center justify-center leading-none select-none text-white">
          <span className="text-[11px] font-semibold">N/A</span>
          <span className="text-[9px] uppercase tracking-wide opacity-70">
            {shoreLabel || 'ERR'}
          </span>
        </div>
      )
    } else if (status === 'active') {
      innerContent = (
        <div className="flex flex-col items-center justify-center leading-none select-none text-white">
          <HardnessResultLines mode={mode} resultShoreA={resultShoreA} resultShoreD={resultShoreD} />
        </div>
      )
    }

    const cellClass = [
      'flex h-full w-full items-center justify-center rounded-none box-border',
      status === 'active' ? 'animate-pulse' : '',
      isClickable ? 'cursor-pointer hover:brightness-125 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white' : '',
      RESULT_STATUS_CLASS[status] ?? RESULT_STATUS_CLASS.excluded,
    ].join(' ')

    if (isClickable) {
      return (
        <button
          aria-label={`Sample ${id} - ${status}${sampleError ? ` (${sampleError})` : ''} — click to view image`}
          style={{ aspectRatio: '1' }}
          className={cellClass}
          onClick={() => onSampleClick(id)}
        >
          {innerContent}
        </button>
      )
    }

    return (
      <div
        aria-label={`Sample ${id} - ${status}${sampleError ? ` (${sampleError})` : ''}`}
        style={{ aspectRatio: '1' }}
        className={cellClass}
      >
        {innerContent}
      </div>
    )
  }

  const { selected, mode } = sample
  const shoreLabel = SHORE_LABELS[mode] ?? ''
  const hasData = shoreLabel !== ''
  const labelColor = selected ? 'text-slate-900' : 'text-white'

  let stateClass
  if (!selected) {
    stateClass = 'bg-slate-950 border border-slate-700 hover:bg-slate-800 hover:border-slate-500'
  } else if (hasData) {
    stateClass = 'bg-amber-300 border border-amber-200 hover:bg-amber-200'
  } else {
    stateClass = 'bg-amber-500 border border-amber-400 hover:bg-amber-400'
  }

  return (
    <button
      onClick={() => onClick(id)}
      aria-pressed={selected}
      aria-label={`Sample ${id}${selected ? ' selected' : ''}`}
      style={{ aspectRatio: '1' }}
      className={[
        'flex h-full w-full items-center justify-center rounded-none box-border',
        'transition-[background-color,border-color,box-shadow] duration-100',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white',
        stateClass,
      ].join(' ')}
    >
      {shoreLabel && (
        <span className={`text-sm font-bold leading-none pointer-events-none select-none ${labelColor}`}>
          {shoreLabel}
        </span>
      )}
    </button>
  )
}

export default function SampleTrayGrid({
  samples,
  rows,
  cols,
  trayCount = 2,
  toggleSample,
  onSampleClick,
  variant = 'hardness',
  className = '',
}) {
  return (
    <div className={['flex flex-col h-full w-full min-h-0', className].join(' ')}>

      {/* Tray grids — side by side, filling available height */}
      <div className="flex flex-1 min-h-0 items-center justify-center gap-8">
        {Array.from({ length: trayCount }, (_, trayIndex) => (
          <div key={trayIndex} className="flex h-full min-w-0 flex-1 flex-col items-center justify-center gap-2">
            <div className="shrink-0 text-xs font-semibold uppercase tracking-widest text-slate-500">
              Tray {trayIndex + 1}
            </div>
            <div
              className="grid max-h-full max-w-full bg-black border border-black gap-px"
              style={{
                gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
                gridTemplateRows:    `repeat(${rows}, minmax(0, 1fr))`,
                aspectRatio:         `${cols} / ${rows}`,
                width:               `min(100%, calc(100vh * ${cols} / ${rows}))`,
              }}
            >
              {Array.from({ length: rows }, (_, r) => (
                Array.from({ length: cols }, (_, c) => {
                  const sampleId = r * cols + c
                  const id = sampleKeyForTray(trayIndex, sampleId)
                  return (
                    <SampleCell
                      key={id}
                      id={id}
                      sample={samples[id] ?? { selected: false, mode: 'none', status: 'excluded' }}
                      onClick={toggleSample}
                      onSampleClick={onSampleClick}
                      variant={variant}
                    />
                  )
                })
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Trickler indicator — down arrow at the physical bottom of the testing bed */}
      <div className="flex shrink-0 items-center justify-center gap-2 mt-3 pb-1">
        <svg
          width="10" height="8" viewBox="0 0 10 8"
          className="fill-slate-500 shrink-0"
          aria-hidden="true"
        >
          <polygon points="5,8 0,0 10,0" />
        </svg>
        <span className="text-[10px] text-slate-500 uppercase tracking-wider select-none">
          trickler
        </span>
      </div>

    </div>
  )
}
