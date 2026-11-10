import { useEffect, useRef } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode, RefObject } from 'react'
import './Sheet.css'

export function Sheet({
  open,
  onClose,
  labelledBy,
  describedBy,
  className,
  id,
  returnFocusTo,
  children,
}: {
  open: boolean
  onClose: () => void
  labelledBy: string
  describedBy?: string
  className: string
  id?: string
  returnFocusTo?: RefObject<HTMLElement | null>
  children: ReactNode
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)
  const parentCloseRef = useRef(false)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      dialog.showModal()
      dialog.querySelector<HTMLElement>('[data-sheet-autofocus]')?.focus()
    } else if (!open && dialog.open) {
      parentCloseRef.current = true
      dialog.close()
    }
  }, [open])

  useEffect(() => () => {
    const dialog = dialogRef.current
    if (dialog?.open) dialog.close()
  }, [])

  const restoreFocus = () => {
    const target = returnFocusTo?.current ?? returnFocusRef.current
    returnFocusRef.current = null
    requestAnimationFrame(() => target?.focus())
  }

  const trapTab = (event: ReactKeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== 'Tab') return
    const focusable = [...(dialogRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])') ?? [])]
      .filter((item) => item.getAttribute('aria-hidden') !== 'true')
    if (focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <dialog
      ref={dialogRef}
      id={id}
      className={`sheet-dialog ${className}`}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      onClose={() => {
        if (!parentCloseRef.current) onClose()
        parentCloseRef.current = false
        restoreFocus()
      }}
      onKeyDown={trapTab}
      onClick={(event) => {
        if (event.target === event.currentTarget) dialogRef.current?.close()
      }}
    >
      {children}
    </dialog>
  )
}
