import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ComparePage } from "@/pages/compare-page"

const { apiMock, snapshotMock } = vi.hoisted(() => ({
  apiMock: {
    getTracks: vi.fn(async () => ({
      tracks: {
        dashboard: { track: "dashboard", model_variant: "baseline", config_hash: "011e7743e143e26b" },
        lab: { track: "lab", model_variant: "v5", config_hash: "3936389c4ef2d5b9" },
      },
      effective_config_hash: { dashboard: "011e7743e143e26b", lab: "3936389c4ef2d5b9" },
      history: [],
    })),
  },
  snapshotMock: { value: {} as Record<string, unknown> },
}))

vi.mock("@/lib/api", () => ({ api: apiMock }))
vi.mock("@/providers/live-snapshot-provider", () => ({
  useLiveSnapshot: () => snapshotMock.value,
}))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ComparePage />
    </QueryClientProvider>,
  )
}

describe("ComparePage", () => {
  it("shows the lab-off notice when the challenger section is missing", async () => {
    snapshotMock.value = {
      isLiveActive: false,
      liveTournament: undefined,
      upcomingTournament: { event_name: "RBC", rankings: [], matchup_bets: [] },
      labLiveTournament: null,
      labUpcomingTournament: null,
    }
    renderPage()
    await waitFor(() => expect(screen.getByTestId("compare-page")).toBeInTheDocument())
    expect(screen.getByTestId("compare-lab-off")).toBeInTheDocument()
  })

  it("renders rank deltas and pick overlap when both tracks are present", async () => {
    snapshotMock.value = {
      isLiveActive: false,
      liveTournament: undefined,
      upcomingTournament: {
        event_name: "RBC",
        model_variant: "baseline",
        rankings: [
          { rank: 1, player_key: "a", player: "Player A", composite: 80, course_fit: 0, form: 0, momentum: 0 },
          { rank: 2, player_key: "b", player: "Player B", composite: 78, course_fit: 0, form: 0, momentum: 0 },
        ],
        matchup_bets: [
          { pick: "A", pick_key: "a", opponent: "B", opponent_key: "b", odds: "-110", model_win_prob: 0.55, implied_prob: 0.52, ev: 0.06, ev_pct: "6%", composite_gap: 2, form_gap: 1, course_fit_gap: 1, reason: "x" },
        ],
      },
      labUpcomingTournament: {
        event_name: "RBC",
        model_variant: "v5",
        rankings: [
          { rank: 5, player_key: "a", player: "Player A", composite: 70, course_fit: 0, form: 0, momentum: 0 },
          { rank: 1, player_key: "b", player: "Player B", composite: 82, course_fit: 0, form: 0, momentum: 0 },
        ],
        matchup_bets: [
          { pick: "C", pick_key: "c", opponent: "D", opponent_key: "d", odds: "+120", model_win_prob: 0.5, implied_prob: 0.45, ev: 0.1, ev_pct: "10%", composite_gap: 1, form_gap: 0, course_fit_gap: 0, reason: "y" },
        ],
      },
      labLiveTournament: null,
    }
    renderPage()
    await waitFor(() => expect(screen.getByTestId("compare-rank-deltas")).toBeInTheDocument())
    // Player A: champion #1 vs challenger #5 => delta -4 (challenger ranks worse).
    const table = screen.getByTestId("compare-rank-deltas")
    expect(table).toHaveTextContent("Player A")
    expect(table).toHaveTextContent("Player B")
    // Overlap: champion has a|b, challenger has c|d => 0 both, 1 champion-only, 1 challenger-only.
    const overlap = screen.getByTestId("compare-pick-overlap")
    expect(overlap).toHaveTextContent("Champion only")
    expect(overlap).toHaveTextContent("Challenger only")
    expect(screen.getByTestId("track-badge-dashboard")).toBeInTheDocument()
    expect(screen.getByTestId("track-badge-lab")).toBeInTheDocument()
  })
})
