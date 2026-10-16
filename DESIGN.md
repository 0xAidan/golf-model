---
name: "Golf Model — Rankings Workspace"
description: "The shipped field index, evidence charts and model-learning workspace."
colors:
  bg: "#f6f8f7"
  paper: "#fff"
  ink: "#182e28"
  muted: "#596b64"
  faint: "#6b7c74"
  rule: "#dce5df"
  tint: "#edf3ef"
  accent: "#1c684e"
  positive: "#1b6e4d"
  negative: "#a33e39"
  rail: "#163d32"
  rail-text: "#c0d1c6"
  warning: "#78541d"
  warning-bg: "#f7f0e3"
  dark-bg: "#14231e"
  dark-paper: "#192b24"
  dark-ink: "#e6eee9"
  dark-muted: "#b1c4b8"
  dark-faint: "#a0b3a7"
  dark-rule: "#344b3e"
  dark-tint: "#243b2f"
  dark-accent: "#a0cbb0"
  dark-positive: "#a4d5b7"
  dark-negative: "#f0a29c"
  dark-rail: "#10342a"
  dark-rail-text: "#c3d5c9"
  dark-warning: "#e9c281"
  dark-warning-bg: "#3b3222"
  rail-active: "#e2eddf"
  rail-active-ink: "#234836"
  rail-hover: "#254d3e"
  dark-button-ink: "#163025"
typography:
  display:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "34px"
    fontWeight: 500
    lineHeight: 1.18
    letterSpacing: "-0.035em"
  rankings-heading:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "27px"
    fontWeight: 500
    lineHeight: 1.18
    letterSpacing: "-0.035em"
  rankings-heading-mobile:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "25px"
    fontWeight: 500
    lineHeight: 1.18
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 500
    lineHeight: 1.4
  body:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  control:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.5
  table:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
  support:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.6
  metric:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "-0.02em"
  player-score:
    fontFamily: "Switzer, Arial, sans-serif"
    fontSize: "43px"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "-0.045em"
rounded:
  segment: "3px"
  control: "4px"
  panel: "5px"
  circle: "50%"
spacing:
  compact: "8px"
  control-gap: "12px"
  mobile-rankings-gutter: "16px"
  compact-panel: "18px"
  mobile-panel: "20px"
  panel: "22px"
  section: "24px"
  compact-main: "25px"
  board-gap: "30px"
  main-gutter: "38px"
  wide-gutter: "48px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "10px 15px"
  button-primary-hover:
    backgroundColor: "color-mix(in srgb, var(--lw-accent) 88%, var(--lw-ink))"
  button-primary-dark:
    backgroundColor: "{colors.dark-accent}"
    textColor: "{colors.dark-button-ink}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "10px 15px"
  button-secondary-hover:
    backgroundColor: "{colors.tint}"
  button-icon:
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    width: "36px"
    height: "36px"
  input-search:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  input-select:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 28px 8px 10px"
  nav-primary:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.rail-text}"
  nav-selected:
    backgroundColor: "{colors.rail-active}"
    textColor: "{colors.rail-active-ink}"
    rounded: "{rounded.panel}"
    padding: "12px 15px"
  segmented-control:
    backgroundColor: "{colors.tint}"
    rounded: "{rounded.panel}"
    padding: "3px"
  segmented-selected:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.segment}"
    padding: "6px 12px"
  chip-research:
    backgroundColor: "{colors.warning-bg}"
    textColor: "{colors.warning}"
    rounded: "{rounded.segment}"
    padding: "5px 8px"
  panel:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "22px"
  panel-analysis:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "23px"
  ranking-selected:
    backgroundColor: "{colors.tint}"
    textColor: "{colors.ink}"
    typography: "{typography.table}"
---

# Design System: Golf Model — Rankings Workspace

## Overview

**Creative North Star: "The Club Field Index"**

A quiet field index pairs deep pine navigation with cool paper, pale sage selection and precise ruled records. Switzer carries headings, controls and tabular data in one voice. The application is compact enough to compare a full field while keeping source dates, model identity and uncertain evidence close to the values they qualify.

This system covers the shipped Rankings, Markets, Performance, Models, My card and Season archive workspace. Light and dark themes share structure and semantic roles. Embedded market and archive surfaces inherit the new palette and heading family while retaining their existing record geometry. Linked player, research, evaluation and system tools retain their earlier terminal system; the standalone shared-card reader retains the earlier desk shell.

