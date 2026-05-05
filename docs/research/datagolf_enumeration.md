# Data Golf — how to enumerate public articles (verified)

**Checked:** 2026-05-05 against live responses from `datagolf.com`.

## Sitemap

These paths all returned **HTTP 404** (HTML app shell, not XML):

- `https://datagolf.com/robots.txt`
- `https://datagolf.com/sitemap.xml`
- `https://datagolf.com/sitemap_index.xml`
- `https://datagolf.com/wp-sitemap.xml`
- `https://www.datagolf.com/sitemap.xml`

So there is **no** standard sitemap at the usual locations for automated URL harvest. Enumeration must use **on-site navigation and HTML parsing**.

## “Analytics Blog” vs `/blog` vs `/blog-home/`

From the **Analytics Blog** article template (verified on `https://datagolf.com/how-sharp-are-bookmakers-part-2`):

1. **“More from the Analytics Blog”** — built in-page from a JavaScript array `var recents = [ ... ]` (titles, paths, one-line descriptions). It is a **curated short list**, not the full archive. The same pattern appears on other Analytics posts; **recents may differ or be updated** over time—treat as hints, not a complete index.

2. **“Archive →”** in that sidebar — implemented as a link to **`/blog`** (tagged blog listing with “load more”), not a separate `/analytics-archive` URL.

3. **Site nav “Analytics Blog”** (top menu) — points to **`/blog-home/`**, which is a **landing page** with many internal links (mix of **articles**, **tools**, **archives**, etc.). A single scrape of `/blog-home/` is **not** article-only; filter with a denylist (e.g. `betting-tool-*`, `fantasy-projections*`, `*-archive`, `player-profiles`).

4. **Related streams** (same sidebar block): **Model Talk** → `/model-talk`; **Data Visualization Blog** → `/viz-blog`.

5. **Commented `popular` array** in the same template still contains useful **seed URLs** (methodology, a few `datagolfblogs.ca` links, etc.)—worth grepping from any Analytics page that includes it.

## Practical harvest order (families A–C)

| Step | Source | Notes |
|------|--------|--------|
| A | `https://datagolfblogs.ca/old-blogs-directory/` | Directory of legacy posts |
| B | `https://datagolf.com/blog` | All tags + load more |
| C | `https://datagolf.com/blog-home/` | Extract `href="/..."`; **filter** tools/archives |
| C | Root-slug Analytics posts | e.g. `/where-to-miss-tpc-sawgrass`; grep `var recents` / `var popular` on samples |
| C | `/model-talk`, `/viz-blog` | Series indexes |

## `recents` excerpt (HSB Part II page, for regression / testing)

Captured from page source 2026-05-05:

- `/shot-level-course-fit` — Shot-level course fit at Augusta  
- `/what-makes-a-golf-tournament-entertaining` — What makes golf entertaining?  
- `/how-sharp-are-bookmakers-part-2` — How sharp are bookmakers? Part II  
- `/what-makes-justin-thomas-great` — What makes Justin Thomas a great iron player?  
- `/who-plays-well-at-the-open` — Who plays well at The Open?  
- `/where-to-miss-tpc-sawgrass` — Where to miss at TPC Sawgrass  
- `/who-benefits-from-wide-fairways` — Who benefits from wide fairways?  
- `/data-driven-history-augusta-national` — Data-driven history of Augusta  
- `/performance-and-pressure` — Sleeping on the lead  

`popular` (commented in sidebar; still in source): `/predictive-model-methodology/`, `http://datagolfblogs.ca/does-a-players-course-history-predict-performance/`, `/comparing-pro-tours/`, `http://datagolfblogs.ca/the-luck-of-the-draw/`, `/important-holes-at-augusta/`, `/whats-the-strongest-field-in-professional-golf/`.
