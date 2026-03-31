import { useJubileeStore } from '../store/jubileeStore'
import { ProgressBar } from './ui'

const STATE_DOT = {
  idle:         'bg-green-400',
  running:      'bg-amber-400',
  homing:       'bg-amber-400',
  error:        'bg-red-500',
  disconnected: 'bg-slate-600',
}

export default function BottomBar() {
  const wsConnected = useJubileeStore((s) => s.wsConnected)
  const telemetry   = useJubileeStore((s) => s.telemetry)

  const rawState    = telemetry.state ?? 'disconnected'
  const displayState = wsConnected ? rawState : 'disconnected'
  const dot          = STATE_DOT[displayState] ?? 'bg-slate-600'

  const weight = telemetry.weight ?? null
  const job    = telemetry.job    ?? null

  return (
    <div className="flex items-center gap-5 px-6 h-12 bg-slate-950 border-t border-slate-800 shrink-0 text-xs text-slate-500">

      {/* Machine state — shows "disconnected" automatically when WS is down */}
      <span className="flex items-center gap-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
        <span className="uppercase tracking-widest">{displayState}</span>
      </span>

      {/* Live weight */}
      {wsConnected && weight !== null && (
        <>
          <span className="text-slate-800">|</span>
          <span className="font-mono tabular-nums text-slate-400">
            {weight.toFixed(3)} g
          </span>
        </>
      )}

      {/* Job progress — only while a job is running */}
      {job?.running && (
        <>
          <span className="text-slate-800">|</span>
          <ProgressBar
            value={job.total > 0 ? (job.completed / job.total) * 100 : 0}
            label={`${job.job_type ? job.job_type.charAt(0).toUpperCase() + job.job_type.slice(1) : 'Job'} — ${job.completed} / ${job.total}`}
            className="flex-1 min-w-0"
          />
        </>
      )}

    </div>
  )
}
