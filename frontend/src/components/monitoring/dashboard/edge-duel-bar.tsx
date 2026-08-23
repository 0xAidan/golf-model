/**
 * EdgeDuelBar — the signature "model vs market" visual.
 * Model probability fills from the right in emerald, market implied
 * from the left in blue; they duel toward the center. Center shows
 * the edge percentage. Pure CSS (overhaul.css) — motion-safe.
 */
export function EdgeDuelBar({
  modelProb,
  marketProb,
  edgePct,
  testId,
}: {
  modelProb: number // 0..1
  marketProb: number // 0..1
  edgePct: number
  testId?: string
}) {
  const modelPct = Math.max(0, Math.min(100, modelProb * 100))
  const marketPct = Math.max(0, Math.min(100, marketProb * 100))

  return (
    <div className="edge-duel" data-testid={testId ?? "edge-duel"}>
      <div className="edge-duel__side edge-duel__side--model" aria-hidden>
        <div className="edge-duel__fill" style={{ width: `${modelPct}%` }} />
      </div>
      <span className="edge-duel__center num">
        {edgePct >= 0 ? "+" : ""}
        {(edgePct * 100).toFixed(1)}%
      </span>
      <div className="edge-duel__side edge-duel__side--market" aria-hidden>
        <div className="edge-duel__fill" style={{ width: `${marketPct}%` }} />
      </div>
    </div>
  )
}
