import type { ColumnDef } from "@tanstack/react-table"
import { Link } from "react-router-dom"

import { CourseWeatherFeedPanel } from "@/components/cockpit/event-modules"
import { HeroDataGrid } from "@/components/monitoring/hero-data-grid"
import { CollapsibleSection } from "@/components/ui/collapsible-section"
import { FilterSheet } from "@/components/ui/filter-sheet"
import type { PredictionTab } from "@/hooks/use-prediction-tab"
import type { CockpitFeedItemModel, CockpitMetricModel } from "@/lib/cockpit-event-models"
import { buildRecentResultsColumns } from "@/lib/cockpit-columns"
import { DEFAULT_US_BOOKS } from "@/lib/prediction-board"

import type { WorkspacePastReplay } from "./use-workspace-past-replay"
import { WorkspaceEmptyState } from "./workspace-grade-cells"

export type WorkspaceLeftRailProps = {
  predictionTab: PredictionTab
  isNarrow: boolean
  pastReplay: WorkspacePastReplay
  courseFeedMetrics: CockpitMetricModel[]
  courseFeedItems: CockpitFeedItemModel[]
  displayAvailableBooks: string[]
  selectedBooks: string[]
  onSelectedBooksChange: (value: string[]) => void
  matchupSearch: string
  onMatchupSearchChange: (value: string) => void
  minEdge: number
  onMinEdgeChange: (value: number) => void
}

