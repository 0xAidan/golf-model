import { useState, type SyntheticEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { NavLink } from "react-router-dom"

import { PREVIEW_ROUTE_MANIFEST, preloadPreviewRoute, prefetchPreviewRoute } from "@/app/operator/route-manifest"
import {
  useOperatorBoardData,
  useOperatorSnapshotMetadata,
} from "@/features/operator-data/operator-data-provider"
import { requestRefreshNow } from "@/features/operator-data/operator-api"

const statusStyles = {
  loading: "border-sky-400/40 bg-sky-400/10 text-sky-100",
  ready: "border-emerald-400/40 bg-emerald-400/10 text-emerald-100",
  stale: "border-amber-400/40 bg-amber-400/10 text-amber-100",
  empty: "border-slate-500/40 bg-slate-800 text-slate-200",
  unavailable: "border-slate-500/40 bg-slate-800 text-slate-200",
  error: "border-red-400/40 bg-red-400/10 text-red-100",
} as const

const titleByState = {
  loading: "Loading operator board",
  ready: "Current operator board",
  stale: "Last known good board",
  empty: "No board rows available",
  unavailable: "Board unavailable",
  error: "Board request failed",
} as const

const getPlayerName = (row: Record<string, unknown>): string =>
  String(row.player_name ?? row.player_display ?? row.player ?? "Unknown player")

export function OperatorApp() {
  const { board, viewState, cacheHydration, error } = useOperatorBoardData()
  const { refresh } = useOperatorSnapshotMetadata()
  const queryClient = useQueryClient()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const refreshMutation = useMutation({
    mutationFn: requestRefreshNow,
    onSuccess: () => {
      refresh()
    },
  })
  const isStaleBoard = viewState === "stale"

  const handleRefreshNow = () => {
    refreshMutation.mutate()
  }

  const handleDetailsToggle = (event: SyntheticEvent<HTMLDetailsElement>) => {
    setDetailsOpen(event.currentTarget.open)
  }

  const handlePreviewRouteIntent = (route: (typeof PREVIEW_ROUTE_MANIFEST)[number]) => {
    preloadPreviewRoute(route)
    void prefetchPreviewRoute(queryClient, route)
  }

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100 sm:px-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <header className="flex flex-col gap-4 border-b border-slate-800 pb-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-300">Operator preview</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Recovery data shell</h1>
            <p className="mt-2 text-sm text-slate-400">
              {board?.event.event_name ?? "No event selected"}{board?.event.course_name ? ` · ${board.event.course_name}` : ""}
            </p>
          </div>
          <button
            type="button"
            className="min-h-11 rounded-md bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 active:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={handleRefreshNow}
            disabled={refreshMutation.isPending}
            aria-busy={refreshMutation.isPending}
          >
            {refreshMutation.isPending ? "Refreshing…" : "Refresh now"}
          </button>
        </header>

        <nav className="flex gap-2" aria-label="Operator preview routes">
          {PREVIEW_ROUTE_MANIFEST.map((route) => (
            <NavLink
              key={route.id}
              to={route.path}
              onMouseEnter={() => {
                handlePreviewRouteIntent(route)
              }}
              onFocus={() => {
                handlePreviewRouteIntent(route)
              }}
              onClick={() => {
                handlePreviewRouteIntent(route)
              }}
              className={({ isActive }) =>
                `min-h-11 rounded-md border px-4 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 ${
                  isActive
                    ? "border-emerald-400/60 bg-emerald-400/10 text-emerald-200"
                    : "border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-500 hover:text-white active:bg-slate-800"
                }`
              }
            >
              {route.id === "dashboard" ? "Dashboard" : "Lab"}
            </NavLink>
          ))}
        </nav>

        <section className={`rounded-lg border p-6 ${statusStyles[viewState]}`} aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.14em]">{viewState}</p>
              <h2 className="mt-1 text-xl font-semibold">{titleByState[viewState]}</h2>
              <p className="mt-2 max-w-2xl text-sm opacity-90">
                {cacheHydration === "pending"
                  ? "Checking locally retained operator data."
                  : isStaleBoard
                    ? `Showing retained snapshot ${board?.source.snapshot_id ?? "unknown"} — it is not current.`
                    : board?.reason.message ?? error?.message ?? "No operator data is available."}
              </p>
            </div>
            {board?.source.generated_at ? (
              <p className="font-mono text-xs opacity-80">snapshot {board.source.snapshot_id ?? "unknown"}</p>
            ) : null}
          </div>
          {refreshMutation.isError ? (
            <p className="mt-4 text-sm text-red-100">Refresh request failed. {String(refreshMutation.error)}</p>
          ) : null}
        </section>

        {viewState === "ready" || viewState === "stale" ? (
          <>
            <section className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900">
              <div className="border-b border-slate-800 px-6 py-4">
                <h2 className="text-lg font-semibold">Rankings</h2>
                <p className="mt-1 text-sm text-slate-400">
                  {isStaleBoard ? "Retained rows, explicitly stale." : "Current Champion or Challenger board rows."}
                </p>
              </div>
              <ul className="divide-y divide-slate-800">
                {board?.rankings.slice(0, 12).map((row, index) => (
                  <li key={`${getPlayerName(row)}-${index}`} className="flex items-center justify-between px-6 py-4">
                    <span className="font-medium">{getPlayerName(row)}</span>
                    <span className="font-mono text-sm text-slate-400">#{String(row.rank ?? index + 1)}</span>
                  </li>
                ))}
              </ul>
            </section>

            <details className="rounded-lg border border-slate-800 bg-slate-900" onToggle={handleDetailsToggle}>
              <summary className="min-h-11 cursor-pointer px-6 py-4 text-sm font-semibold text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-300">
                Expand pick payloads
              </summary>
              {detailsOpen ? (
                <div className="border-t border-slate-800 p-6">
                  <p className="text-sm text-slate-400">
                    Matchups: {board?.picks.matchups.length ?? 0} · Value bets: {board?.picks.value_bets.length ?? 0}
                  </p>
                </div>
              ) : null}
            </details>
          </>
        ) : null}
      </div>
    </main>
  )
}
