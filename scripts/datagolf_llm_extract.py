#!/usr/bin/env python3
"""
Fetch Data Golf / legacy blog HTML and extract dense, structured notes via OpenAI.

Outputs:
  docs/research/datagolf_extractions.jsonl — one JSON record per URL (full extraction).
Updates:
  docs/research/datagolf_article_index.csv — summary_bullets, proposed_change,
  code_touchpoints, verify_with, model_dimensions, status, extraction_method.

Requires OPENAI_API_KEY (see .env.example). Forces OpenAI for this script regardless
of AI_BRAIN_PROVIDER. Uses low temperature for extraction fidelity.

Usage (repo root):
  python3 scripts/datagolf_llm_extract.py --limit 5
  python3 scripts/datagolf_llm_extract.py --dry-run --limit 2
  python3 scripts/datagolf_llm_extract.py --force --limit 1   # re-run even if extracted
  python3 scripts/datagolf_llm_extract.py --sync-csv-from-jsonl  # merge jsonl into CSV only
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

from src.ai_brain import _bootstrap_env_from_dotenv, _call_ai  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "docs/research/datagolf_article_index.csv"
DEFAULT_JSONL = REPO_ROOT / "docs/research/datagolf_extractions.jsonl"
USER_AGENT = "golf-model-datagolf-research/1.0 (+local lab extraction)"
MAX_BODY_CHARS = 120_000
SUMMARY_CSV_MAX = 20_000


def _is_article_fetch_url(url: str) -> bool:
    """Skip junk rows (markdown typos, endpoints) that are not HTML articles."""
    if not url.startswith("https://"):
        return False
    if "**" in url or "*" in url:
        return False
    if "xmlrpc" in url.lower():
        return False
    low = url.lower()
    for tail in (
        "/robots.txt",
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/wp-sitemap.xml",
    ):
        if low.endswith(tail):
            return False
    if "):" in url:
        return False
    if url.rstrip("/") in ("https://datagolf.com", "https://datagolfblogs.ca"):
        return False
    if not (
        url.startswith("https://datagolf.com/")
        or url.startswith("https://datagolfblogs.ca/")
    ):
        return False
    return True


def _strip_html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html).strip()
    return html


def _fetch_text(url: str, timeout: int) -> tuple[str, int]:
    r = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )
    r.raise_for_status()
    raw = r.text
    text = _strip_html_to_text(raw)
    if len(text) > MAX_BODY_CHARS:
        text = text[:MAX_BODY_CHARS] + "\n\n[TRUNCATED_FOR_CONTEXT_LIMIT]"
    return text, len(raw)


def _extraction_schema() -> dict:
    """OpenAI strict json_schema: every object property listed in required."""
    section = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["title", "notes"],
        "additionalProperties": False,
    }
    qclaim = {
        "type": "object",
        "properties": {
            "claim": {"type": "string"},
            "numbers_or_evidence": {"type": "string"},
        },
        "required": ["claim", "numbers_or_evidence"],
        "additionalProperties": False,
    }
    props = {
        "article_kind": {
            "type": "string",
            "description": "methodology|visualization|model_talk|opinion|news|data_notes|other",
        },
        "one_line_premise": {"type": "string"},
        "executive_summary": {
            "type": "string",
            "description": "Thorough summary of thesis, evidence, and conclusions.",
        },
        "detailed_sections": {"type": "array", "items": section},
        "quantitative_claims": {"type": "array", "items": qclaim},
        "definitions_and_terms": {"type": "array", "items": {"type": "string"}},
        "methodology_steps": {"type": "array", "items": {"type": "string"}},
        "modeling_implications": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concrete changes or hypotheses for a stroke-gained / simulation golf model.",
        },
        "suggested_code_areas": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Repo-oriented guesses e.g. course_fit, form.py, v5_probabilities.",
        },
        "backtest_or_validation_ideas": {"type": "array", "items": {"type": "string"}},
        "related_hypotheses": {"type": "array", "items": {"type": "string"}},
        "caveats_and_limits": {"type": "string"},
        "model_dimension_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "From docs/research/datagolf_topic_taxonomy.md IDs where applicable.",
        },
    }
    required = list(props.keys())
    return {
        "name": "datagolf_article_extraction",
        "schema": {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
    }


def _build_user_prompt(url: str, title: str, body: str) -> str:
    return (
        f"URL: {url}\n"
        f"INDEX_TITLE: {title or '(empty)'}\n\n"
        "ARTICLE_TEXT (HTML stripped, may be truncated):\n"
        f"{body}\n\n"
        "Extract structured notes for an internal golf probability-model engineering team. "
        "Preserve numbers, units, percentages, and sample sizes exactly where stated. "
        "If the text is thin or not an article, still fill schema with best-effort notes and "
        "mark article_kind as other. Use empty arrays or empty strings where nothing applies."
    )


def _rows_from_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def _load_extracted_urls(jsonl_path: Path) -> set[str]:
    if not jsonl_path.exists():
        return set()
    out: set[str] = set()
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            u = obj.get("url")
            if isinstance(u, str):
                out.add(u)
        except json.JSONDecodeError:
            continue
    return out


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def sync_csv_from_jsonl(csv_path: Path, jsonl_path: Path) -> int:
    """Apply existing jsonl extraction payloads to matching CSV rows (no API calls)."""
    if not jsonl_path.is_file():
        print(f"No jsonl at {jsonl_path}", file=sys.stderr)
        return 1
    rows = _rows_from_csv(csv_path)
    if not rows:
        print("CSV has no rows.", file=sys.stderr)
        return 1
    fieldnames = list(rows[0].keys())
    by_url = {(r.get("url") or "").strip(): r for r in rows}
    updated = 0
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = (obj.get("url") or "").strip()
        ext = obj.get("extraction")
        if not url or not isinstance(ext, dict):
            continue
        row = by_url.get(url)
        if not row:
            continue
        _apply_extraction_to_row(row, ext)
        updated += 1
    _write_csv(csv_path, rows, fieldnames)
    print(f"Synced {updated} CSV row(s) from {jsonl_path}")
    return 0


def _apply_extraction_to_row(row: dict, ext: dict) -> None:
    dims = ext.get("model_dimension_ids") or []
    row["model_dimensions"] = ";".join(str(x) for x in dims if str(x).strip())

    summary = (ext.get("executive_summary") or "").strip()
    premise = (ext.get("one_line_premise") or "").strip()
    bullets = "\n".join(f"- {x}" for x in (ext.get("modeling_implications") or [])[:12])
    block = "\n\n".join(p for p in [premise, summary, bullets] if p)
    if len(block) > SUMMARY_CSV_MAX:
        block = block[: SUMMARY_CSV_MAX - 20] + "\n...[truncated]"
    row["summary_bullets"] = block

    impls = ext.get("modeling_implications") or []
    row["proposed_change"] = "\n".join(str(x) for x in impls)

    areas = ext.get("suggested_code_areas") or []
    row["code_touchpoints"] = "; ".join(str(x) for x in areas)

    ideas = ext.get("backtest_or_validation_ideas") or []
    row["verify_with"] = "\n".join(str(x) for x in ideas)

    row["status"] = "llm_extracted_v1"
    row["extraction_method"] = "openai_json_schema"


def main() -> int:
    ap = argparse.ArgumentParser(description="LLM batch extract from Data Golf article index.")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    ap.add_argument("--limit", type=int, default=5, help="Max articles to process this run.")
    ap.add_argument("--sleep", type=float, default=0.75, help="Seconds between API calls.")
    ap.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds.")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument(
        "--status",
        default="pending_read",
        help="Only process rows with this status (default: pending_read).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-extract even if status is already llm_extracted_v1 or URL exists in jsonl.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print sizes only; no OpenAI calls or file writes.",
    )
    ap.add_argument(
        "--sync-csv-from-jsonl",
        action="store_true",
        help="Copy extraction fields from jsonl into CSV for matching URLs; no network.",
    )
    args = ap.parse_args()

    csv_path: Path = args.csv
    jsonl_path: Path = args.jsonl
    if args.sync_csv_from_jsonl:
        return sync_csv_from_jsonl(csv_path, jsonl_path)

    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 1

    rows = _rows_from_csv(csv_path)
    if not rows:
        print("CSV has no rows.", file=sys.stderr)
        return 1

    fieldnames = list(rows[0].keys())
    jsonl_urls = _load_extracted_urls(jsonl_path) if not args.force else set()

    _bootstrap_env_from_dotenv()
    os.environ["AI_BRAIN_PROVIDER"] = "openai"

    schema = _extraction_schema()
    system = (
        "You are a senior golf analytics researcher. Extract maximum useful technical detail "
        "for building and validating a PGA stroke-gained / tournament simulation model. "
        "Respond only with JSON matching the provided schema."
    )

    processed = 0
    for row in rows:
        if processed >= args.limit:
            break
        url = (row.get("url") or "").strip()
        if not url:
            continue
        if not _is_article_fetch_url(url):
            print(f"[skip bad url] {url}", file=sys.stderr)
            continue
        st = (row.get("status") or "").strip()
        if st != args.status and not args.force:
            continue
        if not args.force and st == "llm_extracted_v1":
            continue
        if not args.force and url in jsonl_urls:
            continue

        title = (row.get("title") or "").strip()
        try:
            body, raw_len = _fetch_text(url, args.timeout)
        except Exception as exc:
            print(f"[skip fetch] {url}: {exc}", file=sys.stderr)
            continue

        if args.dry_run:
            print(f"[dry-run] {url} raw_html={raw_len} text={len(body)} title={title[:60]!r}")
            processed += 1
            continue

        user = _build_user_prompt(url, title, body)
        try:
            ext = _call_ai(system, user, response_schema=schema, temperature=args.temperature)
        except Exception as exc:
            print(f"[skip llm] {url}: {exc}", file=sys.stderr)
            continue

        record = {
            "url": url,
            "title_index": title,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "raw_html_bytes": raw_len,
            "stripped_text_chars": len(body),
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o"),
            "extraction": ext,
        }
        _append_jsonl(jsonl_path, record)
        jsonl_urls.add(url)
        _apply_extraction_to_row(row, ext)
        processed += 1
        _write_csv(csv_path, rows, fieldnames)
        print(f"[ok] {url}", flush=True)
        time.sleep(args.sleep)

    if not args.dry_run and processed:
        print(f"Finished {processed} extraction(s); CSV updated each step; jsonl at {jsonl_path}")
    elif args.dry_run:
        print(f"Dry-run complete ({processed} row(s) checked).")
    else:
        print("No rows matched filters or all fetches/LLM calls failed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
