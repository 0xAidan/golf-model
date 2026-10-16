---
name: Golf Model — Matchup Desk
description: The shipped team-golf broadcast system for Markets, My card and Results.
colors:
  ground: '#f4f6f3'
  paper: '#fff'
  ink: '#142d28'
  muted: '#5c6e65'
  rule: '#d9e1d9'
  tint: '#eaf0e8'
  accent: '#155a42'
  positive: '#236b41'
  warning: '#795117'
  warning-bg: '#fff4df'
  mast: '#133e32'
  gold: '#d8dc82'
  dark-ground: '#101e1a'
  dark-paper: '#172b23'
  dark-ink: '#e6ede4'
  dark-muted: '#adbcaf'
  dark-rule: '#34483b'
  dark-tint: '#20362b'
  dark-accent: '#b4d58c'
  dark-positive: '#b4d58c'
  dark-warning: '#edc47b'
  dark-warning-bg: '#342c1c'
  dark-mast: '#10382c'
  mast-text: '#eff5ec'
  mast-link: '#c5d7c7'
  mast-tools: '#d5e3d3'
  card-count-bg: '#2c5343'
  card-count-text: '#eaf2e6'
typography:
  display:
    fontFamily: Barlow Condensed, Arial, sans-serif
    fontSize: 44px
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: -0.015em
  display-compact:
    fontFamily: Barlow Condensed, Arial, sans-serif
    fontSize: 39px
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: -0.015em
  display-mobile:
    fontFamily: Barlow Condensed, Arial, sans-serif
    fontSize: 37px
    fontWeight: 600
    lineHeight: 1.03
    letterSpacing: -0.015em
  headline:
    fontFamily: Barlow Condensed, Arial, sans-serif
    fontSize: 29px
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: -0.015em
  title:
    fontFamily: Barlow Condensed, Arial, sans-serif
    fontSize: 25px
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: -0.015em
  player:
    fontFamily: Barlow, Arial, sans-serif
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.2
  price:
    fontFamily: Barlow, Arial, sans-serif
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.25
  metric:
    fontFamily: Barlow, Arial, sans-serif
    fontSize: 17px
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: Barlow, Arial, sans-serif
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.5
  support:
    fontFamily: Barlow, Arial, sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  control:
    fontFamily: Barlow, Arial, sans-serif
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.25
  label:
    fontFamily: Barlow, Arial, sans-serif
    fontSize: 11px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0.05em
rounded:
  square: '0'
  focus: 2px
  control: 3px
  segmented: 4px
  marker: 50%
spacing:
  compact: 8px
  control-gap: 12px
  row: 16px
  mobile-gutter: 20px
  section: 24px
  desktop-gutter: 32px
  page-top: 40px
  column-gap: 48px
  page-bottom: 64px
components:
  button-primary:
    backgroundColor: '{colors.accent}'
    textColor: '{colors.paper}'
    typography: '{typography.control}'
    rounded: '{rounded.control}'
    padding: 10px 15px
  button-primary-hover:
    backgroundColor: color-mix(in srgb, var(--md-accent) 90%, var(--md-ink))
    textColor: '{colors.paper}'
  button-secondary:
    backgroundColor: '{colors.paper}'
    textColor: '{colors.ink}'
    typography: '{typography.control}'
    rounded: '{rounded.control}'
    padding: 10px 15px
  button-secondary-hover:
    backgroundColor: '{colors.tint}'
  button-save:
    backgroundColor: '{colors.paper}'
    textColor: '{colors.ink}'
    rounded: '{rounded.control}'
    width: 32px
    height: 32px
  button-save-selected:
    backgroundColor: '{colors.tint}'
    textColor: '{colors.accent}'
  input-search:
    backgroundColor: '{colors.paper}'
    textColor: '{colors.ink}'
    rounded: '{rounded.control}'
    height: 38px
    padding: 0 11px
  input-select:
    backgroundColor: '{colors.paper}'
    textColor: '{colors.ink}'
    rounded: '{rounded.control}'
    height: 40px
    padding: 8px 5px
  nav-primary:
    backgroundColor: '{colors.mast}'
    textColor: '{colors.mast-link}'
  chip-count:
    backgroundColor: '{colors.tint}'
    textColor: '{colors.muted}'
    rounded: '{rounded.focus}'
    padding: 0 5px
  segmented-control:
    rounded: '{rounded.segmented}'
    padding: 3px
  segmented-selected:
    backgroundColor: '{colors.tint}'
    textColor: '{colors.ink}'
    rounded: '{rounded.focus}'
    padding: 6px 12px
  saved-card:
    backgroundColor: '{colors.paper}'
    textColor: '{colors.ink}'
    rounded: '{rounded.square}'
    padding: 20px 22px
  matchup-detail:
    backgroundColor: '{colors.tint}'
    textColor: '{colors.ink}'
    padding: 24px
  evidence-notice:
    backgroundColor: '{colors.warning-bg}'
    textColor: '{colors.warning}'
    rounded: '{rounded.square}'
    padding: 18px 22px
