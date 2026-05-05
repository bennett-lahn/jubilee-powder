/**
 * SampleTrayGrid - interactive hardness sample tray visualisation.
 *
 * Samples are rendered as square cells in packed trays. Adjacent samples within
 * a tray are separated only by the black grid line, while trays have visible
 * spacing between them.
 */

import { useCallback, useMemo, useState } from 'react'

const SHORE_LABELS = {
  shore_a:   'A',
  shore_a_d: 'A+D',
  shore_d:   'D',
  none:      '',
}

const RESULT_STATUS_CLASS = {
  excluded: 'bg-slate-800',
  pending:  'bg-slate-950',
  active:   'bg-amber-500',
  complete: 'bg-green-700',
  error:    'bg-red-800',
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

export function useSampleTrayGrid(rows = 5, cols = 5, trayCount = 2) {
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

function SampleCell({ id, sample, onClick, variant }) {
  if (variant === 'result') {
    const { status = 'excluded', mode = 'none' } = sample
    const shoreLabel = SHORE_LABELS[mode] ?? ''

    let innerContent = null
    if (status === 'complete') {
      innerContent = (
        <span className="text-xs font-semibold leading-none select-none text-white">
          {shoreLabel || '✓'}
        </span>
      )
    } else if (status === 'active') {
      innerContent = (
        <span className="text-xs font-semibold leading-none select-none text-white">···</span>
      )
    }

    return (
      <div
        aria-label={`Sample ${id} - ${status}`}
        style={{ aspectRatio: '1' }}
        className={[
          'flex h-full w-full items-center justify-center rounded-none',
          status === 'active' ? 'animate-pulse' : '',
          RESULT_STATUS_CLASS[status] ?? RESULT_STATUS_CLASS.excluded,
        ].join(' ')}
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
    stateClass = 'bg-slate-900 hover:bg-slate-700'
  } else if (hasData) {
    stateClass = 'bg-amber-300 hover:bg-amber-200'
  } else {
    stateClass = 'bg-amber-400 hover:bg-amber-300'
  }

  return (
    <button
      onClick={() => onClick(id)}
      aria-pressed={selected}
      aria-label={`Sample ${id}${selected ? ' selected' : ''}`}
      style={{ aspectRatio: '1' }}
      className={[
        'flex h-full w-full items-center justify-center rounded-none',
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
  variant = 'hardness',
  className = '',
}) {
  return (
    <div className={['flex h-full w-full min-h-0 items-center justify-center gap-8', className].join(' ')}>
      {Array.from({ length: trayCount }, (_, trayIndex) => (
        <div key={trayIndex} className="flex h-full min-w-0 flex-1 flex-col items-center justify-center gap-2">
          <div className="shrink-0 text-xs font-semibold uppercase tracking-widest text-slate-500">
            Tray {trayIndex + 1}
          </div>
          <div
            className="grid aspect-square max-h-full max-w-full bg-black border border-black gap-px"
            style={{
              gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
              gridTemplateRows:    `repeat(${rows}, minmax(0, 1fr))`,
              width:               'min(100%, 100vh)',
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
                    variant={variant}
                  />
                )
              })
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
