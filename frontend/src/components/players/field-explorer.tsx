import { Search, X } from "lucide-react"

import { SgTrajectoryMeter } from "@/components/sg-trajectory-meter"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { useFieldExplorer } from "@/features/players/use-field-explorer"
import type { FieldExplorerFilter, FieldExplorerSort } from "@/features/players/player-workspace-types"
import { formatNumber } from "@/lib/format"
import { computeSgTrajectoryBounds } from "@/lib/metric-heat"
import { POWER_RANKINGS_HELP } from "@/lib/metric-tooltips"
import type { CompositePlayer } from "@/lib/types"
import { cn } from "@/lib/utils"
import { useIsNarrowViewport } from "@/hooks/use-media-query"

const SORT_OPTIONS: Array<{ id: FieldExplorerSort; label: string }> = [
  { id: "rank", label: "Rank" },
  { id: "composite", label: "Composite" },
  { id: "form", label: "Form" },
  { id: "trajectory", label: "Trajectory" },
  { id: "name", label: "Name" },
]

const FieldExplorerList = ({
  players,
  selectedKey,
  onSelect,
  trajectoryBounds,
  className,
}: {
  players: CompositePlayer[]
  selectedKey: string | null
  onSelect: (key: string, display: string) => void
  trajectoryBounds: { min: number; max: number }
  className?: string
}) => {
  const { query, setQuery, sort, setSort, filter, setFilter, displayList } = useFieldExplorer({
    players,
    selectedKey,
    onSelect,
  })

  return (
    <div className={cn("players-field-explorer", className)} data-testid="players-field-explorer">
      <div className="players-field-explorer__search">
        <Search size={14} className="players-field-explorer__search-icon" aria-hidden />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search players…"
          data-testid="players-search"
          aria-label="Search players"
          className="players-field-explorer__search-input"
        />
        {query ? (
          <button
            type="button"
            onClick={() => setQuery("")}
            className="players-field-explorer__search-clear"
            aria-label="Clear search"
          >
            <X size={12} />
          </button>
        ) : null}
      </div>

      <div className="players-field-explorer__toolbar">
        <div className="players-field-explorer__sort" role="group" aria-label="Sort field">
          {SORT_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={cn(
                "players-field-explorer__chip",
                sort === opt.id && "players-field-explorer__chip--active",
              )}
              onClick={() => setSort(opt.id)}
              data-testid={`field-sort-${opt.id}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="players-field-explorer__filter" role="group" aria-label="Filter list">
          {(["field", "all"] as FieldExplorerFilter[]).map((f) => (
            <button
              key={f}
              type="button"
              className={cn(
                "players-field-explorer__chip",
                filter === f && "players-field-explorer__chip--active",
              )}
              onClick={() => setFilter(f)}
              data-testid={`field-filter-${f}`}
            >
              {f === "field" ? "In field" : "All"}
            </button>
          ))}
        </div>
      </div>

      <div className="players-field-explorer__list" data-testid="players-field-list">
        {displayList.length === 0 ? (
          <div className="players-field-explorer__empty">
            {query.length >= 2 ? "No players found" : "No field loaded"}
          </div>
        ) : (
          displayList.map((row) => {
            const isSelected = selectedKey === row.player_key
            const model = row.model
            return (
              <button
                key={row.player_key}
                type="button"
                className={cn(
                  "players-field-card",
                  isSelected && "players-field-card--selected",
                )}
                onClick={() => onSelect(row.player_key, row.player_display)}
                data-testid={`field-card-${row.player_key}`}
                aria-current={isSelected ? "true" : undefined}
              >
                <div className="players-field-card__main">
                  <span className="players-field-card__name">{row.player_display}</span>
                  {!row.inField ? (
                    <span className="players-field-card__badge">DB</span>
                  ) : model ? (
                    <span className="players-field-card__rank" title={POWER_RANKINGS_HELP.rank}>
                      #{model.rank}
                    </span>
                  ) : null}
                </div>
                {model ? (
                  <div className="players-field-card__stats">
                    <span title={POWER_RANKINGS_HELP.composite}>
                      C <span className="num">{formatNumber(model.composite, 1)}</span>
                    </span>
                    <span title={POWER_RANKINGS_HELP.form}>
                      F <span className="num">{formatNumber(model.form, 1)}</span>
                    </span>
                    <span className="players-field-card__traj">
                      <SgTrajectoryMeter
                        momentumTrend={model.momentum_trend}
                        momentumDirection={model.momentum_direction}
                        normMin={trajectoryBounds.min}
                        normMax={trajectoryBounds.max}
                      />
                    </span>
                  </div>
                ) : null}
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}

export const FieldExplorer = ({
  players,
  selectedKey,
  selectedDisplay,
  onSelect,
}: {
  players: CompositePlayer[]
  selectedKey: string | null
  selectedDisplay: string
  onSelect: (key: string, display: string) => void
}) => {
  const isNarrow = useIsNarrowViewport()
  const trajectoryBounds = computeSgTrajectoryBounds(players)

  if (!isNarrow) {
    return (
      <FieldExplorerList
        players={players}
        selectedKey={selectedKey}
        onSelect={onSelect}
        trajectoryBounds={trajectoryBounds}
        className="players-field-explorer--sidebar"
      />
    )
  }

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="players-field-explorer__mobile-trigger"
          data-testid="players-field-mobile-trigger"
        >
          {selectedDisplay || "Select player"}
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="players-field-explorer__sheet w-full max-w-sm p-0">
        <SheetHeader className="border-b border-[var(--border)] px-4 py-3 text-left">
          <SheetTitle>Field</SheetTitle>
          <SheetDescription>Search and select a player</SheetDescription>
        </SheetHeader>
        <FieldExplorerList
          players={players}
          selectedKey={selectedKey}
          onSelect={onSelect}
          trajectoryBounds={trajectoryBounds}
          className="players-field-explorer--sheet"
        />
      </SheetContent>
    </Sheet>
  )
}
