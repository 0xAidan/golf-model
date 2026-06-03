/** ECharts theme fragments synced to CSS variables (light/dark via document class). */

export function readCssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

export function getEchartsTooltipStyle() {
  return {
    backgroundColor: readCssVar("--surface", "#141719"),
    borderColor: readCssVar("--border", "#1f2426"),
    borderWidth: 1,
    textStyle: {
      color: readCssVar("--text", "#e8ecef"),
      fontSize: 11,
      fontFamily: readCssVar("--font-mono", "monospace"),
    },
    extraCssText: "border-radius:4px;box-shadow:0 4px 16px rgba(0,0,0,0.25);",
  }
}

export function getEchartsAxisStyle() {
  const muted = readCssVar("--text-muted", "#6b7a84")
  const border = readCssVar("--border", "#1f2426")
  return {
    axisLine: { lineStyle: { color: border } },
    axisLabel: { color: muted, fontFamily: readCssVar("--font-mono", "monospace"), fontSize: 10 },
    splitLine: { lineStyle: { color: border, opacity: 0.6 } },
  }
}
