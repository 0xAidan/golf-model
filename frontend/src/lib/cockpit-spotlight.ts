import { formatNumber } from "@/lib/format"
import type { CompositePlayer, FlattenedSecondaryBet, LiveLeaderboardRow, MatchupBet } from "@/lib/types"

export type SpotlightStat = {
  label: string
  value: string
  detail?: string
  tone?: "default" | "positive" | "warning"
}

export type SpotlightInventoryNote = {
  label: string
  detail: string
}

export type CockpitSpotlightModel = {
  playerKey: string
  playerName: string
  eventName: string
  mode: "live" | "upcoming" | "test" | "past"
  modeLabel: string
  sourceBadges: string[]
  narrative: string
  headerStats: SpotlightStat[]
  summaryStats: SpotlightStat[]
  inventoryNotes: SpotlightInventoryNote[]
}

type BuildCockpitSpotlightInput = {
  predictionTab: "live" | "upcoming" | "test" | "past"
  eventName: string
  selectedPlayerKey: string
  players: CompositePlayer[]
  leaderboardRows: LiveLeaderboardRow[]
  topPlays: MatchupBet[]
  rawGeneratedMatchups: MatchupBet[]
  rawGeneratedSecondaryBets: FlattenedSecondaryBet[]
}

export function buildCockpitSpotlight({
  predictionTab,
  eventName,
  selectedPlayerKey,
  players,
  leaderboardRows,
  topPlays,
  rawGeneratedMatchups,
  rawGeneratedSecondaryBets,
}: BuildCockpitSpotlightInput): CockpitSpotlightModel | null {
  if (!selectedPlayerKey) {
    return null
  }

  const selectedPlayer = players.find((player) => player.player_key === selectedPlayerKey) ?? null
  const selectedLeaderboardRow = leaderboardRows.find((row) => row.player_key === selectedPlayerKey) ?? null
  const featuredMatchups = topPlays.filter(
    (matchup) => matchup.pick_key === selectedPlayerKey || matchup.opponent_key === selectedPlayerKey,
  )
  const generatedMatchups = rawGeneratedMatchups.filter(
    (matchup) => matchup.pick_key === selectedPlayerKey || matchup.opponent_key === selectedPlayerKey,
  )
  const generatedSecondary = rawGeneratedSecondaryBets.filter(
    (bet) => bet.player_key === selectedPlayerKey,
  )

  const featuredPlayerName = featuredMatchups[0]
    ? featuredMatchups[0].pick_key === selectedPlayerKey
      ? featuredMatchups[0].pick
      : featuredMatchups[0].opponent
    : null
  const secondaryPlayerName = generatedSecondary[0]?.player_display ?? generatedSecondary[0]?.player ?? null
  const selectedName =
    selectedPlayer?.player_display
    ?? selectedLeaderboardRow?.player
    ?? featuredPlayerName
    ?? secondaryPlayerName

  if (!selectedName) {
    return null
  }

  const generatedSecondaryByName = rawGeneratedSecondaryBets.filter(
    (bet) =>
      bet.player_key === selectedPlayerKey
      || normalizeName(bet.player_display ?? bet.player) === normalizeName(selectedName),
  )
  const totalGeneratedPickCount = generatedMatchups.length + generatedSecondaryByName.length
  const sourceBadges = buildSourceBadges({
    hasRanking: Boolean(selectedPlayer),
    hasLeaderboard: Boolean(selectedLeaderboardRow),
    hasFeaturedPlay: featuredMatchups.length > 0,
    hasGeneratedPicks: totalGeneratedPickCount > 0,
  })

  return {
    playerKey: selectedPlayerKey,
    playerName: selectedName,
    eventName,
    mode: predictionTab,
    modeLabel:
      predictionTab === "live"
        ? "Live"
        : predictionTab === "upcoming"
          ? "Upcoming"
          : predictionTab === "test"
            ? "Test (v5)"
            : "Past",
    sourceBadges,
    narrative: buildNarrative({
      predictionTab,
      eventName,
      selectedName,
      selectedPlayer,
      selectedLeaderboardRow,
      featuredMatchupCount: featuredMatchups.length,
      totalGeneratedPickCount,
    }),
    headerStats: buildHeaderStats({
      predictionTab,
      selectedPlayer,
      selectedLeaderboardRow,
      featuredMatchupCount: featuredMatchups.length,
      totalGeneratedPickCount,
    }),
    summaryStats: buildSummaryStats({
      predictionTab,
      selectedPlayer,
      selectedLeaderboardRow,
      generatedSecondaryCount: generatedSecondaryByName.length,
    }),
    inventoryNotes: buildInventoryNotes({
      predictionTab,
      featuredMatchups,
      generatedMatchups,
      generatedSecondary: generatedSecondaryByName,
    }),
  }
}

