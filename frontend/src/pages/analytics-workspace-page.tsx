import { useCallback, useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"

import { HeroDataGrid } from "@/components/monitoring/hero-data-grid"
import { MacroKpiStrip } from "@/components/monitoring/macro-kpi-strip"
import { BentoGrid, BentoPanel } from "@/components/monitoring"
import { Button } from "@/components/ui/button"
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

const DEFAULT_PARAMS: Record<string, string> = {
  lane: "cockpit",
  season: "2026",
}

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
  { accessorKey: "player_display", header: "Player" },
  { accessorKey: "bet_type", header: "Market" },
  { accessorKey: "book", header: "Book" },
  {
    accessorKey: "ev",
    header: "EV",
    cell: ({ getValue }) => {
      const v = Number(getValue() ?? 0)
      return <span className="num">{(v * 100).toFixed(1)}%</span>
    },
  },
  {
    accessorKey: "profit",
    header: "Units",
    cell: ({ getValue }) => {
      const v = getValue()
      if (v == null) return <span className="num num-faint">—</span>
      return <span className="num">{Number(v).toFixed(2)}</span>
    },
  },
  { accessorKey: "event_name", header: "Event" },
]

export function AnalyticsWorkspacePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [filters, setFilters] = useState(() => readParamsFromUrl(searchParams))
  const [presets, setPresets] = useLocalStorageState<AnalyticsPreset[]>(PRESETS_KEY, [])
  const [presetName, setPresetName] = useState("")
  const [drawerPlayer, setDrawerPlayer] = useState<string | null>(null)

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
    queryKey: ["analytics-picks", queryParams, drawerPlayer],
    queryFn: () =>
      api.getAnalyticsPicks({
        ...queryParams,
        player: drawerPlayer ?? queryParams.player,
        limit: 200,
        offset: 0,
      }),
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
    const csv = await api.exportAnalyticsCsv(queryParams)
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

  return (
    <div className="monitor-scroll-region px-5 pb-8" data-testid="analytics-workspace">
      <div className="flex flex-wrap items-end gap-3 py-4">
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
      </div>

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
          { id: "picks", label: "Picks", value: String(kpis?.pick_count ?? "—") },
          { id: "units", label: "Units", value: kpis ? kpis.profit_units.toFixed(2) : "—" },
          { id: "roi", label: "ROI", value: kpis ? `${kpis.roi_pct.toFixed(1)}%` : "—" },
          { id: "win", label: "Win rate", value: kpis ? `${kpis.win_rate_pct.toFixed(1)}%` : "—" },
        ]}
      />

      <BentoGrid columns={2} className="mt-4">
        <BentoPanel title="By event" span={6}>
          <div className="overflow-x-auto text-sm">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="text-left py-1">Event</th>
                  <th className="text-right py-1">Units</th>
                  <th className="text-right py-1">ROI</th>
                </tr>
              </thead>
              <tbody>
                {(rollupQuery.data?.rows ?? []).slice(0, 12).map((row) => (
                  <tr
                    key={String(row.group_key)}
                    className="cursor-pointer hover:bg-[var(--surface-2)]"
                    onClick={() => syncUrl({ ...filters, event_id: String(row.group_key) })}
                  >
                    <td className="py-1">
                      {String(row.group_label ?? row.group_key)}
                    </td>
                    <td className="text-right num py-1">{Number(row.profit ?? 0).toFixed(2)}</td>
                    <td className="text-right num py-1">{Number(row.roi_pct ?? 0).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </BentoPanel>

        <BentoPanel title="Pick ledger" span={6}>
          <HeroDataGrid
            data={picksQuery.data?.picks ?? []}
            columns={ledgerColumns}
            getRowId={(row) => String(row.pick_key ?? row.player_key ?? row.player_display)}
            onRowClick={(row) => setDrawerPlayer(String(row.player_key ?? row.player_display ?? ""))}
            emptyMessage="No picks match filters"
          />
        </BentoPanel>
      </BentoGrid>

      {drawerPlayer ? (
        <div
          className="fixed inset-y-0 right-0 z-50 w-full max-w-md border-l border-[var(--border)] bg-[var(--surface)] p-4 shadow-xl"
          role="dialog"
          aria-label="Player pick history"
          data-testid="player-pick-drawer"
        >
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold">{drawerPlayer}</h3>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDrawerPlayer(null)}>
              Close
            </button>
          </div>
          <Link
            to={`/players/${encodeURIComponent(drawerPlayer)}`}
            className="link-subtle text-sm"
          >
            Open full profile
          </Link>
          <ul className="mt-4 space-y-2 text-sm max-h-[70vh] overflow-y-auto">
            {(picksQuery.data?.picks ?? [])
              .filter((p) => String(p.player_key ?? p.player_display) === drawerPlayer)
              .map((p) => (
                <li key={String(p.pick_key)} className="border-b border-[var(--border)] pb-2">
                  {String(p.bet_type)} · {String(p.book)} · EV{" "}
                  <span className="num">{(Number(p.ev ?? 0) * 100).toFixed(1)}%</span>
                </li>
              ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
