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
      <div className="panel-empty" style={{ padding: "32px 12px" }}>
        <Radar style={{ width: 14, height: 14 }} />
        <span>Select a player to load spotlight</span>
      </div>
    )
  }

  return (
    <div>
      {/* Player header */}
      <div className="spotlight-head">
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "8px" }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="term-row-eye">{spotlight.modeLabel} spotlight</div>
            <div className="spotlight-player-name">{spotlight.playerName}</div>
            {spotlight.narrative ? (
              <div className="spotlight-narrative">{spotlight.narrative}</div>
            ) : null}
          </div>
          <div className="tier-badge" style={{ flexShrink: 0, marginTop: "2px" }}>
            {spotlight.eventName}
          </div>
        </div>

        {spotlight.sourceBadges.length > 0 ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginTop: "6px" }}>
            {spotlight.sourceBadges.map((badge) => (
              <span key={badge} className="tier-badge">{badge}</span>
            ))}
          </div>
        ) : null}
      </div>

      {/* Header stats */}
      {spotlight.headerStats.length > 0 ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "4px", padding: "8px" }}>
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
      ) : null}

      {/* Summary stats */}
      {spotlight.summaryStats.length > 0 ? (
        <>
          <div className="term-section-head">Summary Stats</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "4px", padding: "8px" }}>
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
        </>
      ) : null}

      {/* Inventory notes */}
      {spotlight.inventoryNotes.length > 0 ? (
        <>
          <div className="term-section-head">
            <ScanSearch style={{ width: 9, height: 9 }} />
            Why this player matters
          </div>
          <div>
            {spotlight.inventoryNotes.map((note) => (
              <div key={note.label} className="term-row">
                <span className="term-row-eye">{note.label}</span>
                <span className="term-row-det" style={{ WebkitLineClamp: 3 }}>{note.detail}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}

      {/* Rich profile sections */}
      {player ? (
        richProfilesEnabled ? (
          <div>
            <div className="term-section-head">
              <span style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                <Radar style={{ width: 9, height: 9 }} />
                <ActivitySquare style={{ width: 9, height: 9 }} />
                <Layers3 style={{ width: 9, height: 9 }} />
                <Trophy style={{ width: 9, height: 9 }} />
                Profile Drill-Down
              </span>
            </div>
            <div style={{ padding: "8px" }}>
              <PlayerProfileSections player={player} profile={profile} profileReady={profileReady} />
            </div>
          </div>
        ) : (
          <div className="term-row">
            <span className="term-row-det">Rich profiles disabled by configuration — spotlight shows cockpit-native context only.</span>
          </div>
        )
      ) : (
        <div className="term-row">
          <span className="term-row-det">Player available via cockpit context — no ranking row for embedded profile drill-down.</span>
        </div>
      )}
    </div>
  )
}
