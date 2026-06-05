import { ProDataGrid, type ProDataGridProps } from "@/components/ui/pro-data-grid"
import { cn } from "@/lib/utils"

export type HeroDataGridProps<T> = ProDataGridProps<T>

export function HeroDataGrid<T>({ className, density = "compact", ...props }: HeroDataGridProps<T>) {
  return (
    <ProDataGrid
      {...props}
      density={density}
      className={cn("hero-data-grid monitor-lane", className)}
      testId={props.testId ?? "hero-data-grid"}
    />
  )
}
