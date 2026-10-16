"""Lossless, non-grading index of preserved Markdown prediction artifacts.

No database/model imports. A prediction observation is a source line, not a bet.
Original text, headings, cell strings and every source reference remain available.
"""
from __future__ import annotations

import hashlib
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plain(value: str) -> str:
    return re.sub(r"[*_`]", "", value).strip()


def cells(line: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def column(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", plain(value).lower()).strip("_")


def parse_markdown(data: bytes, *, source_hash: str | None = None) -> dict:
    """Index all player tables and forecast-like bullets without inventing rules."""
    sha = source_hash or digest(data)
    if digest(data) != sha:
        raise ValueError("Source content hash does not match.")
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    title = next((line[2:].strip() for line in lines if line.startswith("# ")), "")
    event = re.split(r"\s+[—–-]\s+(?:Betting Card|Team Event|Predictions|Model)", title, flags=re.I)[0]
    if re.search(r"betting card|team event notice", title, re.I):
        role = "original_card"
    elif re.search(r"methodology", title, re.I):
        role = "methodology_restatement"
    elif re.search(r"audit|grading|roi.*today", title, re.I):
        role = "retrospective_report"
    elif re.search(r"research|plan|backtest|dossier|experiment", title, re.I):
        role = "research_document"
    else:
        role = "unclassified_artifact"
    execution_context = "sandbox" if re.search(r"baseline strategy[^\n]*\bvia\s+`?sandbox\b", text[:4000], re.I) else None
    event_identity = "unresolved" if re.fullmatch(r"(?:test|fixture|current|future|next|sample|demo)(?:\s+event)?", event.strip(), re.I) or not event else "name_only"
    generated = None
    for line in lines[:60]:
        match = re.search(r"(?:\*\*)?(?:Generated|Run date|Generated at)(?:\*\*)?\s*:\s*(?:\*\*)?(.+)", line, re.I)
        if match:
            generated = plain(match.group(1))
            break
    headings: list[tuple[int, str]] = []
    observations, unparsed = [], []
    headers: list[str] | None = None
    header_line = None
    fenced = False
    forecast_context = bool(re.search(r"betting card|model rankings|prediction|matchup edges", text[:12000], re.I))
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)", line)
        if heading:
            level = len(heading.group(1))
            headings = [(n, h) for n, h in headings if n < level] + [(level, heading.group(2).strip())]
            headers = None
            continue
        context = " > ".join(h for _, h in headings)
        is_table = line.strip().startswith("|") and line.strip().endswith("|")
        if is_table:
            values = cells(line)
            if i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
                headers = values
                header_line = i + 1
                continue
            if all(re.fullmatch(r":?-+:?", value.replace(" ", "")) for value in values):
                continue
            if headers:
                keys = [column(v) for v in headers]
                if not any(v in {"player", "pick", "golfer", "name", "player_a", "player_1", "selection"} for v in keys):
                    continue
                row = {key: values[j] if j < len(values) else None for j, key in enumerate(keys)}
                if any(v in keys for v in ["composite", "course_fit", "momentum"]) and "rank" in keys:
                    kind = "ranking"
                elif re.search(r"recommended bets|ai bets", context, re.I):
                    kind = "ai_recommendation"
                elif any(re.search(r"odds|prob|win_pct|ev", key) for key in keys):
                    kind = "priced_prediction"
                elif forecast_context:
                    kind = "qualitative_prediction"
                else:
                    continue
                player_key = next((v for v in ["player", "pick", "golfer", "name", "player_a", "player_1", "selection"] if v in row), "")
                observations.append({"id": digest(f"{sha}:{i+1}".encode()), "source_sha256": sha, "line": i + 1,
                                     "kind": kind, "event_label": event, "generated_label": generated,
                                     "section": context, "player_label": plain(row.get(player_key) or ""),
                                     "headers": headers, "cells": values, "fields": row,
                                     "raw_text": line, "table_header_line": header_line,
                                     "publication_verified": False, "settlement_inferred": False})
                continue
        else:
            headers = None
        if not forecast_context or not re.match(r"^\s*(?:[-*]|\d+\.)\s+", line):
            continue
        kind = None
        if re.search(r"\bmodel\s+\d+(?:\.\d+)?%|\bEV\s+[+-]?\d|\b[+-]\d{3,}\s*@", line, re.I):
            kind = "priced_prediction"
        elif re.search(r"\*\*.+?\*\*\s+(?:over|vs\.?)\s+.+?(?:edge|pts|odds)", line, re.I):
            kind = "matchup_projection"
        elif re.search(r"fade|avoid|players to watch|players to fade", context, re.I) and re.search(r"\*\*[^*]+\*\*", line):
            kind = "qualitative_prediction"
        if kind:
            player = re.search(r"\*\*(?!VALUE\*\*|PASS\*\*|BET\*\*)([^*]+)\*\*", line)
            observations.append({"id": digest(f"{sha}:{i+1}".encode()), "source_sha256": sha, "line": i + 1,
                                 "kind": kind, "event_label": event, "generated_label": generated,
                                 "section": context, "player_label": player.group(1) if player else "",
                                 "raw_text": line, "fields": {}, "headers": [], "cells": [],
                                 "publication_verified": False, "settlement_inferred": False})
        elif re.search(r"\b(?:odds|EV|probability|over|vs\.?|units|composite)\b", line, re.I):
            unparsed.append({"line": i + 1, "section": context, "raw_text": line})
    for row in observations:
        row["artifact_role"] = role
        row["event_identity_status"] = event_identity
        if execution_context:
            row["declared_execution_context"] = execution_context
    return {"sha256": sha, "title": title, "event_label": event, "generated_label": generated,
            "artifact_role": role, "event_identity_status": event_identity, "declared_execution_context": execution_context,
            "line_count": len(lines), "decode_replacement": "\ufffd" in text,
            "forecast_context": forecast_context, "observations": observations,
            "unparsed_candidates": unparsed}


def parse_json_forecasts(data: bytes, *, source_hash: str | None = None) -> dict:
    """Retain supported saved forecast arrays with exact JSON pointers/payloads.

    This is an index, never an execution engine. Unknown structures stay preserved
    and explicitly unindexed; a provenance-only JSON file is not a prediction.
    """
    sha = source_hash or digest(data)
    if digest(data) != sha:
        raise ValueError("Source content hash does not match.")
    payload = json.loads(data)
    observations = []
    if not isinstance(payload, dict):
        return {"sha256": sha, "observations": [], "state": "unsupported_root"}
    def emit_rows(rows, pointer, kind, context):
        if not isinstance(rows, list):
            return
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            player = next((row[k] for k in ("player", "player_display", "pick", "player_key", "pick_key", "player_name") if row.get(k)), None)
            if player is None:
                continue
            ref = f"{pointer}/{i}"
            observations.append({"id": digest(f"{sha}:{ref}".encode()), "source_sha256": sha,
                                 "json_pointer": ref, "kind": kind, "player_label": str(player),
                                 "event_label": context.get("event_name"),
                                 "source_event_id": context.get("source_event_id") or context.get("event_id"),
                                 "model_variant": context.get("model_variant"),
                                 "generated_label": context.get("generated_at") or payload.get("generated_at"),
                                 "payload": row, "publication_verified": False, "settlement_inferred": False})
    roots = [("", payload)]
    def wrappers(prefix, obj, depth=0):
        if depth >= 3:
            return
        for key in ("snapshot", "data", "result", "body"):
            if isinstance(obj.get(key), dict):
                path = f"{prefix}/{key}"
                roots.append((path, obj[key]))
                wrappers(path, obj[key], depth + 1)
    wrappers("", payload)
    sections = list(roots)
    for root_prefix, root in roots:
        for key in ("live_tournament", "upcoming_tournament", "legacy_tournament", "lab_live_tournament", "lab_upcoming_tournament"):
            if isinstance(root.get(key), dict):
                context = dict(root[key])
                context.setdefault("generated_at", root.get("generated_at"))
                sections.append((f"{root_prefix}/{key}", context))
        for key in ("events", "tournaments"):
            if isinstance(root.get(key), list):
                for i, event in enumerate(root[key]):
                    if isinstance(event, dict):
                        context = dict(event)
                        context.setdefault("event_name", event.get("name") or event.get("event"))
                        sections.append((f"{root_prefix}/{key}/{i}", context))
    for prefix, section in sections:
        emit_rows(section.get("rankings"), f"{prefix}/rankings", "ranking", section)
        for key in ("pre_tournament_rankings", "frozen_pre_teeoff_rankings", "live_rankings"):
            emit_rows(section.get(key), f"{prefix}/{key}", f"ranking_{key}", section)
        for key in ("matchups", "matchup_bets", "matchup_bets_all_books", "market_rows", "picks", "predictions", "bets", "top_picks"):
            emit_rows(section.get(key), f"{prefix}/{key}", "saved_market_prediction", section)
        value = section.get("value_bets")
        if isinstance(value, dict):
            for key, rows in value.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                emit_rows(rows, f"{prefix}/value_bets/{escaped}", "saved_market_prediction", section)
        else:
            emit_rows(value, f"{prefix}/value_bets", "saved_market_prediction", section)
    return {"sha256": sha, "observations": observations,
            "state": "indexed" if observations else "no_supported_forecast_arrays",
            "root_keys": sorted(payload)}


def build_structured_archive(corpus_roots: list[Path], output: Path) -> dict:
    for root in corpus_roots:
        if not any((root / name).is_file() for name in ("sources.jsonl", "structured_sources.jsonl")):
            raise FileNotFoundError(f"Missing source manifest under: {root}")
    if output.exists():
        raise FileExistsError("Archive generations are immutable; choose a new output directory.")
    output.mkdir(parents=True)
    sources, paths = defaultdict(list), {}
    for root in corpus_roots:
        for name in ("sources.jsonl", "structured_sources.jsonl"):
            manifest = root / name
            if not manifest.exists():
                continue
            for line in manifest.read_text().splitlines():
                source = json.loads(line)
                path = Path(source["corpus_path"])
                if not path.is_absolute():
                    path = root / path
                if not str(path).lower().endswith((".json", ".json.gz")):
                    continue
                source = {**source, "corpus_root": str(root.resolve()), "resolved_corpus_path": str(path.resolve())}
                sha = source["sha256"]
                sources[sha].append(source)
                paths[sha] = path
    files, counts = [], Counter()
    with (output / "structured-prediction-observations.jsonl").open("x") as stream:
        for sha, path in sorted(paths.items()):
            data = gzip.decompress(path.read_bytes()) if str(path).endswith(".gz") else path.read_bytes()
            try:
                parsed = parse_json_forecasts(data, source_hash=sha)
            except (ValueError, UnicodeError) as exc:
                if digest(data) != sha:
                    raise ValueError("Source content hash does not match.") from exc
                files.append({"sha256": sha, "sources": sources[sha], "state": "not_complete_valid_json"})
                continue
            files.append({k: v for k, v in parsed.items() if k != "observations"} | {"sources": sources[sha], "observations": len(parsed["observations"])})
            for row in parsed["observations"]:
                row["source_kinds"] = sorted({s.get("source_kind", "unclassified_source") for s in sources[sha]})
                row["content_statuses"] = sorted({s.get("content_status", "preserved_file_bytes") for s in sources[sha]})
                counts[row["kind"]] += 1
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    result = {"schema_version": 1, "source_files": len(paths), "source_references": sum(map(len, sources.values())),
              "counts": dict(counts), "files": files,
              "limits": ["Saved source rows retain original payloads; projections across snapshots are not independent wagers.",
                         "No publication, placement or settlement is inferred. Unsupported/partial JSON remains in the preserved corpus."]}
    (output / "structured-archive-index.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return result


def build_archive(corpus_roots: list[Path], output: Path) -> dict:
    """Create an exclusive generation; content dedupe retains every source path."""
    for root in corpus_roots:
        if not (root / "sources.jsonl").is_file():
            raise FileNotFoundError(f"Missing source manifest: {root / 'sources.jsonl'}")
    if output.exists():
        raise FileExistsError("Archive generations are immutable; choose a new output directory.")
    output.mkdir(parents=True)
    sources: dict[str, list[dict]] = defaultdict(list)
    paths: dict[str, Path] = {}
    for root in corpus_roots:
        manifest = root / "sources.jsonl"
        if not manifest.exists():
            raise FileNotFoundError(f"Missing source manifest: {manifest}")
        for line in manifest.read_text().splitlines():
            source = json.loads(line)
            sha = source["sha256"]
            path = Path(source["corpus_path"])
            if not path.is_absolute():
                path = root / path
            if not str(path).lower().endswith((".md", ".md.gz")):
                continue
            source = {**source, "corpus_root": str(root.resolve()), "resolved_corpus_path": str(path.resolve())}
            sources[sha].append(source)
            paths[sha] = path
    counts: Counter = Counter()
    role_counts: dict[str, Counter] = defaultdict(Counter)
    original_counts: Counter = Counter()
    files, events = [], defaultdict(lambda: {"files": 0, "observations": 0, "kinds": Counter(), "dates": set()})
    with (output / "prediction-observations.jsonl").open("x") as stream, (output / "unparsed-candidates.jsonl").open("x") as missing:
        for sha, path in sorted(paths.items()):
            payload = gzip.decompress(path.read_bytes()) if str(path).endswith(".gz") else path.read_bytes()
            parsed = parse_markdown(payload, source_hash=sha)
            source_kinds = {s.get("source_kind", "unclassified_source") for s in sources[sha]}
            research_path = any(re.search(r"(?:^|[/!])(?:sandbox(?:[/_])|backtests/|research/)", s.get("source_path", ""), re.I) for s in sources[sha])
            if (parsed["artifact_role"] == "original_card"
                    and (source_kinds & {"sandbox_or_backtest_output", "research_trial", "research_output"} or research_path)
                    and "original_card_candidate" not in source_kinds):
                parsed["artifact_role"] = "research_card"
                for row in parsed["observations"]:
                    row["artifact_role"] = "research_card"
            file = {k: v for k, v in parsed.items() if k not in {"observations", "unparsed_candidates"}}
            file["sources"] = sources[sha]
            file["prediction_observations"] = len(parsed["observations"])
            file["unparsed_candidates"] = len(parsed["unparsed_candidates"])
            files.append(file)
            if parsed["observations"]:
                e = events[parsed["event_label"]]
                e["files"] += 1
                e["observations"] += len(parsed["observations"])
                if parsed["generated_label"]:
                    e["dates"].add(parsed["generated_label"])
            for row in parsed["observations"]:
                counts[row["kind"]] += 1
                role_counts[row["artifact_role"]][row["kind"]] += 1
                row["source_kinds"] = sorted({s.get("source_kind", "unclassified_source") for s in sources[sha]})
                row["content_statuses"] = sorted({s.get("content_status", "preserved_file_bytes") for s in sources[sha]})
                if row["artifact_role"] == "original_card" and row["event_identity_status"] != "unresolved":
                    original_counts[row["kind"]] += 1
                events[row["event_label"]]["kinds"][row["kind"]] += 1
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            for row in parsed["unparsed_candidates"]:
                missing.write(json.dumps({"source_sha256": sha, **row}, ensure_ascii=False, sort_keys=True) + "\n")
    result = {"schema_version": 1, "basis": "preserved_prediction_artifacts", "source_files": len(paths),
              "source_references": sum(map(len, sources.values())), "counts": dict(counts),
              "counts_by_artifact_role": {k: dict(v) for k, v in role_counts.items()},
              "named_original_card_observations": dict(original_counts), "files": files,
              "events": [{"label": k, **{a: sorted(b) if a == "dates" else dict(b) if a == "kinds" else b for a, b in v.items()}} for k, v in sorted(events.items())],
              "limits": ["Source lines are prediction observations, not independent wagers.",
                         "File generation labels are retained as written; pre-event publication is not certified.",
                         "Original card text and all provenance references remain intact. Missing contracts and unparsed candidates are retained.",
                         "No grading, settlement, stakes, ROI or CLV is inferred by this inventory."]}
    (output / "archive-index.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return result
