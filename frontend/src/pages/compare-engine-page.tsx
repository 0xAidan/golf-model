import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import ReactECharts from "echarts-for-react"

import { PageEnter, Reveal, Stagger, StaggerItem } from "@/components/motion/primitives"
import { SkeletonPanelRows } from "@/components/motion/skeletons"
import { PageHeader } from "@/components/ui/page-header"
import { api } from "@/lib/api"
import { getChartPalette, getEchartsAxisStyle, getEchartsTooltipStyle } from "@/lib/chart-theme"
import type { PairwiseCompare, SgWindowValue } from "@/lib/types"

/**
 * CompareEnginePage — pick any two players and see everything
 * overlaid: SG trajectories, latest skill windows, graded
 * head-to-head record, and a model verdict.
 */
export function CompareEnginePage() {
  const [playerA, setPlayerA] = useState("")
  const [playerB, setPlayerB] = useState("")

  const enabled = playerA.length > 0 && playerB.length > 0 && playerA !== playerB
  const query = useQuery({
    queryKey: ["redesign-compare", playerA, playerB],
    queryFn: () => api.redesign.comparePlayers(playerA, playerB),
    enabled,
    staleTime: 120_000,
  })

  return (
    <div
      className="monitor-research-page monitor-scroll-region product-page--satellite"
      data-testid="compare-engine-page"
    >
      <div className="px-5 pt-5">
        <PageHeader
          eyebrow="Head to head"
          title="Compare players"
          description="Overlay two players' form, skills, and the model's graded history between them."
        />
        <PlayerPickers
          valueA={playerA}
          valueB={playerB}
          onChangeA={setPlayerA}
          onChangeB={setPlayerB}
        />
      </div>

      <div className="px-5 pb-5 pt-4">
        {!enabled ? (
          <div className="panel p-8 text-center text-sm text-[var(--text-muted)]" data-testid="compare-empty">
            Pick two different players above to run the comparison.
          </div>
        ) : query.isLoading ? (
          <div className="panel p-5">
            <SkeletonPanelRows rows={5} />
          </div>
        ) : query.isError || !query.data ? (
          <div className="panel p-5 text-sm text-[var(--text-muted)]" data-testid="compare-error">
            Comparison failed to load. Try again.
          </div>
        ) : (
          <ComparePanels data={query.data} playerA={playerA} playerB={playerB} />
        )}
      </div>
    </div>
  )
}

function PlayerPickers({
  valueA,
  valueB,
  onChangeA,
  onChangeB,
}: {
  valueA: string
  valueB: string
  onChangeA: (value: string) => void
  onChangeB: (value: string) => void
}) {
  const searchA = useQuery({
    queryKey: ["player-search-a", ""],
    queryFn: () => api.searchPlayers(""),
    staleTime: 10 * 60_000,
  })
  const options = searchA.data?.players ?? []

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2" data-testid="compare-pickers">
      <PlayerPicker label="Player A" accent="var(--chart-c1)" value={valueA} onChange={onChangeA} options={options.map((p) => ({ key: p.player_key, name: p.player_display }))} />
      <PlayerPicker label="Player B" accent="var(--chart-c2)" value={valueB} onChange={onChangeB} options={options.map((p) => ({ key: p.player_key, name: p.player_display }))} />
    </div>
  )
}

function PlayerPicker({
  label,
  accent,
  value,
  onChange,
  options,
}: {
  label: string
  accent: string
  value: string
  onChange: (value: string) => void
  options: Array<{ key: string; name: string }>
}) {
  const [filter, setFilter] = useState("")
  const filtered = useMemo(
    () =>
      options
        .filter((option) =>
          filter.length === 0
            ? true
            : option.name.toLowerCase().includes(filter.toLowerCase()) ||
              option.key.toLowerCase().includes(filter.toLowerCase()),
        )
        .slice(0, 60),
    [options, filter],
  )

  return (
    <label className="panel block px-4 py-3">
      <span className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: accent }} aria-hidden />
        {label}
      </span>
      <input
        type="search"
        className="w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-sm text-[var(--text)] outline-none focus:border-[var(--accent-focus)]"
        placeholder="Filter players…"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        data-testid={`compare-filter-${label.slice(-1)}`}
      />
      <select
        className="mt-2 w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm text-[var(--text)]"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label={`${label} select`}
        data-testid={`compare-select-${label.slice(-1)}`}
      >
        <option value="">Select…</option>
        {filtered.map((option) => (
          <option key={option.key} value={option.key}>
            {option.name}
          </option>
        ))}
      </select>
    </label>
  )
}

function ComparePanels({
  data,
  playerA,
  playerB,
}: {
  data: PairwiseCompare
  playerA: string
  playerB: string
}) {
  return (
    <Stagger className="flex flex-col gap-4">
      <StaggerItem>
        <TrajectoryPanel data={data} playerA={playerA} playerB={playerB} />
      </StaggerItem>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <StaggerItem>
          <SkillDiffPanel data={data} />
        </StaggerItem>
        <StaggerItem>
          <H2HPanel data={data} playerA={playerA} playerB={playerB} />
        </StaggerItem>
      </div>
    </Stagger>
  )
}

