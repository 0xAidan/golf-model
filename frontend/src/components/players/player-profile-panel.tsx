import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { ModelCommandLayout, ModelCommandSection } from "@/components/product"
import type { PlayerWorkspaceData } from "@/features/players/player-workspace-types"
import type { CompositePlayer } from "@/lib/types"
import { User } from "lucide-react"

import { FormHistorySection } from "./form-history-section"
import { InsightSummary } from "./insight-summary"
import { LinkedPicksPanel } from "./linked-picks-panel"
import { OverviewBentoGrid } from "./overview-bento-grid"
import { PlayerIdentityHero } from "./player-identity-hero"
import { SkillFieldSection } from "./skill-field-section"

export const PlayerProfilePanel = ({
  playerKey,
  playerDisplay,
  players,
  workspace,
}: {
  playerKey: string
  playerDisplay: string
  players: CompositePlayer[]
  workspace: PlayerWorkspaceData
}) => {
  const { standalone, standaloneState, standaloneError, modelPlayer, linkedPicks, fieldPercentiles } =
    workspace

  if (standaloneState === "loading") {
    return (
      <div className="players-profile-loading" data-testid="players-profile-loading">
        <div className="players-profile-loading-pulse" />
        <p className="players-profile-loading-label">Loading {playerDisplay}…</p>
      </div>
    )
  }

  if (standaloneState === "error" || !standalone) {
    return (
      <div className="players-profile-error" data-testid="players-profile-error">
        <p className="players-profile-error-title">Failed to load profile</p>
        <p className="players-profile-error-msg">
          {standaloneError ?? "Check that the backend is running and the player key is valid."}
        </p>
        <Button type="button" size="sm" variant="outline" onClick={() => workspace.refetchStandalone()}>
          Retry
        </Button>
      </div>
    )
  }

  const sections = [
    {
      id: "overview",
      label: "Overview",
      content: (
        <>
          <PlayerIdentityHero
            standalone={standalone}
            modelPlayer={modelPlayer}
            playerKey={playerKey}
          />
          <OverviewBentoGrid
            standalone={standalone}
            modelPlayer={modelPlayer}
            players={players}
            fieldPercentiles={fieldPercentiles}
          />
          <InsightSummary
            modelPlayer={modelPlayer}
            standalone={standalone}
            fieldPercentiles={fieldPercentiles}
            linkedPicks={linkedPicks}
          />
        </>
      ),
    },
    {
      id: "picks",
      label: "Picks",
      badge: linkedPicks.totalCount || undefined,
      content: (
        <ModelCommandSection
          id="players-this-week"
          title="This week's edge"
          description="+EV picks involving this player from the current Dashboard board"
          testId="players-section-picks"
        >
          <LinkedPicksPanel
            playerKey={playerKey}
            playerDisplay={playerDisplay}
            linkedPicks={linkedPicks}
          />
        </ModelCommandSection>
      ),
    },
    {
      id: "skills",
      label: "Skills",
      content: (
        <SkillFieldSection
          standalone={standalone}
          modelPlayer={modelPlayer}
          players={players}
          fieldPercentiles={fieldPercentiles}
        />
      ),
    },
    {
      id: "history",
      label: "History",
      content: <FormHistorySection standalone={standalone} />,
    },
  ]

  const hasAnyData =
    standalone.has_skill_data ||
    standalone.has_ranking_data ||
    standalone.has_approach_data ||
    standalone.recent_events.length > 0

  return (
    <div className="players-profile-panel" data-testid="players-profile-panel">
      <ModelCommandLayout sections={sections} defaultMobileSectionId="overview" />
      {!hasAnyData ? (
        <EmptyState
          message="No data available for this player"
          description="Ensure DATAGOLF_API_KEY is set and round data has been backfilled."
          icon={<User size={24} className="profile-empty-icon" />}
          className="profile-empty-center"
        />
      ) : null}
    </div>
  )
}
