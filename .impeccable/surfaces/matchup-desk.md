# Matchup desk

Mode: Operate. Build: code-led. The owner delegated the overhaul and wants autonomous implementation; the confirmed workflow is personal card building plus shared picks, with full-stack speed and reliability.

## Direction

Grounded candidates, in resonance order: golf scorecard typography; European sports annual; caddie yardage annotations; tournament pairings sheet; clubhouse wayfinding; international team-golf broadcast graphics; championship results archive. FORM seed c9f11010 assigned candidate six; the retained roll is `.impeccable/questions/roll.json`. Its contribution is a deep evergreen masthead, cool pale ground, condensed Barlow heading type, clear tabular numbers, and the split probability rule in a matchup detail. Standard web navigation, filters and tables carry the actual workflow.

The challengers were evaluated for audience recognition and clarity: type specimen, botanical folio, orienteering map, Crouwel grid, convention catalog and airline wallet all lose both to team-golf broadcast at this scope. Kept disciplines: type specimen's clear type hierarchy; folio's consistent comparisons; map's unambiguous state colors; Crouwel's alignment; catalog's compact scanning; wallet's explicit preserved states. No visual motifs borrowed.

## First viewport

An evergreen horizontal masthead contains Golf Model and visible Markets / My card / Results links. On Markets, the event name, course, data timestamp and Upcoming / In play context form one row below it. A market tab strip exposes 72 holes, 18 holes, Groups and Other markets. Search, book and edge controls sit directly above the market table. A right-hand evidence column links market history and shows honest coverage. No models, deployment vocabulary or research tools interrupt this flow.

When no lines exist, the board says so and gives event research and results as useful destinations. It never fills the table with invented opportunities. With rows, selecting a matchup opens an inline comparison and the frozen model probability/price/EV, then saves that exact quote to a personal card. The card preserves its original timestamp and warns when the quote is no longer current. Saving is research, not bet placement.

## Card and sharing extension

My card keeps saved selections in this browser. Its heading leads to Share picks and CSV export; each saved record retains its price, model win probability, EV, event, market, round when supplied, explanation and source timestamps. Quote record reveals the snapshot and saved times, source market and event ID. The current event bar is absent here because a card can contain earlier events.

Share picks opens an inline composer in place of the saved-record list. Ruled checkbox rows pair matchup identity with the saved book price. The owner chooses up to 32 picks, creates a link, then copies it or previews the recipient view. Copy picks also supplies formatted text, with a selectable text fallback if clipboard access fails. Changing the selection clears the generated link and previous copy fallback. Closing the composer returns to the saved records without changing the card.

The `/shared-card#card=…` reader uses the same saved-record presentation without removal or saving controls. It decodes a fixed snapshot from the link, displays its sharing time, and labels selections unverified and prices potentially changed. Anyone with the link can read it; later edits to the owner's card do not update it. Copy picks is the reader's primary action. Incomplete or unsupported links have an explicit error state. This route does not import picks into the recipient's browser card or request current market data.

Market family, Upcoming / In play context, search, book, minimum EV and sort live in the URL. The owner's Markets / My card / Results navigation carries that query string, so returning to the board preserves the investigation. My card makes no board or evidence requests; Results reads the season report or current-store evidence for its selected view. Leaving a data surface cancels obsolete board or current-evidence requests. Cached board rows remain visible during revalidation with a checking label; new saves wait for that check.

| Built component | Surface responsibility |
| --- | --- |
| `MatchupDesk` / `MarketBoard` in `matchup-desk.tsx` | Shared navigation, URL filter context, route-specific reads and quote-save eligibility. |
| `CardPage` / `ShareCard` in `card-page.tsx` | Browser-local card, CSV export, subset selection and fixed share-link creation. |
| `SavedPickList` in `card-page.tsx` | Reused quote presentation and expandable provenance; removal appears only on the owner's card. |
| `CopyPicks` in `card-page.tsx` | Explicit clipboard action, status feedback and manual-copy fallback. |
| `SharedCardPage` in `shared-card-page.tsx` | Standalone read-only snapshot, loading/error states and recipient copy action. |

The extension retains `DESIGN.md` and `.impeccable/design.json` unchanged: the composer uses the existing square paper surface, thin rules, accent action and small-radius fields. At 560px and below its padding reduces from 24px to 16px; selection count and link field take full rows. Saved records retain the existing one-column reflow below 850px and labeled values below 560px. Reviewed captures are `.impeccable/review/share-composer-{desktop,mobile,668}.png` and `shared-reader-{desktop,mobile}.png`; their explicitly labeled fixtures verify layout, not live market performance.

