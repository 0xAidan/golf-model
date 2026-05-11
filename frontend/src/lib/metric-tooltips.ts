/**
 * Copy for native `title` tooltips across cockpit tables and KPI tiles.
 * Keeps explanations aligned wherever the same metric appears.
 */

export const SG_TRAJECTORY_HELP =
  "Rolling SG:TOT rank movement across time windows (vs career-long baseline). Not the same as last week's tournament finish."

export const POWER_RANKINGS_HELP = {
  rank: "Sort position on the current event board (1 = top of the model ordering).",
  player: "Player from the field list. Click the row to open spotlight and context.",
  composite:
    "Blended 0–100 score combining course fit, recent form, and momentum for this event. Higher is stronger vs the field.",
  form: "Recent-performance sub-score (rolling rounds and skill trends), 0–100 within this field.",
  course:
    "Course-fit sub-score: how well the player's historical strokes-gained profile matches this venue, 0–100.",
  momentum:
    "Momentum sub-model score (recent trend vs baseline), 0–100 within this field — distinct from SG trajectory.",
  sgTraj: SG_TRAJECTORY_HELP,
} as const

/** Player spotlight grid — keyed by stat label as rendered in the UI. */
export const SPOTLIGHT_STAT_TOOLTIPS: Record<string, string> = {
  Leaderboard: "Live tournament position label from the current leaderboard feed (e.g. T2).",
  "To par": "Total strokes vs par so far this week on the live board.",
  "Featured plays": "Count of top-picks list rows that name this player as the pick or opponent.",
  "Generated picks": "Count of matchup or secondary lines in the full generated inventory for this player.",
  "Replay rank": "Model rank stored on the replay snapshot for this completed event.",
  Composite: POWER_RANKINGS_HELP.composite,
  "Model rank": "The player's rank on the power rankings table for the active event context.",
  "Latest round": "Most recently posted completed round number in live scoring.",
  "Round score": "Stroke total for that latest posted round (gross, not vs par).",
  "Secondary markets": "Count of generated secondary prop/top-N style lines tied to this player.",
  "Replay focus": "Spotlight is showing saved card and pick context from the replay capture, not live data.",
  Form: POWER_RANKINGS_HELP.form,
  "Course fit": POWER_RANKINGS_HELP.course,
  Momentum: "Momentum sub-model score (trend vs baseline), 0–100 within this field.",
  "Best fit now": "Which single sub-score (composite, form, course fit, or momentum) is currently highest for this player.",
}

/** Live leaderboard table column headers. */
export const LEADERBOARD_COLUMN_TOOLTIPS: Record<string, string> = {
  Pos: "Leaderboard position (ties use standard golf notation).",
  Player: "Player name; click to select and sync spotlight.",
  Score: "Total strokes vs par for the tournament to date.",
  Rd: "Label for the latest round reflected in this row.",
  Tot: "Total strokes (gross) or event total score per the feed — use with the round column for context.",
}

/** Top picks / matchup tables. */
export const MATCHUP_TABLE_TOOLTIPS = {
  pick: "Model pick vs opponent for this matchup market.",
  pickVsOpp: "Bet side (pick) versus the listed opponent.",
  bookOdds: "Sportsbook and posted price used for the edge calculation.",
  book: "Sportsbook offering this line.",
  odds: "American odds as fetched for this pick.",
  tier: "Confidence bucket from model conviction and filters (e.g. STRONG vs LEAN).",
  reason: "Short model rationale when the pipeline attached one.",
  ev: "Expected value vs posted implied probability using the model's ev_prob (calibrated, placement dead-heat when applicable) — not vs de-vigged fair odds.",
  winPct: "Blended model win probability for the pick side (DG + model where applicable). EV uses the same mass as this display unless the row exposes ev_prob for audit.",
  result:
    "Past events only: graded head-to-head result from final finishes (W/L), push (P), Pending when data is incomplete, or unavailable (—) for markets we do not derive here.",
  lane: "Bet type or pipeline lane (e.g. matchup vs alternate line).",
  market: "Secondary market type (top 5, top 10, etc.).",
  player: "Player named on the prop or finishing market.",
  opponent: "Opposing player or field side when the line is a matchup.",
} as const

export const GRADING_TABLE_TOOLTIPS = {
  event: "Tournament or snapshot that was graded after completion.",
  pl: "Profit or loss in your configured units for that event's card.",
  hitPct: "Share of graded picks that won or pushed as a hit, for that event.",
  modelWin: "Model-assigned win chance for the pick at decision time.",
  edgePct: "Edge vs implied odds (percentage points).",
  result: "Recorded outcome for the ticket (win/loss/push or finish context).",
} as const

