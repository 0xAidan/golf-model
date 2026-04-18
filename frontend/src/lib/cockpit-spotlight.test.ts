import { describe, expect, it } from "vitest"

import { buildCockpitSpotlight } from "@/lib/cockpit-spotlight"
import type { CompositePlayer, LiveLeaderboardRow, MatchupBet } from "@/lib/types"

const basePlayer: CompositePlayer = {
  player_key: "scottie_scheffler",
  player_display: "Scottie Scheffler",
  rank: 1,
  composite: 92.4,
  course_fit: 90.1,
  form: 93.8,
  momentum: 88.5,
  momentum_direction: "hot",
}

const liveRow: LiveLeaderboardRow = {
  rank: 2,
  position: "T2",
  player_key: "scottie_scheffler",
  player: "Scottie Scheffler",
  total_to_par: -7,
  latest_round_num: 3,
  latest_round_score: 67,
}

const featuredMatchup: MatchupBet = {
  pick: "Scottie Scheffler",
  pick_key: "scottie_scheffler",
  opponent: "Rory McIlroy",
  opponent_key: "rory_mcilroy",
  odds: "-115",
  book: "draftkings",
  model_win_prob: 0.58,
  implied_prob: 0.53,
  ev: 0.08,
  ev_pct: "8.0%",
  composite_gap: 1.8,
  form_gap: 1.4,
  course_fit_gap: 0.9,
  reason: "Model edge",
  tier: "GOOD",
  conviction: 73,
}

describe("buildCockpitSpotlight", () => {
  it("builds live context from rankings, leaderboard, featured plays, and generated inventory", () => {
    const spotlight = buildCockpitSpotlight({
      predictionTab: "live",
      eventName: "RBC Heritage",
      selectedPlayerKey: "scottie_scheffler",
      players: [basePlayer],
      leaderboardRows: [liveRow],
      topPlays: [featuredMatchup],
      rawGeneratedMatchups: [
        featuredMatchup,
        {
          ...featuredMatchup,
          odds: "-110",
          ev: 0.06,
          ev_pct: "6.0%",
          book: "fanduel",
        },
      ],
      rawGeneratedSecondaryBets: [
        { market: "Top 10", player: "Scottie Scheffler", odds: "+105", ev: 0.05, book: "betmgm" },
      ],
    })

    expect(spotlight).not.toBeNull()
    expect(spotlight?.playerName).toBe("Scottie Scheffler")
    expect(spotlight?.sourceBadges).toEqual(["Rankings", "Leaderboard", "Featured play", "Generated picks"])
    expect(spotlight?.narrative).toContain("live board")
    expect(spotlight?.headerStats.map((item) => `${item.label}:${item.value}`)).toEqual([
      "Leaderboard:T2",
      "To par:-7",
      "Featured plays:1",
      "Generated picks:3",
    ])
    expect(spotlight?.summaryStats.map((item) => `${item.label}:${item.value}`)).toContain("Model rank:#1")
  })

  it("builds upcoming context when the player is driven by rankings and generated inventory", () => {
    const spotlight = buildCockpitSpotlight({
      predictionTab: "upcoming",
      eventName: "RBC Heritage",
      selectedPlayerKey: "scottie_scheffler",
      players: [basePlayer],
      leaderboardRows: [],
      topPlays: [],
      rawGeneratedMatchups: [],
      rawGeneratedSecondaryBets: [
        { market: "Top 5", player: "Scottie Scheffler", odds: "+210", ev: 0.09, book: "draftkings" },
      ],
    })

    expect(spotlight).not.toBeNull()
    expect(spotlight?.sourceBadges).toEqual(["Rankings", "Generated picks"])
    expect(spotlight?.narrative).toContain("pre-tournament board")
    expect(spotlight?.headerStats.map((item) => `${item.label}:${item.value}`)).toEqual([
      "Model rank:#1",
      "Composite:92.4",
      "Featured plays:0",
      "Generated picks:1",
    ])
    expect(spotlight?.summaryStats.map((item) => `${item.label}:${item.value}`)).toContain("Best fit now:Form")
  })

  it("builds replay context for past mode without requiring leaderboard data", () => {
    const spotlight = buildCockpitSpotlight({
      predictionTab: "past",
      eventName: "Masters Tournament",
      selectedPlayerKey: "scottie_scheffler",
      players: [basePlayer],
      leaderboardRows: [],
      topPlays: [featuredMatchup],
      rawGeneratedMatchups: [featuredMatchup],
      rawGeneratedSecondaryBets: [],
    })

    expect(spotlight).not.toBeNull()
    expect(spotlight?.narrative).toContain("replay snapshot")
    expect(spotlight?.headerStats.map((item) => `${item.label}:${item.value}`)).toEqual([
      "Replay rank:#1",
      "Composite:92.4",
      "Featured plays:1",
      "Generated picks:1",
    ])
    expect(spotlight?.summaryStats.map((item) => `${item.label}:${item.value}`)).toContain("Replay focus:Captured card context")
  })
})
