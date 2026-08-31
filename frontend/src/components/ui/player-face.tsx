import { useState } from "react"

import {
  usePlayerIdentity,
  usePlayerIdentityIndexLoaded,
} from "@/providers/player-identity-provider"
import { cn } from "@/lib/utils"

export type PlayerFaceSize = "sm" | "md" | "lg"

export type PlayerFaceProps = {
  playerKey?: string | null
  name: string
  size?: PlayerFaceSize
  country?: string | null
  className?: string
  /** Try the photo URL before the index loads (hero only). Tables wait. */
  eager?: boolean
}

const SIZE_CLASS: Record<PlayerFaceSize, string> = {
  sm: "h-6 w-6 text-[9px]",
  md: "h-8 w-8 text-[10px]",
  lg: "h-14 w-14 text-lg",
}

export const playerInitials = (name: string) =>
  name
    .split(/\s+/)
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase() || "?"

export const PlayerFace = ({
  playerKey,
  name,
  size = "md",
  country,
  className,
  eager = false,
}: PlayerFaceProps) => {
  const [failed, setFailed] = useState(false)
  const identity = usePlayerIdentity(playerKey)
  const indexLoaded = usePlayerIdentityIndexLoaded()
  const flag = (country || identity?.country || "").trim()
  const showPhoto =
    Boolean(playerKey) &&
    !failed &&
    (identity?.hasPhoto === true || (eager && !indexLoaded))
  const src = showPhoto && playerKey ? `/api/players/${encodeURIComponent(playerKey)}/photo` : null

  const handleError = () => {
    setFailed(true)
  }

  return (
    <span className={cn("player-face", className)} data-testid="player-face">
      <span
        className={cn("player-face__disk", SIZE_CLASS[size])}
        aria-hidden
      >
        {src ? (
          <img
            src={src}
            alt=""
            className="player-face__img"
            data-testid="player-face-img"
            onError={handleError}
          />
        ) : (
          <span className="player-face__initials">{playerInitials(name)}</span>
        )}
      </span>
      {flag ? (
        <span className="player-face__country" data-testid="player-face-country">
          {flag}
        </span>
      ) : null}
    </span>
  )
}
