/**
 * Home Screen.
 *
 * Acts as the primary "job dashboard" — either showing a live running job or
 * a summary of the most recently completed one.
 *
 * Layout
 * ──────
 *   Left panel (fixed width)
 *     • Small ArcProgress — compact overview, secondary element
 *     • Cancel button     — small, graceful stop after current mold
 *     • Abort button      — larger danger button; one press sends emergency stop
 *   Right panel (flex-1)
 *     • WellGrid in 'result' variant — the primary display element
 *   Status line at the very bottom
 *
 * States
 * ──────
 *   idle / no data   — placeholder card prompting the user to start a job
 *   job running      — live telemetry drives the arc and well colours
 *   job finished     — arc locked at final %, wells show completion colours
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useJubileeStore } from '../store/jubileeStore'
import WellGrid from '../components/WellGrid'
import SampleTrayGrid, { sampleKeyForTray } from '../components/SampleTrayGrid'
import ArcProgress from '../components/ArcProgress'
import { Button, Card, Dialog } from '../components/ui'
import {
  DISPENSING_LAYOUT,
  DISPENSING_ROWS,
  DISPENSING_COLS,
} from '../constants/dispensingBed'


const SAMPLE_TRAY_ROWS = 5
const SAMPLE_TRAY_COLS = 7
const SAMPLE_TRAY_COUNT = 2
const HARDNESS_ROWS = SAMPLE_TRAY_ROWS

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Return a short date string for the results heading, e.g. "Mar 31, 2026".
 * Accepts a job object that may carry either a `date` field (YYYY-MM-DD, from
 * a persisted log file) or a `started_at` field (ISO-8601, from live progress).
 */
function formatJobDate(job) {
  if (!job) return null
  const raw = job.date ?? (job.started_at ? job.started_at.slice(0, 10) : null)
  if (!raw) return null
  // Parse as local midnight so the displayed day matches the job date.
  const [y, m, d] = raw.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

/** Format an integer number of seconds as "MM:SS" or "H:MM:SS". */
function formatElapsed(totalSeconds) {
  const s = totalSeconds % 60
  const m = Math.floor(totalSeconds / 60) % 60
  const h = Math.floor(totalSeconds / 3600)
  const pad = (n) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

/**
 * Build a `wells` map for WellGrid from a job progress object.
 *
 * All ROWS×COLS wells are initialised as `excluded`.  Wells present in
 * `job.items` are marked pending / active / complete based on the current
 * `job.completed` counter and `job.current_item`.
 */
function buildResultWells(rows, cols, job, jobType) {
  const wells = {}

  if (jobType === 'hardness') {
    const total = rows * cols
    for (let trayIndex = 0; trayIndex < SAMPLE_TRAY_COUNT; trayIndex++) {
      for (let sampleIndex = 0; sampleIndex < total; sampleIndex++) {
        const id = sampleKeyForTray(trayIndex, sampleIndex)
        wells[id] = {
          selected:      false,
          targetWeight:  0,
          currentWeight: 0,
          mode:          'none',
          status:        'excluded',
          actualWeight:  null,
          result:        null,
          resultShoreA:  null,
          resultShoreD:  null,
          sampleError:   null,
        }
      }
    }
  } else {
    // Use physical layout to init only real mold positions (skip scale placeholders).
    DISPENSING_LAYOUT.flat().filter((id) => id !== null).forEach((id) => {
      wells[String(id)] = {
        selected:      false,
        targetWeight:  0,
        currentWeight: 0,
        mode:          'none',
        status:        'excluded',
        actualWeight:  null,
        result:        null,
        resultShoreA:  null,
        resultShoreD:  null,
        sampleError:   null,
      }
    })
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
    } else if (item.sample_error) {
      status = 'error'
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
      result:       item.result ?? null,
      resultShoreA: item.result_shore_a ?? null,
      resultShoreD: item.result_shore_d ?? null,
      sampleError:  item.sample_error ?? null,
      mode:         item.mode ?? 'none',
      status,
    }
  })

  return wells
}

// ---------------------------------------------------------------------------
// HomeScreen
// ---------------------------------------------------------------------------

