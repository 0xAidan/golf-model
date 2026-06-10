import type { ChangeEvent } from "react"
import { Filter, X } from "lucide-react"

import type { PredictionTab } from "@/hooks/use-prediction-tab"

const MIN_EDGE_OPTIONS = [0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.1] as const

export type ModelFilterToolbarProps = {
  predictionTab: PredictionTab
  /** Books offered for filtering. Sourced so this is non-empty even with zero current edges. */
  availableBooks: string[]
  selectedBooks: string[]
  matchupSearch: string
  minEdge: number
  /** When omitted the toolbar renders read-only (legacy summary-only behavior). */
  onSelectedBooksChange?: (value: string[]) => void
  onMatchupSearchChange?: (value: string) => void
  onMinEdgeChange?: (value: number) => void
}

/**
 * Always-visible filter bar for the picks workflow. The book filter (restrict
 * visible plays to selected sportsbooks) regressed out of reach in the PR #145
 * rebuild; this restores it next to the picks instead of burying it in a tab.
 */
export const ModelFilterToolbar = ({
  predictionTab,
  availableBooks,
  selectedBooks,
  matchupSearch,
  minEdge,
  onSelectedBooksChange,
  onMatchupSearchChange,
  onMinEdgeChange,
}: ModelFilterToolbarProps) => {
  const interactive = Boolean(onSelectedBooksChange || onMinEdgeChange || onMatchupSearchChange)
  const selectedSet = new Set(selectedBooks.map((book) => book.trim().toLowerCase()))

  const handleToggleBook = (book: string) => {
    if (!onSelectedBooksChange) return
    const normalized = book.trim().toLowerCase()
    const next = selectedSet.has(normalized)
      ? selectedBooks.filter((b) => b.trim().toLowerCase() !== normalized)
      : [...selectedBooks, normalized]
    onSelectedBooksChange(next)
  }

  const handleClearBooks = () => {
    if (!onSelectedBooksChange) return
    onSelectedBooksChange([])
  }

  const handleMinEdgeChange = (event: ChangeEvent<HTMLSelectElement>) => {
    if (!onMinEdgeChange) return
    onMinEdgeChange(Number(event.target.value))
  }

  const handleSearchChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (!onMatchupSearchChange) return
    onMatchupSearchChange(event.target.value)
  }

  const summaryLabel =
    selectedBooks.length > 0
      ? `${selectedBooks.length} book${selectedBooks.length === 1 ? "" : "s"}`
      : "All books"

  return (
    <div className="model-filter-toolbar" data-testid="model-filter-toolbar">
      <Filter size={14} className="shrink-0 text-[var(--text-tertiary)]" aria-hidden />
      <span className="text-sm text-[var(--text-secondary)]">
        {predictionTab === "past" ? "Past replay filters" : "Active board filters"}
      </span>

      {interactive && availableBooks.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter plays by sportsbook">
          {availableBooks.map((book) => {
            const isActive = selectedSet.has(book.trim().toLowerCase())
            return (
              <button
                key={book}
                type="button"
                aria-pressed={isActive}
                aria-label={`${isActive ? "Hide" : "Show only"} ${book} plays`}
                onClick={() => handleToggleBook(book)}
                className={`filter-chip${isActive ? " active" : ""}`}
                data-testid={`toolbar-book-chip-${book.trim().toLowerCase()}`}
              >
                {book}
              </button>
            )
          })}
          {selectedBooks.length > 0 ? (
            <button
              type="button"
              onClick={handleClearBooks}
              className="filter-chip"
              aria-label="Clear sportsbook filter (show all books)"
              data-testid="toolbar-book-chip-clear"
            >
              <X size={11} aria-hidden /> Clear
            </button>
          ) : null}
        </div>
      ) : null}

      {interactive && onMinEdgeChange ? (
        <label className="flex items-center gap-1.5 text-sm text-[var(--text-tertiary)]">
          <span className="uppercase tracking-wide text-[var(--text-faint)]">Min edge</span>
          <select
            value={MIN_EDGE_OPTIONS.includes(minEdge as (typeof MIN_EDGE_OPTIONS)[number]) ? minEdge : 0.02}
            onChange={handleMinEdgeChange}
            aria-label="Minimum edge threshold"
            data-testid="toolbar-min-edge"
            className="rounded border border-[var(--border)] bg-[var(--surface)] px-1.5 py-0.5 text-[var(--text-secondary)]"
          >
            {MIN_EDGE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {(option * 100).toFixed(0)}%
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {interactive && onMatchupSearchChange ? (
        <input
          type="search"
          value={matchupSearch}
          onChange={handleSearchChange}
          placeholder="Search player…"
          aria-label="Filter plays by player name"
          data-testid="toolbar-search"
          className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-0.5 text-sm text-[var(--text-secondary)] placeholder:text-[var(--text-faint)]"
        />
      ) : null}

      <span className="ml-auto text-sm text-[var(--text-tertiary)]" data-testid="filter-summary-chip">
        {summaryLabel}
        {" · "}
        {(minEdge * 100).toFixed(0)}% min edge
        {matchupSearch.trim() ? ` · “${matchupSearch.trim()}”` : ""}
      </span>
    </div>
  )
}
