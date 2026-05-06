import { Collapsible } from "radix-ui"
import { ChevronDown } from "lucide-react"

import { ResearchInstrumentationDeck } from "@/components/cockpit/research-instrumentation-deck"
import { buttonVariants } from "@/components/ui/button"
import type { PredictionTab } from "@/hooks/use-prediction-tab"
import type { LiveRefreshSnapshot } from "@/lib/types"
import { cn } from "@/lib/utils"

export function LabResearchInstrumentationPanel({
  expanded,
  onExpandedChange,
  liveSnapshot,
  predictionTab,
}: {
  expanded: boolean
  onExpandedChange: (open: boolean) => void
  liveSnapshot: LiveRefreshSnapshot | null
  predictionTab: PredictionTab
}) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <Collapsible.Root open={expanded} onOpenChange={onExpandedChange}>
        <Collapsible.Trigger
          type="button"
          data-slot="button"
          data-testid="lab-board-research-toggle"
          className={cn(
            buttonVariants({ variant: "outline", size: "sm" }),
            "h-auto min-h-8 w-full justify-between gap-2 py-2 font-normal whitespace-normal",
            "text-muted-foreground hover:text-foreground",
          )}
        >
          <span className="min-w-0 flex-1 text-left text-sm font-medium text-foreground">
            Research instrumentation
          </span>
          <span className="text-xs text-muted-foreground">{expanded ? "Hide" : "Show"}</span>
          <ChevronDown
            className={cn("size-4 shrink-0 text-muted-foreground transition-transform", expanded && "rotate-180")}
            aria-hidden
          />
        </Collapsible.Trigger>
        <Collapsible.Content className="min-h-0 overflow-hidden data-[state=open]:mt-1">
          <ResearchInstrumentationDeck
            liveSnapshot={liveSnapshot}
            predictionTab={predictionTab}
            hideTitle
          />
        </Collapsible.Content>
      </Collapsible.Root>
    </div>
  )
}