export function WorkspaceLeftRail({
  predictionTab,
  isNarrow,
  pastReplay,
  courseFeedMetrics,
  courseFeedItems,
  displayAvailableBooks,
  selectedBooks,
  onSelectedBooksChange,
  matchupSearch,
  onMatchupSearchChange,
  minEdge,
  onMinEdgeChange,
}: WorkspaceLeftRailProps) {
  const recentResultsColumns = buildRecentResultsColumns()
  const {
    pastEventOptions,
    selectedPastEventKey,
    setSelectedPastEventKey,
    selectedPastEvent,
    pastReplaySection,
    setPastReplaySection,
    pastReplayHasError,
    pastReplayErrorMessage,
    pastReplayHasHistoryLanes,
    pastEventsQuery,
    pastSnapshotQuery,
    pastTimelineQuery,
    pastMarketRowsQuery,
    pastRecentResults,
  } = pastReplay

  const allBooksSelected = selectedBooks.length === 0
  const isUsDefaultSelection =
    selectedBooks.length === DEFAULT_US_BOOKS.length &&
    DEFAULT_US_BOOKS.every((book) => selectedBooks.includes(book))

  return (
    <div className="cockpit-left-rail-stack" data-testid="workspace-left-rail">
      <FilterSheet title="Board filters" description="Books, player search, min edge">
        <div className="card">
          <div className="card-header">
            <div className="card-title">Filters</div>
            <div className="left-rail-filter-actions">
              {!isUsDefaultSelection && (
                <button
                  className="btn btn-ghost btn-compact-md"
                  onClick={() => onSelectedBooksChange([...DEFAULT_US_BOOKS])}
                  title="Show only books you can bet in the US"
                >
                  My books
                </button>
              )}
              {!allBooksSelected && (
                <button
                  className="btn btn-ghost btn-compact-md"
                  onClick={() => onSelectedBooksChange([])}
                  title="Include every book in the feed (incl. offshore)"
                >
                  All
                </button>
              )}
            </div>
          </div>
          <div className="card-body card-body-stack-10">
            {displayAvailableBooks.length > 0 && (
              <div>
                <div className="field-label">
                  Sportsbook{" "}
                  <span className="text-muted-11">
                    {allBooksSelected ? "all books" : "your books only"}
                  </span>
                </div>
                <div className="filter-chips">
                  {displayAvailableBooks.map((book) => (
                    <button
                      key={book}
                      onClick={() => {
                        const next = selectedBooks.includes(book)
                          ? selectedBooks.filter((b) => b !== book)
                          : [...selectedBooks, book]
                        onSelectedBooksChange(next)
                      }}
                      className={`filter-chip${selectedBooks.includes(book) || allBooksSelected ? " active" : ""}`}
                      data-testid={`book-chip-${book}`}
                    >
                      {book}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div className="field-label">Search player</div>
              <div className="search-input">
                <svg
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="search-icon"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
                <input
                  type="text"
                  value={matchupSearch}
                  onChange={(e) => onMatchupSearchChange(e.target.value)}
                  placeholder="Player name…"
                  aria-label="Search matchups by player name"
                  data-testid="search-matchups"
                />
              </div>
            </div>

            <div>
              <div className="field-label">
                Min edge: <span className="text-muted-11">{(minEdge * 100).toFixed(0)}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="0.2"
                step="0.01"
                value={minEdge}
                onChange={(e) => onMinEdgeChange(Number(e.target.value))}
                className="workspace-range"
                aria-label="Minimum edge threshold"
                data-testid="min-edge-slider"
              />
            </div>
          </div>
        </div>
      </FilterSheet>

      {predictionTab === "past" && (
        <div className="card">
          <div className="card-header">
            <div className="card-title">Replay selector</div>
          </div>
          <div className="card-body card-body-stack-8">
                    {pastEventOptions.length === 0 && (
                      <div
                        role="status"
                        data-testid="past-events-empty"
                        className="workspace-status-banner"
                      >
                        No past events to replay: snapshot history is empty and no graded tournaments with a
                        DataGolf <code>event_id</code> were found (legacy rows may still resolve from round data
                        after deploy). Ensure the live-refresh worker has run for completed events and grading has
                        stored picks linked to the tournament.
                      </div>
                    )}
                    <div>
                      <div className="field-label field-label--tight">Event</div>
                      <select
                        value={selectedPastEventKey || selectedPastEvent?.event_id || ""}
                        onChange={(e) => setSelectedPastEventKey(e.target.value)}
                        aria-label="Select past event for replay"
                        disabled={pastEventOptions.length === 0}
                        className="workspace-select"
                        data-testid="past-event-select"
                      >
                        {pastEventOptions.map((e) => (
                          <option key={e.event_id} value={e.event_id}>
                            {e.event_name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <div className="field-label field-label--tight">Lane</div>
                      <div className="workspace-lane-row">
                        {(["completed", "live", "upcoming"] as const).map((lane) => (
                          <button
                            key={lane}
                            type="button"
                            onClick={() => setPastReplaySection(lane)}
                            aria-pressed={pastReplaySection === lane}
                            className="workspace-lane-btn"
                          >
                            {lane}
                          </button>
                        ))}
                      </div>
                    </div>
                    {pastReplayHasError && (
                      <div role="alert" className="workspace-alert-error">
                        <div>Replay request failed: {pastReplayErrorMessage}</div>
                        <div className="flex-wrap-gap-6">
                          <button
                            type="button"
                            className="btn btn-ghost btn-compact"
                            onClick={() => {
                              void pastEventsQuery.refetch()
                              void pastSnapshotQuery.refetch()
                              if (pastReplayHasHistoryLanes) {
                                void pastTimelineQuery.refetch()
                              }
                              void pastMarketRowsQuery.refetch()
                            }}
                          >
                            Retry replay fetch
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

      <CollapsibleSection
        title="Course & weather"
        description="Secondary context"
        defaultOpen={isNarrow}
        testId="intel-course-weather"
      >
        <CourseWeatherFeedPanel metrics={courseFeedMetrics} feedItems={courseFeedItems} />
      </CollapsibleSection>

      <CollapsibleSection
        title={predictionTab === "past" ? "Past events" : "Recent results"}
        description={predictionTab === "past" ? "Replay history" : "Graded events"}
        defaultOpen={isNarrow || predictionTab === "past"}
        testId="intel-recent-results"
      >
        <div className="flex-end-row">
          <Link to="/grading" className="link-accent-11">
            All grading →
          </Link>
        </div>
        <div className="table-scroll">
          {pastRecentResults.length > 0 ? (
            <HeroDataGrid
              data={pastRecentResults}
              columns={recentResultsColumns as ColumnDef<(typeof pastRecentResults)[number], unknown>[]}
              density="compact"
              virtualizeAfter={40}
              getRowId={(row) => `${row.event.event_id}-${row.event.name}`}
            />
          ) : (
            <div className="card-body-pad">
              <WorkspaceEmptyState
                message={
                  predictionTab === "past"
                    ? "No past events available yet. Run live-refresh through a completed tournament week first."
                    : "No graded events yet."
                }
              />
            </div>
          )}
        </div>
      </CollapsibleSection>
    </div>
  )
}
