import { ActivitySquare, Layers3, Radar, ScanSearch, Trophy } from "lucide-react"

import { PlayerProfileSections } from "@/components/player-profile-sections"
import { MetricTile } from "@/components/shell"
import type { CockpitSpotlightModel } from "@/lib/cockpit-spotlight"
import type { CompositePlayer, PlayerProfile } from "@/lib/types"

export function PlayerSpotlightPanel({
  spotlight,
  player,
  profile,
  profileReady,
  richProfilesEnabled,
}: {
  spotlight: CockpitSpotlightModel | null
  player: CompositePlayer | null
  profile?: PlayerProfile
  profileReady: boolean
  richProfilesEnabled: boolean
}) {
  if (!spotlight) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 bg-black/15 px-4 py-8 text-center text-sm text-slate-400">
        Select a player from rankings, leaderboard, featured plays, or generated picks to load the shared spotlight.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
              {spotlight.modeLabel} spotlight
            </p>
            <h4 className="mt-1 text-2xl font-semibold text-white">{spotlight.playerName}</h4>
            <p className="mt-2 max-w-xl text-sm leading-6 text-slate-300">{spotlight.narrative}</p>
          </div>
          <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-cyan-100">
            {spotlight.eventName}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {spotlight.sourceBadges.map((badge) => (
            <span
              key={badge}
              className="rounded-full border border-white/10 bg-white/6 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-300"
            >
              {badge}
            </span>
          ))}
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {spotlight.headerStats.map((item) => (
            <MetricTile
              key={item.label}
              label={item.label}
              value={item.value}
              detail={item.detail}
              tone={item.tone}
            />
          ))}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {spotlight.summaryStats.map((item) => (
          <MetricTile
            key={item.label}
            label={item.label}
            value={item.value}
            detail={item.detail}
            tone={item.tone}
          />
        ))}
      </div>

      <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
        <div className="mb-3 flex items-center gap-2 text-slate-200">
          <ScanSearch className="h-4 w-4 text-cyan-200" />
          <p className="text-sm font-semibold">Why this player matters now</p>
        </div>
        <div className="space-y-3">
          {spotlight.inventoryNotes.map((note) => (
            <div key={note.label} className="rounded-2xl border border-white/6 bg-black/15 px-3 py-3">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{note.label}</p>
              <p className="mt-1 text-sm leading-6 text-slate-300">{note.detail}</p>
            </div>
          ))}
        </div>
      </div>

      {player ? (
        richProfilesEnabled ? (
          <div className="space-y-3">
            <div className="rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.08] px-4 py-3">
              <div className="flex flex-wrap items-center gap-3 text-sm text-slate-100">
                <ProfileModeChip icon={Radar} label="Cockpit profile" />
                <ProfileModeChip icon={Layers3} label="Embedded drill-down" />
                <ProfileModeChip icon={ActivitySquare} label="Shared spotlight surface" />
                <ProfileModeChip icon={Trophy} label="Event-aware context" />
              </div>
            </div>
            <PlayerProfileSections player={player} profile={profile} profileReady={profileReady} />
          </div>
        ) : (
          <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-4 text-sm leading-6 text-slate-300">
            Rich profile sections are disabled by configuration, so the spotlight stays on cockpit-native event context and summary metrics.
          </div>
        )
      ) : (
        <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-4 text-sm leading-6 text-slate-300">
          This player is available through cockpit context, but no ranking row is attached for the embedded rich profile drill-down yet.
        </div>
      )}
    </div>
  )
}

function ProfileModeChip({
  icon: Icon,
  label,
}: {
  icon: typeof Radar
  label: string
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-black/15 px-2.5 py-1 text-xs font-medium text-slate-200">
      <Icon className="h-3.5 w-3.5 text-cyan-200" />
      {label}
    </span>
  )
}