export const PLAYER_PROFILE_TABLE_TOOLTIPS = {
  event: "Tournament name for this history row.",
  date: "Start or round reference date from the history feed.",
  finish: "Finishing position or cut notation when available.",
  avgSg: "Average strokes gained total per round in that event, from stored rounds.",
  bet: "Market or matchup label from the profile's bet list.",
  confidence: "Grading or tier label attached to that line.",
} as const

/** Metric tiles built in cockpit-event-models (Course feed, leaderboard rail, market intel, replay, diagnostics). */
export const COCKPIT_METRIC_TOOLTIPS: Partial<Record<string, string>> = {
  "Replay captures": "Number of immutable snapshot records stored for this event's timeline.",
  "Weather lean": "Largest weather-driven model adjustment among ranked players on the board.",
  "Field risk": "Whether the field mix triggered cross-tour or data-quality warnings.",
  "Snapshot freshness": "Seconds since the prediction snapshot backing this view was built.",
  Leader: "Best score to par on the visible leaderboard slice.",
  "Visible rows": "Players shown in the current leaderboard table after filters.",
  "Rounds logged": "Round rows present in the database for players on this board.",
  "Opening watchlist": "Pre-tournament ranked players before live scores replace seeding.",
  "Seeded rows": "Leaderboard rows still mirroring model ranks until live scoring arrives.",
  "Top composite": "Highest composite score among players visible in this leaderboard list.",
  "History rows": "Past-market rows stored for this event in replay or history mode.",
  "Books seen": "Distinct sportsbook sources represented in the current lines sample.",
  "Best edge": "Strongest positive EV among rows in the current market sample.",
  "Latest rows": "Count of current live or pre-tournament market rows.",
  "Current rows": "Active market lines in the working snapshot.",
  "Best captured edge": "Best EV recorded in the stored replay or historical scrape.",
  "Latest capture": "Timestamp of the most recent replay snapshot.",
  "Last snapshot": "When the pipeline last wrote a decision snapshot for this context.",
  "Model lane": "Which model output or blend is driving the current card.",
  "Snapshot state": "Pipeline or replay state label for diagnostics.",
  "AI layer": "Whether qualitative AI commentary was merged for this run.",
  "Strategy source": "Which strategy profile or registry entry supplied weights and gates.",
  "Rows selected": "Lines that passed filters into the exportable card for this run.",
}

/** Expanded matchup row (inline details). */
export const MATCHUP_DETAIL_TOOLTIPS = {
  compositeGap: "Difference in composite model score between pick and opponent — overall strength gap.",
  formGap: "Difference in recent-form sub-score between the two sides.",
  courseGap: "Difference in course-fit sub-score for this venue/setup.",
  impliedProb: "Win probability implied by the posted American price (raw, includes vig; not de-vigged).",
  conviction: "Model conviction score for this matchup (internal strength-of-signal, not tier).",
  momentum: "Whether short-term momentum / trajectory lines up with the pick vs mixed signals.",
} as const

export const EV_BADGE_TOOLTIP =
  "Expected value: model fair win probability vs the book line — positive means edge over implied odds before vig."

export const TIER_BADGE_TOOLTIP =
  "Confidence tier from conviction and pipeline filters (e.g. STRONG / GOOD / LEAN). Higher tiers met stricter gates."

/** Players page — header KPI strip (database / DG header). */
export const PLAYER_PAGE_KPI_TOOLTIPS: Record<string, string> = {
  "DG Rank": "Data Golf skill-based ranking when available for this player.",
  OWGR: "Official World Golf Ranking position stored in the profile.",
  "DG Skill": "Data Golf estimated strokes-gained skill vs an average tour baseline.",
  "Total SG": "Strokes gained: total — overall vs-field performance from skill estimates.",
  "Events (DB)": "Tournament events with stored results for this player locally.",
  "Rounds (DB)": "Round rows saved in the database (drives rolling sample depth).",
}

/** Metric cards & tiles used on Players page + profile drill-down (label must match UI text). */
export const PLAYER_PROFILE_STAT_TOOLTIPS: Record<string, string> = {
  "Model Rank": "Rank on the current event's power rankings board.",
  Composite: POWER_RANKINGS_HELP.composite,
  Form: POWER_RANKINGS_HELP.form,
  "Course Fit": POWER_RANKINGS_HELP.course,
  "Course fit": POWER_RANKINGS_HELP.course,
  Momentum: POWER_RANKINGS_HELP.momentum,
  "DG Rank": PLAYER_PAGE_KPI_TOOLTIPS["DG Rank"],
  OWGR: PLAYER_PAGE_KPI_TOOLTIPS.OWGR,
  "DG Skill": PLAYER_PAGE_KPI_TOOLTIPS["DG Skill"],
  "Primary Tour": "Primary tour affiliation from Data Golf (PGA Tour, DP World, etc.).",
  Distance: "Driving distance from the skill profile (yards).",
  Accuracy: "Driving accuracy / effectiveness from the skill profile (share or SG context).",
}

