import type { ReactNode } from "react"

import { MetricChip } from "@/components/ui/metric-chip"

export type MetricTileProps = {
  label: string
  value: ReactNode
  detail?: ReactNode
  tone?: "neutral" | "positive" | "negative" | "warning"
  title?: string
  className?: string
}

/** Canonical KPI tile — thin alias over MetricChip for the U4 component kit. */
export function MetricTile(props: MetricTileProps) {
  return <MetricChip {...props} />
}

export { MetricChip }
