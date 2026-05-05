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

## “Analytics Blog” — **`/blog` is the main archive**

**[`https://datagolf.com/blog`](https://datagolf.com/blog)** is the **single listing** you want for Analytics-style posts: tag filters, “load more,” and the same root-slug URLs as the sidebar (verified 2026-05-05: e.g. `where-to-miss-tpc-sawgrass`, `shot-level-course-fit`, `how-sharp-are-bookmakers-part-2` all appear in `/blog` HTML). Treat **`/blog` as the primary crawl for Family B** on `datagolf.com`—not `/blog-home/`.

From the **Analytics Blog** article template (verified on `https://datagolf.com/how-sharp-are-bookmakers-part-2`):

1. **“More from the Analytics Blog”** — built in-page from a JavaScript array `var recents = [ ... ]` (titles, paths, one-line descriptions). It is a **curated short list** for the sidebar only, not the full catalog. **Do not rely on `recents` alone**—use **`/blog`** for completeness.

2. **“Archive →”** in that sidebar — links to **`/blog`** (same archive as above).

3. **Site nav “Analytics Blog”** (top menu) — still points to **`/blog-home/`**, a **marketing-style landing page** (articles + tools + archives mixed). Optional extra link harvest after **`/blog`** is exhausted; if you scrape it, apply the same **tool/archive denylist** as before.

4. **Related streams** (same sidebar block): **Model Talk** → `/model-talk`; **Data Visualization Blog** → `/viz-blog` (these are **not** fully duplicated on `/blog`—enumerate those hubs separately).

5. **Commented `popular` array** in the same template still contains useful **seed URLs** (methodology, a few `datagolfblogs.ca` links, etc.)—worth grepping from any Analytics page that includes it.

## Practical harvest order (families A–C)

| Step | Source | Notes |
|------|--------|--------|
| A | `https://datagolfblogs.ca/old-blogs-directory/` | Directory of legacy posts |
| B | **`https://datagolf.com/blog`** | **Primary:** all tags + “load more” until empty — this is the consolidated Analytics (and related) feed |
| C | `https://datagolf.com/blog-home/` | **Optional:** extra links after `/blog`; **filter** tools/archives |
| C | `/model-talk`, `/viz-blog` | Series indexes (parallel to `/blog`) |
| C | `var recents` / `var popular` on sample Analytics pages | Optional seeds / cross-check only |

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

## Extraction feasibility (for model-relevant notes)

- **URL list (L0):** Achievable with the waves above; `/blog` is the primary Analytics archive.
- **Key claims (L1):** Article **prose is present in server HTML** for representative Analytics posts (spot-check 2026-05-05: `curl` on `/where-to-miss-tpc-sawgrass` returned ~188kB HTML containing obvious article tokens). Automated or LLM summarization still needs a **QA gate** (two-pass review + spot sampling) before tying rows to code changes—see project plan “accuracy contract” and optional CSV columns `extraction_method`, `superseded_by`, `artifacts_note` in [datagolf_topic_taxonomy.md](datagolf_topic_taxonomy.md).