export const ROLLING_FORM_TILE_TOOLTIPS = {
  avgSgWindow: "Average strokes gained per round over the selected L10 / L25 / L50 window.",
  benchmarkSg: "Benchmark cohort SG per round for the same window (tour avg, top 50, or top 10).",
  edgeVsBench: "Player window SG minus benchmark — quick read vs peer baseline.",
} as const

export const ROLLING_SG_GRID_HEADER_TOOLTIPS: Record<string, string> = {
  Window: "Rolling lookback: last N recorded rounds in each row.",
  TOTAL: "Strokes gained total per round vs the field.",
  OTT: "Strokes gained off the tee (driving).",
  APP: "Strokes gained on approach shots.",
  ARG: "Strokes gained around the green.",
  PUTT: "Strokes gained putting.",
  T2G: "Tee-to-green strokes gained (off-tee + approach + around-green).",
}

export const ROLLING_WINDOW_ROW_TOOLTIP =
  "Values use only rounds inside that lookback window (L10 = last 10 rounds, etc.)."

export const PROFILE_COURSE_SUMMARY_TOOLTIPS: Record<string, string> = {
  "Events Tracked": "Count of recent tournaments in the profile history sample.",
  "Cuts Made": "Cuts made in that recent sample.",
  "Recent Avg SG": "Mean strokes gained total per round across those recent events.",
  "Course Avg SG": "Historical mean SG at courses in the profile's course-history sample.",
}

export const PROFILE_BETTING_SUMMARY_TOOLTIPS: Record<string, string> = {
  "Linked Bets": "Bets tied to this player in the current card or profile export.",
  "Avg EV": "Average expected value across those linked lines.",
  "High Confidence": "How many linked bets used a high-confidence bucket.",
}

export const CHAMPION_TABLE_TOOLTIPS = {
  model: "Registry strategy name — champion is live; challengers are shadow-only.",
  brier30: "Brier score on 30-day window — lower means better probability calibration.",
  n: "Count of prediction outcomes in the Brier window.",
  roi14: "Matchup ROI % on trailing 14 days (paper/shadow).",
  roi30: "Matchup ROI % on trailing 30 days.",
  clv30: "Closing line value in basis points over 30 days (line vs close).",
} as const

export const GRADING_KPI_STRIP_TOOLTIPS: Record<string, string> = {
  "Total P&L": "Sum of graded profit/loss across tournaments in this view.",
  Tournaments: "Number of graded events represented.",
  "Hit rate": "Hits divided by graded picks (wins + pushes counted per your grading rules).",
  "Latest event": "Most recently graded event summary.",
  Course: "Venue name stored for that graded tournament.",
  Year: "Season year for the graded event.",
  "Win rate": "Wins over all resolved picks in the track-record summary.",
  Wins: "Count of winning picks in the track record summary.",
}

export const SPOTLIGHT_NOTE_TOOLTIPS: Record<string, string> = {
  "Featured play": "Line appearing on the live or upcoming top-picks table for this player.",
  "Captured featured play": "Featured play saved on the past-event replay snapshot.",
  "Best secondary market": "Strongest EV secondary (prop/top-N) line for this player.",
  "Generated matchup inventory": "Number of generated matchup rows mentioning this player.",
  "Dashboard context": "Player is selected for context even without a featured or secondary line.",
}

export const PROFILE_CHART_LABEL_TOOLTIPS: Record<string, string> = {
  sgPerRoundBars: "Each bar: strokes gained in that skill bucket vs tour average (0 = baseline).",
  modelScoreComponents: "Internal model decomposition when Data Golf skill bars are unavailable.",
  sgRoundTrend: "Chronological rounds: each point is SG:total for one round.",
  avgSgByEvent: "One column per event — height is mean SG:total for rounds in that event.",
  courseHistorySpark: "Sequential course-history events by average SG (older toward the left).",
}

export const ROLLING_UI_TOOLTIPS = {
  windowPills: "How many recent rounds feed the rolling averages (L10 / L25 / L50).",
  benchmarkPills: "Cohort baseline for comparison: tour average, top 50, or top 10 SG.",
} as const

export const SKILL_HIGHLIGHT_TOOLTIPS = {
  strength: "Skill bucket with the strongest strokes-gained vs tour baseline in this profile.",
  weakness: "Skill bucket furthest below tour baseline in this profile.",
} as const
