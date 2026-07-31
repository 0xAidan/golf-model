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
    <div className="fixed inset-0 z-50 bg-black/60 p-4 sm:p-6" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="ml-auto flex h-full w-full max-w-md flex-col border border-slate-700 bg-[#11151a] shadow-2xl focus-visible:outline-none"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="flex min-h-14 items-center justify-between border-b border-slate-700 px-4">
          <h2 className="text-base font-semibold text-white">{title}</h2>
          <button type="button" className="min-h-11 min-w-11 text-sm text-slate-300 hover:text-white" onClick={onClose} aria-label="Close drawer">
            Close
          </button>
        </header>
        <div className="overflow-y-auto p-4 text-sm text-slate-300">{children}</div>
      </div>
    </div>
  )
}