**Key Characteristics:**

- Pine navigation with a pale, text-labeled active item.
- Self-hosted Switzer throughout the workspace, with tabular numerals.
- Flat paper panels, thin rules and modest control corners.
- Persistent selected-player identity with a shared field distribution and component bars.
- Charts and tables that keep units, cohort, model version and missing evidence visible.

This refresh supersedes the old Matchup Desk world for the workspace routes. Its durable commitments to tabular comparisons, explicit evidence states, paired themes and SVG markers remain. Source evidence: `frontend/src/features/learning-workspace/learning-workspace.css`, its TSX pages and charts, embedded `frontend/src/features/matchup-desk/` styles and components, and `frontend/src/App.tsx`. The finished desktop, tablet, mobile, dark, Performance, Markets and Models captures in `.impeccable/review/` corroborate the implementation. `PRODUCT.md` supplies the durable obligation to preserve the baseline and historical evidence; the surface contract supplies the confirmed world, not token values.

## Colors

Cool paper and sage work areas sit beside a deep pine rail. Green identifies selection and measured data; amber and muted red qualify evidence and results. The frontmatter owns the exact shipped values. The sidecar's eight-step OKLCH ramps are synthesized preview swatches, not additional application tokens.

### Primary

- **Field green** (`accent`, `dark-accent`): primary buttons, selected score marks, chart lines, component bars, links and focus outlines.
- **Pine rail** (`rail`, `dark-rail`): persistent navigation in both themes.
- **Positive green** (`positive`, `dark-positive`): positive paper results and market EV; it remains distinct from a verified outcome claim.

### Secondary

- **Amber caution** (`warning`, `warning-bg`, and dark counterparts): research status, source age, incomplete evidence and availability notices.
- **Muted result red** (`negative`, `dark-negative`): negative measured results and error feedback.

### Neutral

- **Cool ground / paper** (`bg`, `paper`, and dark counterparts): page ground and bordered data surfaces.
- **Ink / supporting ink** (`ink`, `muted`, `faint`, and dark counterparts): primary values, readable context and minor chart guides.
- **Rule / sage tint** (`rule`, `tint`, and dark counterparts): separators, table headings, selected records and control tracks.
- **Rail text / active sage** (`rail-text`, `dark-rail-text`, `rail-active`, `rail-active-ink`, `rail-hover`): navigation labels and a pale selected item. On mobile, selected text uses the existing pine-rail value and a green bottom rule.
- **Dark action ink** (`dark-button-ink`): legible dark lettering on the pale dark-theme primary button.

**The Paired State Rule.** Pair state color with text, a marker or a structural change: selected records retain their identity, warnings explain the limitation, and saved quotes show a check.

## Typography

**Display Font:** Switzer, with Arial and sans-serif fallbacks.
**Body Font:** Switzer, with the same fallbacks.
**Label/Mono Font:** Switzer; run identifiers also inherit it rather than introducing a second family.

The workspace self-hosts `switzer-regular.woff2` at weight 400 and `switzer-medium.woff2` declared for weights 500–800, with swap loading. This is a regular/medium file pairing, not evidence of a variable font or separate bold files. Numerical content uses `font-variant-numeric: tabular-nums` throughout.

### Hierarchy

- **Display:** general page heading. It reduces to 30px at the compact desktop breakpoint and 29px on mobile. Rankings uses the separate `rankings-heading` and `rankings-heading-mobile` roles to keep the field high in the viewport.
- **Headline / title:** section headings and supporting headings. Event names and individual panels make local size adjustments within the same medium-weight family.
- **Body / table:** the workspace base and aligned record values. Table headers and some metadata are smaller contextual annotations, not a second display voice.
- **Control:** the shared framed-action role. Navigation uses 13px on desktop; native fields and most buttons use 12px.
- **Support:** compact explanatory prose. Longer context typically caps at 70–80ch; evidence explanations can reach 95ch.
- **Metric / player score:** emphasized numerical roles. Selected-player names use 24px, falling to 22px on mobile; these stay subordinate to the selected score.

The scale follows implemented roles rather than a fabricated modular ratio. The existing market records retain larger player, price and EV sizing and their semibold weight while inheriting Switzer. In the integrated desk, general heading tracking is -0.025em and the main title is 28px.