function TrajectoryPanel({
  data,
  playerA,
  playerB,
}: {
  data: PairwiseCompare
  playerA: string
  playerB: string
}) {
  const palette = getChartPalette()
  const tooltip = getEchartsTooltipStyle()
  const axis = getEchartsAxisStyle()

  // Oldest → newest per side, aligned by event order (not date-paired).
  const seriesFor = (key: "a" | "b") => {
    const rows = [...data[key].trend].reverse()
    return {
      name: key === "a" ? playerA : playerB,
      data: rows.map((row) => row.sg_total),
    }
  }

  const sA = seriesFor("a")
  const sB = seriesFor("b")
  const maxLen = Math.max(sA.data.length, sB.data.length)

  if (maxLen === 0) {
    return (
      <div className="panel p-5 text-sm text-[var(--text-muted)]">No round history for this pairing yet.</div>
    )
  }

  return (
    <Reveal>
      <div className="panel">
        <div className="panel__header">
          <span className="panel__title">SG total trajectory — last {maxLen} rounds</span>
        </div>
        <div className="px-3 pb-3 pt-1">
          <ReactECharts
            style={{ height: 280 }}
            notMerge
            option={{
              animation: true,
              animationDuration: 600,
              grid: { top: 16, right: 16, bottom: 28, left: 40 },
              legend: {
                data: [sA.name, sB.name],
                textStyle: { color: tooltip.textStyle.color, fontSize: 11 },
                top: 0,
                right: 0,
              },
              xAxis: { type: "category", boundaryGap: false, ...axis },
              yAxis: { type: "value", scale: true, ...axis },
              tooltip: { trigger: "axis", ...tooltip },
              series: [
                {
                  name: sA.name,
                  type: "line",
                  data: sA.data,
                  smooth: 0.35,
                  showSymbol: false,
                  connectNulls: true,
                  lineStyle: { width: 2.5, color: palette[0] },
                  itemStyle: { color: palette[0] },
                },
                {
                  name: sB.name,
                  type: "line",
                  data: sB.data,
                  smooth: 0.35,
                  showSymbol: false,
                  connectNulls: true,
                  lineStyle: { width: 2.5, color: palette[1] },
                  itemStyle: { color: palette[1] },
                },
              ],
            }}
          />
        </div>
      </div>
    </Reveal>
  )
}

function SkillDiffPanel({ data }: { data: PairwiseCompare }) {
  const latest = (rows: SgWindowValue[], metric: string): number | null => {
    for (const row of rows) {
      if (row.metric_name === metric && row.metric_value != null) return row.metric_value
    }
    return null
  }

  const metrics = [
    { key: "sg_ott", label: "OTT" },
    { key: "sg_app", label: "APP" },
    { key: "sg_arg", label: "ARG" },
    { key: "sg_putt", label: "PUTT" },
    { key: "sg_total", label: "TOTAL" },
  ]

  return (
    <div className="panel h-full" data-testid="compare-skill-diff">
      <div className="panel__header">
        <span className="panel__title">Latest skill windows</span>
      </div>
      <ul className="divide-y divide-[var(--divider)]">
        {metrics.map((metric) => {
          const aVal = latest(data.a.sg, metric.key)
          const bVal = latest(data.b.sg, metric.key)
          const leader =
            aVal == null || bVal == null ? null : aVal === bVal ? "tie" : aVal > bVal ? "a" : "b"
          return (
            <li key={metric.key} className="grid grid-cols-[4rem_1fr_4rem] items-center gap-3 px-5 py-2.5 text-sm">
              <span className="num font-semibold text-[var(--text)]">{aVal != null ? aVal.toFixed(2) : "—"}</span>
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{metric.label}</span>
                {leader ? (
                  <span
                    className={
                      leader === "a"
                        ? "h-1.5 w-8 rounded-full bg-[var(--chart-c1)]"
                        : leader === "b"
                          ? "ml-auto h-1.5 w-8 rounded-full bg-[var(--chart-c2)]"
                          : ""
                    }
                    aria-label={leader === "tie" ? "Even" : `${leader} leads`}
                  />
                ) : null}
              </div>
              <span className="num text-right font-semibold text-[var(--text)]">{bVal != null ? bVal.toFixed(2) : "—"}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function H2HPanel({
  data,
  playerA,
  playerB,
}: {
  data: PairwiseCompare
  playerA: string
  playerB: string
}) {
  const h2h = data.head_to_head
  const total = h2h.a_wins + h2h.b_wins

  return (
    <div className="panel flex h-full flex-col" data-testid="compare-h2h">
      <div className="panel__header">
        <span className="panel__title">Graded head-to-head</span>
        <span className="text-xs text-[var(--text-faint)]">{h2h.graded} model picks</span>
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6">
        {total === 0 ? (
          <p className="text-center text-sm text-[var(--text-muted)]">{h2h.note}</p>
        ) : (
          <>
            <div className="flex w-full items-center justify-between text-sm">
              <span className="num font-bold text-[var(--chart-c1)]">{h2h.a_wins}</span>
              <span className="text-xs uppercase tracking-widest text-[var(--text-faint)]">wins</span>
              <span className="num font-bold text-[var(--chart-c2)]">{h2h.b_wins}</span>
            </div>
            <div className="flex h-2.5 w-full overflow-hidden rounded-full">
              <div
                className="h-full bg-[var(--chart-c1)] transition-all"
                style={{ width: `${(h2h.a_wins / total) * 100}%` }}
              />
              <div
                className="h-full bg-[var(--chart-c2)] transition-all"
                style={{ width: `${(h2h.b_wins / total) * 100}%` }}
              />
            </div>
            <p className="text-center text-xs text-[var(--text-faint)]">{h2h.note}</p>
          </>
        )}
      </div>
    </div>
  )
}
