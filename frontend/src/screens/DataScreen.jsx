/**
 * Data Browser Screen.
 *
 * Two view states
 * ───────────────
 *   File list   — lists all job log JSON files via GET /api/files.
 *                 Each row shows filename, size, and modification date.
 *   Job result  — clicking a JSON file fetches it via GET /api/files/{filename},
 *                 normalises it, and renders a read-only arc + well grid view
 *                 identical in layout to the HomeScreen completed-job display.
 *                 An "← Back" button in the header returns to the file list.
 */

import { useState, useEffect } from 'react'
import {
  ArrowLeft, FileText, Image, FileSpreadsheet,
  Folder, RefreshCw, FolderOpen,
} from 'lucide-react'
import { Button, Card, StatusBadge } from '../components/ui'
import WellGrid from '../components/WellGrid'
import SampleTrayGrid, { sampleKeyForTray } from '../components/SampleTrayGrid'
import ArcProgress from '../components/ArcProgress'

const DISPENSING_ROWS = 4
const DISPENSING_COLS = 6
const SAMPLE_TRAY_ROWS = 5
const SAMPLE_TRAY_COLS = 5
const SAMPLE_TRAY_COUNT = 2
const HARDNESS_ROWS = SAMPLE_TRAY_ROWS

// ---------------------------------------------------------------------------
// Shared helpers (mirrors of HomeScreen equivalents)
// ---------------------------------------------------------------------------

