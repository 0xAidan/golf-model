import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { GitCompare } from "lucide-react"

import { TrackBadge } from "@/components/product/track-badge"
import { EmptyState } from "@/components/ui/empty-state"
import { TerminalPageHeader } from "@/components/ui/terminal-page-header"
import { api } from "@/lib/api"
import { POLLING } from "@/lib/query-polling"
import { useLiveSnapshot } from "@/providers/live-snapshot-provider"
import type { LiveRankingRow, LiveTournamentSnapshot, MatchupBet } from "@/lib/types"

type RankDeltaRow = {
  playerKey: string
  player: string
  championRank: number | null
  challengerRank: number | null
  delta: number | null
}

const matchupKey = (bet: MatchupBet) =>
  `${(bet.pick_key || "").toLowerCase()}|${(bet.opponent_key || "").toLowerCase()}`

const buildRankIndex = (rows: LiveRankingRow[] | undefined) => {
  const index = new Map<string, LiveRankingRow>()
  for (const row of rows ?? []) {
    const key = (row.player_key || "").toLowerCase()
    if (key) index.set(key, row)
  }
  return index
}

const RANK_LIMIT = 40

export function ComparePage() {
  const { liveTournament, upcomingTournament, labLiveTournament, labUpcomingTournament, isLiveActive } =
    useLiveSnapshot()

  const tracksQuery = useQuery({
    queryKey: ["tracks"],
    queryFn: api.getTracks,
    refetchInterval: POLLING.dashboard,
    staleTime: POLLING.queryDefaultStale,
  })

  const usingLive = isLiveActive
  const championSection: LiveTournamentSnapshot | undefined = usingLive ? liveTournament : upcomingTournament
  const challengerSection: LiveTournamentSnapshot | null | undefined = usingLive
    ? labLiveTournament
    : labUpcomingTournament

  const dashboardTrack = tracksQuery.data?.tracks?.dashboard
  const labTrack = tracksQuery.data?.tracks?.lab

  const rankDeltas = useMemo<RankDeltaRow[]>(() => {
    const champIndex = buildRankIndex(championSection?.rankings)
    const challIndex = buildRankIndex(challengerSection?.rankings)
    const keys = new Set<string>([...champIndex.keys(), ...challIndex.keys()])
    const rows: RankDeltaRow[] = []
    for (const key of keys) {
      const champ = champIndex.get(key)
      const chall = challIndex.get(key)
      const championRank = champ?.rank ?? null
      const challengerRank = chall?.rank ?? null
      const delta =
        championRank !== null && challengerRank !== null ? championRank - challengerRank : null
      rows.push({
        playerKey: key,
        player: champ?.player || chall?.player || key,
        championRank,
        challengerRank,
        delta,
      })
    }
    rows.sort((a, b) => {
      const da = a.delta === null ? -1 : Math.abs(a.delta)
      const db = b.delta === null ? -1 : Math.abs(b.delta)
      return db - da
    })
    return rows.slice(0, RANK_LIMIT)
  }, [championSection?.rankings, challengerSection?.rankings])

  const overlap = useMemo(() => {
    const champ = new Map<string, MatchupBet>()
    for (const bet of championSection?.matchup_bets ?? []) champ.set(matchupKey(bet), bet)
    const chall = new Map<string, MatchupBet>()
    for (const bet of challengerSection?.matchup_bets ?? []) chall.set(matchupKey(bet), bet)
    const both: MatchupBet[] = []
    const championOnly: MatchupBet[] = []
    const challengerOnly: MatchupBet[] = []
    for (const [key, bet] of champ) {
      if (chall.has(key)) both.push(bet)
      else championOnly.push(bet)
    }
    for (const [key, bet] of chall) {
      if (!champ.has(key)) challengerOnly.push(bet)
    }
    return { both, championOnly, challengerOnly }
  }, [championSection?.matchup_bets, challengerSection?.matchup_bets])

  const eventName = championSection?.event_name || challengerSection?.event_name || "current event"
  const labOff = !challengerSection
  const noEventLoaded = !championSection && !challengerSection

  return (
    <div className="product-page product-page--satellite" data-testid="compare-page">
      <TerminalPageHeader
        eyebrow="Research"
        title="Track comparison"
        description="Same event, both model tracks. Differences are informational — not a recommendation to switch."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <TrackBadge
              track="dashboard"
              variant={championSection?.model_variant ?? dashboardTrack?.model_variant}
              configHash={dashboardTrack?.config_hash ?? tracksQuery.data?.effective_config_hash?.dashboard}
            />
            <span aria-hidden className="text-[var(--text-tertiary)]">vs</span>
            <TrackBadge
              track="lab"
              variant={challengerSection?.model_variant ?? labTrack?.model_variant}
              configHash={labTrack?.config_hash ?? tracksQuery.data?.effective_config_hash?.lab}
            />
          </div>
        }
      />
      <p className="mb-4 text-sm text-[var(--text-secondary)]">
        {eventName} · {usingLive ? "Live" : "Upcoming"}
      </p>

      {noEventLoaded ? (
        <div data-testid="compare-no-event">
          <EmptyState
            message="No event loaded"
            description="Switch the dashboard to Upcoming or Live, or open Lab when the parallel lane is enabled."
            icon={<GitCompare size={24} aria-hidden />}
          />
        </div>
      ) : labOff ? (
        <div className="card" data-testid="compare-lab-off">
          <div className="card-body">
            <p className="text-sm text-[var(--text-secondary)]">
              Lab lane is off or has not produced a board for this event yet, so there is nothing to
              compare. Enable the parallel lab lane (<code>LIVE_REFRESH_LAB_PROFILE_ENABLED=1</code>) and
              wait for the next live-refresh tick. See the Lab page for lane status.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <section className="card" data-testid="compare-pick-overlap">
            <div className="card-header">
              <div className="card-title">Pick overlap (matchups)</div>
            </div>
            <div className="card-body grid grid-cols-1 gap-4 text-center sm:grid-cols-3 sm:gap-3">
              <div>
                <div className="text-2xl font-semibold text-[var(--text-primary)]">{overlap.both.length}</div>
                <div className="text-xs uppercase tracking-wide text-[var(--text-faint)]">Both tracks</div>
              </div>
              <div>
                <div className="text-2xl font-semibold text-[var(--text-primary)]">
                  {overlap.championOnly.length}
                </div>
                <div className="text-xs uppercase tracking-wide text-[var(--text-faint)]">Champion only</div>
              </div>
              <div>
                <div className="text-2xl font-semibold text-[var(--text-primary)]">
                  {overlap.challengerOnly.length}
                </div>
                <div className="text-xs uppercase tracking-wide text-[var(--text-faint)]">Challenger only</div>
              </div>
            </div>
          </section>

          <section className="card" data-testid="compare-rank-deltas">
            <div className="card-header">
              <div className="card-title">Biggest ranking disagreements</div>
              <div className="text-xs text-[var(--text-faint)]">Top {RANK_LIMIT} by |Δ rank|</div>
            </div>
            <div className="card-body overflow-x-auto pb-2 pr-2">
              <table className="compare-rank-table w-full min-w-[480px] text-sm">
                <thead>
                  <tr className="text-left text-[var(--text-faint)]">
                    <th className="min-w-[140px] py-2 pr-4 font-medium">Player</th>
                    <th className="min-w-[88px] py-2 pr-4 font-medium num">Champion #</th>
                    <th className="min-w-[88px] py-2 pr-4 font-medium num">Challenger #</th>
                    <th className="min-w-[56px] py-2 pr-2 font-medium num">Δ</th>
                  </tr>
                </thead>
                <tbody>
                  {rankDeltas.map((row) => (
                    <tr key={row.playerKey} className="border-t border-[var(--border)]">
                      <td
                        className="max-w-[220px] truncate py-2 pr-4 text-[var(--text-secondary)]"
                        title={row.player}
                      >
                        {row.player}
                      </td>
                      <td className="py-2 pr-4 num">{row.championRank ?? "—"}</td>
                      <td className="py-2 pr-4 num">{row.challengerRank ?? "—"}</td>
                      <td
                        className={
                          "py-2 pr-2 num " +
                          (row.delta && row.delta > 0
                            ? "text-[var(--green)]"
                            : row.delta && row.delta < 0
                                ? "text-[var(--red)]"
                                : "text-[var(--text-faint)]")
                        }
                      >
                        {row.delta === null ? "—" : row.delta > 0 ? `+${row.delta}` : row.delta}
                      </td>
                    </tr>
                  ))}
                  {rankDeltas.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-3 text-center text-[var(--text-faint)]">
                        No overlapping ranked players to compare yet.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

export default ComparePage
