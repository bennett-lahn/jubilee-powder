/**
 * Surface / card primitive.
 *
 * Variants
 *   raised     — default elevated card (slate-800, subtle border)
 *   flat       — flush with parent, no border
 *   highlight  — amber-tinted; used for warnings / active states
 */

const VARIANTS = {
  raised:    'bg-slate-800 border border-slate-700',
  flat:      'bg-slate-800/50',
  highlight: 'bg-jubilee/10 border border-jubilee/30',
}

export default function Card({
  variant = 'raised',
  className = '',
  children,
  ...props
}) {
  return (
    <div
      className={['rounded-2xl', VARIANTS[variant], className].join(' ')}
      {...props}
    >
      {children}
    </div>
  )
}
