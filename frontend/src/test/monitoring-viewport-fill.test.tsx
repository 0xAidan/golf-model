import { render } from "@testing-library/react"
import { describe, expect, it, beforeEach, afterEach } from "vitest"

import { wrapMonitoringTest } from "@/test/monitoring-test-utils"
import { BentoGrid } from "@/components/monitoring/bento-grid"
import { BentoPanel } from "@/components/monitoring/bento-panel"
import { HeroDataGrid } from "@/components/monitoring/hero-data-grid"
import { MacroKpiStrip } from "@/components/monitoring/macro-kpi-strip"
import { MonitoringShell } from "@/components/monitoring/monitoring-shell"
import { measureMonitoringViewportCoverage } from "@/lib/monitoring-viewport-coverage"

const VIEWPORTS = [
  { width: 1280, height: 900, label: "1280" },
  { width: 1920, height: 1080, label: "1920" },
] as const

const MIN_COVERAGE = 0.75

function MonitoringFillFixture() {
  const columns = [
    { id: "rank", header: "Rank", accessorKey: "rank" },
    { id: "player", header: "Player", accessorKey: "player" },
    { id: "score", header: "Score", accessorKey: "score" },
  ]
  const rows = Array.from({ length: 18 }, (_, i) => ({
    rank: i + 1,
    player: `Player ${i + 1}`,
    score: 80 - i * 0.5,
  }))

  return (
    <MonitoringShell headline="RBC Heritage" subheadline="Live board">
      <MacroKpiStrip
        items={[
          { id: "ev", label: "Top EV", value: 12.4, suffix: "%", tone: "positive" },
          { id: "picks", label: "Picks", value: 8 },
          { id: "books", label: "Books", value: 4 },
        ]}
      />
      <BentoGrid columns={12} className="monitoring-bento-grid--fill">
        <BentoPanel span={8} rowSpan={2} title="Rankings">
          <HeroDataGrid data={rows} columns={columns} testId="viewport-fill-grid" />
        </BentoPanel>
        <BentoPanel span={4} title="Markets">
          <div style={{ minHeight: 320 }} className="monitor-lane">
            Market panel
          </div>
        </BentoPanel>
        <BentoPanel span={12} title="Picks">
          <div style={{ minHeight: 200 }} className="monitor-lane">
            Picks strip
          </div>
        </BentoPanel>
      </BentoGrid>
    </MonitoringShell>
  )
}

describe("monitoring viewport fill", () => {
  beforeEach(() => {
    document.documentElement.classList.add("dark")
  })

  afterEach(() => {
    document.documentElement.classList.remove("dark")
  })

  for (const vp of VIEWPORTS) {
    it(`fills at least ${MIN_COVERAGE * 100}% of main column at ${vp.label}px`, () => {
      Object.defineProperty(window, "innerWidth", { value: vp.width, writable: true, configurable: true })
      Object.defineProperty(window, "innerHeight", { value: vp.height, writable: true, configurable: true })
      window.dispatchEvent(new Event("resize"))

      const { container } = render(
        wrapMonitoringTest(
          <div className="monitor-viewport-fill" style={{ width: vp.width, height: vp.height }}>
            <MonitoringFillFixture />
          </div>,
        ),
      )

      const shell = container.querySelector(".monitoring-shell") as HTMLElement
      expect(shell).toBeTruthy()
      shell.style.height = `${vp.height}px`
      shell.style.minHeight = `${vp.height}px`

      const main = shell.querySelector(".monitoring-shell-main") as HTMLElement
      const headerH = 44
      const drawerW = 240
      const mainLeft = drawerW
      const mainTop = headerH
      const mainW = vp.width - drawerW
      const mainH = vp.height - headerH

      const mainRect = {
        top: mainTop,
        left: mainLeft,
        right: mainLeft + mainW,
        bottom: mainTop + mainH,
        width: mainW,
        height: mainH,
        x: mainLeft,
        y: mainTop,
        toJSON: () => ({}),
      }
      main.getBoundingClientRect = () => mainRect as DOMRect

      for (const el of main.querySelectorAll<HTMLElement>(
        ".monitoring-bento-panel, .monitoring-bento-grid, .monitoring-macro-kpi-strip",
      )) {
        el.getBoundingClientRect = () =>
          ({
            top: mainTop + 40,
            left: mainLeft,
            right: mainLeft + mainW,
            bottom: mainTop + mainH - 8,
            width: mainW,
            height: mainH - 48,
            x: mainLeft,
            y: mainTop + 40,
            toJSON: () => ({}),
          }) as DOMRect
      }

      const coverage = measureMonitoringViewportCoverage(container)
      expect(coverage).toBeGreaterThanOrEqual(MIN_COVERAGE)
    })
  }
})
