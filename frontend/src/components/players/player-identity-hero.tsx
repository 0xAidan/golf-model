import { Copy, ExternalLink } from "lucide-react"

import type { EventCommandKpi } from "@/components/product/event-command-header"
import type { CompositePlayer, StandalonePlayerProfile } from "@/lib/types"
import { cn } from "@/lib/utils"

const signed = (v?: number | null, d = 2) => {
  if (v == null) return "—"
  return `${v > 0 ? "+" : ""}${v.toFixed(d)}`
}

const tone = (v?: number | null): "positive" | "negative" | "neutral" => {
  if (v == null) return "neutral"
  return v > 0 ? "positive" : v < 0 ? "negative" : "neutral"
}

export const PlayerIdentityHero = ({
  standalone,
  modelPlayer,
  playerKey,
}: {
  standalone?: StandalonePlayerProfile
  modelPlayer?: CompositePlayer
  playerKey: string
}) => {
  if (!standalone) return null

  const handleCopyKey = async () => {
    try {
      await navigator.clipboard.writeText(playerKey)
    } catch {
      /* ignore */
    }
  }

  const kpis: EventCommandKpi[] = [
    {
      id: "dg-rank",
      label: "DG Rank",
      value: standalone.header.dg_rank ? `#${standalone.header.dg_rank}` : "—",
    },
    {
      id: "owgr",
      label: "OWGR",
      value: standalone.header.owgr_rank ? `#${standalone.header.owgr_rank}` : "—",
    },
    {
      id: "dg-skill",
      label: "DG Skill",
      value: standalone.header.dg_skill_estimate != null ? signed(standalone.header.dg_skill_estimate) : "—",
      tone: tone(standalone.header.dg_skill_estimate),
    },
    {
      id: "total-sg",
      label: "Total SG",
      value: standalone.sg_skills.sg_total != null ? signed(standalone.sg_skills.sg_total, 3) : "—",
      tone: tone(standalone.sg_skills.sg_total),
    },
    {
      id: "model-rank",
      label: "Model Rank",
      value: modelPlayer ? `#${modelPlayer.rank}` : "—",
      tone: modelPlayer ? "positive" : "neutral",
    },
    {
      id: "composite",
      label: "Composite",
      value: modelPlayer ? modelPlayer.composite.toFixed(1) : "—",
      tone: modelPlayer ? "positive" : "neutral",
    },
  ]

  return (
    <header className="players-identity-hero" data-testid="players-identity-hero">
      <div className="players-identity-hero__top">
        <div>
          <p className="players-identity-hero__eyebrow">Player profile</p>
          <h2 className="players-identity-hero__name">{standalone.player_display}</h2>
          {standalone.header.primary_tour ? (
            <p className="players-identity-hero__tour">{standalone.header.primary_tour}</p>
          ) : null}
        </div>
        <div className="players-identity-hero__actions">
          <a
            href={`/?player=${encodeURIComponent(playerKey)}`}
            className="players-identity-hero__action"
            data-testid="players-view-dashboard"
          >
            <ExternalLink size={14} aria-hidden />
            Dashboard
          </a>
          <button
            type="button"
            className="players-identity-hero__action"
            onClick={handleCopyKey}
            aria-label="Copy player key"
            data-testid="players-copy-key"
          >
            <Copy size={14} aria-hidden />
            Key
          </button>
        </div>
      </div>

      <div className="players-identity-hero__pills">
        {standalone.has_skill_data ? (
          <span className="players-identity-hero__pill players-identity-hero__pill--good">DG Skills</span>
        ) : null}
        {standalone.has_ranking_data ? (
          <span className="players-identity-hero__pill players-identity-hero__pill--good">Rankings</span>
        ) : null}
        {standalone.has_approach_data ? (
          <span className="players-identity-hero__pill players-identity-hero__pill--good">Approach</span>
        ) : null}
        {!standalone.has_skill_data && !standalone.has_ranking_data ? (
          <span className="players-identity-hero__pill players-identity-hero__pill--warn">Limited DG data</span>
        ) : null}
      </div>

      <div className="players-identity-hero__kpis" data-testid="players-identity-kpis">
        {kpis.map((kpi) => (
          <div key={kpi.id} className="players-identity-hero__kpi">
            <div className="players-identity-hero__kpi-label">{kpi.label}</div>
            <div
              className={cn(
                "players-identity-hero__kpi-value num",
                kpi.tone === "positive" && "metric--positive",
                kpi.tone === "negative" && "metric--negative",
              )}
            >
              {kpi.value}
            </div>
          </div>
        ))}
      </div>
    </header>
  )
}
