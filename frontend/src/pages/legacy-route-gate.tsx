import type { ReactNode } from "react"
import { Link } from "react-router-dom"

import { SectionTitle, SurfaceCard } from "@/components/shell"
import type { PredictionTab } from "@/hooks/use-prediction-tab"

type LegacyReplayBlockedRoute = "players" | "matchups" | "course"

const ROUTE_COPY: Record<LegacyReplayBlockedRoute, { title: string; message: string }> = {
  players: {
    title: "Legacy players route unavailable in replay mode",
    message: "Use the cockpit home route for replay-aware rankings, spotlight, and player context.",
  },
  matchups: {
    title: "Legacy matchups route unavailable in replay mode",
    message: "Use the cockpit home route for stored matchup replay, featured edges, and the full generated picks inventory.",
  },
  course: {
    title: "Legacy course route unavailable in replay mode",
    message: "Use the cockpit home route for replay-aware course context, weather/feed framing, and stored event diagnostics.",
  },
}

export function LegacyRouteGate({
  route,
  mode,
  children,
}: {
  route: LegacyReplayBlockedRoute
  mode: PredictionTab
  children: ReactNode
}) {
  if (mode !== "past") {
    return <>{children}</>
  }

  const copy = ROUTE_COPY[route]

  return (
    <SurfaceCard>
      <SectionTitle
        title={copy.title}
        description="Replay mode is backed by immutable snapshots, while these legacy routes still assume current-event state."
      />
      <div className="space-y-4">
        <div className="rounded-2xl border border-amber-400/20 bg-amber-500/10 px-4 py-4 text-sm leading-6 text-amber-100" role="status">
          {copy.message}
        </div>
        <Link
          to="/"
          className="inline-flex h-8 items-center rounded-lg border border-white/10 bg-white/5 px-3 text-sm font-medium text-white transition hover:bg-white/10"
        >
          Return to cockpit home
        </Link>
      </div>
    </SurfaceCard>
  )
}
