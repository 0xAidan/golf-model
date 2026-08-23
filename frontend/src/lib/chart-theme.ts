/** ECharts theme fragments synced to CSS variables (light/dark via document class). */

export function readCssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

export function getEchartsTooltipStyle() {
  return {
    backgroundColor: readCssVar("--popover", "#171c24"),
    borderColor: readCssVar("--border-mid", "#2b3341"),
    borderWidth: 1,
    textStyle: {
      color: readCssVar("--text", "#eef2f6"),
      fontSize: 11,
      fontFamily: readCssVar("--font-mono", "monospace"),
    },
    extraCssText: "border-radius:8px;box-shadow:0 8px 24px -8px rgba(0,0,0,0.45);padding:8px 10px;",
  }
}

export function getEchartsAxisStyle() {
  const muted = readCssVar("--text-muted", "#98a5b3")
  const grid = readCssVar("--chart-grid", "rgba(148, 163, 184, 0.12)")
  return {
    axisLine: { lineStyle: { color: readCssVar("--border", "#232a35") } },
    axisLabel: {
      color: muted,
      fontFamily: readCssVar("--font-mono", "monospace"),
      fontSize: 10,
    },
    splitLine: { lineStyle: { color: grid } },
  }
}

/** Shared categorical series palette (theme-synced via --chart-c* tokens). */
export function getChartPalette() {
  return [
    readCssVar("--chart-c1", "#34d399"),
    readCssVar("--chart-c2", "#60a5fa"),
    readCssVar("--chart-c3", "#fbbf24"),
    readCssVar("--chart-c4", "#f87171"),
    readCssVar("--chart-c5", "#a78bfa"),
    readCssVar("--chart-c6", "#22d3ee"),
  ]
}

/** Diverging heat scale for SG / hole grids (cool→warm). */
export function getHeatScale() {
  return {
    negStrong: readCssVar("--heat-neg-strong", "#f87171"),
    neg: readCssVar("--heat-neg", "#fb923c"),
    neutral: readCssVar("--heat-neutral", "rgba(148, 163, 184, 0.25)"),
    pos: readCssVar("--heat-pos", "#4ade80"),
    posStrong: readCssVar("--heat-pos-strong", "#22c55e"),
  }
}

/** Positive/negative series colors for value charts. */
export function getChartValueColors() {
  return {
    up: readCssVar("--accent-edge", "#34d399"),
    down: readCssVar("--red", "#f87171"),
  }
}