function buildSourceBadges({
  hasRanking,
  hasLeaderboard,
  hasFeaturedPlay,
  hasGeneratedPicks,
}: {
  hasRanking: boolean
  hasLeaderboard: boolean
  hasFeaturedPlay: boolean
  hasGeneratedPicks: boolean
}) {
  const badges: string[] = []

  if (hasRanking) {
    badges.push("Rankings")
  }
  if (hasLeaderboard) {
    badges.push("Leaderboard")
  }
  if (hasFeaturedPlay) {
    badges.push("Featured play")
  }
  if (hasGeneratedPicks) {
    badges.push("Generated picks")
  }

  return badges
}

function buildNarrative({
  predictionTab,
  eventName,
  selectedName,
  selectedPlayer,
  selectedLeaderboardRow,
  featuredMatchupCount,
  totalGeneratedPickCount,
}: {
  predictionTab: "live" | "upcoming" | "test" | "past"
  eventName: string
  selectedName: string
  selectedPlayer: CompositePlayer | null
  selectedLeaderboardRow: LiveLeaderboardRow | null
  featuredMatchupCount: number
  totalGeneratedPickCount: number
}) {
  if (predictionTab === "live") {
    const position = selectedLeaderboardRow?.position ?? formatRank(selectedLeaderboardRow?.rank)
    const liveLead = position !== "--"
      ? `${selectedName} is on the live board at ${position}`
      : `${selectedName} is part of the live board scan`
    const rankTail = selectedPlayer ? ` while still carrying model rank ${formatRank(selectedPlayer.rank)}` : ""
    return `${liveLead} for ${eventName}${rankTail}. The cockpit is tracking ${featuredMatchupCount} featured play mention${pluralize(featuredMatchupCount)} and ${totalGeneratedPickCount} total generated pick${pluralize(totalGeneratedPickCount)} for this player right now.`
  }

  if (predictionTab === "upcoming" || predictionTab === "test") {
    const composite = selectedPlayer ? formatNumber(selectedPlayer.composite, 1) : "--"
    return `${selectedName} matters on the pre-tournament board for ${eventName}${selectedPlayer ? ` with model rank ${formatRank(selectedPlayer.rank)} and a ${composite} composite score` : ""}. The cockpit is tying that ranking view to ${totalGeneratedPickCount} generated pick${pluralize(totalGeneratedPickCount)} before the event starts.`
  }

  return `${selectedName} is anchored in the replay snapshot for ${eventName}${selectedPlayer ? ` with captured model rank ${formatRank(selectedPlayer.rank)}` : ""}. This keeps the stored card context, featured plays, and generated-pick inventory connected while reviewing a completed event.`
}

function buildHeaderStats({
  predictionTab,
  selectedPlayer,
  selectedLeaderboardRow,
  featuredMatchupCount,
  totalGeneratedPickCount,
}: {
  predictionTab: "live" | "upcoming" | "test" | "past"
  selectedPlayer: CompositePlayer | null
  selectedLeaderboardRow: LiveLeaderboardRow | null
  featuredMatchupCount: number
  totalGeneratedPickCount: number
}) {
  if (predictionTab === "live" && selectedLeaderboardRow) {
    return [
      { label: "Leaderboard", value: selectedLeaderboardRow.position ?? formatRank(selectedLeaderboardRow.rank) },
      { label: "To par", value: formatToPar(selectedLeaderboardRow.total_to_par) },
      { label: "Featured plays", value: String(featuredMatchupCount) },
      { label: "Generated picks", value: String(totalGeneratedPickCount) },
    ]
  }

  if (predictionTab === "past") {
    return [
      { label: "Replay rank", value: selectedPlayer ? formatRank(selectedPlayer.rank) : "--" },
      { label: "Composite", value: selectedPlayer ? formatNumber(selectedPlayer.composite, 1) : "--" },
      { label: "Featured plays", value: String(featuredMatchupCount) },
      { label: "Generated picks", value: String(totalGeneratedPickCount) },
    ]
  }

  return [
    { label: "Model rank", value: selectedPlayer ? formatRank(selectedPlayer.rank) : "--" },
    { label: "Composite", value: selectedPlayer ? formatNumber(selectedPlayer.composite, 1) : "--" },
    { label: "Featured plays", value: String(featuredMatchupCount) },
    { label: "Generated picks", value: String(totalGeneratedPickCount) },
  ]
}