export default function HomeScreen() {
  const telemetry   = useJubileeStore((s) => s.telemetry)
  const cancelJob   = useJubileeStore((s) => s.cancelJob)
  const abortJob    = useJubileeStore((s) => s.abortJob)
  const clearJam    = useJubileeStore((s) => s.clearJam)
  const fetchJobLog = useJubileeStore((s) => s.fetchJobLog)
  const jobLog      = useJubileeStore((s) => s.jobLog)

  const job = telemetry.job

  // ── Fetch job log on mount + after a job finishes ────────────────────────
  const prevRunning = useRef(false)
  useEffect(() => { fetchJobLog() }, [])
  useEffect(() => {
    const running = job?.running ?? false
    if (prevRunning.current && !running) fetchJobLog()
    prevRunning.current = running
  }, [job?.running])

  // ── Elapsed time counter ─────────────────────────────────────────────────
  const [elapsedSec, setElapsedSec] = useState(0)
  const timerRef = useRef(null)

  useEffect(() => {
    if (job?.running && job.started_at) {
      const startMs = new Date(job.started_at).getTime()
      setElapsedSec(Math.max(0, Math.floor((Date.now() - startMs) / 1000)))
      timerRef.current = setInterval(() => {
        setElapsedSec(Math.max(0, Math.floor((Date.now() - startMs) / 1000)))
      }, 1000)
    } else {
      clearInterval(timerRef.current)
      timerRef.current = null
      if (!job?.running) setElapsedSec(0)
    }
    return () => clearInterval(timerRef.current)
  }, [job?.running, job?.started_at])

  // ── Cancel confirmation dialog ───────────────────────────────────────────
  const [cancelOpen, setCancelOpen] = useState(false)

  // ── Jam intervention ─────────────────────────────────────────────────────
  const jamDetected = (telemetry.state === 'running') && (job?.jam_detected ?? false)
  const jamWellId   = job?.jam_well_id ?? null
  const [jamClearing, setJamClearing] = useState(false)

  const handleClearJam = useCallback(async () => {
    setJamClearing(true)
    await clearJam()
    setJamClearing(false)
  }, [clearJam])

  const [actionStatus, setActionStatus] = useState('')

  const handleAbortClick = useCallback(async () => {
    setActionStatus('Aborting…')
    const { ok, error } = await abortJob()
    setActionStatus(ok
      ? 'Emergency stop sent — machine is in ERROR state.'
      : `Abort error: ${error}`)
  }, [abortJob])

  async function handleCancelConfirm() {
    setCancelOpen(false)
    const itemName = jobType === 'hardness' ? 'sample' : 'mold'
    setActionStatus(`Cancelling after current ${itemName}...`)
    const { ok, error } = await cancelJob()
    setActionStatus(ok
      ? `Cancelling - machine will stop after the current ${itemName}.`
      : `Error: ${error}`)
  }

  // ── Derived display values ───────────────────────────────────────────────
  const isRunning    = job?.running ?? false
  const hasJobData   = (job?.total ?? 0) > 0
  const jobType      = job?.job_type ?? jobLog?.job_type ?? null
  const jobTypeLabel = jobType === 'dispensing' ? 'Dispensing'
                     : jobType === 'hardness'   ? 'Hardness'
                     : 'Job'
  const itemName = jobType === 'hardness' ? 'sample' : 'mold'
  const itemNamePlural = jobType === 'hardness' ? 'samples' : 'molds'

  const displayJob = hasJobData ? job : jobLog
  const completed  = displayJob?.completed ?? 0
  const total      = displayJob?.total     ?? 0
  const pct        = total > 0 ? (completed / total) * 100 : 0

  const arcColor = isRunning
    ? '#fcd34d'   // amber-300
    : total > 0 && completed === total
      ? '#16a34a' // green-600
      : '#334155' // slate-700

  const resultRows = jobType === 'hardness' ? HARDNESS_ROWS : DISPENSING_ROWS
  const resultCols = jobType === 'hardness' ? SAMPLE_TRAY_COLS : DISPENSING_COLS
  const resultWells = buildResultWells(resultRows, resultCols, displayJob, jobType)
  const jobDate     = formatJobDate(displayJob)

  // Most recent hardness reading image for the live feed.
  const liveImageUrl = jobType === 'hardness'
    ? (() => {
        const items = displayJob?.items ?? []
        for (let i = items.length - 1; i >= 0; i--) {
          const url = items[i]?.image_path_shore_a ?? items[i]?.image_path_shore_d
          if (url) return url
        }
        return null
      })()
    : null

  // ── Empty state ──────────────────────────────────────────────────────────
  if (!hasJobData && !jobLog) {
    return (
      <div className="flex flex-col gap-3 h-full">
        <Card className="flex items-center py-2 px-3 shrink-0">
          <span className="font-semibold text-slate-300">Home</span>
        </Card>
        <Card className="flex-1 flex flex-col items-center justify-center gap-2">
          <span className="text-slate-400 text-lg font-medium">No active job</span>
          <span className="text-slate-600 text-sm">
            Start a job from Dispensing or Hardness Testing
          </span>
        </Card>
      </div>
    )
  }

  // ── Main job dashboard ───────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-3 h-full">

      {/* ── Two-column body ──────────────────────────────────────────────── */}
      <div className="flex flex-row gap-3 flex-1 min-h-0">

        {/* ── Left panel: compact arc + action buttons ─────────────────── */}
        <Card className="flex flex-col items-center gap-3 p-3 w-48 shrink-0">

          {/* Job title */}
          <div className="self-start w-full">
            <p className="text-sm font-semibold text-slate-300 leading-tight">
              {jobTypeLabel} Job
            </p>
            {!isRunning && total > 0 && (
              <p className="text-xs text-slate-600 leading-tight">last run</p>
            )}
          </div>

          {/* Compact arc — fills the panel width */}
          <ArcProgress
            value={pct}
            completed={completed}
            total={total}
            elapsed={isRunning ? formatElapsed(elapsedSec) : '--:--'}
            label={jobTypeLabel}
            color={arcColor}
            className="w-full"
          />

          <div className="flex-1" />

          {/* Action buttons — only visible while a job is running */}
          {isRunning && (
            <div className="flex flex-col gap-2 w-full">

              {/* Cancel: small, graceful — confirmed via dialog */}
              <Button
                size="sm"
                variant="outlined"
                onClick={() => setCancelOpen(true)}
                className="w-full"
              >
                Cancel
              </Button>

              <Button
                size="md"
                variant="danger"
                onClick={handleAbortClick}
                className="w-full"
              >
                Abort
              </Button>

            </div>
          )}

          {/* Live reading image — shown for hardness jobs when an image is available */}
          {liveImageUrl && (
            <div className="w-full flex flex-col gap-1">
              <p className="text-[10px] uppercase tracking-widest text-slate-500 select-none">
                Live reading
              </p>
              <img
                src={liveImageUrl}
                alt="LCD display reading"
                className="w-full rounded object-contain bg-slate-950"
              />
            </div>
          )}
        </Card>

        {/* ── Right panel: well result grid (primary content) ──────────── */}
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
              physicalLayout={DISPENSING_LAYOUT}
            />
          )}
        </Card>

      </div>

      {/* ── Status line ──────────────────────────────────────────────────── */}
      <p className="text-center text-sm text-slate-400 shrink-0 pb-1">
        {actionStatus || (isRunning
          ? `${jobTypeLabel} job running - ${completed} of ${total} ${itemNamePlural} complete.`
          : total > 0
            ? `Last job: ${completed} / ${total} ${itemNamePlural} complete.`
            : ''
        )}
      </p>

      {/* ── Cancel confirmation dialog ────────────────────────────────────── */}
      <Dialog
        open={cancelOpen}
        title="Cancel Job"
        onClose={() => setCancelOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCancelOpen(false)}>
              Go Back
            </Button>
            <Button variant="outlined" onClick={handleCancelConfirm}>
              Confirm Cancel
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-300 mb-2">
          The machine will finish the <span className="font-semibold text-slate-100">current {itemName}</span>, then
          stop and stow the tool.
        </p>
        <p className="text-sm text-slate-500">
          The machine will return to idle and be ready for a new job.
        </p>
      </Dialog>

      {/* ── Jam intervention dialog ───────────────────────────────────────── */}
      <Dialog
        open={jamDetected}
        title="Powder Flow Jam"
        footer={
          <Button
            variant="outlined"
            onClick={handleClearJam}
            disabled={jamClearing}
          >
            {jamClearing ? 'Resuming...' : 'Blockage Cleared - Resume'}
          </Button>
        }
      >
        <p className="text-sm text-slate-300 mb-2">
          Powder flow has stalled{jamWellId != null
            ? <> on well <span className="font-semibold text-slate-100">{jamWellId}</span></>
            : null
          }.
        </p>
        <p className="text-sm text-slate-400 mb-2">
          Clear the blockage in the trickler hopper, then press the button below
          to resume dispensing.
        </p>
        <p className="text-xs text-slate-500">
          To abandon this job entirely, use the Cancel or Abort buttons instead.
        </p>
      </Dialog>

    </div>
  )
}
