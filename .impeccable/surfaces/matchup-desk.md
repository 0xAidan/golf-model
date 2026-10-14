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

Market family, Upcoming / In play context, search, book, minimum EV and sort live in the URL. The owner's Markets / My card / Results navigation carries that query string, so returning to the board preserves the investigation. My card makes no board or evidence requests, Results requests only evidence, and leaving either data surface cancels obsolete requests. Cached board rows remain visible during revalidation with a checking label; new saves wait for that check.

| Built component | Surface responsibility |
| --- | --- |
| `MatchupDesk` / `MarketBoard` in `matchup-desk.tsx` | Shared navigation, URL filter context, route-specific reads and quote-save eligibility. |
| `CardPage` / `ShareCard` in `card-page.tsx` | Browser-local card, CSV export, subset selection and fixed share-link creation. |
| `SavedPickList` in `card-page.tsx` | Reused quote presentation and expandable provenance; removal appears only on the owner's card. |
| `CopyPicks` in `card-page.tsx` | Explicit clipboard action, status feedback and manual-copy fallback. |
| `SharedCardPage` in `shared-card-page.tsx` | Standalone read-only snapshot, loading/error states and recipient copy action. |

The extension retains `DESIGN.md` and `.impeccable/design.json` unchanged: the composer uses the existing square paper surface, thin rules, accent action and small-radius fields. At 560px and below its padding reduces from 24px to 16px; selection count and link field take full rows. Saved records retain the existing one-column reflow below 850px and labeled values below 560px. Reviewed captures are `.impeccable/review/share-composer-{desktop,mobile,668}.png` and `shared-reader-{desktop,mobile}.png`; their explicitly labeled fixtures verify layout, not live market performance.

## FORM / signature

FORM seed `c9f11010` is corroborated by `.impeccable/questions/roll.json`. The team-golf broadcast comparison becomes a shared 0–100% probability rule in selected matchup details: a round model marker and a vertical bookmaker break-even marker show both supplied values. This ties the design directly to the product's price-comparison purpose. The bookmaker value is not an opponent complement or a new forecast; omit the rule unless both original probabilities are present.

## Boundaries

Do not mutate original model outputs, historic picks, grades, source weights or configurations. New reporting reads SQLite without init or migrations. Group data remains research-only unless the existing model explicitly supplies eligible rows. Unknown market duration stays unknown. Old routes remain reachable in More tools.

## Responsive and quality bar

Desktop: stable table plus evidence aside. Mobile: event context above horizontally scrollable market tabs, readable stacked matchup rows, evidence below. Keyboard access, explicit labels, reduced motion, current/loading/error/empty/stale states. Review actual 1440px, 390px and user viewport. No decorative photography, fake profit figures or generic metric tiles. Flat saved-quote containers and their mobile stacking remain part of the shipped system.