## Season Results extension

Results opens Season record at `/evidence`; the adjacent Current store link preserves the existing evidence view at `/evidence?view=store`. This second navigation uses the established underline treatment and retains the board query context. `SeasonResults` in `season-results.tsx` reads the published 2026 report snapshot; its heading shows the snapshot date and links to Report JSON and Audit rows CSV. Loading and unavailable states remain explicit, with retry and a Current store alternative. This report view does not request the current board or current-store evidence.

The market record table separates Dashboard and Lab lanes. It shows all market families, including those with no records, and distinguishes all records from qualified settled returns. Selecting a market scopes the coverage strip and selection research; it does not remove the other market rows. Model version is a separate selector within selection research, not a filter on the market record table. The research heading repeats market, lane and version so its figures cannot be mistaken for the broader table totals.

Paper return displays stored profit in units; its ROI is stored profit divided by stored stake for complete, consistent settled contracts. The source-basis notice stays above the table. Incomplete contracts, conflicts and missing round IDs remain visible while their returns are withheld; absent returns use an em dash. Qualified zero returns are not labeled pushes, and stored voids remain archive labels. Neither positive return color nor a recovered record claims a verified placed bet, sportsbook settlement or bankroll result.

`EventCoverage` maps each calendar event to a keyboard-selectable mark. Filled accent means recovered records, an accent outline means archived cards only, dashed amber means no reconciled picks, and an unfilled mark means upcoming. The selected event has an ink underline and an expanded detail area; arrow keys, Home and End move through events. The strip follows the selected market but explicitly covers both model lanes. Its event count compares elapsed events with reconciled picks against all elapsed calendar events, preserving gaps rather than treating them as losses. Within event detail, record and archived-card counts follow the market; conflicts and selection eligibility remain labeled as event-wide counts across all markets. Archived cards are source evidence, not settled records. A disclosure retains the full calendar table; the selected event links to official dates when a source URL is available.

Selection research distinguishes the report-wide eligible count across all markets, lanes and versions from the selected scope's eligible records and events. The visible status is **No rule promoted**. Fixed-rule comparisons use the selected market, lane and version, show their required earlier/later event and decision counts, and disclose that later events are retrospective rather than an untouched holdout. The comparison disclosure starts open only when at least one displayed rule has sufficient evidence. Nothing on this surface changes model outputs or live pick order. Sources, gaps, caveats and the report identifier remain in a separate disclosure.

On desktop, market records use the existing aligned table. At 560px and below, each populated market exposes just All records and Paper return first; Outcome & evidence details reveals wins, losses, zero returns, voids, incomplete/conflicting, ungraded and selection-eligible counts. Empty markets stay compact with their explicit no-records label. The calendar changes from 24 columns to 12 at 850px, and event metrics use two columns on mobile. Rule comparisons reflow into labeled records; the full calendar table keeps horizontal scrolling inside its disclosure. These are surface-specific density choices, not a new global rule to hide evidence.

`season-results.css` reuses the desk's semantic palette, Barlow Condensed headings, Barlow data, ruled surfaces, native selects and disclosure chevrons. No durable token or world change is needed in `DESIGN.md` or `.impeccable/design.json`. The implemented scope and responsive structure are corroborated by `.impeccable/review/season-desktop-final.png` and `season-mobile-final.png`; their snapshot counts are evidence of that report, not permanent design values.

## FORM / signature

FORM seed `c9f11010` is corroborated by `.impeccable/questions/roll.json`. The team-golf broadcast comparison becomes a shared 0–100% probability rule in selected matchup details: a round model marker and a vertical bookmaker break-even marker show both supplied values. This ties the design directly to the product's price-comparison purpose. The bookmaker value is not an opponent complement or a new forecast; omit the rule unless both original probabilities are present.

## Boundaries

Do not mutate original model outputs, historic picks, grades, source weights or configurations. New reporting reads SQLite without init or migrations. Group data remains research-only unless the existing model explicitly supplies eligible rows. Unknown market duration stays unknown. Old routes remain reachable in More tools.

## Responsive and quality bar

Desktop: stable table plus evidence aside. Mobile: event context above horizontally scrollable market tabs, readable stacked matchup rows, evidence below. Keyboard access, explicit labels, reduced motion, current/loading/error/empty/stale states. Review actual 1440px, 390px and user viewport. No decorative photography, fake profit figures or generic metric tiles. Flat saved-quote containers and their mobile stacking remain part of the shipped system.
