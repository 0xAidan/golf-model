import { useState } from "react"

import { PlayerFace } from "@/components/ui/player-face"
import { BettingRecordTab } from "@/components/players/betting-record-tab"
import { CourseDnaTab } from "@/components/players/course-dna-tab"
import { Reveal } from "@/components/motion/primitives"
import { cn } from "@/lib/utils"
import type { StandalonePlayerProfile } from "@/lib/types"

const TABS = [
  { id: "betting", label: "Betting Record" },
  { id: "dna", label: "Course DNA" },
] as const

export type PlayerDeepTabId = (typeof TABS)[number]["id"]

/**
 * PlayerIntelligencePanels — the flagship deep-dive sections
 * rendered below the existing profile content, with a glass sticky
 * tab bar. Designed to be extended with Form Lab / Round Log.
 */
export function PlayerIntelligencePanels({
  playerKey,
  courseId,
}: {
  playerKey: string
  courseId?: string | null
}) {
  const [tab, setTab] = useState<PlayerDeepTabId>("betting")

  return (
    <section className="mt-6" data-testid="player-intelligence-panels">
      <div className="sticky top-[var(--header-h)] z-10 mb-4 flex items-center gap-1 rounded-[var(--r-sm)] border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            onClick={() => setTab(entry.id)}
            aria-pressed={tab === entry.id}
            data-testid={`player-deep-tab-${entry.id}`}
            className={cn(
              "rounded-full px-4 py-1.5 text-xs font-semibold transition-colors",
              tab === entry.id
                ? "bg-[color-mix(in_srgb,var(--accent-focus)_14%,transparent)] text-[var(--text)]"
                : "text-[var(--text-muted)] hover:text-[var(--text)]",
            )}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <Reveal key={tab}>
        {tab === "betting" ? <BettingRecordTab playerKey={playerKey} /> : null}
        {tab === "dna" ? <CourseDnaTab playerKey={playerKey} courseId={courseId} /> : null}
      </Reveal>
    </section>
  )
}

/** Hero band shown above the existing profile header on deep links. */
export function PlayerHeroBand({ profile }: { profile: StandalonePlayerProfile }) {
  return (
    <Reveal className="mb-4">
      <div className="panel flex flex-wrap items-center gap-5 px-5 py-4" data-testid="player-hero-band">
        <PlayerFace
          playerKey={profile.player_key}
          name={profile.header.player_display ?? profile.player_key}
          size="lg"
          country={profile.header.country}
          eager
        />
        <div className="min-w-0">
          <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted)]">
            Player intelligence
          </div>
          <div className="truncate text-xl font-semibold tracking-tight text-[var(--text)]">
            {profile.header.player_display ?? profile.player_key}
          </div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {profile.ranking_card?.dg_rank ? (
            <RankMedallion label="DG" value={`#${profile.ranking_card.dg_rank}`} />
          ) : null}
          {profile.ranking_card?.owgr_rank ? (
            <RankMedallion label="OWGR" value={`#${profile.ranking_card.owgr_rank}`} />
          ) : null}
        </div>
      </div>
    </Reveal>
  )
}

function RankMedallion({ label, value }: { label: string; value: string }) {
  return (
    <span
      className="inline-flex items-baseline gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1"
      title={`${label} ranking`}
    >
      <span className="text-[9px] font-semibold uppercase tracking-widest text-[var(--text-faint)]">{label}</span>
      <span className="num text-sm font-bold text-[var(--text)]">{value}</span>
    </span>
  )
}
