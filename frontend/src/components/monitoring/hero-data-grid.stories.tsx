import type { Meta, StoryObj } from "@storybook/react"

import { HeroDataGrid } from "./hero-data-grid"

const columns = [
  { id: "rank", header: "Rank", accessorKey: "rank" },
  { id: "player", header: "Player", accessorKey: "player" },
  { id: "composite", header: "Composite", accessorKey: "composite" },
]

const rows = [
  { rank: 1, player: "Scottie Scheffler", composite: 82.4 },
  { rank: 2, player: "Rory McIlroy", composite: 80.1 },
  { rank: 3, player: "Xander Schauffele", composite: 79.6 },
]

const meta: Meta<typeof HeroDataGrid> = {
  title: "Monitoring/HeroDataGrid",
  component: HeroDataGrid,
  args: {
    data: rows,
    columns,
    density: "compact",
  },
}

export default meta
type Story = StoryObj<typeof HeroDataGrid>

export const Default: Story = {}

export const Empty: Story = {
  args: { data: [], emptyMessage: "No rows" },
}
