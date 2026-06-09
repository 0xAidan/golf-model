/**
 * Standalone Players Page — rebuilt command center with Dashboard integration.
 * Route: /players
 */
import { PlayersCommandCenter } from "@/components/players/players-command-center"
import type { PlayersWorkspaceProps } from "@/features/players/player-workspace-types"

export type PlayersPageProps = PlayersWorkspaceProps

export function PlayersPage(props: PlayersPageProps) {
  return <PlayersCommandCenter {...props} />
}