function buildSummaryStats({
  predictionTab,
  selectedPlayer,
  selectedLeaderboardRow,
  generatedSecondaryCount,
}: {
  predictionTab: "live" | "upcoming" | "test" | "past"
  selectedPlayer: CompositePlayer | null
  selectedLeaderboardRow: LiveLeaderboardRow | null
  generatedSecondaryCount: number
}) {
  if (predictionTab === "live") {
    return [
      { label: "Model rank", value: selectedPlayer ? formatRank(selectedPlayer.rank) : "--" },
      { label: "Latest round", value: String(selectedLeaderboardRow?.latest_round_num ?? "--") },
      { label: "Round score", value: String(selectedLeaderboardRow?.latest_round_score ?? "--") },
      { label: "Secondary markets", value: String(generatedSecondaryCount) },
    ]
  }

  if (predictionTab === "past") {
    return [
      { label: "Replay focus", value: "Captured card context" },
      { label: "Form", value: selectedPlayer ? formatNumber(selectedPlayer.form, 1) : "--" },
      { label: "Course fit", value: selectedPlayer ? formatNumber(selectedPlayer.course_fit, 1) : "--" },
      { label: "Momentum", value: selectedPlayer ? formatNumber(selectedPlayer.momentum, 1) : "--" },
    ]
  }

  return [
    { label: "Model rank", value: selectedPlayer ? formatRank(selectedPlayer.rank) : "--" },
    { label: "Best fit now", value: selectedPlayer ? strongestModelArea(selectedPlayer) : "--" },
    { label: "Momentum", value: selectedPlayer ? formatNumber(selectedPlayer.momentum, 1) : "--" },
    { label: "Secondary markets", value: String(generatedSecondaryCount) },
  ]
}

function buildInventoryNotes({
  predictionTab,
  featuredMatchups,
  generatedMatchups,
  generatedSecondary,
}: {
  predictionTab: "live" | "upcoming" | "test" | "past"
  featuredMatchups: MatchupBet[]
  generatedMatchups: MatchupBet[]
  generatedSecondary: FlattenedSecondaryBet[]
}) {
  const notes: SpotlightInventoryNote[] = []
  const featured = featuredMatchups[0]

  if (featured) {
    notes.push({
      label: predictionTab === "past" ? "Captured featured play" : "Featured play",
      detail: `${featured.pick} over ${featured.opponent} at ${featured.book ?? "book"} (${featured.ev_pct})`,
    })
  }

  const secondary = generatedSecondary[0]
  if (secondary) {
    notes.push({
      label: "Best secondary market",
      detail: `${secondary.market} ${secondary.odds} at ${secondary.book ?? "book"} (${formatPercentValue(secondary.ev)})`,
    })
  }

  const matchupCount = generatedMatchups.length
  if (matchupCount > 0) {
    notes.push({
      label: "Generated matchup inventory",
      detail: `${matchupCount} matchup row${pluralize(matchupCount)} include this player in the full pick inventory.`,
    })
  }

  if (notes.length === 0) {
    notes.push({
      label: "Cockpit context",
      detail: "This player is currently selected from the active event context even without a featured or generated market mention.",
    })
  }

  return notes.slice(0, 3)
}

function strongestModelArea(player: CompositePlayer) {
  const candidates = [
    { label: "Composite", value: player.composite },
    { label: "Form", value: player.form },
    { label: "Course fit", value: player.course_fit },
    { label: "Momentum", value: player.momentum },
  ]
  const best = candidates.reduce((highest, entry) => (entry.value > highest.value ? entry : highest), candidates[0]!)
  return best.label
}

function normalizeName(value: string) {
  return value.toLowerCase().trim()
}

function formatToPar(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--"
  }
  if (value === 0) {
    return "E"
  }
  return value > 0 ? `+${value}` : `${value}`
}

function formatRank(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--"
  }
  return `#${value}`
}

function formatPercentValue(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--"
  }
  return `${(value * 100).toFixed(1)}% EV`
}

function pluralize(value: number) {
  return value === 1 ? "" : "s"
}
