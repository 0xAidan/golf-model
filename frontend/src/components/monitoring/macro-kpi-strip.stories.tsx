import type { Meta, StoryObj } from "@storybook/react"

import { MacroKpiStrip } from "./macro-kpi-strip"

const meta: Meta<typeof MacroKpiStrip> = {
  title: "Monitoring/MacroKpiStrip",
  component: MacroKpiStrip,
  args: {
    items: [
      { id: "ev", label: "Top EV", value: 14.2, suffix: "%", tone: "positive" },
      { id: "picks", label: "Picks", value: 12 },
      { id: "hit", label: "Hit rate", value: "58%", tone: "neutral" },
      { id: "clv", label: "CLV", value: 2.1, suffix: "u", tone: "warning" },
    ],
  },
}

export default meta
type Story = StoryObj<typeof MacroKpiStrip>

export const Default: Story = {}
