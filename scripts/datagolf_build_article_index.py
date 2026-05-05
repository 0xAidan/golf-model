#!/usr/bin/env python3
"""
Rebuild docs/research/datagolf_article_index.csv from enumeration sources (Wave A, C, research docs).

Run from repo root:
  python scripts/datagolf_build_article_index.py

Requires network for fetches. Rate-limited; idempotent merge by normalized URL.
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "research" / "datagolf_article_index.csv"
RESEARCH_GLOB = ROOT / "docs" / "research" / "*.md"

HEADER = [
    "url",
    "title",
    "published_date",
    "source_family",
    "source_domain",
    "discovery_source",
    "content_tier",
    "implementation_lane",
    "series",
    "dg_tags",
    "model_dimensions",
    "summary_bullets",
    "proposed_change",
    "code_touchpoints",
    "verify_with",
    "status",
    "extraction_method",
    "superseded_by",
    "artifacts_note",
]

TOOL_PATH_PREFIXES = (
    "/betting-tool-",
    "/fantasy-projections",
    "/tournament-props",
    "-archive",
    "/live-model",
    "/dfs-points-archive",
    "/raw-data-archive",
    "/predictions-archive",
    "/outright-odds-archive",
    "/matchup-odds-archive",
    "/player-profiles",
    "/skill-ratings",
    "/course-fit-tool",
    "/course-history-tool",
    "/custom-simulation",
    "/pressure-tool",
    "/true-sg-query",
    "/true-strokes-gained-am",
    "/field-updates",
    "/tournaments",
    "/course-table",
    "/datagolf-am-rankings",
    "/datagolf-rankings",
    "/performance-table",
    "/trend-table",
    "/fedex-cup",
    "/field-strength-table",
    "/futures-pricing",
    "/historic-event-data",
    "/historical-tournament-stats",
    "/major-fields",
    "/tour-standings",
    "/tournament-summaries",
    "/presidents-cup",
    "/ryder-cup",
    "/korn-ferry-finals",
    "/live-blog",
    "/live-strokes-gained",
    "/my-bets",
    "/my-model",
    "/api-access",
    "/contact",
    "/privacy-policy",
    "/terms-and-conditions",
    "/login",
    "/player-projections",
)

EXACT_DENY = frozenset(
    {
        "/blog",
        "/blog-home",
        "/viz-blog",
        "/model-talk",
        "/approach-skill",
    }
)


def curl(url: str) -> str:
    r = subprocess.run(
        ["curl", "-sS", "-L", "-m", "35", "-A", "golf-model-research-index/1.0", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        print(f"warn: curl failed {url} rc={r.returncode}", file=sys.stderr)
        return ""
    return r.stdout or ""


def norm_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    u = u.replace("http://datagolfblogs.ca", "https://datagolfblogs.ca")
    u = u.replace("http://www.datagolf.com", "https://datagolf.com")
    u = u.replace("https://www.datagolf.com", "https://datagolf.com")
    p = urlparse(u)
    if not p.scheme or not p.netloc:
        return ""
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse(("https", p.netloc.lower(), path, "", "", ""))


def key_url(u: str) -> str:
    k = norm_url(u)
    return k.lower()


def slug_title(path: str) -> str:
    slug = path.strip("/").split("/")[-1].replace("-", " ")
    return slug[:1].upper() + slug[1:] if slug else ""


def classify_series(url: str) -> str:
    if "datagolfblogs.ca" in url:
        return "legacy_blog"
    if "/model-talk/" in url:
        return "model_talk"
    if "/viz-blog/" in url:
        return "viz_blog"
    if url.rstrip("/") in {
        "https://datagolf.com/frequently-asked-questions",
        "https://datagolf.com/raw-data-notes",
        "https://datagolf.com/api-access",
    }:
        return "standalone"
    return "analytics_blog"


def classify_family(url: str) -> tuple[str, str]:
    if "datagolfblogs.ca" in url:
        return "A", "datagolfblogs.ca"
    return "C", "datagolf.com"


def is_article_path(host: str, path: str) -> bool:
    if host != "datagolf.com":
        return True
    if path in EXACT_DENY:
        return False
    if any(path.startswith(p) or p in path for p in TOOL_PATH_PREFIXES):
        return False
    if path.count("/") > 2:
        return False
    return len(path) > 2


def is_valid_datagolfblogs_post(url: str) -> bool:
    p = urlparse(url)
    if "datagolfblogs.ca" not in (p.netloc or "").lower():
        return False
    parts = [x for x in p.path.split("/") if x]
    if not parts:
        return False
    if parts[0] in {"author", "tag", "category", "page", "feed", "wp-content", "wp-includes"}:
        return False
    return True


def extract_old_blogs_directory(html: str) -> set[str]:
    out: set[str] = set()
    for m in re.finditer(r'href="(https?://datagolfblogs\.ca[^"#]+)"', html, re.I):
        out.add(norm_url(m.group(1)))
    for m in re.finditer(r"href='(https?://datagolfblogs\.ca[^'#]+)'", html, re.I):
        out.add(norm_url(m.group(1)))
    return {
        u
        for u in out
        if u
        and "old-blogs-directory" not in u
        and "/wp-" not in u
        and is_valid_datagolfblogs_post(u)
    }


def extract_model_talk(html: str) -> set[str]:
    out = set()
    for m in re.finditer(r'href="(/model-talk/[a-z0-9\-]+)"', html, re.I):
        out.add(norm_url("https://datagolf.com" + m.group(1)))
    return out


def extract_blog_home_paths(html: str) -> set[str]:
    out: set[str] = set()
    for m in re.finditer(r'href="(/[a-z0-9][a-z0-9\-/]*)"', html, re.I):
        path = m.group(1).split("?")[0].rstrip("/") or "/"
        if not path.startswith("/") or path == "/":
            continue
        if path.count("/") != 1:
            continue
        if not is_article_path("datagolf.com", path):
            continue
        out.add(norm_url("https://datagolf.com" + path))
    return out


def extract_viz_blog(html: str) -> set[str]:
    out = set()
    for m in re.finditer(r'href="(/viz-blog/[a-z0-9\-]+)"', html, re.I):
        out.add(norm_url("https://datagolf.com" + m.group(1)))
    return out


def urls_from_research_markdown() -> set[str]:
    out: set[str] = set()
    for md in sorted(ROOT.glob("docs/research/*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(
            r"https?://(?:www\.)?(datagolf\.com|datagolfblogs\.ca)[a-zA-Z0-9\-._~:/?#%[\]@!$&'()*+,;=]*",
            text,
        ):
            raw = m.group(0).rstrip(").,;]")
            nu = norm_url(raw)
            if not nu:
                continue
            if "datagolfblogs.ca" in nu and not is_valid_datagolfblogs_post(nu):
                continue
            if "datagolf.com" in nu:
                path = urlparse(nu).path
                if path in EXACT_DENY or not is_article_path("datagolf.com", path.split("?")[0]):
                    continue
            out.add(nu)
    return out


def tier1_urls() -> set[str]:
    return {
        norm_url("https://datagolf.com/predictive-model-methodology/"),
        norm_url("https://datagolf.com/frequently-asked-questions"),
        norm_url("https://datagolf.com/raw-data-notes"),
        norm_url("https://datagolf.com/comparing-pro-tours/"),
        norm_url("https://datagolf.com/api-access"),
    }


def load_existing_rows() -> dict[str, dict[str, str]]:
    if not OUT.is_file():
        return {}
    by_key: dict[str, dict[str, str]] = {}
    with OUT.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            u = row.get("url") or ""
            k = key_url(u)
            if not k:
                continue
            full = {h: row.get(h, "") for h in HEADER}
            by_key[k] = full
    return by_key


def blank_row(url: str, discovery: str, content_tier: str) -> dict[str, str]:
    fam, dom = classify_family(url)
    row = {h: "" for h in HEADER}
    row["url"] = url
    row["title"] = slug_title(urlparse(url).path)
    row["source_family"] = fam
    row["source_domain"] = dom
    row["discovery_source"] = discovery
    row["content_tier"] = content_tier
    row["series"] = classify_series(url)
    row["status"] = "pending_read"
    row["extraction_method"] = "curl_html"
    return row


def main() -> int:
    by_key = load_existing_rows()
    print(f"loaded {len(by_key)} existing rows", file=sys.stderr)

    # Wave A
    print("fetch old-blogs-directory...", file=sys.stderr)
    html_a = curl("https://datagolfblogs.ca/old-blogs-directory/")
    time.sleep(0.5)
    for u in extract_old_blogs_directory(html_a):
        k = key_url(u)
        if k not in by_key:
            by_key[k] = blank_row(u, "wave_a_old_blogs_directory", "directory_listed")

    # Model talk index
    print("fetch model-talk...", file=sys.stderr)
    html_mt = curl("https://datagolf.com/model-talk")
    time.sleep(0.5)
    for u in extract_model_talk(html_mt):
        k = key_url(u)
        if k not in by_key:
            by_key[k] = blank_row(u, "wave_c_model_talk_index", "model_talk")

    # Viz hub
    print("fetch viz-blog...", file=sys.stderr)
    html_v = curl("https://datagolf.com/viz-blog")
    time.sleep(0.5)
    for u in extract_viz_blog(html_v):
        k = key_url(u)
        if k not in by_key:
            by_key[k] = blank_row(u, "wave_c_viz_blog_index", "viz_or_betting")

    # Blog-home article-like paths
    print("fetch blog-home...", file=sys.stderr)
    html_bh = curl("https://datagolf.com/blog-home/")
    time.sleep(0.5)
    for u in extract_blog_home_paths(html_bh):
        k = key_url(u)
        if k not in by_key:
            by_key[k] = blank_row(u, "wave_c_blog_home_crawl", "blog_tagged")

    # Tier 1 hubs
    for u in tier1_urls():
        k = key_url(u)
        if k not in by_key:
            by_key[k] = blank_row(u, "wave_c_tier1_seed", "canonical_hub")
        else:
            if not by_key[k].get("content_tier"):
                by_key[k]["content_tier"] = "canonical_hub"

    # Research markdown URLs
    for u in urls_from_research_markdown():
        k = key_url(u)
        if not k:
            continue
        if k not in by_key:
            by_key[k] = blank_row(u, "research_doc_scan", "blog_tagged")

    # Ensure new columns exist on merged old rows
    for row in by_key.values():
        for h in HEADER:
            row.setdefault(h, "")

    def row_keep(url: str) -> bool:
        u = norm_url(url)
        if not u:
            return False
        if "datagolfblogs.ca" in u:
            return is_valid_datagolfblogs_post(u)
        path = urlparse(u).path.split("?")[0]
        return is_article_path("datagolf.com", path)

    by_key = {k: v for k, v in by_key.items() if row_keep(v.get("url", ""))}

    rows = sorted(by_key.values(), key=lambda r: (r["source_family"], r["url"].lower()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} rows to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