---

# Design System: Golf Model — Matchup Desk

## Overview

**Creative North Star: "The Team-Golf Broadcast Desk"**

The desk takes its visual character from international team-golf broadcast graphics: an evergreen masthead, cool pale surfaces, condensed headings and aligned numerical comparisons. It is compact and factual, with visible rules separating records and a small amount of yellow-green used in the masthead and browser selection.

This system applies to the implemented Markets (`/`), My card (`/card`) and Results (`/evidence`) surfaces. The dark theme translates the same structure into green-black ground and pale foliage accents. Retained research and operations routes use their incumbent styles; their terminal tokens have not been redesigned or absorbed into this system.

**Key Characteristics:**

- Evergreen masthead with a yellow-green active navigation rule.
- Self-hosted Barlow Condensed headings and Barlow body text with tabular numerals.
- Flat, ruled records and minimally rounded controls.
- A shared probability scale distinguished by a round model marker and a vertical bookmaker marker.
- Visible labels and text explanations for saved, stale, unavailable and research-only states.

Extracted from `frontend/src/features/matchup-desk/matchup-desk.css`, `matchup-desk.tsx`, `market-rows.ts` and `frontend/src/App.tsx`; product constraints come from `PRODUCT.md` and world context from `.impeccable/surfaces/matchup-desk.md`. The reviewed desktop, mobile, dark and fixture captures corroborate the structure. Fixture numbers are examples, not live data. Frontmatter records the actual reused values; CSS custom properties are scoped to the desk, with dark overrides under `.dark`.

## Colors

A restrained evergreen palette combines cool paper, green-tinted rules and a yellow-green masthead accent. The frontmatter is the normative value table. The sidecar’s eight-step OKLCH ramps are synthesized swatch previews, not additional shipped palette tokens.

### Primary

- **Evergreen accent** (`accent`, `dark-accent`): selected market tabs, interactive links, focus outlines, comparison markers and the primary action.
- **Broadcast evergreen** (`mast`, `dark-mast`): the full-width masthead in each theme.
- **Positive green** (`positive`, `dark-positive`): positive model EV on the market board and saved card. Dark positive shares the accent value.

### Secondary

- **Tournament gold** (`gold`): the second word of the brand, active masthead navigation underline and selection background. It does not change between themes.
- **Amber caution** (`warning`, `warning-bg`, and their dark counterparts): stale or unavailable data, incomplete evidence and limited-sample explanations. Warning panels use a border mixed from warning color at 23% and transparency.

### Neutral

- **Cool ground / paper** (`ground`, `paper`, and dark counterparts): page ground and record or control surfaces.
- **Ink / muted ink** (`ink`, `muted`, and dark counterparts): primary content and supporting labels.
- **Rule / tint** (`rule`, `tint`, and dark counterparts): separators, table headers, selected small controls and expanded records.
- **Masthead text** (`mast-text`, `mast-link`, `mast-tools`): the fixed pale masthead palette. Active and hovered navigation uses paper-white; the masthead itself stays dark in both themes.
- **Saved-count palette** (`card-count-bg`, `card-count-text`): the small count beside My card.

**The Paired State Rule.** Use color with text, shape or an underline: a selected tab has an underline, a saved quote has a check, and a warning has an explanation.

## Typography

**Display Font:** Barlow Condensed, with Arial and sans-serif fallback.
**Body Font:** Barlow, with Arial and sans-serif fallback.
**Label/Mono Font:** Barlow; the desk does not introduce a separate monospace family.

The self-hosted files are `Barlow-Regular.ttf`, `Barlow-SemiBold.ttf` and `BarlowCondensed-SemiBold.ttf`, loaded with `font-display: swap`. The semibold files are declared for the 600–900 range; they are not separate bold assets. Condensed headings give short titles a broadcast character while the wider body face keeps records and controls legible.

