"""
Intel Harvester

Background worker that scrapes external data sources for player-related
intelligence, processes it with AI, and stores actionable signals.

Sources:
  1. Google News RSS (free, no API key needed)
  2. Reddit (r/golf, r/sportsbook — public JSON API)
  3. Golf RSS feeds (Golf Digest, GolfWRX, PGA Tour News)

Each source returns raw items which are:
  1. Matched to players in the current field
  2. Scored for relevance
  3. Optionally analyzed by AI for impact assessment
  4. Stored in intel_events table

Run as a daemon thread or standalone:
    python -m workers.intel_harvester --players "Scottie Scheffler,Rory McIlroy"
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus

import requests

from src import db
from src.player_normalizer import normalize_name

logger = logging.getLogger("intel_harvester")

# Golf-specific RSS/news feeds
GOLF_RSS_FEEDS = [
    "https://www.pgatour.com/feeds/news.rss",
    "https://www.golfdigest.com/feed/rss",
    "https://www.golfwrx.com/feed/",
]

# Reddit subreddits to check
REDDIT_SUBS = ["golf", "sportsbook", "dfsports"]

# Equipment-related keywords
EQUIPMENT_KEYWORDS = [
    "new driver", "new putter", "equipment change", "switched to",
    "testing", "prototype", "new irons", "new ball", "new wedges",
    "bag change", "titleist", "taylormade", "callaway", "ping",
    "cobra", "mizuno", "srixon", "bridgestone", "scotty cameron",
]

# Injury/withdrawal keywords
INJURY_KEYWORDS = [
    "injury", "injured", "withdraw", "withdrawal", "WD",
    "back pain", "wrist", "knee", "surgery", "rehab",
    "illness", "sick", "out indefinitely", "pulled out",
]


def _fetch_google_news(player_name: str, max_results: int = 5) -> list[dict]:
    """
    Fetch recent news for a player from Google News RSS.
    Free, no API key needed.
    """
    query = quote_plus(f'"{player_name}" golf')
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    try:
        import feedparser
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_results]:
            items.append({
                "title": entry.get("title", ""),
                "source": "google_news",
                "source_url": entry.get("link", ""),
                "snippet": entry.get("summary", "")[:500],
                "published_at": entry.get("published", ""),
                "player_name": player_name,
            })
        return items
    except ImportError:
        logger.warning("feedparser not installed, skipping Google News")
        return []
    except Exception as e:
        logger.warning("Google News fetch failed for %s: %s", player_name, e)
        return []


def _fetch_reddit_mentions(player_name: str, subreddit: str = "golf",
                           max_results: int = 5) -> list[dict]:
    """
    Fetch recent Reddit mentions of a player.
    Uses Reddit's public JSON API (no auth needed for read-only).
    """
    query = quote_plus(player_name)
    url = f"https://www.reddit.com/r/{subreddit}/search.json?q={query}&sort=new&t=week&limit={max_results}"
    headers = {"User-Agent": "GolfModel/1.0 (research)"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = []
        for post in data.get("data", {}).get("children", []):
            pd = post.get("data", {})
            items.append({
                "title": pd.get("title", ""),
                "source": f"reddit_r/{subreddit}",
                "source_url": f"https://reddit.com{pd.get('permalink', '')}",
                "snippet": (pd.get("selftext", "") or "")[:500],
                "published_at": datetime.fromtimestamp(
                    pd.get("created_utc", 0)
                ).isoformat() if pd.get("created_utc") else "",
                "player_name": player_name,
            })
        return items
    except Exception as e:
        logger.warning("Reddit fetch failed for %s in r/%s: %s", player_name, subreddit, e)
        return []


def _fetch_rss_feed(feed_url: str, max_results: int = 10) -> list[dict]:
    """Fetch items from a golf RSS feed."""
    try:
        import feedparser
        feed = feedparser.parse(feed_url)
        items = []
        for entry in feed.entries[:max_results]:
            items.append({
                "title": entry.get("title", ""),
                "source": feed_url.split("/")[2],  # domain
                "source_url": entry.get("link", ""),
                "snippet": entry.get("summary", "")[:500],
                "published_at": entry.get("published", ""),
            })
        return items
    except ImportError:
        return []
    except Exception as e:
        logger.warning("RSS fetch failed for %s: %s", feed_url, e)
        return []


def _match_player(text: str, player_names: list[str]) -> Optional[str]:
    """
    Check if any player name appears in the text.
    Returns the matched player name or None.
    """
    text_lower = text.lower()
    for name in player_names:
        # Check full name
        if name.lower() in text_lower:
            return name
        # Check last name only (for common references)
        parts = name.split()
        if len(parts) > 1 and len(parts[-1]) > 3:
            if parts[-1].lower() in text_lower:
                return name
    return None


def _classify_intel(title: str, snippet: str) -> tuple[str, float]:
    """
    Classify an intel item by category and assign a base relevance score.

    Returns: (category, base_relevance)
    """
    combined = (title + " " + snippet).lower()

    # Check for equipment changes (high relevance)
    for kw in EQUIPMENT_KEYWORDS:
        if kw in combined:
            return "equipment", 0.8

    # Check for injury/withdrawal (very high relevance)
    for kw in INJURY_KEYWORDS:
        if kw in combined:
            return "injury", 0.9

    # Check for form-related keywords
    form_keywords = ["winning", "victory", "champion", "leader", "first round",
                     "shot", "under par", "birdie", "eagle", "streak"]
    for kw in form_keywords:
        if kw in combined:
            return "form", 0.5

    # Check for personal/motivation
    personal_keywords = ["wedding", "baby", "father", "family", "motivation",
                         "caddie change", "new coach", "swing change"]
    for kw in personal_keywords:
        if kw in combined:
            return "personal", 0.4

    # Check for weather
    weather_keywords = ["weather", "wind", "rain", "forecast", "conditions"]
    for kw in weather_keywords:
        if kw in combined:
            return "weather", 0.3

    return "general", 0.2


def _detect_equipment_change(title: str, snippet: str,
                             player_name: str) -> Optional[dict]:
    """
    Detect if an intel item describes an equipment change.

    Returns equipment change dict or None.
    """
    combined = (title + " " + snippet).lower()

    categories = {
        "driver": ["driver", "1-wood", "1w"],
        "irons": ["irons", "iron set"],
        "putter": ["putter", "flat stick"],
        "wedges": ["wedges", "lob wedge", "sand wedge"],
        "ball": ["ball", "golf ball", "pro v1", "tp5", "chrome soft"],
        "fairway_wood": ["fairway wood", "3-wood", "5-wood"],
    }

    detected_category = None
    for cat, keywords in categories.items():
        for kw in keywords:
            if kw in combined:
                detected_category = cat
                break
        if detected_category:
            break

    if not detected_category:
        return None

    return {
        "player_key": normalize_name(player_name),
        "change_date": datetime.now().strftime("%Y-%m-%d"),
        "category": detected_category,
        "old_equipment": None,
        "new_equipment": None,
        "source": "intel_harvester",
    }


def harvest_for_field(player_names: list[str],
                      use_ai: bool = False,
                      tournament_id: int = None) -> dict:
    """
    Run a full intel harvest for a list of player names.

    Steps:
    1. Fetch Google News for each player
    2. Fetch Reddit mentions for each player
    3. Scan golf RSS feeds for any player mentions
    4. Classify and score each item
    5. Optionally run AI analysis
    6. Store in intel_events table

    Returns summary dict.
    """
    summary = {
        "players_searched": len(player_names),
        "items_found": 0,
        "items_stored": 0,
        "equipment_changes": 0,
        "errors": [],
    }

    all_items = []

    # 1. Google News (per player)
    for name in player_names:
        items = _fetch_google_news(name)
        for item in items:
            item["player_key"] = normalize_name(name)
        all_items.extend(items)
        time.sleep(0.5)  # Rate limit

    # 2. Reddit (per player, across subreddits)
    for name in player_names[:20]:  # Limit to top 20 to avoid rate limits
        for sub in REDDIT_SUBS:
            items = _fetch_reddit_mentions(name, sub)
            for item in items:
                item["player_key"] = normalize_name(name)
            all_items.extend(items)
            time.sleep(1.0)  # Reddit rate limit

    # 3. Golf RSS feeds (scan for any player mention)
    for feed_url in GOLF_RSS_FEEDS:
        feed_items = _fetch_rss_feed(feed_url)
        for item in feed_items:
            matched = _match_player(
                item.get("title", "") + " " + item.get("snippet", ""),
                player_names,
            )
            if matched:
                item["player_name"] = matched
                item["player_key"] = normalize_name(matched)
                all_items.append(item)
        time.sleep(0.5)

    summary["items_found"] = len(all_items)

    # 4. Classify and store
    conn = db.get_conn()
    for item in all_items:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        pkey = item.get("player_key", "")
        source_url = item.get("source_url", "")

        if not pkey or not source_url:
            continue

        category, relevance = _classify_intel(title, snippet)

        try:
            conn.execute("""
                INSERT OR IGNORE INTO intel_events
                (player_key, source, source_url, title, snippet,
                 published_at, tournament_id, relevance_score, category)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                pkey,
                item.get("source", ""),
                source_url,
                title[:500],
                snippet[:1000],
                item.get("published_at", ""),
                tournament_id,
                relevance,
                category,
            ))
            summary["items_stored"] += 1
        except Exception as e:
            summary["errors"].append(str(e))

        # 5. Detect equipment changes
        equip = _detect_equipment_change(title, snippet, item.get("player_name", ""))
        if equip:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO equipment_changes
                    (player_key, change_date, category, source)
                    VALUES (?,?,?,?)
                """, (
                    equip["player_key"],
                    equip["change_date"],
                    equip["category"],
                    "intel_harvester: " + source_url[:200],
                ))
                summary["equipment_changes"] += 1
            except Exception:
                pass

    conn.commit()

    # 6. Optional AI analysis
    if use_ai and all_items:
        _ai_analyze_intel(all_items[:20])

    logger.info("Intel harvest: %d items found, %d stored, %d equipment changes",
                summary["items_found"], summary["items_stored"], summary["equipment_changes"])
    return summary


def _ai_analyze_intel(items: list[dict]):
    """Use AI to analyze top intel items and update relevance/summary."""
    try:
        from src.ai_brain import call_ai
        from src.prompts import intel_analysis
    except ImportError:
        return

    prompt = intel_analysis(items)
    try:
        response = call_ai(prompt, max_tokens=1500)
        if not response:
            return

        # Parse JSON response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start < 0 or end <= start:
            return
        parsed = json.loads(response[start:end])

        conn = db.get_conn()
        for analyzed in parsed.get("analyzed_items", []):
            source_url = None
            for item in items:
                if item.get("title") == analyzed.get("original_title"):
                    source_url = item.get("source_url")
                    break

            if source_url:
                conn.execute("""
                    UPDATE intel_events
                    SET relevance_score = ?,
                        category = ?,
                        ai_summary = ?,
                        analyzed_at = datetime('now')
                    WHERE source_url = ?
                """, (
                    analyzed.get("relevance_score", 0.5),
                    analyzed.get("category", "general"),
                    analyzed.get("summary", ""),
                    source_url,
                ))
        conn.commit()
    except Exception as e:
        logger.warning("AI intel analysis failed: %s", e)


def get_field_intel(player_keys: list[str],
                    min_relevance: float = 0.3) -> list[dict]:
    """
    Get stored intel for a list of players, filtered by relevance.
    Returns list of intel dicts sorted by relevance.
    """
    if not player_keys:
        return []

    conn = db.get_conn()
    placeholders = ",".join(["?"] * len(player_keys))
    rows = conn.execute(f"""
        SELECT player_key, title, snippet, source, category,
               ai_summary, relevance_score, published_at
        FROM intel_events
        WHERE player_key IN ({placeholders})
          AND relevance_score >= ?
        ORDER BY relevance_score DESC
        LIMIT 50
    """, [*player_keys, min_relevance]).fetchall()

    return [dict(r) for r in rows]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Intel Harvester")
    parser.add_argument("--players", required=True,
                        help="Comma-separated player names")
    parser.add_argument("--ai", action="store_true",
                        help="Use AI to analyze intel")
    args = parser.parse_args()

    from src.db import ensure_initialized
    ensure_initialized()

    players = [p.strip() for p in args.players.split(",")]
    result = harvest_for_field(players, use_ai=args.ai)
    print(json.dumps(result, indent=2))
