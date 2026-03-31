/**
 * Inline status badge — coloured dot + label.
 *
 * status values
 *   ok    green dot  — connected, running, ready
 *   error red dot    — disconnected, failed
 *   warn  amber dot  — warning, in-progress
 *   idle  grey dot   — standby, not configured
 */

const DOT = {
  ok:    'bg-green-400',
  error: 'bg-red-500',
  warn:  'bg-jubilee',
  idle:  'bg-slate-600',
}

const TEXT = {
  ok:    'text-green-400',
  error: 'text-red-400',
  warn:  'text-jubilee',
  idle:  'text-slate-500',
}

export default function StatusBadge({ status = 'idle', label, className = '' }) {
  return (
    <span className={['inline-flex items-center gap-2', className].join(' ')}>
      <span className={['h-2 w-2 rounded-full shrink-0', DOT[status]].join(' ')} />
      <span className={['text-sm', TEXT[status]].join(' ')}>{label}</span>
    </span>
  )
}
