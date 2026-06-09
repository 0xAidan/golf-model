import type { ReactNode } from "react"

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"

export const PlayerInsightDrawer = ({
  open,
  onOpenChange,
  playerName,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  playerName?: string
  children: ReactNode
}) => (
  <Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent
      side="right"
      className="player-insight-drawer flex w-full flex-col gap-0 p-0 sm:max-w-md"
      data-testid="player-insight-drawer"
    >
      <SheetHeader className="border-b border-[var(--border)] px-5 py-4 text-left">
        <SheetTitle className="font-display text-lg">
          {playerName ?? "Player insight"}
        </SheetTitle>
        <SheetDescription className="text-sm text-[var(--text-secondary)]">
          Model signals, linked picks, and profile context for this player.
        </SheetDescription>
      </SheetHeader>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
    </SheetContent>
  </Sheet>
)