**The One Typeface Rule.** Use Switzer for workspace headings, controls, prose and data. Keep numerical comparisons tabular and aligned.

## Layout

The desktop shell is a two-column grid: a pine navigation rail (210px) and a flexible workarea. The rail is sticky, fills the viewport height and contains grouped navigation. A paper topbar (minimum 72px) and the main content share horizontal insets. Main content caps at 1700px including its padding; the usual main inset is 38px, with 38px top and 26px bottom padding. Rankings uses a compact 25px top inset and closer event, verification and table spacing.

The field grid pairs a flexible table with a sticky selected-player panel (285px), separated by 25px. The table panel clips its corners while an inner wrapper handles horizontal scrolling. Ranking rows use the final compact 11px vertical cell padding, with 9px header padding. General data tables use 15px by 12px cells. Standard panels use roughly 20–26px internal space; small controls use 8–15px, with the exact component values recorded above.

Responsive behavior follows the final cascade rather than earlier overwritten declarations:

- **At 1600px and wider:** the selected-player column becomes 310px with a 30px gap; main padding becomes 44px by 48px and the player panel uses 26px. Rankings retains its later compact vertical row override.
- **At 1200px and narrower:** the rail becomes 180px, the main inset becomes 25px, and the player column becomes 250px with an 18px gap. General page headings reduce to 30px; Rankings retains its own role.
- **At 1050px and narrower:** the field becomes one column. Player insight is closed initially, reachable from the selected-player summary at the table, and appears above the field when opened. Its content uses two columns until the mobile breakpoint. Model overview becomes one column; toolbars stack. Research fields become two columns, with the final field spanning the row.
- **At 760px and narrower:** navigation becomes a static top brand and four equal primary tabs, retaining icon and text labels. Secondary rail links and the rail footer are hidden. The topbar minimum height becomes 42px. Rankings uses 16px page gutters; other workspace pages use 20px. Player insight becomes a single column. Analysis panels stack and the four-metric row becomes two columns.
- **Rankings on mobile:** retain the full semantic comparison table with a 530px minimum width inside its horizontal scroller. The final compact cell padding is 9px vertically. The selected-player summary stays reachable above the headers.
- **Event record, benchmark and run-history tables on mobile:** the implemented responsive variant keeps semantic headers visually hidden and turns each record into labeled two-column values beneath a full-width record name. The challenger value stays in the second column of its benchmark row; run promotion status spans both columns. Other simple tables may continue to scroll.
- **Embedded Markets / My card / Season archive:** inherit workspace color and type, but retain their own record breakpoints (1100px, 850px and 560px) and wide aside expansion (1550px). Market rows become player identity plus three labeled values at 560px; saved cards collapse to one column at 850px. Archive record tables reflow at 560px. The outer shell still changes at 760px.

## Elevation & Depth

Depth is mostly tonal: ground, paper, sage tint and one-pixel rules organize the information. Data panels do not lift on hover. The selected segment has a small ambient shadow (`0 1px 3px #142d2410`). The retained More tools menu has the earlier ambient shadow (`0 10px 25px -12px #001a2260`), but its masthead is hidden inside the workspace; this is not a new workspace card token.

**The Ruled Surface Rule.** Separate records with tonal fills and thin rules. Keep data panels flat; the small pressed-segment shadow is a control state, not a card treatment.

Movement communicates state rather than page spectacle. Buttons transition background and border color over 150ms with ease-out; rail items and table-row fills use 160ms ease-out. Selected-player field markers, guides and component bars update over 220ms with `cubic-bezier(.16,1,.3,1)`. There is no authored entrance-animation system. Reduced-motion mode removes transitions and animations and restores automatic scrolling.

## Shapes

Panels, event headers, evidence sections and the navigation selection use modest panel corners. Buttons, fields and search use the smaller control corner; selected segments and research tags use the segment corner. One-pixel borders establish structure. Integrated market records retain their square form and smaller three-pixel controls; the system does not force all records into identical cards.

Circles are functional: chart observations, the event emblem and status marks. The brand uses a small arched flag frame. Icons are Lucide SVG strokes; the factual PGA TOUR identifier is event context. No raster illustration or decorative image layer is part of the workspace.

## Components

### Buttons

