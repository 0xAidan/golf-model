import type { Meta, StoryObj } from "@storybook/react"

import { StatusPill } from "./status-pill"

const meta: Meta<typeof StatusPill> = {
  title: "Monitoring/StatusPill",
  component: StatusPill,
}

export default meta
type Story = StoryObj<typeof StatusPill>

export const Live: Story = {
  args: { status: "live", label: "Live" },
}

export const Warn: Story = {
  args: { status: "warn", label: "Stale snapshot" },
}

export const Idle: Story = {
  args: { status: "idle", label: "Idle" },
}

export const Error: Story = {
  args: { status: "error", label: "Worker down" },
}