### Hierarchy

- **Display:** page heading, reduced through the `display-compact` and `display-mobile` roles at the recorded breakpoints.
- **Headline:** evidence aside heading. Other implemented condensed headings include empty-board (31px/1.15), saved player (27px/1.1), section heading (26px), and supporting subsection (22px/1.2).
- **Title:** event heading; it becomes 23px at the compact desktop breakpoint and 24px/1.15 on mobile.
- **Player / price / metric:** stronger Barlow data roles. Mobile price and metric values use 18px; saved-card values use 19px.
- **Body / support:** normal prose. Supporting descriptions commonly use 13px; secondary metadata uses 10–12px and is not the size model for primary content.
- **Label:** uppercase table column labels with tracking. Mobile value labels use 10px and 0.03em tracking; they remain attached to their data.

There is no fabricated modular ratio: this is a role-specific pixel ramp. The desk sets `font-variant-numeric: tabular-nums` globally. Page descriptions cap at 70ch; record explanations at 72ch; compact explanatory copy generally at 48–49ch.

**The Two Voices Rule.** Use Barlow Condensed for headings and Barlow for controls, prose and data; keep numerical columns tabular and aligned.

## Layout

The shell is full width with a centered main area (maximum 1504px including 32px desktop gutters). Desktop main padding is 40px at the top and 64px below; masthead, event bar and footer align to a 1440px content region with a minimum 32px side inset. Single-page card and evidence sections cap at 1180px inside that shell.

The market board pairs a flexible main column with a 256px evidence aside and a 48px gap. Rows align player, book price, model win, EV and save action in the grid `minmax(160px, 1fr) 125px 90px 90px 36px`, with 12px gaps. Records have a 90px minimum height and 15px by 16px padding. The saved-card collection uses two equal columns with a 24px gap.

The reusable spacing is an observed set, not a forced single increment: compact control gaps, 12–16px record spacing, 20–24px internal or mobile spacing, and 32–64px shell spacing. Preserve the component-specific values recorded above.

Responsive behavior follows the source cascade:

- **At 1550px and wider:** the evidence aside becomes 290px with a 64px gap.
- **At 1100px and narrower:** the aside becomes 210px with a 28px gap; rows tighten to `minmax(130px, 1fr) 96px 72px 72px 32px`; page headings use the compact role.
- **At 850px and narrower:** gutters become 24px; the evidence aside moves below the board; saved cards become one column. Market records in the evidence aside use three columns. The final stylesheet override makes the aside a block, superseding the earlier two-column aside rule.
- **At 560px and narrower:** gutters become 20px, the masthead navigation wraps below the brand, event controls form a second row, and search occupies a full filter row. Horizontally scrollable market tabs remain visible. Matchups become two-row records: player and save above, three labeled numerical values below. The evidence aside remains below the board.
- **Mobile Results:** the actual table becomes a series of bordered records with two columns of labeled values; semantic headers remain visually hidden. The desktop table minimum width is 840px, while mobile removes that minimum. Calibration and explanatory content stack into a single column. SVG plot labels grow from 11 to 17 user units at the mobile breakpoint.

## Elevation & Depth

The desk is flat at rest. Paper and tint establish layers, and one-pixel rules establish boundaries. The More tools menu alone floats over content with an ambient shadow (`0 10px 25px -12px #001a2260`); it is not a repeated card treatment. Focus uses an outline rather than a shadow.

**The Ruled Surface Rule.** Use tonal fills and thin rules to separate records. The More tools menu is the only desk surface with an ambient shadow.

State changes are immediate: the desk defines no entrance animation or transition timing vocabulary. The expanded-row chevron rotates 180 degrees without an authored transition. Reduced-motion mode explicitly removes animations and transitions and restores automatic scrolling.

## Shapes

Records and evidence panels have square corners. Most small controls have the `control` radius; selected segments and count tags use `focus`; the segmented-control wrapper uses `segmented`. This modest radius system does not turn records into large rounded tiles. One-pixel borders use the semantic rule color.

Round shapes are functional: the model marker and chart observations use circles. The bookmaker marker is a narrow vertical stroke. Icons are Lucide SVG strokes, commonly 14–18px in controls and larger in empty states, with a flag in the brand. The PGA TOUR label is factual event identification beside the title, not an invented eyebrow.

## Components

### Buttons

