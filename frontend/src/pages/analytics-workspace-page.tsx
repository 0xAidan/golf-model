import { useCallback, useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"

import { HeroDataGrid } from "@/components/monitoring/hero-data-grid"
import { MacroKpiStrip } from "@/components/monitoring/macro-kpi-strip"
import { BentoGrid, BentoPanel } from "@/components/monitoring"
import { Button } from "@/components/ui/button"
import { FilterBar } from "@/components/ui/filter-bar"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { api } from "@/lib/api"
import { useLocalStorageState } from "@/lib/storage"
import { cn } from "@/lib/utils"

const PRESETS_KEY = "golf.analytics.presets"

type AnalyticsPreset = {
  id: string
  name: string
  params: Record<string, string>
}

type LedgerRow = Record<string, unknown>
type RollupRow = Record<string, unknown>
type DrawerPlayer = {
  playerKey: string
  label: string
}

const DEFAULT_PARAMS: Record<string, string> = {
  lane: "cockpit",
  season: "2026",
}

const LEDGER_LIMIT = 200

const readParamsFromUrl = (searchParams: URLSearchParams): Record<string, string> => {
  const keys = [
    "lane",
    "season",
    "book",
    "bet_type",
    "event_id",
    "player",
    "ev_min",
    "ev_max",
    "outcome",
    "confidence",
    "from",
    "to",
  ]
  const out: Record<string, string> = { ...DEFAULT_PARAMS }
  keys.forEach((key) => {
    const v = searchParams.get(key)
    if (v) out[key] = v
  })
  return out
}

const ledgerColumns: ColumnDef<LedgerRow>[] = [
  {
    accessorKey: "player_display",
    header: "Player",
    meta: { sticky: true, label: "Player" },
  },
  { accessorKey: "bet_type", header: "Market", meta: { label: "Market" } },
  { accessorKey: "book", header: "Book", meta: { label: "Book" } },
  {
    accessorKey: "ev",
    header: "EV",
    meta: { align: "right", mono: true, label: "EV" },
    cell: ({ getValue }) => {
      const v = Number(getValue() ?? 0)
      return <span className="num">{(v * 100).toFixed(1)}%</span>
    },
  },
  {
    accessorKey: "profit",
    header: "Units",
    meta: { align: "right", mono: true, label: "Units" },
    cell: ({ getValue }) => {
      const v = getValue()
      if (v == null) return <span className="num num-faint">—</span>
      return <span className="num">{Number(v).toFixed(2)}</span>
    },
  },
  { accessorKey: "event_name", header: "Event", meta: { label: "Event" } },
]

const rollupColumns: ColumnDef<RollupRow>[] = [
  {
    accessorKey: "group_label",
    header: "Event",
    meta: { sticky: true, label: "Event" },
    cell: ({ row, getValue }) => String(getValue() ?? row.original.group_key ?? "Unknown event"),
  },
  {
    accessorKey: "count",
    header: "Picks",
    meta: { align: "right", mono: true, label: "Picks" },
    cell: ({ getValue }) => <span className="num">{Number(getValue() ?? 0)}</span>,
  },
  {
    accessorKey: "profit",
    header: "Units",
    meta: { align: "right", mono: true, label: "Units" },
    cell: ({ getValue }) => <span className="num">{Number(getValue() ?? 0).toFixed(2)}</span>,
  },
  {
    accessorKey: "roi_pct",
    header: "ROI",
    meta: { align: "right", mono: true, label: "ROI" },
    cell: ({ getValue }) => <span className="num">{Number(getValue() ?? 0).toFixed(1)}%</span>,
  },
]

function hasNarrowingFilters(filters: Record<string, string>): boolean {
  return Boolean(
    filters.book ||
      filters.bet_type ||
      filters.player ||
      filters.ev_min ||
      filters.ev_max ||
      filters.outcome ||
      filters.confidence ||
      filters.from ||
      filters.to,
  )
}

export function AnalyticsWorkspacePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [filters, setFilters] = useState(() => readParamsFromUrl(searchParams))
  const [presets, setPresets] = useLocalStorageState<AnalyticsPreset[]>(PRESETS_KEY, [])
  const [presetName, setPresetName] = useState("")
  const [drawerPlayer, setDrawerPlayer] = useState<DrawerPlayer | null>(null)

  useEffect(() => {
    setFilters(readParamsFromUrl(searchParams))
  }, [searchParams])

  const syncUrl = useCallback(
    (next: Record<string, string>) => {
      const params = new URLSearchParams()
      params.set("tab", "analytics")
      Object.entries(next).forEach(([k, v]) => {
        if (v) params.set(k, v)
      })
      setSearchParams(params, { replace: true })
      setFilters(next)
    },
    [setSearchParams],
  )

  const queryParams = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(filters).map(([k, v]) => [k, v === "" ? undefined : v]),
      ),
    [filters],
  )

  const summaryQuery = useQuery({
    queryKey: ["analytics-summary", queryParams],
    queryFn: () => api.getAnalyticsSummary(queryParams),
  })

  const dashboardQuery = useQuery({
    queryKey: ["dashboard-state"],
    queryFn: api.getDashboardState,
    staleTime: 60_000,
  })

  const picksQuery = useQuery({
    queryKey: ["analytics-picks", queryParams],
    queryFn: () =>
      api.getAnalyticsPicks({
        ...queryParams,
        limit: LEDGER_LIMIT,
        offset: 0,
      }),
  })

  const playerHistoryQuery = useQuery({
    queryKey: ["analytics-player-history", queryParams, drawerPlayer?.playerKey],
    queryFn: () =>
      api.getAnalyticsPicks({
        ...queryParams,
        player: drawerPlayer?.playerKey,
        limit: LEDGER_LIMIT,
        offset: 0,
      }),
    enabled: drawerPlayer != null,
  })

  const rollupQuery = useQuery({
    queryKey: ["analytics-rollup", queryParams],
    queryFn: () =>
      api.getAnalyticsRollup({
        group_by: "event",
        season: queryParams.season,
        lane: queryParams.lane,
        book: queryParams.book,
        bet_type: queryParams.bet_type,
        ev_min: queryParams.ev_min,
      }),
  })

  useEffect(() => {
    if (filters.event_id) return
    const latest = dashboardQuery.data?.latest_completed_event?.event_id
    if (!latest) return
    syncUrl({ ...filters, event_id: String(latest) })
  }, [dashboardQuery.data?.latest_completed_event?.event_id, filters, syncUrl])

  const handleExportCsv = async () => {
    const csv = await api.exportAnalyticsCsv({
      ...queryParams,
      limit: picksQuery.data?.picks.length ?? LEDGER_LIMIT,
      offset: 0,
    })
    const blob = new Blob([csv], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "analytics-picks.csv"
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleSavePreset = () => {
    const name = presetName.trim()
    if (!name) return
    const id = `${name}-${Date.now()}`
    setPresets([...presets.filter((p) => p.name !== name), { id, name, params: filters }])
    setPresetName("")
  }

  const kpis = summaryQuery.data
  const filterMismatch = hasNarrowingFilters(filters)
  const rollupEmptyMessage = filterMismatch
    ? "No events match the current filters."
    : "No graded picks available for this selection yet."
  const ledgerEmptyMessage = filterMismatch
    ? "No picks match the current filters."
    : "No graded picks available for this selection yet."

  return (
    <div className="monitor-scroll-region px-5 pb-8" data-testid="analytics-workspace">
      <FilterBar className="flex flex-wrap items-end gap-3 py-4" aria-label="Analytics filters">
        <label className="flex min-w-[7rem] flex-col gap-1 text-xs">
          Season
          <input
            className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm num"
            value={filters.season ?? DEFAULT_PARAMS.season}
            onChange={(e) => syncUrl({ ...filters, season: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Lane
          <select
            className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
            value={filters.lane ?? "cockpit"}
            onChange={(e) => syncUrl({ ...filters, lane: e.target.value })}
          >
            <option value="cockpit">Dashboard</option>
            <option value="lab">Lab</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Book
          <input
            className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
            value={filters.book ?? ""}
            placeholder="draftkings or dk"
            onChange={(e) => syncUrl({ ...filters, book: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Market
          <input
            className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
            value={filters.bet_type ?? ""}
            placeholder="optional"
            onChange={(e) => syncUrl({ ...filters, bet_type: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          EV min
          <input
            className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm num"
            value={filters.ev_min ?? ""}
            placeholder="optional"
            onChange={(e) => syncUrl({ ...filters, ev_min: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Event ID
          <input
            className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
            value={filters.event_id ?? ""}
            onChange={(e) => syncUrl({ ...filters, event_id: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Player
          <input
            className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
            value={filters.player ?? ""}
            placeholder="optional"
            onChange={(e) => syncUrl({ ...filters, player: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          From
          <input
            className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
            type="date"
            value={filters.from ?? ""}
            onChange={(e) => syncUrl({ ...filters, from: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          To
          <input
            className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
            type="date"
            value={filters.to ?? ""}
            onChange={(e) => syncUrl({ ...filters, to: e.target.value })}
          />
        </label>
        <Button type="button" variant="outline" size="sm" onClick={() => void handleExportCsv()}>
          Export CSV
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => syncUrl({ ...DEFAULT_PARAMS })}
        >
          Clear filters
        </Button>
      </FilterBar>

      <div className="mb-4 flex flex-wrap gap-2 items-center">
        <input
          className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-sm"
          placeholder="Preset name"
          value={presetName}
          onChange={(e) => setPresetName(e.target.value)}
        />
        <Button type="button" size="sm" variant="secondary" onClick={handleSavePreset}>
          Save preset
        </Button>
        {presets.map((p) => (
          <button
            key={p.id}
            type="button"
            className={cn(
              "rounded-md border px-2 py-1 text-xs",
              "border-[var(--border)] hover:border-[var(--green)]",
            )}
            onClick={() => syncUrl(p.params)}
          >
            {p.name}
          </button>
        ))}
      </div>

      <MacroKpiStrip
        items={[
          {
            id: "units",
            label: "Units",
            value: kpis?.profit_units ?? "—",
            tone: kpis && kpis.profit_units > 0 ? "positive" : kpis && kpis.profit_units < 0 ? "negative" : "neutral",
          },
          { id: "roi", label: "ROI", value: kpis?.roi_pct ?? "—", suffix: kpis ? "%" : undefined },
          { id: "picks", label: "Picks", value: kpis?.pick_count ?? "—" },
          { id: "win", label: "Win rate", value: kpis?.win_rate_pct ?? "—", suffix: kpis ? "%" : undefined },
        ]}
      />

      <BentoGrid columns={2} className="mt-4">
        <BentoPanel title="By event" span={6}>
          <HeroDataGrid
            data={(rollupQuery.data?.rows ?? []).slice(0, 12)}
            columns={rollupColumns}
            getRowId={(row) => String(row.group_key ?? row.group_label ?? "rollup-row")}
            onRowClick={(row) => syncUrl({ ...filters, event_id: String(row.group_key ?? "") })}
            emptyMessage={rollupEmptyMessage}
            isLoading={rollupQuery.isLoading}
            loadingMessage="Loading event rollup…"
            testId="analytics-rollup-grid"
          />
        </BentoPanel>

        <BentoPanel title="Pick ledger" span={6}>
          <HeroDataGrid
            data={picksQuery.data?.picks ?? []}
            columns={ledgerColumns}
            getRowId={(row) => String(row.pick_key ?? row.player_key ?? row.player_display)}
            onRowClick={(row) =>
              setDrawerPlayer({
                playerKey: String(row.player_key ?? row.player_display ?? ""),
                label: String(row.player_display ?? row.player_key ?? "Player history"),
              })
            }
            emptyMessage={ledgerEmptyMessage}
            isLoading={picksQuery.isLoading}
            loadingMessage="Loading pick ledger…"
            testId="analytics-ledger-grid"
          />
        </BentoPanel>
      </BentoGrid>

      <Sheet open={drawerPlayer != null} onOpenChange={(open) => !open && setDrawerPlayer(null)}>
        <SheetContent
          side="right"
          className="w-full max-w-md border-l border-[var(--border)] bg-[var(--surface)]"
          data-testid="player-pick-drawer"
        >
          <SheetHeader>
            <SheetTitle>{drawerPlayer?.label ?? "Player pick history"}</SheetTitle>
            <SheetDescription>
              Matching picks from the current analytics filters for this player.
            </SheetDescription>
          </SheetHeader>
          {drawerPlayer ? (
            <div className="flex min-h-0 flex-1 flex-col gap-4 px-4 pb-4">
              <Link
                to={`/players/${encodeURIComponent(drawerPlayer.playerKey)}`}
                className="link-subtle text-sm"
              >
                Open full profile
              </Link>
              <HeroDataGrid
                data={playerHistoryQuery.data?.picks ?? []}
                columns={ledgerColumns}
                getRowId={(row) => String(row.pick_key ?? row.player_key ?? row.player_display)}
                emptyMessage="No pick history matches the current filters."
                isLoading={playerHistoryQuery.isLoading}
                loadingMessage="Loading player history…"
                testId="analytics-player-history-grid"
              />
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  )
}
