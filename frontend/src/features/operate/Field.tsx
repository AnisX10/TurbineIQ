import { useId } from 'react'
import type { ReactNode } from 'react'

/** A labelled form control with an optional hint or error, wired for screen readers. */
export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: (ids: { id: string; describedBy?: string }) => ReactNode }) {
  const id = useId()
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined
  return (
    <div className="operate-field">
      <label htmlFor={id}>{label}</label>
      {children({ id, describedBy })}
      {error ? <small id={`${id}-error`} className="operate-field-error" role="alert">{error}</small>
        : hint ? <small id={`${id}-hint`}>{hint}</small> : null}
    </div>
  )
}
