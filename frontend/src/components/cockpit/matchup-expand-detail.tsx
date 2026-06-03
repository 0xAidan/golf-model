import { formatNumber } from "@/lib/format"
import { MATCHUP_DETAIL_TOOLTIPS } from "@/lib/metric-tooltips"
import type { MatchupBet } from "@/lib/types"

export function MatchupExpandDetail({ matchup }: { matchup: MatchupBet }) {
  return (
    <div className="matchup-detail">
      <div className="matchup-detail-grid">
        <div>
          <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.compositeGap}>
            Composite gap
          </div>
          <div className="detail-item-value num">{formatNumber(matchup.composite_gap, 2)}</div>
        </div>
        <div>
          <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.formGap}>
            Form gap
          </div>
          <div className="detail-item-value num">{formatNumber(matchup.form_gap, 2)}</div>
        </div>
        <div>
          <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.courseGap}>
            Course gap
          </div>
          <div className="detail-item-value num">{formatNumber(matchup.course_fit_gap, 2)}</div>
        </div>
        <div>
          <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.impliedProb}>
            Implied prob
          </div>
          <div className="detail-item-value num">{(matchup.implied_prob * 100).toFixed(1)}%</div>
        </div>
        <div>
          <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.conviction}>
            Conviction
          </div>
          <div className="detail-item-value num">{formatNumber(matchup.conviction, 0)}</div>
        </div>
        <div>
          <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.momentum}>
            Momentum
          </div>
          <div
            className={`detail-item-value ${matchup.momentum_aligned ? "metric--positive" : "metric--neutral"}`}
          >
            {matchup.momentum_aligned ? "Aligned ↑" : "Mixed"}
          </div>
        </div>
      </div>
      {matchup.reason ? (
        <div className="matchup-detail-reason">{matchup.reason}</div>
      ) : null}
    </div>
  )
}
