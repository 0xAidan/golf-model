import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, XCircle } from "lucide-react"

import { TerminalPageHeader } from "@/components/ui/terminal-page-header"
import { TrackBadge } from "@/components/product/track-badge"
import { api } from "@/lib/api"
import type { TrackMetrics } from "@/lib/types"

const CONFIRM_PHRASE = "PROMOTE"

function GateRow({ id, passed, detail }: { id: string; passed: boolean; detail: string }) {
  return (
    <li className="flex items-start gap-2 py-1" data-testid={`promotion-gate-${id}`}>
      {passed ? (
        <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-[var(--green)]" aria-hidden />
      ) : (
        <XCircle size={16} className="mt-0.5 shrink-0 text-[var(--red)]" aria-hidden />
      )}
      <span className="text-sm">
        <span className="font-medium text-[var(--text-primary)]">{id}</span>
        <span className="text-[var(--text-secondary)]"> — {detail}</span>
      </span>
    </li>
  )
}

function PromotionTab() {
  const queryClient = useQueryClient()
  const [confirm, setConfirm] = useState("")
  const [reason, setReason] = useState("")
  const [message, setMessage] = useState<string | null>(null)

  const readiness = useQuery({
    queryKey: ["promotion-readiness"],
    queryFn: api.getPromotionReadiness,
    refetchInterval: 30_000,
  })

  const promote = useMutation({
    mutationFn: () => api.promoteTrack({ reason }),
    onSuccess: () => {
      setMessage("Challenger promoted to the dashboard slot (config of record).")
      setConfirm("")
      queryClient.invalidateQueries({ queryKey: ["tracks"] })
      queryClient.invalidateQueries({ queryKey: ["promotion-readiness"] })
    },
    onError: (err) => setMessage(err instanceof Error ? err.message : "Promotion failed"),
  })

  const rollback = useMutation({
    mutationFn: () => api.rollbackTrack({}),
    onSuccess: () => {
      setMessage("Dashboard slot rolled back to its previous config.")
      queryClient.invalidateQueries({ queryKey: ["tracks"] })
    },
    onError: (err) => setMessage(err instanceof Error ? err.message : "Rollback failed"),
  })

  const data = readiness.data
  const enabled = data?.promotion_enabled ?? false
  const gatesPass = data?.passed ?? false
  const canPromote = enabled && gatesPass && confirm === CONFIRM_PHRASE && reason.trim().length > 0

  return (
    <div className="flex flex-col gap-4" data-testid="eval-promotion-tab">
      {!enabled ? (
        <div className="card" data-testid="promotion-disabled-note">
          <div className="card-body text-sm text-[var(--text-secondary)]">
            Promotion is disabled (<code>TRACK_PROMOTION_ENABLED</code> is off). Gates below are
            informational. Enable only after a documented AB + soak per
            <code> docs/research/LAB_PROMOTION_GATES.md</code>.
          </div>
        </div>
      ) : null}

      <section className="card">
        <div className="card-header">
          <div className="card-title">Promotion readiness</div>
          <div className="text-xs text-[var(--text-faint)]">
            {gatesPass ? "All gates pass" : "Gates not met"}
          </div>
        </div>
        <div className="card-body">
          <ul>
            {(data?.gates ?? []).map((g) => (
              <GateRow key={g.id} id={g.id} passed={g.passed} detail={g.detail} />
            ))}
            {(data?.gates ?? []).length === 0 ? (
              <li className="py-1 text-sm text-[var(--text-faint)]">Loading gates…</li>
            ) : null}
          </ul>
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <div className="card-title">Promote challenger → champion</div>
        </div>
        <div className="card-body flex flex-col gap-3">
          <p className="text-sm text-[var(--text-secondary)]">
            Promotion requires passing gates, a written reason, and typing
            <strong> {CONFIRM_PHRASE}</strong> to confirm. Always reversible via Rollback.
          </p>
          <label className="text-sm">
            <span className="mb-1 block text-[var(--text-faint)]">Reason (audit trail)</span>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. AB + 4-week soak shows +CLV, gates green"
              className="w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-sm"
              data-testid="promotion-reason"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-[var(--text-faint)]">Type {CONFIRM_PHRASE} to confirm</span>
            <input
              type="text"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-44 rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-sm"
              data-testid="promotion-confirm"
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn btn-primary"
              disabled={!canPromote || promote.isPending}
              onClick={() => promote.mutate()}
              data-testid="promotion-promote-btn"
            >
              {promote.isPending ? "Promoting…" : "Promote"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={!enabled || rollback.isPending}
              onClick={() => rollback.mutate()}
              data-testid="promotion-rollback-btn"
            >
              {rollback.isPending ? "Rolling back…" : "Rollback dashboard"}
            </button>
          </div>
          {message ? (
            <p className="text-sm text-[var(--text-secondary)]" data-testid="promotion-message">
              {message}
            </p>
          ) : null}
        </div>
      </section>
    </div>
  )
}

function MetricCell({ label, value, suffix = "" }: { label: string; value: number | null; suffix?: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-[var(--text-faint)]">{label}</div>
      <div className="num text-lg text-[var(--text-primary)]">
        {value == null ? "—" : `${value}${suffix}`}
      </div>
    </div>
  )
}

function TrackMetricsCard({ track, metrics }: { track: "dashboard" | "lab"; metrics?: TrackMetrics }) {
  return (
    <section className="card" data-testid={`track-metrics-${track}`}>
      <div className="card-header flex items-center gap-2">
        <TrackBadge track={track} />
        {metrics?.low_sample ? (
          <span className="text-xs text-[var(--amber,#d97706)]" data-testid={`low-sample-${track}`}>
            low sample (n&lt;30)
          </span>
        ) : null}
      </div>
      <div className="card-body grid grid-cols-3 gap-3">
        <MetricCell label="Bets" value={metrics?.n ?? null} />
        <MetricCell label="Hit rate" value={metrics?.hit_rate_pct ?? null} suffix="%" />
        <MetricCell label="ROI (1u)" value={metrics?.roi_pct ?? null} suffix="%" />
        <MetricCell label="P/L (u)" value={metrics?.pnl_units ?? null} />
        <MetricCell label="Brier" value={metrics?.brier ?? null} />
        <MetricCell label="Wins" value={metrics?.wins ?? null} />
      </div>
    </section>
  )
}

function TrackCompareTab() {
  const [window, setWindow] = useState<"30d" | "90d" | "season">("30d")
  const query = useQuery({
    queryKey: ["track-comparison", window],
    queryFn: () => api.getTrackComparison(window),
    refetchInterval: 60_000,
  })
  const data = query.data
  return (
    <div className="flex flex-col gap-4" data-testid="eval-track-compare-tab">
      <div className="flex items-center gap-2">
        {(["30d", "90d", "season"] as const).map((w) => (
          <button
            key={w}
            type="button"
            className={`filter-chip${window === w ? " active" : ""}`}
            onClick={() => setWindow(w)}
            data-testid={`compare-window-${w}`}
            aria-pressed={window === w}
          >
            {w}
          </button>
        ))}
      </div>
      <p className="text-sm text-[var(--text-secondary)]">{data?.note}</p>
      <div className="grid gap-4 md:grid-cols-2">
        <TrackMetricsCard track="dashboard" metrics={data?.tracks?.cockpit} />
        <TrackMetricsCard track="lab" metrics={data?.tracks?.lab} />
      </div>
      <section className="card" data-testid="eval-overlap">
        <div className="card-header">
          <div className="card-title">Pick overlap</div>
        </div>
        <div className="card-body grid grid-cols-3 gap-3 text-center">
          <MetricCell label="Both" value={data?.overlap?.both ?? null} />
          <MetricCell label="Champion only" value={data?.overlap?.cockpit_only ?? null} />
          <MetricCell label="Challenger only" value={data?.overlap?.lab_only ?? null} />
        </div>
      </section>
    </div>
  )
}

const TABS = [
  { id: "compare", label: "Track compare" },
  { id: "promotion", label: "Promotion" },
] as const

export function EvalPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("compare")
  return (
    <div className="product-page product-page--satellite" data-testid="eval-page">
      <TerminalPageHeader
        eyebrow="Model validity"
        title="Eval"
        description="Prove the challenger before promoting it. Champion vs challenger evidence and gated promotion."
      />
      <div className="mt-4 flex gap-2" role="tablist" aria-label="Eval sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`filter-chip${tab === t.id ? " active" : ""}`}
            onClick={() => setTab(t.id)}
            data-testid={`eval-tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-4">
        {tab === "promotion" ? <PromotionTab /> : null}
        {tab === "compare" ? <TrackCompareTab /> : null}
      </div>
    </div>
  )
}

export default EvalPage
