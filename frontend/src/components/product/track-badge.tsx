import { cn } from "@/lib/utils"

export type TrackKind = "dashboard" | "lab"

/**
 * Provenance badge for a model track. Extends ModelLaneBadge with the model variant and
 * a short config hash so operators can always tell which config produced a board/row.
 * `champion` (dashboard) vs `challenger (validation pending)` (lab) — the lab track is
 * not labelled superior until its validation lands.
 */
export const TrackBadge = ({
  track,
  variant,
  configHash,
  className,
}: {
  track: TrackKind
  variant?: string | null
  configHash?: string | null
  className?: string
}) => {
  const roleLabel = track === "dashboard" ? "Champion" : "Challenger"
  return (
    <span
      className={cn(
        "model-lane-badge",
        track === "dashboard" ? "model-lane-badge--dashboard" : "model-lane-badge--lab",
        "inline-flex items-center gap-1.5",
        className,
      )}
      data-testid={`track-badge-${track}`}
      title={configHash ? `config ${configHash}` : undefined}
    >
      <span className="font-semibold">{roleLabel}</span>
      {variant ? <span className="opacity-80">{variant}</span> : null}
      {configHash ? (
        <span className="font-mono text-[10px] opacity-70" data-testid={`track-badge-hash-${track}`}>
          #{configHash.slice(0, 8)}
        </span>
      ) : null}
    </span>
  )
}
