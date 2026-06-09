import { EventCommandHeader, TrustStatusBanner } from "@/components/product"
import { EmptyState } from "@/components/ui/empty-state"
import { buildPlayersTrustState } from "@/features/players/build-players-trust"
import { formatSnapshotAge, resolvePlayersEventContext } from "@/features/players/event-context"
import type { PlayersWorkspaceProps } from "@/features/players/player-workspace-types"
import { usePlayerWorkspace } from "@/features/players/use-player-workspace"
import { useIsNarrowViewport } from "@/hooks/use-media-query"
import { User } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"

import { FieldExplorer } from "./field-explorer"
import { PlayerProfilePanel } from "./player-profile-panel"

export const PlayersCommandCenter = ({
  players,
  liveSnapshot,
  snapshotNotice,
  snapshotAgeSeconds,
  predictionTab,
  tournamentId,
  courseNum,
  selectedPlayerKey,
  onPlayerSelect,
  filteredMatchups,
  secondaryBets,
  richProfilesEnabled,
}: PlayersWorkspaceProps) => {
  const initialFromUrl =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("player")
      : null

  const [localKey, setLocalKey] = useState<string | null>(initialFromUrl || selectedPlayerKey || null)
  const [localDisplay, setLocalDisplay] = useState("")

  const first = players[0]
  const effectiveKey = localKey || selectedPlayerKey || first?.player_key || null

  const fallbackDisplay = effectiveKey
    ? (players.find((p) => p.player_key === effectiveKey)?.player_display ??
      effectiveKey.replaceAll("_", " "))
    : ""

  const effectiveDisplay =
    localKey && localDisplay
      ? localDisplay
      : selectedPlayerKey === effectiveKey && selectedPlayerKey
        ? fallbackDisplay
        : fallbackDisplay

  const handleSelect = useCallback(
    (key: string, display: string) => {
      setLocalKey(key)
      setLocalDisplay(display)
      onPlayerSelect(key)
    },
    [onPlayerSelect],
  )

  useEffect(() => {
    if (!effectiveKey || typeof window === "undefined") return
    const url = new URL(window.location.href)
    url.searchParams.set("player", effectiveKey)
    window.history.replaceState({}, "", url.toString())
  }, [effectiveKey])

  useEffect(() => {
    if (selectedPlayerKey && selectedPlayerKey !== localKey) {
      setLocalKey(selectedPlayerKey)
      const display =
        players.find((p) => p.player_key === selectedPlayerKey)?.player_display ??
        selectedPlayerKey.replaceAll("_", " ")
      setLocalDisplay(display)
    }
  }, [localKey, players, selectedPlayerKey])

  const eventContext = useMemo(
    () => resolvePlayersEventContext({ liveSnapshot, predictionTab }),
    [liveSnapshot, predictionTab],
  )

  const trustState = useMemo(
    () => buildPlayersTrustState({ snapshotNotice, liveSnapshot, predictionTab }),
    [liveSnapshot, predictionTab, snapshotNotice],
  )

  const isNarrow = useIsNarrowViewport()

  const workspace = usePlayerWorkspace({
    playerKey: effectiveKey ?? "",
    players,
    tournamentId,
    courseNum,
    richProfilesEnabled,
    filteredMatchups,
    secondaryBets,
  })

  const headerMeta = eventContext.courseName
    ? `${eventContext.courseName} · ${formatSnapshotAge(snapshotAgeSeconds)}`
    : formatSnapshotAge(snapshotAgeSeconds)

  return (
    <div className="players-command-center" data-testid="players-page">
      <EventCommandHeader
        lane="dashboard"
        eventName={eventContext.eventName}
        meta={headerMeta}
        kpis={[
          { id: "field", label: "Field", value: String(players.length || eventContext.fieldSize) },
          {
            id: "selected",
            label: "Selected",
            value: effectiveDisplay || "—",
          },
        ]}
      />

      {trustState ? (
        <TrustStatusBanner
          tone={trustState.tone}
          title={trustState.title}
          message={trustState.message}
          testId="players-trust-banner"
        />
      ) : null}

      <div className="players-command-center__body">
        {!isNarrow ? (
          <aside className="players-command-center__sidebar">
            <FieldExplorer
              players={players}
              selectedKey={effectiveKey}
              selectedDisplay={effectiveDisplay}
              onSelect={handleSelect}
            />
          </aside>
        ) : null}

        <main className="players-command-center__main">
          {isNarrow ? (
            <FieldExplorer
              players={players}
              selectedKey={effectiveKey}
              selectedDisplay={effectiveDisplay}
              onSelect={handleSelect}
            />
          ) : null}
          {effectiveKey ? (
            <PlayerProfilePanel
              key={effectiveKey}
              playerKey={effectiveKey}
              playerDisplay={effectiveDisplay}
              players={players}
              workspace={workspace}
            />
          ) : (
            <EmptyState
              message="Select a player from the field"
              description="View model alignment, skills, linked picks, and round history."
              icon={<User size={24} className="profile-empty-icon" />}
              className="profile-empty-center"
            />
          )}
        </main>
      </div>
    </div>
  )
}
