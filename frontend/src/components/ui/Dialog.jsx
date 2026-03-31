/**
 * Modal dialog primitive using a React portal.
 *
 * Renders into document.body so it always sits above the kiosk layout.
 * Backdrop click is intentionally disabled — kiosk dialogs require an
 * explicit button press to dismiss to prevent accidental closes on touch.
 *
 * Props
 *   open      boolean  — controls visibility
 *   title     string   — headline text
 *   onClose   fn       — called when the dialog should close
 *   children  node     — dialog body content
 *   footer    node     — action buttons row (optional, renders at bottom)
 *   width     string   — Tailwind max-w class (default 'max-w-md')
 */

import { useEffect } from 'react'
import { createPortal } from 'react-dom'

export default function Dialog({
  open,
  title,
  onClose,
  children,
  footer,
  width = 'max-w-md',
}) {
  // Close on Escape for accessibility (kiosk may have a keyboard attached).
  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      aria-modal="true"
      role="dialog"
      aria-label={title}
    >
      <div className={['bg-slate-800 border border-slate-700 rounded-2xl w-full mx-6 overflow-hidden', width].join(' ')}>
        {/* Header */}
        {title && (
          <div className="px-6 pt-6 pb-4 border-b border-slate-700">
            <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
          </div>
        )}

        {/* Body */}
        <div className="px-6 py-5">
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div className="px-6 pb-6 flex items-center justify-end gap-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}
