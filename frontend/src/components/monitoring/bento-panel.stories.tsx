import type { Meta, StoryObj } from "@storybook/react"

import { BentoPanel } from "./bento-panel"

const meta: Meta<typeof BentoPanel> = {
  title: "Monitoring/BentoPanel",
  component: BentoPanel,
  args: {
    title: "Rankings",
    span: 8,
    rowSpan: 2,
    children: <p className="text-sm text-[var(--text-muted)]">Panel body</p>,
  },
}

export default meta
type Story = StoryObj<typeof BentoPanel>

export const Default: Story = {}

export const FullWidth: Story = {
  args: { span: 12, rowSpan: 1, title: "Full width panel" },
}
