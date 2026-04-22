import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { SnapshotChip } from "./snapshot-chip"
import {
  computeAgeSeconds,
  formatAgeLabel,
  normalizeSourceLabel,
  resolveTone,
} from "@/lib/snapshot-chip"

const FIXED_NOW_ISO = "2026-04-22T12:00:00Z"
const FIXED_NOW_MS = Date.parse(FIXED_NOW_ISO)

function isoMinus(seconds: number): string {
  return new Date(FIXED_NOW_MS - seconds * 1000).toISOString()
}

describe("snapshot chip helpers", () => {
  it("computes age in whole seconds", () => {
    expect(computeAgeSeconds(isoMinus(5), FIXED_NOW_MS)).toBe(5)
    expect(computeAgeSeconds(isoMinus(125), FIXED_NOW_MS)).toBe(125)
  })

  it("returns null for missing or invalid timestamps", () => {
    expect(computeAgeSeconds(null, FIXED_NOW_MS)).toBeNull()
    expect(computeAgeSeconds(undefined, FIXED_NOW_MS)).toBeNull()
    expect(computeAgeSeconds("not-a-date", FIXED_NOW_MS)).toBeNull()
  })

  it("formats age labels", () => {
    expect(formatAgeLabel(5)).toBe("5s ago")
    expect(formatAgeLabel(125)).toBe("2m ago")
    expect(formatAgeLabel(14 * 60)).toBe("14m ago")
    expect(formatAgeLabel(61 * 60)).toBe("stale (>60m)")
    expect(formatAgeLabel(null)).toBe("—")
  })

  it("resolves tone thresholds", () => {
    expect(resolveTone(10)).toBe("green")
    expect(resolveTone(29 * 60)).toBe("green")
    expect(resolveTone(30 * 60)).toBe("amber")
    expect(resolveTone(60 * 60)).toBe("amber")
    expect(resolveTone(61 * 60)).toBe("red")
    expect(resolveTone(null)).toBe("grey")
  })

  it("normalizes source labels", () => {
    expect(normalizeSourceLabel("live")).toBe("LIVE")
    expect(normalizeSourceLabel("REPLAY")).toBe("REPLAY")
    expect(normalizeSourceLabel("fixture")).toBe("FIXTURE")
    expect(normalizeSourceLabel(null)).toBe("—")
    expect(normalizeSourceLabel("weird")).toBe("—")
  })
})

describe("<SnapshotChip />", () => {
  it("renders green tone for fresh snapshots", () => {
    render(
      <SnapshotChip
        generatedAt={isoMinus(12)}
        dataSource="live"
        now={() => FIXED_NOW_MS}
      />,
    )
    const chip = screen.getByTestId("snapshot-chip")
    expect(chip).toHaveAttribute("data-tone", "green")
    expect(chip.className).toContain("snapshot-chip-green")
    expect(screen.getByTestId("snapshot-chip-age")).toHaveTextContent("12s ago")
    expect(screen.getByTestId("snapshot-chip-source")).toHaveTextContent("LIVE")
  })

  it("renders amber tone between 30-60m", () => {
    render(
      <SnapshotChip
        generatedAt={isoMinus(45 * 60)}
        dataSource="replay"
        now={() => FIXED_NOW_MS}
      />,
    )
    const chip = screen.getByTestId("snapshot-chip")
    expect(chip).toHaveAttribute("data-tone", "amber")
    expect(chip.className).toContain("snapshot-chip-amber")
    expect(screen.getByTestId("snapshot-chip-age")).toHaveTextContent("45m ago")
    expect(screen.getByTestId("snapshot-chip-source")).toHaveTextContent("REPLAY")
  })

  it("renders red tone when stale past 60 minutes", () => {
    render(
      <SnapshotChip
        generatedAt={isoMinus(90 * 60)}
        dataSource="fixture"
        now={() => FIXED_NOW_MS}
      />,
    )
    const chip = screen.getByTestId("snapshot-chip")
    expect(chip).toHaveAttribute("data-tone", "red")
    expect(chip.className).toContain("snapshot-chip-red")
    expect(screen.getByTestId("snapshot-chip-age")).toHaveTextContent("stale (>60m)")
    expect(screen.getByTestId("snapshot-chip-source")).toHaveTextContent("FIXTURE")
  })

  it("renders grey placeholder when no snapshot is loaded", () => {
    render(<SnapshotChip generatedAt={null} dataSource={null} now={() => FIXED_NOW_MS} />)
    const chip = screen.getByTestId("snapshot-chip")
    expect(chip).toHaveAttribute("data-tone", "grey")
    expect(chip.className).toContain("snapshot-chip-grey")
    expect(screen.getByTestId("snapshot-chip-age")).toHaveTextContent("—")
    expect(screen.getByTestId("snapshot-chip-source")).toHaveTextContent("—")
  })
})
