# `datagolf_article_index.csv`

## Regenerate URL list (Wave A + C + research doc links)

From repo root (network required):

```bash
python3 scripts/datagolf_build_article_index.py
```

Sources merged:

- [datagolfblogs.ca/old-blogs-directory](https://datagolfblogs.ca/old-blogs-directory/) (Wave A)
- [datagolf.com/model-talk](https://datagolf.com/model-talk) index, [viz-blog](https://datagolf.com/viz-blog) hub, [blog-home](https://datagolf.com/blog-home/) article-like paths (Wave C)
- Tier 1 hub URLs (methodology, FAQ, raw-data-notes, comparing-pro-tours, api-access)
- `https://datagolf.com` / `datagolfblogs.ca` URLs found in `docs/research/*.md`

Manual seeds (sidebar `recents` / `popular` from a sample Analytics page) are preserved if already present with `discovery_source` `page_sidebar_*`.

### Gaps (follow-up)

- **`/blog` “load more”** is mostly JS-driven; this script uses **`/blog-home/`** link harvest plus research-doc URLs instead of full per-tag pagination. Re-run after major site changes or extend the script if you capture the XHR the blog uses.
- **Model Talk** rows come from the **index page** only (10 posts visible in static HTML today); older posts may need manual rows or a deeper crawl.

## Next (human / QA phase)

Fill `summary_bullets`, `proposed_change`, `verify_with`; set `superseded_by` when Model Talk overrides an older post; use `artifacts_note` for charts. See [datagolf_topic_taxonomy.md](datagolf_topic_taxonomy.md) and [datagolf_enumeration.md](datagolf_enumeration.md).
