import { Filter } from "lucide-react"

import type { PredictionTab } from "@/hooks/use-prediction-tab"

export const ModelFilterToolbar = ({
  predictionTab,
  selectedBooks,
  matchupSearch,
  minEdge,
}: {
  predictionTab: PredictionTab
  selectedBooks: string[]
  matchupSearch: string
  minEdge: number
}) => (
  <div className="model-filter-toolbar" data-testid="model-filter-toolbar">
    <Filter size={14} className="shrink-0 text-[var(--text-tertiary)]" aria-hidden />
    <span className="text-sm text-[var(--text-secondary)]">
      {predictionTab === "past" ? "Past replay filters" : "Active board filters"}
    </span>
    <span className="text-sm text-[var(--text-tertiary)]" data-testid="filter-summary-chip">
      {selectedBooks.length > 0
        ? `${selectedBooks.length} book${selectedBooks.length === 1 ? "" : "s"}`
        : "All books"}
      {" · "}
      {(minEdge * 100).toFixed(0)}% min edge
      {matchupSearch.trim() ? ` · “${matchupSearch.trim()}”` : ""}
    </span>
  </div>
)