Compact, labeled actions. Primary buttons use field green with paper text; the dark variant uses dark action ink on pale green. Secondary buttons use paper, ink and a rule border. Both use the control radius, a minimum height of 40px, a 10px icon gap and the recorded padding. Hover adds tint and an accent border; the primary hover mixes 88% accent with ink. Disabled buttons use half opacity and a not-allowed cursor. Icon-only buttons are framed 36px squares; Rankings refresh becomes 30px on mobile.

Keyboard focus is a two-pixel accent outline offset by four pixels. Search uses the same width with a two-pixel offset around the group. Text links gain an underline on hover and keep their SVG direction cue.

### Chips

Research status is a small amber text-and-SVG tag with a three-pixel corner and its recorded padding. Counts remain attached to a heading or tab, using tint and supporting ink. The navigation selection is a full labeled navigation item, not an isolated status badge.

### Cards / Containers

Paper and a thin rule frame organize field rankings, player insight, charts, model comparisons and run history. Their radius is consistent; internal padding varies with content and breakpoint. Baseline preservation uses a sage banner. Caution notices use amber text and background rather than a floating toast. Empty and loading states keep the same flat surface vocabulary and explicit text.

### Inputs / Fields

Native selects use paper, ink, a rule border, a four-pixel radius and a minimum height of 36px. Search pairs an SVG magnifier with an unframed input inside a single ground-filled bordered group. Placeholder text uses supporting ink; the group carries focus. Research settings use the same field border, radius and palette. Errors and saved status appear as inline text near their controls.

### Navigation

Desktop primary links pair an 18px SVG icon and a text label inside a minimum 44px target; the active item gains a pale fill, darker lettering and a trailing chevron. Hover uses a brighter pine fill and white text. Secondary links sit below a ruled divider. At the mobile breakpoint, four equal icon-and-label tabs replace the rail, with a pale selected tab and a bottom rule. Season access remains in the topbar.

### Segmented Controls

A tinted, bordered wrapper contains native buttons. Selected state uses paper, ink and the small ambient control shadow; unselected labels use supporting ink. Selection is exposed with `aria-pressed`. These switch view context without changing the surrounding shell.

### Ranked Field and Player Insight

A thin-rule table aligns rank, player identity and tabular metrics. Hover changes ground; selection uses sage tint. Top-three rank numbers and composite scores use accent. The player name is a real button, and the visible selected summary can reopen details on compact screens. Selecting a player updates the common-scale distribution and the component bars; closing compact detail restores focus to the selection control. Research projections keep their own units and version context.

### Evidence Charts and Mobile Records

SVG charts use rule-colored grids, green data marks, a dashed zero line or guide where implemented, and visible value/date readouts. The cumulative paper-return chart has a keyboard-accessible range control; the selected event stays identified above it. Calibration observations use circle area to show sample size and a shared diagonal comparison. Model cohorts appear as three adjacent chronological segments, using related greens. On small screens, only the explicitly responsive tables become labeled records, preserving the metric-to-model relationship.

## Do's and Don'ts

### Do:

- **Do** use the paired light and dark semantic palettes and the visible pale navigation selection.
- **Do** keep units, source age, model identity and evidence limitations next to the affected values.
- **Do** preserve stable player identity and a shared comparison scale when selection changes.
- **Do** retain horizontal comparison for the Rankings table and use labeled mobile records only for the tables that implement that pattern.
- **Do** keep color accompanied by text, marker shape or selection structure.
- **Do** retain semantic table headers when mobile presentation visually hides them.

### Don't:

- **Don't** present recorded model selections or paper returns as verified placed bets or profit.
- **Don't** erase missing data, uncertain provenance or research status with a success treatment.
- **Don't** extend the retained terminal or standalone shared-reader styling into the new workspace by default.
- **Don't** add decorative kickers, glyph icons, hard offset shadows or system-font display headings.
- **Don't** turn the observed 9–10px supporting annotations into a reusable primary-text standard.

Not canonized or repaired: retained terminal routes and the standalone shared-card reader remain outside this workspace world; observed 9–10px supporting and chart annotations are not promoted to primary-text tokens. No new craft-floor defect was found in the sampled workspace sources. This documentation pass checked source and final captures; it did not re-run the detector, tests, live-data verification or deployment. No approved raster comp or QUALITY BAR card exists for this code-led build, and no shipping raster assets were introduced.
