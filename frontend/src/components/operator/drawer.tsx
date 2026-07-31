import { useEffect, useRef, type ReactNode } from "react"

export function Drawer({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean
  title: string
  children: ReactNode
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const openerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialogRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => {
      window.removeEventListener("keydown", handleKeyDown)
      openerRef.current?.focus()
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="operator-app fixed inset-0 z-50 flex bg-black/65 backdrop-blur-sm" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="ml-auto flex h-full w-full max-w-md flex-col border-l border-[var(--op-border-strong)] bg-[var(--op-surface)] shadow-2xl focus-visible:outline-none"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="flex min-h-14 items-center justify-between border-b border-[var(--op-border)] px-5">
          <h2 className="text-base font-semibold text-white">{title}</h2>
          <button
            type="button"
            className="op-focus flex h-9 w-9 items-center justify-center rounded-lg text-[var(--op-text-secondary)] transition-colors hover:bg-[var(--op-surface-3)] hover:text-white"
            onClick={onClose}
            aria-label="Close details"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true" className="h-5 w-5">
              <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round" />
            </svg>
          </button>
        </header>
        <div className="overflow-y-auto p-5 text-sm text-[var(--op-text-secondary)]">{children}</div>
      </div>
    </div>
  )
}
