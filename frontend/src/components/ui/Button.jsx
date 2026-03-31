/**
 * Kiosk-grade button primitive.
 *
 * Text sizes are intentionally large relative to button height so the label
 * fills most of the button face — important for readability at kiosk distances.
 *
 * Variants
 *   filled   — bright amber fill, dark text; primary actions (Start Job, Connect)
 *   outlined — amber border + text on transparent bg; secondary actions
 *   ghost    — no background, light text; tertiary / deselect actions
 *   danger   — vivid red fill, white text; destructive actions (Disconnect, Stop)
 *
 * Disabled state uses opacity + transition so the shift from dim→vivid as
 * validation criteria are met is clearly animated.
 */

const VARIANTS = {
  // Base is amber-300 (light) so the resting button is clearly visible against
  // the dark kiosk background. Hover moves to amber-200 (even lighter).
  filled:   'bg-amber-300 text-slate-900 hover:bg-amber-200 active:bg-amber-400',

  outlined: 'border border-jubilee text-jubilee hover:bg-jubilee/15 active:bg-jubilee/25',

  // slate-200 ensures ghost buttons are legible against slate-800/900 surfaces
  // and clearly distinct from the opacity-40 disabled state.
  ghost:    'text-slate-200 hover:bg-slate-700/70 hover:text-white active:bg-slate-600',

  // red-600 (not red-700) so the resting state is vivid rather than muddy.
  danger:   'bg-red-600 text-white hover:bg-red-500 active:bg-red-700',
}

// Text is one step larger than a "standard" mapping so the label visually
// fills the button face rather than floating in a sea of padding.
const SIZES = {
  sm: 'h-10 px-4 text-base  font-semibold rounded-xl',
  md: 'h-12 px-6 text-lg   font-semibold rounded-xl',
  lg: 'h-14 px-8 text-xl   font-semibold rounded-xl',
}

export default function Button({
  variant = 'filled',
  size = 'md',
  disabled = false,
  className = '',
  children,
  ...props
}) {
  return (
    <button
      disabled={disabled}
      className={[
        'inline-flex items-center justify-center tracking-wide select-none',
        'transition-[background-color,color,border-color,opacity] duration-150',
        'disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none',
        VARIANTS[variant],
        SIZES[size],
        className,
      ].join(' ')}
      {...props}
    >
      {children}
    </button>
  )
}
