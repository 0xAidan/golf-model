import { cn } from "@/lib/utils"

export type ModelLane = "dashboard" | "lab"

export const ModelLaneBadge = ({
  lane,
  className,
}: {
  lane: ModelLane
  className?: string
}) => (
  <span
    className={cn(
      "model-lane-badge",
      lane === "dashboard" ? "model-lane-badge--dashboard" : "model-lane-badge--lab",
      className,
    )}
    data-testid={`model-lane-badge-${lane}`}
  >
    {lane === "dashboard" ? "Dashboard model" : "Lab model"}
  </span>
)
