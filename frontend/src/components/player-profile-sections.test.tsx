import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { PlayerProfileSections } from "@/components/player-profile-sections"
import type { CompositePlayer, PlayerProfile } from "@/lib/types"

// Profile sections renders several heavyweight charts. Stub them all out so
// the test focuses on layout / control wiring rather than the SVG internals.
vi.mock("@/components/charts", () => ({
  SparklineChart: ({ values }: { values: number[] }) => (
    <div data-testid="sparkline-chart">{values.length}</div>
  ),
  SgSkillBarsChart: () => <div data-testid="sg-skill-bars-chart" />,
  SgRollingChart: () => <div data-testid="sg-rolling-chart" />,
  TournamentHistoryChart: () => <div data-testid="tournament-history-chart" />,
  ApproachBucketsChart: () => <div data-testid="approach-buckets-chart" />,
  BarTrendChart: () => <div data-testid="bar-trend-chart" />,
}))

const basePlayer: CompositePlayer = {
  player_key: "jon_rahm",
  player_display: "Jon Rahm",
  rank: 2,
  composite: 82.6,
  course_fit: 79.4,
  form: 80.3,
  momentum: 77.9,
  momentum_direction: "warming",
  course_confidence: 0.74,
  course_rounds: 14,
  details: {
    course_components: { driving: 1.1, approach: 0.9 },
    form_components: { baseline: 0.5 },
    momentum_windows: { w12: 0.25 },
  },
}

const richProfile: PlayerProfile = {
  player_key: "jon_rahm",
  player_display: "Jon Rahm",
  current_metrics: {
    dg_skill: { sg_total: 1.8, sg_app: 0.7 },
  },
  recent_rounds: [{ sg_total: 1.2 }, { sg_total: 0.8 }, { sg_total: 1.5 }],
  course_history: [{ sg_total: 0.6 }, { sg_total: -0.2 }],
  linked_bets: [
    {
      bet_type: "matchup",
      player_display: "Jon Rahm",
      opponent_display: "Scottie Scheffler",
      market_odds: "-110",
      ev: 0.07,
      confidence: "high",
      reasoning: "Model form edge",
    },
  ],
  header: {
    dg_rank: 4,
    owgr_rank: 3,
    dg_skill_estimate: 2.1,
    field_size: 88,
    field_status: "confirmed",
  },
  skill_breakdown: {
    primary: [
      { key: "dg_sg_total", label: "DG SG Total", value: 2.1 },
      { key: "dg_sg_app", label: "DG Approach", value: 0.8 },
    ],
    approach_buckets: [
      { key: "100_150_fw_sg_per_shot", label: "100 150 Fw Sg Per Shot", value: 0.25 },
    ],
    component_deltas: [{ key: "dg_total_fit_adj", label: "Course-Fit Adjustment", value: 0.18 }],
    summary: {
      best_area: { key: "dg_sg_total", label: "DG SG Total", value: 2.1 },
      weakest_area: { key: "dg_sg_putt", label: "DG Putting", value: -0.1 },
    },
  },
  rolling_form: {
    windows: { "10": 0.7, "25": 0.5, "50": 0.3 },
    benchmarks: {
      tour_avg: { "10": 0.2, "25": 0.15, "50": 0.1 },
      top50: { "10": 0.5, "25": 0.35, "50": 0.2 },
      top10: { "10": 0.8, "25": 0.65, "50": 0.5 },
    },
    trend_series: [0.2, 0.4, 0.7, 0.6, 0.9],
    summary: { delta_short_vs_medium: 0.2, rounds_in_sample: 24 },
  },
  course_event_context: {
    recent_starts: [
      { event_name: "Masters Tournament", event_completed: "2026-04-12", fin_text: "T5", avg_sg_total: 0.92 },
    ],
    recent_summary: { events_tracked: 8, made_cuts: 7, avg_sg_total: 0.43 },
    course_summary: { rounds_tracked: 12, avg_sg_total: 0.36, best_round_sg: 2.2, worst_round_sg: -1.1 },
  },
  betting_context: {
    summary: { linked_bet_count: 1, average_ev: 0.07, high_confidence_count: 1 },
  },
}

describe("PlayerProfileSections", () => {
  it("renders rich profile sections with dynamic controls", async () => {
    const user = userEvent.setup()
    render(<PlayerProfileSections player={basePlayer} profile={richProfile} profileReady />)

    // Section labels were tightened during the player-profile redesign:
    // "Profile Header" → "Player Overview", "Skill Breakdown" →
    // "SG Skill Profile", "Course/Event Context" → "Recent Tournament History".
    expect(screen.getByText("Player Overview")).toBeInTheDocument()
    expect(screen.getByText("SG Skill Profile")).toBeInTheDocument()
    expect(screen.getByText("Rolling Form")).toBeInTheDocument()
    expect(screen.getByText("Recent Tournament History")).toBeInTheDocument()
    expect(screen.getByText("Betting Context")).toBeInTheDocument()

    // Window selector is now a pill group ("L10" / "L25" / "L50"); clicking
    // L10 retitles the metric tile to "Avg SG (L10)".
    await user.click(screen.getByRole("button", { name: "L10" }))
    expect(screen.getByText("Avg SG (L10)")).toBeInTheDocument()

    // Benchmark selector is also a pill group ("Tour Avg" / "Top 50" /
    // "Top 10"); clicking Top 10 retitles the comparison tile to "Top 10 SG".
    await user.click(screen.getByRole("button", { name: "Top 10" }))
    expect(screen.getByText("Top 10 SG")).toBeInTheDocument()
  })

  it("shows loading state when profile is not ready", () => {
    render(<PlayerProfileSections player={basePlayer} profile={undefined} profileReady={false} />)
    // Loading copy was shortened to "Loading profile…" during the player
    // profile redesign; the test still guards that a loading affordance
    // appears when the profile data hasn't arrived yet.
    expect(screen.getByText(/loading profile/i)).toBeInTheDocument()
  })
})
