import { renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { useCockpitSpotlight } from "@/hooks/use-cockpit-spotlight"
import type { CompositePlayer, FlattenedSecondaryBet } from "@/lib/types"

const basePlayer: CompositePlayer = {
  player_key: "scottie_scheffler",
  player_display: "Scottie Scheffler",
  rank: 1,
  composite: 92.4,
  course_fit: 90.1,
  form: 93.8,
  momentum: 88.5,
}

describe("useCockpitSpotlight", () => {
  it("suppresses spotlight selection when live tab has no active live event", () => {
    const onPlayerSelect = vi.fn()

    const { result } = renderHook(() =>
      useCockpitSpotlight({
        predictionTab: "live",
        isLiveActive: false,
        eventName: "RBC Heritage",
        selectedPlayerKey: "scottie_scheffler",
        onPlayerSelect,
        players: [basePlayer],
        leaderboardRows: [],
        topPlays: [],
        rawGeneratedMatchups: [],
        rawGeneratedSecondaryBets: [],
      }),
    )

    expect(result.current.spotlightMode).toBe("upcoming")
    expect(result.current.spotlight).toBeNull()
    expect(result.current.spotlightCandidateKeys).toEqual([])
    expect(onPlayerSelect).not.toHaveBeenCalled()
  })

  it("auto-selects a player surfaced only through generated secondary picks when a stable key exists", () => {
    const onPlayerSelect = vi.fn()
    const secondaryOnly: FlattenedSecondaryBet = {
      market: "Top 10",
      player: "Akshay Bhatia",
      player_display: "Akshay Bhatia",
      player_key: "akshay_bhatia",
      odds: "+210",
      ev: 0.08,
      book: "draftkings",
    }

    renderHook(() =>
      useCockpitSpotlight({
        predictionTab: "upcoming",
        isLiveActive: false,
        eventName: "RBC Heritage",
        selectedPlayerKey: "",
        onPlayerSelect,
        players: [],
        leaderboardRows: [],
        topPlays: [],
        rawGeneratedMatchups: [],
        rawGeneratedSecondaryBets: [secondaryOnly],
      }),
    )

    expect(onPlayerSelect).toHaveBeenCalledWith("akshay_bhatia")
  })

  it("falls back from secondary-pick name matching when a stable key is not present", () => {
    const onPlayerSelect = vi.fn()
    const secondaryOnly: FlattenedSecondaryBet = {
      market: "Top 20",
      player: "Akshay Bhatia",
      player_display: "Akshay Bhatia",
      odds: "+140",
      ev: 0.05,
      book: "fanduel",
    }

    renderHook(() =>
      useCockpitSpotlight({
        predictionTab: "upcoming",
        isLiveActive: false,
        eventName: "RBC Heritage",
        selectedPlayerKey: "",
        onPlayerSelect,
        players: [
          {
            ...basePlayer,
            player_key: "akshay_bhatia",
            player_display: "Akshay Bhatia",
            rank: 8,
          },
        ],
        leaderboardRows: [],
        topPlays: [],
        rawGeneratedMatchups: [],
        rawGeneratedSecondaryBets: [secondaryOnly],
      }),
    )

    expect(onPlayerSelect).toHaveBeenCalledWith("akshay_bhatia")
  })

  it("auto-selects a player surfaced only through raw generated matchup inventory", () => {
    const onPlayerSelect = vi.fn()

    renderHook(() =>
      useCockpitSpotlight({
        predictionTab: "upcoming",
        isLiveActive: false,
        eventName: "RBC Heritage",
        selectedPlayerKey: "",
        onPlayerSelect,
        players: [],
        leaderboardRows: [],
        topPlays: [],
        rawGeneratedMatchups: [
          {
            pick: "Akshay Bhatia",
            pick_key: "akshay_bhatia",
            opponent: "Tom Kim",
            opponent_key: "tom_kim",
            odds: "-110",
            model_win_prob: 0.55,
            implied_prob: 0.52,
            ev: 0.03,
            ev_pct: "3.0%",
            composite_gap: 1.2,
            form_gap: 0.8,
            course_fit_gap: 0.4,
            reason: "Inventory-only row",
          },
        ],
        rawGeneratedSecondaryBets: [],
      }),
    )

    expect(onPlayerSelect).toHaveBeenCalledWith("akshay_bhatia")
  })
})
