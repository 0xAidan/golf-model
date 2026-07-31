import type { Meta, StoryObj } from "@storybook/react"

import { DataTable } from "@/components/operator/data-table"
import { Drawer } from "@/components/operator/drawer"
import { FeedbackState } from "@/components/operator/feedback-state"
import { MetricHelp } from "@/components/operator/metric-help"
import { PageHeader } from "@/components/operator/page-header"
import { PickRow } from "@/components/operator/pick-row"
import { StatusBanner } from "@/components/operator/status-banner"
import { TrackBadge } from "@/components/operator/track-badge"

const meta = { title: "Operator/Primitives" } satisfies Meta
export default meta

export const PageHeaderDefault: StoryObj = { render: () => <PageHeader eyebrow="Live model board" title="Rocket Classic" detail="Detroit Golf Club" /> }
export const StatusBannerStates: StoryObj = { render: () => <div className="space-y-2"><StatusBanner state="ready" message="Updated 10:42 ET." /><StatusBanner state="refreshing" message="Refreshing lines; current picks remain visible." /><StatusBanner state="stale" message="Showing the last retained board." /><StatusBanner state="error" message="Data request failed." /></div> }
export const TrackBadgeStates: StoryObj = { render: () => <div className="flex gap-2"><TrackBadge track="champion" /><TrackBadge track="challenger" /></div> }
export const MetricHelpDefault: StoryObj = { render: () => <MetricHelp label="Composite" detail="The current model score." /> }
export const DataTableDefault: StoryObj = { render: () => <DataTable caption="Rankings" rows={[{ id: "1", player: "Hideki Matsuyama", score: "88.4" }]} columns={[{ id: "player", label: "Player", render: (row) => row.player }, { id: "score", label: "Score", align: "right", render: (row) => row.score }]} /> }
export const PickRowDefault: StoryObj = { render: () => <PickRow pick={{ id: "matsu", player: "Hideki Matsuyama", opponent: "Collin Morikawa", market: "72-hole matchup", edge: "+7.8%", odds: "-110" }} /> }
export const FeedbackStates: StoryObj = { render: () => <div className="space-y-3"><FeedbackState state="loading" title="Loading operator dashboard" /><FeedbackState state="empty" title="No qualifying picks" /><FeedbackState state="error" title="Dashboard request failed" actionLabel="Retry" onAction={() => undefined} /></div> }
export const DrawerOpen: StoryObj = { render: () => <Drawer open title="Pick details" onClose={() => undefined}><p>Hideki Matsuyama over Collin Morikawa</p></Drawer> }
