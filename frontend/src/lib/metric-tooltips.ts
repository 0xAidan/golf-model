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
  ev: "Expected value vs posted implied probability (model edge).",
  winPct: "Model win probability for the pick side, before vig.",
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
