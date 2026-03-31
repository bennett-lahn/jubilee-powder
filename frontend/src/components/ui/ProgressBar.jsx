/**
 * Linear progress bar primitive.
 *
 * Props
 *   value    number  — 0–100
 *   label    string  — optional text above the bar
 *   color    string  — CSS color value for the fill (default green-500)
 */

export default function ProgressBar({
  value = 0,
  label,
  color = '#22c55e',   // green-500 — explicit CSS value so the fill always renders
  className = '',
}) {
  const clamped = Math.min(100, Math.max(0, value))

  return (
    <div className={['flex flex-col gap-1.5 w-full', className].join(' ')}>
      {label && (
        <span className="text-xs text-slate-400">{label}</span>
      )}

      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          style={{ width: `${clamped}%`, backgroundColor: color }}
          className="h-full rounded-full transition-all duration-300"
          role="progressbar"
          aria-valuenow={clamped}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
    </div>
  )
}
