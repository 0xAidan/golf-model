import { useEffect, type ReactNode } from "react"

import { useTheme } from "@/components/theme-provider"
import { readCssVar } from "@/lib/chart-theme"

/** Re-reads CSS variables when light/dark changes so ECharts consumers pick up new colors. */
export function ChartThemeProvider({ children }: { children: ReactNode }) {
  const { resolvedDark } = useTheme()

  useEffect(() => {
    document.documentElement.dataset.chartTheme = resolvedDark ? "dark" : "light"
    void readCssVar("--text", "#e8ecef")
  }, [resolvedDark])

  return children
}
