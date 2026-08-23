import { useCallback, useEffect, useState } from "react";

type CycleStatus = {
  heartbeat: { ts: string; stage: string; status: string } | null;
  heartbeat_age_seconds: number | null;
  next_nightly_utc: string;
  hours_until_next_cycle: number;
  effort: string;
};

type LedgerRow = Record<string, unknown> & {
  ts?: string;
  kind?: string;
  decision?: string;
  mutation?: string;
};

type Dossier = {
  config_hash?: string;
  status?: string;
  changes_vs_champion?: { scope: string; field: string; from: unknown; to: unknown }[];
  search_window?: { summary?: Record<string, unknown> };
  confirmation_window?: { summary?: Record<string, unknown> };
  multiplicity_context?: { trials_run_this_lineage?: number };
};

type Era = {
  config_hash: string | null;
  label: string | null;
  status: string;
  activated_at: string | null;
  picks: number;
  wins: number;
  win_rate_pct: number | null;
  roi_pct: number;
};

const apiGet = async <T,>(path: string): Promise<T> => {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status}`);
  return (await res.json()) as T;
};

const apiPost = async <T,>(path: string, body: unknown): Promise<T> => {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = (await res.json()) as T & { detail?: unknown };
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? res.status));
  return data;
};

const pct = (v: unknown) =>
  typeof v === "number" ? `${v > 0 ? "+" : ""}${v.toFixed(2)}%` : "—";

export function AutoresearchViewPage() {
  const [status, setStatus] = useState<CycleStatus | null>(null);
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [dossiers, setDossiers] = useState<Dossier[]>([]);
  const [eras, setEras] = useState<Era[]>([]);
  const [allTimeRoi, setAllTimeRoi] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [s, l, d, e] = await Promise.all([
        apiGet<CycleStatus>("/api/autoresearch/view/status"),
        apiGet<{ rows: LedgerRow[] }>("/api/autoresearch/view/ledger?limit=50"),
        apiGet<{ dossiers: Dossier[] }>("/api/autoresearch/view/promotion-ready"),
        apiGet<{ eras: Era[]; all_time: { roi_pct: number | null } }>(
          "/api/autoresearch/view/eras"
        ),
      ]);
      setStatus(s);
      setLedger(l.rows);
      setDossiers(d.dossiers);
      setEras(e.eras);
      setAllTimeRoi(e.all_time?.roi_pct ?? null);
    } catch {
      setMessage("Backend unreachable — is the API running?");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), 30_000);
    return () => clearInterval(t);
  }, [refresh]);

  const handleEffort = async (effort: string) => {
    setBusy(true);
    try {
      await apiPost("/api/autoresearch/view/effort", { effort });
      setMessage(`Effort set to ${effort}. Takes effect next cycle.`);
      await refresh();
    } catch (e) {
      setMessage(`Failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const handlePromote = async (configHash: string) => {
    const reason = window.prompt("Promotion reason (recorded in the audit trail):");
    if (!reason) return;
    setBusy(true);
    try {
      await apiPost("/api/autoresearch/view/promote-to-lab", {
        config_hash: configHash,
        reason,
      });
      setMessage("Lab track updated. Rollback available below.");
      await refresh();
    } catch (e) {
      setMessage(`Failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const handleRollback = async () => {
    setBusy(true);
    try {
      await apiPost("/api/autoresearch/view/rollback-lab", {});
      setMessage("Lab track rolled back to previous algorithm.");
      await refresh();
    } catch (e) {
      setMessage(`Failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-shell--route p-6 space-y-6 max-w-5xl mx-auto" aria-label="Autoresearch view">
      <header>
        <h1 className="text-2xl font-semibold">Autoresearch</h1>
        <p className="text-sm opacity-70">
          Autonomous research loop — it proposes; you promote.
        </p>
      </header>

      {message && (
        <div role="status" className="rounded-md border px-4 py-2 text-sm">
          {message}
        </div>
      )}

      {/* Cycle status + effort dial */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-lg border p-4">
          <div className="text-xs uppercase tracking-wide opacity-60">Next nightly cycle</div>
          <div className="text-lg font-medium num">
            {status ? `${status.hours_until_next_cycle}h` : "—"}
          </div>
          <div className="text-xs opacity-60">{status?.next_nightly_utc ?? ""} UTC</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs uppercase tracking-wide opacity-60">Last heartbeat</div>
          <div className="text-lg font-medium">
            {status?.heartbeat
              ? `${status.heartbeat.stage}: ${status.heartbeat.status}`
              : "no cycles yet"}
          </div>
          <div className="text-xs opacity-60">
            {status?.heartbeat_age_seconds != null
              ? `${Math.round(status.heartbeat_age_seconds / 60)} min ago`
              : ""}
          </div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs uppercase tracking-wide opacity-60">Effort</div>
          <div className="mt-2 flex gap-2" role="group" aria-label="Research effort">
            {["light", "standard", "max"].map((e) => (
              <button
                key={e}
                type="button"
                disabled={busy || status?.effort === e}
                onClick={() => void handleEffort(e)}
                aria-pressed={status?.effort === e}
                className={`px-3 py-1 rounded-md border text-sm ${
                  status?.effort === e ? "font-semibold bg-emerald-700/20" : ""
                } disabled:opacity-50`}
              >
                {e}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Promotion-ready */}
      <section>
        <h2 className="text-lg font-semibold mb-2">Promotion-ready candidates</h2>
        {dossiers.length === 0 && (
          <p className="text-sm opacity-60">None staged. The loop alerts you when one appears.</p>
        )}
        <div className="space-y-3">
          {dossiers.map((d) => (
            <article key={d.config_hash} className="rounded-lg border p-4 space-y-2">
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div className="num text-sm font-mono">{d.config_hash}</div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => d.config_hash && void handlePromote(d.config_hash)}
                    className="px-4 py-1.5 rounded-md border text-sm font-medium disabled:opacity-50"
                  >
                    Promote to Lab…
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleRollback()}
                    className="px-4 py-1.5 rounded-md border text-sm disabled:opacity-50"
                  >
                    Rollback lab
                  </button>
                </div>
              </div>
              <ul className="text-sm list-disc pl-5">
                {(d.changes_vs_champion ?? []).map((c) => (
                  <li key={`${c.scope}.${c.field}`}>
                    {c.scope} · {c.field}: {String(c.from)} → {String(c.to)}
                  </li>
                ))}
              </ul>
              <div className="text-sm opacity-80 num">
                Search ROI {pct(d.search_window?.summary?.weighted_roi_pct)} on{" "}
                {String(d.search_window?.summary?.total_bets ?? "?")} bets · Confirmation{" "}
                {pct(d.confirmation_window?.summary?.weighted_roi_pct)} on{" "}
                {String(d.confirmation_window?.summary?.total_bets ?? "?")} bets
              </div>
              <div className="text-xs opacity-60">
                Trials in lineage: {d.multiplicity_context?.trials_run_this_lineage ?? "?"} — treat
                the edge as provisional until the sealed holdout opens.
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* Algorithm eras */}
      <section>
        <h2 className="text-lg font-semibold mb-2">
          Algorithm eras{" "}
          <span className="text-sm font-normal opacity-70">(all-time matchup ROI: {pct(allTimeRoi)})</span>
        </h2>
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="opacity-60 text-left">
              <tr>
                <th className="px-3 py-2">Algorithm</th>
                <th className="px-3 py-2">Active</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Picks</th>
                <th className="px-3 py-2 text-right">Win %</th>
                <th className="px-3 py-2 text-right">ROI</th>
              </tr>
            </thead>
            <tbody>
              {eras.map((era) => (
                <tr key={`${era.config_hash}-${era.activated_at}`} className="border-t">
                  <td className="px-3 py-2 font-mono">{era.label ?? era.config_hash}</td>
                  <td className="px-3 py-2">{era.activated_at?.slice(0, 10) ?? "—"}</td>
                  <td className="px-3 py-2">{era.status}</td>
                  <td className="px-3 py-2 text-right num">{era.picks}</td>
                  <td className="px-3 py-2 text-right num">
                    {era.win_rate_pct != null ? `${era.win_rate_pct}%` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right num">{pct(era.roi_pct)}</td>
                </tr>
              ))}
              {eras.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-sm opacity-60">
                    No lab-track activations recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Ledger browser */}
      <section>
        <h2 className="text-lg font-semibold mb-2">Experiment ledger (latest)</h2>
        <div className="overflow-x-auto rounded-lg border max-h-96 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="opacity-60 text-left sticky top-0">
              <tr>
                <th className="px-3 py-2">When</th>
                <th className="px-3 py-2">Kind</th>
                <th className="px-3 py-2">Decision</th>
                <th className="px-3 py-2">Mutation / detail</th>
              </tr>
            </thead>
            <tbody>
              {ledger.map((row, i) => (
                <tr key={i} className="border-t">
                  <td className="px-3 py-2 whitespace-nowrap num">{row.ts?.slice(0, 19)}</td>
                  <td className="px-3 py-2">{row.kind}</td>
                  <td className="px-3 py-2">{row.decision ?? ""}</td>
                  <td className="px-3 py-2 truncate max-w-[28rem]" title={row.mutation}>
                    {row.mutation ?? JSON.stringify(row).slice(0, 90)}
                  </td>
                </tr>
              ))}
              {ledger.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-4 text-sm opacity-60">
                    Ledger empty.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default AutoresearchViewPage;
