import type { ReactNode } from "react"
import { SlidersHorizontal } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { useIsNarrowViewport } from "@/hooks/use-media-query"

export function FilterSheet({
  title = "Filters",
  description,
  children,
  triggerLabel = "Filters",
}: {
  title?: string
  description?: string
  children: ReactNode
  triggerLabel?: string
}) {
  const isNarrow = useIsNarrowViewport()

  if (!isNarrow) {
    return <>{children}</>
  }

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button type="button" variant="outline" size="sm" data-testid="filter-sheet-open">
          <SlidersHorizontal size={14} aria-hidden />
          {triggerLabel}
        </Button>
      </SheetTrigger>
      <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description ? <SheetDescription>{description}</SheetDescription> : null}
        </SheetHeader>
        <div className="stack-col-12 px-4 pb-6">{children}</div>
      </SheetContent>
    </Sheet>
  )
}
