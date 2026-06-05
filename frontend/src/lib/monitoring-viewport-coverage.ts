/**
 * Estimates how much of the monitoring main column is occupied by lane content
 * (bento panels, grids, tables) vs empty chrome.
 */
export function measureMonitoringViewportCoverage(root: HTMLElement): number {
  const shell = root.querySelector(".monitoring-shell") ?? root
  const main = shell.querySelector(".monitoring-shell-main") as HTMLElement | null
  if (!main) return 0

  const mainRect = main.getBoundingClientRect()
  const mainArea = mainRect.width * mainRect.height
  if (mainArea <= 0) return 0

  const selectors = [
    ".monitoring-bento-panel",
    ".monitoring-bento-grid",
    ".hero-data-grid",
    ".monitoring-macro-kpi-strip",
    ".cockpit-lab-root",
  ]

  let covered = 0
  const seen = new Set<Element>()

  for (const selector of selectors) {
    for (const el of main.querySelectorAll(selector)) {
      if (seen.has(el)) continue
      seen.add(el)
      const rect = el.getBoundingClientRect()
      const overlapW = Math.max(0, Math.min(rect.right, mainRect.right) - Math.max(rect.left, mainRect.left))
      const overlapH = Math.max(0, Math.min(rect.bottom, mainRect.bottom) - Math.max(rect.top, mainRect.top))
      covered += overlapW * overlapH
    }
  }

  return Math.min(1, covered / mainArea)
}