function formatJobDate(job) {
  if (!job) return null
  const raw = job.date ?? (job.started_at ? job.started_at.slice(0, 10) : null)
  if (!raw) return null
  const [y, m, d] = raw.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

function buildResultWells(rows, cols, job, jobType) {
  const total = rows * cols
  const wells = {}

  if (jobType === 'hardness') {
    for (let trayIndex = 0; trayIndex < SAMPLE_TRAY_COUNT; trayIndex++) {
      for (let sampleIndex = 0; sampleIndex < total; sampleIndex++) {
        const id = sampleKeyForTray(trayIndex, sampleIndex)
        wells[id] = {
          selected: false, targetWeight: 0, currentWeight: 0,
          mode: 'none', status: 'excluded', actualWeight: null,
        }
      }
    }
  } else {
    for (let i = 0; i < total; i++) {
      wells[String(i)] = {
        selected: false, targetWeight: 0, currentWeight: 0,
        mode: 'none', status: 'excluded', actualWeight: null,
      }
    }
  }

  const items = job?.items
  if (!items?.length) return wells

  items.forEach((item, idx) => {
    const id = item.well_id != null
      ? String(item.well_id)
      : sampleKeyForTray(item.tray_index, item.sample_id)
    if (!(id in wells)) return
    let status
    if (item.status) {
      status = item.status
    } else if (idx < (job.completed ?? 0)) {
      status = 'complete'
    } else if (String(job.current_item) === id) {
      status = 'active'
    } else {
      status = 'pending'
    }
    wells[id] = {
      ...wells[id],
      targetWeight: item.target_weight ?? 0,
      actualWeight: item.actual_weight ?? null,
      mode:         item.mode ?? 'none',
      status,
    }
  })
  return wells
}

/**
 * Convert a raw job JSON file to the normalised live-progress shape used by
 * buildResultWells and the arc.
 */
function normalizeFileLog(raw) {
  const meta  = raw?.metadata ?? {}
  const state = raw?.state    ?? {}
  const jobType = meta.job_type ?? ''
  const items   = state.molds ?? state.samples ?? []
  const completed = items.filter((it) => it.status === 'complete').length
  return {
    job_type:   jobType,
    date:       meta.date   ?? null,
    started_at: null,
    status:     meta.outcome ?? 'complete',
    completed,
    total:      items.length,
    error:      null,
    items,
  }
}

// ---------------------------------------------------------------------------
// File-list helpers
// ---------------------------------------------------------------------------

const ICON_MAP = {
  '.csv':  FileSpreadsheet,
  '.json': FileText,
  '.txt':  FileText,
  '.png':  Image,
  '.jpg':  Image,
  '.jpeg': Image,
  '.pdf':  FileText,
  '.xlsx': FileSpreadsheet,
}

function fileIcon(name) {
  if (!name) return FileText
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase()
  return ICON_MAP[ext] ?? FileText
}

function formatSize(bytes) {
  const units = ['B', 'KB', 'MB', 'GB']
  let n = bytes
  for (const u of units) {
    if (n < 1024) return `${n.toFixed(1)} ${u}`
    n /= 1024
  }
  return `${n.toFixed(1)} TB`
}

function formatModified(iso) {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

// ---------------------------------------------------------------------------
// Outcome → badge mapping
// ---------------------------------------------------------------------------

const OUTCOME_BADGE = {
  successful: { status: 'ok',    label: 'Successful' },
  cancelled:  { status: 'warn',  label: 'Cancelled'  },
  aborted:    { status: 'error', label: 'Aborted'    },
}

// ---------------------------------------------------------------------------
// JobResultView — read-only arc + well grid, mirroring HomeScreen layout
// ---------------------------------------------------------------------------

function JobResultView({ job, onBack }) {
  const jobType      = job.job_type ?? ''
  const jobTypeLabel = jobType === 'dispensing' ? 'Dispensing'
                     : jobType === 'hardness'   ? 'Hardness'
                     : 'Job'
  const completed    = job.completed ?? 0
  const total        = job.total     ?? 0
  const pct          = total > 0 ? (completed / total) * 100 : 0
  const jobDate      = formatJobDate(job)
  const badge        = OUTCOME_BADGE[job.status] ?? { status: 'idle', label: job.status ?? 'Unknown' }
  const arcColor     = completed === total && total > 0 ? '#16a34a' : '#334155'
  const resultRows   = jobType === 'hardness' ? HARDNESS_ROWS : DISPENSING_ROWS
  const resultCols   = jobType === 'hardness' ? SAMPLE_TRAY_COLS : DISPENSING_COLS
  const resultWells  = buildResultWells(resultRows, resultCols, job, jobType)
  const unitLabel    = jobType === 'dispensing' ? 'molds' : 'samples'

  return (
    <div className="flex flex-col gap-3 h-full">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <Card className="flex items-center gap-3 p-3 shrink-0">
        <Button variant="ghost" size="sm" onClick={onBack} className="shrink-0">
          <ArrowLeft size={16} className="mr-1" />
          Back
        </Button>
        <div className="w-px h-4 bg-slate-700 shrink-0" />
        <span className="text-slate-300 font-medium">{jobTypeLabel} Job</span>
        {jobDate && (
          <span className="text-slate-500 text-sm">{jobDate}</span>
        )}
        <div className="flex-1" />
        <StatusBadge status={badge.status} label={badge.label} />
      </Card>

      {/* ── Two-column body ──────────────────────────────────────────────── */}
      <div className="flex flex-row gap-3 flex-1 min-h-0">

        {/* Left panel: arc */}
        <Card className="flex flex-col items-center gap-3 p-3 w-48 shrink-0">
          <div className="self-start w-full">
            <p className="text-sm font-semibold text-slate-300 leading-tight">
              {jobTypeLabel} Job
            </p>
            <p className="text-xs text-slate-600 leading-tight">historical record</p>
          </div>
          <ArcProgress
            value={pct}
            completed={completed}
            total={total}
            elapsed="--:--"
            label={jobTypeLabel}
            color={arcColor}
            className="w-full"
          />
        </Card>

        {/* Right panel: well grid */}
        <Card className="flex-1 flex flex-col gap-2 p-4 min-h-0">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 shrink-0">
            Results{jobDate ? ` \u2014 ${jobDate}` : ''}
          </p>
          {jobType === 'hardness' ? (
            <SampleTrayGrid
              samples={resultWells}
              rows={resultRows}
              cols={resultCols}
              toggleSample={() => {}}
              variant="result"
              trayCount={SAMPLE_TRAY_COUNT}
              className="flex-1 min-h-0"
            />
          ) : (
            <WellGrid
              wells={resultWells}
              rows={resultRows}
              cols={resultCols}
              toggleWell={() => {}}
              selectRow={() => {}}
              selectCol={() => {}}
              variant="result"
              className="flex-1 min-h-0"
            />
          )}
        </Card>

      </div>

      {/* ── Status line ──────────────────────────────────────────────────── */}
      <p className="text-center text-sm text-slate-400 shrink-0 pb-1">
        {completed} / {total} {unitLabel} complete
      </p>

    </div>
  )
}

// ---------------------------------------------------------------------------
// DataScreen
// ---------------------------------------------------------------------------

export default function DataScreen() {
  const [files, setFiles]           = useState([])
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)
  const [selectedJob, setSelectedJob] = useState(null)   // null | { loading } | { data, filename }
  const [jobLoadError, setJobLoadError] = useState(null)

  async function loadFiles() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/files')
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      setFiles(await res.json())
    } catch (e) {
      setError(e.message)
      setFiles([])
    } finally {
      setLoading(false)
    }
  }

  async function openFile(filename) {
    setSelectedJob({ loading: true })
    setJobLoadError(null)
    try {
      const res = await fetch(`/api/files/${encodeURIComponent(filename)}`)
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const raw = await res.json()
      setSelectedJob({ data: normalizeFileLog(raw), filename })
    } catch (e) {
      setJobLoadError(e.message)
      setSelectedJob(null)
    }
  }

  useEffect(() => { loadFiles() }, [])

  // ── Job result view ──────────────────────────────────────────────────────
  if (selectedJob?.data) {
    return (
      <JobResultView
        job={selectedJob.data}
        onBack={() => setSelectedJob(null)}
      />
    )
  }

  // ── File list view ───────────────────────────────────────────────────────
  const listLoading = loading || selectedJob?.loading

  return (
    <div className="flex flex-col gap-4 h-full">

      {/* Header toolbar */}
      <Card className="flex items-center gap-4 p-4 shrink-0">
        <FolderOpen size={20} className="text-slate-400" />
        <span className="text-slate-300 font-medium">Data Browser</span>
        <div className="flex-1" />
        {jobLoadError && (
          <span className="text-xs text-red-400 truncate max-w-xs">{jobLoadError}</span>
        )}
        <Button variant="ghost" size="sm" onClick={loadFiles} disabled={listLoading}>
          <RefreshCw size={14} className={['mr-2', listLoading ? 'animate-spin' : ''].join(' ')} />
          Refresh
        </Button>
      </Card>

      {/* File list */}
      <Card className="flex-1 overflow-y-auto p-2">

        {listLoading && (
          <div className="flex items-center justify-center h-full">
            <p className="text-slate-500 text-sm">
              {selectedJob?.loading ? 'Loading job…' : 'Loading files…'}
            </p>
          </div>
        )}

        {!listLoading && error && (
          <div className="flex flex-col items-center justify-center h-full gap-2">
            <StatusBadge status="error" label="Could not load files" />
            <p className="text-xs text-slate-600">{error}</p>
          </div>
        )}

        {!listLoading && !error && files.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <p className="text-slate-500 text-sm">No files in data directory.</p>
          </div>
        )}

        {!listLoading && !error && files.length > 0 && (
          <ul className="divide-y divide-slate-700/50">
            {files.map((f) => {
              const isJson = f.name.endsWith('.json')
              const Icon   = f.type === 'folder' ? Folder : fileIcon(f.name)
              return (
                <li key={f.name}>
                  <button
                    className={[
                      'w-full flex items-center gap-4 px-4 py-3 rounded-xl text-left transition-colors',
                      isJson
                        ? 'hover:bg-slate-700/50 cursor-pointer'
                        : 'cursor-default opacity-60',
                    ].join(' ')}
                    onClick={() => isJson && openFile(f.name)}
                  >
                    <Icon size={20} className="text-slate-400 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-200 truncate">{f.name}</p>
                      {f.type !== 'folder' && (
                        <p className="text-xs text-slate-500">
                          {formatSize(f.size)} &middot; {formatModified(f.modified)}
                        </p>
                      )}
                    </div>
                    {isJson && (
                      <span className="text-xs text-slate-600 shrink-0">View →</span>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        )}

      </Card>
    </div>
  )
}
