import { ActivitySquare, Layers3, Radar, ScanSearch, Trophy } from "lucide-react"

import { PlayerProfileSections } from "@/components/player-profile-sections"
import { MetricTile } from "@/components/shell"
import { PanelChrome } from "@/components/ui/panel-chrome"
import type { CockpitSpotlightModel } from "@/lib/cockpit-spotlight"
import { SPOTLIGHT_NOTE_TOOLTIPS } from "@/lib/metric-tooltips"
import type { CompositePlayer, PlayerProfile } from "@/lib/types"

export function PlayerSpotlightPanel({
  spotlight,
  player,
  profile,
  profileState,
  profileErrorMessage,
  onRetryProfile,
  richProfilesEnabled,
}: {
  spotlight: CockpitSpotlightModel | null
  player: CompositePlayer | null
  profile?: PlayerProfile
  profileState: "loading" | "ready" | "error" | "unavailable"
  profileErrorMessage?: string
  onRetryProfile?: () => void
  richProfilesEnabled: boolean
}) {
  if (!spotlight) {
    return (
      <div className="panel-empty panel-empty--padded">
        <Radar className="panel-empty-icon" aria-hidden />
        <span>Select a player to load spotlight</span>
      </div>
    )
  }

  return (
    <PanelChrome
      title={spotlight.playerName}
      description={`${spotlight.modeLabel} spotlight · ${spotlight.eventName}`}
    >
      <div className="spotlight-head">
        {spotlight.narrative ? <div className="spotlight-narrative">{spotlight.narrative}</div> : null}
        {spotlight.sourceBadges.length > 0 ? (
          <div className="spotlight-badges-row">
            {spotlight.sourceBadges.map((badge) => (
              <span key={badge} className="tier-badge">
                {badge}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {spotlight.headerStats.length > 0 ? (
        <div className="spotlight-stats-grid">
          {spotlight.headerStats.map((item) => (
            <MetricTile
              key={item.label}
              label={item.label}
              value={item.value}
              detail={item.detail}
              tone={item.tone}
              title={item.title}
            />
          ))}
        </div>
      ) : null}

      {spotlight.summaryStats.length > 0 ? (
        <>
          <div className="term-section-head">Summary Stats</div>
          <div className="spotlight-stats-grid">
            {spotlight.summaryStats.map((item) => (
              <MetricTile
                key={item.label}
                label={item.label}
                value={item.value}
                detail={item.detail}
                tone={item.tone}
                title={item.title}
              />
            ))}
          </div>
        </>
      ) : null}

      {spotlight.inventoryNotes.length > 0 ? (
        <>
          <div className="term-section-head">
            <ScanSearch className="term-section-icon" aria-hidden />
            Why this player matters
          </div>
          <div>
            {spotlight.inventoryNotes.map((note) => (
              <div key={note.label} className="term-row">
                <span className="term-row-eye" title={SPOTLIGHT_NOTE_TOOLTIPS[note.label]}>
                  {note.label}
                </span>
                <span className="term-row-det term-row-det-clamp">{note.detail}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}

      {player ? (
        richProfilesEnabled ? (
          <div>
            <div className="term-section-head">
              <span className="spotlight-section-icons">
                <Radar className="term-section-icon" aria-hidden />
                <ActivitySquare className="term-section-icon" aria-hidden />
                <Layers3 className="term-section-icon" aria-hidden />
                <Trophy className="term-section-icon" aria-hidden />
                Profile Drill-Down
              </span>
            </div>
            <div className="spotlight-profile-pad">
              <PlayerProfileSections
                player={player}
                profile={profile}
                profileState={profileState}
                errorMessage={profileErrorMessage}
                onRetry={onRetryProfile}
              />
            </div>
          </div>
        ) : (
          <div className="term-row">
            <span className="term-row-det">
              Rich profiles disabled by configuration — spotlight shows cockpit-native context only.
            </span>
          </div>
        )
      ) : (
        <div className="term-row">
          <span className="term-row-det">
            Player available via cockpit context — no ranking row for embedded profile drill-down.
          </span>
        </div>
      )}
    </PanelChrome>
  )
}
