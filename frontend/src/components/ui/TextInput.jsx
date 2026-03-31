/**
 * Labelled text / number input primitive.
 *
 * Designed for kiosk use:
 *   - Tall touch target (h-12)
 *   - High-contrast placeholder text
 *   - Clear disabled visual state
 *   - Optional inline right-side unit label (e.g. "g" for grams)
 */

export default function TextInput({
  label,
  hint,
  unit,
  value,
  onChange,
  disabled = false,
  type = 'text',
  placeholder = '',
  className = '',
  inputClassName = '',
  ...props
}) {
  return (
    <div className={['flex flex-col gap-1', className].join(' ')}>
      {label && (
        <label className="text-xs font-medium uppercase tracking-widest text-slate-400">
          {label}
        </label>
      )}

      <div className="relative flex items-center">
        <input
          type={type}
          value={value}
          onChange={(e) => onChange?.(e.target.value)}
          disabled={disabled}
          placeholder={placeholder}
          className={[
            'w-full h-12 bg-slate-900 border border-slate-600 rounded-xl px-4',
            'text-slate-100 placeholder-slate-600 text-sm',
            'focus:outline-none focus:border-jubilee focus:ring-1 focus:ring-jubilee/40',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            unit ? 'pr-12' : '',
            inputClassName,
          ].join(' ')}
          {...props}
        />
        {unit && (
          <span className="absolute right-4 text-slate-500 text-sm pointer-events-none">
            {unit}
          </span>
        )}
      </div>

      {hint && (
        <p className="text-xs text-slate-500">{hint}</p>
      )}
    </div>
  )
}
