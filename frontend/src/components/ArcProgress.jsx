/**
 * ArcProgress — semi-circular SVG progress indicator.
 *
 * The arc spans 240° (opens at the bottom with a 120° gap), drawn from the
 * lower-left clockwise through the top to the lower-right.  A filled amber
 * stroke grows clockwise from the start point as value increases from 0→100.
 *
 * Annotations inside the arc:
 *   • Job type label  — small uppercase caption (e.g. "DISPENSING")
 *   • Count           — large "completed / total" figure
 *   • Elapsed time    — "MM:SS" or "HH:MM:SS" beneath the count
 *
 * The SVG uses viewBox="0 0 200 165" and is fully responsive (fills its
 * container width while maintaining aspect ratio).
 *
 * Props
 *   value     0–100    — fill percentage
 *   completed number   — wells / samples completed
 *   total     number   — total wells / samples in the job
 *   elapsed   string   — pre-formatted elapsed string ("02:34")
 *   label     string   — job type label shown above the count
 *   color     string   — CSS colour for the progress stroke (default amber-300)
 *   className string
 */

// Arc geometry constants — all in SVG-user-unit space (viewBox 0 0 200 165)
const CX          = 100    // arc centre x
const CY          = 115    // arc centre y  (lower than midpoint so text fits above)
const R           = 78     // arc path radius (stroke centre-line)
const STROKE_W    = 14     // stroke width in SVG units
const START_DEG   = 150    // clockwise from the positive x-axis (lower-left)
const TOTAL_DEG   = 240    // total arc span in degrees

function polarToXY(cx, cy, r, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

/**
 * Build an SVG arc path string.
 * Draws a clockwise arc starting at startDeg and spanning spanDeg degrees.
 * Clamps the span to (0, 359.99] to avoid degenerate zero-length or full-circle
 * paths which SVG renderers handle inconsistently.
 */
function arcPath(cx, cy, r, startDeg, spanDeg) {
  const clamped = Math.max(0.01, Math.min(spanDeg, 359.99))
  const s = polarToXY(cx, cy, r, startDeg)
  const e = polarToXY(cx, cy, r, startDeg + clamped)
  const large = clamped > 180 ? 1 : 0
  return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`
}

export default function ArcProgress({
  value     = 0,
  completed = 0,
  total     = 0,
  elapsed   = '--:--',
  label     = '',
  color     = '#fcd34d',   // amber-300
  className = '',
}) {
  const pct        = Math.min(100, Math.max(0, value))
  const progressDeg = (pct / 100) * TOTAL_DEG

  const trackD    = arcPath(CX, CY, R, START_DEG, TOTAL_DEG)
  const progressD = pct > 0 ? arcPath(CX, CY, R, START_DEG, progressDeg) : null

  return (
    <div className={['w-full', className].join(' ')}>
      <svg
        viewBox="0 0 200 165"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full"
        aria-label={`Progress: ${completed} of ${total} complete`}
        role="img"
      >
        {/* Track — full 240° arc in dark slate */}
        <path
          d={trackD}
          fill="none"
          stroke="#1e293b"
          strokeWidth={STROKE_W}
          strokeLinecap="round"
        />

        {/* Progress fill — grows clockwise */}
        {progressD && (
          <path
            d={progressD}
            fill="none"
            stroke={color}
            strokeWidth={STROKE_W}
            strokeLinecap="round"
          />
        )}

        {/* Job type label */}
        {label && (
          <text
            x={CX}
            y={CY - 38}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="#64748b"
            fontSize={10}
            fontFamily="inherit"
            letterSpacing={2}
            fontWeight={600}
          >
            {label.toUpperCase()}
          </text>
        )}

        {/* Count — "completed / total" */}
        <text
          x={CX}
          y={CY - 14}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#f8fafc"
          fontSize={26}
          fontFamily="inherit"
          fontWeight={700}
        >
          {completed}
          <tspan fill="#475569" fontSize={18}> / {total}</tspan>
        </text>

        {/* Elapsed time */}
        <text
          x={CX}
          y={CY + 14}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#94a3b8"
          fontSize={13}
          fontFamily="inherit"
          fontWeight={500}
        >
          {elapsed}
        </text>
      </svg>
    </div>
  )
}
