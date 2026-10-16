"""Pure, provenance-first reporting over preserved history. No app/model imports.

The input is an immutable vault, never a live database. Source-local foreign keys
are resolved before any cross-generation deduplication. A consensus is a stored
paper record, not proof of a placed wager or an independently correct settlement.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

CORE_TABLES = {"tournaments", "picks", "pick_outcomes", "results", "prediction_log"}
MARKETS = {
    "72h": "72-hole matchups", "18h": "18-hole matchups", "group": "Group markets",
    "unspecified": "Unspecified matchups", "top5": "Top 5", "top10": "Top 10",
    "top20": "Top 20", "outright": "Outrights", "other": "Other markets",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def normalized(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def market_of(row):
    market = normalized(row.get("market_type"))
    bet = normalized(row.get("bet_type"))
    if market in {"tournament_matchups", "72h", "72_hole_matchups"}:
        return "72h"
    if market in {"round_matchups", "18h", "18_hole_matchups"}:
        return "18h"
    if market in {"groups", "group", "3balls", "3ball", "three_balls"}:
        return "group"
    if bet == "matchup":
        return "unspecified"
    return bet if bet in MARKETS else "other"


def date_part(value):
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (ValueError, TypeError):
        return None


def chronology(recorded_at, event):
    recorded = date_part(recorded_at)
    if recorded == "2026-01-01":
        return "restore_placeholder"
    if not recorded or not event:
        return "unknown"
    if recorded < event["starts_on"]:
        return "recorded_before_event"
    if recorded > event["ends_on"]:
        return "recorded_after_event"
    return "recorded_during_event"


def load_vault(path):
    """Check all row hashes, source/table closures and counts; keep partial states."""
    sources, streams, rows = {}, {}, []
    source_closed, opened = set(), set()
    counts = Counter()
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            kind, sid = obj["type"], obj.get("source_id")
            key = (sid, obj.get("table"))
            if kind == "source_begin":
                if sid in sources:
                    raise ValueError("Duplicate source announcement")
                sources[sid] = obj["source"]
            elif kind == "table_begin":
                if sid not in sources or key in opened:
                    raise ValueError("Invalid or duplicate table stream")
                opened.add(key)
            elif kind == "row":
                if key not in opened or key in streams or digest(obj["row"]) != obj["row_sha256"]:
                    raise ValueError("Row outside stream or payload hash mismatch")
                counts[key] += 1
                if obj["ordinal"] != counts[key]:
                    raise ValueError("Non-contiguous source ordinal")
                if obj["table"] in CORE_TABLES:
                    rows.append(obj)
            elif kind == "table_end":
                if key not in opened or key in streams or counts[key] != obj["rows"]:
                    raise ValueError("Stream count mismatch")
                streams[key] = obj
            elif kind == "source_end":
                if sid not in sources or sid in source_closed or obj.get("source_metadata_unchanged") is False:
                    raise ValueError("Source changed or invalid closure")
                source_closed.add(sid)
    if source_closed != set(sources) or set(streams) != opened:
        raise ValueError("Truncated vault")
    return {"sources": sources, "streams": streams, "rows": rows}


def resolve_event(row, calendar):
    # Provider IDs are strings (including leading zeros), not local primary keys.
    candidates = [e for e in calendar if str(e.get("provider_event_id")) == str(row.get("event_id"))
                  and e["year"] == row.get("year")
                  and normalized(row.get("name")) in {normalized(x) for x in e.get("aliases", [e["name"]])}]
    return candidates[0] if len(candidates) == 1 else None


def is_fixture(row):
    return str(row.get("event_id")) in {"700", "123", "124"} and normalized(row.get("name")) in {
        "current event", "test event", "future event"}


def outcome_value(row):
    """Keep original amounts, classify only explicit compatible stored outcomes."""
    profit, stake, hit = number(row.get("profit")), number(row.get("stake")), row.get("hit")
    finish = normalized(row.get("actual_finish"))
    authority = normalized(row.get("grading_authority"))
    issues = []
    if stake is None or stake <= 0 or profit is None:
        return "unknown", profit, stake, ["missing_or_invalid_settlement_amount"]
    if profit < -stake - 1e-8:
        issues.append("loss_exceeds_stake")
    if "void" in finish or authority == "void":
        if abs(profit) > 1e-8:
            issues.append("void_has_nonzero_profit")
        return "void", profit, stake, issues
    if finish in {"win vs win", "loss vs loss"}:
        issues.append("contradictory_matchup_result")
    if finish == "win vs loss" and hit != 1 or finish == "loss vs win" and hit != 0:
        issues.append("hit_disagrees_with_finish")
    if profit > 0 and hit != 1 or profit < 0 and hit != 0:
        issues.append("hit_disagrees_with_profit")
    if hit not in (0, 1):
        issues.append("missing_hit")
    return ("zero_return" if profit == 0 else "win" if profit > 0 else "loss"), profit, stake, issues


def reconcile(vault, calendar, *, cutoff="2026-10-14", cards=(), lineage=()):
    """Return decisions plus a compact public report; do not modify any input."""
    date.fromisoformat(cutoff)
    by_table = defaultdict(list)
    salvage, partial = [], []
    for obs in vault["rows"]:
        state = vault["streams"].get((obs["source_id"], obs["table"]), {}).get("state", "complete")
        if obs.get("provenance_status") == "salvaged_unverified" or vault["sources"][obs["source_id"]].get("recovery_status") == "salvaged_unverified":
            salvage.append(obs)
            continue
        if state != "complete":
            partial.append(obs)
            continue
        by_table[obs["table"]].append(obs)
    healthy_hashes = {(obs["table"], obs["row_sha256"]) for rows in by_table.values() for obs in rows}
    salvage_corroborated = sum((obs["table"], obs["row_sha256"]) in healthy_hashes for obs in salvage)
    tournaments, outcomes = defaultdict(list), defaultdict(list)
    for obs in by_table["tournaments"]:
        tournaments[(obs["source_id"], obs["row"]["id"])].append(obs)
    for obs in by_table["pick_outcomes"]:
        outcomes[(obs["source_id"], obs["row"].get("pick_id"))].append(obs)
    recovery_candidates = defaultdict(list)
    for row in lineage:
        if row.get("source_origin") not in {"restore", "market_row_backfill"}:
            continue
        recovery_candidates[(row["source_id"], row.get("tournament_id"), row.get("bet_type"),
                             row.get("player_key"), row.get("opponent_key"), normalized(row.get("book")),
                             number(row.get("odds")))].append(row)
    groups, excluded, links = defaultdict(list), [], []
    for obs in by_table["picks"]:
        p, sid = obs["row"], obs["source_id"]
        t = tournaments[(sid, p.get("tournament_id"))]
        event = resolve_event(t[0]["row"], calendar) if len(t) == 1 else None
        if len(t) == 1 and is_fixture(t[0]["row"]):
            excluded.append(obs)
            continue
        event_key = event["key"] if event else f"unresolved:{sid}:{p.get('tournament_id')}"
        # Same saved quote repeated in backups is one reporting lineage. Market,
        # forecast and config changes stay IN that lineage and cause a conflict.
        identity = [event_key, p.get("source"), p.get("bet_type"), p.get("player_key"),
                    p.get("opponent_key") or "", normalized(p.get("market_book")), number(p.get("market_odds")),
                    p.get("created_at")]
        if not p.get("created_at"):
            identity += [sid, p.get("id")]  # no invented cross-source multiplicity
        key = digest(identity)
        groups[key].append((obs, event, outcomes[(sid, p.get("id"))]))
        links.append({"decision_id": key, "source_id": sid, "table": "picks",
                      "ordinal": obs["ordinal"], "row_sha256": obs["row_sha256"]})
        if len(t) == 1:
            links.append({"decision_id": key, "source_id": sid, "table": "tournaments",
                          "ordinal": t[0]["ordinal"], "row_sha256": t[0]["row_sha256"]})

    # Recovery can insert the identical economic quote under another local id and
    # timestamp. Neither two bets nor the earlier decision time can be inferred.
    # Join these reporting families and exclude ambiguous repetitions from totals.
    parent = {key: key for key in groups}
    def root(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    economic_seen = {}
    for key, items in groups.items():
        for obs, event, _ in items:
            p = obs["row"]
            signature = digest([event["key"] if event else [obs["source_id"], p.get("tournament_id")],
                                *[p.get(field) for field in ("source", "bet_type", "player_key")], p.get("opponent_key") or "",
                                normalized(p.get("market_book")), number(p.get("market_odds")),
                                *[p.get(field) for field in ("market_type", "model_prob", "ev", "model_variant", "model_config_hash", "round", "round_number", "participants", "group_id")]])
            if signature in economic_seen:
                a, b = sorted((root(key), root(economic_seen[signature])))
                parent[b] = a
            economic_seen[signature] = key
    merged = defaultdict(list)
    for key, items in groups.items():
        merged[root(key)].extend(items)
    for link in links:
        link["decision_id"] = root(link["decision_id"])
    groups = merged

    decisions = []
    for key, items in sorted(groups.items()):
        first, event, _ = items[0]
        p = first["row"]
        issues = set()
        fields = ("market_type", "model_prob", "ev", "model_variant", "model_config_hash", "round", "round_number", "participants", "group_id")
        changes = [field for field in fields if len({canonical(item[0]["row"].get(field)) for item in items}) > 1]
        if changes:
            issues.update("changed_" + field for field in changes)
        market = market_of(p)
        if "market_type" in changes:
            market = "unspecified" if p.get("bet_type") == "matchup" else market
        round_number = p.get("round") or p.get("round_number")
        incomplete = []
        if market == "18h" and number(round_number) not in (1, 2, 3, 4):
            incomplete.append("missing_round")
        participants = p.get("participants")
        if market == "group" and (not isinstance(participants, list) or len(set(map(str, participants))) < 3 or not p.get("group_id") or p.get("player_key") not in participants):
            incomplete.append("missing_group_members")
        recorded_times = sorted({str(item[0]["row"].get("created_at") or "") for item in items})
        if len(recorded_times) > 1:
            incomplete.append("ambiguous_quote_repetition")
        if market in {"unspecified", "other"}:
            incomplete.append("unspecified_contract")
        if not p.get("player_key") or market in {"18h", "72h"} and not p.get("opponent_key"):
            incomplete.append("missing_participant")
        if not p.get("created_at"):
            incomplete.append("missing_recorded_time")
        if not event:
            issues.add("unresolved_event")
        price = number(p.get("market_odds"))
        if price is None or abs(price) < 100 or not p.get("market_book"):
            incomplete.append("missing_or_invalid_quote")
        issues.update(incomplete)
        recovery_links = []
        for obs, _, _ in items:
            saved = obs["row"]
            candidate_key = (obs["source_id"], saved.get("tournament_id"), saved.get("bet_type"),
                             saved.get("player_key"), saved.get("opponent_key"), normalized(saved.get("market_book")),
                             number(saved.get("market_odds")))
            for ledger in recovery_candidates.get(candidate_key, []):
                saved_lane = {"lab_sandbox": "lab"}.get(saved.get("source"), saved.get("source"))
                if ledger.get("lane") != saved_lane or ledger.get("model_variant") != saved.get("model_variant"):
                    continue
                if event and (str(ledger.get("event_id")) != str(event.get("provider_event_id")) or ledger.get("year") != event["year"]):
                    continue
                if ledger.get("model_config_hash") and ledger["model_config_hash"] != saved.get("model_config_hash"):
                    continue
                # A candidate is an exclusion signal, never proof that this ledger
                # primary key identifies this pick. Restoration times are not quotes.
                if ledger["source_origin"] == "restore" or ledger.get("created_at") == saved.get("created_at"):
                    issues.add("recovery_lineage_candidate")
                    recovery_links.append({"source_id": ledger["source_id"], "ordinal": ledger["ordinal"],
                                           "row_sha256": ledger["row_sha256"], "origin": ledger["source_origin"]})
        probability = number(p.get("model_prob"))
        if probability is None or not 0 <= probability <= 1:
            issues.add("missing_or_invalid_probability")
        all_outcomes = {}
        for obs, _, os in items:
            for o in os:
                all_outcomes[(o["source_id"], o["ordinal"])] = o
                links.append({"decision_id": key, "source_id": o["source_id"], "table": "pick_outcomes",
                              "ordinal": o["ordinal"], "row_sha256": o["row_sha256"]})
        values = [outcome_value(o["row"]) for o in all_outcomes.values()]
        signatures = {(v[0], v[1], v[2]) for v in values}
        for v in values:
            issues.update(v[3])
        # A disagreement in recorded finish/price is material even if profit agrees.
        for field in ("hit", "actual_finish", "odds_decimal"):
            present = {canonical(o["row"].get(field)) for o in all_outcomes.values() if o["row"].get(field) is not None}
            if len(present) > 1:
                issues.add("changed_outcome_" + field)
        if len(signatures) > 1:
            issues.add("changed_settlement")
        if signatures:
            settlement, profit, stake = next(iter(sorted(signatures, key=repr)))
        else:
            settlement, profit, stake = "ungraded", None, None
        # Matchup win/loss grading must agree with the actual stored quote.
        if market in {"72h", "18h"} and price is not None and abs(price) >= 100:
            decimal = 1 + (price / 100 if price > 0 else 100 / -price)
            for o in all_outcomes.values():
                out_decimal = number(o["row"].get("odds_decimal"))
                if out_decimal is not None and not math.isclose(out_decimal, decimal, abs_tol=0.011):
                    issues.add("settlement_quote_mismatch")
        timing = chronology(p.get("created_at"), event)
        if timing == "restore_placeholder":
            issues.add("restore_placeholder")
        conflict_issues = {i for i in issues if i.startswith("changed_") or i in {
            "loss_exceeds_stake", "void_has_nonzero_profit", "contradictory_matchup_result",
            "hit_disagrees_with_finish", "hit_disagrees_with_profit", "settlement_quote_mismatch"}}
        status = "conflict" if conflict_issues else "unresolved_event" if not event else "incomplete" if incomplete else "consistent"
        if status == "conflict":
            settlement, profit, stake = "conflict", None, None
        elapsed = bool(event and event["ends_on"] < cutoff)
        performance = status == "consistent" and elapsed and settlement in {"win", "loss", "zero_return"} and stake is not None and stake > 0
        eligible = bool(performance and timing == "recorded_before_event" and price is not None
                        and abs(price) >= 100 and probability is not None and 0 <= probability <= 1
                        and p.get("market_book") and not issues)
        d = {
            "decision_id": key, "event_key": event["key"] if event else None,
            "event_name": event["name"] if event else "Unresolved event",
            "season": event["year"] if event else None, "event_start": event["starts_on"] if event else None,
            "event_end": event["ends_on"] if event else None, "market": market,
            "lane": p.get("source") or "unknown", "player": p.get("player_key"), "opponent": p.get("opponent_key"),
            "player_display": p.get("player_display"), "opponent_display": p.get("opponent_display"),
            "book": p.get("market_book"), "odds": price, "probability": probability, "ev": number(p.get("ev")),
            "model_variant": p.get("model_variant"), "model_config_hash": p.get("model_config_hash"),
            "recorded_at": p.get("created_at") if len(recorded_times) == 1 else None,
            "recorded_times": recorded_times, "round": round_number, "participants": p.get("participants"),
            "group_id": p.get("group_id"), "status": status, "settlement": settlement, "profit": profit, "stake": stake,
            "return_units": profit / stake if profit is not None and stake is not None and stake > 0 else None,
            "issues": sorted(issues), "chronology": timing, "eligible_for_retrospective_selection": eligible,
            "included_in_paper_record": performance, "observation_count": len(items),
            "source_count": len({item[0]["source_id"] for item in items}), "outcome_observation_count": len(all_outcomes),
            "recovery_lineage_candidates": recovery_links,
        }
        decisions.append(d)
    card_groups = {digest([c["input_sha256"], c["line"]]): c for c in cards}
    def card_market(card):
        return "18h" if card["market"] == "18h_round_unknown" else card["market"]
    issues_count = Counter(i for d in decisions for i in d["issues"])
    def metrics(ds):
        accepted = [d for d in ds if d["included_in_paper_record"]]
        stake = sum(d["stake"] for d in accepted)
        profit = sum(d["profit"] for d in accepted)
        return {"records": len(ds), "events": len({d["event_key"] for d in ds if d["event_key"]}),
                "wins": sum(d["settlement"] == "win" for d in accepted), "losses": sum(d["settlement"] == "loss" for d in accepted),
                "zero_return": sum(d["settlement"] == "zero_return" for d in accepted),
                "void": sum(d["settlement"] == "void" for d in ds), "ungraded": sum(d["settlement"] in {"ungraded", "unknown"} for d in ds),
                "conflicts": sum(d["status"] == "conflict" for d in ds),
                "missing_round": sum("missing_round" in d["issues"] for d in ds),
                "incomplete": sum(any(i in d["issues"] for i in ("missing_round", "missing_group_members", "unspecified_contract", "missing_participant", "missing_recorded_time", "missing_or_invalid_quote", "ambiguous_quote_repetition")) for d in ds),
                "settled": len(accepted), "profit": round(profit, 6) if accepted else None,
                "stake": round(stake, 6) if accepted else None, "roi": profit / stake if stake else None,
                "selection_eligible": sum(d["eligible_for_retrospective_selection"] for d in ds)}
    lane_names = {"cockpit": "dashboard", "lab_sandbox": "lab"}
    markets = [{"key": k, "label": label, "lanes": [dict(lane=lane_names.get(lane, lane), **metrics([d for d in decisions if d["market"] == k and d["lane"] == lane]))
                for lane in sorted({"cockpit", "lab_sandbox"} | {d["lane"] for d in decisions})]} for k, label in MARKETS.items()]
    events = []
    for e in sorted(calendar, key=lambda e: (e["starts_on"], e["key"])):
        ds = [d for d in decisions if d["event_key"] == e["key"]]
        cs = [c for c in card_groups.values() if c.get("canonical_event_key") == e["key"]]
        counts = Counter(d["market"] for d in ds)
        for c in cs:
            counts.setdefault(card_market(c), 0)
        events.append({"key": e["key"], "name": e["name"], "starts_on": e["starts_on"], "ends_on": e["ends_on"],
                       "state": "elapsed" if e["ends_on"] < cutoff else "upcoming", "cards": len(cs),
                       **{k: v for k, v in metrics(ds).items() if k in {"records", "conflicts", "incomplete", "selection_eligible"}},
                       "markets": [{"key": k, "records": n, "cards": sum(card_market(c) == k for c in cs)} for k, n in sorted(counts.items())],
                       "source_url": e["source_url"]})
    report = {"schema_version": 1, "as_of": cutoff, "basis": "stored_paper_records",
              "coverage": {"source_generations": sum(not s.get("recovery_method") for s in vault["sources"].values()), "core_observations": len(vault["rows"]),
                           "pick_observations": len(by_table["picks"]), "decision_groups": len(decisions),
                           "calendar_elapsed_events": sum(e["state"] == "elapsed" for e in events),
                           "events_with_picks": sum(e["records"] > 0 for e in events), "events_with_cards": sum(e["cards"] > 0 for e in events),
                           "unresolved_events": len({(x[0]["source_id"], x[0]["row"].get("tournament_id")) for items in groups.values() for x in items if x[1] is None}),
                           "conflict_groups": sum(d["status"] == "conflict" for d in decisions),
                           "incomplete_contract_groups": sum(d["status"] == "incomplete" for d in decisions),
                           "selection_eligible": sum(d["eligible_for_retrospective_selection"] for d in decisions),
                           "unreadable_sources": len({sid for (sid, _), stream in vault["streams"].items() if stream.get("state") == "partial"}),
                           "salvaged_observations": len(salvage), "salvaged_exact_payload_matches": salvage_corroborated,
                           "salvaged_uncorroborated": len(salvage) - salvage_corroborated,
                           "partial_stream_observations_excluded": len(partial),
                           "fixture_pick_observations_excluded": len(excluded),
                           "card_observations": len(cards), "distinct_card_lines": len(card_groups)},
              "markets": markets, "events": events,
              "issues": [{"key": key, "label": key.replace("_", " ").capitalize(), "count": n} for key, n in issues_count.most_common()],
              "selection": {"status": "not_evaluated", "message": "No selection rule promoted.", "rules": []},
              "caveats": [
                  "This is a season-to-date inventory, not a complete record of bets placed. Amounts are stored paper results; quotes across books and model lanes are correlated.",
                  "Profit and W/L include only consistent, settled, complete contracts from elapsed events. Conflicting records and missing round/group identities are excluded; no favorable version is selected.",
                  "A zero return is not assumed to be a push. Voids, ungraded records and incomplete contracts remain separate. No outcome has been regraded.",
                  "Recorded-before-event means the saved calendar date precedes the official start date. It does not prove publication time, execution, timezone or price availability.",
                  "January 1 restoration timestamps and post-event imports cannot justify historical selection. Archived card rows provide coverage only; they do not supply settlements or stakes.",
                  "Historical configs changed across source generations. Retrospective selection comparisons are not untouched holdouts or proof about today's unchanged model.",
                  "Source rows and archives are preserved. Reconciliation is a separate reporting layer with source-local joins and explicit ambiguity.",
                  "Identical economic quotes with different recorded times are grouped as ambiguous repetitions and excluded from return totals; there is no evidence they were separate bets.",
                  "Damaged-database salvage is retained separately. Exact payload matches corroborate existing rows; unmatched salvage adds no profit or selection evidence.",
                  "Issue counts overlap: a round matchup can have both a missing round and a conflicting settlement. These columns are not disjoint buckets.",
              ]}
    return decisions, report, links


def write_store(path, vault, decisions, links, artifacts):
    """Create an exclusive derived file; never connect to a pre-existing database."""
    path = Path(path)
    with path.open("xb"):
        pass
    conn = sqlite3.connect(path)
    try:
        conn.executescript("""
            CREATE TABLE artifacts (name TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL);
            CREATE TABLE sources (source_id TEXT PRIMARY KEY, descriptor_json TEXT NOT NULL);
            CREATE TABLE source_streams (source_id TEXT, table_name TEXT, state_json TEXT, PRIMARY KEY(source_id,table_name));
            CREATE TABLE observations (source_id TEXT, table_name TEXT, ordinal INTEGER, row_sha256 TEXT, payload_json TEXT, envelope_json TEXT,
                                       PRIMARY KEY(source_id,table_name,ordinal));
            CREATE TABLE decisions (decision_id TEXT PRIMARY KEY, event_key TEXT, market TEXT, lane TEXT, status TEXT, decision_json TEXT);
            CREATE TABLE provenance_links (decision_id TEXT, source_id TEXT, table_name TEXT, ordinal INTEGER, row_sha256 TEXT,
                                           PRIMARY KEY(decision_id,source_id,table_name,ordinal));
            CREATE INDEX decisions_market ON decisions(market,lane);
        """)
        conn.executemany("INSERT INTO artifacts VALUES (?,?,?)", [(a["name"], a["sha256"], a["bytes"]) for a in artifacts])
        conn.executemany("INSERT INTO sources VALUES (?,?)", [(sid, canonical(s)) for sid, s in vault["sources"].items()])
        conn.executemany("INSERT INTO source_streams VALUES (?,?,?)", [(sid, table, canonical(s)) for (sid, table), s in vault["streams"].items()])
        conn.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?)", [(o["source_id"], o["table"], o["ordinal"], o["row_sha256"], canonical(o["row"]), canonical(o)) for o in vault["rows"]])
        conn.executemany("INSERT INTO decisions VALUES (?,?,?,?,?,?)", [(d["decision_id"], d["event_key"], d["market"], d["lane"], d["status"], canonical(d)) for d in decisions])
        conn.executemany("INSERT OR IGNORE INTO provenance_links VALUES (?,?,?,?,?)", [(link["decision_id"], link["source_id"], link["table"], link["ordinal"], link["row_sha256"]) for link in links])
        conn.commit()
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Derived store failed integrity check")
    finally:
        conn.close()