Compact and lightly framed. The secondary button uses paper, ink and a rule border; hover fills it with tint. The primary variant uses accent with paper text; hover mixes 90% accent with ink and retains paper text. Both use the `control` type role and the recorded padding/radius. Text links use accent and gain an underline on hover. Global disabled buttons use opacity 0.5 and a default cursor.

The save button is square (32px) with a drawn plus. Hover and saved state use tint with accent border and icon; saved state changes the icon to a check. Ineligible unsaved records disable saving. Refresh is a related 30px by 32px bordered control.

Keyboard focus is a two-pixel accent outline offset by four pixels, with no shadow and a two-pixel radius. The search group uses a two-pixel outline offset by two pixels instead, and suppresses the inner field outline.

### Chips

Small counts belong to their parent navigation or market tab. Market counts use tint, muted text and a two-pixel radius, with 11px text on an 18px line. The masthead count uses its dedicated dark-green palette, a three-pixel radius, and 12px text on a 20px line. These are counts, not a general status-pill vocabulary.

### Cards / Containers

Saved selections use square paper containers with a rule border and no shadow. The default internal spacing is recorded in `saved-card`; mobile uses 17px. Removal sits at the top right. The player identity is prominent, followed by the preserved price, probability, EV, event and source timestamp. On mobile the identity spans the width above three values.

Empty states use a centered SVG, condensed heading, short explanation and a useful action. Loading, error, unavailable and no-lines states have distinct copy. Do not borrow their centered composition for populated records.

### Inputs / Fields

Search is a paper field with a rule border, muted SVG and explicit accessible label. Its input is 38px high; the enclosing border adds to its rendered height. Selects are native, bordered paper controls with a 40px height; on mobile they become 35px high. Placeholders use the same muted color at full opacity.

The event mode control has a bordered four-pixel wrapper and two smaller segments. `aria-pressed` drives tint, ink and semibold selected text. Market filters retain their visible or accessible names as space contracts.

### Navigation

The evergreen masthead uses Barlow semibold links and a three-pixel gold active underline. Hover raises link text to white. The active state is an underline rather than a filled tab. The mobile masthead wraps the same primary links into a second line. More tools opens a bordered paper menu with tint hover and the single floating shadow.

Market tabs use a three-pixel accent underline, accent text for the selected tab, and muted text otherwise. Counts stay adjacent. They scroll horizontally on narrow screens without hiding market families behind a menu.

### Probability Comparison

An expanded matchup places both supplied probabilities on one horizontal 0–100% rule (4px high). The model is a 12px round accent marker with a two-pixel paper border; the bookmaker break-even is a 2px by 16px ink stroke. Labels repeat those shapes. The component is omitted unless both source probabilities are present; no invented complementary probability is drawn.

### Evidence and Results

Warnings use the amber pairing, thin tinted border and SVG information mark. Market evidence rows use separators with readable sample limits. Result values are right-aligned in the desktop table and explicitly labeled after mobile reflow. Missing probability, EV and price values use an em dash rather than zero.

The calibration plot uses rule-colored grid lines, a muted dashed reference (4 5), and accent points at 0.85 opacity with paper strokes. Points retain their source-derived sizes; larger points represent more results. Dark mode changes semantic colors without changing the chart grammar.

## Do's and Don'ts

### Do:

- **Do** keep the light and dark semantic palettes paired; the gold masthead accent stays the same in both themes.
- **Do** preserve text labels and distinct marker shapes alongside state color.
- **Do** use the same tabular number treatment for prices, probabilities, EV and evidence tables.
- **Do** reflow a record into labeled values on narrow screens while retaining its identity and source context.
- **Do** show the probability comparison only when both supplied probabilities exist; missing values remain explicit.
- **Do** keep actual table headers and market labels; they identify data and are not decorative heading labels.

### Don't:

- **Don't** extend this desk specification to retained legacy routes without an explicit design change.
- **Don't** turn saved research selections or recorded model results into visual claims of placed bets or verified profit.
- **Don't** replace the round model marker and vertical bookmaker marker with a filled proportion that implies an opponent complement.
- **Don't** add decorative kickers, hard offset shadows, glyph icons or system-font display headings.
- **Don't** prohibit cards globally: saved selections and mobile result records are flat bordered containers in the shipped system.

Not canonized or repaired: retained legacy terminal styling remains outside this desk scope; 10px supporting metadata is documented as an observation, not a primary-text standard. No craft-floor defect was identified in the sampled desk sources.
